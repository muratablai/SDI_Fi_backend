# services.py — consolidation (raw->canonical) and billing scaffolding
from __future__ import annotations
from tortoise.transactions import in_transaction
from tortoise.expressions import Q
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from models import (
    Meter, MeterDataRaw, MeterData, DataSource,
    MeterAssignment, MeterOdPodAssignment, MeterSiteAssignment,
    Tariff, TariffAssignment, TariffOperatorPrice,
    Offer, OfferScope, VatRateHistory,
    BillingDocument, BillingLine,
)

BUCKET_MINUTES = 15  # adjust if needed

def bucketize(ts: datetime) -> datetime:
    minute = (ts.minute // BUCKET_MINUTES) * BUCKET_MINUTES
    return ts.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute)

async def resolve_constant(meter: Meter, at_ts: datetime, fallback: Optional[float]) -> Optional[float]:
    if fallback is not None:
        return fallback
    hist = await meter.constant_history.filter(valid_from__lte=at_ts).order_by("-valid_from").first()
    if hist and (hist.valid_to is None or hist.valid_to > at_ts):
        return hist.constant
    return meter.constant

async def choose_best_raw(rows: List[MeterDataRaw]) -> MeterDataRaw:
    src_priority: Dict[int, int] = {}
    for r in rows:
        if r.source_id not in src_priority:
            src = await DataSource.get(id=r.source_id)
            src_priority[r.source_id] = src.priority

    def qrank(q: Optional[str]) -> int:
        order = {"GOOD": 0, "REPLACED": 1, "INTERPOLATED": 2, "ESTIMATED": 3, None: 4}
        return order.get(q, 5)

    rows_sorted = sorted(
        rows,
        key=lambda r: (
            r.estimated,
            r.interpolated,
            qrank(r.quality),
            src_priority[r.source_id],
            -(r.received_at or datetime.min).timestamp(),
        ),
    )
    return rows_sorted[0]

async def upsert_meter_data_from_raw_group(meter_no: str, bucket_ts: datetime, group_rows: List[MeterDataRaw]):
    best = await choose_best_raw(group_rows)
    meter = await Meter.get(meter_no=meter_no)
    const = await resolve_constant(meter, bucket_ts, best.constant)

    md_vals = dict(
        meter_no=meter_no,
        timestamp=bucket_ts,
        active_import=best.active_import or 0.0,
        active_import_t1=best.active_import_t1 or 0.0,
        active_import_t2=best.active_import_t2 or 0.0,
        active_import_t3=best.active_import_t3 or 0.0,
        active_import_t4=best.active_import_t4 or 0.0,
        active_export=best.active_export or 0.0,
        active_export_t1=best.active_export_t1 or 0.0,
        active_export_t2=best.active_export_t2 or 0.0,
        active_export_t3=best.active_export_t3 or 0.0,
        active_export_t4=best.active_export_t4 or 0.0,
        reactive_import=best.reactive_import or 0.0,
        reactive_export=best.reactive_export or 0.0,
        reactive_q1=best.reactive_q1 or 0.0,
        reactive_q2=best.reactive_q2 or 0.0,
        reactive_q3=best.reactive_q3 or 0.0,
        reactive_q4=best.reactive_q4 or 0.0,
        power_import=best.power_import or 0.0,
        power_export=best.power_export or 0.0,
        constant=const,
        chosen_raw_id=best.id,
        chosen_source_code=(await DataSource.get(id=best.source_id)).code,
        quality=best.quality,
        estimated=best.estimated,
        interpolated=best.interpolated,
        reset_detected=best.reset_detected,
    )

    existing = await MeterData.filter(meter_no=meter_no, timestamp=bucket_ts).first()
    if existing:
        await MeterData.filter(id=existing.id).update(**md_vals)
        return await MeterData.get(id=existing.id)
    else:
        return await MeterData.create(**md_vals)

async def consolidate_raw_to_canonical(period_start: datetime, period_end: datetime, meter_nos: Optional[List[str]] = None) -> int:
    """
    Consolidate raw rows in [period_start, period_end) into canonical MeterData buckets.
    Returns number of buckets upserted.
    """
    q = Q(timestamp__gte=period_start) & Q(timestamp__lt=period_end)
    if meter_nos:
        q &= Q(meter_no__in=meter_nos)
    raws = await MeterDataRaw.filter(q).all()

    groups: Dict[Tuple[str, datetime], List[MeterDataRaw]] = {}
    for r in raws:
        bt = r.bucket_ts or bucketize(r.timestamp)
        groups.setdefault((r.meter_no, bt), []).append(r)

    count = 0
    async with in_transaction():
        for (mno, bt), rows in groups.items():
            await upsert_meter_data_from_raw_group(mno, bt, rows)
            count += 1
    return count

