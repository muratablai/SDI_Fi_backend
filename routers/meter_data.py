import json
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from typing import List

from models import MeterData
from schemas import MeterDataCreate, MeterDataRead
from deps import get_current_active_user

router = APIRouter(prefix="/meter-data", tags=["meter-data"])

@router.get("", response_model=List[MeterDataRead])
async def list_meter_data(
    request: Request,
    range: str = Query("[0,9]"),
    filter: str = Query("{}"),
    sort: str = Query('["id","ASC"]'),
    user = Depends(get_current_active_user),
):
    start, end = json.loads(range)
    skip = int(start)
    limit = int(end) - skip + 1
    sort_field, sort_order = json.loads(sort)
    qs = MeterData.all()
    total = await qs.count()
    order = f"{'-' if sort_order.upper()=='DESC' else ''}{sort_field}"
    items = await qs.order_by(order).offset(skip).limit(limit)
    end_real = skip + len(items) - 1
    content_range = f"items {skip}-{end_real}/{total}"
    return JSONResponse(
        content=[MeterDataRead.model_validate(m).model_dump() for m in items],
        headers={"Content-Range": content_range},
    )

@router.post("", response_model=MeterDataRead)
async def create_meter_data(
    data: MeterDataCreate,
    user = Depends(get_current_active_user),
):
    #m = await MeterData.create(**data.dict())
    m = await MeterData.create(**data.model_dump())
    return MeterDataRead.model_validate(m)
