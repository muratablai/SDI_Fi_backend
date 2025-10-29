# integration/msd_exporter.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, List

from models import BillingDocument, BillingLine, BillingEvent  # if you have BillingEvent; else remove
from integration.azure_file_gateway import AzureFileGateway
from services.csv_builder import build_csv_bytes
from services.pdf_builder import build_pdf_bytes

UTC = timezone.utc

def _csv_name(doc: BillingDocument, rev: int) -> str:
    end = doc.period_end.strftime("%Y%m%d")
    return f"RNEW_InvoiceLines_{doc.id}_{end}_v{rev}.csv"

def _pdf_name(doc: BillingDocument, rev: int) -> str:
    end = doc.period_end.strftime("%Y%m%d")
    return f"RNEW_InvoicePDF_{doc.id}_{end}_v{rev}.pdf"

async def export_document(doc_id: str, gw: AzureFileGateway, *, lines_dir: str, pdfs_dir: str) -> Dict:
    doc = await BillingDocument.get(id=doc_id).prefetch_related("lines")
    lines: List[BillingLine] = await BillingLine.filter(document_id=doc_id).order_by("id").all()

    # use attempts+1 as a light revision number
    rev = (doc.csv_attempts or 0) + 1

    csv_bytes = await build_csv_bytes(doc, lines)
    pdf_bytes = await build_pdf_bytes(doc, lines)

    csv_name = _csv_name(doc, rev)
    pdf_name = _pdf_name(doc, rev)

    gw.upload_bytes(f"{lines_dir}/Source", csv_name, csv_bytes)
    gw.upload_bytes(f"{pdfs_dir}/Source",  pdf_name,  pdf_bytes)

    # remember on lines which file they were in (for error correlation)
    for ln in lines:
        ln.last_export_filename = csv_name
    await BillingLine.bulk_update(lines, fields=["last_export_filename"])

    # update doc export fields (map to your names)
    now = datetime.now(tz=UTC)
    doc.csv_blob_url = f"{lines_dir}/Source/{csv_name}"   # store azure path here
    doc.csv_sent_at = now
    doc.csv_attempts = rev
    doc.csv_last_error = None

    doc.pdf_blob_url = f"{pdfs_dir}/Source/{pdf_name}"
    doc.pdf_sent_at = now
    doc.pdf_last_error = None

    doc.status = "EXPORTED"
    await doc.save()

    # If you don't have BillingEvent, remove the next line
    try:
        await BillingEvent.create(document=doc, kind="EXPORT", payload={"csv": csv_name, "pdf": pdf_name})
    except Exception:
        pass

    return {"csv": csv_name, "pdf": pdf_name, "revision": rev}
