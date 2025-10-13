from fastapi import APIRouter, Depends, HTTPException
from models import User
from schemas import UserCreate, UserUpdate, UserRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item
from passlib.hash import bcrypt
from deps import get_current_user
import uuid

router = APIRouter(prefix="/users", tags=["users"])

# --- helpers ---------------------------------------------------------------

def to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "t", "yes", "y"}

async def to_user_read(m: User) -> UserRead:
    # Pydantic v2: from_attributes=True lets us validate from ORM objects
    return UserRead.model_validate(m)

# --- routes ----------------------------------------------------------------

@router.get("", response_model=list[UserRead])
async def list_users(params: RAListParams = Depends()):
    qs = User.all()
    fmap = {
        "username": lambda q, v: q.filter(username__icontains=str(v)),
        "email":    lambda q, v: q.filter(email__icontains=str(v)),
        "disabled": lambda q, v: q.filter(disabled=to_bool(v)),
        "is_admin": lambda q, v: q.filter(is_admin=to_bool(v)),
    }
    qs = apply_filter_map(qs, params.filters, fmap)
    order = parse_sort(params.sort, ["id", "username", "email", "disabled", "is_admin"])
    return await paginate_and_respond(qs, params.skip, params.limit, order, to_user_read)

# Put /me BEFORE /{user_id}, or constrain {user_id} below.
@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)):
    # DO NOT await here; model_validate is sync
    return UserRead.model_validate(current_user)

# Constrain to UUID so "me" won't match this route
@router.get("/{user_id:uuid}", response_model=UserRead)
async def get_user(user_id: uuid.UUID):
    obj = await User.get_or_none(id=user_id)
    if not obj:
        raise HTTPException(404, "User not found")
    return await respond_item(obj, to_user_read)

@router.post("", response_model=UserRead, status_code=201)
async def create_user(payload: UserCreate):
    hashed_password = bcrypt.hash(payload.password)
    obj = await User.create(
        username=payload.username,
        email=str(payload.email),
        hashed_password=hashed_password,
        disabled=False,
        is_admin=False,
    )
    return await respond_item(obj, to_user_read, status_code=201)

@router.put("/{user_id:uuid}", response_model=UserRead)
async def update_user(user_id: uuid.UUID, payload: UserUpdate):
    obj = await User.get_or_none(id=user_id)
    if not obj:
        raise HTTPException(404, "User not found")
    obj.username = payload.username
    obj.email = str(payload.email)
    if payload.password:
        obj.hashed_password = bcrypt.hash(payload.password)
    await obj.save()
    return await respond_item(obj, to_user_read)
