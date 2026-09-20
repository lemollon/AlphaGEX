"""Read-only operator status for EMBER's XSP sleeve."""

from fastapi import APIRouter

from .runtime import read_status


router = APIRouter(tags=["EMBER"])


@router.get("/api/spreadworks/ember/xsp/status")
def ember_xsp_status():
    return read_status()
