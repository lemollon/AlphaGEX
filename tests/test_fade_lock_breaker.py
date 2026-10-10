"""H=3 fade + 6b trailing-lock target + rally circuit breaker (SHIB, paper).

Covers trading/perp_strategies/fade_lock_breaker.py and its wiring into
AGAPE-SHIB-PERP (strategy_mode="fade_lock_breaker", the bot's default).
Includes a parity test against the round9_lock_breaker research's
independent re-implementation (verify/reimpl.py) run once over a saved
real SHIB daily-candle fixture -- see tests/fixtures/SHIB_1d.csv and
SHIB_1d_expected_trades.json.
"""
import csv
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from trading.perp_strategies import fade_lock_breaker as flb

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _flat(n, price=1.0e-5, start_ts=0):
    """n perfectly flat daily candles -- never triggers (sd90 stays 0)."""
    return [{"ts": start_ts + i * flb.DAY, "o": price, "h": price, "l": price, "c": price}
            for i in range(n)]


def _daily(n, closes, start_ts=0, base_hl=0.0):
    """n daily candles with the given close path; o=prev close, h/l hug the close."""
    out = []
    prev = closes[0]
    for i, c in enumerate(closes[:n]):
        o = prev
        h = max(o, c) + base_hl
        l = min(o, c) - base_hl
        out.append({"ts": start_ts + i * flb.DAY, "o": o, "h": h, "l": l, "c": c})
        prev = c
    return out


# ---------------------------------------------------------------------------
# evaluate(): trigger up/down/none, insufficient history, breaker gating
# ---------------------------------------------------------------------------

def test_insufficient_history_waits():
    sig = flb.evaluate(_flat(10))
    assert sig.direction == 0
    assert sig.reason.startswith("FADE_LOCK_BREAKER_INSUFFICIENT_CANDLES")


def test_no_trigger_on_flat_series():
    sig = flb.evaluate(_flat(120))
    assert sig.direction == 0
    assert sig.reason == "FADE_LOCK_BREAKER_NO_TRIGGER"


def _build_trigger_series(n=120, base=1.0e-5, noise=0.0003, spike=None):
    """n-1 candles of small, low-variance noise around `base`, then one
    final candle that spikes `spike` fraction above/below the 3-day-ago
    close -- large enough relative to the noise-derived sd90 to trigger."""
    closes = [base]
    for i in range(1, n - 1):
        # tiny alternating wiggle -> small, stable sd90
        sign = 1 if i % 2 == 0 else -1
        closes.append(base * (1 + sign * noise))
    if spike is not None:
        closes.append(closes[-3] * (1 + spike))
    return _daily(n, closes)


def test_fade_up_triggers_short():
    candles = _build_trigger_series(spike=0.08)  # +8% vs 3 days ago, well under the breaker's 1.5x
    sig = flb.evaluate(candles)
    assert sig.direction == -1
    assert sig.reason == "FADE_LOCK_BREAKER_FADE_UP"
    assert sig.move > 0 and sig.sma3 is not None


def test_fade_down_triggers_long():
    candles = _build_trigger_series(spike=-0.08)  # -8% vs 3 days ago
    sig = flb.evaluate(candles)
    assert sig.direction == 1
    assert sig.reason == "FADE_LOCK_BREAKER_FADE_DOWN"
    assert sig.move > 0


def test_breaker_blocks_short_after_big_rally():
    """Close > 1.5x the trailing 30-day low blocks a NEW short, even when
    the fade-up trigger itself fires."""
    base = 1.0e-5
    # 45 flat days (>= the 43 candles evaluate() needs) establish a stable
    # 30-day low/mean, then a rally to > 1.5x that low, then the final
    # candle spikes further up (vs 3 days ago) to trigger a fade-up (short)
    # signal while the breaker is active.
    closes = [base] * 45
    closes += [base * 1.0, base * 1.3, base * 1.6]  # close(t)=1.6x base > 1.5x low(30d)=base
    closes.append(closes[-1] * 1.1)  # fresh up-spike vs 3 days ago -> fade trigger
    candles = _daily(len(closes), closes)
    sig = flb.evaluate(candles)
    assert sig.direction == 0
    assert sig.reason == "FADE_LOCK_BREAKER_BREAKER_BLOCKS_SHORT"
    assert sig.breaker_blocked is True


