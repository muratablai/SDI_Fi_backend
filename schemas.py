import uuid
from datetime import datetime, date
from typing import List, Optional

from pydantic import BaseModel, EmailStr, ConfigDict

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    username: str
    email: EmailStr
    password: Optional[str] = None

class UserRead(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr
    disabled: bool
    is_admin: bool

    model_config = ConfigDict(from_attributes=True)

class MeterDataCreate(BaseModel):
    meter_no: str
    timestamp: datetime
    fa: float; fa_t1: float; fa_t2: float; fa_t3: float; fa_t4: float
    fr: float; ra: float; rr: float
    r_q1: float; r_q2: float; r_q3: float; r_q4: float
    p_fa: float; p_fr: float

class MeterDataRead(MeterDataCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)

class BillingCreate(BaseModel):
    period_start: date
    period_end: date
    amount: float
    allowed_user_ids: Optional[List[uuid.UUID]] = []

class BillingRead(BillingCreate):
    id: uuid.UUID
    owner_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)
