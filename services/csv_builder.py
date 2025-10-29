# services/csv_builder.py
from __future__ import annotations
from typing import List, Any
import csv, io, os, datetime, decimal, json, importlib

from models import BillingDocument, BillingLine
import services.config as config
import yaml  # pip install pyyaml

def _get_attr_path(root: Any, path: str):
    cur = root
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur

def _fmt_value(val: Any, col_cfg: dict) -> Any:
    if val is None:
        return col_cfg.get("default", "")
    # date formatting
    if "date_format" in col_cfg:
        # support datetime/date/str
        if isinstance(val, (datetime.datetime, datetime.date)):
            return val.strftime(col_cfg["date_format"])
        # try parse ISO string
        try:
            dt = datetime.datetime.fromisoformat(str(val).replace("Z",""))
            return dt.strftime(col_cfg["date_format"])
        except Exception:
            return str(val)

    # numeric scaling/rounding
    if isinstance(val, (int, float, decimal.Decimal)):
        x = decimal.Decimal(str(val))
        if "scale" in col_cfg:
            x = x * decimal.Decimal(str(col_cfg["scale"]))
        if "round" in col_cfg:
            q = decimal.Decimal(10) ** (-int(col_cfg["round"]))
            x = x.quantize(q, rounding=decimal.ROUND_HALF_UP)
        # keep as plain string to avoid locale issues
        return format(x, "f")

    # booleans → lowercase strings (common for CSVs)
    if isinstance(val, bool):
        return "true" if val else "false"

    return str(val)

def _load_map() -> dict:
    path = config.CSV_MAP_FILE
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    # fallback minimal map
    return {
        "delimiter": ",",
        "quotechar": '"',
        "mode": "line",
        "header": ["Line No","Meter","Tariff","Unit","Quantity","Unit Price (cents)","VAT %","Amount (cents)"],
        "columns": [
            {"name":"Line No","source":"line.export_seq"},
            {"name":"Meter","source":"line.meter_no"},
            {"name":"Tariff","source":"line.tariff_code"},
            {"name":"Unit","source":"line.unit","default":"kWh"},
            {"name":"Quantity","source":"line.quantity","round":6},
            {"name":"Unit Price (cents)","source":"line.unit_price_cents"},
            {"name":"VAT %","source":"line.vat_rate_percent","round":2},
            {"name":"Amount (cents)","source":"line.amount_cents"},
        ],
    }

async def build_csv_bytes(doc: BillingDocument, lines: List[BillingLine]) -> bytes:
    cfg = _load_map()
    delimiter = cfg.get("delimiter", ",")
    quotechar = cfg.get("quotechar", '"')
    header = cfg.get("header", [])
    cols = cfg.get("columns", [])
    mode = cfg.get("mode", "line")

    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=delimiter, quotechar=quotechar)

    if header:
        writer.writerow(header)

    if mode == "line":
        # ensure export_seq is set 1..N if missing
        seq = 1
        for ln in lines:
            if ln.export_seq is None:
                ln.export_seq = seq
                seq += 1
        # persist any newly assigned seqs
        await BillingLine.bulk_update([ln for ln in lines if ln.export_seq is not None], fields=["export_seq"])

        for ln in lines:
            row = []
            for c in cols:
                src = c.get("source", "")
                # route source to document/line root
                if src.startswith("document."):
                    val = _get_attr_path(doc, src[len("document."):])
                elif src.startswith("line."):
                    val = _get_attr_path(ln, src[len("line."):])
                elif src:  # raw literal path (rare)
                    val = _get_attr_path({"document": doc, "line": ln}, src)
                else:
                    val = None
                row.append(_fmt_value(val, c))
            writer.writerow(row)
    else:
        # other modes could be added later
        raise NotImplementedError(f"CSV build mode '{mode}' not implemented")

    return out.getvalue().encode("utf-8")
