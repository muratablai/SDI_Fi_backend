from fastapi import APIRouter, Depends, HTTPException
from tortoise.expressions import Q
from models import TariffAssignment, Site, OdPod, Pod, Tariff
from schemas import TariffAssignmentCreate, TariffAssignmentRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item

router = APIRouter(prefix="/location-tariffs", tags=["tariff-assignments"])

def to_read(m: TariffAssignment) -> TariffAssignmentRead:
    # We expose scope_type/scope_id via schema; DB has site/od_pod/pod FKs
    scope_type = "site" if m.site else ("od_pod" if m.od_pod else "pod")
    scope_id = m.site or m.od_pod or m.pod
    base = {
        "id": m.id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "tariff_id": m.tariff,
        "operator": m.operator,
        "valid_from": m.valid_from,
        "valid_to": m.valid_to,
        "is_primary": m.is_primary,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }
    return TariffAssignmentRead.model_validate(base)

@router.get("", response_model=list[TariffAssignmentRead])
async def list_assignments(params: RAListParams = Depends()):
    qs = TariffAssignment.all()
    # Support RA views that pass location_id (means pod_id in new model)
    def by_location_id(q, v):
        return q.filter(pod_id=int(v))
    fmap = {
        "scope_type": lambda q, v: q.filter(
            Q(site_id__not_isnull=True) if v == "site"
            else Q(od_pod_id__not_isnull=True) if v == "od_pod"
            else Q(pod_id__not_isnull=True)
        ),
        "scope_id": lambda q, v: q.filter(
            Q(site_id=int(v)) | Q(od_pod_id=int(v)) | Q(pod_id=int(v))
        ),
        "location_id": by_location_id,
        "operator": lambda q, v: q.filter(operator__icontains=str(v)),
        "active": lambda q, v: q.filter(valid_to__isnull=True) if v else q,
    }
    qs = apply_filter_map(qs, params.filters, fmap)
    order = parse_sort(params.sort, ["id", "tariff_id", "operator", "valid_from", "valid_to", "is_primary", "created_at"])
    return await paginate_and_respond(qs, params.skip, params.limit, order, to_read)

@router.post("", response_model=TariffAssignmentRead, status_code=201)
async def create_assignment(payload: TariffAssignmentCreate):
    data = payload.model_dump()
    scope_type = data.pop("scope_type")
    scope_id = int(data.pop("scope_id"))
    # route to the correct FK
    fk = {"site_id": None, "od_pod_id": None, "pod_id": None}
    if scope_type == "site":
        fk["site_id"] = scope_id
    elif scope_type == "od_pod":
        fk["od_pod_id"] = scope_id
    else:
        fk["pod_id"] = scope_id
    obj = await TariffAssignment.create(**fk, **data)
    return respond_item(obj, to_read, status_code=201)
