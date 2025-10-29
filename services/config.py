# services/config.py
from __future__ import annotations
import os

# ===== MySQL (source ingestion) =====
MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER: str = os.getenv("MYSQL_USER", "mdc")
MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB: str = os.getenv("MYSQL_DB", "energy")

MYSQL_PROC_TV: str = os.getenv("MYSQL_PROC_TV", "FetchMeterData_v2")
MYSQL_PROC_SEGMENTS_BUCKETS: str = os.getenv("MYSQL_PROC_SEGMENTS_BUCKETS", "FetchMeterData_SegmentsBuckets_V2")

DEFAULT_BUCKET: str = os.getenv("ENERGY_BUCKET", "minute")
DEFAULT_MINUTE_BUCKET: int = int(os.getenv("ENERGY_MINUTE_BUCKET", "15"))

# Which meters the scheduler maintains
METER_NOS: list[str] = [m.strip() for m in os.getenv("METER_NOS", "").split(",") if m.strip()]

# ===== Azure File Share =====
AZURE_FILES_ACCOUNT_NAME = os.getenv("AZURE_FILES_ACCOUNT_NAME")
AZURE_FILES_ACCOUNT_KEY  = os.getenv("AZURE_FILES_ACCOUNT_KEY")
AZURE_FILES_SAS_URL      = os.getenv("AZURE_FILES_SAS_URL")   # prefer SAS
AZURE_FILES_SHARE        = os.getenv("AZURE_FILES_SHARE", "billing-share")
AZURE_FILES_BASE_DIR     = os.getenv("AZURE_FILES_BASE_DIR", "")  # optional root inside the share

# Directory layout (matches your description)
MSD_DIR_LINES   = "AVEVA2MSDInvoiceLines/RNEW"
MSD_DIR_PDFS    = "AVEVA2MSDInvoicePDF/RNEW"
MSD_DIR_NUMBERS = "MSD2AVEVAInvoiceNumbers/RNEW"
