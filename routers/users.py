import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from passlib.context import CryptContext

from models import User
from schemas import UserCreate, UserUpdate, UserRead
from deps import get_current_admin_user, get_current_active_user
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/users", tags=["users"])

ALLOWED_SORTS = {"id", "username", "email", "disabled", "is_admin"}

@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_active_user)):
    user_obj = UserRead.model_validate(current_user)
    payload  = jsonable_encoder(user_obj.model_dump())
    return JSONResponse(content=payload)

@router.post("", response_model=UserRead)
async def create_user(
    user_in: UserCreate,
    admin: User = Depends(get_current_admin_user),
):
    hashed = pwd_ctx.hash(user_in.password)
    user = await User.create(
        id=uuid.uuid4(),
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed,
    )
    return UserRead.model_validate(user)

@router.get("", response_model=List[UserRead])
async def list_users(
    params: RAListParams = Depends(),
    admin: User = Depends(get_current_admin_user),
):
    qs = User.all()

    # Filters: username (icontains), email (icontains), disabled, is_admin
    fmap = {
        "username": lambda q, v: q.filter(username__icontains=v),
        "email":    lambda q, v: q.filter(email__icontains=v),
        "disabled": lambda q, v: q.filter(disabled=bool(v)),
        "is_admin": lambda q, v: q.filter(is_admin=bool(v)),
    }
    qs = apply_filter_map(qs, params.filters, fmap)

    order = parse_sort(params.sort, ALLOWED_SORTS)
    return await paginate_and_respond(qs, params.skip, params.limit, order, UserRead.model_validate)

@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID = Path(...),
    admin:  User      = Depends(get_current_admin_user),
):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRead.model_validate(user)

@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_in:   UserUpdate,
    user_id:   uuid.UUID = Path(...),
    admin:     User      = Depends(get_current_admin_user),
):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    payload = {"username": user_in.username, "email": user_in.email}
    if user_in.password:
        payload["hashed_password"] = pwd_ctx.hash(user_in.password)
    await user.update_from_dict(payload).save()
    return UserRead.model_validate(user)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID = Path(...),
    admin:   User      = Depends(get_current_admin_user),
):
    deleted = await User.filter(id=user_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT)
