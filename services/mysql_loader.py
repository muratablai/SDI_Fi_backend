from __future__ import annotations
from typing import Iterable, Dict, Any, List
from datetime import datetime, timezone
import aiomysql

from services import config

UTC = timezone.utc

_pool: aiomysql.Pool | None = None

async def _get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=config.MYSQL_HOST,
            port=config.MYSQL_PORT,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD,
            db=config.MYSQL_DB,
            autocommit=True,
            cursorclass=aiomysql.DictCursor,
        )
    return _pool

def _fmt_ts(ts: datetime) -> str:
    # MySQL proc expects strings like "{ts 'YYYY-MM-DD HH:MM:SS'}"
    ts = ts.astimezone(UTC).replace(microsecond=0)
    return "{ts '" + ts.strftime("%Y-%m-%d %H:%M:%S") + "'}"

async def fetch_tv_rows(
    meter_no: str,
    start: datetime,
    end: datetime,
    *,
    proc_name: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Calls MySQL TV procedure (default: FetchMeterData_v2) and returns rows shaped for ingest_mysql_tv_counters().
    Output keys: tv, EA+, EA-, ER+, ER-, R_Q1..R_Q4, (optional: constant, quality, reset_mark)
    """
    proc = proc_name or config.MYSQL_PROC_TV
    pool = await _get_pool()
    start_s = _fmt_ts(start)
    end_s = _fmt_ts(end)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # CALL FetchMeterData_v2(meter_no, start_ts, end_ts)
            await cur.callproc(proc, (meter_no, start_s, end_s))
            rows = await cur.fetchall()
            # Normalize column names -> expected ingest keys
            out = []
            for r in rows:
                # MySQL columns expected: TV as bac.TV mapped to tv, and energy counters aliases from your proc.
                tv = r.get("TV") or r.get("tv") or r.get("Tv")
                if isinstance(tv, datetime) and tv.tzinfo is None:
                    tv = tv.replace(tzinfo=UTC)
                out.append({
                    "tv": tv,
                    "EA+": r.get("EA_plus") or r.get("EA+") or r.get("EA_plus".upper()),
                    "EA-": r.get("EA_minus") or r.get("EA-") or r.get("EA_minus".upper()),
                    "ER+": r.get("ER_plus") or r.get("ER+") or r.get("ER_plus".upper()),
                    "ER-": r.get("ER_minus") or r.get("ER-") or r.get("ER_minus".upper()),
                    "R_Q1": r.get("R_Q1"),
                    "R_Q2": r.get("R_Q2"),
                    "R_Q3": r.get("R_Q3"),
                    "R_Q4": r.get("R_Q4"),
                    # Optional fields if present
                    "constant": r.get("constant"),
                    "quality": r.get("quality"),
                    "reset_mark": r.get("reset_mark"),
                })
            return out

async def fetch_bucket_rows(
    meter_no: str,
    start: datetime,
    end: datetime,
    *,
    bucket: str | None = None,
    minute_bucket: int | None = None,
    proc_name: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Calls MySQL Segments/Buckets procedure (default: FetchMeterData_SegmentsBuckets_V2).
    Returns rows compatible with ingest_mysql_bucket_counters():
      bucket_end, EA+_End, EA-_End, ER+_End, ER-_End, R_Q1_End..R_Q4_End, Reset_Steps, (optional: constant)
    """
    proc = proc_name or config.MYSQL_PROC_SEGMENTS_BUCKETS
    buck = (bucket or config.DEFAULT_BUCKET).lower()
    minb = minute_bucket or config.DEFAULT_MINUTE_BUCKET

    pool = await _get_pool()
    start_s = _fmt_ts(start)
    end_s = _fmt_ts(end)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # CALL FetchMeterData_SegmentsBuckets_V2(meter, start, end, bucket, minute_bucket)
            await cur.callproc(proc, (meter_no, start_s, end_s, buck, int(minb)))
            rows = await cur.fetchall()
            out = []
            # The proc returns three result sets; aiomysql fetches sequentially on nextset(). We need the 3rd set.
            # Try to advance to last result set (bucketed totals).
            # First set
            # NOTE: Some MySQL servers return only the final set. We'll try nextset() safely.
            more = await cur.nextset()
            if more:
                # second set
                more2 = await cur.nextset()
                if more2:
                    # third set is now current; re-fetch rows
                    rows = await cur.fetchall()

            for r in rows:
                bs = r.get("bucket_start")
                be = r.get("bucket_end")
                if isinstance(bs, datetime) and bs.tzinfo is None:
                    bs = bs.replace(tzinfo=UTC)
                if isinstance(be, datetime) and be.tzinfo is None:
                    be = be.replace(tzinfo=UTC)
                out.append({
                    "bucket_start": bs,
                    "bucket_end": be,
                    "EA+": r.get("EA+"),
                    "EA+_Start": r.get("EA+_Start"),
                    "EA+_End": r.get("EA+_End"),
                    "EA-": r.get("EA-"),
                    "EA-_Start": r.get("EA-_Start"),
                    "EA-_End": r.get("EA-_End"),
                    "ER+": r.get("ER+"),
                    "ER+_Start": r.get("ER+_Start"),
                    "ER+_End": r.get("ER+_End"),
                    "ER-": r.get("ER-"),
                    "ER-_Start": r.get("ER-_Start"),
                    "ER-_End": r.get("ER-_End"),
                    "R_Q1": r.get("R_Q1"),
                    "R_Q1_Start": r.get("R_Q1_Start"),
                    "R_Q1_End": r.get("R_Q1_End"),
                    "R_Q2": r.get("R_Q2"),
                    "R_Q2_Start": r.get("R_Q2_Start"),
                    "R_Q2_End": r.get("R_Q2_End"),
                    "R_Q3": r.get("R_Q3"),
                    "R_Q3_Start": r.get("R_Q3_Start"),
                    "R_Q3_End": r.get("R_Q3_End"),
                    "R_Q4": r.get("R_Q4"),
                    "R_Q4_Start": r.get("R_Q4_Start"),
                    "R_Q4_End": r.get("R_Q4_End"),
                    "Reset_Steps": r.get("Reset_Steps", 0),
                    "constant": r.get("constant"),
                })
            return out
