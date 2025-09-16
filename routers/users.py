# backend/routers/users.py

import uuid
import json
from typing import List

from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from passlib.context import CryptContext

from models import User
from schemas import UserCreate, UserRead, UserUpdate
from deps import get_current_admin_user, get_current_active_user

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserRead)
async def read_me(
    current_user: User = Depends(get_current_active_user),  # ← must be a dependency!
):
    # Convert the Tortoise model to your Pydantic schema,
    # then into pure JSON-serializable primitives
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
    range: str = Query("[0,9]"),
    sort:  str = Query('["id","ASC"]'),
    filter: str = Query("{}"),
    admin: User = Depends(get_current_admin_user),
):
    start, end = json.loads(range)
    skip = int(start)
    limit = int(end) - skip + 1
    sort_field, sort_order = json.loads(sort)

    total = await User.all().count()
    order = f"{'-' if sort_order.upper()=='DESC' else ''}{sort_field}"
    items = await User.all().order_by(order).offset(skip).limit(limit)

    end_real     = skip + len(items) - 1
    content_range = f"items {skip}-{end_real}/{total}"
    data = [UserRead.model_validate(u).model_dump() for u in items]

    return JSONResponse(
        content=jsonable_encoder(data),
        headers={"Content-Range": content_range},
    )


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
async def update_user(user_in: UserUpdate, user_id: uuid.UUID = Path(...), admin: User = Depends(get_current_admin_user)):
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
