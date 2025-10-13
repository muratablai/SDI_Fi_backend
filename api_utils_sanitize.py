# app/api_utils_sanitize.py
from __future__ import annotations
from typing import Iterable, Sequence, Any, Mapping
from fastapi import HTTPException
from tortoise.models import Model
from tortoise.queryset import QuerySet

# --- Core materializers ------------------------------------------------------

async def qs_to_list(
    qs: QuerySet[Model],
    fields: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Materialize a Tortoise QuerySet into a list of plain dicts using .values(...).
    Never returns a QuerySet.
    """
    if fields:
        rows = await qs.values(*fields)
    else:
        rows = await qs.values()
    return list(rows)

async def get_one_as_dict(
    qs: QuerySet[Model],
    fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Fetch exactly one row (by filtering before calling), returned as a dict.
    404 if missing.
    """
    if fields:
        row = await qs.values(*fields).first()
    else:
        row = await qs.values().first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row

def ensure_plain(value: Any) -> Any:
    """
    Last-resort guard. If someone passes model/queryset by mistake, explode early
    with a clear error instead of letting FastAPI encoder crash later.
    """
    if isinstance(value, QuerySet) or isinstance(value, Model):
        raise RuntimeError(
            "Unsafe return value detected (Model/QuerySet). Use qs_to_list()/get_one_as_dict()/Pydantic DTO."
        )
    if isinstance(value, Mapping):
        # dict is fine, but block nested QuerySets/Models
        for v in value.values():
            if isinstance(v, (QuerySet, Model)):
                raise RuntimeError(
                    "Unsafe nested Model/QuerySet in dict. Flatten or convert to IDs/DTOs."
                )
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, dict)):
        for v in value:
            if isinstance(v, (QuerySet, Model)):
                raise RuntimeError(
                    "Unsafe Model/QuerySet inside list. Use qs_to_list()/DTO first."
                )
    return value
