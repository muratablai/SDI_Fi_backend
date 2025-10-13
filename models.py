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


class MeterData(models.Model):
    id = fields.IntField(pk=True)
    meter_no = fields.CharField(max_length=64, index=True)
    timestamp = fields.DatetimeField(index=True)

    # energy & power channels
    fa = fields.FloatField()
    fa_t1 = fields.FloatField()
    fa_t2 = fields.FloatField()
    fa_t3 = fields.FloatField()
    fa_t4 = fields.FloatField()
    fr = fields.FloatField()
    ra = fields.FloatField()
    rr = fields.FloatField()
    r_q1 = fields.FloatField()
    r_q2 = fields.FloatField()
    r_q3 = fields.FloatField()
    r_q4 = fields.FloatField()
    p_fa = fields.FloatField()
    p_fr = fields.FloatField()

    class Meta:
        table = "meter_data"
        indexes = (("meter_no", "timestamp"),)


# -------- Billing & Tariffs --------
class Billing(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    owner_id = fields.ForeignKeyField('models.User', related_name='bills', index=True, on_delete=fields.CASCADE)
    allowed_user_ids = fields.JSONField(default=list)
    period_start = fields.DateField(index=True)
    period_end = fields.DateField(index=True)
    amount = fields.FloatField()

    class Meta:
        table = "billing"


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

    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "tariff_assignments"
        unique_together = ("tariff", "operator", "site", "od_pod", "pod", "valid_from")

    def __str__(self):
        scope = "site" if self.site else "od_pod" if self.od_pod else "pod"
        scope_val = self.site or self.od_pod or self.pod
        return f"TariffAssignment({scope}={scope_val}, tariff={self.tariff}, op={self.operator})"
