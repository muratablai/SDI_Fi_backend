from tortoise import fields, models
import uuid


# -------- Users --------
class User(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    username = fields.CharField(max_length=50, unique=True, index=True)
    email = fields.CharField(max_length=100, unique=True, index=True)
    hashed_password = fields.CharField(max_length=128)
    disabled = fields.BooleanField(default=False)
    is_admin = fields.BooleanField(default=False)

    class Meta:
        table = "users"

    def __str__(self) -> str:
        return f"{self.username} ({self.email})"


# -------- Core hierarchy --------
class Site(models.Model):
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=64, unique=True, null=True, index=True)  # e.g. Project ID
    name = fields.CharField(max_length=200, index=True)
    address = fields.CharField(max_length=255, null=True)
    city = fields.CharField(max_length=100, null=True)
    county = fields.CharField(max_length=100, null=True)
    latitude = fields.FloatField(null=True)
    longitude = fields.FloatField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "sites"

    def __str__(self) -> str:
        return self.name or (self.code or f"Site#{self.id}")


class Operator(models.Model):
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=64, unique=True, index=True)
    name = fields.CharField(max_length=200)

    class Meta:
        table = "operators"

    def __str__(self) -> str:
        return self.name


class OdPod(models.Model):
    """Distribution Operator POD (parent of SDI PODs)"""
    id = fields.IntField(pk=True)
    pod_od = fields.CharField(max_length=64, unique=True, index=True)  # DSO POD code
    name = fields.CharField(max_length=200, null=True)
    site = fields.ForeignKeyField("models.Site", related_name="od_pods", on_delete=fields.CASCADE, index=True)
    operator = fields.ForeignKeyField("models.Operator", null=True, related_name="od_pods", on_delete=fields.SET_NULL)
    valid_from = fields.DatetimeField(null=True, index=True)
    valid_to = fields.DatetimeField(null=True, index=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "od_pods"

    def __str__(self) -> str:
        return self.pod_od


class Pod(models.Model):
    """SDI POD"""
    id = fields.IntField(pk=True)
    pod_sdi = fields.CharField(max_length=64, unique=True, index=True)
    name = fields.CharField(max_length=200, null=True)
    role = fields.CharField(max_length=40, null=True)  # consumer / prosumer / etc.
    site = fields.ForeignKeyField("models.Site", related_name="pods", on_delete=fields.CASCADE, index=True)
    od_pod = fields.ForeignKeyField("models.OdPod", null=True, related_name="sdi_pods", on_delete=fields.SET_NULL, index=True)
    trafo_no = fields.CharField(max_length=64, null=True)
    bmc_nr = fields.CharField(max_length=64, null=True)
    pvv_nr = fields.CharField(max_length=64, null=True)
    pvc_nr = fields.CharField(max_length=64, null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "pods"

    def __str__(self) -> str:
        return self.pod_sdi


# -------- Metering --------
class Meter(models.Model):
    id = fields.IntField(pk=True)
    meter_no = fields.CharField(max_length=64, unique=True, index=True)
    name = fields.CharField(max_length=200, null=True)

    # link to one (or none) of the scopes, so you can park meters at site/od_pod/pod level
    pod = fields.ForeignKeyField("models.Pod", null=True, related_name="meters", on_delete=fields.SET_NULL, index=True)
    od_pod = fields.ForeignKeyField("models.OdPod", null=True, related_name="meters", on_delete=fields.SET_NULL, index=True)
    site = fields.ForeignKeyField("models.Site", null=True, related_name="meters", on_delete=fields.SET_NULL, index=True)

    constant = fields.FloatField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "meters"

    def __str__(self) -> str:
        return self.meter_no


class MeterAssignment(models.Model):
    """
    Assignment of a meter to an SDI POD over a validity window.
    """
    id = fields.IntField(pk=True)
    pod = fields.ForeignKeyField("models.Pod", related_name="assignments", on_delete=fields.CASCADE, index=True)
    meter = fields.ForeignKeyField("models.Meter", related_name="assignments", on_delete=fields.CASCADE, index=True)
    valid_from = fields.DatetimeField(index=True)
    valid_to = fields.DatetimeField(null=True, index=True)  # null = still active

    class Meta:
        table = "meter_assignments"
        unique_together = ("pod", "meter", "valid_from")

    def __str__(self) -> str:
        return f"{self.meter}@{self.pod} ({self.valid_from}..{self.valid_to or '∞'})"

# ========================
# Historical tracking (ADDED — no removals)
# ========================
class MeterConstantHistory(models.Model):
    id = fields.IntField(pk=True)
    meter = fields.ForeignKeyField("models.Meter", related_name="constant_history", on_delete=fields.CASCADE, index=True)
    constant = fields.FloatField()
    valid_from = fields.DatetimeField(index=True)
    valid_to = fields.DatetimeField(null=True, index=True)


    class Meta:
        table = "meter_constant_history"
        unique_together = ("meter", "valid_from")


class MeterOdPodAssignment(models.Model):
    id = fields.IntField(pk=True)
    od_pod = fields.ForeignKeyField("models.OdPod", related_name="meter_assignments", on_delete=fields.CASCADE, index=True)
    meter = fields.ForeignKeyField("models.Meter", related_name="odpod_assignments", on_delete=fields.CASCADE, index=True)
    valid_from = fields.DatetimeField(index=True)
    valid_to = fields.DatetimeField(null=True, index=True)


    class Meta:
        table = "meter_odpod_assignments"
        unique_together = ("od_pod", "meter", "valid_from")


class MeterSiteAssignment(models.Model):
    id = fields.IntField(pk=True)
    site = fields.ForeignKeyField("models.Site", related_name="meter_assignments", on_delete=fields.CASCADE, index=True)
    meter = fields.ForeignKeyField("models.Meter", related_name="site_assignments", on_delete=fields.CASCADE, index=True)
    valid_from = fields.DatetimeField(index=True)
    valid_to = fields.DatetimeField(null=True, index=True)


    class Meta:
        table = "meter_site_assignments"
        unique_together = ("site", "meter", "valid_from")


class MeterReplacement(models.Model):
    id = fields.IntField(pk=True)
    old_meter = fields.ForeignKeyField("models.Meter", related_name="replaced_by", on_delete=fields.RESTRICT, index=True)
    new_meter = fields.ForeignKeyField("models.Meter", related_name="replaces", on_delete=fields.RESTRICT, index=True)
    replacement_ts = fields.DatetimeField(index=True)
    handover_read_active_import = fields.FloatField(null=True)
    note = fields.TextField(null=True)


    class Meta:
        table = "meter_replacements"
        unique_together = ("old_meter", "new_meter", "replacement_ts")

# ========================
# Provenance (NEW)
# ========================
class DataSource(models.Model):
    """Where a reading came from (DSO CSV, OPC UA, API, manual, etc.)"""
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=64, unique=True, index=True)
    name = fields.CharField(max_length=128)
    description = fields.TextField(null=True)
    priority = fields.IntField(default=100, index=True) # lower = preferred
    active = fields.BooleanField(default=True, index=True)


    class Meta:
        table = "data_sources"


class IngestBatch(models.Model):
    id = fields.IntField(pk=True)
    source = fields.ForeignKeyField("models.DataSource", related_name="batches", on_delete=fields.RESTRICT, index=True)
    started_at = fields.DatetimeField(auto_now_add=True, index=True)
    finished_at = fields.DatetimeField(null=True, index=True)
    file_name = fields.CharField(max_length=255, null=True)
    file_hash = fields.CharField(max_length=128, null=True)
    note = fields.TextField(null=True)


    class Meta:
        table = "ingest_batches"


class MeterDataRaw(models.Model):
    """Raw readings as received, with provenance and quality."""
    id = fields.IntField(pk=True)
    meter_no = fields.CharField(max_length=64, index=True)
    timestamp = fields.DatetimeField(index=True)  # original ts
    bucket_ts = fields.DatetimeField(null=True, index=True)  # snapped bucket ts (e.g., 15-min start)

    # channels (mirrors canonical) — RENAMED to descriptive names
    active_import = fields.FloatField(null=True)  # was: fa
    active_import_t1 = fields.FloatField(null=True)  # was: fa_t1
    active_import_t2 = fields.FloatField(null=True)  # was: fa_t2
    active_import_t3 = fields.FloatField(null=True)  # was: fa_t3
    active_import_t4 = fields.FloatField(null=True)  # was: fa_t4

    active_export = fields.FloatField(null=True)  # was: fr
    # OPTIONAL: export by TOU (PV) — ADDITIVE, safe to ignore if unused
    active_export_t1 = fields.FloatField(null=True)
    active_export_t2 = fields.FloatField(null=True)
    active_export_t3 = fields.FloatField(null=True)
    active_export_t4 = fields.FloatField(null=True)

    reactive_import = fields.FloatField(null=True)  # was: ra
    reactive_export = fields.FloatField(null=True)  # was: rr

    reactive_q1 = fields.FloatField(null=True)  # was: r_q1
    reactive_q2 = fields.FloatField(null=True)  # was: r_q2
    reactive_q3 = fields.FloatField(null=True)  # was: r_q3
    reactive_q4 = fields.FloatField(null=True)  # was: r_q4

    power_import = fields.FloatField(null=True)  # was: p_fa
    power_export = fields.FloatField(null=True)  # was: p_fr

    # per-reading constant (NEW) — snapshot of Meter.constant at ingest time
    constant = fields.FloatField(null=True)
    # provenance & quality (unchanged)
    source = fields.ForeignKeyField("models.DataSource", related_name="raw_rows", on_delete=fields.RESTRICT, index=True)
    batch = fields.ForeignKeyField("models.IngestBatch", null=True, related_name="raw_rows", on_delete=fields.SET_NULL, index=True)
    quality = fields.CharField(max_length=32, null=True, index=True) # 'GOOD','ESTIMATED','INTERPOLATED','REPLACED'
    quality_code = fields.IntField(null=True)
    estimated = fields.BooleanField(default=False, index=True)
    interpolated = fields.BooleanField(default=False, index=True)
    reset_detected = fields.BooleanField(default=False, index=True)
    duplicate = fields.BooleanField(default=False, index=True)

    received_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "meter_data_raw"
        indexes = (
        ("meter_no", "timestamp", "source_id"),
        ("meter_no", "bucket_ts"),
        )

class MeterData(models.Model):
    id = fields.IntField(pk=True)
    meter_no = fields.CharField(max_length=64, index=True)
    timestamp = fields.DatetimeField(index=True)

    # energy & power channels — RENAMED to descriptive names
    active_import = fields.FloatField()  # was: fa
    active_import_t1 = fields.FloatField()  # was: fa_t1
    active_import_t2 = fields.FloatField()  # was: fa_t2
    active_import_t3 = fields.FloatField()  # was: fa_t3
    active_import_t4 = fields.FloatField()  # was: fa_t4

    active_export = fields.FloatField()  # was: fr
    # OPTIONAL: export by TOU (PV) — ADDITIVE
    active_export_t1 = fields.FloatField(default=0.0)
    active_export_t2 = fields.FloatField(default=0.0)
    active_export_t3 = fields.FloatField(default=0.0)
    active_export_t4 = fields.FloatField(default=0.0)

    reactive_import = fields.FloatField()  # was: ra
    reactive_export = fields.FloatField()  # was: rr

    reactive_q1 = fields.FloatField()  # was: r_q1
    reactive_q2 = fields.FloatField()  # was: r_q2
    reactive_q3 = fields.FloatField()  # was: r_q3
    reactive_q4 = fields.FloatField()  # was: r_q4

    power_import = fields.FloatField()  # was: p_fa
    power_export = fields.FloatField()  # was: p_fr

    # per-reading constant (NEW) — snapshot of Meter.constant at consolidation time
    constant = fields.FloatField(null=True)

    # denormalized provenance (unchanged)
    chosen_raw = fields.ForeignKeyField("models.MeterDataRaw", null=True, related_name="chosen_for",
                                        on_delete=fields.SET_NULL, index=True)
    chosen_source_code = fields.CharField(max_length=64, null=True, index=True)
    quality = fields.CharField(max_length=32, null=True, index=True)
    estimated = fields.BooleanField(default=False, index=True)
    interpolated = fields.BooleanField(default=False, index=True)
    reset_detected = fields.BooleanField(default=False, index=True)

    class Meta:
        table = "meter_data"

    indexes = (("meter_no", "timestamp"),)


# ========================
# Tariffs
# ========================

class Tariff(models.Model):
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=64, unique=True, index=True)
    description = fields.TextField(null=True)
    unit = fields.CharField(max_length=32, null=True)
    billing_type = fields.CharField(max_length=64, null=True)
    active = fields.BooleanField(default=True, index=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    prices: fields.ReverseRelation["TariffOperatorPrice"]

    class Meta:
        table = "tariffs"

    def __str__(self) -> str:
        return self.code


class TariffOperatorPrice(models.Model):
    id = fields.IntField(pk=True)
    tariff = fields.ForeignKeyField("models.Tariff", related_name="prices", on_delete=fields.CASCADE)
    operator = fields.CharField(max_length=128)   # e.g. “Distribuitor X”
    price = fields.FloatField()

    class Meta:
        table = "tariff_operator_prices"
        unique_together = ("tariff", "operator")


class TariffAssignment(models.Model):
    """
    Attach a tariff to EXACTLY ONE scope (site | od_pod | pod).
    Validity window + operator + is_primary included.
    """
    id = fields.IntField(pk=True)

    # scopes (pick exactly one)
    site = fields.ForeignKeyField("models.Site", related_name="tariff_assignments", null=True, on_delete=fields.CASCADE, index=True)
    od_pod = fields.ForeignKeyField("models.OdPod", related_name="tariff_assignments", null=True, on_delete=fields.CASCADE, index=True)
    pod = fields.ForeignKeyField("models.Pod", related_name="tariff_assignments", null=True, on_delete=fields.CASCADE, index=True)

    tariff = fields.ForeignKeyField("models.Tariff", related_name="tariff_assignments", on_delete=fields.CASCADE, index=True)

    operator = fields.CharField(max_length=128, null=True, index=True)
    valid_from = fields.DatetimeField(null=True, index=True)
    valid_to = fields.DatetimeField(null=True, index=True)
    is_primary = fields.BooleanField(default=True, index=True)

    # Optional per-assignment overrides (apply if set)
    price_override_cents = fields.IntField(null=True)
    discount_percent = fields.FloatField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "tariff_assignments"
        unique_together = ("tariff", "operator", "site", "od_pod", "pod", "valid_from")

    def __str__(self):
        scope = "site" if self.site else "od_pod" if self.od_pod else "pod"
        scope_val = self.site or self.od_pod or self.pod
        return f"TariffAssignment({scope}={scope_val}, tariff={self.tariff}, op={self.operator})"

# -------- Offers (ADDED) --------
class Offer(models.Model):
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=64, unique=True, index=True)
    name = fields.CharField(max_length=128)
    tariff = fields.ForeignKeyField("models.Tariff", related_name="offers", on_delete=fields.RESTRICT)
    operator = fields.CharField(max_length=128, null=True, index=True)
    unit_price_cents = fields.IntField(null=True)
    discount_percent = fields.FloatField(null=True)
    valid_from = fields.DatetimeField(index=True)
    valid_to = fields.DatetimeField(null=True, index=True)
    active = fields.BooleanField(default=True, index=True)

    class Meta:
        table = "offers"


