# routers/location_energy.py
from __future__ import annotations
import json, time
from typing import List, Literal, Optional, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

import aiomysql
from fastapi import APIRouter, Depends, Request, HTTPException

from models import Meter, User
from deps import get_current_active_user
from api_utils import RAListParams, respond_plain_list

router = APIRouter(prefix="/location-data/energy", tags=["location-energy"])

# ---- Config ----
PROC_NAME = "FetchMeterData_SegmentsBuckets"  # hardcoded procedure
BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")

Granularity = Literal["hour", "day", "month", "year"]
ALLOWED_SORTS = {
    "bucket_start", "bucket_end", "energy",
    "ea_plus", "ea_minus", "er_plus", "er_minus",
    "r_q1", "r_q2", "r_q3", "r_q4", "reset_steps",
}

# ---- Helpers ----

async def _resolve_current_meter_name_for_location(filters: dict) -> Optional[str]:
    """
    Pick the *current* meter for a location (latest updated/created).
    Return its NAME (preferred by the proc); fallback to meter_no.
    """
    loc_id = filters.get("location_id")
    if not loc_id:
        return None
    m = await Meter.filter(location_id=loc_id).order_by("-updated_at", "-created_at").first()
    if not m:
        return None
    return str(getattr(m, "name", None) or getattr(m, "meter_no", None) or "")


def _iso_to_mysql_bucharest_wall(ts: Optional[str]) -> Optional[str]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return ts
    return dt.astimezone(BUCHAREST_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _wrap_ts_literal(mysql_dt: Optional[str]) -> str:
    return f"{{ts '{mysql_dt}'}}" if mysql_dt else "NULL"


def _coerce_dt(v) -> Optional[datetime]:
    """Treat naive datetimes from the proc as Bucharest local; keep aware ones."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=BUCHAREST_TZ)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=BUCHAREST_TZ)
        except Exception:
            return None
    return None


def _to_iso_bucharest(v) -> Optional[str]:
    dt = _coerce_dt(v)
    return dt.astimezone(BUCHAREST_TZ).isoformat() if dt else None


def _normalize_row(row: dict, meter_name: str) -> Optional[dict]:
    """
    Normalize a row from the procedure. Your logs show Segment_Start/Segment_End,
    so we prefer those, but fall back to bucket_* if present.
    """
    bs_iso = _to_iso_bucharest(row.get("Segment_Start") or row.get("bucket_start"))
    be_iso = _to_iso_bucharest(row.get("Segment_End")   or row.get("bucket_end"))
    if not bs_iso:
        return None

    ea_plus  = float(row.get("EA+") or row.get("EA_plus") or 0)
    ea_minus = float(row.get("EA-") or row.get("EA_minus") or 0)
    er_plus  = float(row.get("ER+") or row.get("ER_plus") or 0)
    er_minus = float(row.get("ER-") or row.get("ER_minus") or 0)

    return {
        "id": bs_iso,
        "meter_name": meter_name,
        "meter_no": None,
        "bucket_start": bs_iso,
        "bucket_end": be_iso,
        "ea_plus": ea_plus,
        "ea_minus": ea_minus,
        "er_plus": er_plus,
        "er_minus": er_minus,
        "r_q1": float(row.get("R_Q1") or 0),
        "r_q2": float(row.get("R_Q2") or 0),
        "r_q3": float(row.get("R_Q3") or 0),
        "r_q4": float(row.get("R_Q4") or 0),
        "reset_steps": int(row.get("Reset_Steps") or 0),
        "energy": ea_plus,
    }

# ---- Endpoint ----

@router.get("", response_model=List[dict])
async def list_location_energy(
    request: Request,
    params: RAListParams = Depends(),
    user: User = Depends(get_current_active_user),
):
    filters = dict(params.filters or {})
    gran_raw = str(filters.get("granularity") or "day").lower()
    gran: Granularity = gran_raw if gran_raw in {"hour", "day", "month", "year"} else "day"

    meter_name = await _resolve_current_meter_name_for_location(filters)
    if not meter_name:
        print("⚠️  No current meter for location/filters:", filters)
        return respond_plain_list([], params.skip, params.limit)

    # Bucharest wall-time window
    date_from_iso = filters.get("date_gte")
    date_to_iso   = filters.get("date_lte")
    date_from_mysql = _iso_to_mysql_bucharest_wall(date_from_iso)
    date_to_mysql   = _iso_to_mysql_bucharest_wall(date_to_iso)

    ts_from = _wrap_ts_literal(date_from_mysql)
    ts_to   = _wrap_ts_literal(date_to_mysql)

    stmt = f"CALL {PROC_NAME}(%s, {ts_from}, {ts_to}, %s, NULL)"
    params_tuple: Tuple[str, str] = (meter_name, gran)

    print("➡️  Calling procedure (location):", PROC_NAME)
    print("    INCOMING ISO:", date_from_iso, "→", date_to_iso)
    print("    BUCHAREST wall:", date_from_mysql, "→", date_to_mysql)
    print("    SQL:", stmt)
    print("    PARAMS:", params_tuple)

    # Execute the proc
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
                    if not await cur.nextset():
                        break
    except Exception as e:
        print("❌ Error executing procedure:", e)
        raise HTTPException(status_code=500, detail=f"Procedure execution failed: {e}")

    dt_ms = (time.perf_counter() - t0) * 1000.0
    print(f"✅ Procedure done in {dt_ms:.1f} ms, rows={len(rows)}")
    if rows:
        preview = dict(list(rows[0].items())[:8])
        print("    First row sample:", preview)

    # Normalize
    items: list[dict] = []
    for r in rows:
        norm = _normalize_row(r, meter_name)
        if norm is not None:
            items.append(norm)

    # 🚨 Drop the first row (procedure summary/header)
    if items:
        dropped = items.pop(0)
        print("   ⛔ dropped first row (summary/header):",
              dropped.get("bucket_start"), "→", dropped.get("bucket_end"))

    # Optional client sort
    try:
        sort_field, sort_order = json.loads(params.sort)
        reverse = str(sort_order).upper() == "DESC"
        if sort_field in ALLOWED_SORTS:
            items.sort(key=lambda x: x.get(sort_field), reverse=reverse)
    except Exception:
        pass

    return respond_plain_list(items, params.skip, params.limit)
