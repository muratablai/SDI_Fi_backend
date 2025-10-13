# tools/merge_meter_constants.py
import json
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

VALIDARE_PATH = Path("../data/Validare finala contorizari.xlsx")
METERS_JSON = Path("../data/meters_seed.json")

# Put your best-guess sheet & column names here:
SHEET_CANDIDATES = ["Centralizator", "contoare"]
SERIAL_COL_CANDS = ["Serie contor", "Seria contor", "SN", "Serie", "S/N"]
CONST_COL_CANDS  = ["Constanta", "Constant", "Factor", "C.T.", "CT", "K"]

def pick_column(df, candidates) -> Optional[str]:
    lows = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lows:
            return lows[key]
    # try contains
    for c in df.columns:
        if any(key in str(c).lower() for key in [x.lower() for x in candidates]):
            return c
    return None

def build_constants_map() -> Dict[str, float]:
    if not VALIDARE_PATH.exists():
        print(f"[merge_constants] Missing {VALIDARE_PATH}, defaulting to empty map.")
        return {}
    xls = pd.ExcelFile(VALIDARE_PATH)
    for sheet in SHEET_CANDIDATES:
        if sheet not in xls.sheet_names:
            continue
        df = pd.read_excel(xls, sheet_name=sheet, dtype=object)
        ser_col = pick_column(df, SERIAL_COL_CANDS)
        k_col   = pick_column(df, CONST_COL_CANDS)
        if not ser_col or not k_col:
            continue
        m: Dict[str, float] = {}
        for _, r in df.iterrows():
            sn = str(r.get(ser_col) or "").strip()
            if not sn:
                continue
            try:
                k = float(str(r.get(k_col)).replace(",", "."))
            except Exception:
                continue
            if k > 0:
                m[sn] = k
        if m:
            print(f"[merge_constants] Found {len(m)} constants in sheet '{sheet}' using cols ({ser_col}, {k_col}).")
            return m
    print("[merge_constants] No constants found in candidate sheets/columns.")
    return {}

def main():
    if not METERS_JSON.exists():
        print(f"[merge_constants] Missing {METERS_JSON}")
        return
    meters = json.loads(METERS_JSON.read_text(encoding="utf-8"))
    const_map = build_constants_map()
    updated = 0
    for m in meters:
        sn = str(m.get("name") or "").strip()
        if sn in const_map:
            m["constant"] = const_map[sn]
            updated += 1
        else:
            m.setdefault("constant", 1.0)  # default
    METERS_JSON.write_text(json.dumps(meters, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[merge_constants] Updated {updated} meters with constants. Defaulted the rest to 1.0.")

if __name__ == "__main__":
    main()
