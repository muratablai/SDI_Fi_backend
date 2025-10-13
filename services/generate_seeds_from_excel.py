#!/usr/bin/env python3
"""
Generate seed JSONs for Sites, OD PODs, SDI PODs, and Meters by
combining two Excel workbooks:

A) "Contorizare in SDI"      -> POD OD (col D) & POD SDI (col H), values start at row 4 (1-indexed)
B) "LV meters_13.05.2025 1"  -> Project/Site, POD SDI, meter S/N, meter name, etc.

Outputs (in ../data):
  - sites_seed.json
  - od_pods_seed.json
  - pods_seed.json
  - meters_seed.json
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from typing import Dict, Optional, Any, Tuple, List

import pandas as pd

# =========================
# CONFIG
# =========================

FILE_A = Path("../data/Anexe facturare mai 2025 v1.xlsx")
SHEET_A = "Contorizare in SDI"
POD_OD_COL_LETTER = "D"   # starts row 4 (1-indexed)
POD_SDI_COL_LETTER = "H"  # starts row 4 (1-indexed)

FILE_B = Path("../data/LV meters_13.05.2025 1.xlsm")
SHEET_B = "locatii JT"

B_POD_SDI_LETTER = "W"
B_LOC_NAME_LETTER = "Y"
B_PROJECT_ID_HEADER = "Project ID"
B_PROJECT_ID_FALLBACK_LETTER: Optional[str] = None  # if needed, e.g. "B"

B_SN_HEADER = "S/N"
B_COSEM_HEADER = "COSEM Device Name"
B_TRAFO_HEADER = "Nr. Trafo"
B_BMC_HEADER = "BMC NR"
B_PVV_HEADER = "PVV NR"
B_PVC_HEADER = "PVC NR"

OUT_DIR = Path("../data")
SITES_JSON = OUT_DIR / "sites_seed.json"
OD_PODS_JSON = OUT_DIR / "od_pods_seed.json"
PODS_JSON = OUT_DIR / "pods_seed.json"
METERS_JSON = OUT_DIR / "meters_seed.json"

# =========================
# Helpers
# =========================

SERIAL_FLOAT_TAIL = re.compile(r"^\d+\.0$")


def letter_to_index(letter: str) -> int:
    s = letter.strip().upper()
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def norm_str(x) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    s = str(x).strip()
    return s or None


def conv_pod_sdi(x) -> Optional[str]:
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


def conv_pod_od(x) -> Optional[str]:
    s = norm_str(x)
    if not s:
        return None
    if SERIAL_FLOAT_TAIL.match(s):
        s = s[:-2]
    return s


def strip_after_slash(s: str) -> str:
    """Return substring before first '/', if any."""
    i = s.find("/")
    return s[:i] if i >= 0 else s


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


# =========================
# Loaders
# =========================

def load_od_to_sdi_pairs(path: Path) -> Dict[str, str]:
    """
    From 'Contorizare in SDI' (A): row 4 onward, POD OD in D, POD SDI in H.
    Returns: { pod_od : pod_sdi }
    """
    if not path.exists():
        print(f"[ERR] File not found: {path}")
        sys.exit(1)

    df = pd.read_excel(path, sheet_name=SHEET_A, header=None, dtype=object)
    # start at row index 3 (1-indexed row 4)
    df = df.iloc[3:]

    od_idx = letter_to_index(POD_OD_COL_LETTER)
    sdi_idx = letter_to_index(POD_SDI_COL_LETTER)

    od_series = df.iloc[:, od_idx].map(conv_pod_od)
    sdi_series = df.iloc[:, sdi_idx].map(conv_pod_sdi)

    mapping: Dict[str, str] = {}
    for od, sdi in zip(od_series, sdi_series):
        if not od or not sdi:
            continue
        mapping[od] = sdi
    return mapping


def load_sdi_meter_and_site(path: Path):
    """
    From 'LV meters_13.05.2025 1.xlsm' (B): build
      - sites: {code,name}
      - pods: keyed by pod_sdi with site_code + metadata
      - meters: [{meter_no, name, pod_sdi, site_code}]
    """
    if not path.exists():
        print(f"[ERR] File not found: {path}")
        sys.exit(1)

    df = pd.read_excel(path, sheet_name=SHEET_B, dtype=object)

    pod_idx = letter_to_index(B_POD_SDI_LETTER)
    locname_idx = letter_to_index(B_LOC_NAME_LETTER)

    pod_series = df.iloc[:, pod_idx].map(conv_pod_sdi)
    locname_series = df.iloc[:, locname_idx].map(norm_str)

    if B_PROJECT_ID_HEADER in df.columns:
        proj_series = df[B_PROJECT_ID_HEADER].map(norm_str).ffill()
    elif B_PROJECT_ID_FALLBACK_LETTER:
        proj_idx = letter_to_index(B_PROJECT_ID_FALLBACK_LETTER)
        proj_series = df.iloc[:, proj_idx].map(norm_str).ffill()
    else:
        print(f"[ERR] Missing '{B_PROJECT_ID_HEADER}' column (and no fallback letter set).")
        sys.exit(1)

    # optional fields
    trafo_series = df[B_TRAFO_HEADER].map(norm_str) if B_TRAFO_HEADER in df.columns else pd.Series([None]*len(df))
    bmc_series = df[B_BMC_HEADER].map(norm_str) if B_BMC_HEADER in df.columns else pd.Series([None]*len(df))
    pvv_series = df[B_PVV_HEADER].map(norm_str) if B_PVV_HEADER in df.columns else pd.Series([None]*len(df))
    pvc_series = df[B_PVC_HEADER].map(norm_str) if B_PVC_HEADER in df.columns else pd.Series([None]*len(df))
    sn_series = df[B_SN_HEADER].map(conv_sn) if B_SN_HEADER in df.columns else pd.Series([None]*len(df))
    cosem_series = df[B_COSEM_HEADER].map(norm_str) if B_COSEM_HEADER in df.columns else pd.Series([None]*len(df))

    # build sites
    sites: Dict[str, Dict[str, Any]] = {}
    for proj in proj_series:
        code, name = parse_project_id(proj)
        if code and code not in sites:
            sites[code] = {"code": code, "name": name}

    # build pods
    pods: Dict[str, Dict[str, Any]] = {}
    for proj, sdi, locname, trafo, bmc, pvv, pvc in zip(
        proj_series, pod_series, locname_series, trafo_series, bmc_series, pvv_series, pvc_series
    ):
        if not sdi:
            continue
        site_code, _ = parse_project_id(proj)
        pods[sdi] = {
            "pod_sdi": sdi,
            "name": locname,
            "site_code": site_code,
            "trafo_no": trafo,
            "bmc_nr": bmc,
            "pvv_nr": pvv,
            "pvc_nr": pvc,
            # "od_pod": will be filled later
        }

    # build meters
    meters: List[Dict[str, Any]] = []
    seen = set()
    for proj, sdi, sn, cosem in zip(proj_series, pod_series, sn_series, cosem_series):
        if not sn or sn in seen:
            continue
        seen.add(sn)
        site_code, _ = parse_project_id(proj)
        meters.append({
            "meter_no": sn,
            "name": cosem,
            "pod_sdi": sdi,
            "site_code": site_code,
        })

    return sites, pods, meters


# =========================
# Main
# =========================

def main():
    a = Path(sys.argv[1]) if len(sys.argv) > 1 else FILE_A
    b = Path(sys.argv[2]) if len(sys.argv) > 2 else FILE_B

    print(f"[INFO] Using A={a}, B={b}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # (1) Load OD->SDI pairs from A
    od_to_sdi = load_od_to_sdi_pairs(a)

    # (2) Load Sites, SDI PODs, and Meters from B
    sites, pods, meters = load_sdi_meter_and_site(b)

    # Map SDI -> site_code
    sdi_to_site: Dict[str, Optional[str]] = {sdi: p.get("site_code") for sdi, p in pods.items()}

    # (3) Build OD PODs from A (site_code via SDI if possible)
    od_pods: Dict[str, Dict[str, Any]] = {}
    for od, sdi in od_to_sdi.items():
        site_code = sdi_to_site.get(sdi)
        od_pods[od] = {
            "pod_od": od,
            "site_code": site_code,  # may be None; we’ll backfill below
            "name": None,
            "operator_code": None,
            "operator_name": None,
            "valid_from": None,
            "valid_to": None,
        }

    # (4) Enrich SDI PODs with od_pod:
    #     First try to find mapping in A; if not found, fallback to pod_sdi before "/"
    for sdi, pod_row in pods.items():
        chosen_od = None
        # Try exact mapping from A
        for od_key, sdi_val in od_to_sdi.items():
            if sdi_val == sdi:
                chosen_od = od_key
                break
        # Fallback: use sdi truncated before "/"
        if not chosen_od and sdi:
            chosen_od = strip_after_slash(sdi)
        pod_row["od_pod"] = chosen_od or None

    # (5) BACKFILL OD POD site_code using meters:
    #     Build a dict { od_pod_from_pod_sdi : site_code } from meters list
    #     od_pod_from_pod_sdi is pod_sdi with everything after '/' removed (including '/')
    od_from_meters: Dict[str, str] = {}
    # track multiple site_codes per od (if inconsistent, we keep first and note)
    od_site_candidates: Dict[str, Dict[str, int]] = {}

    for m in meters:
        sdi = m.get("pod_sdi")
        site_code = m.get("site_code")
        if not sdi or not site_code:
            continue
        od = strip_after_slash(sdi)
        if not od:
            continue
        # count candidates to detect conflicts
        od_site_candidates.setdefault(od, {})
        od_site_candidates[od][site_code] = od_site_candidates[od].get(site_code, 0) + 1

    # choose most frequent site_code for each od
    for od, counts in od_site_candidates.items():
        best_site = max(counts.items(), key=lambda kv: kv[1])[0]
        od_from_meters[od] = best_site

    # (5a) Create OD POD rows missing from A, using meters-derived mapping
    created_from_meters = 0
    for od, site_code in od_from_meters.items():
        if od not in od_pods:
            od_pods[od] = {
                "pod_od": od,
                "site_code": site_code,
                "name": None,
                "operator_code": None,
                "operator_name": None,
                "valid_from": None,
                "valid_to": None,
            }
            created_from_meters += 1

    # (5b) Backfill missing site_code on existing OD POD rows
    backfilled = 0
    for od, row in od_pods.items():
        if not row.get("site_code"):
            m_site = od_from_meters.get(od)
            if m_site:
                row["site_code"] = m_site
                backfilled += 1

    # --- Write outputs ---
    with open(SITES_JSON, "w", encoding="utf-8") as f:
        json.dump(list(sites.values()), f, indent=2, ensure_ascii=False)

    with open(OD_PODS_JSON, "w", encoding="utf-8") as f:
        json.dump(list(od_pods.values()), f, indent=2, ensure_ascii=False)

    with open(PODS_JSON, "w", encoding="utf-8") as f:
        json.dump(list(pods.values()), f, indent=2, ensure_ascii=False)

    with open(METERS_JSON, "w", encoding="utf-8") as f:
        json.dump(meters, f, indent=2, ensure_ascii=False)

    # --- Stats ---
    total_sites = len(sites)
    total_od = len(od_pods)
    total_pods = len(pods)
    total_meters = len(meters)
    missing_site_after = sum(1 for r in od_pods.values() if not r.get("site_code"))

    print(f"[OK] Sites: {total_sites} | OD PODs: {total_od} | PODs: {total_pods} | Meters: {total_meters}")
    print(f"     OD PODs created from meters: {created_from_meters}, backfilled site_code: {backfilled}")
    if missing_site_after:
        print(f"     WARNING: {missing_site_after} OD PODs still lack site_code after backfill.")


if __name__ == "__main__":
    main()
