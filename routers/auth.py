from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import uuid

from models import User
from schemas import Token
from deps import SECRET_KEY, REFRESH_SECRET, ALGORITHM

router = APIRouter()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
ACCESS_EXPIRE = 15 * 60
REFRESH_EXPIRE = 7 * 24 * 3600

def create_token(data: dict, secret: str, expires: int) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(seconds=expires)
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)

@router.post("/login/access-token", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = await User.get_or_none(username=form.username)
    if not user or not pwd_ctx.verify(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    data = {"sub": str(user.id), "is_admin": user.is_admin}
    return {
        "access_token": create_token(data, SECRET_KEY, ACCESS_EXPIRE),
        "refresh_token": create_token(data, REFRESH_SECRET, REFRESH_EXPIRE),
        "token_type": "bearer",
    }

@router.post("/login/refresh-token", response_model=Token)
async def refresh_token(payload: Token):
    try:
        decoded = jwt.decode(payload.refresh_token, REFRESH_SECRET, algorithms=[ALGORITHM])
        sub = decoded.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        user_id = uuid.UUID(sub)
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    data = {"sub": str(user.id), "is_admin": user.is_admin}
    return {
        "access_token": create_token(data, SECRET_KEY, ACCESS_EXPIRE),
        "refresh_token": create_token(data, REFRESH_SECRET, REFRESH_EXPIRE),
        "token_type": "bearer",
    }
