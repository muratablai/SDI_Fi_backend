# routers/pod_data.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, Iterable

from fastapi import APIRouter, Depends, HTTPException
from tortoise.expressions import Q

from api_utils import RAListParams, parse_sort, respond_plain_list
from models import MeterAssignment, Meter, MeterData

router = APIRouter(prefix="/pod-data", tags=["pod-data"])

# ----------------- helpers -----------------

def _parse_iso_drop_tz(v: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO (with or without Z/offset) and return a NAIVE datetime
    with the SAME wall clock time (no timezone conversion).
    This matches SQLite naive storage used by meter_data.
    """
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except Exception:
        return None
    # strip tz WITHOUT astimezone() to preserve the wall time
    return dt.replace(tzinfo=None)

async def _resolve_meters_for_pod(pod_id: int, dt_from: Optional[datetime], dt_to: Optional[datetime]):
    """
    1) Try meters via MeterAssignment overlapping [dt_from, dt_to]
    2) Fallback to meters directly linked to the pod (Meter.pod_id)
    Returns: list[{"id": int, "meter_no": str}]
    """
    ass_qs = MeterAssignment.filter(pod_id=pod_id)
    if dt_from is not None:
        ass_qs = ass_qs.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=dt_from))
    if dt_to is not None:
        ass_qs = ass_qs.filter(valid_from__lte=dt_to)

    meter_ids = await ass_qs.values_list("meter_id", flat=True)
    if meter_ids:
        meters = await Meter.filter(id__in=meter_ids).values("id", "meter_no")
        if meters:
            return meters

    # Fallback: directly linked meters
    return await Meter.filter(pod_id=pod_id).values("id", "meter_no")

# ----------------- route -------------------

@router.get("")
async def list_pod_data(params: RAListParams = Depends()):
    f = params.filters or {}

    pod_raw = f.get("pod")
    if pod_raw is None:
        raise HTTPException(status_code=400, detail="Missing 'pod' in filter")
    try:
        pod_id = int(str(pod_raw))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid 'pod' id")

    # Match meter_data behavior: drop tz, no conversion
    dt_from = _parse_iso_drop_tz(f.get("date_gte"))
    dt_to   = _parse_iso_drop_tz(f.get("date_lte"))

    print("attempting to resolve meters")
    meters = await _resolve_meters_for_pod(pod_id, dt_from, dt_to)
    meter_nos = [m.get("meter_no") for m in meters if m.get("meter_no")]
    id_by_no = {m["meter_no"]: m["id"] for m in meters if m.get("meter_no")}

    # Debug so you can confirm what’s being used
    print(f"[pod-data] pod={pod_id} meter_nos={meter_nos} dt_from={dt_from} dt_to={dt_to}")

    if not meter_nos:
        return respond_plain_list([], params.skip, params.limit)

    qs = MeterData.filter(meter_no__in=meter_nos)
    if dt_from is not None:
        qs = qs.filter(timestamp__gte=dt_from)
    if dt_to is not None:
        qs = qs.filter(timestamp__lte=dt_to)

    allowed_sort: Iterable[str] = {
        "id","timestamp","meter_no","fa","fr","ra",
        "fa_t1","fa_t2","fa_t3","fa_t4",
        "rr","r_q1","r_q2","r_q3","r_q4","p_fa","p_fr"
    }
    order = parse_sort(params.sort, allowed_sort)

    rows = await qs.order_by(order).offset(params.skip).limit(params.limit).values(
        "id","meter_no","timestamp","fa","fr","ra",
        "fa_t1","fa_t2","fa_t3","fa_t4",
        "rr","r_q1","r_q2","r_q3","r_q4","p_fa","p_fr"
    )

    for r in rows:
        r["meter_id"] = id_by_no.get(r["meter_no"])

    print(f"[pod-data] returned={len(rows)}")
    return respond_plain_list(rows, params.skip, params.limit)
