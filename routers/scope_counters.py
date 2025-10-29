from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Query, Response
from models import MeterData
from services.scope_utils import meters_in_scope

router = APIRouter(prefix="/scope/counters", tags=["scope-counters"])


@router.get("")
async def list_scope_counters(
    response: Response,
    scope: str = Query(...),
    scope_id: int = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
):
    """
    Returns per-meter canonical COUNTERS (not energies) for a scope,
    with provenance fields for RA drilldown.
    """
    meters = await meters_in_scope(scope, scope_id)
    items = []
    for m in meters:
        rows = await (
            MeterData.filter(meter_no=m.meter_no, timestamp__gte=start, timestamp__lt=end)
            .order_by("timestamp")
            .values(
                "id",
                "meter_no",
                "timestamp",
                "active_import",
                "active_export",
                "reactive_import",
                "reactive_export",
                "reactive_q1",
                "reactive_q2",
                "reactive_q3",
                "reactive_q4",
                "estimated",
                "estimation_method",
                "chosen_source_code",
                "chosen_raw_id",
                "quality",
                "reset_detected",
                "constant",
            )
        )
        for r in rows:
            r.update({"scope": scope, "scope_id": scope_id})
            items.append(r)
    response.headers["X-Total-Count"] = str(len(items))
    return items
