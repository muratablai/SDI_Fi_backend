# routers/meters.py
from typing import List
from fastapi import APIRouter, Depends, Path, Request, HTTPException
from models import Meter, User
from schemas import MeterRead
from deps import get_current_active_user
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond

router = APIRouter(prefix="/meters", tags=["meters"])

ALLOWED_SORTS = {"id", "name", "meter_no", "location_id", "created_at", "updated_at"}

@router.get("", response_model=List[MeterRead])
async def list_meters(
    request: Request,
    params: RAListParams = Depends(),
    user: User = Depends(get_current_active_user),
):
    qs = Meter.all()

    def _to_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    fmap = {
        "location_id": lambda q, v: q.filter(location_id=_to_int(v)) if _to_int(v) is not None else q,
        "area_id":     lambda q, v: q.filter(area_id=_to_int(v))     if _to_int(v) is not None else q,
        "meter_no":    lambda q, v: q.filter(meter_no=str(v)),
        "name":        lambda q, v: q.filter(name__icontains=str(v)),
        "pod_sdi": lambda q, v: q.filter(location__pod_sdi=str(v)),
        # If you ever filter by POD, you can also support:
        # "pod_sdi":   lambda q, v: q.filter(location__pod_sdi=str(v)),
    }
    qs = apply_filter_map(qs, params.filters, fmap)

    order = parse_sort(params.sort, ALLOWED_SORTS)
    return await paginate_and_respond(qs, params.skip, params.limit, order, MeterRead.model_validate)

@router.get("/{meter_id}", response_model=MeterRead)
async def get_meter(
    meter_id: int = Path(...),
    user: User = Depends(get_current_active_user),
):
    m = await Meter.get_or_none(id=meter_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meter not found")
    return MeterRead.model_validate(m)
