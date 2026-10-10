"""H=3 daily variance-ratio fade, 6b trailing-lock target, rally circuit
breaker. AGAPE-SHIB-PERP only. PAPER research strategy.

Ported from `perp_replay/shib_hunt/round9_lock_breaker` ("Test B: 6b +
circuit breaker"). Independently re-implemented and numerically verified
against `round9_lock_breaker/verify/reimpl.py` (fresh code, no import of
the research engine) before being wired into this bot -- see that round's
PREREG.md / results.md for the full walk-forward record. Fixed parameters
below match reimpl.py exactly; nothing here is tunable from config or the
database (there is deliberately no `flb_*` config surface, unlike
`weekly_breakout.py`'s `wb_*` knobs -- an operator changing these numbers
would silently invalidate the backtested edge).

Disclosed research caveats (do not re-derive a "PASS" from this module
alone -- read round9's results.md before treating this as validated):
  - This combination (Round 8's variant 6b + variant 4) was assembled
    AFTER seeing Round 8's per-variant OOS results -- a post-hoc pick of
    the two least regime-like survivors out of 11, not a design that
    existed before those numbers were known.
  - The +1-day lag-robustness test clears the round's 1.2 PF bar by only
    0.024 (1.224 vs the 1.2 floor) -- a thin margin.
  - The identical frozen rule loses money pooled across DOGE/PEPE/FLOKI
    (PF 0.972, net -12.8%); it does not travel past SHIB's own path.
  Round 9's own verdict: "does NOT survive as a live-worthy edge, despite
  clearing the numeric bar." Shipped here as PAPER-ONLY research, not as
  a live-money recommendation.

Rule (all fixed, no menu, no fold-local selection):
  H=3 daily return  r3[t] = c[t] / c[t-3] - 1
  trigger: |r3[t]| >= K * sd90(r3, min_periods=40)          (K=1.5)
  direction (fade): r3 > 0 (up move)   -> fade it -> SHORT
                     r3 < 0 (down move) -> fade it -> LONG
  stop    = entry * (1 -/+ 2 * |r3[t]|)                     (2x the trigger move)
  target  = entry + 1.0 * (sma3[t] - entry)                 (100% reversion to
            the 3-day SMA as of the trigger day; "hard target")
  trailing lock (6b): once price reaches 50% of the way from entry to the
    hard target, the stop ratchets (monotonic, never loosens) to lock 50%
    of the best favorable excursion seen so far. Stop is checked before
    target on a same-candle double touch.
  time stop: 6 trading days held (entry day counts as day 1)
  circuit breaker: no NEW shorts while the daily close is > 1.5x the
    trailing 30-day closing low, until a daily close back below the
    trailing 20-day mean close (state machine, own SHIB close series)

Live/backtest translation (disclosed -- these are mechanism choices, not
rule tuning):
  - The backtest is bar-indexed: signal on closed day t, entry at day
    t+1's OPEN, 6-BAR time stop. This bot runs on a live scan cycle
    instead of a daily-bar replay, so entry is approximated by acting
    immediately once a new closed daily candle triggers the signal (the
    same translation `weekly_breakout.py` already makes for its own
    hourly bars), and the 6-trading-day time stop is enforced as
    6*24=144 elapsed wall-clock hours from `open_time` (the same
    mechanism as `wb_max_hold_hours` / `max_hold_hours` elsewhere in
    this bot). Crypto trades 24/7, so "trading day" and "calendar day"
    are the same thing here.
  - Only fully closed daily UTC candles are ever evaluated; the bot acts
    at most once per new closed candle (mirrors `weekly_breakout.py`'s
    `_wb_last_candle_ts` guard).
  - `best_price` (the favorable-excursion tracker feeding the trailing
    lock) uses the live scan-cycle price, not the true intrabar high/low
    the backtest has -- the same live approximation `weekly_breakout.py`
    already makes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

COINBASE_PRODUCT = "SHIB-USD"
DAY = 86400

# Fixed rule parameters (verify/reimpl.py, round9_lock_breaker Test B) --
# no tuning, no config override.
H = 3
K_TRIGGER = 1.5
SD_WINDOW = 90
SD_MIN_PERIODS = 40
STOP_MULT = 2.0
TARGET_FRAC = 1.0            # 100% reversion to the 3-day SMA
TRAIL_TRIGGER_FRAC = 0.5     # trailing lock activates at 50% of the way to target
TRAIL_LOCK_FRAC = 0.5        # locks 50% of the best favorable excursion
TIME_STOP_DAYS = 6
TIME_STOP_HOURS = TIME_STOP_DAYS * 24
BREAKER_LOW_WINDOW = 30
BREAKER_MEAN_WINDOW = 20
BREAKER_MULT = 1.5


@dataclass(frozen=True)
class FadeSignal:
    direction: int              # +1 long, -1 short, 0 none
    candle_ts: Optional[int]    # start time (s) of the closed candle evaluated
    close: Optional[float]
    move: Optional[float]       # |r3| at the trigger day (feeds the 2x stop)
    sma3: Optional[float]       # 3-day SMA at the trigger day (feeds the hard target)
    breaker_blocked: bool
    reason: str


def fetch_daily_candles(ticker: str = "SHIB", timeout: float = 10.0) -> List[Dict]:
    """Up to 300 daily candles from Coinbase Exchange, oldest first,
    excluding the still-forming UTC day."""
    if ticker.upper() != "SHIB":
        return []
    resp = requests.get(
        f"https://api.exchange.coinbase.com/products/{COINBASE_PRODUCT}/candles",
        params={"granularity": DAY},
        headers={"User-Agent": "AlphaGEX/1.0"},
        timeout=timeout,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        return []
    now = time.time()
    candles = [
        {"ts": int(r[0]), "l": float(r[1]), "h": float(r[2]), "o": float(r[3]), "c": float(r[4])}
        for r in rows
        if int(r[0]) + DAY <= now  # closed UTC days only
    ]
    candles.sort(key=lambda x: x["ts"])
    return candles


def _closes(candles: List[Dict]) -> pd.Series:
    return pd.Series([k["c"] for k in candles], dtype=float)


def build_indicators(candles: List[Dict]):
    """r3, sd90, sma3 aligned to `candles`' index -- identical math to
    verify/reimpl.py's build_signal()."""
    c = _closes(candles)
    r3 = c / c.shift(H) - 1.0
    sd90 = r3.rolling(SD_WINDOW, min_periods=SD_MIN_PERIODS).std()
    sma3 = c.rolling(3, min_periods=3).mean()
    return r3, sd90, sma3


