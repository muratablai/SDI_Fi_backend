from typing import List
from datetime import timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from models import MeterData, Meter, User
from schemas import MeterDataCreate, MeterDataRead
from deps import get_current_active_user
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond

router = APIRouter(prefix="/meter-data", tags=["meter-data"])

ALLOWED_SORTS = {"id", "meter_no", "timestamp", "fa", "fr", "ra", "rr", "p_fa", "p_fr"}

@router.get("", response_model=List[MeterDataRead])
async def list_meter_data(
    request: Request,
    params: RAListParams = Depends(),
    user: User = Depends(get_current_active_user),
):
    qs = MeterData.all()

    async def _resolve_meter_no_from_id(meter_id):
        m = await Meter.get_or_none(id=meter_id)
        if not m:
            raise HTTPException(status_code=404, detail="Meter not found")
        return m.meter_no

    # Support both:
    #  - meter_no: "1234..."
    #  - meter_id: 42  (we translate to its meter_no)
    #  - date_gte/date_lte (your Show component)
    #  - timestamp_gte/timestamp_lte (backward compat)
    filters = params.filters.copy()
    if "meter_id" in filters and filters["meter_id"] is not None:
        meter_no_val = await _resolve_meter_no_from_id(filters["meter_id"])
        filters["meter_no"] = meter_no_val

    # normalize aliases
    if "date_gte" in filters and "timestamp_gte" not in filters:
        filters["timestamp_gte"] = filters["date_gte"]
    if "date_lte" in filters and "timestamp_lte" not in filters:
        filters["timestamp_lte"] = filters["date_lte"]

    fmap = {
        "meter_no":      lambda q, v: q.filter(meter_no=str(v)),
        "timestamp_gte": lambda q, v: q.filter(timestamp__gte=v),
        "timestamp_lte": lambda q, v: q.filter(timestamp__lte=v),
    }
    qs = apply_filter_map(qs, filters, fmap)

    order = parse_sort(params.sort, ALLOWED_SORTS)
    # if frontend sets recent=true elsewhere, you can still override to '-timestamp'
    if filters.get("recent"):
        order = "-timestamp"

    return await paginate_and_respond(qs, params.skip, params.limit, order, MeterDataRead.model_validate)

@router.post("", response_model=MeterDataRead)
async def create_meter_data(
    data: MeterDataCreate,
    user: User = Depends(get_current_active_user),
):
    ts = data.timestamp
    if ts.tzinfo is None:
        data.timestamp = ts.replace(tzinfo=timezone.utc)
    else:
        data.timestamp = ts.astimezone(timezone.utc)

    m = await MeterData.create(**data.model_dump())
    return MeterDataRead.model_validate(m)
