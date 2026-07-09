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
    # RIPPLE — SPLASH's A/B twin (added 2026-07-09): SAME SPX 0DTE long fly,
    # same entry window and one-entry-per-day, but the fly_bt.py sweep winner
    # config: WIDE wing (sd 1.5 -> ~1.275x straddle, debit ~0.395x wing,
    # ~$2,000/lot) and HOLD TO CASH SETTLEMENT instead of the 14:45 CT
    # buyback. The sweep (train 22-24 / holdout 24-25 / real-quote referee
    # Mar-May 26) found the buyback exit forfeits the whole edge (-$4..-$9/day
    # at real 2026 fills) while settle earns +$5..+$24/day/SPY-lot; wing 1.5
    # beats 1.0 by +$6..+$18/day on identical days. RIPPLE vs SPLASH on the
    # dashboard equity charts IS the live A/B of those two findings.
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
    # SPLASH — SPY 0DTE long butterfly ONLY, rebuilt 2026-07-09 after the
    # $500 pin+drift variant bricked in 3 days (-$462.50/6 trades). The live
    # loss was NOT the pin edge: 4 of 6 closes were phantom SLs — missing leg
    # quotes marked the 8-leg combo NEGATIVE (impossible for a net-long debit
    # structure), tripping the "disabled" sl_pct=1.0 stop, then the scanner
    # re-entered fresh debits same-day (3 entries on 7/8, one at a junk $0.065
    # quote). Fix = fly-only (4 legs, one expiration -> clean marks) + the
    # TIDE-style unreachable stop + one-entry-per-day + a min-debit gate.
    # Config = the REAL-FILL validated RIVER setup (ThetaData 2022-25,
    # examples/backtest_real_abc.py): enter morning, hold to the 14:45 CT
    # close, no PT, no SL. +$8/day/lot net of commissions on SPY, ~44% win
    # (low-win/positive-EV), green every year; real morning debit ~0.27x wing
    # vs ~0.38-0.45 breakeven. The 30/25/20% PT ladder is UNVALIDATED for the
    # fly, so pt_ladder=False and pt_pct=1.0 (only reachable pinned at expiry)
    # -> effective exit is the EOD close, exactly like the backtest.
    # Trades SPX (operator decision 2026-07-09): same underlying dynamics the
    # backtest validated at 10x notional per lot — one SPX fly ~= 10 SPY flies
    # (~$1,000-1,200 debit/lot), cash-settled PM (SPXW root), no assignment
    # risk. NOTE the $-P&L per lot is 10x the SPY backtest figures.
    "splash": {
        "display": "SPLASH",
        "strategy": "long_butterfly",
        "ticker": "SPX",
        "front_dte": 0,
        "back_dte": None,
        # Backtest = one morning entry/day; live churned 3 entries on 7/8.
        "one_entry_per_day": True,
        # Keep the signal's static PT (unreachable at 1.0) instead of the
        # intraday 30/25/20 ladder — hold-to-EOD is the validated exit.
        "pt_ladder": False,
        # Live A/B vs RIPPLE (wing 1.5 + settle-at-expiry) — overlaid on the
        # equity chart so the sweep's verdict is checked with real forward data.
        "compare_with": "ripple",
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": True,
            # SPX fly debit ~$1,000-1,200/lot -> bp 0.20 on $10k = 1-2 lots;
            # high-vol days (bigger straddle -> wider wing -> bigger debit)
            # auto-skip on budget, a built-in vol gate. Cap keeps compounding
            # inside where the fill model is credible.
            "max_contracts": 4,
            "bp_pct": 0.20,
            "sd_mult": 1.0,
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
