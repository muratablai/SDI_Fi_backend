from tortoise import fields, models
import uuid

class User(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    username = fields.CharField(max_length=50, unique=True)
    email = fields.CharField(max_length=100, unique=True)
    hashed_password = fields.CharField(max_length=128)
    disabled = fields.BooleanField(default=False)
    is_admin = fields.BooleanField(default=False)

class MeterData(models.Model):
    id = fields.IntField(pk=True)
    meter_no = fields.CharField(max_length=50, index=True)
    timestamp = fields.DatetimeField()
    fa = fields.FloatField(); fa_t1 = fields.FloatField(); fa_t2 = fields.FloatField()
    fa_t3 = fields.FloatField(); fa_t4 = fields.FloatField()
    fr = fields.FloatField(); ra = fields.FloatField(); rr = fields.FloatField()
    r_q1 = fields.FloatField(); r_q2 = fields.FloatField()
    r_q3 = fields.FloatField(); r_q4 = fields.FloatField()
    p_fa = fields.FloatField(); p_fr = fields.FloatField()

class Billing(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    owner_id = fields.ForeignKeyField('models.User', related_name='bills')
    allowed_user_ids = fields.JSONField(default=list)  # list of UUID strings
    period_start = fields.DateField()
    period_end = fields.DateField()
    amount = fields.FloatField()


