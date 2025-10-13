# routers/tariff_operator.py
from __future__ import annotations
from typing import List, Dict

from fastapi import APIRouter, Depends

from models import TariffOperatorPrice, User
from deps import get_current_active_user

router = APIRouter(prefix="/tariff-operators", tags=["tariffs"])

@router.get("", response_model=List[Dict[str, str]])
async def list_operators(user: User = Depends(get_current_active_user)):
    """
    Distinct operator names from the operator-price table.
    Returns items with `id` and `name` (both string names) for RA Selects.
    """
    rows = await TariffOperatorPrice.all().values_list("operator", flat=True)
    uniq = sorted({(op or "").strip() for op in rows if (op or "").strip()})
    return [{"id": op, "name": op} for op in uniq]
