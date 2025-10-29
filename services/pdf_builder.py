# services/pdf_builder.py
from __future__ import annotations
from typing import List
from models import BillingDocument, BillingLine

async def build_pdf_bytes(doc: BillingDocument, lines: List[BillingLine]) -> bytes:
    """
    Replace with your real PDF renderer; this stub just returns text bytes.
    """
    txt = f"Invoice {doc.id}\nPeriod: {doc.period_start}..{doc.period_end}\nLines: {len(lines)}\n"
    return txt.encode("utf-8")
