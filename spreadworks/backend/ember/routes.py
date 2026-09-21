"""Read-only operator status for the complete EMBER strategy fleet."""

from fastapi import APIRouter

from .astra_runtime import read_status as read_astra_status
from .fleet_runtime import read_status as read_fleet_status
from .runtime import read_status as read_xsp_status


router = APIRouter(tags=["EMBER"])


@router.get("/api/spreadworks/ember/xsp/status")
def ember_xsp_status():
    return read_xsp_status()


@router.get("/api/spreadworks/ember/status")
def ember_fleet_status():
    return {"strategies": [
        {"strategy": "xsp_flow", "runtime": "render", **read_xsp_status()},
        {"strategy": "astra3_live", **read_astra_status()},
    ] + read_fleet_status()}
