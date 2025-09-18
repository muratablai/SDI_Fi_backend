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

# ---- NEW ----
class LocationRead(BaseModel):
    id: str
    name: str
    model_config = ConfigDict(from_attributes=True)

class MeterRead(BaseModel):
    id: int
    name: Optional[str] = None
    meter_no: str
    # Tortoise provides `location_id` alongside the FK; we can expose it directly
    location_id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class MeterDataCreate(BaseModel):
    meter_no: str
    timestamp: datetime
    fa: float
    fr: float
    ra: float
    # Make the rest optional with sensible defaults so your form works
    fa_t1: float = 0.0
    fa_t2: float = 0.0
    fa_t3: float = 0.0
    fa_t4: float = 0.0
    rr: float = 0.0
    r_q1: float = 0.0
    r_q2: float = 0.0
    r_q3: float = 0.0
    r_q4: float = 0.0
    p_fa: float = 0.0
    p_fr: float = 0.0

class MeterDataRead(MeterDataCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class BillingCreate(BaseModel):
    period_start: date
    period_end: date
    amount: float
    allowed_user_ids: Optional[List[uuid.UUID]] = None

class BillingRead(BillingCreate):
    id: uuid.UUID
    owner_id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)
