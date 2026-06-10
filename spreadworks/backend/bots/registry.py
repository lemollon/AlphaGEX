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
    # RIVER — SPY 0DTE Long (debit) Butterfly. The debit-paid sibling of
    # BREEZE: same gamma-magnet body thesis, but built as a single-type 1-2-1
    # long fly (auto-picks the cheaper OTM call vs put side) paid for with a
    # net debit. Defined risk = the debit. PT = % of max profit, SL = % of the
    # debit paid. Sized 50% BP uncapped like BREEZE/FLOW.
    "river": {
        "display": "RIVER",
        "strategy": "long_butterfly",
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": None,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": True,
            "max_contracts": 0,
            "bp_pct": 0.50,
            "sd_mult": 1.0,
            "pt_pct": 0.30,
            "sl_pct": 0.50,
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
    # UNDERTOW — single-leg long-call dip-buyer across an ETF + mega-cap
    # universe. Buys an ATM ~10-DTE call when a name pulls back >= 3% from its
    # 5-day high, oversold (RSI(2)<10) and still above its 20-day SMA. Exits
    # all-or-nothing: PT +40% / SL -50% of premium / 2-day time-stop / never
    # hold to expiry. Paper-only, ships disabled. dip/exit params live here in
    # `params` (swept later); only universal knobs sit in undertow_config.
    "undertow": {
        "display": "UNDERTOW",
        "strategy": "dip_buy",
        "ticker": "SPY",  # nominal; real scanning iterates `universe`
        "universe": ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "AMD", "META"],
        "front_dte": 10,
        "back_dte": None,
        "params": {
            "lookback_n": 5,
            "dip_threshold": 0.03,
            "use_rsi_confirm": True,
            "rsi_period": 2,
            "rsi_max": 10,
            "use_trend_gate": True,
            "sma_period": 20,
            "max_spread_pct": 0.15,
            "min_option_price": 0.20,
            "earnings_exclude_days": 3,
            "hold_days": 2,
        },
        "defaults": {
            "starting_capital": 25000.0,
            "enabled": False,
            "max_contracts": 10,
            "bp_pct": 0.02,
            "sd_mult": 1.0,
            "pt_pct": 0.40,
            "sl_pct": 0.50,
            "entry_start_ct": "08:35",
            "entry_end_ct": "14:30",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
            "max_concurrent_positions": 5,
        },
    },
    # MEADOW — SPY Credit Double Diagonal. The credit-side sibling of DRIFT:
    # sell the near-dated (6 DTE) strangle close to the money, buy a slightly-
    # longer-dated (9 DTE) strangle $5 further OTM, for a net credit. Short
    # vega, positive theta. Enters Mondays and Fridays only (entry_days gate).
    # Sized 50% BP uncapped like the other bots; PT=50% / SL=100% of credit.
    "meadow": {
        "display": "MEADOW",
        "strategy": "double_diagonal_credit",
        "ticker": "SPY",
        "front_dte": 6,
        "back_dte": 9,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": True,
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
            "entry_days": "mon,fri",
            # Open a fresh position on EVERY entry day (Mon/Fri) even if an
            # earlier one is still open — capped to one entry per entry-day by
            # the scanner. The other bots trade daily and stay one-at-a-time.
            "allow_stacking": True,
            # Hold at most 2 positions open at once (caps stacked collateral to
            # ~2x bp_pct of equity). 0 = unlimited.
            "max_concurrent_positions": 2,
        },
    },
}


def list_bots() -> list[str]:
    return list(BOT_REGISTRY.keys())


def get_bot(bot: str) -> dict[str, Any]:
    if bot not in BOT_REGISTRY:
        raise KeyError(f"Unknown bot: {bot!r}. Known: {sorted(BOT_REGISTRY)}")
    return BOT_REGISTRY[bot]
