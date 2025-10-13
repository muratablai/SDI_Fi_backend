# routers/location_tariffs.py

from __future__ import annotations
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from tortoise.queryset import QuerySet
from tortoise.expressions import Q

from models import LocationTariff, Tariff, User
from schemas import LocationTariffRead
from deps import get_current_active_user
from api_utils import RAListParams, parse_sort, paginate_and_respond

router = APIRouter(prefix="/location-tariffs", tags=["location-tariffs"])

ALLOWED_SORTS = {
    "id","location_id","tariff_id","operator",
    "valid_from","valid_to","is_primary","created_at","updated_at",
}

def _as_bool(v) -> Optional[bool]:
    if v is None: return None
    if isinstance(v, bool): return v
    s = str(v).strip().lower()
    if s in {"1","true","yes"}: return True
    if s in {"0","false","no"}: return False
    return None

@router.get("", response_model=List[LocationTariffRead])
async def list_location_tariffs(
    params: RAListParams = Depends(),
    user: User = Depends(get_current_active_user),
):
    filters = dict(params.filters or {})

    location_id = filters.get("location_id")
    operator: Optional[str] = filters.get("operator")
    active_flag = _as_bool(filters.get("active"))

    at_raw = filters.get("at")
    if isinstance(at_raw, str):
        try:
            at = datetime.fromisoformat(at_raw.replace("Z","+00:00"))
        except Exception:
            at = datetime.now(timezone.utc)
    else:
        at = datetime.now(timezone.utc)

    qs: QuerySet[LocationTariff] = LocationTariff.all().prefetch_related("tariff")

    if location_id is not None:
        qs = qs.filter(location_id=int(location_id))
    if operator:
        qs = qs.filter(operator__icontains=str(operator))

    if active_flag is True:
        qs = qs.filter(Q(valid_from__lte=at) | Q(valid_from__isnull=True))
        qs = qs.filter(Q(valid_to__gte=at) | Q(valid_to__isnull=True))
    elif active_flag is False:
        active_q = (Q(valid_from__lte=at) | Q(valid_from__isnull=True)) & (
            Q(valid_to__gte=at) | Q(valid_to__isnull=True)
        )
        qs = qs.exclude(active_q)

    order = parse_sort(params.sort, ALLOWED_SORTS)

    def to_read(m: LocationTariff) -> LocationTariffRead:
        t: Optional[Tariff] = getattr(m, "tariff", None)
        return LocationTariffRead.model_validate(
            {
                "id": m.id,
                "location_id": m.location_id,
                "tariff_id": m.tariff_id,
                "operator": m.operator,
                "valid_from": m.valid_from,
                "valid_to": m.valid_to,
                "is_primary": m.is_primary,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
                "tariff_code": getattr(t, "code", None),
                "tariff_description": getattr(t, "description", None),
                "tariff_unit": getattr(t, "unit", None),
                "tariff_billing_type": getattr(t, "billing_type", None),
            }
        )

    return await paginate_and_respond(
        qs,
        params.skip,
        params.limit,
        order,
        to_read,
    )
