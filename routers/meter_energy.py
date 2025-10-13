# routers/meter_energy.py
from __future__ import annotations
import json, time
from typing import List, Literal, Optional, Tuple
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiomysql
from fastapi import APIRouter, Depends, Request, HTTPException

from models import Meter, User
from deps import get_current_active_user
from api_utils import RAListParams, respond_plain_list

router = APIRouter(prefix="/meter-data/energy", tags=["meter-energy"])


# ---- Config ----
PROC_NAME = "FetchMeterData_SegmentsBuckets"  # hardcoded procedure name
BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")

Granularity = Literal["hour", "day", "month", "year"]
ALLOWED_SORTS = {
    "bucket_start", "bucket_end", "energy",
    "ea_plus", "ea_minus", "er_plus", "er_minus",
    "r_q1", "r_q2", "r_q3", "r_q4", "reset_steps",
}

# ---- Helpers ----

# replace _resolve_meter_name with:
async def _resolve_meter_name(filters: dict) -> Optional[str]:
    """
    Resolve the meter NAME for the proc.
    Priority:
      1) name
      2) meter_id
      3) meter_no
      4) pod / od_pod / site -> pick latest meter there
    """
    # explicit name
    if filters.get("name"):
        return str(filters["name"])

    # by meter_id
    if filters.get("meter_id") is not None:
        m = await Meter.get_or_none(id=int(filters["meter_id"]))
        if m and m.name:
            return str(m.name)

    # by meter_no
    if filters.get("meter_no"):
        m = await Meter.get_or_none(meter_no=str(filters["meter_no"]))
        if m and m.name:
            return str(m.name)

    # by pod / od_pod / site (pick current/latest)
    for fk, field in (("pod", "pod_id"), ("od_pod", "od_pod_id"), ("site", "site_id")):
        if filters.get(fk) is not None:
            try:
                scope_id = int(filters[fk])
            except (TypeError, ValueError):
                continue
            m = await Meter.filter(**{field: scope_id}).order_by("-updated_at", "-created_at").first()
            if m:
                return str(m.name or m.meter_no or "")
    return None


