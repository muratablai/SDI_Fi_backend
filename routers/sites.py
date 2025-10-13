# routers/sites.py
from fastapi import APIRouter, Depends, HTTPException
from tortoise.expressions import Q
from models import Site
from schemas import SiteCreate, SiteUpdate, SiteRead
from api_utils import RAListParams, parse_sort, apply_filter_map, paginate_and_respond, respond_item

router = APIRouter(prefix="/sites", tags=["sites"])

@router.get("", response_model=list[SiteRead])
async def list_sites(params: RAListParams = Depends()):
    qs = Site.all()
    fmap = {
        "code": lambda q, v: q.filter(code__icontains=str(v)),
        "name": lambda q, v: q.filter(name__icontains=str(v)),
        "city": lambda q, v: q.filter(city__icontains=str(v)),
        "county": lambda q, v: q.filter(county__icontains=str(v)),
    }
    qs = apply_filter_map(qs, params.filters, fmap)
    order = parse_sort(params.sort, ["id", "code", "name", "city", "county", "created_at", "updated_at"])
    return await paginate_and_respond(qs, params.skip, params.limit, order, lambda m: SiteRead.model_validate(m))

@router.get("/{site_id}", response_model=SiteRead)
async def get_site(site_id: int):
    obj = await Site.get_or_none(id=site_id)
    if not obj:
        raise HTTPException(404, "Site not found")
    return respond_item(obj, lambda m: SiteRead.model_validate(m))

@router.post("", response_model=SiteRead, status_code=201)
async def create_site(payload: SiteCreate):
    obj = await Site.create(**payload.model_dump())
    return respond_item(obj, lambda m: SiteRead.model_validate(m), status_code=201)

@router.put("/{site_id}", response_model=SiteRead)
async def update_site(site_id: int, payload: SiteUpdate):
    obj = await Site.get_or_none(id=site_id)
    if not obj:
        raise HTTPException(404, "Site not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await obj.save()
    return respond_item(obj, lambda m: SiteRead.model_validate(m))