def test_breaker_releases_after_close_back_below_20d_mean():
    base = 1.0e-5
    closes = [base] * 35
    closes += [base * 1.3, base * 1.6]  # trip the breaker (> 1.5x 30d low)
    closes += [base * 0.9] * 25         # closes back below the 20-day mean -> releases
    closes.append(closes[-1] * 1.4)     # fresh up-spike -> fade trigger, breaker now off
    candles = _daily(len(closes), closes)
    sig = flb.evaluate(candles)
    assert sig.direction == -1
    assert sig.reason == "FADE_LOCK_BREAKER_FADE_UP"
    assert sig.breaker_blocked is False


def test_breaker_series_matches_state_machine_by_hand():
    """breaker_blocked_series: on, then off once close < trailing 20d mean."""
    base = 1.0e-5
    closes = [base] * 35 + [base * 1.6] + [base * 0.5] * 25
    candles = _daily(len(closes), closes)
    blocked = flb.breaker_blocked_series(candles)
    assert blocked[35] is True          # the rally candle itself trips it
    assert blocked[-1] is False         # 25 low closes later, well below the 20d mean


# ---------------------------------------------------------------------------
# initial_stop / compute_hard_target
# ---------------------------------------------------------------------------

def test_initial_stop_long_and_short():
    entry, move = 1.0e-5, 0.2
    assert flb.initial_stop(entry, 1, move) == pytest.approx(entry * 0.6)   # 1 - 2*0.2
    assert flb.initial_stop(entry, -1, move) == pytest.approx(entry * 1.4)  # 1 + 2*0.2


def test_hard_target_is_full_reversion_to_sma3():
    entry, sma3 = 1.0e-5, 1.2e-5
    assert flb.compute_hard_target(entry, sma3) == pytest.approx(sma3)
    entry2, sma3_2 = 1.0e-5, 0.8e-5
    assert flb.compute_hard_target(entry2, sma3_2) == pytest.approx(sma3_2)


# ---------------------------------------------------------------------------
# exit_decision(): stop / trailing lock / target / ordering
# ---------------------------------------------------------------------------

def test_long_stop_hit_before_trail_activates():
    entry, stop = 1.0, 0.8
    target = 1.4  # 100% reversion target well above entry
    close, reason, new_stop = flb.exit_decision(
        "long", entry, stop, target, current_stop=None, best_price=1.0, price=0.79)
    assert close and reason == "FLB_STOP" and new_stop == stop


def test_long_trailing_lock_activates_and_tightens_only():
    entry, stop, target = 1.0, 0.8, 1.4
    half_target = entry + 0.5 * (target - entry)  # 1.2
    # Price runs to 1.25 (past the 50%-of-the-way point) -> lock 50% of the
    # favorable move: entry + 0.5*(1.25-1.0) = 1.125
    close, reason, new_stop = flb.exit_decision(
        "long", entry, stop, target, current_stop=None, best_price=1.25, price=1.20)
    assert not close
    assert new_stop == pytest.approx(1.125)
    # A worse best_price on a later call must never loosen the lock.
    close2, reason2, new_stop2 = flb.exit_decision(
        "long", entry, stop, target, current_stop=new_stop, best_price=1.22, price=1.15)
    assert not close2 and new_stop2 == pytest.approx(new_stop)
    # Price falls through the locked stop -> closes profitably as a trail-lock exit.
    close3, reason3, new_stop3 = flb.exit_decision(
        "long", entry, stop, target, current_stop=new_stop, best_price=1.25, price=1.10)
    assert close3 and reason3 == "FLB_TRAIL_LOCK" and new_stop3 > entry


def test_long_target_hit():
    entry, stop, target = 1.0, 0.8, 1.4
    close, reason, new_stop = flb.exit_decision(
        "long", entry, stop, target, current_stop=None, best_price=1.4, price=1.4)
    assert close and reason == "FLB_TARGET"


def test_short_stop_and_target():
    entry, stop, target = 1.0, 1.2, 0.7
    close, reason, _ = flb.exit_decision(
        "short", entry, stop, target, current_stop=None, best_price=1.0, price=1.21)
    assert close and reason == "FLB_STOP"
    close2, reason2, _ = flb.exit_decision(
        "short", entry, stop, target, current_stop=None, best_price=0.7, price=0.7)
    assert close2 and reason2 == "FLB_TARGET"


