from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Iterable, Dict, Any, Callable, Awaitable

# ⬇️ This is the missing piece: import the default MySQL loaders
from services.mysql_loader import fetch_tv_rows, fetch_bucket_rows

# Ingestion -> DB writes
from services.ingest_sdi import (
    ingest_mysql_tv_counters,
    ingest_mysql_bucket_counters,
)

# Raw -> Canonical consolidation
from services.consolidation_counters import (
    consolidate_raw_to_canonical_counters,
)

# Scope estimates -> synthetic raw counters
from services.estimation_allocation import (
    allocate_scope_estimates_to_meters,
)

RowLoader = Callable[[str, datetime, datetime], Awaitable[Iterable[Dict[str, Any]]]]


# ---------- Ingestion runners (use MySQL loaders by default) ----------

async def run_ingest_tv(
    meter_no: str,
    start: datetime,
    end: datetime,
    row_loader: RowLoader | None = None,
) -> Dict[str, Any]:
    """
    Fetch TV snapshot rows from MySQL (or custom loader) and write them into MeterDataRaw.
    """
    loader = row_loader or fetch_tv_rows          # default: MySQL SP FetchMeterData_v2
    rows = await loader(meter_no, start, end)     # -> list of dicts with 'tv', 'EA+', 'ER+', ...
    n = await ingest_mysql_tv_counters(meter_no, start, end, rows)
    return {"mode": "tv", "meter_no": meter_no, "rows": n}


async def run_ingest_buckets(
    meter_no: str,
    start: datetime,
    end: datetime,
    row_loader: RowLoader | None = None,
) -> Dict[str, Any]:
    """
    Fetch Segments/Buckets rows from MySQL (or custom loader) and write END counters into MeterDataRaw.
    """
    loader = row_loader or fetch_bucket_rows      # default: MySQL SP FetchMeterData_SegmentsBuckets_V2
    rows = await loader(meter_no, start, end)     # -> list of dicts with 'bucket_end', 'EA+_End', ...
    n = await ingest_mysql_bucket_counters(meter_no, start, end, rows)
    return {"mode": "buckets", "meter_no": meter_no, "rows": n}


# ---------- Consolidation ----------

async def run_consolidate(
    start: datetime,
    end: datetime,
    meter_nos: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Pick best raw per (meter, timestamp) and upsert counters into MeterData.
    """
    return await consolidate_raw_to_canonical_counters(start, end, meter_nos)


# ---------- Allocation (scope estimates -> synthetic raw) ----------

async def run_allocate(
    scope: str,
    scope_id: int,
    start: datetime,
    end: datetime,
    method: str = "equal_split",
) -> Dict[str, Any]:
    """
    Allocate ScopeEstimate energies to meters and synthesize end-of-bucket counters in MeterDataRaw.
    """
    return await allocate_scope_estimates_to_meters(scope, scope_id, start, end, method=method)
