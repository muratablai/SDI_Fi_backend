# services/csv_builder.py
from __future__ import annotations
from typing import List
import csv, io
from models import BillingDocument, BillingLine

async def build_csv_bytes(doc: BillingDocument, lines: List[BillingLine]) -> bytes:
    """
    Minimal CSV builder — replace the row mapping with your real mapping or external YAML.
    Also sets export_seq (1-based) on each line to match partner error rows later.
    """
    out = io.StringIO(newline="")
    w = csv.writer(out, delimiter=",", quotechar='"')

    header = ["Line No", "Meter", "Tariff", "Unit", "Quantity", "Unit Price (cents)", "VAT %", "Amount (cents)"]
    w.writerow(header)

    seq = 1
    for ln in lines:
        w.writerow([
            seq,
            ln.meter_no,
            ln.tariff_code,
            ln.unit,
            str(ln.quantity),
            ln.unit_price_cents,
            str(ln.vat_rate_percent),
            ln.amount_cents,
        ])
        ln.export_seq = seq
        seq += 1

    await BillingLine.bulk_update(lines, fields=["export_seq"])
    return out.getvalue().encode("utf-8")
