# routers/od_pods.py
from fastapi import APIRouter, Depends, HTTPException
from models import OdPod
from schemas import OdPodCreate, OdPodUpdate, OdPodRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item

router = APIRouter(prefix="/od-pods", tags=["od-pods"])

@router.get("", response_model=list[OdPodRead])
async def list_odpods(params: RAListParams = Depends()):
    qs = OdPod.all().select_related("site", "operator")
    fmap = {
        "pod_od": lambda q, v: q.filter(pod_od__icontains=str(v)),
        "site": lambda q, v: q.filter(site_id=int(v)),
        "operator_id": lambda q, v: q.filter(operator_id=int(v)),
        "valid": lambda q, v: (q.filter(valid_to__isnull=True) if v else q.filter(valid_to__isnull=False)),
    }
    qs = apply_filter_map(qs, params.filters, fmap)
    order = parse_sort(params.sort, ["id", "pod_od", "name", "site_id", "operator_id", "valid_from", "valid_to", "created_at", "updated_at"])
    return await paginate_and_respond(qs, params.skip, params.limit, order, lambda m: OdPodRead.model_validate(m))

@router.get("/{od_pod_id}", response_model=OdPodRead)
async def get_odpod(od_pod_id: int):
    obj = await OdPod.get_or_none(id=od_pod_id)
    if not obj:
        raise HTTPException(404, "OD POD not found")
    return respond_item(obj, lambda m: OdPodRead.model_validate(m))

@router.post("", response_model=OdPodRead, status_code=201)
async def create_odpod(payload: OdPodCreate):
    obj = await OdPod.create(**payload.model_dump())
    return respond_item(obj, lambda m: OdPodRead.model_validate(m), status_code=201)

@router.put("/{od_pod_id}", response_model=OdPodRead)
async def update_odpod(od_pod_id: int, payload: OdPodUpdate):
    obj = await OdPod.get_or_none(id=od_pod_id)
    if not obj:
        raise HTTPException(404, "OD POD not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await obj.save()
    return respond_item(obj, lambda m: OdPodRead.model_validate(m))
