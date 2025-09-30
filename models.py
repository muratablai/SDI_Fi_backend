from tortoise import fields, models
import uuid

class User(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    username = fields.CharField(max_length=50, unique=True, index=True)
    email = fields.CharField(max_length=100, unique=True, index=True)
    hashed_password = fields.CharField(max_length=128)
    disabled = fields.BooleanField(default=False)
    is_admin = fields.BooleanField(default=False)

class Area(models.Model):
    """Top-level site (from Project ID)"""
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=64, unique=True, index=True)  # e.g. '2206013-001'
    name = fields.CharField(max_length=255)
    address = fields.CharField(max_length=255, null=True)
    city = fields.CharField(max_length=120, null=True)
    county = fields.CharField(max_length=120, null=True)
    latitude = fields.FloatField(null=True)
    longitude = fields.FloatField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "areas"


class Location(models.Model):
    """Actual metering location (POD SDI)"""
    id = fields.IntField(pk=True)
    pod_sdi = fields.CharField(max_length=80, unique=True, index=True)
    name = fields.CharField(max_length=255, null=True)      # consumer/producer label
    role = fields.CharField(max_length=32, null=True)       # 'consumer' | 'producer' | None
    area = fields.ForeignKeyField("models.Area", related_name="locations", index=True)
    trafo_no = fields.CharField(max_length=50, null=True)
    bmc_nr = fields.CharField(max_length=50, null=True)
    pvv_nr = fields.CharField(max_length=50, null=True)
    pvc_nr = fields.CharField(max_length=50, null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "locations"


class Meter(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=200, null=True)
    meter_no = fields.CharField(max_length=80, unique=True, index=True)
    # Every meter belongs to an Area (site)
    area = fields.ForeignKeyField("models.Area", related_name="meters", index=True)
    # Optional direct link to the specific Location (POD SDI)
    location = fields.ForeignKeyField("models.Location", related_name="meters", index=True, null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

    class Meta:
        table = "meters"

class MeterData(models.Model):
    id = fields.IntField(pk=True)
    meter_no = fields.CharField(max_length=50, index=True)
    timestamp = fields.DatetimeField(index=True)
    fa = fields.FloatField(); fa_t1 = fields.FloatField()
    fa_t2 = fields.FloatField(); fa_t3 = fields.FloatField(); fa_t4 = fields.FloatField()
    fr = fields.FloatField(); ra = fields.FloatField(); rr = fields.FloatField()
    r_q1 = fields.FloatField(); r_q2 = fields.FloatField()
    r_q3 = fields.FloatField(); r_q4 = fields.FloatField()
    p_fa = fields.FloatField(); p_fr = fields.FloatField()

class Billing(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    owner_id = fields.ForeignKeyField('models.User', related_name='bills', index=True)
    allowed_user_ids = fields.JSONField(default=list)
    period_start = fields.DateField(index=True)
    period_end = fields.DateField(index=True)
    amount = fields.FloatField()
