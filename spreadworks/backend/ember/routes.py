"""Read-only operator status for the complete EMBER strategy fleet."""

from fastapi import APIRouter

from .astra_runtime import read_status as read_astra_status
from .fleet_runtime import read_status as read_fleet_status
from .pnl import aggregate_pnl
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


@router.get("/api/spreadworks/ember/pnl")
def ember_fleet_pnl():
    """Combined realized ($) P&L across the complete 7-strategy fleet. See
    pnl.py's module docstring for where each strategy's number actually
    comes from and which strategies have no ledger yet."""
    return aggregate_pnl()
