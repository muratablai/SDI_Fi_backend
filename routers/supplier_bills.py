# routers/supplier_bills.py
from fastapi import APIRouter, Depends, HTTPException, Request
from tortoise.queryset import QuerySet
from datetime import datetime, time

from models import SupplierBill
from schemas import SupplierBillRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item
from bill_interpreter.service import scan_once

router = APIRouter(prefix="/supplier-bills", tags=["supplier-bills"])

ALLOWED_SORTS = {"id", "invoice_series", "invoice_number", "issue_date", "created_at", "pod_od"}

def _as_str(v): return str(v) if v is not None else None

@router.get("", response_model=list[SupplierBillRead])
async def list_bills(request: Request, params: RAListParams = Depends()):
    filters = params.filters or {}
    qs: QuerySet[SupplierBill] = SupplierBill.all().prefetch_related("supplier")

    # Map RA filters → Tortoise filters
    fmap = {
        "invoice_series": lambda q, v: q.filter(invoice_series__icontains=_as_str(v)),
        "invoice_number": lambda q, v: q.filter(invoice_number__icontains=_as_str(v)),
        "pod_od":        lambda q, v: q.filter(pod_od__icontains=_as_str(v)),
        "supplier_code": lambda q, v: q.filter(supplier__code__icontains=_as_str(v)),
        "supplier_name": lambda q, v: q.filter(supplier__name__icontains=_as_str(v)),
    }
    qs = apply_filter_map(qs, filters, fmap)

    order = parse_sort(params.sort, ALLOWED_SORTS)

    def to_pyd(obj: SupplierBill) -> SupplierBillRead:
        base = str(request.base_url).rstrip("/")  # e.g. http://localhost:8000
        pdf_url_abs = f"{base}{obj.pdf_path}" if obj.pdf_path and not obj.pdf_path.startswith("http") else obj.pdf_path
        return SupplierBillRead(
            id=str(obj.id),
            supplier_code=(obj.supplier.code if obj.supplier else None),
            supplier_name=(obj.supplier.name if obj.supplier else None),
            invoice_series=obj.invoice_series,
            invoice_number=obj.invoice_number,
            issue_date=(obj.issue_date and datetime.combine(obj.issue_date, time.min)),
            pod_od=obj.pod_od,
            pdf_url=pdf_url_abs,  # send absolute here
            created_at=obj.created_at,
        )

    return await paginate_and_respond(qs, params.skip, params.limit, order, to_pyd)

@router.get("/{bill_id}", response_model=SupplierBillRead)
async def get_bill(request:Request, bill_id: str):
    obj = await SupplierBill.get_or_none(id=bill_id).prefetch_related("supplier")
    if not obj:
        raise HTTPException(404, "Bill not found")
    def to_pyd(o: SupplierBill) -> SupplierBillRead:
        base = str(request.base_url).rstrip("/")  # e.g. http://localhost:8000
        pdf_url_abs = f"{base}{obj.pdf_path}" if obj.pdf_path and not obj.pdf_path.startswith("http") else obj.pdf_path
        return SupplierBillRead(
            id=str(o.id),
            supplier_code=(o.supplier.code if o.supplier else None),
            supplier_name=(o.supplier.name if o.supplier else None),
            invoice_series=o.invoice_series,
            invoice_number=o.invoice_number,
            issue_date=(o.issue_date and datetime.combine(o.issue_date, time.min)),
            pod_od=o.pod_od,
            pdf_url=pdf_url_abs,
            created_at=o.created_at,
        )
    return respond_item(obj, to_pyd)

@router.post("/scan")
async def trigger_scan():
    """Manual trigger; background loop already runs, but this lets you kick it instantly."""
    n = await scan_once()
    return {"processed": n}
