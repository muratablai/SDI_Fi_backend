from fastapi import APIRouter, Depends, HTTPException
from models import MeterAssignment
from schemas import MeterAssignmentCreate, MeterAssignmentUpdate, MeterAssignmentRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item

router = APIRouter(prefix="/meter-assignments", tags=["meter-assignments"])

@router.get("", response_model=list[MeterAssignmentRead])
async def list_assignments(params: RAListParams = Depends()):
    qs = MeterAssignment.all()
    fmap = {
        "pod_id": lambda q, v: q.filter(pod_id=int(v)),
        "meter_id": lambda q, v: q.filter(meter_id=int(v)),
        "active": lambda q, v: q.filter(valid_to__isnull=True) if v else q.filter(valid_to__isnull=False),
        "valid_from_gte": lambda q, v: q.filter(valid_from__gte=v),
        "valid_to_lte": lambda q, v: q.filter(valid_to__lte=v),
    }
    qs = apply_filter_map(qs, params.filters, fmap)
    order = parse_sort(params.sort, ["id", "pod_id", "meter_id", "valid_from", "valid_to"])
    return await paginate_and_respond(qs, params.skip, params.limit, order, lambda m: MeterAssignmentRead.model_validate(m))

@router.get("/{assignment_id}", response_model=MeterAssignmentRead)
async def get_assignment(assignment_id: int):
    obj = await MeterAssignment.get_or_none(id=assignment_id)
    if not obj:
        raise HTTPException(404, "Assignment not found")
    return respond_item(obj, lambda m: MeterAssignmentRead.model_validate(m))

@router.post("", response_model=MeterAssignmentRead, status_code=201)
async def create_assignment(payload: MeterAssignmentCreate):
    obj = await MeterAssignment.create(**payload.model_dump())
    return respond_item(obj, lambda m: MeterAssignmentRead.model_validate(m), status_code=201)

@router.put("/{assignment_id}", response_model=MeterAssignmentRead)
async def update_assignment(assignment_id: int, payload: MeterAssignmentUpdate):
    obj = await MeterAssignment.get_or_none(id=assignment_id)
    if not obj:
        raise HTTPException(404, "Assignment not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await obj.save()
    return respond_item(obj, lambda m: MeterAssignmentRead.model_validate(m))
