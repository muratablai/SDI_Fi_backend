# app/routers/locations.py
from fastapi import APIRouter, Request, Response, Query, HTTPException
from typing import Optional, Any, Dict
import json
from models import Location

router = APIRouter(prefix="/locations", tags=["locations"])

def _parse_json_param(param: Optional[str], default):
    if not param:
        return default
    try:
        return json.loads(param)
    except Exception:
        return default

@router.get("")  # GET /locations
async def list_locations(
    response: Response,
    sort: Optional[str] = Query(None),    # '["pod_sdi","ASC"]'
    range: Optional[str] = Query(None),   # '[0,24]'
    filter: Optional[str] = Query(None),  # '{}'
):
    # Base queryset
    qs = Location.all()

    # Filters (adjust as you need)
    f: Dict[str, Any] = _parse_json_param(filter, {})
    if f:
        if "pod_sdi" in f:
            qs = qs.filter(pod_sdi=f["pod_sdi"])
        if "area_id" in f:
            qs = qs.filter(area_id=f["area_id"])
        if "role" in f:
            qs = qs.filter(role=f["role"])

    # Sorting
    s = _parse_json_param(sort, ["pod_sdi", "ASC"])
    if isinstance(s, list) and len(s) == 2:
        field, order = s
        qs = qs.order_by(f"{'' if str(order).upper() == 'ASC' else '-'}{field}")

    total = await qs.count()

    # Range / pagination
    r = _parse_json_param(range, [0, 24])
    start, end = (r + [0, 24])[:2] if isinstance(r, list) else (0, 24)
    limit = end - start + 1
    rows = await qs.offset(start).limit(limit)

    # Body must be a PLAIN ARRAY for ra-data-simple-rest
    data = [
        {
            "id": loc.id,
            "pod_sdi": loc.pod_sdi,
            "name": loc.name,
            "role": loc.role,
            "area_id": loc.area_id,
            "trafo_no": loc.trafo_no,
            "bmc_nr": loc.bmc_nr,
            "pvv_nr": loc.pvv_nr,
            "pvc_nr": loc.pvc_nr,
        }
        for loc in rows
    ]

    # Content-Range header REQUIRED by ra-data-simple-rest
    response.headers["Content-Range"] = f"locations {start}-{start+len(data)-1}/{total}"
    # Make sure the header is visible to the browser (CORS)
    response.headers["Access-Control-Expose-Headers"] = "Content-Range"

    # 200 is fine; 206 also works. We'll return 200.
    return data


@router.get("/{id}")  # GET /locations/:id
async def get_location(id: int):
    loc = await Location.get_or_none(id=id)
    if not loc:
        raise HTTPException(404, "Location not found")
    # For GET_ONE, ra-data-simple-rest expects a single object, not wrapped
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
    }
