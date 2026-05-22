"""Single source of truth for bot identity + config defaults.

When changing this file, mirror updates in
`spreadworks/frontend/src/lib/botRegistry.js`.
"""
from __future__ import annotations

from typing import Any

BOT_REGISTRY: dict[str, dict[str, Any]] = {
    "breeze": {
        "display": "BREEZE",
        "strategy": "iron_butterfly",
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": None,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,
            # Deploy 50% of the account, uncapped (max_contracts=0), matching
            # FLOW. Sizing = floor((equity * bp_pct) / max_loss_per_contract).
            "max_contracts": 0,
            "bp_pct": 0.50,
            "sd_mult": 1.0,
            "pt_pct": 0.30,
            "sl_pct": 2.0,
            "entry_start_ct": "08:35",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
    "tide": {
        "display": "TIDE",
        "strategy": "double_calendar",
        "ticker": "SPY",
        "front_dte": 1,
        "back_dte": 14,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,
            # Deploy 50% of the account, uncapped (max_contracts=0), matching
            # FLOW. Sizing = floor((equity * bp_pct) / max_loss_per_contract).
            "max_contracts": 0,
            "bp_pct": 0.50,
            "sd_mult": 1.0,
            "pt_pct": 0.50,
            "sl_pct": 1.0,
            "entry_start_ct": "08:35",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
    "drift": {
        "display": "DRIFT",
        "strategy": "double_diagonal",
        "ticker": "SPY",
        "front_dte": 1,
        "back_dte": 14,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,
            # Deploy 50% of the account, uncapped (max_contracts=0), matching
            # FLOW. Sizing = floor((equity * bp_pct) / max_loss_per_contract).
            "max_contracts": 0,
            "bp_pct": 0.50,
            "sd_mult": 1.0,
            "pt_pct": 0.50,
            "sl_pct": 1.0,
            "entry_start_ct": "08:35",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
    # FLOW — SPY 1DTE Iron Condor. Ported from IronForge SPARK criteria:
    # SD=1.2, $5 wings, PT=30% of max profit, SL=50% of max profit, VIX<=32,
    # entry 08:30-14:00 CT, EOD close 14:45. max_contracts=0 means "size by
    # BP only" (no contract ceiling), mirroring SPARK's Kelly-but-uncapped
    # paper-account behavior.
    "flow": {
        "display": "FLOW",
        "strategy": "iron_condor",
        "ticker": "SPY",
        "front_dte": 1,
        "back_dte": None,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,
            "max_contracts": 0,
            "bp_pct": 0.50,
            "sd_mult": 1.2,
            "pt_pct": 0.30,
            "sl_pct": 0.50,
            "entry_start_ct": "08:30",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
}


def list_bots() -> list[str]:
    return list(BOT_REGISTRY.keys())


def get_bot(bot: str) -> dict[str, Any]:
    if bot not in BOT_REGISTRY:
        raise KeyError(f"Unknown bot: {bot!r}. Known: {sorted(BOT_REGISTRY)}")
    return BOT_REGISTRY[bot]
