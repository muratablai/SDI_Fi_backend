#!/usr/bin/env python3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
import pandas as pd

EXCEL_PATH = Path("../data/Anexe facturare mai 2025 v1.xlsx")
SHEET = "Preturi si tarife"
OUT_JSON = Path("../data/tariffs_seed.json")

# Column names we must detect on the HEADER ROW (case-insensitive)
REQ_COL_TARIF_ID = "tarif id"
REQ_COL_DESC     = "denumire servicii facturate"
REQ_COL_BILLTYPE = "billing type"

# Columns to IGNORE as operators
EXCLUDE_HEADERS_LOWER = {REQ_COL_TARIF_ID, REQ_COL_DESC, REQ_COL_BILLTYPE, "" , "unnamed"}

def _norm(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip()

def _find_header_row(df: pd.DataFrame) -> Optional[int]:
    """
    Scan the first ~10 rows to find a row that contains 'Tarif ID' (case-insensitive).
    Return the 0-based row index, or None.
    """
    check_rows = min(len(df), 12)
    for ridx in range(check_rows):
        row = df.iloc[ridx].tolist()
        lowers = [_norm(c).lower() for c in row]
        if any(REQ_COL_TARIF_ID == c for c in lowers):
            return ridx
    return None

def _pick_units_row(df: pd.DataFrame, header_row_idx: int) -> Optional[int]:
    """
    If the next row contains things like 'RON'/'kWh', treat it as units row.
    Otherwise, return None.
    """
    units_idx = header_row_idx + 1
    if units_idx >= len(df):
        return None
    vals = [_norm(x).lower() for x in df.iloc[units_idx].tolist()]
    score = sum(int(("ron" in v) or ("kwh" in v) or ("lei" in v)) for v in vals)
    return units_idx if score >= 1 else None

def _lower_list(xs: List[str]) -> List[str]:
    return [x.lower() for x in xs]

def _is_operator_header(h: str) -> bool:
    hl = h.lower()
    if hl in EXCLUDE_HEADERS_LOWER:
        return False
    # ignore excel "Unnamed: xx"
    if hl.startswith("unnamed"):
        return False
    return True

def main():
    if not EXCEL_PATH.exists():
        print(f"[tariffs] ERROR: Excel not found: {EXCEL_PATH}")
        return

    # Read raw (no header), we’ll discover header row manually
    raw = pd.read_excel(EXCEL_PATH, sheet_name=SHEET, header=None, dtype=object)
    if raw.empty:
        print("[tariffs] ERROR: empty sheet")
        return

    header_row_idx = _find_header_row(raw)
    if header_row_idx is None:
        print("[tariffs] ERROR: could not find 'Tarif ID' header row in first 12 rows.")
        return

    headers = [_norm(x) for x in raw.iloc[header_row_idx].tolist()]
    lowers  = [h.lower() for h in headers]

    # Validate presence of required headers
    try:
        id_idx   = lowers.index(REQ_COL_TARIF_ID)
        desc_idx = lowers.index(REQ_COL_DESC)
        bill_idx = lowers.index(REQ_COL_BILLTYPE)
    except ValueError:
        print("[tariffs] ERROR: could not find required columns on detected header row.")
        print("          headers found:", headers)
        return

    # Optional units row
    units_idx = _pick_units_row(raw, header_row_idx)
    units_row = [_norm(x) for x in (raw.iloc[units_idx].tolist() if units_idx is not None else [])]

    # Data starts after header (+ units row if present)
    start_row = header_row_idx + (2 if units_idx is not None else 1)
    data = raw.iloc[start_row:].reset_index(drop=True)

    # Operator columns = those not excluded
    operator_cols: List[int] = []
    for i, h in enumerate(headers):
        if _is_operator_header(h):
            operator_cols.append(i)

    if not operator_cols:
        print("[tariffs] WARNING: no operator columns detected. Will still write codes & descriptions.")
    else:
        print(f"[tariffs] Detected operator columns: {[headers[i] for i in operator_cols]}")

    tariffs: List[Dict[str, Any]] = []
    for _, row in data.iterrows():
        code = _norm(row[id_idx])
        if not code or not code.upper().startswith("T"):  # Keep only T*, e.g. T1, T36
            continue

        desc = _norm(row[desc_idx]) or None
        billtype = _norm(row[bill_idx]) or None

        # Pick unit from first operator column that has a non-empty unit cell on units row
        unit: Optional[str] = None
        if units_idx is not None:
            for i in operator_cols:
                u = _norm(units_row[i]) if i < len(units_row) else ""
                if u:
                    unit = u
                    break

        # Collect operator prices from operator columns
        operator_prices: Dict[str, float] = {}
        for i in operator_cols:
            op_name = headers[i]
            v_raw = row[i]
            if pd.isna(v_raw):
                continue
            try:
                price = float(str(v_raw).replace(",", "."))
                operator_prices[op_name] = price
            except Exception:
                continue

        tariffs.append({
            "code": code,
            "description": desc,
            "unit": unit,
            "billing_type": billtype,
            "operator_prices": operator_prices or None,
            "active": True,
        })

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(tariffs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[tariffs] OK: exported {len(tariffs)} tariffs -> {OUT_JSON}")

if __name__ == "__main__":
    main()
