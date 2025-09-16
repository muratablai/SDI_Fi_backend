# backend/routers/billing.py

import json
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from typing import List

from models import Billing
from schemas import BillingCreate, BillingRead
from deps import get_current_active_user

router = APIRouter(prefix="/billing", tags=["billing"])

@router.get("", response_model=List[BillingRead])
async def list_billing(
    request: Request,
    range: str = Query("[0,9]"),
    sort: str = Query('["id","ASC"]'),
    user = Depends(get_current_active_user),
):
    # Decode React-Admin parameters
    start, end = json.loads(range)
    skip = int(start)
    limit = int(end) - skip + 1
    sort_field, sort_order = json.loads(sort)

    # If admin, show all; otherwise only their own
    if user.is_admin:
        qs = Billing.all()
    else:
        qs = Billing.filter(owner_id=user.id)

    # Total count before pagination
    total = await qs.count()

    # Apply sort & pagination in the DB
    order = f"{'-' if sort_order.upper() == 'DESC' else ''}{sort_field}"
    items = await qs.order_by(order).offset(skip).limit(limit)

    # Build Content-Range header
    end_real = skip + max(len(items) - 1, 0)
    content_range = f"items {skip}-{end_real}/{total}"

    # Return JSON + header for React-Admin pagination
    return JSONResponse(
        content=[BillingRead.model_validate(b).model_dump() for b in items],
        headers={"Content-Range": content_range},
    )

@router.post("", response_model=BillingRead)
async def create_billing(
    billing: BillingCreate,
    user = Depends(get_current_active_user),
):
    b = await Billing.create(
        owner_id=user.id,
        period_start=billing.period_start,
        period_end=billing.period_end,
        amount=billing.amount,
        allowed_user_ids=[str(u) for u in billing.allowed_user_ids or []],
    )
    return BillingRead.model_validate(b)
