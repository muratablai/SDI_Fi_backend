import uuid
from datetime import datetime, date
from typing import Optional, Literal, Dict
from pydantic import BaseModel, EmailStr, ConfigDict, Field


# =========================
# Auth
# =========================
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None


class UserRead(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr
    disabled: bool
    is_admin: bool
    model_config = ConfigDict(from_attributes=True)


# =========================
# Core hierarchy
# =========================
class SiteCreate(BaseModel):
    code: Optional[str] = None
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SiteUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SiteRead(SiteCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OperatorCreate(BaseModel):
    code: str
    name: str


class OperatorUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None


class OperatorRead(OperatorCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class OdPodCreate(BaseModel):
    pod_od: str
    name: Optional[str] = None
    site_id: int
    operator_id: Optional[int] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class OdPodUpdate(BaseModel):
    pod_od: Optional[str] = None
    name: Optional[str] = None
    site_id: Optional[int] = None
    operator_id: Optional[int] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class OdPodRead(OdPodCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PodCreate(BaseModel):
    pod_sdi: str
    name: Optional[str] = None
    role: Optional[str] = None  # "consumer" | "prosumer" | ...
    site_id: int
    od_pod_id: Optional[int] = None
    trafo_no: Optional[str] = None
    bmc_nr: Optional[str] = None
    pvv_nr: Optional[str] = None
    pvc_nr: Optional[str] = None


class PodUpdate(BaseModel):
    pod_sdi: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    site_id: Optional[int] = None
    od_pod_id: Optional[int] = None
    trafo_no: Optional[str] = None
    bmc_nr: Optional[str] = None
    pvv_nr: Optional[str] = None
    pvc_nr: Optional[str] = None


class PodRead(PodCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# =========================
# Metering
# =========================
class MeterCreate(BaseModel):
    meter_no: str
    name: Optional[str] = None
    pod_id: Optional[int] = None
    od_pod_id: Optional[int] = None
    site_id: Optional[int] = None
    constant: Optional[float] = Field(default=1.0)


class MeterUpdate(BaseModel):
    name: Optional[str] = None
    pod_id: Optional[int] = None
    od_pod_id: Optional[int] = None
    site_id: Optional[int] = None
    constant: Optional[float] = None


class MeterRead(MeterCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MeterDataCreate(BaseModel):
    meter_no: str
    timestamp: datetime
    fa: float
    fr: float
    ra: float
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
    constant: Optional[float] = Field(default=1.0)


class MeterDataRead(MeterDataCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class MeterAssignmentCreate(BaseModel):
    pod_id: int
    meter_id: int
    valid_from: datetime
    valid_to: Optional[datetime] = None


class MeterAssignmentUpdate(BaseModel):
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class MeterAssignmentRead(BaseModel):
    id: int
    pod_id: int
    meter_id: int
    valid_from: datetime
    valid_to: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# =========================
# Billing & Tariffs
# =========================
class BillingCreate(BaseModel):
    period_start: date
    period_end: date
    amount: float
    allowed_user_ids: Optional[list[uuid.UUID]] = None


class BillingUpdate(BaseModel):
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    amount: Optional[float] = None
    allowed_user_ids: Optional[list[uuid.UUID]] = None


class BillingRead(BillingCreate):
    id: uuid.UUID
    owner_id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)


# ---- Tariffs (base + operator prices map) ----
class TariffCreate(BaseModel):
    code: str
    description: Optional[str] = None
    unit: Optional[str] = None
    billing_type: Optional[str] = None
    active: bool = True
    # optional: prices keyed by operator name
    operator_prices: Optional[Dict[str, float]] = None


class TariffUpdate(BaseModel):
    code: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    billing_type: Optional[str] = None
    active: Optional[bool] = None
    operator_prices: Optional[Dict[str, float]] = None


class TariffRead(BaseModel):
    id: int
    code: str
    description: Optional[str] = None
    unit: Optional[str] = None
    billing_type: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: datetime
    operator_prices: Optional[Dict[str, float]] = None
    model_config = ConfigDict(from_attributes=True)


ScopeType = Literal["site", "od_pod", "pod"]


class TariffAssignmentBase(BaseModel):
    scope_type: ScopeType
    scope_id: int
    tariff_id: int
    operator: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    is_primary: bool = True


class TariffAssignmentCreate(TariffAssignmentBase):
    pass


class TariffAssignmentUpdate(BaseModel):
    scope_type: Optional[ScopeType] = None
    scope_id: Optional[int] = None
    tariff_id: Optional[int] = None
    operator: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    is_primary: Optional[bool] = None


class TariffAssignmentRead(TariffAssignmentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# =========================
# Timeseries for Pods (formerly LocationData)
# =========================
class PodDataRead(BaseModel):
    """
    Flattened timeseries row joined to the *active* meter for a pod.
    """
    id: int
    timestamp: datetime
    meter_id: int
    fa: float
    fr: float
    ra: float
    fa_t1: float
    fa_t2: float
    fa_t3: float
    fa_t4: float
    rr: float
    r_q1: float
    r_q2: float
    r_q3: float
    r_q4: float
    p_fa: float
    p_fr: float

    model_config = ConfigDict(from_attributes=True)


class PodLatestRead(BaseModel):
    timestamp: datetime
    meter_no: str
    fa: float
    fr: float
    ra: float
    p_fa: float
    p_fr: float
