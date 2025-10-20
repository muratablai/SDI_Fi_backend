import uuid
from datetime import datetime, date
from typing import Optional, Literal, Dict, List, Any
from pydantic import BaseModel, EmailStr, ConfigDict, Field
from uuid import UUID


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
# Historical Tracking data
# =========================
class MeterConstantHistoryCreate(BaseModel):
    meter_id: int
    constant: float
    valid_from: datetime
    valid_to: Optional[datetime] = None


class MeterConstantHistoryRead(MeterConstantHistoryCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class MeterOdPodAssignmentCreate(BaseModel):
    od_pod_id: int
    meter_id: int
    valid_from: datetime
    valid_to: Optional[datetime] = None


class MeterOdPodAssignmentRead(MeterOdPodAssignmentCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class MeterSiteAssignmentCreate(BaseModel):
    site_id: int
    meter_id: int
    valid_from: datetime
    valid_to: Optional[datetime] = None


class MeterSiteAssignmentRead(MeterSiteAssignmentCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class MeterReplacementCreate(BaseModel):
    old_meter_id: int
    new_meter_id: int
    replacement_ts: datetime
    handover_read_active_import: Optional[float] = None
    note: Optional[str] = None


class MeterReplacementRead(MeterReplacementCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

# =========================
# Provenance DTOs (NEW)
# =========================
class DataSourceCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    priority: int = 100
    active: bool = True


class DataSourceUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    active: Optional[bool] = None


class DataSourceRead(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    priority: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


class IngestBatchCreate(BaseModel):
    source_id: int
    file_name: Optional[str] = None
    file_hash: Optional[str] = None
    note: Optional[str] = None


class IngestBatchRead(IngestBatchCreate):
    id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class MeterDataRawCreate(BaseModel):
    meter_no: str
    timestamp: datetime
    source_id: int
    batch_id: Optional[int] = None

    bucket_ts: Optional[datetime] = None

    active_import: Optional[float] = Field(default=None, alias="fa")
    active_import_t1: Optional[float] = Field(default=None, alias="fa_t1")
    active_import_t2: Optional[float] = Field(default=None, alias="fa_t2")
    active_import_t3: Optional[float] = Field(default=None, alias="fa_t3")
    active_import_t4: Optional[float] = Field(default=None, alias="fa_t4")

    active_export: Optional[float] = Field(default=None, alias="fr")
    active_export_t1: Optional[float] = None
    active_export_t2: Optional[float] = None
    active_export_t3: Optional[float] = None
    active_export_t4: Optional[float] = None

    reactive_import: Optional[float] = Field(default=None, alias="ra")
    reactive_export: Optional[float] = Field(default=None, alias="rr")

    reactive_q1: Optional[float] = Field(default=None, alias="r_q1")
    reactive_q2: Optional[float] = Field(default=None, alias="r_q2")
    reactive_q3: Optional[float] = Field(default=None, alias="r_q3")
    reactive_q4: Optional[float] = Field(default=None, alias="r_q4")

    power_import: Optional[float] = Field(default=None, alias="p_fa")
    power_export: Optional[float] = Field(default=None, alias="p_fr")

    # per-reading constant (NEW)
    constant: Optional[float] = None

    quality: Optional[str] = None
    quality_code: Optional[int] = None
    estimated: Optional[bool] = False
    interpolated: Optional[bool] = False
    reset_detected: Optional[bool] = False
    duplicate: Optional[bool] = False

    class Config:
        populate_by_name = True


class MeterDataRawRead(MeterDataRawCreate):
    id: int
    received_at: datetime
    model_config = ConfigDict(from_attributes=True)


# =========================
# Canonical series DTOs (EXTENDED)
# =========================
class MeterDataCreate(BaseModel):
    meter_no: str
    timestamp: datetime

    active_import: float = Field(alias="fa")
    active_import_t1: float = Field(alias="fa_t1")
    active_import_t2: float = Field(alias="fa_t2")
    active_import_t3: float = Field(alias="fa_t3")
    active_import_t4: float = Field(alias="fa_t4")

    active_export: float = Field(alias="fr")
    active_export_t1: float = 0.0
    active_export_t2: float = 0.0
    active_export_t3: float = 0.0
    active_export_t4: float = 0.0

    reactive_import: float = Field(alias="ra")
    reactive_export: float = Field(alias="rr")

    reactive_q1: float = Field(default=0.0, alias="r_q1")
    reactive_q2: float = Field(default=0.0, alias="r_q2")
    reactive_q3: float = Field(default=0.0, alias="r_q3")
    reactive_q4: float = Field(default=0.0, alias="r_q4")

    power_import: float = Field(default=0.0, alias="p_fa")
    power_export: float = Field(default=0.0, alias="p_fr")

    # per-reading constant (NEW)
    constant: Optional[float] = None

    class Config:
        populate_by_name = True


class MeterDataRead(MeterDataCreate):
    id: int
    chosen_raw_id: Optional[int] = None
    chosen_source_code: Optional[str] = None
    quality: Optional[str] = None
    estimated: bool = False
    interpolated: bool = False
    reset_detected: bool = False
    model_config = ConfigDict(from_attributes=True)

# =========================
# Tariffs
# =========================

ScopeType = Literal["site", "od_pod", "pod"]

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


class TariffAssignmentBase(BaseModel):
    scope_type: ScopeType
    scope_id: int
    tariff_id: int
    operator: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    is_primary: bool = True
    # Optional overrides
    price_override_cents: Optional[int] = None
    discount_percent: Optional[float] = None


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
    price_override_cents: Optional[int] = None
    discount_percent: Optional[float] = None


class TariffAssignmentRead(TariffAssignmentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OfferCreate(BaseModel):
    code: str
    name: str
    tariff_id: int
    operator: Optional[str] = None
    unit_price_cents: Optional[int] = None
    discount_percent: Optional[float] = None
    valid_from: datetime
    valid_to: Optional[datetime] = None
    active: bool = True


class OfferRead(OfferCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class OfferScopeCreate(BaseModel):
    offer_id: int
    scope_type: Literal["pod", "od_pod", "site"]
    scope_id: int


class OfferScopeRead(OfferScopeCreate):
    id: int
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


# =========================
# Billing Documents DTOs
# =========================

class BillingLineRead(BaseModel):
    currency: str = "RON"
    status: Literal["DRAFT", "ISSUED", "VOID"] = "DRAFT"
    subtotal_cents: int
    vat_cents: int
    total_cents: int
    contains_estimated: bool = False
    ref_invoice_id: Optional[uuid.UUID] = None

class BillingLineCreate(BaseModel):
    document_id: uuid.UUID
    meter_no: str
    tariff_code: str
    unit: str = "kWh"
    quantity: float
    unit_price_cents: int
    amount_cents: int
    contains_estimated: bool = False
    period_start: datetime
    period_end: datetime

class BillingDocumentCreate(BaseModel):
    document_id: uuid.UUID
    meter_no: str
    tariff_code: str
    unit: str = "kWh"
    quantity: float
    unit_price_cents: int
    amount_cents: int
    contains_estimated: bool = False
    period_start: datetime
    period_end: datetime

class BillingDocumentRead(BillingDocumentCreate):
    id: uuid.UUID
    generated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# -------- Period locks DTOs (NEW) --------
class BillingPeriodLockCreate(BaseModel):
    customer_id: str
    period_start: datetime
    period_end: datetime


class BillingPeriodLockRead(BillingPeriodLockCreate):
    id: uuid.UUID
    locked_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------- Reconciliation DTOs (NEW) --------
class ReconciliationRunCreate(BaseModel):
    od_pod_id: int
    period_start: datetime
    period_end: datetime
    dso_energy_kwh: float
    sdi_energy_kwh: float
    delta_kwh: float
    method: Literal["PRO_RATA", "SINK", "MANUAL"] = "PRO_RATA"
    status: Literal["DRAFT", "CONFIRMED"] = "DRAFT"
    note: Optional[str] = None


class ReconciliationRunRead(ReconciliationRunCreate):
    id: uuid.UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReconciliationAllocationCreate(BaseModel):
    run_id: uuid.UUID
    pod_id: int
    allocated_kwh: float
    basis: Literal["PRO_RATA_ENERGY", "FIXED", "LOSS_SINK"] = "PRO_RATA_ENERGY"
    share_ratio: Optional[float] = None


class ReconciliationAllocationRead(ReconciliationAllocationCreate):
    id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)


# -------- (Deprecated) Simple Billing DTOs kept for compatibility --------
class BillingCreate(BaseModel):
    period_start: date
    period_end: date
    amount: float
    allowed_user_ids: Optional[List[uuid.UUID]] = None


class BillingUpdate(BaseModel):
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    amount: Optional[float] = None
    allowed_user_ids: Optional[List[uuid.UUID]] = None


class BillingRead(BillingCreate):
    id: uuid.UUID
    owner_id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)

class SupplierBillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    supplier_code: str | None = None
    supplier_name: str | None = None
    invoice_series: str | None = None
    invoice_number: str
    issue_date: datetime | None = None
    pod_od: str | None = None
    pdf_url: str | None = None
    created_at: datetime | None = None

class SupplierBillLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    bill_id: UUID
    name: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    qty: float | None = None
    unit: str | None = None
    price: float | None = None
    value: float | None = None
    extra: Any | None = None

class SupplierBillMeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    bill_id: UUID
    meter_no: str | None = None
    channel: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    index_old: float | None = None
    method_old: str | None = None
    index_new: float | None = None
    method_new: str | None = None
    energy_value: float | None = None
    unit: str | None = None
    extra: Any | None = None