def breaker_blocked_series(candles: List[Dict]) -> List[bool]:
    """Stateful rally-circuit-breaker scan -- identical to
    verify/reimpl.py's breaker_state(). Own SHIB close series only."""
    c = _closes(candles)
    n = len(c)
    low30 = c.rolling(BREAKER_LOW_WINDOW, min_periods=BREAKER_LOW_WINDOW).min()
    mean20 = c.rolling(BREAKER_MEAN_WINDOW, min_periods=BREAKER_MEAN_WINDOW).mean()
    blocked = [False] * n
    state = False
    for t in range(n):
        lo, mn = low30.iloc[t], mean20.iloc[t]
        if pd.isna(lo) or pd.isna(mn):
            blocked[t] = False
            continue
        if not state and c.iloc[t] > BREAKER_MULT * lo:
            state = True
        elif state and c.iloc[t] < mn:
            state = False
        blocked[t] = state
    return blocked


def evaluate(candles: List[Dict]) -> FadeSignal:
    """Fade-trigger decision on the most recently CLOSED daily candle."""
    n = len(candles)
    min_needed = SD_MIN_PERIODS + H  # sd90 needs 40 pts of r3; r3 needs H prior closes
    if n < min_needed:
        return FadeSignal(0, None, None, None, None, False, f"FADE_LOCK_BREAKER_INSUFFICIENT_CANDLES_{n}")
    r3, sd90, sma3 = build_indicators(candles)
    blocked = breaker_blocked_series(candles)
    t = n - 1
    last = candles[t]
    r3_t, sd_t, sma_t = r3.iloc[t], sd90.iloc[t], sma3.iloc[t]
    if pd.isna(r3_t) or pd.isna(sd_t) or sd_t <= 0:
        return FadeSignal(0, last["ts"], last["c"], None, None, blocked[t], "FADE_LOCK_BREAKER_NO_TRIGGER")
    if abs(r3_t) < K_TRIGGER * sd_t:
        return FadeSignal(0, last["ts"], last["c"], abs(r3_t), sma_t, blocked[t], "FADE_LOCK_BREAKER_NO_TRIGGER")
    # Fade: an UP move is faded with a SHORT; a DOWN move is faded with a LONG.
    if r3_t > 0:
        direction, reason = -1, "FADE_LOCK_BREAKER_FADE_UP"
    else:
        direction, reason = 1, "FADE_LOCK_BREAKER_FADE_DOWN"
    if direction == -1 and blocked[t]:
        return FadeSignal(0, last["ts"], last["c"], abs(r3_t), sma_t, True, "FADE_LOCK_BREAKER_BREAKER_BLOCKS_SHORT")
    return FadeSignal(direction, last["ts"], last["c"], abs(r3_t), sma_t, blocked[t], reason)


