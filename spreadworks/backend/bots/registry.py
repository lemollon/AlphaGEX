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
    # UPDRAFT — SPY 0DTE long call on put-heavy flow INTO a rising tape.
    # Research 2026-07-26 (ironforge-data/examples/hf_*.py, ADR 0007):
    # buy the +1 OTM call when the 30-min 0DTE tape is put-heavy AND spot is
    # up over the same window — fading a put crowd the tape is running over.
    # Full sample n=843 (with BACKDRAFT, 3 concurrent): +15.92%/trade,
    # t=3.30, 248 trades/yr, 4/4 years positive, beats a time-matched
    # placebo 30/30 (placebo -8.10%). Held-out 2025-26: +12.83%, t=1.55 —
    # 95% CI [-2.00%, +28.98%] INCLUDES ZERO, so this is an UNCONFIRMED
    # candidate shipped as PAPER. Do not arm real money on it.
    # A 5-minute scan cadence was measured to retain 86% of the edge.
    "updraft": {
        "display": "UPDRAFT",
        "strategy": "updraft",
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": 0,                  # single expiration, no back leg
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            "bp_pct": 0.02,
            # Required by the bot_config schema (db.py seeds every column
            # directly). Unused by this strategy: there is no spread to
            # width, no skew to apply, and strike choice is a fixed +1 OTM
            # offset rather than a gamma wall.
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            # Thresholds are quantiles fitted on 2023-24 and FROZEN. They were
            # never re-tuned on the held-out period; loosening them was tested
            # and is strictly worse in dollars (qr q90 $2,370/yr per contract
            # vs q80 $1,491 vs q70 $395).
            "flow_max": -0.1378,
            "r30_min": 19.23,
            "strike_offset": 1,
            "hold_minutes": 45,
            # NO profit target — a PT cut returns ~6x in research. 9.9999 is
            # the LARGEST value pt_pct NUMERIC(5,4) can hold; +999.99% of
            # premium is unreachable over a 45-minute 0DTE hold. Do not raise
            # it: 99.0 overflows the column and aborts create_bot_tables for
            # EVERY bot (the seeding runs in one transaction).
            "pt_pct": 9.9999,
            "sl_pct": 0.50,
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            # 08:31–14:00 CT == 09:31–15:00 ET, the researched entry window.
            "entry_start_ct": "08:31",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            # The book depends on holding up to 3 at once: raising the cap
            # from 1 to 3 gave 2.5x the trades AND a higher mean (+14.57% ->
            # +15.92%). The blocked signals were as good as the taken ones.
            "allow_stacking": True,
            "max_concurrent_positions": 3,
            # The edge lives in the FIRST touch of a burst (+15.30% vs +5.01%
            # across all signal minutes), so stand down after an entry.
            "cooldown_min": 45,
            "discord_alerts": False,
        },
    },
    # THERMAL — UPDRAFT's exact signal, ridden to the CLOSE instead of 45
    # minutes (2026-07-28). Same frozen gates (flow<=-0.1378, r30>=19.23bp);
    # the ONLY changes are ATM strike, no stop, one entry/day, and exit at
    # settlement (~intrinsic at the 14:59 CT MTM).
    #
    # Research (first event/day, C+0, no stop, settle payoff, entry-side
    # cost only): TRAIN +25.9% / TEST +35.5% per trade (t~1.5 both), 44%
    # win rate, ~45/yr. $1,000 sim at 1 contract: -> $9,209 in 3.4y, max DD
    # 45%, years +37/-12/+49/+20. Heavy right skew: most of the year is a
    # handful of trend days — expect losing streaks. t<2 -> UNCONFIRMED,
    # PAPER ONLY on a $1k account.
    "thermal": {
        "display": "THERMAL",
        "strategy": "updraft",          # same module, same mode=updraft gates
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": 0,
        # research construction is ONE ride per day (vs UPDRAFT's k=3 bursts)
        "one_entry_per_day": True,
        "defaults": {
            # $1k paper framing (FLASHPOINT precedent)
            "starting_capital": 1000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            # ATM calls ~$100-350; 50% of $1k covers $500 so sizing never
            # floors to zero (the AFTERBURN lesson)
            "bp_pct": 0.50,
            # schema-required, unused — see UPDRAFT
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "updraft",
            "flow_max": -0.1378,             # FROZEN, same as UPDRAFT
            "r30_min": 19.23,                # FROZEN, same as UPDRAFT
            "strike_offset": 0,              # ATM (C+0 beat C+1: DD 45% vs 72%)
            # timer must NEVER fire before the close — the EOD close is the
            # exit. 600m from a 08:31 entry lands past the bell.
            "hold_minutes": 600,
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            # research ran NO stop: a settle hold rides -80% drawdowns into
            # green closes; 0.99 is the no-stop sentinel (AFTERBURN precedent)
            "sl_pct": 0.99,
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "08:31",
            "entry_end_ct": "14:00",
            # as late as the 2-minute scan cycle can reliably exit before the
            # 15:00 CT bell — ~intrinsic, the research's settlement payoff
            "eod_close_ct": "14:57",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,             # belt-and-braces with one/day
            "discord_alerts": False,
        },
    },
    # BACKDRAFT — the same +1 OTM 0DTE call, triggered by flow EXTREMITY plus
    # dealer-gamma support instead of momentum. Shares zero entry minutes
    # with UPDRAFT in research (43 shared days of 145/89), so the two are
    # genuinely separate signals rather than one trade twice. Held-out
    # +14.32%/trade, t=1.55, ~40 trades/yr. PAPER, same caveat as UPDRAFT.
    "backdraft": {
        "display": "BACKDRAFT",
        "strategy": "updraft",          # same module, mode=backdraft
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": 0,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            "bp_pct": 0.02,
            # schema-required, unused here — see UPDRAFT. The put wall IS
            # part of this signal, but it is read from chain["gex"] inside
            # the strategy, not through this flag (which drives strike
            # placement for the spread bots).
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "backdraft",
            "backdraft_flow_max": -0.35,
            "require_put_wall": True,
            "strike_offset": 1,
            "hold_minutes": 30,
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            "sl_pct": 0.50,
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "08:31",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "allow_stacking": True,
            "max_concurrent_positions": 3,
            "cooldown_min": 30,
            "discord_alerts": False,
        },
    },
    # WILDFIRE — BACKDRAFT's exact signal, ridden to the CLOSE (2026-07-28,
    # THERMAL's twin on the book's strongest per-trade trigger). Same frozen
    # gates (flow < -0.35 AND spot above the intraday put wall); the exit is
    # the whole change: ATM, NO stop, one entry/day, EOD close 14:57 CT
    # (~intrinsic, the research's settlement payoff).
    #
    # Research (first event/day, C+0, no stop, settle, entry cost only):
    # TRAIN +38.5% (t=1.6) / TEST +20.6% (t=0.9), ~27/yr. $1,000 sim at 1
    # contract -> $3,778 in 3.4y. Settle-holds only work on the MOMENTUM
    # signals: REVERSAL-settle and FLASHPOINT-settle both bankrupt a $1k
    # account — do not extend this pattern to reversion legs. t<2 ->
    # UNCONFIRMED, PAPER ONLY on a $1k account.
    "wildfire": {
        "display": "WILDFIRE",
        "strategy": "updraft",          # same module, mode=backdraft gates
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": 0,
        "one_entry_per_day": True,
        "defaults": {
            # $1k paper framing (FLASHPOINT/THERMAL precedent)
            "starting_capital": 1000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            # ATM calls ~$100-350; 50% of $1k never floors to zero contracts
            "bp_pct": 0.50,
            # schema-required, unused — see UPDRAFT
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "backdraft",
            "backdraft_flow_max": -0.35,     # FROZEN, same as BACKDRAFT
            "require_put_wall": True,        # the wall IS the signal's half
            "strike_offset": 0,              # ATM for the all-day ride
            # timer must NEVER fire before the 14:57 EOD close (THERMAL)
            "hold_minutes": 600,
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            "sl_pct": 0.99,     # research ran NO stop — settle holds ride
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "08:31",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:57",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,             # belt-and-braces with one/day
            "discord_alerts": False,
        },
    },
    # REVERSAL — the third leg. Same 0DTE call, but an ATM strike and a
    # completely different mechanism: a multi-day hourly oversold state
    # resolving upward, rather than fading a put-buying crowd.
    #
    # THE ENTRY IS THE WHOLE EDGE. It fires only when hourly RSI(14) closes
    # back ABOVE 30 having been below. Measured three ways:
    #     recovery cross (this)      SPY +10.68%, XSP +12.58%, TEST >= TRAIN
    #     cross down (into the fall) SPY  -3.87%, XSP  -3.74%
    #     "RSI is low" as a state    SPY  +1.24%, XSP  +2.66%
    # The sign flips on that distinction — never relax it to a level test.
    #
    # WHAT IT ADDS TO THE BOOK: not money, diversification. It shares ZERO
    # entry minutes with UPDRAFT and BACKDRAFT. Book with it vs without:
    #     2-leg  442 trades/yr  +14.51%  t=3.23  TEST +10.77% (t=1.47)  $3,509/yr
    #     3-leg  441 trades/yr  +13.58%  t=3.48  TEST +11.42% (t=1.84)  $3,506/yr
    # Same dollars, better t and better out-of-sample — it cuts the book's
    # reliance on the single flow mechanism.
    #
    # NOT individually confirmed: 72 cells were screened and the best reached
    # t=1.79, which does not clear a multiplicity bar. PAPER ONLY.
    "reversal": {
        "display": "REVERSAL",
        "strategy": "updraft",          # same module, mode=reversal
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": 0,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            "bp_pct": 0.02,
            # schema-required, unused here — see UPDRAFT.
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "reversal",
            "rsi_threshold": 30.0,
            "rsi_period": 14,
            # ATM, not +1 OTM. The 45-minute hold was best at EVERY strike
            # (30m and 60m both weaker), and ATM carried the best dollars
            # per trade of the non-artifact cells.
            "strike_offset": 0,
            "hold_minutes": 45,
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            "sl_pct": 0.50,
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "08:31",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "allow_stacking": True,
            "max_concurrent_positions": 3,
            # One entry per hourly cross. The trigger is a single bar event,
            # so a 60-minute cooldown spans the bar that produced it.
            "cooldown_min": 60,
            "discord_alerts": False,
        },
    },
    # EMBREACH — the 4th leg and the book's FIRST PUT leg. Fires when the
    # session's move from open first crosses BELOW -0.8x the ATM-straddle
    # expected move: the day broke its priced range -> downside CONTINUATION.
    #
    # Research (em-breach memo, hf_28/29/30): P+0 45m TRAIN +4.55% / TEST
    # +8.43%; the SAME put at the SAME time of day WITHOUT the signal loses
    # -21%, so the event flips the sign of a structurally losing trade
    # (edge over placebo +28pts). Edge lives on ORDINARY days: NEGATIVE when
    # the open priced a catalyst, hence max_open_straddle_pct. 3/4 years
    # positive; TEST t=1.3-1.6 -> UNCONFIRMED. PAPER ONLY.
    #
    # This is the documented exception to "long puts always lose": the
    # upward-drift objection is suspended once the day has already broken
    # its own priced range.
    "embreach": {
        "display": "EMBREACH",
        "strategy": "updraft",          # same module, mode=em_breach
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": 0,
        # the research construction is ONE event entry per day
        "one_entry_per_day": True,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            "bp_pct": 0.02,
            # schema-required, unused here — see UPDRAFT.
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "em_breach",
            "em_frac": 0.8,                  # fixed a priori in research
            "max_open_straddle_pct": 0.75,   # TRAIN q90 of the open straddle
            "strike_offset": 0,              # ATM PUT (P+0 was the best cell)
            "hold_minutes": 45,
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            "sl_pct": 0.50,
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "08:31",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,             # belt-and-braces with one/day
            "discord_alerts": False,
        },
    },
    # EMBREACHQ — EMBREACH replicated on QQQ (2026-07-28). Same mechanism,
    # QQQ's own thresholds (percentile transplant, never raw values): the
    # -0.8x EM breach multiple is structural and carries over; the catalyst
    # filter re-fits to QQQ's open-straddle TRAIN q90 = 1.04% (SPY 0.75%).
    #
    # Research (qqq_option_minute, 893 sessions, REAL QQQ quote costs from
    # the 60-session sample — 1.14-1.86x the SPY model in $0.50+ buckets):
    # P+0 45m first-cross, entries 08:31-14:00 CT, catalyst-filtered:
    # TRAIN +3.13% / TEST +9.15% (t=1.2, n=400) — the same shape as SPY's
    # +4.55/+8.43. ~115 events/yr: roughly DOUBLES the mechanism's trade
    # count. Weaker t than SPY -> UNCONFIRMED. PAPER ONLY.
    "embreachq": {
        "display": "EMBREACHQ",
        "strategy": "updraft",          # same module, mode=em_breach
        "ticker": "QQQ",
        "front_dte": 0,
        "back_dte": 0,
        "one_entry_per_day": True,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            # QQQ ATM 0DTE puts at breach times run ~$1.50-3.00 ($150-300 a
            # contract). bp 2% of $10k = $200 can floor to ZERO contracts —
            # the AFTERBURN sizing lesson — so 4% here.
            "bp_pct": 0.04,
            # schema-required, unused here — see UPDRAFT.
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "em_breach",
            "em_frac": 0.8,                  # structural, carried from SPY
            "max_open_straddle_pct": 1.04,   # QQQ TRAIN q90 (SPY was 0.75)
            "strike_offset": 0,              # ATM PUT
            "hold_minutes": 45,
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            "sl_pct": 0.50,
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "08:31",
            "entry_end_ct": "14:00",
            "eod_close_ct": "14:45",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,             # belt-and-braces with one/day
            "discord_alerts": False,
        },
    },
    # FLASHPOINT — wide opening range -> first break above it -> ATM call
    # (2026-07-28). Unfiltered ORB is breakeven (+0.56/+2.36, t<1); the edge
    # is CONDITIONAL on a wide morning: OR width (08:31-09:00 CT, as % of
    # open) / open ATM straddle % > TRAIN q67 = 0.5709. Wide morning =
    # realized vol already beating implied; the upward break gives direction.
    #
    # Research (hf frequency-frontier session): calls-only TRAIN +10.28%
    # (t=1.8) / TEST +5.19% (t=1.1), ~56/yr; put side TRAIN-NEGATIVE — no
    # put twin. $1,000 sim, 1 contract: -> $3,328 over 3.5y ($656/yr), max
    # DD 54%, worst trade -$335. ⚠️ Cutoff picked among ~4 candidates and
    # dose-response is non-monotone -> WEAKEST evidence grade of the family.
    # PAPER ONLY at $1k; paper P&L adjudicates.
    "flashpoint": {
        "display": "FLASHPOINT",
        "strategy": "updraft",          # same module, mode=flashpoint
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": 0,
        "one_entry_per_day": True,
        "defaults": {
            # Leron's framing: run this one on a $1,000 paper account so the
            # reported P&L reads directly as "what $1k does".
            "starting_capital": 1000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            # ATM 0DTE calls on wide-range days run ~$100-350; 50% of $1k
            # covers up to a $500 premium -> 1 contract, never 0 (the
            # AFTERBURN sizing lesson).
            "bp_pct": 0.50,
            # schema-required, unused here — see UPDRAFT.
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "flashpoint",
            "or_width_min_em": 0.5709,       # TRAIN q67, frozen
            "strike_offset": 0,              # ATM CALL
            "hold_minutes": 45,
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            "sl_pct": 0.50,
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            # range completes 09:00; breakout window mirrors research
            # (entries 09:01-13:30 CT)
            "entry_start_ct": "09:01",
            "entry_end_ct": "13:30",
            "eod_close_ct": "14:45",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,             # belt-and-braces with one/day
            "discord_alerts": False,
        },
    },
    # AFTERGLOW — the day's UPDRAFT signal predicts the NEXT TWO DAYS
    # (2026-07-29). Buy a weekly ATM call at the close of any day the flow
    # gates fired; exit ~2 trading days later. Research (real EOD quotes,
    # ask-in/bid-out): SPY +20.7% TRAIN / +20.3% TEST (4/4 years, 6/6 cells
    # positive both halves, ~35/yr); PLACEBO (same call, random days) is
    # FLAT OOS (-0.3%); SPX replication +21.2/+28.4 (t=1.7). The strongest
    # new find of the 5-ideas hunt. t per-cell ~1.2-1.5 -> PAPER ONLY.
    "afterglow": {
        "display": "AFTERGLOW",
        "strategy": "updraft",          # same module, mode=afterglow
        "ticker": "SPY",
        # nearest weekly: research used the first expiry 4-9 calendar days out
        "front_dte": 5,
        "back_dte": 5,
        "one_entry_per_day": True,
        "defaults": {
            "starting_capital": 1000.0,   # the $1k reporting frame
            # no Friday entries: a Fri close + 2880m timer would exit Sunday
            # and slip to Monday's first scan — a different (untested) hold.
            "entry_days": "mon,tue,wed,thu",
            "enabled": False,   # no bot ships armed
            "max_contracts": 1,
            # SPY weekly ATM ~$250-450; 50% of $1k never floors to zero
            "bp_pct": 0.50,
            "sd_mult": 1.0, "delta_skew": 0, "use_gex_walls": False,
            "mode": "afterglow",
            "flow_max": -0.1378,          # FROZEN — same gates as UPDRAFT
            "r30_min": 19.23,
            "strike_offset": 0,
            # wall-clock ~2 trading days: 14:55 + 2880m = 14:55 two days on.
            # EOD close can't preempt it (front expiry is ~a week out).
            "hold_minutes": 2880,
            "pt_pct": 9.9999,
            "sl_pct": 0.99,               # research ran NO stop
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            # read the day flag in the last minutes, AFTERBURN-style
            "entry_start_ct": "14:50",
            "entry_end_ct": "14:59",
            "eod_close_ct": "14:59",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,
            "discord_alerts": False,
        },
    },
    # EMBER — AFTERGLOW's twin on the REVERSAL signal: hourly RSI recovery
    # crossed at any bar today -> weekly ATM call at the close, ~2-day hold.
    # Research: h1 +20.9/+13.5, h2 +35.7/+25.6 (both halves, beats the flat
    # placebo), ~20/yr, n=51-70 -> CANDIDATE grade, weakest sample of the
    # three 7/29 finds. PAPER ONLY.
    "ember": {
        "display": "EMBER",
        "strategy": "updraft",          # same module, mode=ember
        "ticker": "SPY",
        "front_dte": 5,
        "back_dte": 5,
        "one_entry_per_day": True,
        "defaults": {
            "starting_capital": 1000.0,
            "enabled": False,   # no bot ships armed
            "max_contracts": 1,
            "bp_pct": 0.50,
            "entry_days": "mon,tue,wed,thu",
            "sd_mult": 1.0, "delta_skew": 0, "use_gex_walls": False,
            "mode": "ember",
            "rsi_threshold": 30.0,        # the cross level IS the edge
            "rsi_period": 14,
            "strike_offset": 0,
            "hold_minutes": 2880,
            "pt_pct": 9.9999,
            "sl_pct": 0.99,
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "14:50",
            "entry_end_ct": "14:59",
            "eod_close_ct": "14:59",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,
            "discord_alerts": False,
        },
    },
    # AFTERBURN — strong close -> overnight 1DTE call. The only leg that
    # holds past the bell, and the cleanest research profile of the campaign:
    # 9/9 cells (3 strikes x 3 thresholds) positive in BOTH periods, MONOTONE
    # dose-response in the threshold, 4/4 years positive (2026 +17.9%),
    # placebo (unconditional overnight call) +2.35% vs +10-28% conditioned.
    # C+0 at TRAIN-q80: TRAIN +10.08% / TEST +24.26% (t=2.35), ~38 trades/yr.
    #
    # MECHANICS, because they are non-obvious:
    #   front_dte=1        -> tomorrow's expiry; decide_exit's EOD close only
    #                         fires ON the front-leg expiration day, so the
    #                         overnight hold needs no new exit machinery.
    #   hold_minutes=1056  -> WALL-CLOCK timer: 14:55 entry + 1056m = ~08:31
    #                         CT next morning = the researched exit-at-open.
    #   entry_days mon-thu -> no Friday entries. Research had ZERO Friday
    #                         events (no 1DTE into a weekend) — structural.
    #   sl_pct=0.99        -> research ran NO stop (none is possible
    #                         overnight anyway); PT unreachable as usual.
    # TEST > TRAIN everywhere (2025-26 drift-flattered) and ~50 cells were
    # screened -> UNCONFIRMED. PAPER ONLY.
    "afterburn": {
        "display": "AFTERBURN",
        "strategy": "updraft",          # same module, mode=afterburn
        "ticker": "SPY",
        "front_dte": 1,
        "back_dte": 1,
        "one_entry_per_day": True,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            # schema-required, unused here — see UPDRAFT.
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "afterburn",
            # ATM 1DTE premium runs $300-400/contract. bp 2% of $10k = $200
            # sizes to ZERO contracts and the bot silently never trades
            # (caught by test). 5% = one contract at these premiums.
            "bp_pct": 0.05,
            "afterburn_min_ret_pct": 0.52,   # TRAIN q80 session return
            "strike_offset": 0,              # ATM call
            "hold_minutes": 1056,            # 14:55 -> ~08:31 CT next day
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            "sl_pct": 0.99,     # no stop in research; none possible overnight
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "14:50",
            "entry_end_ct": "14:59",
            "eod_close_ct": "14:45",         # only bites on expiry day
            "entry_days": "mon,tue,wed,thu",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,
            "discord_alerts": False,
        },
    },
    # WEEKENDER — AFTERBURN's Friday twin: buy a 3DTE ATM call at Friday's
    # close, hold THROUGH THE WEEKEND, exit Monday ~08:31 CT. Fills the one
    # session AFTERBURN structurally cannot trade (no 1DTE into a weekend).
    #
    # Research (hf_35): ALL Fridays, both periods positive — TRAIN +7.55% /
    # TEST +13.28% (t~1.0, n=138, ~40/yr). The strong-close-Friday split was
    # stronger (+34.5% TEST) but n=30, so the leg ships UNCONDITIONAL
    # (afterburn_min_ret_pct=-99 disables the gate) and the split stays a
    # config experiment for later.
    #
    # ⚠️ BELOW the campaign's evidence gate (t~1.0) — shipped to paper at
    # Leron's explicit call; paper adjudicates. NEVER arm real money on this
    # without a positive paper record.
    #
    # Mechanics mirror AFTERBURN: front_dte=3 (Monday expiry on a Friday;
    # EOD close only fires on expiration day) + wall-clock hold_minutes
    # 3936 (Fri 14:55 + 3936m = Mon ~08:31 CT; the scanner is asleep all
    # weekend and the timer fires on Monday's first post-08:31 scan).
    # bp_pct 0.10: a 3DTE ATM call runs ~$450-650/contract — 5% of $10k
    # would size to zero exactly like the AFTERBURN bug.
    "weekender": {
        "display": "WEEKENDER",
        "strategy": "updraft",          # same module, mode=weekender
        "ticker": "SPY",
        "front_dte": 3,
        "back_dte": 3,
        "one_entry_per_day": True,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,   # UNCONFIRMED — paper only, ships disarmed
            "max_contracts": 1,
            # schema-required, unused here — see UPDRAFT.
            "sd_mult": 1.0,
            "delta_skew": 0,
            "use_gex_walls": False,
            "mode": "weekender",
            "bp_pct": 0.10,                  # 3DTE ATM premium ~$450-650
            "afterburn_min_ret_pct": -99.0,  # UNCONDITIONAL (see header)
            "strike_offset": 0,              # ATM call
            "hold_minutes": 3936,            # Fri 14:55 -> Mon ~08:31 CT
            "pt_pct": 9.9999,   # see UPDRAFT — NUMERIC(5,4) ceiling
            "sl_pct": 0.99,     # no stop possible over a weekend
            "min_option_price": 0.10,
            "max_spread_pct": 0.15,
            "entry_start_ct": "14:50",
            "entry_end_ct": "14:59",
            "eod_close_ct": "14:45",         # only bites on expiry day (Mon)
            "entry_days": "fri",
            "allow_stacking": False,
            "max_concurrent_positions": 1,
            "cooldown_min": 390,
            "discord_alerts": False,
        },
    },
}


def list_bots() -> list[str]:
    return list(BOT_REGISTRY.keys())


def get_bot(bot: str) -> dict[str, Any]:
    if bot not in BOT_REGISTRY:
        raise KeyError(f"Unknown bot: {bot!r}. Known: {sorted(BOT_REGISTRY)}")
    return BOT_REGISTRY[bot]
