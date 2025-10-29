# integration/azure_diag.py
from __future__ import annotations
from typing import Dict, List
from integration.azure_file_gateway import AzureFileGateway, FileInfo
from services import config

MSD_PATHS_TO_CHECK = [
    "",  # root of the share
    "AVEVA2MSDInvoiceLines/RNEW/Source",
    "AVEVA2MSDInvoiceLines/RNEW/Processed",
    "AVEVA2MSDInvoiceLines/RNEW/Error",
    "AVEVA2MSDInvoicePDF/RNEW/Source",
    "AVEVA2MSDInvoicePDF/RNEW/Processed",
    "AVEVA2MSDInvoicePDF/RNEW/Error",
    "MSD2AVEVAInvoiceNumbers/RNEW/Processed",
    "MSD2AVEVAInvoiceNumbers/RNEW/Source",
]

def _gateway() -> AzureFileGateway:
    return AzureFileGateway(
        connection_string=(config.AZURE_FILES_CONNECTION_STRING or None),
        account_name=(config.AZURE_FILES_ACCOUNT_NAME or None),
        account_key=(config.AZURE_FILES_ACCOUNT_KEY or None),
        sas_url=(config.AZURE_FILES_SAS_URL or None),
        share_name=config.AZURE_FILES_SHARE,
        base_dir=config.AZURE_FILES_BASE_DIR,
    )

def _summarize(files: List[FileInfo], sample_bytes_checked: int) -> Dict:
    return {
        "count": len(files),
        "total_bytes": sum(f.size or 0 for f in files),
        "sample_read_bytes": sample_bytes_checked,
        "examples": [f.name for f in files[:5]],
    }

def _read_samples(gw: AzureFileGateway, path: str, files: List[FileInfo], max_files: int, head_bytes: int) -> int:
    checked = 0
    for f in files[:max_files]:
        try:
            _ = gw.read_head(path, f.name, nbytes=head_bytes)
            checked += head_bytes
        except Exception:
            # ignore individual file failures; caller will see in summary
            pass
    return checked

def run_connectivity_check(max_files_per_dir: int = 3, head_bytes: int = 256) -> Dict:
    result = {"ok": True, "paths": {}, "errors": []}
    try:
        gw = _gateway()
    except Exception as e:
        return {"ok": False, "paths": {}, "errors": [f"Auth/init error: {e}"]}

    for path in MSD_PATHS_TO_CHECK:
        path_info = {"exists": False, "count": 0, "total_bytes": 0, "sample_read_bytes": 0, "examples": []}
        exists, why = gw.exists(path)
        path_info["exists"] = exists
        if not exists:
            result["ok"] = False
            result["errors"].append(f"{path or '<root>'}: {why}")
            result["paths"][path] = path_info
            continue

        try:
            files = gw.list_files(path)
            path_info.update(_summarize(files, 0))
            path_info["sample_read_bytes"] = _read_samples(gw, path, files, max_files_per_dir, head_bytes)
        except Exception as e:
            result["ok"] = False
            result["errors"].append(f"{path or '<root>'}: {e}")
        result["paths"][path] = path_info

    return result
