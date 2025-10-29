from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

from models import MeterData
from services.scope_utils import meters_in_scope

UTC = timezone.utc


def floor_bucket(ts: datetime, bucket: str, minute_bucket: int = 15) -> datetime:
    ts = ts.astimezone(UTC)
    if bucket == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "month":
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if bucket == "year":
        return ts.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if bucket == "minute":
        sec = int(ts.timestamp())
        base = (sec // (minute_bucket * 60)) * (minute_bucket * 60)
        return datetime.fromtimestamp(base, tz=UTC)
    return ts


async def energies_for_meter(
    meter_no: str,
    start: datetime,
    end: datetime,
    *,
    bucket: str = "minute",
    minute_bucket: int = 15,
) -> List[Dict[str, Any]]:
    """
    Compute energies from canonical counters (non-negative deltas of consecutive rows).
    """
    qs = (
        MeterData.filter(
            meter_no=meter_no, timestamp__gte=start - timedelta(hours=1), timestamp__lt=end
        )
        .order_by("timestamp")
    )
    rows = await qs.values(
        "timestamp",
        "active_import",
        "active_export",
        "reactive_import",
        "reactive_export",
        "reactive_q1",
        "reactive_q2",
        "reactive_q3",
        "reactive_q4",
    )
    if not rows:
        return []

    out: Dict[datetime, Dict[str, Any]] = {}
    prev = None
    for cur in rows:
        if prev is None:
            prev = cur
            continue
        start_ts = prev["timestamp"].astimezone(UTC)
        end_ts = cur["timestamp"].astimezone(UTC)
        if end_ts <= start or end_ts > end:
            prev = cur
            continue
        bstart = floor_bucket(start_ts, bucket, minute_bucket)

        def d(k: str) -> float:
            a = prev.get(k)
            b = cur.get(k)
            if a is None or b is None:
                return 0.0
            return max(b - a, 0.0)

        rec = out.setdefault(
            bstart,
            {
                "bucket_start": bstart,
                "EA+": 0.0,
                "EA-": 0.0,
                "ER+": 0.0,
                "ER-": 0.0,
                "R_Q1": 0.0,
                "R_Q2": 0.0,
                "R_Q3": 0.0,
                "R_Q4": 0.0,
            },
        )
        rec["EA+"] += d("active_import")
        rec["EA-"] += d("active_export")
        rec["ER+"] += d("reactive_import")
        rec["ER-"] += d("reactive_export")
        rec["R_Q1"] += d("reactive_q1")
        rec["R_Q2"] += d("reactive_q2")
        rec["R_Q3"] += d("reactive_q3")
        rec["R_Q4"] += d("reactive_q4")
        prev = cur

    # finalize bucket_end
    out_list = []
    for bstart, r in out.items():
        if bucket == "minute":
            bend = bstart + timedelta(minutes=minute_bucket)
        elif bucket == "hour":
            bend = bstart + timedelta(hours=1)
        elif bucket == "day":
            bend = bstart + timedelta(days=1)
        elif bucket == "month":
            m = 12 if bstart.month == 12 else bstart.month + 1
            y = bstart.year + 1 if bstart.month == 12 else bstart.year
            bend = bstart.replace(year=y, month=m)
        elif bucket == "year":
            bend = bstart.replace(year=bstart.year + 1, month=1, day=1)
        else:
            bend = bstart
        r["bucket_end"] = bend
        out_list.append(r)
    out_list.sort(key=lambda x: x["bucket_start"])
    return out_list


async def energies_for_scope(
    scope: str,
    scope_id: int,
    start: datetime,
    end: datetime,
    *,
    bucket: str = "minute",
    minute_bucket: int = 15,
) -> List[Dict[str, Any]]:
    meters = await meters_in_scope(scope, scope_id)
    bucket_map: Dict[datetime, Dict[str, Any]] = {}
    for m in meters:
        rows = await energies_for_meter(m.meter_no, start, end, bucket=bucket, minute_bucket=minute_bucket)
        for r in rows:
            rec = bucket_map.setdefault(
                r["bucket_start"],
                {
                    "bucket_start": r["bucket_start"],
                    "bucket_end": r["bucket_end"],
                    "EA+": 0.0,
                    "EA-": 0.0,
                    "ER+": 0.0,
                    "ER-": 0.0,
                    "R_Q1": 0.0,
                    "R_Q2": 0.0,
                    "R_Q3": 0.0,
                    "R_Q4": 0.0,
                },
            )
            for k in ("EA+", "EA-", "ER+", "ER-", "R_Q1", "R_Q2", "R_Q3", "R_Q4"):
                rec[k] += r.get(k, 0.0)
    return sorted(bucket_map.values(), key=lambda x: x["bucket_start"])
