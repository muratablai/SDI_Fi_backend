from typing import List
from fastapi import APIRouter, Depends, Request
from models import Location, User
from schemas import LocationRead
from deps import get_current_active_user
from api_utils import RAListParams, parse_sort, paginate_and_respond

router = APIRouter(prefix="/locations", tags=["locations"])

ALLOWED_SORTS = {"id", "name"}

@router.get("", response_model=List[LocationRead])
async def list_locations(
    request: Request,
    params: RAListParams = Depends(),
    user: User = Depends(get_current_active_user),
):
    qs = Location.all()
    order = parse_sort(params.sort, ALLOWED_SORTS)
    return await paginate_and_respond(qs, params.skip, params.limit, order, LocationRead.model_validate)
