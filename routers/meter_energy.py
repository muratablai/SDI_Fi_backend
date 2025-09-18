# routers/meter_energy.py
from __future__ import annotations
import os, json
from typing import List, Literal, Any, Callable

from fastapi import APIRouter, Depends, Request, HTTPException
from tortoise import Tortoise

from models import Meter, User
from deps import get_current_active_user
from api_utils import RAListParams, respond_plain_list

router = APIRouter(prefix="/meter-data/energy", tags=["meter-energy"])

Granularity = Literal["hour", "day", "month", "year"]
ALLOWED_SORTS = {"bucket_start", "energy", "meter_no", "id"}
PROC_ENV_NAME = "METER_ENERGY_PROC"  # optional: name of DB proc/function

def _dialect() -> str:
    conn = Tortoise.get_connection("default")
    d = getattr(getattr(conn, "capabilities", None), "dialect", None)
    return (d or conn.__class__.__name__).lower()

async def _resolve_meter_no(filters: dict) -> str | None:
    if filters.get("meter_no"):
        return str(filters["meter_no"])
    if filters.get("meter_id") is not None:
        m = await Meter.get_or_none(id=filters["meter_id"])
        if not m:
            # if an id is passed but doesn't exist, behave like "no selection"
            return None
        return m.meter_no
    return None

def _bucket_sql(dialect: str, gran: Granularity) -> tuple[str, str]:
    # returns (bucket_expr, order_expr)
    if dialect.startswith("postgres"):
        if gran == "hour":  return ("date_trunc('hour',  timestamp)", "date_trunc('hour',  timestamp)")
        if gran == "day":   return ("date_trunc('day',   timestamp)", "date_trunc('day',   timestamp)")
        if gran == "month": return ("date_trunc('month', timestamp)", "date_trunc('month', timestamp)")
        return ("date_trunc('year',  timestamp)", "date_trunc('year',  timestamp)")
    if dialect.startswith("mysql"):
        if gran == "hour":  return ("DATE_FORMAT(timestamp, '%Y-%m-%d %H:00:00')", "DATE_FORMAT(timestamp, '%Y-%m-%d %H:00:00')")
        if gran == "day":   return ("DATE(timestamp)", "DATE(timestamp)")
        if gran == "month": return ("DATE_FORMAT(timestamp, '%Y-%m-01')", "DATE_FORMAT(timestamp, '%Y-%m-01')")
        return ("DATE_FORMAT(timestamp, '%Y-01-01')", "DATE_FORMAT(timestamp, '%Y-01-01')")
    # sqlite fallback
    if gran == "hour":  return ("strftime('%Y-%m-%dT%H:00:00Z', timestamp)", "strftime('%Y-%m-%dT%H', timestamp)")
    if gran == "day":   return ("strftime('%Y-%m-%dT00:00:00Z', timestamp)", "strftime('%Y-%m-%d', timestamp)")
    if gran == "month": return ("strftime('%Y-%m-01T00:00:00Z', timestamp)", "strftime('%Y-%m', timestamp)")
    return ("strftime('%Y-01-01T00:00:00Z', timestamp)", "strftime('%Y', timestamp)")

@router.get("", response_model=List[dict])
async def list_energy(
    request: Request,
    params: RAListParams = Depends(),
    user: User = Depends(get_current_active_user),
):
    # be forgiving with missing params
    filters = dict(params.filters or {})
    gran: str = str(filters.get("granularity") or "day").lower()
    if gran not in {"hour", "day", "month", "year"}:
        gran = "day"

    meter_no = await _resolve_meter_no(filters)
    # if no meter selected yet, return an empty page (so RA UI stays happy)
    if not meter_no:
        return respond_plain_list([], params.skip, params.limit)

    date_from = filters.get("date_gte")
    date_to   = filters.get("date_lte")

    conn     = Tortoise.get_connection("default")
    dialect  = _dialect()
    procname = os.getenv(PROC_ENV_NAME, "").strip()

    # ---- Stored procedure / function path (optional) ----
    if procname and (dialect.startswith("postgres") or dialect.startswith("mysql")):
        if dialect.startswith("postgres"):
            sql = f"SELECT * FROM {procname}($1,$2,$3,$4)"
            rows = await conn.execute_query_dict(sql, [meter_no, gran, date_from, date_to])
        else:
            sql = f"CALL {procname}(%s,%s,%s,%s)"
            rows = await conn.execute_query_dict(sql, [meter_no, gran, date_from, date_to])

        # normalize
        norm = []
        for r in rows:
            b = r.get("bucket_start") or r.get("bucket") or r.get("bucket_start_ts")
            e = r.get("energy") or r.get("sum_energy") or r.get("value")
            norm.append({
                "id": str(b),
                "bucket_start": b,
                "meter_no": meter_no,
                "energy": float(e or 0),
            })
        # client sort (optional)
        try:
            sort_field, sort_order = json.loads(params.sort)
            reverse = str(sort_order).upper() == "DESC"
            if sort_field in ALLOWED_SORTS:
                norm.sort(key=lambda x: x[sort_field], reverse=reverse)
        except Exception:
            pass
        return respond_plain_list(norm, params.skip, params.limit)

    # ---- SQL fallback path ----
    bucket_expr, order_expr = _bucket_sql(dialect, gran)
    if dialect.startswith("postgres"):
        base = f"""
            SELECT {bucket_expr} AS bucket_start, SUM(fa) AS energy
            FROM meterdata
            WHERE meter_no = $1
              { "AND timestamp >= $2" if date_from else "" }
              { "AND timestamp <= $3" if date_to   else "" }
            GROUP BY 1
            ORDER BY {order_expr} ASC
        """
        args = [meter_no]
        if date_from: args.append(date_from)
        if date_to:   args.append(date_to)
        rows = await conn.execute_query_dict(base, args)
    elif dialect.startswith("mysql"):
        base = f"""
            SELECT {bucket_expr} AS bucket_start, SUM(fa) AS energy
            FROM meterdata
            WHERE meter_no = %s
              { "AND timestamp >= %s" if date_from else "" }
              { "AND timestamp <= %s" if date_to   else "" }
            GROUP BY 1
            ORDER BY {order_expr} ASC
        """
        args = [meter_no]
        if date_from: args.append(date_from)
        if date_to:   args.append(date_to)
        rows = await conn.execute_query_dict(base, args)
    else:
        # sqlite
        base = f"""
            SELECT {bucket_expr} AS bucket_start, SUM(fa) AS energy
            FROM meterdata
            WHERE meter_no = ?
              { "AND timestamp >= ?" if date_from else "" }
              { "AND timestamp <= ?" if date_to   else "" }
            GROUP BY 1
            ORDER BY {order_expr} ASC
        """
        args = [meter_no]
        if date_from: args.append(date_from)
        if date_to:   args.append(date_to)
        rows = await conn.execute_query_dict(base, args)

    items = [{
        "id": str(r["bucket_start"]),
        "bucket_start": r["bucket_start"],
        "meter_no": meter_no,
        "energy": float(r["energy"] or 0),
    } for r in rows]

    # optional client sort
    try:
        sort_field, sort_order = json.loads(params.sort)
        reverse = str(sort_order).upper() == "DESC"
        if sort_field in ALLOWED_SORTS:
            items.sort(key=lambda x: x[sort_field], reverse=reverse)
    except Exception:
        pass

    return respond_plain_list(items, params.skip, params.limit)
