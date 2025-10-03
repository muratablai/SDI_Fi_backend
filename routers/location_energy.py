# routers/location_energy.py
from __future__ import annotations
import json, time
from typing import List, Literal, Optional, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

import aiomysql
from fastapi import APIRouter, Depends, Request, HTTPException, Query, Response

from models import Meter, User
from deps import get_current_active_user


router = APIRouter(prefix="/location-data/energy", tags=["location-energy"])
print("✅ location_energy router LOADED (manual parser)")
# Stored procedure name (hardcoded as requested)
PROC_NAME = "FetchMeterData_SegmentsBuckets"
BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")
Granularity = Literal["hour", "day", "month", "year"]
ALLOWED_SORTS = {
    "bucket_start", "bucket_end", "energy",
    "ea_plus", "ea_minus", "er_plus", "er_minus",
    "r_q1", "r_q2", "r_q3", "r_q4", "reset_steps",
}

# ---------- Helpers ----------

def _iso_to_mysql_bucharest_wall(ts: Optional[str]) -> Optional[str]:
    """Incoming ISO (usually 'Z') -> Bucharest local wall time 'YYYY-MM-DD HH:MM:SS'."""
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
    """Treat naive datetimes from the proc as Bucharest local time; keep aware ones."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=BUCHAREST_TZ)
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(v, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=BUCHAREST_TZ)
            except Exception:
                pass
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=BUCHAREST_TZ)
        except Exception:
            return None
    return None

def _to_iso_bucharest(v) -> Optional[str]:
    dt = _coerce_dt(v)
    return dt.astimezone(BUCHAREST_TZ).isoformat() if dt else None

def _normalize_row(row: dict) -> Optional[dict]:
    """Map proc headers to normalized JSON; skip if bucket_start invalid."""
    bs_iso = _to_iso_bucharest(row.get("bucket_start") or row.get("bucket") or row.get("Segment_Start"))
    be_iso = _to_iso_bucharest(row.get("bucket_end") or row.get("Segment_End"))
    if not bs_iso:
        return None

    ea_plus  = float(row.get("EA+") or row.get("EA_plus") or 0)
    ea_minus = float(row.get("EA-") or row.get("EA_minus") or 0)
    er_plus  = float(row.get("ER+") or row.get("ER_plus") or 0)
    er_minus = float(row.get("ER-") or row.get("ER_minus") or 0)

    print("   normalized bucket_start(Bucharest):", bs_iso, "bucket_end:", be_iso)

    return {
        "id": bs_iso,
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
        "energy": ea_plus,  # back-compat with previous single-series UI
    }

async def _call_proc_for_meter(
    pool: aiomysql.Pool,
    meter_name: str,
    gran: Granularity,
    date_from_mysql: Optional[str],
    date_to_mysql: Optional[str],
) -> list[dict]:
    ts_from = _wrap_ts_literal(date_from_mysql)
    ts_to   = _wrap_ts_literal(date_to_mysql)
    stmt = f"CALL {PROC_NAME}(%s, {ts_from}, {ts_to}, %s, NULL)"
    params_tuple: Tuple[str, str] = (meter_name, gran)

    print("➡️  CALL /location-data/energy:", PROC_NAME)
    print("    meter_name:", meter_name)
    print("    SQL:", stmt)
    print("    PARAMS:", params_tuple)

    rows: list[dict] = []
    t0 = time.perf_counter()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(stmt, params_tuple)
            while True:
                part = await cur.fetchall()
                if part:
                    rows.extend(part)
                if not await cur.nextset():
                    break
    print(f"    ✅ proc rows={len(rows)} time={(time.perf_counter()-t0)*1000:.1f}ms")
    if rows:
        print("    first row sample:", dict(list(rows[0].items())[:8]))
    return rows

def _parse_ra_params(
    filter_param: Optional[str],
    sort_param: Optional[str],
    range_param: Optional[str],
):
    # filters
    filters = {}
    if filter_param:
        try:
            filters = json.loads(filter_param)
        except Exception:
            filters = {}

    # sort
    sort_field = "bucket_start"
    sort_order = "ASC"
    if sort_param:
        try:
            s = json.loads(sort_param)
            if isinstance(s, list) and len(s) == 2:
                sort_field, sort_order = s[0], s[1]
        except Exception:
            pass

    # range
    start = 0
    end = 9999
    if range_param:
        try:
            r = json.loads(range_param)
            if isinstance(r, list) and len(r) == 2:
                start, end = int(r[0]), int(r[1])
        except Exception:
            pass

    return filters, (sort_field, sort_order), (start, end)

def _paginate(items: list[dict], start: int, end: int, resp: Response, resource_name: str):
    total = len(items)
    slice_items = items[start : end + 1]  # RA uses inclusive end
    resp.headers["Content-Range"] = f"{resource_name} {start}-{start + len(slice_items) - 1}/{total}"
    resp.headers["X-Total-Count"] = str(total)
    resp.status_code = 206  # Partial Content (RA expects this)
    return slice_items

# ---------- Endpoint ----------

@router.get("", response_model=List[dict])
async def list_location_energy(
    request: Request,
    response: Response,
    filter: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    range: Optional[str] = Query(None),
    user: User = Depends(get_current_active_user),
):
    print("🚏 ENTER /location-data/energy (current-meter, manual RA params)")
    filters, (sort_field, sort_order), (start, end) = _parse_ra_params(filter, sort, range)

    # Required: location_id
    location_id = filters.get("location_id")
    if not location_id:
        print("⚠️  Missing location_id in filters:", filters)
        return _paginate([], 0, 0, response, "location_energy")

    # Granularity
    gran_raw = str(filters.get("granularity") or "day").lower()
    gran: Granularity = gran_raw if gran_raw in {"hour", "day", "month", "year"} else "day"

    # Date bounds → Bucharest wall
    date_from_iso = filters.get("date_gte")
    date_to_iso   = filters.get("date_lte")
    date_from_mysql = _iso_to_mysql_bucharest_wall(date_from_iso)
    date_to_mysql   = _iso_to_mysql_bucharest_wall(date_to_iso)

    print("📍 Location energy (current meter)")
    print("    location_id:", location_id)
    print("    INCOMING ISO:", date_from_iso, "→", date_to_iso)
    print("    BUCHAREST wall:", date_from_mysql, "→", date_to_mysql)
    print("    granularity:", gran)

    # Choose the "current" meter = most recently updated/created at location
    m = await Meter.filter(location_id=location_id).order_by("-updated_at", "-created_at").first()
    if not m:
        print("    ⚠️ No meter currently assigned to location.")
        return _paginate([], 0, 0, response, "location_energy")

    meter_name = (getattr(m, "name", None) or getattr(m, "meter_no", None))
    if not meter_name:
        print("    ⚠️ Meter has no name/meter_no; id=", m.id)
        return _paginate([], 0, 0, response, "location_energy")
    meter_name = str(meter_name)

    # MySQL pool
    try:
        pool: aiomysql.Pool = request.app.state.mysql_pool
    except AttributeError:
        raise HTTPException(status_code=500, detail="MySQL pool not initialized")

    # Call proc for that meter
    try:
        raw_rows = await _call_proc_for_meter(pool, meter_name, gran, date_from_mysql, date_to_mysql)
    except Exception as e:
        print("❌ Error executing procedure:", e)
        raise HTTPException(status_code=500, detail=f"Procedure execution failed: {e}")

    # Normalize
    items = []
    for rr in raw_rows:
        norm = _normalize_row(rr)
        if norm:
            items.append(norm)

    # Sort
    reverse = str(sort_order).upper() == "DESC"
    if sort_field in ALLOWED_SORTS:
        items.sort(key=lambda x: x.get(sort_field), reverse=reverse)

    # Paginate + RA headers
    return _paginate(items, start, end, response, "location_energy")
