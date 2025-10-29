# services/scope_utils.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from models import (
    Meter,
    MeterAssignment,           # POD ↔ Meter
    MeterOdPodAssignment,      # OdPod ↔ Meter
    MeterSiteAssignment,       # Site ↔ Meter
    MeterReplacement,          # replacement continuity
)

UTC = timezone.utc


def _overlaps(a_start: datetime, a_end: Optional[datetime],
              b_start: datetime, b_end: Optional[datetime]) -> bool:
    """Interval overlap for [start, end) semantics; None means +∞."""
    a_end = a_end or datetime.max.replace(tzinfo=UTC)
    b_end = b_end or datetime.max.replace(tzinfo=UTC)
    return a_start < b_end and a_end > b_start


async def _assignments_for_scope(scope: str, scope_id: int) -> List[Dict[str, Any]]:
    """
    Fetch raw assignment rows (without time filtering).
    Returns dicts with meter_id, valid_from, valid_to.
    """
    if scope == "pod":
        return await MeterAssignment.filter(pod_id=scope_id).values(
            "meter_id", "valid_from", "valid_to"
        )
    if scope == "od_pod":
        return await MeterOdPodAssignment.filter(od_pod_id=scope_id).values(
            "meter_id", "valid_from", "valid_to"
        )
    if scope == "site":
        return await MeterSiteAssignment.filter(site_id=scope_id).values(
            "meter_id", "valid_from", "valid_to"
        )
    return []


async def meters_in_scope_at(scope: str, scope_id: int, at: Optional[datetime] = None) -> List[Meter]:
    """
    Point-in-time resolution: which meters are active for this scope at 'at'.
    """
    at = (at or datetime.now(tz=UTC))
    rows = await _assignments_for_scope(scope, scope_id)
    active_ids = [
        r["meter_id"]
        for r in rows
        if r["valid_from"] <= at and (r["valid_to"] is None or r["valid_to"] > at)
    ]
    if not active_ids:
        return []
    return await Meter.filter(id__in=list(set(active_ids))).all()


async def meters_in_scope_during(scope: str, scope_id: int, start: datetime, end: datetime) -> List[Meter]:
    """
    Time-window resolution: meters whose assignment overlaps [start, end).
    """
    rows = await _assignments_for_scope(scope, scope_id)
    overlapping_ids = [
        r["meter_id"] for r in rows if _overlaps(r["valid_from"], r["valid_to"], start, end)
    ]
    if not overlapping_ids:
        return []
    return await Meter.filter(id__in=list(set(overlapping_ids))).all()


async def meter_segments_for_scope_during(
    scope: str,
    scope_id: int,
    start: datetime,
    end: datetime,
    *,
    apply_replacements: bool = True,
) -> List[Dict[str, Any]]:
    """
    Precise coverage: returns time-sliced segments for each meter covering [start, end),
    clipped to assignment validity windows, and optionally split by MeterReplacement events.

    Output example item:
      {
        "meter_id": 42,
        "meter_no": "E123456",
        "from": datetime(..., tzinfo=UTC),
        "to":   datetime(..., tzinfo=UTC),
        "handover_from_prev": Optional[float],  # handover_read_active_import if a replacement starts this segment
      }
    """
    # 1) collect overlapping assignments and clip to [start,end)
    rows = await _assignments_for_scope(scope, scope_id)
    base_segments: List[Tuple[int, datetime, datetime]] = []  # (meter_id, seg_start, seg_end)

    for r in rows:
        a_start: datetime = r["valid_from"]
        a_end: Optional[datetime] = r["valid_to"]
        if not _overlaps(a_start, a_end, start, end):
            continue
        seg_start = max(a_start, start)
        seg_end = min(a_end or end, end)
        base_segments.append((r["meter_id"], seg_start, seg_end))

    if not base_segments:
        return []

    # 2) fetch meter details
    meter_ids = list({mid for (mid, _, _) in base_segments})
    meters = {m.id: m for m in await Meter.filter(id__in=meter_ids).all()}

    # 3) optionally split by replacements
    segments: List[Dict[str, Any]] = []
    if apply_replacements:
        reps = await MeterReplacement.filter(
            replacement_ts__gte=start, replacement_ts__lt=end
        ).values(
            "old_meter_id", "new_meter_id", "replacement_ts", "handover_read_active_import"
        )
        rep_by_old: Dict[int, List[Dict[str, Any]]] = {}
        for rep in reps:
            rep_by_old.setdefault(rep["old_meter_id"], []).append(rep)

        for mid, seg_start, seg_end in base_segments:
            reps_here = sorted(rep_by_old.get(mid, []), key=lambda x: x["replacement_ts"])
            if not reps_here:
                segments.append({
                    "meter_id": mid,
                    "meter_no": getattr(meters[mid], "meter_no", None),
                    "from": seg_start,
                    "to": seg_end,
                    "handover_from_prev": None,
                })
                continue

            cursor = seg_start
            for rep in reps_here:
                ts = rep["replacement_ts"]
                if ts <= cursor or ts >= seg_end:
                    continue
                # old meter up to replacement
                segments.append({
                    "meter_id": mid,
                    "meter_no": getattr(meters[mid], "meter_no", None),
                    "from": cursor,
                    "to": ts,
                    "handover_from_prev": None,
                })
                cursor = ts

                # new meter from replacement → seg_end
                new_mid = rep["new_meter_id"]
                segments.append({
                    "meter_id": new_mid,
                    "meter_no": getattr(meters.get(new_mid), "meter_no", None) if meters.get(new_mid) else None,
                    "from": ts,
                    "to": seg_end,
                    "handover_from_prev": rep.get("handover_read_active_import"),
                })

            if cursor < seg_end and not reps_here:
                segments.append({
                    "meter_id": mid,
                    "meter_no": getattr(meters[mid], "meter_no", None),
                    "from": cursor,
                    "to": seg_end,
                    "handover_from_prev": None,
                })
    else:
        for mid, seg_start, seg_end in base_segments:
            segments.append({
                "meter_id": mid,
                "meter_no": getattr(meters[mid], "meter_no", None),
                "from": seg_start,
                "to": seg_end,
                "handover_from_prev": None,
            })

    segments.sort(key=lambda s: (s["from"], s["meter_id"]))
    return segments


# ---------------------------------------------------------------------------
# Back-compat shim for legacy imports in routers:
# Many existing routers do: `from services.scope_utils import meters_in_scope`
# Keep that name and make it a thin wrapper over the point-in-time resolver.
# ---------------------------------------------------------------------------
async def meters_in_scope(scope: str, scope_id: int, at: Optional[datetime] = None) -> List[Meter]:
    """
    Back-compat wrapper. Returns meters active at 'at' (defaults to now, UTC).
    Prefer using meters_in_scope_at(...) or meters_in_scope_during(...).
    """
    return await meters_in_scope_at(scope, scope_id, at)
