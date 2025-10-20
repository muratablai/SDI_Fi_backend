# routers/supplier_bill_lines.py
from fastapi import APIRouter, Depends, HTTPException
from tortoise.queryset import QuerySet
from uuid import UUID

from models import SupplierBillLine
from schemas import SupplierBillLineRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item

router = APIRouter(prefix="/supplier-bill-lines", tags=["supplier-bill-lines"])

ALLOWED_SORTS = {
    "id", "name", "period_start", "period_end", "qty", "price", "value"
}

def _as_uuid(v):
    try:
        return UUID(str(v))
    except Exception:
        return None

@router.get("", response_model=list[SupplierBillLineRead])
async def list_supplier_bill_lines(params: RAListParams = Depends()):
    filters = params.filters or {}
    qs: QuerySet[SupplierBillLine] = SupplierBillLine.all()

    fmap = {
        "bill_id":      lambda q, v: q.filter(bill_id=_as_uuid(v)) if _as_uuid(v) else q,
        "name":         lambda q, v: q.filter(name__icontains=str(v)),
        # period filters (optional)
        "period_start_gte": lambda q, v: q.filter(period_start__gte=str(v)),
        "period_end_lte":   lambda q, v: q.filter(period_end__lte=str(v)),
    }
    qs = apply_filter_map(qs, filters, fmap)
    order = parse_sort(params.sort, ALLOWED_SORTS)

    to_pyd = lambda o: SupplierBillLineRead.model_validate(o, from_attributes=True)
    return await paginate_and_respond(qs, params.skip, params.limit, order, to_pyd)

@router.get("/{line_id}", response_model=SupplierBillLineRead)
async def get_supplier_bill_line(line_id: str):
    obj = await SupplierBillLine.get_or_none(id=line_id)
    if not obj:
        raise HTTPException(404, "SupplierBillLine not found")
    return respond_item(obj, lambda o: SupplierBillLineRead.model_validate(o, from_attributes=True))
