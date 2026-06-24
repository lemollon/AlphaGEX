"""Single source of truth for bot identity + config defaults.

When changing this file, mirror updates in
`spreadworks/frontend/src/lib/botRegistry.js`.
"""
from __future__ import annotations

from typing import Any

BOT_REGISTRY: dict[str, dict[str, Any]] = {
    # SURGE — SPY 0DTE/1DTE Pin+Drift Combo. The best structure from real-
    # fill (ThetaData 2022-25) backtesting: RIVER's long butterfly (wins on a
    # pin) PLUS two cheap 0DTE/1DTE calendars `drift_offset` either side of the
    # body (win when price drifts there). ~+$24/day/lot at realistic fills, ~52%
    # win, green every year. Replaces BREEZE (which was just RIVER's pin bet in a
    # credit costume — economically redundant). front=0DTE fly+near calendars,
    # back=1DTE calendar far legs. Shipped LIVE (paper, like RIVER) 2026-06-24.
    "surge": {
        "display": "SURGE",
        "strategy": "pin_drift_combo",
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": 1,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": True,
            "max_contracts": 0,
            "bp_pct": 0.50,
            "sd_mult": 1.0,
            "pt_pct": 0.30,
            "sl_pct": 0.50,
            # Calendars sit this many dollars either side of the body (validated
            # sweet spot from the real-fill sweep was +/- $3).
            "drift_offset": 3,
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
        # Front 1->7 / back 14->30 (was 1/14). The 1DTE front was a gamma bomb:
        # its loss on a move accelerated far faster than the 14DTE back's vega
        # could compensate. A 7/30 calendar is far steadier and ~2x the EV in
        # the warehouse backtest (2026-06-24); move-day blowups traced to the
        # ultra-short front + too-close strikes (see strike_mult).
        "front_dte": 7,
        "back_dte": 30,
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
            # Strike placement = spot +/- strike_mult * front-straddle. Widened
            # 1.0->1.5 after the backtest: at 1.0 the strikes sat right where a
            # day's move lands, so >1-straddle moves blew through the short.
            # 1.5 flips move days from -$45/trade to +$103/trade and halves the
            # catastrophic tail (worst -$447 vs -$610), held to expiry.
            "strike_mult": 1.5,
            # Vega-edge gate. Set 0.0 (mild "back not cheaper than front") after
            # the 2026-06-24 warehouse backtest REFUTED the contango thesis: the
            # 0.3 gate halved trades without improving P&L, and backwardation
            # days performed best. EOD data even favored no gate; 0.0 is the
            # conservative pick pending a real-fill morning-entry backtest.
            "min_vega_edge": 0.0,
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
    # RIVER (long butterfly) removed 2026-06-24 — superseded by SURGE, whose
    # butterfly leg IS RIVER's; running both just doubled the pin exposure. The
    # long_butterfly strategy + payoff model are retained (used by SURGE's body
    # logic conceptually and still unit-tested) but no bot trades it standalone.
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
    # UNDERTOW — directional debit vertical across an ETF + mega-cap universe.
    # Buys an ATM ~10-DTE vertical call debit spread when a name pulls back
    # >= 3% from its 5-day high, oversold (RSI(2)<10) and still above its
    # 20-day SMA. The spread_pct wing width limits max loss to the debit paid.
    # Exits: PT +50% / SL -50% of debit / 2-day time-stop. Paper-only, ships
    # disabled. dip/spread params live here in `params`; universal knobs sit
    # in undertow_config.
    "undertow": {
        "display": "UNDERTOW",
        "strategy": "vertical_debit",
        "vertical_mode": "debit",
        "ticker": "SPY",  # nominal; real scanning iterates `universe`
        "universe": ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "AMD", "META"],
        "front_dte": 10,
        "back_dte": None,
        "params": {
            # Loosened 2026-06-18: RSI(2) < 10 + 3% dip almost never aligned
            # (real 4-6% dips like AMD/META sat at RSI 11-17). Eased to
            # rsi_oversold 30 / rsi_overbought 70 / dip 2% so genuine
            # pullbacks-in-uptrend actually fire. Trend gate kept.
            "lookback_n": 5, "dip_threshold": 0.02,
            "rsi_period": 2, "rsi_oversold": 30, "rsi_overbought": 70,
            "use_rsi_confirm": True, "use_trend_gate": True, "sma_period": 20,
            "spread_pct": 0.04, "max_spread_pct": 0.15, "min_option_price": 0.20,
            "earnings_exclude_days": 3, "hold_days": 2,
        },
        "defaults": {
            "starting_capital": 25000.0,
            "enabled": False,
            "max_contracts": 10,
            "bp_pct": 0.05,
            "sd_mult": 1.0,
            "pt_pct": 0.50,
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
    # DELTA — directional credit spreads on the UNDERTOW universe. Sells a put
    # credit spread on the bullish (oversold-dip) setup and a call credit spread
    # on the bearish (overbought-rip) setup. Defined risk = width - credit.
    # Paper-only, ships disabled.
    "delta": {
        "display": "DELTA",
        "strategy": "vertical_credit",
        "vertical_mode": "credit",
        "ticker": "SPY",
        "universe": ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "AMD", "META"],
        "front_dte": 10,
        "back_dte": None,
        "params": {
            # Loosened 2026-06-18 in lockstep with UNDERTOW (shared universe /
            # setup gates): rsi_oversold 30 / rsi_overbought 70 / dip 2% so the
            # credit-spread setups actually trigger. Trend gate kept.
            "lookback_n": 5, "dip_threshold": 0.02,
            "rsi_period": 2, "rsi_oversold": 30, "rsi_overbought": 70,
            "use_rsi_confirm": True, "use_trend_gate": True, "sma_period": 20,
            "short_otm_pct": 0.03, "spread_pct": 0.04, "max_spread_pct": 0.15,
            "min_option_price": 0.20, "min_credit": 0.20,
            "earnings_exclude_days": 3, "hold_days": 2,
        },
        "defaults": {
            "starting_capital": 25000.0, "enabled": False, "max_contracts": 10,
            "bp_pct": 0.05, "sd_mult": 1.0, "pt_pct": 0.50, "sl_pct": 1.5,
            "entry_start_ct": "08:35", "entry_end_ct": "14:30", "eod_close_ct": "14:45",
            "discord_alerts": False, "delta_skew": 0, "use_gex_walls": False,
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
