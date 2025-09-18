from tortoise import fields, models
import uuid

class User(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    username = fields.CharField(max_length=50, unique=True, index=True)
    email = fields.CharField(max_length=100, unique=True, index=True)
    hashed_password = fields.CharField(max_length=128)
    disabled = fields.BooleanField(default=False)
    is_admin = fields.BooleanField(default=False)

class Location(models.Model):
    id = fields.CharField(pk=True, max_length=120)   # frontend uses string ids
    name = fields.CharField(max_length=200, index=True)

class Meter(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=200, null=True)
    meter_no = fields.CharField(max_length=80, unique=True, index=True)
    # IMPORTANT: keep only the FK. Tortoise auto-creates `location_id` for you.
    location = fields.ForeignKeyField("models.Location", related_name="meters", index=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True, index=True)

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
