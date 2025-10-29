# integration/error_parser.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import csv, io

def _find_col(header: List[str], keys: List[str]) -> Optional[int]:
    h = [c.strip().lower() for c in header]
    for i, name in enumerate(h):
        for k in keys:
            if k in name:
                return i
    return None

def parse_partner_error_csv(content: bytes) -> List[Dict[str, Any]]:
    """
    Normalizes error CSV rows into:
      { export_seq, field_name, error_code, message, severity, raw_row }
    """
    text = content.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    header = rows[0]
    body = rows[1:]

    idx_seq  = _find_col(header, ["row", "line", "seq", "lineno", "position"])
    idx_code = _find_col(header, ["code", "error code"])
    idx_msg  = _find_col(header, ["message", "error", "reason", "description"])
    idx_field= _find_col(header, ["field", "column"])
    idx_sev  = _find_col(header, ["severity", "level", "type"])

    out: List[Dict[str, Any]] = []
    for r in body:
        try:
            seq = int(r[idx_seq]) if idx_seq is not None and r[idx_seq].strip() else None
        except Exception:
            seq = None
        out.append({
            "export_seq": seq,
            "field_name": (r[idx_field].strip() if idx_field is not None else None),
            "error_code": (r[idx_code].strip() if idx_code is not None else None),
            "message":    (r[idx_msg].strip()  if idx_msg  is not None else None),
            "severity":   (r[idx_sev].strip()  if idx_sev  is not None else "ERROR"),
            "raw_row":    {header[i]: r[i] for i in range(min(len(header), len(r)))},
        })
    return out
