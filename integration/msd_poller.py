# integration/msd_poller.py
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Dict
from integration.azure_file_gateway import AzureFileGateway
from integration.error_parser import parse_partner_error_csv
from models import BillingDocument, BillingLine, BillingIntegrationError, BillingEvent  # drop BillingEvent if you don't have it

UTC = timezone.utc

PAT_LINES  = re.compile(r"^RNEW_InvoiceLines_(?P<id>[^_]+)_", re.IGNORECASE)
PAT_PDFS   = re.compile(r"^RNEW_InvoicePDF_(?P<id>[^_]+)_",  re.IGNORECASE)
PAT_NUM    = re.compile(r"^RNEW_InvoiceNumbers_(?P<id>[^.]+)\.csv$", re.IGNORECASE)

async def poll_outcomes(
    gw: AzureFileGateway,
    *,
    dir_lines: str,
    dir_pdfs: str,
    dir_numbers: str,
) -> Dict:
    files_ok = set()
    files_err = set()
    numbers_updated = 0
    errors_parsed = 0

    # Processed/Error – lines
    processed_lines = gw.list_files(f"{dir_lines}/Processed")
    error_lines     = gw.list_files(f"{dir_lines}/Error")

    # Processed/Error – pdfs
    processed_pdfs  = gw.list_files(f"{dir_pdfs}/Processed")
    error_pdfs      = gw.list_files(f"{dir_pdfs}/Error")

    for f in processed_lines:
        m = PAT_LINES.match(f.name)
        if m: files_ok.add(m.group("id"))
    for f in processed_pdfs:
        m = PAT_PDFS.match(f.name)
        if m: files_ok.add(m.group("id"))

    for f in error_lines:
        m = PAT_LINES.match(f.name)
        if m: files_err.add(m.group("id"))
    for f in error_pdfs:
        m = PAT_PDFS.match(f.name)
        if m: files_err.add(m.group("id"))

    # Update doc status for OK/ERR files
    for did in files_ok:
        doc = await BillingDocument.get_or_none(id=did)
        if doc and doc.status in ("EXPORTED", "READY"):
            doc.status = "FILESOK"
            await doc.save()
            try:
                await BillingEvent.create(document=doc, kind="FILES_OK", payload={})
            except Exception:
                pass

    for did in files_err:
        doc = await BillingDocument.get_or_none(id=did)
        if doc and doc.status in ("READY", "EXPORTED", "FILESOK"):
            doc.status = "ACKERR"
            # Map partner error summary into ack_* fields (optional)
            doc.ack_error_code = "FILE_ERROR"
            doc.ack_error_message = "Partner moved file to Error."
            await doc.save()
            try:
                await BillingEvent.create(document=doc, kind="FILES_ERROR", payload={})
            except Exception:
                pass

    # Parse line-level error CSVs
    for f in error_lines:
        m = PAT_LINES.match(f.name)
        if not m:
            continue
        did = m.group("id")
        doc = await BillingDocument.get_or_none(id=did)
        if not doc:
            continue

        content = gw.download_bytes(f"{dir_lines}/Error", f.name)
        parsed = parse_partner_error_csv(content)
        if not parsed:
            await BillingIntegrationError.create(
                document=doc,
                line=None,
                partner="MSD",
                source_filename=f.name,
                export_seq=None,
                error_code=None,
                field_name=None,
                message="File rejected; no line details.",
                severity="ERROR",
                raw_row=None,
            )
            errors_parsed += 1
            continue

        # Correlate by export_seq → BillingLine.id
        lines = await BillingLine.filter(document_id=did).values("id", "export_seq")
        by_seq = {r["export_seq"]: r["id"] for r in lines if r["export_seq"] is not None}

        for e in parsed:
            line_id = by_seq.get(e.get("export_seq"))
            await BillingIntegrationError.create(
                document_id=did,
                line_id=line_id,
                partner="MSD",
                source_filename=f.name,
                export_seq=e.get("export_seq"),
                error_code=e.get("error_code"),
                field_name=e.get("field_name"),
                message=e.get("message"),
                severity=e.get("severity") or "ERROR",
                raw_row=e.get("raw_row"),
            )
            errors_parsed += 1

    # Grab invoice numbers
    numbers_files = gw.list_files(f"{dir_numbers}/Processed")  # if MSD drops in Source first, look there
    for f in numbers_files:
        m = PAT_NUM.match(f.name)
        if not m:
            continue
        did = m.group("id")
        doc = await BillingDocument.get_or_none(id=did)
        if not doc:
            continue

        content = gw.download_bytes(f"{dir_numbers}/Processed", f.name).decode("utf-8", errors="ignore")
        first_line = content.strip().splitlines()[0] if content.strip() else ""
        # Simple parse: first token is the number
        external_no = first_line.split(",")[0].strip() if first_line else ""
        if external_no:
            doc.ack_bill_number = external_no
            doc.ack_received_at = datetime.now(tz=UTC)
            if doc.status != "ACKERR":
                doc.status = "ACKOK"
            await doc.save()
            try:
                await BillingEvent.create(document=doc, kind="ACK_OK", payload={"number": external_no})
            except Exception:
                pass
            numbers_updated += 1

    return {
        "files_ok": len(files_ok),
        "files_error": len(files_err),
        "errors_parsed": errors_parsed,
        "numbers_updated": numbers_updated,
    }