def test_stop_checked_before_target_on_double_touch():
    """A bar whose range spans BOTH the stop and the target must exit on
    the (possibly trail-locked) stop, not the target -- matches
    verify/reimpl.py's simulate(), which updates best_price from the bar's
    favorable extreme (ratcheting the lock, since reaching target implies
    reaching the 50%-of-the-way trail trigger first) and THEN checks the
    adverse extreme before the favorable one. Bar-level replay calls
    exit_decision with the adverse extreme first, exactly the two-call
    pattern the parity harness below uses."""
    entry, stop, target = 1.0, 0.9, 1.06
    low, high = 0.85, 1.10  # bar spans through both stop and target
    close, reason, new_stop = flb.exit_decision(
        "long", entry, stop, target, current_stop=None, best_price=high, price=low)
    assert close and reason == "FLB_TRAIL_LOCK"
    assert new_stop == pytest.approx(1.05)  # entry + 0.5*(best_price-entry)


# ---------------------------------------------------------------------------
# decide_entry(): closed-candle guard, act-once-per-candle
# ---------------------------------------------------------------------------

def test_decide_entry_acts_once_per_new_closed_candle():
    holder = SimpleNamespace()
    candles = _build_trigger_series(spike=-0.08)
    with patch.object(flb, "fetch_daily_candles", return_value=candles):
        d1 = flb.decide_entry(None, "SHIB", holder)
        d2 = flb.decide_entry(None, "SHIB", holder)
    assert d1["direction"] == 1
    assert d2["direction"] == 0 and d2["reason"] == "FADE_LOCK_BREAKER_ALREADY_ACTED_THIS_CANDLE"


def test_decide_entry_waits_when_candles_unavailable():
    holder = SimpleNamespace()
    with patch.object(flb, "fetch_daily_candles", side_effect=RuntimeError("down")):
        d = flb.decide_entry(None, "SHIB", holder)
    assert d["direction"] == 0
    assert d["reason"].startswith("FADE_LOCK_BREAKER_CANDLES_UNAVAILABLE")


# ---------------------------------------------------------------------------
# manage_open_position(): trailing lock + time stop wiring
# ---------------------------------------------------------------------------

def test_manage_open_position_closes_on_target_and_updates_trail():
    closed, updates = [], []
    trader = SimpleNamespace(
        db=SimpleNamespace(_execute=lambda sql, params: updates.append(params)),
        _close_position=lambda pos, price, reason: closed.append(reason) or True,
    )
    now = datetime.now(timezone.utc)
    pos = {"position_id": "p1", "side": "long", "entry_price": 1.0, "stop_loss": 0.8,
           "take_profit": 1.4, "current_stop": None, "high_water_mark": 1.0,
           "open_time": now.isoformat()}
    # Runs toward target but not there yet -> trailing lock ratchets, stays open.
    assert flb.manage_open_position(trader, "t", pos, 1.25, now, timezone.utc) is False
    assert updates[-1][0] == pytest.approx(1.125)
    pos["current_stop"] = updates[-1][0]
    pos["high_water_mark"] = 1.25
    # Reaches the hard target -> closes.
    assert flb.manage_open_position(trader, "t", pos, 1.4, now, timezone.utc) is True
    assert closed == ["FLB_TARGET"]


def test_manage_open_position_time_stop_after_six_trading_days():
    from datetime import timedelta

    closed = []
    trader = SimpleNamespace(
        db=SimpleNamespace(_execute=lambda sql, params: None),
        _close_position=lambda pos, price, reason: closed.append(reason) or True,
    )
    now = datetime.now(timezone.utc)
    open_time = now - timedelta(hours=flb.TIME_STOP_HOURS + 1)
    pos = {"position_id": "p2", "side": "long", "entry_price": 1.0, "stop_loss": 0.8,
           "take_profit": 1.4, "current_stop": None, "high_water_mark": 1.0,
           "open_time": open_time.isoformat()}
    assert flb.manage_open_position(trader, "t", pos, 1.05, now, timezone.utc) is True
    assert closed == ["FLB_TIME"]


def test_manage_open_position_missing_target_falls_back_to_breakeven():
    """A position with no stored take_profit (should never happen for a
    real fade_lock_breaker entry) must not crash or hang open forever --
    it fails safe to a break-even target, which the current price (equal
    to entry) immediately satisfies."""
    closed = []
    trader = SimpleNamespace(
        db=SimpleNamespace(_execute=lambda sql, params: None),
        _close_position=lambda pos, price, reason: closed.append(reason) or True,
    )
    now = datetime.now(timezone.utc)
    pos = {"position_id": "p3", "side": "long", "entry_price": 1.0, "stop_loss": 0.8,
           "take_profit": None, "current_stop": None, "high_water_mark": 1.0,
           "open_time": now.isoformat()}
    # Degenerate breakeven case: stop and target both collapse to entry, and
    # the stop check (which runs first) catches it -- still closes safely
    # rather than crashing or holding forever.
    assert flb.manage_open_position(trader, "t", pos, 1.0, now, timezone.utc) is True
    assert closed == ["FLB_STOP"]


