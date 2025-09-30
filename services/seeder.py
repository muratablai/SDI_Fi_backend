# app/services/seeder.py
from __future__ import annotations
import json
from pathlib import Path
from tortoise.transactions import in_transaction
from models import Area, Location, Meter

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def _load_json(filename: str):
    path = DATA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

async def seed_if_empty(logger=print):
    areas_count = await Area.all().count()
    locs_count  = await Location.all().count()
    meters_count = await Meter.all().count()

    logger(f"[seed] counts => areas={areas_count}, locations={locs_count}, meters={meters_count}")

    if areas_count and locs_count and meters_count:
        logger("[seed] already populated — skip seeding.")
        return

    areas = _load_json("areas_seed.json")
    locations = _load_json("locations_seed.json")
    meters = _load_json("meters_seed.json")

    created = {"areas":0, "locations":0, "meters":0}
    updated = {"areas":0, "locations":0, "meters":0}
    skipped = {"areas":0, "locations":0, "meters":0}

    async with in_transaction():
        # Areas
        for a in areas:
            obj = await Area.get_or_none(code=a["code"])
            if not obj:
                await Area.create(**a)
                created["areas"] += 1
            else:
                changed = False
                for f in ("name","address","city","county","latitude","longitude"):
                    nv = a.get(f)
                    if getattr(obj, f) != nv:
                        setattr(obj, f, nv); changed = True
                if changed: await obj.save(); updated["areas"] += 1
                else: skipped["areas"] += 1

        # Locations (needs area_code)
        for l in locations:
            area = await Area.get_or_none(code=l["area_code"])
            if not area:
                raise RuntimeError(f"[seed] unknown area_code {l['area_code']} for POD {l.get('pod_sdi')}")
            obj = await Location.get_or_none(pod_sdi=l["pod_sdi"])
            if not obj:
                await Location.create(
                    pod_sdi=l["pod_sdi"], name=l.get("name"), role=l.get("role"),
                    area=area, trafo_no=l.get("trafo_no"), bmc_nr=l.get("bmc_nr"),
                    pvv_nr=l.get("pvv_nr"), pvc_nr=l.get("pvc_nr")
                )
                created["locations"] += 1
            else:
                changed = False
                for f in ("name","role","trafo_no","bmc_nr","pvv_nr","pvc_nr"):
                    nv = l.get(f)
                    if getattr(obj, f) != nv:
                        setattr(obj, f, nv); changed = True
                if obj.area_id != area.id:
                    obj.area = area; changed = True
                if changed: await obj.save(); updated["locations"] += 1
                else: skipped["locations"] += 1

        # Meters (prefer POD link; keep Area aligned)
        for m in meters:
            meter_no = m["meter_no"].strip()
            name = (m.get("name") or "").strip() or None
            area = await Area.get_or_none(code=m.get("area_code")) if m.get("area_code") else None
            loc = await Location.get_or_none(pod_sdi=m.get("pod_sdi")) if m.get("pod_sdi") else None

            if loc:
                area_id = loc.area_id
            elif area:
                area_id = area.id
            else:
                raise RuntimeError(f"[seed] need pod_sdi or area_code for meter {meter_no}")

            obj = await Meter.get_or_none(meter_no=meter_no)
            if not obj:
                await Meter.create(
                    meter_no=meter_no,
                    name=name,
                    area_id=area_id,
                    location_id=(loc.id if loc else None),
                )
                created["meters"] += 1
            else:
                changed = False
                if name is not None and obj.name != name:
                    obj.name = name; changed = True
                if obj.area_id != area_id:
                    obj.area_id = area_id; changed = True
                if loc and obj.location_id != loc.id:
                    obj.location_id = loc.id; changed = True
                if changed: await obj.save(); updated["meters"] += 1
                else: skipped["meters"] += 1

    logger(f"[seed] done. created={created} updated={updated} skipped={skipped}")
