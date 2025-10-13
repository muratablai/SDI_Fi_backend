# routers/tariff_records.py
from __future__ import annotations
import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Request
from tortoise.queryset import QuerySet

from models import Tariff, TariffOperatorPrice, User
from deps import get_current_active_user
from api_utils import RAListParams, parse_sort, respond_plain_list

router = APIRouter(prefix="/tariff-records", tags=["tariff-records"])

ALLOWED_SORTS = {"operator", "code", "description", "unit", "billing_type", "price"}

@router.get("", response_model=List[Dict[str, Any]])
async def list_tariff_records(
    request: Request,
    params: RAListParams = Depends(),
    user: User = Depends(get_current_active_user),
):
    """
    Returns a flat list suitable for RA Lists:
      [{ id, operator, code, description, unit, billing_type, price }]
    Filters: operator, code, description, unit, billing_type (all optional).
    """
    filters = dict(params.filters or {})

    operator: Optional[str]     = filters.pop("operator", None)
    code: Optional[str]         = filters.pop("code", None)
    description: Optional[str]  = filters.pop("description", None)
    unit: Optional[str]         = filters.pop("unit", None)
    billing_type: Optional[str] = filters.pop("billing_type", None)
    _ = filters.pop("allRecords", None)  # accepted no-op

    qs: QuerySet[TariffOperatorPrice] = TariffOperatorPrice.all().select_related("tariff")

    if operator:
        qs = qs.filter(operator__icontains=str(operator))
    if code:
        qs = qs.filter(tariff__code__icontains=str(code))
    if description:
        qs = qs.filter(tariff__description__icontains=str(description))
    if unit:
        qs = qs.filter(tariff__unit__icontains=str(unit))
    if billing_type:
        qs = qs.filter(tariff__billing_type__icontains=str(billing_type))

    order = parse_sort(params.sort, ALLOWED_SORTS)
    if isinstance(order, str) and order:
        qs = qs.order_by(order)

    start = params.skip or 0
    limit = params.limit or 50
    total = await qs.count()
    rows: List[TariffOperatorPrice] = await qs.offset(start).limit(limit)

    payload = []
    for r in rows:
        t = r.tariff
        payload.append({
            "id": r.id,
            "operator": r.operator,
            "code": t.code if t else None,
            "description": t.description if t else None,
            "unit": t.unit if t else None,
            "billing_type": t.billing_type if t else None,
            "price": float(r.price or 0),
        })

    # Note: respond_plain_list(items, skip, limit, total)
    return respond_plain_list(payload, start, limit, total)
