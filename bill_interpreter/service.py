# bill_interpreter/service.py
from __future__ import annotations
import asyncio
import hashlib
from datetime import datetime, time
from pathlib import Path
import shutil
from typing import Optional
import re
import unicodedata

from tortoise.transactions import in_transaction

from models import DataSource, IngestBatch, MeterDataRaw, MeterData, OdPod
from models import Supplier, SupplierBill, SupplierBillLine, SupplierBillMeasurement
from bill_interpreter.mappings import map_channel
from bill_interpreter.ocr_hidroelectrica import build_invoice

INBOX_DIR = Path("data/bills/inbox")
STORE_DIR = Path("data/bills/store")
STORE_URL_PREFIX = "/files/bills"  # served by StaticFiles

INBOX_DIR.mkdir(parents=True, exist_ok=True)
STORE_DIR.mkdir(parents=True, exist_ok=True)

def _clean_cell(x):
    if x is None:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()

def _normkey(s: str | None) -> str:
    if not s:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _build_header_index(header_row: list[str]) -> dict[str, int]:
    # normalize header row first (kills \n)
    header_row = [_clean_cell(h) for h in (header_row or [])]
    idx = {}
    for i, h in enumerate(header_row):
        k = _normkey(h)
        if k and k not in idx:
            idx[k] = i
    return idx

def _col_by_alias(row: list[str], header_row: list[str], aliases: list[str], default=None):
    if not header_row:
        return default
    hidx = _build_header_index(header_row)

    for a in aliases:
        k = _normkey(a)
        if k in hidx:
            i = hidx[k]
            return _clean_cell(row[i]) if i < len(row) else default

    for a in aliases:
        ak = _normkey(a)
        if not ak:
            continue
        for hk, i in hidx.items():
            if ak in hk:
                return _clean_cell(row[i]) if i < len(row) else default

    return default

def _normf(x, *, dbg_label: str | None = None):
    if x in (None, "", "-", "NaN"):
        return None
    s = str(x).strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^0-9,.\-]", "", s)
    if not s or s in (",", ".", "-"):
        return None
    try:
        if "," in s and "." in s:
            s2 = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s2 = s.replace(",", ".")
        else:
            s2 = s
        return float(s2)
    except Exception:
        if dbg_label:
            print(f"[bill_interpreter] ⚠️  _normf failed for {dbg_label!r}: raw={x!r} cleaned={s!r}")
        return None

def _parse_date(s: Optional[str]):
    if not s:
        return None
    s = s.replace("/", ".").replace("-", ".")
    parts = [p for p in s.split(".") if p]
    if len(parts) < 3:
        return None
    dd, mm, yy = parts[0], parts[1], parts[2]
    if len(yy) == 2:
        yy = "20" + yy
    return datetime(int(yy), int(mm), int(dd)).date()

def _zero_defaults():
    return dict(
        active_import=0.0, active_import_t1=0.0, active_import_t2=0.0, active_import_t3=0.0, active_import_t4=0.0,
        active_export=0.0, active_export_t1=0.0, active_export_t2=0.0, active_export_t3=0.0, active_export_t4=0.0,
        reactive_import=0.0, reactive_export=0.0,
        reactive_q1=0.0, reactive_q2=0.0, reactive_q3=0.0, reactive_q4=0.0,
        power_import=0.0, power_export=0.0,
        constant=None, quality="GOOD", estimated=False, interpolated=False, reset_detected=False
    )

