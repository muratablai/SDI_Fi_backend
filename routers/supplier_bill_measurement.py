# routers/supplier_bill_measurements.py
from fastapi import APIRouter, Depends, HTTPException
from tortoise.queryset import QuerySet
from uuid import UUID

from models import SupplierBillMeasurement
from schemas import SupplierBillMeasurementRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item

router = APIRouter(prefix="/supplier-bill-measurements", tags=["supplier-bill-measurements"])

ALLOWED_SORTS = {
    "id", "meter_no", "channel", "period_start", "period_end", "index_old", "index_new", "energy_value", "unit"
}

def _as_uuid(v):
    try:
        return UUID(str(v))
    except Exception:
        return None

@router.get("", response_model=list[SupplierBillMeasurementRead])
async def list_supplier_bill_measurements(params: RAListParams = Depends()):
    filters = params.filters or {}
    qs: QuerySet[SupplierBillMeasurement] = SupplierBillMeasurement.all()

    fmap = {
        "bill_id":      lambda q, v: q.filter(bill_id=_as_uuid(v)) if _as_uuid(v) else q,
        "meter_no":     lambda q, v: q.filter(meter_no__icontains=str(v)),
        "channel":      lambda q, v: q.filter(channel=str(v)),
        # period filters (optional)
        "period_start_gte": lambda q, v: q.filter(period_start__gte=str(v)),
        "period_end_lte":   lambda q, v: q.filter(period_end__lte=str(v)),
    }
    qs = apply_filter_map(qs, filters, fmap)
    order = parse_sort(params.sort, ALLOWED_SORTS)

    to_pyd = lambda o: SupplierBillMeasurementRead.model_validate(o, from_attributes=True)
    return await paginate_and_respond(qs, params.skip, params.limit, order, to_pyd)

@router.get("/{measurement_id}", response_model=SupplierBillMeasurementRead)
async def get_supplier_bill_measurement(measurement_id: str):
    obj = await SupplierBillMeasurement.get_or_none(id=measurement_id)
    if not obj:
        raise HTTPException(404, "SupplierBillMeasurement not found")
    return respond_item(obj, lambda o: SupplierBillMeasurementRead.model_validate(o, from_attributes=True))
