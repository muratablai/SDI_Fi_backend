from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict
from tortoise.transactions import in_transaction
from models import ScopeEstimate, MeterData, MeterDataRaw, DataSource
from services.scope_utils import meters_in_scope

UTC = timezone.utc


async def _source_estimate_scope() -> DataSource:
    src, _ = await DataSource.get_or_create(
        code="ESTIMATE_CLIENT_SCOPE",
        defaults={"name": "Estimate (scope)", "priority": 10},
    )
    return src


async def allocate_scope_estimates_to_meters(
    scope: str,
    scope_id: int,
    start: datetime,
    end: datetime,
    *,
    method: str = "equal_split",
) -> Dict:
    """
    Allocate ScopeEstimate energies to active meters and synthesize RAW counters
    at bucket end. Observed data will displace these during consolidation.
    """
    meters = await meters_in_scope(scope, scope_id)
    meter_nos = [m.meter_no for m in meters]
    src = await _source_estimate_scope()

    ests = await ScopeEstimate.filter(
        scope=scope, scope_id=scope_id, bucket_ts__gte=start, bucket_ts__lt=end
    ).order_by("bucket_ts").values()

    written = 0
    async with in_transaction():
        for e in ests:
            bts = e["bucket_ts"].astimezone(UTC)
            weights = {mn: 1.0 / len(meter_nos) for mn in meter_nos} if meter_nos else {}
            for mn, w in weights.items():
                prev = (
                    await MeterData.filter(meter_no=mn, timestamp__lte=bts)
                    .order_by("-timestamp")
                    .first()
                    .values(
                        "active_import",
                        "active_export",
                        "reactive_import",
                        "reactive_export",
                        "reactive_q1",
                        "reactive_q2",
                        "reactive_q3",
                        "reactive_q4",
                    )
                ) or {}
                def add(prev_v, inc): return float(prev_v or 0.0) + float(inc or 0.0) * w

                payload = dict(
                    meter_no=mn,
                    timestamp=bts,
                    bucket_ts=bts,
                    active_import=add(prev.get("active_import"), e.get("ea_plus")),
                    active_export=add(prev.get("active_export"), e.get("ea_minus")),
                    reactive_import=add(prev.get("reactive_import"), e.get("er_plus")),
                    reactive_export=add(prev.get("reactive_export"), e.get("er_minus")),
                    reactive_q1=add(prev.get("reactive_q1"), e.get("rq1")),
                    reactive_q2=add(prev.get("reactive_q2"), e.get("rq2")),
                    reactive_q3=add(prev.get("reactive_q3"), e.get("rq3")),
                    reactive_q4=add(prev.get("reactive_q4"), e.get("rq4")),
                    constant=None,
                    source_id=src.id,
                    quality="ESTIMATED",
                    quality_code=50,
                    estimated=True,
                    estimation_method=e.get("estimation_method") or "scope_alloc_v1",
                    reset_detected=False,
                )
                await MeterDataRaw.update_or_create(
                    defaults=payload,
                    meter_no=mn,
                    bucket_ts=bts,
                    source_id=src.id,
                )
                written += 1

    return {
        "synthetic_raw_rows": written,
        "buckets": len(ests),
        "meters": len(meter_nos),
    }
