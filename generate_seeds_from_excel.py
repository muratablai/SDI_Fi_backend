#!/usr/bin/env python3
import json, re, sys
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import pandas as pd

# ===== CONFIG =====
EXCEL_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/LV meters_13.05.2025 1.xlsm")
SHEET_NAME = "locatii JT"

# Column letters (1-indexed like Excel: A=1, W=23, Y=25)
POD_COL_LETTER = "W"  # POD SDI column (you said W)
LOC_NAME_COL_LETTER = "Y"  # Location name column (you said Y)

# If Project ID has a header, we’ll use it; otherwise, we can fall back to a letter here (optional)
PROJECT_ID_HEADER = "Project ID"   # preferred
PROJECT_ID_FALLBACK_LETTER = None  # e.g. "B" if needed

# Other helpful headers (optional); we’ll best-effort read them by name
SN_HEADER = "S/N"
COSEM_NAME_HEADER = "COSEM Device Name"
ADDRESS_HEADER = "Adresa"
TRAFO_HEADER = "Nr. Trafo"
BMC_HEADER = "BMC NR"
PVV_HEADER = "PVV NR"
PVC_HEADER = "PVC NR"

OUT_DIR = Path("data")
AREAS_JSON = OUT_DIR / "areas_seed.json"
LOCATIONS_JSON = OUT_DIR / "locations_seed.json"
METERS_JSON = OUT_DIR / "meters_seed.json"
# ==================

SERIAL_FLOAT_TAIL = re.compile(r"^\d+\.0$")

def letter_to_index(letter: str) -> int:
    """Excel column letter (A..Z..AA..) -> zero-based index."""
    letter = letter.strip().upper()
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - ord('A') + 1)
    return n - 1  # zero-based

def norm_str(x) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    s = str(x).strip()
    return s or None

def conv_pod(x) -> Optional[str]:
    s = norm_str(x)
    if not s:
        return None
    s = s.replace(" ", "")
    if SERIAL_FLOAT_TAIL.match(s):
        s = s[:-2]
    return s

def conv_sn(x) -> Optional[str]:
    s = norm_str(x)
    if not s:
        return None
    if SERIAL_FLOAT_TAIL.match(s):
        s = s[:-2]
    return s

def parse_project_id(val: object) -> Tuple[Optional[str], Optional[str]]:
    """
    '2206013-001 Rm Valcea Shopping City' -> ('2206013-001', 'Rm Valcea Shopping City')
    """
    s = norm_str(val)
    if not s:
        return None, None
    parts = s.split()
    code = parts[0]
    name = s[len(code):].strip(" -") or code
    return code, name