# -----------------------------
# BILLING
# -----------------------------
Scope = str  # "site" | "od_pod" | "pod"

async def resolve_vat_rate_at(at_ts: datetime) -> float:
    vat = await VatRateHistory.filter(valid_from__lte=at_ts).order_by("-valid_from").first()
    if vat and (vat.valid_to is None or vat.valid_to > at_ts):
        return float(vat.rate_percent)
    return 0.0

async def meters_in_scope(scope: Scope, scope_id: int) -> List[Meter]:
    if scope == "pod":
        ids = [x.meter_id for x in await MeterAssignment.filter(pod_id=scope_id).all()]
        return await Meter.filter(id__in=ids).all()
    if scope == "od_pod":
        ids = [x.meter_id for x in await MeterOdPodAssignment.filter(od_pod_id=scope_id).all()]
        return await Meter.filter(id__in=ids).all()
    if scope == "site":
        ids = [x.meter_id for x in await MeterSiteAssignment.filter(site_id=scope_id).all()]
        return await Meter.filter(id__in=ids).all()
    return []

async def tariff_assignment_at(scope: Scope, scope_id: int, at_ts: datetime, operator: Optional[str]) -> Optional[TariffAssignment]:
    def valid_q(qs):
        return qs.filter(Q(valid_from__lte=at_ts) | Q(valid_from__isnull=True))\
                 .filter(Q(valid_to__gt=at_ts) | Q(valid_to__isnull=True))
    ta = None
    if scope == "pod":
        ta = await valid_q(TariffAssignment.filter(pod_id=scope_id)).order_by("-is_primary", "-valid_from").first()
    if not ta and scope in ("pod", "od_pod"):
        ta = await valid_q(TariffAssignment.filter(od_pod_id=scope_id)).order_by("-is_primary", "-valid_from").first()
    if not ta:
        ta = await valid_q(TariffAssignment.filter(site_id=scope_id)).order_by("-is_primary", "-valid_from").first()
    if ta and operator and ta.operator and ta.operator != operator:
        alt = await TariffAssignment.filter(id=ta.id, operator=operator).first()
        if alt:
            ta = alt
    return ta

async def offer_for(scope: Scope, scope_id: int, tariff_id: int, operator: Optional[str], at_ts: datetime) -> Optional[Offer]:
    qs = Offer.filter(tariff_id=tariff_id, active=True, valid_from__lte=at_ts)\
              .filter(Q(valid_to__gt=at_ts) | Q(valid_to__isnull=True))
    if operator:
        qs = qs.filter(Q(operator=operator) | Q(operator__isnull=True))
    offers = await qs.all()
    for off in offers:
        if await off.scopes.filter(scope_type=scope, scope_id=scope_id).exists():
            return off
    return None

async def operator_price_cents(tariff_id: int, operator: Optional[str]) -> Optional[int]:
    if operator is None:
        prices = await TariffOperatorPrice.filter(tariff_id=tariff_id).all()
        if not prices:
            return None
        return int(min(p.price for p in prices) * 100)
    p = await TariffOperatorPrice.filter(tariff_id=tariff_id, operator=operator).first()
    return int(p.price * 100) if p else None

async def resolve_unit_price_cents(scope: Scope, scope_id: int, ta: TariffAssignment, at_ts: datetime) -> int:
    off = await offer_for(scope, scope_id, ta.tariff_id, ta.operator, at_ts)
    if off:
        if off.unit_price_cents is not None:
            return off.unit_price_cents
        base = await operator_price_cents(ta.tariff_id, off.operator or ta.operator)
        if base is None:
            raise ValueError("No operator price available for tariff")
        return round(base * (1 - (off.discount_percent or 0) / 100))
    if ta.price_override_cents is not None:
        return ta.price_override_cents
    base = await operator_price_cents(ta.tariff_id, ta.operator)
    if base is None:
        raise ValueError("No operator price available for tariff")
    if ta.discount_percent:
        return round(base * (1 - ta.discount_percent / 100))
    return base

async def slice_boundaries(scope: Scope, scope_id: int, start: datetime, end: datetime) -> List[datetime]:
    points = {start, end}
    tas = await TariffAssignment.filter(
        Q(site_id=scope_id if scope == "site" else None) |
        Q(od_pod_id=scope_id if scope == "od_pod" else None) |
        Q(pod_id=scope_id if scope == "pod" else None)
    ).all()
    for ta in tas:
        if ta.valid_from and start < ta.valid_from < end: points.add(ta.valid_from)
        if ta.valid_to and start < ta.valid_to < end: points.add(ta.valid_to)
    vats = await VatRateHistory.filter(valid_from__lt=end).all()
    for v in vats:
        if start < v.valid_from < end: points.add(v.valid_from)
        if v.valid_to and start < v.valid_to < end: points.add(v.valid_to)
    return sorted(points)

