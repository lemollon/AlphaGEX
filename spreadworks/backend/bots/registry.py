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
            # 2026-07-03 train(22-24)/holdout(25) sweep: quarter-Kelly sizing,
            # PT at 50% of max profit with NO stop (the combo is defined-risk;
            # a -50% stop on intraday marks was the live bleed), wing 1.15x
            # straddle (sd_mult 1.35 x 0.85), calendars +/- $2. ~+$52-58/day/lot
            # at half-spread fills, all years green incl 2023.
            "bp_pct": 0.10,
            "sd_mult": 1.35,
            "pt_pct": 0.50,
            # 1.0 was meant as "no stop" but decide_exit fires at -100% of
            # debit, and a missing leg quote can mark the 8-leg combo below
            # that (2026-07-07: closed at a NEGATIVE combo price for -$888).
            # 3.0 is unreachable — the TIDE fix. Risk stays capped at the
            # debit; the EOD close is the real exit.
            "sl_pct": 3.0,
            "drift_offset": 2,
            "entry_start_ct": "08:35",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
    # RIPPLE — full-size SPX version of the validated 0DTE fly (2026-07-09).
    # Strategy = the fly_bt.py sweep winner: wing sd 1.5 (~1.275x straddle,
    # debit ~0.395x wing, ~$2,000/lot), one morning entry, HOLD TO CASH
    # SETTLEMENT (the sweep found every early exit — 14:45 buyback, PT —
    # forfeits the edge at real fills; settle earned +$5..+$24/day/SPY-lot,
    # green 2022-25, holdout t=2.42). SPLASH runs the IDENTICAL strategy on
    # XSP at 1/10 size — the vehicle/sizing A/B, overlaid on one equity
    # chart (compare_with).
    # settle_at_expiry: the scanner never EOD-closes; the first scan AFTER
    # expiry settles at intrinsic vs the official close (SPXW is European
    # cash-settled, so this mirrors reality exactly — incl. 1:15pm ET
    # half-days, where a 14:45 CT buyback could never fill anyway).
    "ripple": {
        "display": "RIPPLE",
        "strategy": "long_butterfly",
        "ticker": "SPX",
        "front_dte": 0,
        "back_dte": None,
        "one_entry_per_day": True,
        "pt_ladder": False,
        "settle_at_expiry": True,
        "compare_with": "splash",
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": True,
            # 1 lot at ~$2,000 debit on $10k — already ~1.5x Kelly; the cap
            # keeps the A/B readable (same 1-lot-vs-1-lot daily bet).
            "max_contracts": 1,
            "bp_pct": 0.25,
            "sd_mult": 1.5,
            "pt_pct": 1.0,
            "sl_pct": 3.0,
            "entry_start_ct": "08:35",
            "entry_end_ct": "10:00",
            # eod_close_ct is unused for settle_at_expiry bots (kept for the
            # config UI); the position rides to cash settlement.
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
    # SPLASH — XSP (Mini-SPX) twin of RIPPLE (operator decision 2026-07-09):
    # the SAME winning strategy — 0DTE long fly, wing sd 1.5, one morning
    # entry, HOLD TO CASH SETTLEMENT — at 1/10 the contract size (~$200/lot
    # vs ~$2,000). XSP is European PM cash-settled like SPX, single OCC root
    # "XSP", $1 strikes. This is the "what a $10k account can actually
    # afford" vehicle; RIPPLE is the commission-efficient full-size SPX
    # version. The two overlay on one equity chart (compare_with) — same
    # strategy, different vehicle + sizing.
    # NOTE: paper fills at mids don't model XSP's wider real spreads or its
    # 10x per-dollar commission drag — the live A/B compares sizing and
    # tracking, not microstructure. (History: the v1 $500 pin+drift SPLASH
    # bricked 7/6-7/8 via phantom-SL/mark bugs; v2 traded SPX for one day;
    # autopsy + backtest in the vault/memory notes.)
    "splash": {
        "display": "SPLASH",
        "strategy": "long_butterfly",
        "ticker": "XSP",
        "front_dte": 0,
        "back_dte": None,
        # Backtest = one morning entry/day; the v1 bot churned 3 entries/day.
        "one_entry_per_day": True,
        # Static PT (unreachable at 1.0) — no intraday ladder; the fly_bt
        # sweep showed every early exit forfeits edge.
        "pt_ladder": False,
        # Never bought back: settles at intrinsic vs the official close on
        # the first scan after expiry (XSP European cash settlement; the
        # settlement helper falls back to SPX close / 10 if Tradier serves
        # no XSP daily history).
        "settle_at_expiry": True,
        "compare_with": "ripple",
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": True,
            # XSP fly debit ~$200/lot. bp 0.10 on $10k = ~$1,000/day budget
            # -> up to 5 lots: the affordable-sizing tier (~10% of account
            # at risk/day vs RIPPLE's 20% single SPX lot). Tune in Config.
            "max_contracts": 5,
            "bp_pct": 0.10,
            "sd_mult": 1.5,
            "pt_pct": 1.0,
            # 3.0 = unreachable, the TIDE lesson: a long fly can't lose more
            # than its debit, so a 1.0 "stop" only ever fires on garbage
            # intraday marks (that's what killed the $500 SPLASH and SURGE's
            # 7/7 -$888 trade).
            "sl_pct": 3.0,
            # Validated entry is the morning fill (9:35 ET). If no signal
            # builds by 10:00 CT, skip the day rather than take an
            # unvalidated afternoon entry.
            "entry_start_ct": "08:35",
            "entry_end_ct": "10:00",
            # Unused for settle_at_expiry bots (kept for the config UI).
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
            # sl_pct 1.0 -> 3.0 = effectively NO stop (hold to front expiry). A
            # backtest (examples/backtest_tide_stop.py) showed no stop level ever
            # beats holding to expiry: a long calendar can't lose more than its
            # debit, and the deepest EOD mark was only -0.72x debit, so the old
            # 1.0 stop only ever fired INTRADAY on violent days — selling at a
            # near-worthless mark that recovered by close (the live blowups).
            # 3.0 is unreachable, so TIDE rides to expiry; risk stays capped at
            # the debit. (2026-06-24)
            "sl_pct": 3.0,
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
    # UNDERTOW — directional debit vertical on LIQUID ETFs (SPY/QQQ/IWM).
    # Buys an ATM ~10-DTE vertical call debit spread when a name pulls back
    # >= 2% from its 5-day high, oversold (RSI(2)<35) and still above its
    # 20-day SMA. The spread_pct wing width limits max loss to the debit paid.
    # Exits: PT +60% / SL -40% of debit / 2-day time-stop. Paper-only, ships
    # disabled.
    #
    # Universe narrowed to ETFs 2026-06-23 after a real-EOD-chain backtest
    # (ThetaData 2020-2025): the mega-cap single names looked great at MID but
    # their wide bid/ask made the full 8-name basket NET NEGATIVE after
    # realistic slippage (-57% at worst-case fills). SPY/QQQ/IWM have tight
    # enough spreads to stay +EV: +46% even at full bid/ask, +91% at half-
    # spread. The 20-day TREND GATE is essential — removing it (the obvious
    # "trade more" lever) flips the basket to -21k. rsi_oversold 30->35 and
    # PT/SL 0.50/0.50 -> 0.60/0.40 both raised frequency AND worst-case EV.
    "undertow": {
        "display": "UNDERTOW",
        "strategy": "vertical_debit",
        "vertical_mode": "debit",
        "ticker": "SPY",  # nominal; real scanning iterates `universe`
        "universe": ["SPY", "QQQ", "IWM"],
        "front_dte": 10,
        "back_dte": None,
        "params": {
            "lookback_n": 5, "dip_threshold": 0.02,
            "rsi_period": 2, "rsi_oversold": 35, "rsi_overbought": 65,
            "use_rsi_confirm": True, "use_trend_gate": True, "sma_period": 20,
            "spread_pct": 0.04, "max_spread_pct": 0.15, "min_option_price": 0.20,
            "earnings_exclude_days": 3, "hold_days": 2,
        },
        "defaults": {
            "starting_capital": 25000.0,
            "enabled": True,
            "max_contracts": 10,
            "bp_pct": 0.05,
            "sd_mult": 1.0,
            "pt_pct": 0.60,
            "sl_pct": 0.40,
            "entry_start_ct": "08:35",
            "entry_end_ct": "14:30",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
            "max_concurrent_positions": 5,
        },
    },
    # DELTA — directional credit spreads on LIQUID ETFs (SPY/QQQ/IWM). Sells a
    # put credit spread on the bullish (oversold-dip) setup and a call credit
    # spread on the bearish (overbought-rip) setup. Defined risk = width-credit.
    # Paper-only, ships disabled.
    #
    # Same 2026-06-23 real-chain backtest as UNDERTOW: ETF-only is +EV at every
    # fill (+10% worst-case / +18% mid over 2020-2025); the full 8-name basket
    # was -15% after slippage. Trend gate kept (removing it -> -EV). Two changes
    # unlocked the edge: rsi 30/70 -> 40/60 (more setups) and, critically,
    # bp_pct 0.05 -> 0.15 — the old 5% budget was too small for a credit
    # spread's (width-credit) defined risk, so it hit sizing_below_one and
    # almost never traded. At bp 0.15 it sizes properly: worst-case P&L 4.6x
    # baseline (+$2.5k -> +$11.6k). NOTE: 0.15 x up-to-5 concurrent ~= 75% of
    # equity deployed — aggressive by design (operator-approved 2026-06-23).
    "delta": {
        "display": "DELTA",
        "strategy": "vertical_credit",
        "vertical_mode": "credit",
        "ticker": "SPY",
        "universe": ["SPY", "QQQ", "IWM"],
        "front_dte": 10,
        "back_dte": None,
        "params": {
            "lookback_n": 5, "dip_threshold": 0.02,
            "rsi_period": 2, "rsi_oversold": 40, "rsi_overbought": 60,
            "use_rsi_confirm": True, "use_trend_gate": True, "sma_period": 20,
            "short_otm_pct": 0.03, "spread_pct": 0.04, "max_spread_pct": 0.15,
            "min_option_price": 0.20, "min_credit": 0.20,
            "earnings_exclude_days": 3, "hold_days": 2,
        },
        "defaults": {
            "starting_capital": 25000.0, "enabled": True, "max_contracts": 10,
            "bp_pct": 0.15, "sd_mult": 1.0, "pt_pct": 0.50, "sl_pct": 1.5,
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
