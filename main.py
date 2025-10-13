from fastapi import FastAPI
from tortoise.contrib.fastapi import register_tortoise
from passlib.context import CryptContext
from fastapi.middleware.cors import CORSMiddleware
from services.seeder import seed_if_empty
import logging
import uuid
from contextlib import asynccontextmanager
from tortoise import Tortoise
import aiomysql

import models
from models import User
from routers import (
    auth, users,
    # core
    sites, od_pods, pods,
    # meters & data
    meters, meter_data, meter_assignments, meter_energy, pod_data, pod_energy,
    # billing
    billing,
    # tariffs
    tariffs, tariff_operator, tariff_records, tariff_assignments,
)

logger = logging.getLogger("uvicorn")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
lifespan_services = {}

async def seed_admin():
    if not await User.exists():
        await User.create(
            id=uuid.uuid4(),
            username="admin",
            email="admin@example.com",
            hashed_password=pwd_ctx.hash("password123"),
            is_admin=True,
        )

async def inspect_models():
    print("Billing attributes:", [attr for attr in dir(models.Billing) if not attr.startswith("_")])

async def debug_billing_fields():
    print("🧐 Billing._meta.fields_map keys:", list(models.Billing._meta.fields_map.keys()))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) Init DB
    await Tortoise.init(
        db_url="sqlite://./db.sqlite3",
        modules={"models": ["models"]},
    )
    # 2) Ensure schemas
    await Tortoise.generate_schemas()

    # 2) Create MySQL pool for metering proc
    app.state.mysql_pool = await aiomysql.create_pool(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="Enevo123$",
        db="mdc",
        autocommit=True,  # important for CALL ... results
        minsize=1,
        maxsize=5,
    )

    # 3) Run seeds / debug AFTER DB is ready
    from services.seeder import seed_if_empty
    await seed_admin()
    await seed_if_empty(logger=logger.info)
    await inspect_models()
    await debug_billing_fields()

    try:
        yield
    finally:
        await Tortoise.close_connections()


app = FastAPI(lifespan=lifespan, title="SDI Admin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "X-Total-Count"],
)

app.include_router(auth.router)
app.include_router(users.router)

# hierarchy
app.include_router(sites.router)
app.include_router(od_pods.router)
app.include_router(pods.router)

# metering
app.include_router(meters.router)
app.include_router(meter_assignments.router)
app.include_router(meter_data.router)
app.include_router(meter_energy.router)
app.include_router(pod_data.router)
app.include_router(pod_energy.router)

# billing & tariffs
app.include_router(billing.router)
app.include_router(tariffs.router)
app.include_router(tariff_operator.router)
app.include_router(tariff_records.router)
app.include_router(tariff_assignments.router)

from fastapi.routing import APIRoute

for route in app.routes:
    if isinstance(route, APIRoute):
        print(f"{list(route.methods)} -> {route.path}")

'''
register_tortoise(
    app,
    db_url="sqlite://./db.sqlite3",
    modules={"models": ["models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)



@app.on_event("startup")
async def _seed_on_startup():
    await seed_if_empty(logger=logger.info)
@app.on_event("startup")
async def seed_admin():
    if not await User.exists():
        await User.create(
            id=uuid.uuid4(),
            username="admin",
            email="admin@example.com",
            hashed_password=pwd_ctx.hash("password123"),
            is_admin=True,
        )

@app.on_event("startup")
async def inspect_models():
    print("Billing attributes:", [attr for attr in dir(models.Billing) if not attr.startswith("_")])

@app.on_event("startup")
async def debug_billing_fields():
    print("🧐 Billing._meta.fields_map keys:", list(models.Billing._meta.fields_map.keys()))

'''
