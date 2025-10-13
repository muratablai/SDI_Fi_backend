from fastapi import APIRouter, Depends, HTTPException
from models import Billing, User
from schemas import BillingCreate, BillingRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item
from deps import get_current_active_user

router = APIRouter(prefix="/billing", tags=["billing"])

@router.post("", response_model=BillingRead, status_code=201)
async def create_bill(payload: BillingCreate, current_user = Depends(get_current_active_user)):
    obj = await Billing.create(owner_id=current_user.id, **payload.model_dump())
    return BillingRead.model_validate(obj)

@router.get("/{bill_id}", response_model=BillingRead)
async def get_bill(bill_id: str):
    obj = await Billing.get_or_none(id=bill_id)
    if not obj:
        raise HTTPException(404, "Bill not found")
    return respond_item(obj, lambda m: BillingRead.model_validate(m))
