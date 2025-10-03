# app/routers/locations.py
from fastapi import APIRouter, Request, Response, Query, HTTPException
from typing import Optional, Any, Dict, List, Union
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

def _to_int_list(val: Union[List[Any], Any]) -> List[int]:
    """Coerce RA-style values into a list[int]."""
    if isinstance(val, list):
        out = []
        for x in val:
            try:
                out.append(int(x))
            except Exception:
                # ignore non-coercible entries
                pass
        return out
    try:
        return [int(val)]
    except Exception:
        return []

@router.get("")  # GET /locations
async def list_locations(
    response: Response,
    sort: Optional[str] = Query(None),    # '["pod_sdi","ASC"]'
    range: Optional[str] = Query(None),   # '[0,24]'
    filter: Optional[str] = Query(None),  # '{}'
):
    qs = Location.all()

    f: Dict[str, Any] = _parse_json_param(filter, {})

    if f:
        # exact match string fields
        if "pod_sdi" in f and f["pod_sdi"] not in (None, ""):
            qs = qs.filter(pod_sdi=f["pod_sdi"])
        if "role" in f and f["role"] not in (None, ""):
            qs = qs.filter(role=f["role"])

        # id / area_id can be a single value OR an array: use __in when list
        if "id" in f:
            ids = _to_int_list(f["id"])
            if ids:
                qs = qs.filter(id__in=ids)
        if "area_id" in f:
            area_ids = _to_int_list(f["area_id"])
            if area_ids:
                qs = qs.filter(area_id__in=area_ids)

    # Sorting
    s = _parse_json_param(sort, ["pod_sdi", "ASC"])
    if isinstance(s, list) and len(s) == 2:
        field, order = s
        prefix = "" if str(order).upper() == "ASC" else "-"
        qs = qs.order_by(f"{prefix}{field}")

    total = await qs.count()

    # Range / pagination
    r = _parse_json_param(range, [0, 24])
    if isinstance(r, list) and len(r) >= 2:
        start, end = int(r[0]), int(r[1])
    else:
        start, end = 0, 24
    limit = max(0, end - start + 1)
    rows = await qs.offset(start).limit(limit)

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

    last_index = start + len(data) - 1 if data else start
    response.headers["Content-Range"] = f"locations {start}-{last_index}/{total}"
    response.headers["Access-Control-Expose-Headers"] = "Content-Range"
    return data

@router.get("/{id}")  # GET /locations/:id
async def get_location(id: int):
    loc = await Location.get_or_none(id=id)
    if not loc:
        raise HTTPException(404, "Location not found")
    return {
        "id": loc.id,
        "pod_sdi": loc.pod_sdi,
        "name": loc.name,
        "role": loc.role,
        "area_id": loc.area_id,  # <-- fixed
        "trafo_no": loc.trafo_no,
        "bmc_nr": loc.bmc_nr,
        "pvv_nr": loc.pvv_nr,
        "pvc_nr": loc.pvc_nr,
    }
