# main.py (full, lifespan-based)
from __future__ import annotations

import asyncio, logging, uuid, contextlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import aiomysql
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from tortoise import Tortoise

import models
from models import User

# Your existing routers
from routers import (
    auth, users,
    sites, od_pods, pods,
    meters, meter_data, meter_assignments, meter_energy, pod_data, pod_energy,
    billing,
    tariffs, tariff_operator, tariff_records, tariff_assignments,
    supplier_bills, supplier_bill_lines, supplier_bill_measurement,
)
# Extra routers
from routers import scope_counters, admin_tasks
from routers import integration_errors, integration_admin

# Background pieces
from scheduler import Scheduler
from services import config
from services.seeder import seed_if_empty
from services.background import run_ingest_buckets, run_consolidate

# Azure integration jobs
from integration.azure_file_gateway import AzureFileGateway
from integration.msd_exporter import export_document
from integration.msd_poller import poll_outcomes

# Optional: your bill interpreter
from bill_interpreter.service import run_forever

logger = logging.getLogger("uvicorn")
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
UTC = timezone.utc

# ----- helpers -----
async def _seed_admin():
    if not await User.exists():
        await User.create(
            id=uuid.uuid4(),
            username="admin",
            email="admin@example.com",
            hashed_password=pwd_ctx.hash("password123"),
            is_admin=True,
        )

def _window(hours: int = 1):
    now = datetime.now(tz=UTC)
    start = (now - timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
    end = now.replace(second=0, microsecond=0)
    return start, end

def _gw() -> AzureFileGateway:
    return AzureFileGateway(
        account_name=config.AZURE_FILES_ACCOUNT_NAME,
        account_key=config.AZURE_FILES_ACCOUNT_KEY,
        sas_url=config.AZURE_FILES_SAS_URL,
        share_name=config.AZURE_FILES_SHARE,
        base_dir=config.AZURE_FILES_BASE_DIR,
    )

# ----- scheduled jobs -----
async def _job_ingest_and_consolidate():
    if not config.METER_NOS:
        return
    start, end = _window(1)
    for mn in config.METER_NOS:
        try:
            await run_ingest_buckets(mn, start, end)
        except Exception as e:
            logger.warning(f"[scheduler] ingest failed for {mn}: {e}")
    try:
        await run_consolidate(start, end, meter_nos=config.METER_NOS)
    except Exception as e:
        logger.warning(f"[scheduler] consolidate failed: {e}")

async def _job_export_ready():
    from models import BillingDocument
    docs = await BillingDocument.filter(status="READY").limit(20)
    if not docs:
        return
    gw = _gw()
    for d in docs:
        try:
            await export_document(str(d.id), gw, lines_dir=config.MSD_DIR_LINES, pdfs_dir=config.MSD_DIR_PDFS)
            d.status = "EXPORTED"
            await d.save()
        except Exception as e:
            d.csv_last_error = str(e)[:1024]
            d.csv_attempts = (d.csv_attempts or 0) + 1
            await d.save()
            logger.warning(f"[export] doc {d.id} failed: {e}")

async def _job_poll_outcomes():
    gw = _gw()
    try:
        res = await poll_outcomes(
            gw,
            dir_lines=config.MSD_DIR_LINES,
            dir_pdfs=config.MSD_DIR_PDFS,
            dir_numbers=config.MSD_DIR_NUMBERS,
        )
        logger.info(f"[poll] {res}")
    except Exception as e:
        logger.warning(f"[poll] error: {e}")

# ----- lifespan -----
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) DB init
    await Tortoise.init(
        db_url="sqlite://./db.sqlite3",
        modules={"models": ["models"]},
    )
    await Tortoise.generate_schemas()

    # 2) Optional MySQL pool (if your loader needs it — otherwise remove)
    app.state.mysql_pool = await aiomysql.create_pool(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        db=config.MYSQL_DB,
        autocommit=True,
        minsize=1,
        maxsize=5,
    )

    # 3) Seeds
    await _seed_admin()
    await seed_if_empty(logger=logger.info)

    # 4) Start interpreter loop (optional)
    interpreter_task = asyncio.create_task(run_forever(poll_seconds=15))

    # 5) Scheduler
    sched = Scheduler()
    app.state.scheduler = sched

    if config.METER_NOS:
        sched.every(15 * 60, _job_ingest_and_consolidate)
    sched.every(2 * 60, _job_export_ready)
    sched.every(5 * 60, _job_poll_outcomes)

    sched_task = asyncio.create_task(sched.run_forever())
    try:
        yield
    finally:
        if not sched_task.done():
            sched_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sched_task
        if not interpreter_task.done():
            interpreter_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await interpreter_task
        pool = getattr(app.state, "mysql_pool", None)
        if pool:
            pool.close()
            await pool.wait_closed()
        await Tortoise.close_connections()

# ----- app & routers -----
app = FastAPI(lifespan=lifespan, title="SDI Admin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "X-Total-Count"],
)

# Core routers
app.include_router(auth.router)
app.include_router(users.router)

app.include_router(sites.router)
app.include_router(od_pods.router)
app.include_router(pods.router)

app.include_router(meters.router)
app.include_router(meter_assignments.router)
app.include_router(meter_data.router)
app.include_router(meter_energy.router)
app.include_router(pod_data.router)
app.include_router(pod_energy.router)

app.include_router(billing.router)
app.include_router(tariffs.router)
app.include_router(tariff_operator.router)
app.include_router(tariff_records.router)
app.include_router(tariff_assignments.router)
app.include_router(supplier_bills.router)
app.include_router(supplier_bill_lines.router)
app.include_router(supplier_bill_measurement.router)

app.include_router(scope_counters.router)
app.include_router(admin_tasks.router)

app.include_router(integration_errors.router)
app.include_router(integration_admin.router)

# Static files
app.mount("/files/bills", StaticFiles(directory="data/bills/store"), name="bills")

# Optional: print routes
for route in app.routes:
    if isinstance(route, APIRoute):
        logger.info("%s -> %s", list(route.methods), route.path)
