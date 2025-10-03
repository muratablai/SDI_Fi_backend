from fastapi import APIRouter, HTTPException, Path
from typing import List
from models import MeterAssignment
from schemas import MeterAssignmentCreate, MeterAssignmentRead, MeterAssignmentUpdate

router = APIRouter(prefix="/meter-assignments", tags=["meter-assignments"])

@router.get("", response_model=List[MeterAssignmentRead])
async def list_assignments():
    rows = await MeterAssignment.all().order_by("-valid_from")
    return [MeterAssignmentRead.model_validate(r) for r in rows]

@router.post("", response_model=MeterAssignmentRead, status_code=201)
async def create_assignment(body: MeterAssignmentCreate):
    row = await MeterAssignment.create(**body.model_dump())
    return MeterAssignmentRead.model_validate(row)

@router.patch("/{assignment_id}", response_model=MeterAssignmentRead)
async def update_assignment(assignment_id: int, body: MeterAssignmentUpdate):
    row = await MeterAssignment.get_or_none(id=assignment_id)
    if not row:
        raise HTTPException(404, "Assignment not found")
    await row.update_from_dict({k: v for k, v in body.model_dump(exclude_unset=True).items()}).save()
    return MeterAssignmentRead.model_validate(row)
