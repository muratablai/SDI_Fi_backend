# routers/meter_energy.py
from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, Request

from api_utils import RAListParams, respond_plain_list
from services.energy_unified import unified_energy_query

router = APIRouter(prefix="/meter-data/energy", tags=["meter-energy"])

@router.get("", response_model=List[dict])
async def list_energy(request: Request, params: RAListParams = Depends()):
    filters = dict(params.filters or {})
    items = await unified_energy_query(request, filters=filters, sort_json=params.sort)
    return respond_plain_list(items, params.skip, params.limit)
