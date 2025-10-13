# routers/meters.py
from fastapi import APIRouter, Depends, HTTPException
from models import Meter
from schemas import MeterCreate, MeterUpdate, MeterRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item
from tortoise.queryset import QuerySet
from deps import get_current_active_user

router = APIRouter(prefix="/meters", tags=["meters"])

ALLOWED_SORTS = {
    "id", "meter_no", "name", "created_at", "updated_at"
}

def _as_int(v):
    try:
        return int(v)
    except Exception:
        return None

@router.get("", response_model=list[MeterRead])
async def list_meters(
    params: RAListParams = Depends(),
    user = Depends(get_current_active_user),
):
    filters = params.filters or {}

    # include FKs for potential nested views
    qs: QuerySet[Meter] = Meter.all().prefetch_related("pod", "od_pod", "site")

    # Map React-Admin filter keys -> Tortoise filters
    fmap = {
        # text filters
        "meter_no": lambda q, v: q.filter(meter_no__icontains=str(v)),
        "name":     lambda q, v: q.filter(name__icontains=str(v)),

        # exact id
        "id":       lambda q, v: q.filter(id=_as_int(v)) if _as_int(v) is not None else q,

        # FK ids (IMPORTANT)
        # UI sends {"pod": <id>} on the OD-POD / POD show "Meters" tab
        "pod":      lambda q, v: q.filter(pod_id=_as_int(v)) if _as_int(v) is not None else q,
        "od_pod":   lambda q, v: q.filter(od_pod_id=_as_int(v)) if _as_int(v) is not None else q,
        "site":     lambda q, v: q.filter(site_id=_as_int(v)) if _as_int(v) is not None else q,

        # Legacy aliases (if any UI piece still sends these)
        "pod_id":   lambda q, v: q.filter(pod_id=_as_int(v)) if _as_int(v) is not None else q,
        "od_pod_id":lambda q, v: q.filter(od_pod_id=_as_int(v)) if _as_int(v) is not None else q,
        "site_id":  lambda q, v: q.filter(site_id=_as_int(v)) if _as_int(v) is not None else q,
    }

    qs = apply_filter_map(qs, filters, fmap)

    order = parse_sort(params.sort, ALLOWED_SORTS)

    return await paginate_and_respond(
        qs=qs,
        skip=params.skip,
        limit=params.limit,
        order=order,
        to_pydantic=lambda m: MeterRead.model_validate(m),
    )

@router.get("/{meter_id}", response_model=MeterRead)
async def get_meter(meter_id: int):
    obj = await Meter.get_or_none(id=meter_id)
    if not obj:
        raise HTTPException(404, "Meter not found")
    return respond_item(obj, lambda m: MeterRead.model_validate(m))

@router.post("", response_model=MeterRead, status_code=201)
async def create_meter(payload: MeterCreate):
    obj = await Meter.create(**payload.model_dump())
    return respond_item(obj, lambda m: MeterRead.model_validate(m), status_code=201)

@router.put("/{meter_id}", response_model=MeterRead)
async def update_meter(meter_id: int, payload: MeterUpdate):
    obj = await Meter.get_or_none(id=meter_id)
    if not obj:
        raise HTTPException(404, "Meter not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await obj.save()
    return respond_item(obj, lambda m: MeterRead.model_validate(m))
