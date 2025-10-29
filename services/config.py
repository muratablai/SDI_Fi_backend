# services/config.py
from __future__ import annotations
import os

# ------------------------------------------------------------------------------
# Helper: get env var with fallback
# ------------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default

# If you use python-dotenv, uncomment these two lines:
# from dotenv import load_dotenv
# load_dotenv()  # loads values from a local .env file if present

# ------------------------------------------------------------------------------
# MySQL (source ingestion)
# ------------------------------------------------------------------------------
# Fill these defaults to avoid "using password: NO" errors in dev.
MYSQL_HOST: str = _env("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT: int = int(_env("MYSQL_PORT", "3306"))
MYSQL_USER: str = _env("MYSQL_USER", "root")
MYSQL_PASSWORD: str = _env("MYSQL_PASSWORD", "Enevo123$")  # <-- put real password
MYSQL_DB: str = _env("MYSQL_DB", "mdc")

# Stored procedure names (as they exist in your MySQL)
MYSQL_PROC_TV: str = _env("MYSQL_PROC_TV", "FetchMeterData_v2")
MYSQL_PROC_SEGMENTS_BUCKETS: str = _env("MYSQL_PROC_SEGMENTS_BUCKETS", "FetchMeterData_SegmentsBuckets_V2")

# Default bucket settings for the energy endpoints that emulate the SP
DEFAULT_BUCKET: str = _env("ENERGY_BUCKET", "minute")
DEFAULT_MINUTE_BUCKET: int = int(_env("ENERGY_MINUTE_BUCKET", "15"))

# Which meters the scheduler maintains automatically (comma-separated env -> list)
METER_NOS: list[str] = [m.strip() for m in _env("METER_NOS", "").split(",") if m.strip()]

# ---------------- Azure File Share ----------------
# Prefer a connection string when you have one (like your test setup).
AZURE_FILES_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=https;AccountName=d365fointavevatest;AccountKey=K7fu+YWucgdokgn6X3nvTRQodFSx4t+gH0jNY4XddQdnktx7y1I3MflM5hnI/YM5TyCc0Ytd5Ffs+AStG+LOdA==;EndpointSuffix=core.windows.net"
)

# Fallbacks (used only if no connection string provided)

AZURE_FILES_SAS_URL = ""
AZURE_FILES_ACCOUNT_NAME = ""
AZURE_FILES_ACCOUNT_KEY = ""

AZURE_FILES_SHARE = "aveva"     # your file share name
AZURE_FILES_BASE_DIR = ""       # keep empty unless MSD put everything under a nested folder

# Partner directory layout
MSD_DIR_LINES: str   = _env("MSD_DIR_LINES",   "AVEVA2MSDInvoiceLines/RNEW")
MSD_DIR_PDFS: str    = _env("MSD_DIR_PDFS",    "AVEVA2MSDInvoicePDF/RNEW")
MSD_DIR_NUMBERS: str = _env("MSD_DIR_NUMBERS", "MSD2AVEVAInvoiceNumbers/RNEW")


# ---------------- CSV map (YAML) ----------------
# Absolute or relative path to the YAML mapping file above
CSV_MAP_FILE: str = _env("CSV_MAP_FILE", "config/msd_csv_map.yaml")

# Poll/export intervals are set in main via Scheduler; keep values there for clarity.
