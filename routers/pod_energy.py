from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Literal, Optional, Tuple
from api_utils import RAListParams, respond_plain_list
from models import Pod
import json, time
from datetime import datetime
from zoneinfo import ZoneInfo
import aiomysql

router = APIRouter(prefix="/pod-data/energy", tags=["pod-energy"])

Granularity = Literal["hour", "day", "month", "year"]
ALLOWED_SORTS = {"bucket_start", "bucket_end", "energy", "ea_plus", "ea_minus", "er_plus", "er_minus", "r_q1", "r_q2", "r_q3", "r_q4", "reset_steps"}
PROC_NAME = "FetchPodData_SegmentsBuckets"
BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")

def _iso_to_mysql_bucharest_wall(ts: Optional[str]) -> Optional[str]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return ts
    return dt.astimezone(BUCHAREST_TZ).strftime("%Y-%m-%d %H:%M:%S")

def _wrap_ts_literal(mysql_dt: Optional[str]) -> str:
    return "NULL" if not mysql_dt else f"{{ts '{mysql_dt}'}}"

def _normalize_row(row: dict, pod_sdi: str) -> Optional[dict]:
    bs = row.get("bucket_start")
    be = row.get("bucket_end")
    if not bs:
        return None
    # keep them as plain strings; your proc should emit proper timestamps
    ea_plus  = float(row.get("EA+") or 0)
    ea_minus = float(row.get("EA-") or 0)
    er_plus  = float(row.get("ER+") or 0)
    er_minus = float(row.get("ER-") or 0)
    return {
        "id": str(bs),
        "pod_sdi": pod_sdi,
        "bucket_start": str(bs),
        "bucket_end": str(be) if be else None,
        "ea_plus": ea_plus, "ea_minus": ea_minus,
        "er_plus": er_plus, "er_minus": er_minus,
        "r_q1": float(row.get("R_Q1") or 0),
        "r_q2": float(row.get("R_Q2") or 0),
        "r_q3": float(row.get("R_Q3") or 0),
        "r_q4": float(row.get("R_Q4") or 0),
        "reset_steps": int(row.get("Reset_Steps") or 0),
        "energy": ea_plus,
    }

@router.get("", response_model=List[dict])
async def list_energy(
    request: Request,
    params: RAListParams = Depends(),
):
    f = dict(params.filters or {})
    gran_raw = str(f.get("granularity") or "day").lower()
    gran: Granularity = gran_raw if gran_raw in {"hour", "day", "month", "year"} else "day"

    pod_id = f.get("pod_id") or f.get("location_id")
    if not pod_id:
        return respond_plain_list([], params.skip, params.limit)

    pod = await Pod.get_or_none(id=int(pod_id))
    if not pod:
        raise HTTPException(404, "POD not found")

    date_from = _iso_to_mysql_bucharest_wall(f.get("date_gte"))
    date_to = _iso_to_mysql_bucharest_wall(f.get("date_lte"))
    ts_from = _wrap_ts_literal(date_from)
    ts_to = _wrap_ts_literal(date_to)

    stmt = f"CALL {PROC_NAME}(%s, {ts_from}, {ts_to}, %s, NULL)"
    params_tuple: Tuple[str, str] = (pod.pod_sdi, gran)

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
        raise HTTPException(status_code=500, detail=f"Procedure execution failed: {e}")

    items = []
    for r in rows:
        norm = _normalize_row(r, pod.pod_sdi)
        if norm is not None:
            items.append(norm)

    # client sort
    try:
        sort_field, sort_order = json.loads(params.sort)
        reverse = str(sort_order).upper() == "DESC"
        if sort_field in ALLOWED_SORTS:
            items.sort(key=lambda x: x.get(sort_field), reverse=reverse)
    except Exception:
        pass

    return respond_plain_list(items, params.skip, params.limit)
