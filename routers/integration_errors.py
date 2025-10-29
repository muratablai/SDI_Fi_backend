# routers/integration_errors.py
from __future__ import annotations
from fastapi import APIRouter, Query, Response
from typing import Optional
from models import BillingIntegrationError

router = APIRouter(prefix="/integration/errors", tags=["integration-errors"])

@router.get("")
async def list_errors(
    response: Response,
    document_id: Optional[str] = Query(None),  # UUID as string
    partner: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    q = BillingIntegrationError.all()
    if document_id is not None:
        q = q.filter(document_id=document_id)
    if partner:
        q = q.filter(partner=partner)

    total = await q.count()
    rows = await q.order_by("-occurred_at").offset(offset).limit(limit).values(
        "id",
        "document_id",
        "line_id",
        "partner",
        "source_filename",
        "export_seq",
        "error_code",
        "field_name",
        "message",
        "severity",
        "raw_row",
        "occurred_at",
    )
    response.headers["X-Total-Count"] = str(total)
    return rows