def main():
    try:
        import openpyxl  # ensures engine is present
    except ImportError:
        print("ERROR: missing 'openpyxl'. Install with: pip install openpyxl")
        sys.exit(1)

    if not EXCEL_PATH.exists():
        print(f"ERROR: Excel not found: {EXCEL_PATH}")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read the sheet (let pandas keep headers, but we’ll also access by column POSITION for W & Y)
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME, dtype=object)

    # ---------- Resolve key columns ----------
    # 1) POD SDI by letter (W)
    pod_idx = letter_to_index(POD_COL_LETTER)
    if pod_idx >= len(df.columns):
        print(f"ERROR: POD column {POD_COL_LETTER} (idx {pod_idx}) out of range. Sheet has {len(df.columns)} columns.")
        sys.exit(1)
    pod_series = df.iloc[:, pod_idx].map(conv_pod)

    # 2) Location NAME by letter (Y)
    locname_idx = letter_to_index(LOC_NAME_COL_LETTER)
    if locname_idx >= len(df.columns):
        print(f"ERROR: Location name column {LOC_NAME_COL_LETTER} (idx {locname_idx}) out of range. Sheet has {len(df.columns)} columns.")
        sys.exit(1)
    locname_series = df.iloc[:, locname_idx].map(norm_str)
    print(locname_series)

    # 3) Project ID: prefer header; else fallback to a letter if provided
    if PROJECT_ID_HEADER in df.columns:
        proj_series = df[PROJECT_ID_HEADER].map(norm_str)
    elif PROJECT_ID_FALLBACK_LETTER:
        proj_idx = letter_to_index(PROJECT_ID_FALLBACK_LETTER)
        if proj_idx >= len(df.columns):
            print(f"ERROR: Project ID fallback col {PROJECT_ID_FALLBACK_LETTER} out of range.")
            sys.exit(1)
        proj_series = df.iloc[:, proj_idx].map(norm_str)
    else:
        print("ERROR: Could not find 'Project ID' header. Set PROJECT_ID_FALLBACK_LETTER to a column letter.")
        print(f"Available headers: {list(df.columns)}")
        sys.exit(1)

    # Forward-fill Project ID to handle merged cells
    proj_series = proj_series.ffill()

    # Optional helpers by header (best-effort, safe if missing)
    sn_series = df[SN_HEADER].map(conv_sn) if SN_HEADER in df.columns else pd.Series([None]*len(df))
    cosem_series = df[COSEM_NAME_HEADER].map(norm_str) if COSEM_NAME_HEADER in df.columns else pd.Series([None]*len(df))
    addr_series = df[ADDRESS_HEADER].map(norm_str) if ADDRESS_HEADER in df.columns else pd.Series([None]*len(df))
    trafo_series = df[TRAFO_HEADER].map(norm_str) if TRAFO_HEADER in df.columns else pd.Series([None]*len(df))
    bmc_series = df[BMC_HEADER].map(norm_str) if BMC_HEADER in df.columns else pd.Series([None]*len(df))
    pvv_series = df[PVV_HEADER].map(norm_str) if PVV_HEADER in df.columns else pd.Series([None]*len(df))
    pvc_series = df[PVC_HEADER].map(norm_str) if PVC_HEADER in df.columns else pd.Series([None]*len(df))

    # Work dataframe
    work = pd.DataFrame({
        "_project": proj_series,
        "_pod": pod_series,
        "_locname": locname_series,
        "_sn": sn_series,
        "_cosem": cosem_series,
        "_addr": addr_series,
        "_trafo": trafo_series,
        "_bmc": bmc_series,
        "_pvv": pvv_series,
        "_pvc": pvc_series,
    })

    # Keep only rows that have a POD
    work = work[work["_pod"].notna()].copy()

    # ---------- Build AREAS ----------
    areas: Dict[str, Dict[str, Any]] = {}
    for _, r in work.iterrows():
        code, name = parse_project_id(r["_project"])
        if not code:
            continue
        if code not in areas:
            areas[code] = {
                "code": code,
                "name": name,
                "address": r["_addr"],
                "city": None,
                "county": None,
                "latitude": None,
                "longitude": None,
            }

    # ---------- Build LOCATIONS (keyed by POD SDI) ----------
    locations: Dict[str, Dict[str, Any]] = {}
    for _, r in work.iterrows():
        area_code, _ = parse_project_id(r["_project"])
        pod = r["_pod"]
        if not pod:
            continue
        loc_name = r["_locname"]  # <-- comes from column Y exactly

        # Optional role derivation from name
        role = None
        if loc_name:
            low = str(loc_name).lower()
            if low.startswith("cons"):
                role = "consumer"
            elif low.startswith("prod"):
                role = "producer"

        if pod not in locations:
            locations[pod] = {
                "pod_sdi": pod,
                "name": loc_name,        # <-- put column Y value here
                "role": role,
                "area_code": area_code,
                "trafo_no": r["_trafo"],
                "bmc_nr": r["_bmc"],
                "pvv_nr": r["_pvv"],
                "pvc_nr": r["_pvc"],
            }
        else:
            # merge missing fields if duplicate POD rows exist
            loc = locations[pod]
            for k, v in [
                ("name", loc_name),
                ("trafo_no", r["_trafo"]),
                ("bmc_nr", r["_bmc"]),
                ("pvv_nr", r["_pvv"]),
                ("pvc_nr", r["_pvc"]),
            ]:
                if not loc.get(k) and v:
                    loc[k] = v
            if role and not loc.get("role"):
                loc["role"] = role

    # ---------- Build METERS (dedupe by serial) ----------
    meters = []
    seen = set()
    for _, r in work.iterrows():
        area_code, _ = parse_project_id(r["_project"])
        pod = r["_pod"]
        meter_no = r["_sn"]
        if not meter_no:
            continue
        if meter_no in seen:
            continue
        seen.add(meter_no)
        meters.append({
            "meter_no": meter_no,
            "name": r["_cosem"],
            "pod_sdi": pod,
            "area_code": area_code,
        })

    # ---------- WRITE ----------
    AREAS_JSON.write_text(json.dumps(list(areas.values()), indent=2, ensure_ascii=False), encoding="utf-8")
    LOCATIONS_JSON.write_text(json.dumps(list(locations.values()), indent=2, ensure_ascii=False), encoding="utf-8")
    METERS_JSON.write_text(json.dumps(meters, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---------- SUMMARY ----------
    locs_per_area: Dict[str, int] = {}
    for loc in locations.values():
        code = loc["area_code"]
        if code:
            locs_per_area[code] = locs_per_area.get(code, 0) + 1

    print(f"[OK] Areas     : {len(areas)}  -> {AREAS_JSON}")
    print(f"[OK] Locations : {len(locations)} -> {LOCATIONS_JSON}")
    print(f"[OK] Meters    : {len(meters)} -> {METERS_JSON}")
    if locs_per_area:
        print("      Locations per Area (top 10):")
        for code, cnt in sorted(locs_per_area.items(), key=lambda x: (-x[1], x[0]))[:10]:
            print(f"        {code}: {cnt}")

if __name__ == "__main__":
    """
    Usage:
      pip install pandas openpyxl
      python generate_pod_seeds_by_letter.py
      # or
      python generate_pod_seeds_by_letter.py "C:\\path\\to\\LV meters_13.05.2025 1.xlsm"
    """
    main()