def initial_stop(entry_px: float, direction: int, move: float) -> float:
    """2x the triggering move's magnitude from entry."""
    return entry_px * (1 - STOP_MULT * move) if direction == 1 else entry_px * (1 + STOP_MULT * move)


def compute_hard_target(entry_px: float, sma3_val: float) -> float:
    """100% reversion to the 3-day SMA as of the trigger day."""
    return entry_px + TARGET_FRAC * (sma3_val - entry_px)


def exit_decision(side: str, entry: float, stop_loss: float, hard_target: float,
                   current_stop: Optional[float], best_price: float, price: float):
    """Return (should_close, reason, new_stop).

    `best_price` is the most favourable price seen (high for longs, low
    for shorts, approximated live by the scan-cycle price). The stop only
    ever tightens once the trailing lock activates. Stop is checked
    before target on a same-candle double touch (matches
    verify/reimpl.py's simulate()).
    """
    direction = 1 if side == "long" else -1
    stop = current_stop if current_stop is not None else stop_loss
    half_target = entry + TRAIL_TRIGGER_FRAC * (hard_target - entry)
    reached_half = (direction == 1 and best_price >= half_target) or \
                    (direction == -1 and best_price <= half_target)
    if reached_half:
        locked = entry + TRAIL_LOCK_FRAC * (best_price - entry)
        stop = max(stop, locked) if direction == 1 else min(stop, locked)
    hit_stop = price <= stop if direction == 1 else price >= stop
    if hit_stop:
        reason = "FLB_TRAIL_LOCK" if (stop > entry if direction == 1 else stop < entry) else "FLB_STOP"
        return True, reason, stop
    hit_target = price >= hard_target if direction == 1 else price <= hard_target
    if hit_target:
        return True, "FLB_TARGET", stop
    return False, "", stop


def decide_entry(config, ticker: str, holder) -> Dict:
    """Full entry decision for AGAPE-SHIB-PERP.

    `holder` keeps `_flb_last_candle_ts` state (act once per new closed
    daily candle) -- an in-memory restart simply forgets it, which is
    safe because `max_open_positions=1` upstream still caps re-entry.
    """
    try:
        candles = fetch_daily_candles(ticker)
    except Exception as e:  # noqa: BLE001
        return {"direction": 0, "reason": f"FADE_LOCK_BREAKER_CANDLES_UNAVAILABLE_{type(e).__name__}"}
    sig = evaluate(candles)
    if sig.direction == 0:
        return {"direction": 0, "reason": sig.reason, "signal": sig}
    if sig.candle_ts == getattr(holder, "_flb_last_candle_ts", None):
        return {"direction": 0, "reason": "FADE_LOCK_BREAKER_ALREADY_ACTED_THIS_CANDLE", "signal": sig}
    holder._flb_last_candle_ts = sig.candle_ts
    return {"direction": sig.direction, "reason": sig.reason, "signal": sig}


def manage_open_position(trader, table: str, pos: Dict, price: float, now, tz) -> bool:
    """Trailing-lock target (6b) exit + 6-trading-day time stop. Returns
    True when closed."""
    from datetime import datetime

    entry = pos["entry_price"]
    hard_target = pos.get("take_profit")
    if hard_target is None:
        # Should never happen for a fade_lock_breaker entry -- fail safe to
        # break-even rather than leave the position with no target at all.
        hard_target = entry
    best = pos.get("high_water_mark") or entry
    best = max(best, price) if pos["side"] == "long" else min(best, price)
    should_close, reason, new_stop = exit_decision(
        side=pos["side"], entry=entry, stop_loss=pos["stop_loss"],
        hard_target=hard_target, current_stop=pos.get("current_stop"),
        best_price=best, price=price,
    )
    if should_close:
        return trader._close_position(pos, price, reason)
    if new_stop != pos.get("current_stop"):
        trader.db._execute(
            f"UPDATE {table} SET trailing_active = TRUE, current_stop = %s "
            "WHERE position_id = %s AND status = 'open'",
            (float(new_stop), pos["position_id"]),
        )
    open_time = pos.get("open_time")
    if open_time:
        try:
            ot = datetime.fromisoformat(open_time) if isinstance(open_time, str) else open_time
            if ot.tzinfo is None:
                ot = ot.replace(tzinfo=tz)
            if (now - ot).total_seconds() / 3600 >= TIME_STOP_HOURS:
                return trader._close_position(pos, price, "FLB_TIME")
        except (ValueError, TypeError):
            pass
    return False
