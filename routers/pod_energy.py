# routers/pod_energy.py
from __future__ import annotations
import json
import time
from typing import List, Literal, Optional, Tuple
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, Request
from tortoise.expressions import Q

from api_utils import RAListParams, respond_plain_list
from models import Pod, MeterAssignment, Meter

router = APIRouter(prefix="/pod-data/energy", tags=["pod-energy"])

Granularity = Literal["hour", "day", "month", "year"]
ALLOWED_SORTS = {
    "bucket_start", "bucket_end", "energy",
    "ea_plus", "ea_minus", "er_plus", "er_minus",
    "r_q1", "r_q2", "r_q3", "r_q4", "reset_steps",
}
PROC_NAME = "FetchMeterData_SegmentsBuckets"
BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")


# ---------------------- time helpers ----------------------

def _iso_to_mysql_bucharest_wall(ts: Optional[str]) -> Optional[str]:
    """
    Convert incoming ISO (often UTC 'Z') -> Bucharest wall time (no tz) 'YYYY-MM-DD HH:MM:SS'.
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))  # aware if had Z
    except Exception:
        # Already MySQL-like string; pass through
        return ts
    return dt.astimezone(BUCHAREST_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _wrap_ts_literal(mysql_dt: Optional[str]) -> str:
    return "NULL" if not mysql_dt else f"{{ts '{mysql_dt}'}}"


def _parse_iso_to_utc_naive(v: Optional[str]) -> Optional[datetime]:
    """
    Used purely for determining assignment overlap; returns UTC-naive for SQLite-friendly compare.
    """
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------- resolution helpers ----------------------

async def _resolve_meter_for_pod(
    pod_id: int,
    dt_from_iso: Optional[str],
    dt_to_iso: Optional[str],
) -> Optional[Meter]:
    """
    1) Find a meter via MeterAssignment overlapping the requested window.
    2) Fallback: newest meter directly linked to the pod.
    Returns a Meter or None.
    """
    dt_from = _parse_iso_to_utc_naive(dt_from_iso)
    dt_to = _parse_iso_to_utc_naive(dt_to_iso)

    print(f"[pod-energy] resolve-meter pod={pod_id} window_iso={dt_from_iso}..{dt_to_iso} "
          f"window_utc_naive={dt_from}..{dt_to}")

    ass_qs = MeterAssignment.filter(pod_id=pod_id)
    # overlap logic: (valid_from <= dt_to) AND (valid_to IS NULL OR valid_to >= dt_from)
    if dt_to:
        ass_qs = ass_qs.filter(valid_from__lte=dt_to)
    if dt_from:
        ass_qs = ass_qs.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=dt_from))

    ass = await ass_qs.order_by("-valid_from", "-id").first()
    if ass:
        m = await Meter.get_or_none(id=ass.meter)
        print(f"[pod-energy] assignment hit: assignment_id={ass.id if hasattr(ass,'id') else None} "
              f"meter_id={ass.meter} -> meter={m.meter_no if m else None}/{m.name if m else None}")
        if m:
            return m

    # fallback: newest meter bound to pod
    m = await Meter.filter(pod_id=pod_id).order_by("-updated_at", "-created_at", "-id").first()
    print(f"[pod-energy] fallback newest meter on pod -> {m.meter_no if m else None}/{m.name if m else None}")
    return m


def _normalize_row(row: dict, meter_key: str) -> Optional[dict]:
    """
    Normalize one proc row. If bucket_start is missing/invalid, skip.
    """
    bs = row.get("bucket_start")
    be = row.get("bucket_end")
    if not bs:
        return None

    # Keep as strings; proc should output proper timestamps for the client
    ea_plus = float(row.get("EA+") or 0)
    return {
        "id": str(bs),
        "meter_key": meter_key,
        "bucket_start": str(bs),
        "bucket_end": str(be) if be else None,
        "ea_plus": ea_plus,
        "ea_minus": float(row.get("EA-") or 0),
        "er_plus": float(row.get("ER+") or 0),
        "er_minus": float(row.get("ER-") or 0),
        "r_q1": float(row.get("R_Q1") or 0),
        "r_q2": float(row.get("R_Q2") or 0),
        "r_q3": float(row.get("R_Q3") or 0),
        "r_q4": float(row.get("R_Q4") or 0),
        "reset_steps": int(row.get("Reset_Steps") or 0),
        "energy": ea_plus,
    }


# --------------------------- route ---------------------------

@router.get("", response_model=List[dict])
async def list_energy(
    request: Request,
    params: RAListParams = Depends(),
):
    f = dict(params.filters or {})
    print(f"[pod-energy] IN filters={f} sort={params.sort} range=({params.skip},{params.limit})")

    # granularity
    gran_raw = str(f.get("granularity") or "day").lower()
    gran: Granularity = gran_raw if gran_raw in {"hour", "day", "month", "year"} else "day"

    # accept various keys from UI: pod (preferred), pod_id, location_id (legacy)
    pod_id = f.get("pod") or f.get("pod_id") or f.get("location_id")
    if not pod_id:
        print("[pod-energy] ⚠️ no pod id provided → []")
        return respond_plain_list([], params.skip, params.limit)

    try:
        pod_id_int = int(pod_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid 'pod' id")

    pod = await Pod.get_or_none(id=pod_id_int)
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # resolve a meter for this window
    m = await _resolve_meter_for_pod(pod_id_int, f.get("date_gte"), f.get("date_lte"))
    if not m:
        print(f"[pod-energy] ⚠️ no meter could be resolved for pod={pod_id_int} → []")
        return respond_plain_list([], params.skip, params.limit)

    # what identifier to pass to the proc?
    meter_key = (m.name or m.meter_no or "").strip()
    if not meter_key:
        print(f"[pod-energy] ⚠️ resolved meter has no usable name/serial (id={m.id}) → []")
        return respond_plain_list([], params.skip, params.limit)

    # convert bounds to MySQL-literal Bucharest wall-time
    date_from_iso = f.get("date_gte")
    date_to_iso = f.get("date_lte")
    date_from_mysql = _iso_to_mysql_bucharest_wall(date_from_iso)
    date_to_mysql = _iso_to_mysql_bucharest_wall(date_to_iso)
    ts_from = _wrap_ts_literal(date_from_mysql)
    ts_to = _wrap_ts_literal(date_to_mysql)

    print("[pod-energy] RESOLVED:",
          f"pod_id={pod_id_int} pod_sdi={pod.pod_sdi}",
          f"meter_id={m.id} meter_no={m.meter_no} meter_name={m.name}",
          f"→ proc_key='{meter_key}'",
          f"window ISO {date_from_iso}..{date_to_iso} | BUCHAREST {date_from_mysql}..{date_to_mysql}",
          f"gran={gran}",
          sep="\n  ")

    # build call
    stmt = f"CALL {PROC_NAME}(%s, {ts_from}, {ts_to}, %s, NULL)"
    params_tuple: Tuple[str, str] = (meter_key, gran)

    # acquire pool
    try:
        pool: aiomysql.Pool = request.app.state.mysql_pool
    except AttributeError:
        raise HTTPException(status_code=500, detail="MySQL pool not initialized")

    rows: list[dict] = []
    t0 = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                print(f"[pod-energy] SQL:\n  {stmt}\n  params={params_tuple}")
                await cur.execute(stmt, params_tuple)
                while True:
                    part = await cur.fetchall()
                    if part:
                        rows.extend(part)
                    if not await cur.nextset():
                        break
    except Exception as e:
        print(f"[pod-energy] ❌ proc error: {e}")
        raise HTTPException(status_code=500, detail=f"Procedure execution failed: {e}")

    ms = (time.perf_counter() - t0) * 1000.0
    print(f"[pod-energy] ✅ proc done in {ms:.1f} ms, rows={len(rows)}")
    if rows:
        preview = dict(list(rows[0].items())[:8])
        print(f"[pod-energy] first row (truncated): {preview}")

    # normalize
    items = []
    for r in rows:
        norm = _normalize_row(r, meter_key)
        if norm is not None:
            items.append(norm)

    # client sort (optional)
    try:
        sort_field, sort_order = json.loads(params.sort)
        reverse = str(sort_order).upper() == "DESC"
        if sort_field in ALLOWED_SORTS:
            items.sort(key=lambda x: x.get(sort_field), reverse=reverse)
    except Exception:
        pass

    print(f"[pod-energy] returning {len(items)} items")
    return respond_plain_list(items, params.skip, params.limit)
