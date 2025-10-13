# routers/pods.py
from fastapi import APIRouter, Depends, HTTPException
from models import Pod
from schemas import PodCreate, PodUpdate, PodRead
from deps import get_current_active_user
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item
from tortoise.queryset import QuerySet

router = APIRouter(prefix="/pods", tags=["pods"])
ALLOWED_SORTS = {"id", "pod_sdi", "name", "created_at", "updated_at"}

def _as_int(v):
    try:
        return int(v)
    except Exception:
        return None

@router.get("", response_model=list[PodRead])
async def list_pods(
    params: RAListParams = Depends(),
    user = Depends(get_current_active_user),
):
    filters = params.filters or {}

    qs: QuerySet[Pod] = Pod.all().prefetch_related("site", "od_pod")

    # Map React-Admin filter keys to Tortoise filters.
    fmap = {
        # search by text
        "pod_sdi": lambda q, v: q.filter(pod_sdi__icontains=str(v)),
        "name":    lambda q, v: q.filter(name__icontains=str(v)),
        "role":    lambda q, v: q.filter(role=str(v)),

        # foreign keys (IMPORTANT):
        # UI sends numbers (ids) under keys `site` and `od_pod`
        "site":   lambda q, v: q.filter(site_id=_as_int(v)) if _as_int(v) is not None else q,
        "od_pod": lambda q, v: q.filter(od_pod_id=_as_int(v)) if _as_int(v) is not None else q,

        # allow exact id
        "id":      lambda q, v: q.filter(id=_as_int(v)) if _as_int(v) is not None else q,
    }

    qs = apply_filter_map(qs, filters, fmap)

    order = parse_sort(params.sort, ALLOWED_SORTS)

    return await paginate_and_respond(
        qs=qs,
        skip=params.skip,
        limit=params.limit,
        order=order,
        to_pydantic=lambda m: PodRead.model_validate(m),
    )

@router.get("/{pod_id}", response_model=PodRead)
async def get_pod(pod_id: int):
    obj = await Pod.get_or_none(id=pod_id)
    if not obj:
        raise HTTPException(404, "POD not found")
    return respond_item(obj, lambda m: PodRead.model_validate(m))

@router.post("", response_model=PodRead, status_code=201)
async def create_pod(payload: PodCreate):
    obj = await Pod.create(**payload.model_dump())
    return respond_item(obj, lambda m: PodRead.model_validate(m), status_code=201)

@router.put("/{pod_id}", response_model=PodRead)
async def update_pod(pod_id: int, payload: PodUpdate):
    obj = await Pod.get_or_none(id=pod_id)
    if not obj:
        raise HTTPException(404, "POD not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await obj.save()
    return respond_item(obj, lambda m: PodRead.model_validate(m))
