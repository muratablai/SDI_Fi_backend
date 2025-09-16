import json
from typing import Any, Callable, Dict, Iterable, List, Tuple

from fastapi import Query
from fastapi.responses import JSONResponse
from tortoise.queryset import QuerySet

# ---------- React-Admin param parsing ----------

def parse_range(range_param: str) -> tuple[int, int, int]:
    """
    range: '["start","end"]' or '[0,9]' → returns (skip, limit, start)
    """
    start, end = json.loads(range_param)
    skip = int(start)
    limit = int(end) - skip + 1
    return skip, limit, start

def parse_sort(sort_param: str, allowed_fields: Iterable[str]) -> str:
    """
    sort: '["field","ASC|DESC"]' → returns tortoise order_by string.
    Unknown fields fallback to 'id'.
    """
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

def apply_filter_map(qs: QuerySet, filters: Dict[str, Any], fmap: Dict[str, Callable[[QuerySet, Any], QuerySet]]) -> QuerySet:
    """
    Applies filters using a key→callable map. Each callable receives (qs, value) and must return qs.
    """
    for key, fn in fmap.items():
        if key in filters and filters[key] is not None:
            qs = fn(qs, filters[key])
    return qs

async def paginate_and_respond(qs: QuerySet, skip: int, limit: int, order: str, to_pydantic: Callable[[Any], Any]) -> JSONResponse:
    total = await qs.count()
    items = await qs.order_by(order).offset(skip).limit(limit)
    end_real = skip + max(len(items) - 1, 0)
    content_range = f"items {skip}-{end_real}/{total}"
    content = [to_pydantic(it).model_dump() for it in items]
    return JSONResponse(status_code=206, content=content, headers={"Content-Range": content_range})

# ---------- Dependency container for RA list params (optional use) ----------

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
