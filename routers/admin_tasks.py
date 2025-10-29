from __future__ import annotations
from fastapi import APIRouter, Body
from datetime import datetime
from typing import Optional, List

from services.background import run_consolidate, run_allocate

router = APIRouter(prefix="/admin/tasks", tags=["admin-tasks"])


@router.post("/consolidate")
async def consolidate(
    start: datetime = Body(...),
    end: datetime = Body(...),
    meter_nos: Optional[List[str]] = Body(None),
):
    return await run_consolidate(start, end, meter_nos)


@router.post("/allocate")
async def allocate(
    scope: str = Body(...),
    scope_id: int = Body(...),
    start: datetime = Body(...),
    end: datetime = Body(...),
    method: str = Body("equal_split"),
):
    return await run_allocate(scope, scope_id, start, end, method=method)
