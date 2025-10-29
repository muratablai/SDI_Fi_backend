# routers/integration_admin.py
from __future__ import annotations
from fastapi import APIRouter, Body
from integration.azure_file_gateway import AzureFileGateway
from integration.msd_exporter import export_document
from integration.msd_poller import poll_outcomes
from services.config import (
    AZURE_FILES_ACCOUNT_NAME, AZURE_FILES_ACCOUNT_KEY, AZURE_FILES_SAS_URL,
    AZURE_FILES_SHARE, AZURE_FILES_BASE_DIR,
    MSD_DIR_LINES, MSD_DIR_PDFS, MSD_DIR_NUMBERS,
)

router = APIRouter(prefix="/integration/msd", tags=["integration-msd"])

def _gw() -> AzureFileGateway:
    return AzureFileGateway(
        account_name=AZURE_FILES_ACCOUNT_NAME,
        account_key=AZURE_FILES_ACCOUNT_KEY,
        sas_url=AZURE_FILES_SAS_URL,
        share_name=AZURE_FILES_SHARE,
        base_dir=AZURE_FILES_BASE_DIR,
    )

@router.post("/export")
async def export_doc(document_id: str = Body(..., embed=True)):
    gw = _gw()
    res = await export_document(document_id, gw, lines_dir=MSD_DIR_LINES, pdfs_dir=MSD_DIR_PDFS)
    return {"status": "ok", **res}

@router.post("/poll")
async def poll_now():
    gw = _gw()
    res = await poll_outcomes(gw, dir_lines=MSD_DIR_LINES, dir_pdfs=MSD_DIR_PDFS, dir_numbers=MSD_DIR_NUMBERS)
    return {"status": "ok", **res}
