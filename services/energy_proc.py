# services/energy_proc.py
from __future__ import annotations
import time, json
from typing import List, Literal, Optional, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

import aiomysql
from fastapi import HTTPException, Request

# ---- Config ----
PROC_NAME = "FetchMeterData_SegmentsBuckets"
BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")

Granularity = Literal["hour", "day", "month", "year"]
ALLOWED_SORTS = {
    "bucket_start", "bucket_end", "energy",
    "ea_plus", "ea_minus", "er_plus", "er_minus",
    "r_q1", "r_q2", "r_q3", "r_q4", "reset_steps",
}

# ------------------------
# Time helpers
# ------------------------
def _iso_to_mysql_bucharest_wall(ts: Optional[str]) -> Optional[str]:
    """
    Parse incoming ISO (often with Z/UTC from browser),
    convert to Europe/Bucharest, then return as MySQL wall time string.
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        # Already MySQL-like
        return ts
    return dt.astimezone(BUCHAREST_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _wrap_ts_literal(mysql_dt: Optional[str]) -> str:
    """
    Wrap as {ts 'YYYY-MM-DD HH:MM:SS'} or NULL if missing.
    """
    return "NULL" if not mysql_dt else f"{{ts '{mysql_dt}'}}"


def _normalize_row(row: dict, meter_key: str, constant: float) -> Optional[dict]:
    """
    Normalize procedure output row into JSON. Apply scaling constant to active energy.
    Skip rows with invalid bucket_start.
    """
    bs = row.get("bucket_start")
    be = row.get("bucket_end")
    if not bs:
        return None

    ea_plus_raw  = float(row.get("EA+") or 0)
    ea_minus_raw = float(row.get("EA-") or 0)
    er_plus_raw  = float(row.get("ER+") or 0)
    er_minus_raw = float(row.get("ER-") or 0)

    # Apply constant only to active energies (EA+/EA-)
    ea_plus  = ea_plus_raw * constant
    ea_minus = ea_minus_raw * constant

    return {
        "id": str(bs),
        "meter_name": meter_key,
        "bucket_start": str(bs),
        "bucket_end": str(be) if be else None,
        "ea_plus": ea_plus,
        "ea_minus": ea_minus,
        "er_plus": er_plus_raw,
        "er_minus": er_minus_raw,
        "r_q1": float(row.get("R_Q1") or 0),
        "r_q2": float(row.get("R_Q2") or 0),
        "r_q3": float(row.get("R_Q3") or 0),
        "r_q4": float(row.get("R_Q4") or 0),
        "reset_steps": int(row.get("Reset_Steps") or 0),
        "energy": ea_plus,  # main energy used for charts
    }

# ------------------------
# Main call helper
# ------------------------
async def call_energy_proc_with_constant(
    request: Request,
    *,
    meter_key: str,
    constant: float,
    date_from_iso: Optional[str],
    date_to_iso: Optional[str],
    granularity: Granularity = "day",
    debug: bool = True,
) -> list[dict]:
    """
    Calls FetchMeterData_SegmentsBuckets and applies the meter constant.
    """
    if granularity not in {"hour", "day", "month", "year"}:
        granularity = "day"

    date_from_mysql = _iso_to_mysql_bucharest_wall(date_from_iso)
    date_to_mysql   = _iso_to_mysql_bucharest_wall(date_to_iso)
    ts_from = _wrap_ts_literal(date_from_mysql)
    ts_to   = _wrap_ts_literal(date_to_mysql)

    stmt = f"CALL {PROC_NAME}(%s, {ts_from}, {ts_to}, %s, NULL)"
    params_tuple: Tuple[str, str] = (meter_key, granularity)

    if debug:
        print("➡️  Calling procedure:", PROC_NAME)
        print("    Meter key:", meter_key, "| constant:", constant)
        print("    ISO input:", date_from_iso, "→", date_to_iso)
        print("    Bucharest wall:", date_from_mysql, "→", date_to_mysql)
        print("    SQL:", stmt)
        print("    PARAMS:", params_tuple)

    try:
        pool: aiomysql.Pool = request.app.state.mysql_pool
    except AttributeError:
        raise HTTPException(status_code=500, detail="MySQL pool not initialized")

    rows: list[dict] = []
    t0 = time.perf_counter()

    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(stmt, params_tuple)
                while True:
                    part = await cur.fetchall()
                    if part:
                        rows.extend(part)
                    has_next = await cur.nextset()
                    if not has_next:
                        break
    except Exception as e:
        print("❌ Procedure error:", e)
        raise HTTPException(status_code=500, detail=f"Procedure execution failed: {e}")

    dt_ms = (time.perf_counter() - t0) * 1000.0
    if debug:
        print(f"✅ Procedure done in {dt_ms:.1f} ms, rows={len(rows)}")
        if rows:
            preview = dict(list(rows[0].items())[:8])
            print("    First row sample (raw):", preview)

    # Normalize and apply constant
    items = []
    for r in rows:
        norm = _normalize_row(r, meter_key, constant)
        if norm is not None:
            items.append(norm)

    return items


# ------------------------
# Optional client-side sort
# ------------------------
def client_sort(items: list[dict], sort_json: str) -> list[dict]:
    try:
        sort_field, sort_order = json.loads(sort_json)
        reverse = str(sort_order).upper() == "DESC"
        if sort_field in ALLOWED_SORTS:
            items.sort(key=lambda x: x.get(sort_field), reverse=reverse)
    except Exception:
        pass
    return items
