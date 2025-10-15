# app/services/seeder.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

from tortoise.transactions import in_transaction

from models import Site, OdPod, Pod, Meter, Tariff, TariffOperatorPrice

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def _load_json(filename: str):
    p = DATA_DIR / filename
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

def _strip_after_slash(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    i = s.find("/")
    return s[:i] if i >= 0 else s

async def seed_if_empty(logger=print):
    sites_count   = await Site.all().count()
    odpods_count  = await OdPod.all().count()
    pods_count    = await Pod.all().count()
    meters_count  = await Meter.all().count()
    tariffs_count = await Tariff.all().count()

    logger(f"[seed] counts => sites={sites_count}, od_pods={odpods_count}, pods={pods_count}, meters={meters_count}, tariffs={tariffs_count}")

    # Seed if any of these tables are empty (greenfield)
    if sites_count and odpods_count and pods_count and meters_count and tariffs_count:
        logger("[seed] already populated — skipping.")
        return

    sites_seed   = _load_json("sites_seed.json")
    odpods_seed  = _load_json("od_pods_seed.json")
    pods_seed    = _load_json("pods_seed.json")
    meters_seed  = _load_json("meters_seed.json")
    tariffs_seed = _load_json("tariffs_seed.json")

    created = {"sites": 0, "od_pods": 0, "pods": 0, "meters": 0, "tariffs": 0, "tariff_prices": 0}
    updated = {"sites": 0, "od_pods": 0, "pods": 0, "meters": 0, "tariffs": 0, "tariff_prices": 0}
    skipped = {"sites": 0, "od_pods": 0, "pods": 0, "meters": 0, "tariffs": 0, "tariff_prices": 0}

    # Track OD PODs skipped because lacking site
    skipped_od_no_site = 0

    # Build quick lookups (lazy-filled as we create)
    sites_by_code: Dict[str, Site] = {}
    od_by_code: Dict[str, OdPod] = {}
    pods_by_sdi: Dict[str, Pod] = {}

    async with in_transaction():
        # -------------------
        # Sites
        # -------------------
        for s in sites_seed:
            code = (s.get("code") or "").strip()
            name = (s.get("name") or "").strip() or None
            if not code:
                skipped["sites"] += 1
                continue

            obj = await Site.get_or_none(code=code)
            if not obj:
                obj = await Site.create(code=code, name=name)
                created["sites"] += 1
            else:
                changed = False
                if obj.name != name:
                    obj.name = name
                    changed = True
                # Optional fields if present in seeds
                for f in ("address","city","county","latitude","longitude"):
                    if f in s and getattr(obj, f) != s.get(f):
                        setattr(obj, f, s.get(f))
                        changed = True
                if changed:
                    await obj.save()
                    updated["sites"] += 1
                else:
                    skipped["sites"] += 1
            sites_by_code[code] = obj

        # -------------------
        # OD PODs (skip if site_code not resolvable)
        # -------------------
        for r in odpods_seed:
            pod_od = (r.get("pod_od") or "").strip()
            site_code = (r.get("site_code") or "").strip()
            if not pod_od:
                skipped["od_pods"] += 1
                continue

            if not site_code:
                # new policy: don't insert OD PODs without a site_code
                skipped_od_no_site += 1
                skipped["od_pods"] += 1
                continue

            site = sites_by_code.get(site_code) or await Site.get_or_none(code=site_code)
            if not site:
                # site referenced by seeds not present -> skip this OD POD
                skipped_od_no_site += 1
                skipped["od_pods"] += 1
                continue

            obj = await OdPod.get_or_none(pod_od=pod_od)
            if not obj:
                obj = await OdPod.create(
                    pod_od=pod_od,
                    site=site,
                    name=r.get("name"),
                    operator=r.get("operator"),  # if your model uses operator FK instead, adjust here
                    valid_from=r.get("valid_from"),
                    valid_to=r.get("valid_to"),
                )
                created["od_pods"] += 1
            else:
                changed = False
                if obj.site != site.id:
                    obj.site = site; changed = True
                for f in ("name", "valid_from", "valid_to"):
                    nv = r.get(f)
                    if nv is not None and getattr(obj, f) != nv:
                        setattr(obj, f, nv); changed = True
                # if operator string was stored
                if "operator" in r and getattr(obj, "operator", None) != r.get("operator"):
                    setattr(obj, "operator", r.get("operator")); changed = True
                if changed:
                    await obj.save(); updated["od_pods"] += 1
                else:
                    skipped["od_pods"] += 1
            od_by_code[pod_od] = obj

        # -------------------
        # PODs
        # -------------------
        for r in pods_seed:
            pod_sdi = (r.get("pod_sdi") or "").strip()
            site_code = (r.get("site_code") or "").strip()
            if not pod_sdi or not site_code:
                skipped["pods"] += 1
                continue

            site = sites_by_code.get(site_code) or await Site.get_or_none(code=site_code)
            if not site:
                # cannot place the POD anywhere; skip
                skipped["pods"] += 1
                continue

            # link od_pod if present and exists
            od_code = (r.get("od_pod") or "").strip()
            od_obj: Optional[OdPod] = None
            if od_code:
                od_obj = od_by_code.get(od_code) or await OdPod.get_or_none(pod_od=od_code)

            obj = await Pod.get_or_none(pod_sdi=pod_sdi)
            if not obj:
                obj = await Pod.create(
                    pod_sdi=pod_sdi,
                    site=site,
                    od_pod=od_obj,
                    name=r.get("name"),
                    role=r.get("role"),
                    trafo_no=r.get("trafo_no"),
                    bmc_nr=r.get("bmc_nr"),
                    pvv_nr=r.get("pvv_nr"),
                    pvc_nr=r.get("pvc_nr"),
                )
                created["pods"] += 1
            else:
                changed = False
                if obj.site != site.id:
                    obj.site = site; changed = True
                # only overwrite od_pod if we found a resolvable one
                if od_obj and (obj.od_pod != od_obj.id):
                    obj.od_pod = od_obj; changed = True
                for f in ("name","role","trafo_no","bmc_nr","pvv_nr","pvc_nr"):
                    nv = r.get(f)
                    if nv is not None and getattr(obj, f) != nv:
                        setattr(obj, f, nv); changed = True
                if changed:
                    await obj.save(); updated["pods"] += 1
                else:
                    skipped["pods"] += 1
            pods_by_sdi[pod_sdi] = obj

        # -------------------
        # Meters
        # -------------------
        for r in meters_seed:
            meter_no = (r.get("meter_no") or "").strip()
            if not meter_no:
                skipped["meters"] += 1
                continue
            name = (r.get("name") or None) or None
            constant = float(r.get("constant") or 1.0)

            # try to attach to pod first
            pod_sdi = (r.get("pod_sdi") or "").strip()
            pod_obj: Optional[Pod] = None
            if pod_sdi:
                pod_obj = pods_by_sdi.get(pod_sdi) or await Pod.get_or_none(pod_sdi=pod_sdi)

            # site fallback (when pod not resolvable)
            site_code = (r.get("site_code") or "").strip()
            site_obj: Optional[Site] = None
            if not pod_obj and site_code:
                site_obj = sites_by_code.get(site_code) or await Site.get_or_none(code=site_code)

            # od_pod link iff exists (derived from pod_sdi base part)
            od_obj: Optional[OdPod] = None
            if pod_sdi:
                base_od = _strip_after_slash(pod_sdi)
                if base_od:
                    od_obj = od_by_code.get(base_od) or await OdPod.get_or_none(pod_od=base_od)

            obj = await Meter.get_or_none(meter_no=meter_no)
            if not obj:
                kwargs: Dict[str, Any] = {
                    "meter_no": meter_no,
                    "name": name,
                    "constant": constant,
                }
                if pod_obj:
                    kwargs["pod"] = pod_obj
                if od_obj:
                    kwargs["od_pod"] = od_obj
                if site_obj:
                    kwargs["site"] = site_obj

                await Meter.create(**kwargs)
                created["meters"] += 1
            else:
                changed = False
                if name is not None and obj.name != name:
                    obj.name = name; changed = True
                if hasattr(obj, "constant") and obj.constant != constant:
                    obj.constant = constant; changed = True

                # Prefer to keep existing links if already set; otherwise set what we have
                if (obj.pod is None) and pod_obj:
                    obj.pod = pod_obj; changed = True
                if (obj.od_pod is None) and od_obj:
                    obj.od_pod = od_obj; changed = True
                if (obj.site is None) and site_obj:
                    obj.site = site_obj; changed = True

                if changed:
                    await obj.save(); updated["meters"] += 1
                else:
                    skipped["meters"] += 1

        # -------------------
        # Tariffs + prices
        # -------------------
        for t in tariffs_seed:
            code = (t.get("code") or "").strip()
            if not code:
                skipped["tariffs"] += 1
                continue

            obj = await Tariff.get_or_none(code=code)
            if not obj:
                obj = await Tariff.create(
                    code=code,
                    description=t.get("description"),
                    unit=t.get("unit"),
                    billing_type=t.get("billing_type"),
                    active=bool(t.get("active", True)),
                )
                created["tariffs"] += 1
            else:
                changed = False
                for f in ("description","unit","billing_type","active"):
                    if f in t and getattr(obj, f) != t.get(f):
                        setattr(obj, f, t.get(f)); changed = True
                if changed:
                    await obj.save(); updated["tariffs"] += 1
                else:
                    skipped["tariffs"] += 1

            # operator prices
            for op_name, price in (t.get("operator_prices") or {}).items():
                op = str(op_name).strip()
                if not op:
                    continue
                price_f = float(price)
                existing = await TariffOperatorPrice.get_or_none(tariff=obj, operator=op)
                if not existing:
                    await TariffOperatorPrice.create(tariff=obj, operator=op, price=price_f)
                    created["tariff_prices"] += 1
                else:
                    if existing.price != price_f:
                        existing.price = price_f
                        await existing.save()
                        updated["tariff_prices"] += 1
                    else:
                        skipped["tariff_prices"] += 1

    logger(
        "[seed] done.\n"
        f"  created={created}\n"
        f"  updated={updated}\n"
        f"  skipped={skipped}\n"
        f"  skipped_od_pods_without_site={skipped_od_no_site}"
    )
