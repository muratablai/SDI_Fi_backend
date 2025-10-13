# routers/tariffs.py
from fastapi import APIRouter, Depends, HTTPException
from models import Tariff, TariffOperatorPrice
from schemas import TariffCreate, TariffUpdate, TariffRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item

router = APIRouter(prefix="/tariffs", tags=["tariffs"])

def to_tariff_read(t: Tariff) -> TariffRead:
    # fold operator prices
    op_prices = {}
    if hasattr(t, "prices"):
        for p in t.prices:  # if prefetched
            op_prices[p.operator] = float(p.price)
    # If not prefetched, it will be empty here; callers can enrich if needed.
    base = TariffRead.model_validate(t).model_dump()
    base["operator_prices"] = op_prices or None
    return TariffRead.model_validate(base)

@router.get("", response_model=list[TariffRead])
async def list_tariffs(params: RAListParams = Depends()):
    qs = Tariff.all().prefetch_related("prices")
    fmap = {
        "code": lambda q, v: q.filter(code__icontains=str(v)),
        "description": lambda q, v: q.filter(description__icontains=str(v)),
        "unit": lambda q, v: q.filter(unit__icontains=str(v)),
        "billing_type": lambda q, v: q.filter(billing_type__icontains=str(v)),
        # filter by operator NAME existing in prices
        "operator": lambda q, v: q.filter(prices__operator__icontains=str(v)),
        "active": lambda q, v: q.filter(active=bool(v)),
    }
    qs = apply_filter_map(qs, params.filters, fmap)
    order = parse_sort(params.sort, ["id", "code", "description", "unit", "billing_type", "active", "created_at", "updated_at"])
    # Use a local wrapper to ensure we emit operator_prices
    return await paginate_and_respond(qs, params.skip, params.limit, order, to_tariff_read)

@router.get("/{tariff_id}", response_model=TariffRead)
async def get_tariff(tariff_id: int):
    obj = await Tariff.get_or_none(id=tariff_id).prefetch_related("prices")
    if not obj:
        raise HTTPException(404, "Tariff not found")
    return respond_item(obj, to_tariff_read)

@router.post("", response_model=TariffRead, status_code=201)
async def create_tariff(payload: TariffCreate):
    data = payload.model_dump()
    operator_prices = (data.pop("operator_prices", None) or {})  # dict[str, float]
    obj = await Tariff.create(**data)
    # upsert prices
    for op_name, price in operator_prices.items():
        await TariffOperatorPrice.create(tariff=obj, operator=str(op_name), price=float(price))
    obj = await Tariff.get(id=obj.id).prefetch_related("prices")
    return respond_item(obj, to_tariff_read, status_code=201)

@router.put("/{tariff_id}", response_model=TariffRead)
async def update_tariff(tariff_id: int, payload: TariffUpdate):
    obj = await Tariff.get_or_none(id=tariff_id).prefetch_related("prices")
    if not obj:
        raise HTTPException(404, "Tariff not found")
    data = payload.model_dump(exclude_unset=True)
    operator_prices = data.pop("operator_prices", None)

    for k, v in data.items():
        setattr(obj, k, v)
    await obj.save()

    if operator_prices is not None:
        # replace or upsert each provided (keep the rest as-is)
        for op_name, price in operator_prices.items():
            existing = await TariffOperatorPrice.get_or_none(tariff=obj, operator=str(op_name))
            if existing:
                if existing.price != float(price):
                    existing.price = float(price)
                    await existing.save()
            else:
                await TariffOperatorPrice.create(tariff=obj, operator=str(op_name), price=float(price))

    obj = await Tariff.get(id=obj.id).prefetch_related("prices")
    return respond_item(obj, to_tariff_read)
