from fastapi import APIRouter, Depends, HTTPException
from models import MeterData
from schemas import MeterDataCreate, MeterDataRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item

router = APIRouter(prefix="/meter-data", tags=["meter-data"])

@router.get("", response_model=list[MeterDataRead])
async def list_meter_data(params: RAListParams = Depends()):
    qs = MeterData.all()
    fmap = {
        "meter_no": lambda q, v: q.filter(meter_no=str(v)),
        "timestamp_gte": lambda q, v: q.filter(timestamp__gte=v),
        "timestamp_lte": lambda q, v: q.filter(timestamp__lte=v),
        "date_gte": lambda q, v: q.filter(timestamp__gte=v),
        "date_lte": lambda q, v: q.filter(timestamp__lte=v),
        "range": lambda q, v: q,  # front-end quick filters (today/7d/30d/ytd); implement if needed
        "recent": lambda q, v: q,  # optional
        "month": lambda q, v: q.filter(timestamp__startswith=str(v)),  # "YYYY-MM"
        "olderThanMonths": lambda q, v: q,  # optional
    }
    qs = apply_filter_map(qs, params.filters, fmap)
    order = parse_sort(params.sort, ["id", "meter_no", "timestamp", "fa", "fr", "ra"])
    return await paginate_and_respond(qs, params.skip, params.limit, order, lambda m: MeterDataRead.model_validate(m))

@router.post("", response_model=MeterDataRead, status_code=201)
async def create_meter_data(payload: MeterDataCreate):
    obj = await MeterData.create(**payload.model_dump())
    return respond_item(obj, lambda m: MeterDataRead.model_validate(m), status_code=201)