async def _process_pdf(supplier_code: str, supplier_name: str, src_path: Path):
    print(f"[bill_interpreter] 🧾 Processing new bill: {src_path.name}")
    raw_bytes = src_path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    dest_name = src_path.name
    dest_path = STORE_DIR / dest_name
    if not dest_path.exists():
        shutil.copy2(src_path, dest_path)
    pdf_url = f"{STORE_URL_PREFIX}/{dest_name}"

    ds, _ = await DataSource.get_or_create(
        code="SUPPLIER_BILL",
        defaults={"name": "Supplier Bill OCR", "priority": 5, "active": True},
    )
    batch = await IngestBatch.create(source=ds, file_name=dest_name, file_hash=sha256)

    print(f"[bill_interpreter] Running OCR on {dest_name} ...")
    invoice = build_invoice(str(dest_path))
    print(f"[bill_interpreter] ✅ OCR done for {dest_name}")

    g = invoice.get("general", {}) or {}
    issue = _parse_date(g.get("data"))
    series = g.get("serie")
    number = g.get("numar_factura") or dest_name
    supplier, _ = await Supplier.get_or_create(code=supplier_code, defaults={"name": supplier_name})

    async with in_transaction():
        bill = await SupplierBill.create(
            supplier=supplier,
            invoice_series=series,
            invoice_number=number,
            issue_date=issue,
            pdf_path=pdf_url,
            pdf_sha256=sha256,
            pdf_bytes_size=len(raw_bytes),
            ingest_batch=batch,
        )

        # detect POD
        for d in invoice.get("detailed", []):
            pod = d.get("POD") or d.get("pod")
            if pod:
                bill.pod_od = pod.strip()
                await bill.save()
                print(f"[bill_interpreter] Detected POD OD: {bill.pod_od}")
                break

        print(f"[bill_interpreter] 📥 Bill saved to DB: {number} ({series or 'no series'})")

        # ---------- Servicii facturate
        sf = invoice.get("servicii_facturate") or []
        if len(sf) > 1:
            header = [_clean_cell(h) for h in sf[0]]  # <<< normalize header (kills \n)
            SF_NAME_ALIASES    = ["denumire servicii", "denumire servicii facturate", "denumire"]
            SF_QTY_ALIASES     = ["cantitate facturata", "cantitate facturată", "cantitate", "cant"]
            SF_UM_ALIASES      = ["u.m.", "um", "unitate", "unit"]
            SF_PRICE_ALIASES   = ["pret unitar fara tva", "preț unitar fără tva", "pret unitar", "preț unitar"]
            SF_VALUE_ALIASES   = ["valoare fara tva", "valoare fără tva", "valoare", "valoare lei"]
            SF_PER_START_ALIAS = ["perioadă start", "perioada start", "perioada inceput"]
            SF_PER_END_ALIAS   = ["perioadă incheiere", "perioada incheiere", "perioada sfarsit"]

            for row in sf[1:]:
                if not row:
                    continue
                ps = _col_by_alias(row, header, SF_PER_START_ALIAS)
                pe = _col_by_alias(row, header, SF_PER_END_ALIAS)

                name  = _col_by_alias(row, header, SF_NAME_ALIASES) or str(row[0])
                qty   = _normf(_col_by_alias(row, header, SF_QTY_ALIASES), dbg_label="SF.qty")
                um    = _col_by_alias(row, header, SF_UM_ALIASES) or None
                price = _normf(_col_by_alias(row, header, SF_PRICE_ALIASES), dbg_label="SF.price")
                value = _normf(_col_by_alias(row, header, SF_VALUE_ALIASES), dbg_label="SF.value")

                await SupplierBillLine.create(
                    bill=bill,
                    name=name,
                    period_start=(_parse_date(ps) and datetime.combine(_parse_date(ps), time.min)),
                    period_end=(_parse_date(pe) and datetime.combine(_parse_date(pe), time.max)),
                    qty=qty,
                    unit=um,
                    price=price,
                    value=value,
                )

        # ---------- Masurari
        mas = invoice.get("masurari")
        if mas and len(mas) > 1:
            header = [_clean_cell(h) for h in mas[0]]  # <<< normalize header (kills \n)

            MAS_SERIE_ALIASES     = ["serie contor", "serie", "nr contor", "numar contor"]
            MAS_TIP_ALIASES       = ["tip energie", "tip energie facturata", "tip"]
            MAS_UM_ALIASES        = ["u.m.", "um", "unitate", "unit"]
            MAS_QTY_ALIASES       = ["cantitate de facturat", "cantitate facturata", "cantitate masurata", "cantitate măsurată", "cantitate"]
            MAS_IDX_OLD_ALIASES   = ["index vechi", "index initial", "index inceput"]
            MAS_IDX_NEW_ALIASES   = ["index nou", "index final", "index sfarsit"]
            MAS_METH_OLD_ALIASES  = ["mod stabilire vechi", "mod stabilire initial"]
            MAS_METH_NEW_ALIASES  = ["mod stabilire nou", "mod stabilire final"]
            MAS_PER_START_ALIASES = ["masurari perioada start", "masurari perioada inceput", "perioada facturare start", "perioada start"]
            MAS_PER_END_ALIASES   = ["masurari perioada final", "masurari perioada sfarsit", "perioada facturare final", "perioada incheiere", "perioada sfarsit"]

            for row in mas[1:]:
                meter_no = _col_by_alias(row, header, MAS_SERIE_ALIASES)
                tip      = _col_by_alias(row, header, MAS_TIP_ALIASES)
                channel  = map_channel(tip)

                ps = _col_by_alias(row, header, MAS_PER_START_ALIASES)
                pe = _col_by_alias(row, header, MAS_PER_END_ALIASES)
                dps = _parse_date(ps); dpe = _parse_date(pe)
                period_start = (dps and datetime.combine(dps, time.min)) or None
                period_end   = (dpe and datetime.combine(dpe, time.max)) or None

                idx_old  = _normf(_col_by_alias(row, header, MAS_IDX_OLD_ALIASES))
                idx_new  = _normf(_col_by_alias(row, header, MAS_IDX_NEW_ALIASES))
                meth_old = _col_by_alias(row, header, MAS_METH_OLD_ALIASES)
                meth_new = _col_by_alias(row, header, MAS_METH_NEW_ALIASES)

                qty_text = _col_by_alias(row, header, MAS_QTY_ALIASES)
                qty      = _normf(qty_text, dbg_label="MAS.qty")

                unit = (_col_by_alias(row, header, MAS_UM_ALIASES) or "").strip().upper()
                if not unit:
                    unit = "KWH" if channel and "active" in channel else "KVARH"

                m = await SupplierBillMeasurement.create(
                    bill=bill,
                    meter_no=(meter_no or None),
                    channel=channel,
                    period_start=period_start,
                    period_end=period_end,
                    index_old=idx_old,
                    index_new=idx_new,
                    method_old=(meth_old or None),
                    method_new=(meth_new or None),
                    energy_value=qty,
                    unit=unit,
                )

                # Backfill MeterDataRaw (sparse)
                energy = m.energy_value if m.energy_value is not None else (
                    (m.index_new - m.index_old) if (m.index_new is not None and m.index_old is not None) else None
                )
                if m.meter_no and energy is not None:
                    payload = dict(
                        meter_no=m.meter_no,
                        timestamp=period_end or period_start or datetime.utcnow(),
                        bucket_ts=None,
                        constant=None,
                        source_id=ds.id,
                        batch_id=batch.id,
                        quality="GOOD",
                        estimated=False, interpolated=False, reset_detected=False, duplicate=False,
                    )
                    if channel == "active_import":      payload["active_import"]  = energy
                    elif channel == "active_export":    payload["active_export"]  = energy
                    elif channel == "reactive_import":  payload["reactive_import"] = energy
                    elif channel == "reactive_export":  payload["reactive_export"] = energy
                    await MeterDataRaw.create(**payload)

                    md = _zero_defaults()
                    md.update(dict(
                        meter_no=m.meter_no,
                        timestamp=payload["timestamp"],
                        chosen_source_code="SUPPLIER_BILL",
                    ))
                    if channel == "active_import":      md["active_import"]  = energy
                    elif channel == "active_export":    md["active_export"]  = energy
                    elif channel == "reactive_import":  md["reactive_import"] = energy
                    elif channel == "reactive_export":  md["reactive_export"] = energy
                    await MeterData.create(**md)

async def scan_once(supplier_code="HIDROELECTRICA", supplier_name="SPEEH HIDROELECTRICA SA") -> int:
    pdfs = list(INBOX_DIR.glob("*.pdf"))
    for p in pdfs:
        try:
            await _process_pdf(supplier_code, supplier_name, p)
            p.unlink(missing_ok=True)
        except Exception as e:
            print(f"[bill_interpreter] ❌ Failed processing {p.name}: {e}")
            pass
    return len(pdfs)

async def run_forever(poll_seconds: int = 15):
    print(f"[bill_interpreter] 🔁 Background bill watcher started (poll every {poll_seconds}s)")
    while True:
        try:
            pdfs = list(INBOX_DIR.glob("*.pdf"))
            if pdfs:
                print(f"[bill_interpreter] 📂 Found {len(pdfs)} file(s): {[p.name for p in pdfs]}")
                await scan_once()
            else:
                print("[bill_interpreter] (no new bills found)")
        except Exception as e:
            print(f"[bill_interpreter] ❌ Error during scan: {e}")
        await asyncio.sleep(poll_seconds)