async def energy_by_band(meter_no: str, s: datetime, e: datetime) -> Dict[str, float]:
    buckets = await MeterData.filter(meter_no=meter_no, timestamp__gte=s, timestamp__lt=e).order_by("timestamp").all()
    if not buckets:
        return {"A+":0.0,"A-":0.0,"A+T1":0.0,"A+T2":0.0,"A+T3":0.0,"A+T4":0.0,"A-T1":0.0,"A-T2":0.0,"A-T3":0.0,"A-T4":0.0}

    def delta(attr: str) -> float:
        vals = [getattr(b, attr) for b in buckets]
        total = 0.0
        for i in range(1, len(vals)):
            step = (vals[i] - vals[i-1]) * (buckets[i].constant or 1.0)
            if step < 0:
                step = 0.0
            total += step
        return total

    return {
        "A+":  delta("active_import"),
        "A-":  delta("active_export"),
        "A+T1": delta("active_import_t1"),
        "A+T2": delta("active_import_t2"),
        "A+T3": delta("active_import_t3"),
        "A+T4": delta("active_import_t4"),
        "A-T1": delta("active_export_t1"),
        "A-T2": delta("active_export_t2"),
        "A-T3": delta("active_export_t3"),
        "A-T4": delta("active_export_t4"),
    }

async def slice_contains_estimated(meter_no: str, s: datetime, e: datetime) -> bool:
    return await MeterData.filter(
        meter_no=meter_no, timestamp__gte=s, timestamp__lt=e
    ).filter(Q(estimated=True) | Q(interpolated=True)).exists()

async def create_bill_for_scope(
    customer_id: str,
    scope: Scope,
    scope_id: int,
    period_start: datetime,
    period_end: datetime,
    operator: Optional[str] = None,
    currency: str = "RON",
    include_true_up: bool = True
) -> BillingDocument:
    if not (period_start < period_end):
        raise ValueError("Invalid period")

    meters = await meters_in_scope(scope, scope_id)
    if not meters:
        raise ValueError("No meters in scope for the requested period")

    cuts = await slice_boundaries(scope, scope_id, period_start, period_end)
    subtotal = 0
    vat_total = 0
    any_est = False

    async with in_transaction():
        doc = await BillingDocument.create(
            doc_type="INVOICE",
            customer_id=customer_id,
            period_start=period_start,
            period_end=period_end,
            currency=currency,
            status="DRAFT",
        )

        for i in range(len(cuts)-1):
            s, e = cuts[i], cuts[i+1]
            ta = await tariff_assignment_at(scope, scope_id, s, operator)
            if not ta:
                continue
            unit_price_c = await resolve_unit_price_cents(scope, scope_id, ta, s)
            vat_rate = await resolve_vat_rate_at(s)
            tariff_code = (await Tariff.get(id=ta.tariff_id)).code

            for m in meters:
                qtys = await energy_by_band(m.meter_no, s, e)
                est = await slice_contains_estimated(m.meter_no, s, e)
                any_est = any_est or est

                # Bill total A+ (extend to bands if needed)
                items = [("active_import", None, qtys["A+"])]
                # For TOU billing, add:
                # items += [
                #   ("active_import", "T1", qtys["A+T1"]), ..., ("active_import", "T4", qtys["A+T4"])
                # ]

                for channel, band, qty in items:
                    if qty <= 0:
                        continue
                    amount = round(qty * unit_price_c)
                    vat_amt = round(amount * vat_rate / 100)

                    await BillingLine.create(
                        document=doc,
                        meter_no=m.meter_no,
                        tariff_code=tariff_code + (f":{band}" if band else ""),
                        unit="kWh",
                        quantity=qty,
                        unit_price_cents=unit_price_c,
                        amount_cents=amount,
                        vat_rate_percent=vat_rate,
                        vat_amount_cents=vat_amt,
                        contains_estimated=est,
                        period_start=s,
                        period_end=e,
                        channel=channel,
                        tou_band=band,
                        is_true_up=False,
                    )

                    subtotal += amount
                    vat_total += vat_amt

        # Plug your regularizare (true-up) routine here if desired.

        await BillingDocument.filter(id=doc.id).update(
            subtotal_cents=subtotal,
            vat_cents=vat_total,
            total_cents=subtotal + vat_total,
            contains_estimated=any_est,
        )
        return await BillingDocument.get(id=doc.id)
