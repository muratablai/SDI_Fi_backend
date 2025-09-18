# api_utils.py
import json
from typing import Any, Callable, Iterable
from fastapi import Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from tortoise.queryset import QuerySet

# ---------- React-Admin param parsing ----------
def parse_range(range_param: str) -> tuple[int, int, int]:
    start, end = json.loads(range_param)
    skip = int(start)
    limit = int(end) - skip + 1
    return skip, limit, start

def parse_sort(sort_param: str, allowed_fields: Iterable[str]) -> str:
    try:
        field, order = json.loads(sort_param)
    except Exception:
        field, order = ("id", "ASC")
    field = field if field in set(allowed_fields) else "id"
    prefix = "-" if str(order).upper() == "DESC" else ""
    return f"{prefix}{field}"

def parse_filter(filter_param: str | None) -> dict:
    try:
        return json.loads(filter_param or "{}")
    except Exception:
        return {}

# ---------- Query helpers ----------
def apply_filter_map(qs: QuerySet, filters: dict, fmap: dict[str, Callable[[QuerySet, Any], QuerySet]]) -> QuerySet:
    for key, fn in fmap.items():
        if key in filters and filters[key] is not None:
            qs = fn(qs, filters[key])
    return qs

async def paginate_and_respond(
    qs,
    skip: int,
    limit: int,
    order: str,
    to_pydantic: Callable[[Any], Any],
) -> JSONResponse:
    total = await qs.count()
    items = await qs.order_by(order).offset(skip).limit(limit)
    end_real = skip + max(len(items) - 1, 0)
    content_range = f"items {skip}-{end_real}/{total}"

    # 🔐 Robust UUID/datetime-safe encoding:
    # 1) to Pydantic model
    # 2) model_dump_json() -> JSON string using Pydantic’s encoder (UUID->str, datetime->iso)
    # 3) json.loads back to dict so JSONResponse can render the whole list
    content = [json.loads(to_pydantic(it).model_dump_json()) for it in items]

    return JSONResponse(
        status_code=206,
        content=content,
        headers={"Content-Range": content_range},
    )

# ---------- Plain list responder (used by aggregated energy endpoint) ----------
def respond_plain_list(items: list[dict], skip: int, limit: int) -> JSONResponse:
    total = len(items)
    page = items[skip : skip + limit]
    end_real = skip + max(len(page) - 1, 0)
    content_range = f"items {skip}-{end_real}/{total}"
    return JSONResponse(
        status_code=206,
        content=jsonable_encoder(page),
        headers={"Content-Range": content_range},
    )

# ---------- Optional RA params container ----------
class RAListParams:
    def __init__(
        self,
        range: str = Query("[0,9]"),
        sort: str = Query('["id","ASC"]'),
        filter: str = Query("{}"),
    ):
        self.skip, self.limit, self.start = parse_range(range)
        self.filters = parse_filter(filter)
        self.sort = sort
