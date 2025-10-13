# routers/location_data.py
from fastapi import APIRouter, Query, Response, HTTPException
from typing import Optional, List
from datetime import datetime
import json
from tortoise.expressions import Q
from models import MeterData, MeterAssignment, Meter, Location
from schemas import LocationDataRead, LocationLatestRead
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/location-data", tags=["location-data"])

def _parse_json(s: Optional[str], default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default

@router.get("", response_model=List[LocationDataRead])
async def list_location_data(
    response: Response,
    filter: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    range: Optional[str] = Query(None),
):
    f = _parse_json(filter, {})
    location_id = f.get("location_id")
    if not location_id:
        raise HTTPException(400, detail="filter.location_id is required")

    start_s = f.get("start"); end_s = f.get("end")
    start_dt = datetime.fromisoformat(start_s) if start_s else None
    end_dt   = datetime.fromisoformat(end_s) if end_s else None

    meters = await Meter.filter(location_id=int(location_id)).order_by("created_at").all()
    if not meters:
        response.headers["Content-Range"] = "location-data 0-0/0"
        response.headers["Access-Control-Expose-Headers"] = "Content-Range"
        return []

    # ✅ collect meter_no strings, not ids
    meter_nos = [m.meter_no for m in meters]

    latest = await MeterData.filter(meter_no__in=meter_nos).order_by("-timestamp").first()
    if latest:
        chosen_meter_no = latest.meter_no
    else:
        chosen_meter_no = meters[0].meter_no  # fallback is consistent now

    qs = MeterData.filter(meter_no=chosen_meter_no)
    if start_dt:
        qs = qs.filter(timestamp__gte=start_dt)
    if end_dt:
        qs = qs.filter(timestamp__lte=end_dt)

    s = _parse_json(sort, ["timestamp", "ASC"])
    if isinstance(s, list) and len(s) == 2:
        field, order = s
        prefix = "" if str(order).upper() == "ASC" else "-"
        qs = qs.order_by(f"{prefix}{field}")

    total = await qs.count()
    r = _parse_json(range, [0, 999])
    start_i, end_i = (r + [0, 999])[:2]
    limit = end_i - start_i + 1

    rows = await qs.offset(start_i).limit(limit)

    data = [
        {
            "id": md.id,
            "timestamp": md.timestamp,
            "meter_no": md.meter_no,
            "fa": md.fa, "fr": md.fr, "ra": md.ra,
            "fa_t1": md.fa_t1, "fa_t2": md.fa_t2, "fa_t3": md.fa_t3, "fa_t4": md.fa_t4,
            "rr": md.rr, "r_q1": md.r_q1, "r_q2": md.r_q2, "r_q3": md.r_q3, "r_q4": md.r_q4,
            "p_fa": md.p_fa, "p_fr": md.p_fr,
        }
        for md in rows
    ]

    end_index = start_i + max(len(data) - 1, 0)
    response.headers["Content-Range"] = f"location-data {start_i}-{end_index}/{total}"
    response.headers["Access-Control-Expose-Headers"] = "Content-Range"
    return data

@router.get("/{id:int}")
async def get_location_legacy(id: str):
    if id.isdigit():
        return await get_location(int(id))
    # If it's not a digit (like "energy"), redirect to the real energy route.
    return RedirectResponse(url=f"/location-data/energy", status_code=307)

async def get_location(id: int):
    loc = await Location.get_or_none(id=id)
    if not loc:
        raise HTTPException(404, "Location not found")
    return {
        "id": loc.id,
        "pod_sdi": loc.pod_sdi,
        "name": loc.name,
        "role": loc.role,
        "area_id": loc.area_id,
        "trafo_no": loc.trafo_no,
        "bmc_nr": loc.bmc_nr,
        "pvv_nr": loc.pvv_nr,
        "pvc_nr": loc.pvc_nr,
        "created_at": loc.created_at,
        "updated_at": loc.updated_at,
    }

@router.get("/latest", response_model=Optional[LocationLatestRead])
async def latest_for_location(location_id: int):
    # pick most recent meter by latest reading; fallback to first created
    meters = await Meter.filter(location_id=int(location_id)).order_by("created_at").all()
    if not meters:
        return None

    meter_nos = [m.meter_no for m in meters]
    latest = await MeterData.filter(meter_no__in=meter_nos).order_by("-timestamp").first()
    if not latest:
        # no readings yet
        return None

    return {
        "timestamp": latest.timestamp,
        "meter_no": latest.meter_no,
        "fa": latest.fa,
        "fr": latest.fr,
        "ra": latest.ra,
        "p_fa": latest.p_fa,
        "p_fr": latest.p_fr,
    }