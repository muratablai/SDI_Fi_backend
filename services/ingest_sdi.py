from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterable
from tortoise.transactions import in_transaction
from models import MeterDataRaw, DataSource

UTC = timezone.utc


async def _get_or_create_source(code: str, priority: int = 50) -> DataSource:
    src, _ = await DataSource.get_or_create(
        code=code, defaults={"name": code, "priority": priority}
    )
    return src


async def ingest_mysql_tv_counters(
    meter_no: str,
    start: datetime,
    end: datetime,
    rows: Iterable[dict],
    *,
    source_code: str = "SDI_PROC_TV",
    quality_default: int = 95,
) -> int:
    """
    Ingest raw per-TV counter snapshots from MySQL into MeterDataRaw.
    Expect: tv, EA+, EA-, ER+, ER-, R_Q1..R_Q4 (+ optional constant, quality, reset_mark)
    """
    src = await _get_or_create_source(source_code, priority=80)
    n = 0
    async with in_transaction():
        for r in rows:
            tv = r["tv"]
            ts = tv if tv.tzinfo else tv.replace(tzinfo=UTC)
            payload = dict(
                meter_no=meter_no,
                timestamp=ts,
                bucket_ts=ts,
                active_import=r.get("EA+"),
                active_export=r.get("EA-"),
                reactive_import=r.get("ER+"),
                reactive_export=r.get("ER-"),
                reactive_q1=r.get("R_Q1"),
                reactive_q2=r.get("R_Q2"),
                reactive_q3=r.get("R_Q3"),
                reactive_q4=r.get("R_Q4"),
                constant=r.get("constant"),
                source_id=src.id,
                quality="GOOD",
                quality_code=r.get("quality", quality_default),
                estimated=False,
                estimation_method=None,
                reset_detected=bool(r.get("reset_mark", 0)),
            )
            await MeterDataRaw.update_or_create(
                defaults=payload,
                meter_no=meter_no,
                bucket_ts=ts,
                source_id=src.id,
            )
            n += 1
    return n


async def ingest_mysql_bucket_counters(
    meter_no: str,
    start: datetime,
    end: datetime,
    rows: Iterable[dict],
    *,
    source_code: str = "SDI_PROC_BUCKETS",
    quality_base: int = 90,
) -> int:
    """
    Ingest aggregated per-bucket counter END snapshots into MeterDataRaw.
    Expect: bucket_end, *_End counters, Reset_Steps (optional constant)
    """
    src = await _get_or_create_source(source_code, priority=70)
    n = 0
    async with in_transaction():
        for r in rows:
            be = r["bucket_end"]
            ts = be if be.tzinfo else be.replace(tzinfo=UTC)
            reset_steps = int(r.get("Reset_Steps", 0) or 0)
            qcode = max(10, quality_base - 10 * reset_steps)
            payload = dict(
                meter_no=meter_no,
                timestamp=ts,
                bucket_ts=ts,
                active_import=r.get("EA+_End"),
                active_export=r.get("EA-_End"),
                reactive_import=r.get("ER+_End"),
                reactive_export=r.get("ER-_End"),
                reactive_q1=r.get("R_Q1_End"),
                reactive_q2=r.get("R_Q2_End"),
                reactive_q3=r.get("R_Q3_End"),
                reactive_q4=r.get("R_Q4_End"),
                constant=r.get("constant"),
                source_id=src.id,
                quality="GOOD",
                quality_code=qcode,
                estimated=False,
                estimation_method=None,
                reset_detected=reset_steps > 0,
            )
            await MeterDataRaw.update_or_create(
                defaults=payload,
                meter_no=meter_no,
                bucket_ts=ts,
                source_id=src.id,
            )
            n += 1
    return n