# ---------------------------------------------------------------------------
# AGAPE-SHIB-PERP wiring: strategy_mode default + signal generation
# ---------------------------------------------------------------------------

def test_shib_default_strategy_mode_is_fade_lock_breaker():
    from trading.agape_shib_perp.models import AgapeShibPerpConfig
    cfg = AgapeShibPerpConfig()
    assert cfg.strategy_mode == "fade_lock_breaker"
    assert cfg.mode.value == "paper"
    assert cfg.max_open_positions == 1


def test_shib_signal_uses_fade_lock_breaker_stop_and_target():
    from trading.agape_shib_perp.models import AgapeShibPerpConfig, SignalAction
    from trading.agape_shib_perp.signals import AgapeShibPerpSignalGenerator

    cfg = AgapeShibPerpConfig()
    gen = AgapeShibPerpSignalGenerator.__new__(AgapeShibPerpSignalGenerator)
    gen.config = cfg
    candles = _build_trigger_series(spike=-0.08)
    spot = candles[-1]["c"]
    md = {"spot_price": spot, "funding_regime": "BALANCED", "funding_rate": 0.001}
    with patch.object(gen, "get_market_data", return_value=md), \
         patch.object(flb, "fetch_daily_candles", return_value=candles):
        s1 = gen.generate_signal(prophet_data={"advice": "UNAVAILABLE"})
        s2 = gen.generate_signal(prophet_data={"advice": "UNAVAILABLE"})
    assert s1.action == SignalAction.LONG and s1.is_valid
    assert 0 < s1.stop_loss < spot < s1.take_profit
    assert s1.reasoning.startswith("FADE_LOCK_BREAKER_FADE_DOWN")
    assert s2.action == SignalAction.WAIT
    assert s2.reasoning == "FADE_LOCK_BREAKER_ALREADY_ACTED_THIS_CANDLE"


def test_shib_legacy_weekly_breakout_position_closed_on_mode_switch():
    """Switching SHIB from weekly_breakout to fade_lock_breaker must not
    strand an old weekly_breakout paper position (legacy_cleanup.py)."""
    from trading.perp_strategies.legacy_cleanup import close_legacy_and_overcap_positions

    trader = SimpleNamespace(
        config=SimpleNamespace(strategy_mode="fade_lock_breaker", max_open_positions=1,
                                bot_name="AGAPE_SHIB_PERP"),
        db=SimpleNamespace(log=lambda level, action, message, details=None: None),
        _close_position=lambda pos, price, reason: True,
    )
    positions = [{"position_id": "wb1", "signal_reasoning": "WEEKLY_BREAKOUT_BREAKOUT_UP",
                  "open_time": "2026-09-27T16:06:00+00:00"}]
    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=1.0e-5)
    assert remaining == [] and closed == 1


def test_shib_fade_lock_breaker_position_is_kept_on_its_own_mode():
    from trading.perp_strategies.legacy_cleanup import close_legacy_and_overcap_positions

    trader = SimpleNamespace(
        config=SimpleNamespace(strategy_mode="fade_lock_breaker", max_open_positions=1,
                                bot_name="AGAPE_SHIB_PERP"),
        db=SimpleNamespace(log=lambda level, action, message, details=None: None),
        _close_position=lambda pos, price, reason: True,
    )
    positions = [{"position_id": "flb1", "signal_reasoning": "FADE_LOCK_BREAKER_FADE_DOWN move=0.2 ...",
                  "open_time": "2026-09-27T16:06:00+00:00"}]
    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=1.0e-5)
    assert remaining == positions and closed == 0


# ---------------------------------------------------------------------------
# PARITY: replay over a real SHIB daily-candle fixture, compare against the
# round9_lock_breaker research's independent re-implementation
# (verify/reimpl.py, no import of this module or common7/common8), run once
# offline over the SAME fixture to produce SHIB_1d_expected_trades.json.
# ---------------------------------------------------------------------------

WF_START = datetime(2022, 7, 1, tzinfo=timezone.utc)
WF_END = datetime(2026, 9, 29, tzinfo=timezone.utc)
_REASON_MAP = {"FLB_STOP": "stop", "FLB_TRAIL_LOCK": "stop", "FLB_TARGET": "target", "FLB_TIME": "time"}


