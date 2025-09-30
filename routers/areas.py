# app/routers/areas.py
from fastapi import APIRouter, Response, Query, HTTPException
from typing import Optional, Any, Dict
import json
from models import Area

router = APIRouter(prefix="/areas", tags=["areas"])

def _parse_json_param(param: Optional[str], default):
    if not param:
        return default
    try:
        return json.loads(param)
    except Exception:
        return default

@router.get("")  # GET /areas
async def list_areas(
    response: Response,
    sort: Optional[str] = Query(None),    # '["name","ASC"]'
    range: Optional[str] = Query(None),   # '[0,11]'
    filter: Optional[str] = Query(None),  # '{}'
):
    qs = Area.all()

    # filters
    f: Dict[str, Any] = _parse_json_param(filter, {})
    if "code" in f and f["code"]:
        qs = qs.filter(code=f["code"])
    if "name" in f and f["name"]:
        qs = qs.filter(name__icontains=f["name"])

    # sort
    s = _parse_json_param(sort, ["name", "ASC"])
    if isinstance(s, list) and len(s) == 2:
        field, order = s
        qs = qs.order_by(f"{'' if str(order).upper()=='ASC' else '-'}{field}")

    total = await qs.count()

    # range/pagination
    r = _parse_json_param(range, [0, 24])
    start, end = (r + [0, 24])[:2] if isinstance(r, list) else (0, 24)
    limit = end - start + 1
    rows = await qs.offset(start).limit(limit)

    # body must be a PLAIN ARRAY for ra-data-simple-rest
    data = [
        {
            "id": a.id,
            "code": a.code,
            "name": a.name,
            "address": a.address,
            "city": a.city,
            "county": a.county,
            "latitude": a.latitude,
            "longitude": a.longitude,
        }
        for a in rows
    ]

    response.headers["Content-Range"] = f"areas {start}-{start+len(data)-1}/{total}"
    response.headers["Access-Control-Expose-Headers"] = "Content-Range"
    return data

@router.get("/{id}")  # GET /areas/:id
async def get_area(id: int):
    a = await Area.get_or_none(id=id)
    if not a:
        raise HTTPException(404, "Area not found")
    return {
        "id": a.id,
        "code": a.code,
        "name": a.name,
        "address": a.address,
        "city": a.city,
        "county": a.county,
        "latitude": a.latitude,
        "longitude": a.longitude,
    }