class OfferScope(models.Model):
    id = fields.IntField(pk=True)
    offer = fields.ForeignKeyField("models.Offer", related_name="scopes", on_delete=fields.CASCADE)
    scope_type = fields.CharField(max_length=8, index=True) # "pod" | "od_pod" | "site"
    scope_id = fields.IntField(index=True)

    class Meta:
        table = "offer_scopes"
        unique_together = ("offer", "scope_type", "scope_id")


# -------- VAT history (ADDED) --------
class VatRateHistory(models.Model):
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=32, index=True, default="STANDARD") # e.g. STANDARD/REDUCED
    rate_percent = fields.DecimalField(max_digits=5, decimal_places=2)
    valid_from = fields.DatetimeField(index=True)
    valid_to = fields.DatetimeField(null=True, index=True)


    class Meta:
        table = "vat_rate_history"
        unique_together = ("code", "valid_from")

# ========================
# Billing documents (NEW)
# ========================
class BillingDocument(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    doc_type = fields.CharField(max_length=8)  # 'INVOICE' | 'CREDIT' | 'DEBIT'
    customer_id = fields.CharField(max_length=128, index=True)
    period_start = fields.DatetimeField(index=True)
    period_end = fields.DatetimeField(index=True)
    currency = fields.CharField(max_length=3, default="RON")
    status = fields.CharField(max_length=8, default="DRAFT")
    subtotal_cents = fields.IntField(default=0)
    vat_cents = fields.IntField(default=0)
    total_cents = fields.IntField(default=0)
    contains_estimated = fields.BooleanField(default=False)
    generated_at = fields.DatetimeField(auto_now_add=True)
    ref_invoice = fields.ForeignKeyField("models.BillingDocument", null=True, related_name="adjustments",
                                         on_delete=fields.RESTRICT)

    # aggregated true-up totals included in this document (ADDED)
    true_up_subtotal_cents = fields.IntField(default=0)
    true_up_vat_cents = fields.IntField(default=0)

    class Meta:
        table = "billing_documents"


class BillingLine(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    document = fields.ForeignKeyField("models.BillingDocument", related_name="lines", on_delete=fields.CASCADE)
    meter_no = fields.CharField(max_length=64, index=True)
    tariff_code = fields.CharField(max_length=64, index=True)
    unit = fields.CharField(max_length=16, default="kWh")
    quantity = fields.DecimalField(max_digits=18, decimal_places=6)
    unit_price_cents = fields.IntField()
    amount_cents = fields.IntField()

    # per-line VAT lock (ADDED)
    vat_rate_percent = fields.DecimalField(max_digits=5, decimal_places=2, default=0)
    vat_amount_cents = fields.IntField(default=0)

    contains_estimated = fields.BooleanField(default=False)
    period_start = fields.DatetimeField()
    period_end = fields.DatetimeField()

    # regularizare context (ADDED)
    channel = fields.CharField(max_length=32, null=True, index=True)  # 'active_import' | 'active_export' | etc.
    tou_band = fields.CharField(max_length=8, null=True, index=True)  # 'T1'..'T4' or None
    is_true_up = fields.BooleanField(default=False, index=True)
    true_up_of_line = fields.ForeignKeyField("models.BillingLine", null=True, related_name="true_up_children",
                                             on_delete=fields.RESTRICT)
    true_up_reason = fields.TextField(null=True)

    class Meta:
        table = "billing_lines"


class BillingPeriodLock(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    customer_id = fields.CharField(max_length=128, index=True)
    period_start = fields.DatetimeField(index=True)
    period_end = fields.DatetimeField(index=True)
    locked_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "billing_period_locks"

# ========================
# Reconciliation (DSO vs SDI) (NEW)
# ========================
class ReconciliationRun(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    od_pod = fields.ForeignKeyField("models.OdPod", related_name="reconciliations", on_delete=fields.CASCADE, index=True)
    period_start = fields.DatetimeField(index=True)
    period_end = fields.DatetimeField(index=True)
    dso_energy_kwh = fields.DecimalField(max_digits=18, decimal_places=6)
    sdi_energy_kwh = fields.DecimalField(max_digits=18, decimal_places=6)
    delta_kwh = fields.DecimalField(max_digits=18, decimal_places=6)
    method = fields.CharField(max_length=16, default="PRO_RATA")
    status = fields.CharField(max_length=12, default="DRAFT") # DRAFT/CONFIRMED
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)


    class Meta:
        table = "reconciliation_runs"


class ReconciliationAllocation(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    run = fields.ForeignKeyField("models.ReconciliationRun", related_name="allocations", on_delete=fields.CASCADE)
    pod = fields.ForeignKeyField("models.Pod", related_name="recon_allocations", on_delete=fields.CASCADE)
    allocated_kwh = fields.DecimalField(max_digits=18, decimal_places=6)
    basis = fields.CharField(max_length=24, default="PRO_RATA_ENERGY")
    share_ratio = fields.DecimalField(max_digits=12, decimal_places=9, null=True)

    class Meta:
        table = "reconciliation_allocations"


# ========================
# (Deprecated) Simple Billing table — kept for backward compatibility
# ========================
class Billing(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    owner_id = fields.ForeignKeyField('models.User', related_name='bills', index=True, on_delete=fields.CASCADE)
    allowed_user_ids = fields.JSONField(default=list)
    period_start = fields.DateField(index=True)
    period_end = fields.DateField(index=True)
    amount = fields.FloatField()

    class Meta:
        table = "billing"

# ========================
# Supplier bill data
# ========================
class Supplier(models.Model):
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=64, unique=True, index=True)
    name = fields.CharField(max_length=200, index=True)
    cif  = fields.CharField(max_length=64, null=True, index=True)
    class Meta: table = "suppliers"

class SupplierBill(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    supplier = fields.ForeignKeyField("models.Supplier", related_name="bills", on_delete=fields.RESTRICT, index=True)

    # header
    invoice_series = fields.CharField(max_length=64, null=True, index=True)
    invoice_number = fields.CharField(max_length=64, index=True)
    issue_date     = fields.DateField(null=True, index=True)
    due_date       = fields.DateField(null=True, index=True)

    # POD-OD context (the supplier bill is for an OD POD)
    pod_od         = fields.CharField(max_length=64, null=True, index=True)     #  e.g. 5940... from the bill
    od_pod         = fields.ForeignKeyField("models.OdPod", null=True, related_name="supplier_bills",
                                            on_delete=fields.SET_NULL, index=True)

    # files
    pdf_path       = fields.CharField(max_length=512, null=True)
    pdf_sha256     = fields.CharField(max_length=64,  null=True, index=True)
    pdf_bytes_size = fields.IntField(null=True)

    # money (optional now; can fill later)
    currency   = fields.CharField(max_length=8,  null=True)
    total_amount = fields.FloatField(null=True)
    vat_amount   = fields.FloatField(null=True)

    # provenance
    ingest_batch = fields.ForeignKeyField("models.IngestBatch", null=True, related_name="supplier_bills",
                                          on_delete=fields.SET_NULL, index=True)

    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "supplier_bills"
        unique_together = ("supplier", "invoice_series", "invoice_number")

class SupplierBillLine(models.Model):
    id   = fields.UUIDField(pk=True, default=uuid.uuid4)
    bill = fields.ForeignKeyField("models.SupplierBill", related_name="lines", on_delete=fields.CASCADE, index=True)

    name = fields.CharField(max_length=512)
    period_start = fields.DatetimeField(null=True, index=True)
    period_end   = fields.DatetimeField(null=True, index=True)
    qty  = fields.FloatField(null=True)
    unit = fields.CharField(max_length=32, null=True)
    price = fields.FloatField(null=True)
    value = fields.FloatField(null=True)
    extra = fields.JSONField(null=True)

    class Meta: table = "supplier_bill_lines"

class SupplierBillMeasurement(models.Model):
    id   = fields.UUIDField(pk=True, default=uuid.uuid4)
    bill = fields.ForeignKeyField("models.SupplierBill", related_name="measurements", on_delete=fields.CASCADE, index=True)

    meter_no = fields.CharField(max_length=64, index=True, null=True)
    channel  = fields.CharField(max_length=32, index=True)  # 'active_import'|'active_export'|'reactive_import'|'reactive_export'

    period_start = fields.DatetimeField(null=True, index=True)
    period_end   = fields.DatetimeField(null=True, index=True)

    index_old = fields.FloatField(null=True)
    index_new = fields.FloatField(null=True)
    method_old = fields.CharField(max_length=64, null=True)
    method_new = fields.CharField(max_length=64, null=True)
    energy_value = fields.FloatField(null=True)   # prefer explicit energy if present
    unit = fields.CharField(max_length=16, null=True)  # 'kWh'|'kVArh'
    extra = fields.JSONField(null=True)

    class Meta:
        table = "supplier_bill_measurements"
        indexes = (("meter_no", "channel", "period_start", "period_end"),)