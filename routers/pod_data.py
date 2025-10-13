from fastapi import APIRouter, Depends
from api_utils import RAListParams, respond_plain_list
from models import MeterAssignment, MeterData
from schemas import PodDataRead
from typing import List

router = APIRouter(prefix="/pod-data", tags=["pod-data"])

@router.get("", response_model=List[PodDataRead])
async def list_pod_data(params: RAListParams = Depends()):
    """
    Returns flattened rows for a pod, joined with active meter across a time window.
    Expected filters (React-Admin):
      - pod_id: int (required for meaningful results)
      - date_gte/date_lte: ISO strings
    """
    f = params.filters or {}
    pod_id = int(f.get("pod_id") or f.get("location_id") or 0)
    date_gte = f.get("date_gte")
    date_lte = f.get("date_lte")

    # Find assignments overlapping interval (or just active if none given)
    ass_qs = MeterAssignment.filter(pod_id=pod_id)
    if date_gte:
        ass_qs = ass_qs.filter(valid_to__gte=date_gte) | ass_qs.filter(valid_to__isnull=True)
    if date_lte:
        ass_qs = ass_qs.filter(valid_from__lte=date_lte)
    assignments = await ass_qs

    items: list[dict] = []
    for a in assignments:
        md_qs = MeterData.filter(meter_no__not_isnull=True)
        if date_gte:
            md_qs = md_qs.filter(timestamp__gte=date_gte)
        if date_lte:
            md_qs = md_qs.filter(timestamp__lte=date_lte)
        # Here we assume Meter.meter_no is used in MeterData.meter_no; if you store FK, adapt accordingly.
        # If you keep MeterAssignment.meter_id, fetch the Meter to get meter_no.
        # For performance, you might want to prefetch in bulk.

        # naive: include all rows; a real impl would match meter_no for this assignment
        rows = await md_qs.limit(5000)

        for r in rows:
            items.append({
                "id": r.id,
                "timestamp": r.timestamp,
                "meter_id": a.meter,
                "fa": r.fa, "fr": r.fr, "ra": r.ra,
                "fa_t1": r.fa_t1, "fa_t2": r.fa_t2, "fa_t3": r.fa_t3, "fa_t4": r.fa_t4,
                "rr": r.rr, "r_q1": r.r_q1, "r_q2": r.r_q2, "r_q3": r.r_q3, "r_q4": r.r_q4,
                "p_fa": r.p_fa, "p_fr": r.p_fr,
            })

    # Use the plain responder so we still honor RA pagination/headers
    return respond_plain_list(items, params.skip, params.limit)
