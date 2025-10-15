# services/energy_unified.py
from __future__ import annotations
from typing import Optional, Tuple, Literal, Iterable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from tortoise.expressions import Q

from models import Meter, MeterData
from api_utils import respond_plain_list  # only for typing parity if you want

# Reuse the SP helper we already built
from services.energy_proc import (
    call_energy_proc_with_constant,
    client_sort,
    Granularity,
)

BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")

# -------------------------
# Meter resolution
# -------------------------
async def resolve_meter(filters: dict) -> Optional[Meter]:
    """
    Priority:
      1) meter_id
      2) meter_no
      3) name (exact)
      4) pod / od_pod / site -> pick latest
    """
    if filters.get("meter_id") is not None:
        try:
            m = await Meter.get_or_none(id=int(filters["meter_id"]))
            if m: return m
        except (TypeError, ValueError):
            pass

    if filters.get("meter_no"):
        m = await Meter.get_or_none(meter_no=str(filters["meter_no"]))
        if m: return m

    if filters.get("name"):
        m = await Meter.get_or_none(name=str(filters["name"]))
        if m: return m

    # choose latest meter linked at scope
    for fk, field in (("pod", "pod_id"), ("od_pod", "od_pod_id"), ("site", "site_id")):
        if filters.get(fk) is not None:
            try:
                scope_id = int(filters[fk])
            except (TypeError, ValueError):
                continue
            m = await Meter.filter(**{field: scope_id}).order_by("-updated_at", "-created_at").first()
            if m: return m

    return None


# -------------------------
# Backend selection
# -------------------------
def decide_backend(m: Meter, filters: dict) -> Literal["proc", "db"]:
    """
    If caller forces backend via filters["backend"], honor it.
    Otherwise:
      - SDI/PROC if linked to a POD (common for SDI meters)
      - DB if linked to OD_POD or Site (common for OD meters)
      - fallback to PROC if meter.name looks usable; else DB
    """
    forced = (filters.get("backend") or "").lower()
    if forced in {"proc", "db"}:
        return forced  # honor override

    if m.pod:        # typical SDI
        return "proc"
    if m.od_pod or m.site:  # typical OD side
        return "db"

    # Fallback heuristic
    return "proc" if (m.name or "").strip() else "db"


# -------------------------
# Time helpers
# -------------------------
def to_bucharest_iso(dt: datetime | str | None) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dtp = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt  # as-is
    else:
        dtp = dt
    if dtp.tzinfo is None:
        # treat naive as Bucharest wall-time (consistent with UI buckets)
        dtp = dtp.replace(tzinfo=BUCHAREST_TZ)
    return dtp.astimezone(BUCHAREST_TZ).isoformat()


def floor_bucket(dt: datetime, gran: Granularity) -> datetime:
    """Return Bucharest-wall bucket start."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BUCHAREST_TZ)
    dt = dt.astimezone(BUCHAREST_TZ)
    if gran == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    if gran == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if gran == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if gran == "year":
        return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt


def next_bucket_start(dt: datetime, gran: Granularity) -> datetime:
    if gran == "hour":
        return dt + timedelta(hours=1)
    if gran == "day":
        return dt + timedelta(days=1)
    if gran == "month":
        # naive month increment
        month = dt.month + 1
        year = dt.year + (1 if month == 13 else 0)
        month = 1 if month == 13 else month
        return dt.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
    if gran == "year":
        return dt.replace(year=dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt


# -------------------------
# DB (OD) aggregator
# -------------------------
async def fetch_energy_db_meterdata(
    *,
    meter_no: str,
    constant: float,
    date_from_iso: Optional[str],
    date_to_iso: Optional[str],
    granularity: Granularity,
) -> list[dict]:
    """
    Build energy buckets from MeterData (counters). We sum positive deltas within each bucket
    for FA (active import). Adjust with constant.
    """
    qs = MeterData.filter(meter_no=meter_no)
    if date_from_iso:
        qs = qs.filter(timestamp__gte=date_from_iso)
    if date_to_iso:
        qs = qs.filter(timestamp__lte=date_to_iso)

    rows = await qs.order_by("timestamp").values("timestamp", "fa", "fr", "ra")

    # Group by Bucharest buckets and sum deltas of FA
    buckets: dict[datetime, float] = {}
    last_fa: Optional[float] = None
    last_bucket: Optional[datetime] = None

    for r in rows:
        ts: datetime = r["timestamp"]
        if ts.tzinfo is None:
            # treat DB naive timestamps as Bucharest local (keeps UI happy)
            ts = ts.replace(tzinfo=BUCHAREST_TZ)
        bstart = floor_bucket(ts, granularity)

        fa = float(r.get("fa") or 0)

        # refresh bucket boundaries
        if last_bucket is None:
            last_bucket = bstart

        # delta against previous reading (same meter)
        if last_fa is not None:
            delta = fa - last_fa
            if delta < 0:
                # counter rollover/reset protection: skip negative
                delta = 0.0
        else:
            delta = 0.0

        # accumulate in current bucket
        buckets[bstart] = buckets.get(bstart, 0.0) + max(delta, 0.0)

        # move forward
        last_fa = fa
        last_bucket = bstart

    # Normalize into API shape + apply constant
    items: list[dict] = []
    for bstart, ea_plus_counter in sorted(buckets.items()):
        ea_plus = ea_plus_counter * float(constant or 1.0)
        item = {
            "id": to_bucharest_iso(bstart) or str(bstart),
            "meter_name": meter_no,
            "meter_no": meter_no,
            "bucket_start": to_bucharest_iso(bstart),
            "bucket_end": to_bucharest_iso(next_bucket_start(bstart, granularity)),
            "ea_plus": ea_plus,
            "ea_minus": 0.0,
            "er_plus": 0.0,
            "er_minus": 0.0,
            "r_q1": 0.0,
            "r_q2": 0.0,
            "r_q3": 0.0,
            "r_q4": 0.0,
            "reset_steps": 0,
            "energy": ea_plus,
        }
        items.append(item)

    return items


# -------------------------
# Main entry point (used by routers)
# -------------------------
async def unified_energy_query(
    request: Request,
    *,
    filters: dict,
    sort_json: str,
) -> list[dict]:
    """
    Resolve meter + constant, select backend, fetch, sort.
    filters expects keys like: meter_id, meter_no, name, pod, od_pod, site, date_gte, date_lte, granularity, backend?
    """
    m = await resolve_meter(filters)
    if not m:
        return []

    meter_key = (m.name or m.meter_no or "").strip()
    if not meter_key:
        return []

    constant = float(m.constant or 1.0)
    gran_raw = str(filters.get("granularity") or "day").lower()
    gran: Granularity = gran_raw if gran_raw in {"hour", "day", "month", "year"} else "day"

    backend = decide_backend(m, filters)

    if backend == "proc":
        items = await call_energy_proc_with_constant(
            request,
            meter_key=meter_key,   # procedure accepts NAME for SDI, but we pass whatever the NAME is; if blank we used meter_no
            constant=constant,
            date_from_iso=filters.get("date_gte"),
            date_to_iso=filters.get("date_lte"),
            granularity=gran,
            debug=True,
        )
    else:
        # DB path uses MeterData for this meter_no
        items = await fetch_energy_db_meterdata(
            meter_no=m.meter_no,
            constant=constant,
            date_from_iso=filters.get("date_gte"),
            date_to_iso=filters.get("date_lte"),
            granularity=gran,
        )

    # client sort
    items = client_sort(items, sort_json)
    return items