def _iso_to_mysql_bucharest_wall(ts: Optional[str]) -> Optional[str]:
    """
    Parse incoming ISO (often Z/UTC from browser), convert to Europe/Bucharest,
    then DROP tz and return 'YYYY-MM-DD HH:MM:SS' as wall time for the procedure.
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))  # aware
    except Exception:
        # Already a MySQL-like string; pass through
        return ts
    dt_b = dt.astimezone(BUCHAREST_TZ)
    return dt_b.strftime("%Y-%m-%d %H:%M:%S")


def _wrap_ts_literal(mysql_dt: Optional[str]) -> str:
    """
    Wrap as {ts 'YYYY-MM-DD HH:MM:SS'} or return NULL if missing.
    """
    if not mysql_dt:
        return "NULL"
    return f"{{ts '{mysql_dt}'}}"


def _coerce_dt(v) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        # OLD (causes +03:00 shift):
        # return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

        # NEW: treat naive datetimes as BUCHAREST local time
        return v if v.tzinfo else v.replace(tzinfo=BUCHAREST_TZ)

    if isinstance(v, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(v, fmt)
                if dt.tzinfo is None:
                    # OLD:
                    # dt = dt.replace(tzinfo=timezone.utc)

                    # NEW:
                    dt = dt.replace(tzinfo=BUCHAREST_TZ)
                return dt
            except Exception:
                continue
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                # OLD:
                # dt = dt.replace(tzinfo=timezone.utc)

                # NEW:
                dt = dt.replace(tzinfo=BUCHAREST_TZ)
            return dt
        except Exception:
            return None
    return None


def _to_iso_bucharest(v) -> Optional[str]:
    """
    Convert a datetime/str to Europe/Bucharest ISO string with offset.
    Return None if invalid/unparsable.
    """
    dt = _coerce_dt(v)
    if not dt:
        return None
    return dt.astimezone(BUCHAREST_TZ).isoformat()


def _normalize_row(row: dict, meter_name: str) -> Optional[dict]:
    """
    Map proc headers to JSON. Skip rows with invalid bucket_start to avoid phantom 1970 bars.
    """
    bs_iso = _to_iso_bucharest(row.get("bucket_start"))
    be_iso = _to_iso_bucharest(row.get("bucket_end"))
    if not bs_iso:
        return None

    ea_plus  = float(row.get("EA+") or 0)
    ea_minus = float(row.get("EA-") or 0)
    er_plus  = float(row.get("ER+") or 0)
    er_minus = float(row.get("ER-") or 0)

    # print a short line so you can confirm normalization
    print("   normalized bucket_start(Bucharest):", bs_iso, "bucket_end:", be_iso)

    return {
        "id": bs_iso,                   # unique per bucket
        "meter_name": meter_name,
        "meter_no": None,               # not used in this path
        "bucket_start": bs_iso,         # ISO with +02:00/+03:00
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
        "energy": ea_plus,              # back-compat single series
    }

# ---- Endpoint ----

@router.get("", response_model=List[dict])
async def list_energy(
    request: Request,
    params: RAListParams = Depends(),
    user: User = Depends(get_current_active_user),
):
    filters = dict(params.filters or {})

    gran_raw = str(filters.get("granularity") or "day").lower()
    gran: Granularity = gran_raw if gran_raw in {"hour", "day", "month", "year"} else "day"

    # Resolve NAME for the proc
    meter_name = await _resolve_meter_name(filters)
    if not meter_name:
        print("⚠️  No meter name resolved from filters:", filters)
        return respond_plain_list([], params.skip, params.limit)

    # Convert incoming ISO bounds to Bucharest wall-time
    date_from_iso = filters.get("date_gte")
    date_to_iso   = filters.get("date_lte")
    date_from_mysql = _iso_to_mysql_bucharest_wall(date_from_iso)
    date_to_mysql   = _iso_to_mysql_bucharest_wall(date_to_iso)

    ts_from = _wrap_ts_literal(date_from_mysql)
    ts_to   = _wrap_ts_literal(date_to_mysql)

    # Build statement (use 'stmt' so we don't shadow/lose a variable)
    stmt = f"CALL {PROC_NAME}(%s, {ts_from}, {ts_to}, %s, NULL)"
    params_tuple: Tuple[str, str] = (meter_name, gran)

    # Debug prints
    print("➡️  Calling procedure:", PROC_NAME)
    print("    INCOMING ISO:", date_from_iso, "→", date_to_iso)
    print("    BUCHAREST wall:", date_from_mysql, "→", date_to_mysql)
    print("    SQL:", stmt)
    print("    PARAMS:", params_tuple)

    # Execute
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
        print("❌ Error executing procedure:", e)
        # DO NOT reference 'stmt' or 'params_tuple' incorrectly here; they exist in this scope
        raise HTTPException(status_code=500, detail=f"Procedure execution failed: {e}")

    dt_ms = (time.perf_counter() - t0) * 1000.0
    print(f"✅ Procedure done in {dt_ms:.1f} ms, rows={len(rows)}")
    if rows:
        preview = dict(list(rows[0].items())[:8])
        print("    First row sample:", preview)

    # Normalize & filter invalid timestamps
    items = []
    for r in rows:
        norm = _normalize_row(r, meter_name)
        if norm is not None:
            items.append(norm)

    # Optional client sort
    try:
        sort_field, sort_order = json.loads(params.sort)
        reverse = str(sort_order).upper() == "DESC"
        if sort_field in ALLOWED_SORTS:
            items.sort(key=lambda x: x.get(sort_field), reverse=reverse)
    except Exception:
        pass

    return respond_plain_list(items, params.skip, params.limit)
