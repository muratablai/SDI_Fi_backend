from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterable, Optional
from tortoise.transactions import in_transaction
from models import MeterDataRaw, MeterData, DataSource

UTC = timezone.utc


async def consolidate_raw_to_canonical_counters(
    start: datetime,
    end: datetime,
    meter_nos: Optional[Iterable[str]] = None,
) -> dict:
    """
    Best-of selection into canonical COUNTERS (MeterData) keyed by (meter_no, timestamp).
    Ranking:
      - higher quality_code
      - higher DataSource.priority
      - later received_at
    """
    q = MeterDataRaw.filter(bucket_ts__gte=start, bucket_ts__lt=end)
    if meter_nos:
        q = q.filter(meter_no__in=list(meter_nos))

    candidates = await q.values(
        "id",
        "meter_no",
        "bucket_ts",
        "active_import",
        "active_export",
        "reactive_import",
        "reactive_export",
        "reactive_q1",
        "reactive_q2",
        "reactive_q3",
        "reactive_q4",
        "power_import",
        "power_export",
        "constant",
        "estimated",
        "estimation_method",
        "source_id",
        "quality",
        "quality_code",
        "reset_detected",
        "received_at",
    )

    # Cache source priorities
    src_priority = {
        s["id"]: (s["priority"] or 0)
        for s in await DataSource.all().values("id", "priority")
    }

    # Group by meter,bucket_ts
    groups = {}
    for r in candidates:
        groups.setdefault((r["meter_no"], r["bucket_ts"]), []).append(r)

    written = 0
    async with in_transaction():
        for (meter_no, bts), rows in groups.items():
            rows.sort(
                key=lambda x: (
                    -(x.get("quality_code") or 0),
                    -src_priority.get(x["source_id"], 0),
                    x.get("received_at") or datetime.min.replace(tzinfo=UTC),
                ),
                reverse=False,
            )
            best = rows[0]
            src_obj = await DataSource.get(id=best["source_id"])

            defaults = dict(
                meter_no=meter_no,
                timestamp=bts,  # canonical key
                active_import=best["active_import"],
                active_export=best["active_export"],
                reactive_import=best["reactive_import"],
                reactive_export=best["reactive_export"],
                reactive_q1=best["reactive_q1"],
                reactive_q2=best["reactive_q2"],
                reactive_q3=best["reactive_q3"],
                reactive_q4=best["reactive_q4"],
                power_import=best.get("power_import"),
                power_export=best.get("power_export"),
                constant=best["constant"],
                chosen_raw_id=best["id"],
                chosen_source_code=src_obj.code,
                quality=best["quality"],
                estimated=best["estimated"],
                estimation_method=best["estimation_method"],
                reset_detected=best["reset_detected"],
            )

            await MeterData.update_or_create(
                defaults=defaults,
                meter_no=meter_no,
                timestamp=bts,
            )
            written += 1

    return {"canonical_upserted": written, "groups": len(groups)}