def _load_fixture_candles():
    with open(os.path.join(FIXTURES, "SHIB_1d.csv")) as f:
        rows = [
            {"ts": int(row["ts"]), "o": float(row["o"]), "h": float(row["h"]),
             "l": float(row["l"]), "c": float(row["c"])}
            for row in csv.DictReader(f)
        ]
    rows.sort(key=lambda r: r["ts"])
    seen, out = set(), []
    for r in rows:
        if r["ts"] in seen:
            continue
        seen.add(r["ts"])
        out.append(r)
    return out


def _bar_date(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _replay_fixture(candles):
    """Bar-stepping harness driven ONLY by this module's own exposed
    functions (build_indicators/breaker_blocked_series/initial_stop/
    compute_hard_target/exit_decision) -- reproduces reimpl.py's
    simulate() loop (next-bar-open entry, non-overlapping, 6-day time
    stop) using fade_lock_breaker.py's math, not a re-implementation of
    it. Per bar, exit_decision is called twice: once with the adverse
    extreme (checks the stop / trailing lock) and, if not closed, once
    with the favorable extreme (checks the target) -- reproducing
    reimpl.py's "update best-price from the bar's favorable extreme,
    then check stop before target" ordering with a live-shaped API that
    only takes one price per call. The entry-bar gap-through-stop check
    reimpl.py has is not reproduced here because it is structurally
    impossible in this translation: entry_px IS the live decision price,
    so it can never already be beyond a stop defined relative to itself
    (confirmed empirically: 0 of 97 real trades hit that path)."""
    n = len(candles)
    r3, sd90, sma3 = flb.build_indicators(candles)
    blocked = flb.breaker_blocked_series(candles)
    trades = []
    next_avail = 0
    for t in range(n - 1):
        if t < next_avail:
            continue
        r3_t, sd_t, sma_t = r3.iloc[t], sd90.iloc[t], sma3.iloc[t]
        if pd.isna(r3_t) or pd.isna(sd_t) or sd_t <= 0:
            continue
        if abs(r3_t) < flb.K_TRIGGER * sd_t:
            continue
        direction = -1 if r3_t > 0 else 1
        if direction == -1 and blocked[t]:
            continue
        entry_row = t + 1
        if entry_row >= n:
            continue
        entry_ts = candles[entry_row]["ts"]
        entry_date = datetime.fromtimestamp(entry_ts, tz=timezone.utc)
        if not (WF_START <= entry_date < WF_END):
            continue
        entry_px = candles[entry_row]["o"]
        side = "long" if direction == 1 else "short"
        stop_loss = flb.initial_stop(entry_px, direction, abs(r3_t))
        hard_target = flb.compute_hard_target(entry_px, sma_t)
        last_bar = min(entry_row + 5, n - 1)
        current_stop, best = None, entry_px
        exit_reason = exit_ts = None
        j = entry_row
        for j in range(entry_row, last_bar + 1):
            bar = candles[j]
            best = max(best, bar["h"]) if direction == 1 else min(best, bar["l"])
            adverse = bar["l"] if direction == 1 else bar["h"]
            should_close, reason, current_stop = flb.exit_decision(
                side, entry_px, stop_loss, hard_target, current_stop, best, adverse)
            if should_close:
                exit_reason, exit_ts = reason, bar["ts"]
                break
            favorable = bar["h"] if direction == 1 else bar["l"]
            should_close, reason, current_stop = flb.exit_decision(
                side, entry_px, stop_loss, hard_target, current_stop, best, favorable)
            if should_close:
                exit_reason, exit_ts = reason, bar["ts"]
                break
        if exit_reason is None:
            j = last_bar
            exit_reason, exit_ts = "FLB_TIME", candles[j]["ts"]
        trades.append({"entry_date": _bar_date(entry_ts), "exit_date": _bar_date(exit_ts),
                        "direction": direction, "exit_reason": exit_reason})
        next_avail = j + 1
    return trades


def test_parity_against_independent_reimpl_over_real_shib_fixture():
    candles = _load_fixture_candles()
    trades = _replay_fixture(candles)

    with open(os.path.join(FIXTURES, "SHIB_1d_expected_trades.json")) as f:
        expected = json.load(f)

    assert len(trades) == len(expected) == 97

    for i, (actual, exp) in enumerate(zip(trades, expected)):
        assert actual["entry_date"] == exp["entry_date"], f"trade {i} entry_date"
        assert actual["exit_date"] == exp["exit_date"], f"trade {i} exit_date"
        assert actual["direction"] == exp["direction"], f"trade {i} direction"
        norm_reason = _REASON_MAP.get(actual["exit_reason"], actual["exit_reason"])
        assert norm_reason == exp["exit_reason"], f"trade {i} exit_reason"
