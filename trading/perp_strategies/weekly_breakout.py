"""Weekly (168h) Donchian breakout with ATR stop + ATR trailing stop.

Selected for AGAPE-XRP-PERP by a walk-forward search over 5 strategy
families x ~260 parameter sets on 400 days of hourly XRP-USDT-SWAP data
(OKX public), net of 6 bps taker fees + 2 bps slippage per side + funding:

  - 168h breakout, stop 2.5 ATR, trail 2.0 ATR, one position at a time:
    102 trades, +51% summed per-trade return (1x notional), PF 1.74;
    flat-or-positive in 4 of 5 ~80-day windows; picked in 3/4 walk-forward
    folds; neighbouring settings with the trail are mostly positive.
  - Every other family (EMA trend, mean reversion, BTC-lead, squeeze) and the
    previous combined-signal path failed out of sample for XRP.

Rules (decided on CLOSED hourly candles only):
  long  when close > highest high of the previous `lookback` hours
  short when close < lowest  low  of the previous `lookback` hours
  initial stop = entry -/+ stop_atr * ATR(24); trailing stop follows the best
  price at trail_atr * ATR (never loosens); time exit after max_hold_hours.

ATR at entry is recoverable from the stored stop: |entry - stop_loss| / stop_atr,
so no extra DB column is needed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

COINBASE_PRODUCTS = {"BTC": "BTC-USD", "ETH": "ETH-USD", "XRP": "XRP-USD",
                     "SOL": "SOL-USD", "DOGE": "DOGE-USD", "AVAX": "AVAX-USD",
                     "SHIB": "SHIB-USD"}
HOUR = 3600


@dataclass(frozen=True)
class BreakoutSignal:
    direction: int          # +1 long, -1 short, 0 none
    atr: Optional[float]
    candle_ts: Optional[int]  # start time (s) of the closed candle evaluated
    close: Optional[float]
    upper: Optional[float]
    lower: Optional[float]
    reason: str


def fetch_hourly_candles(ticker: str, timeout: float = 10.0) -> List[Dict]:
    """Up to 300 hourly candles from Coinbase Exchange, oldest first,
    excluding the still-forming current hour."""
    product = COINBASE_PRODUCTS.get(ticker.upper())
    if not product:
        return []
    resp = requests.get(
        f"https://api.exchange.coinbase.com/products/{product}/candles",
        params={"granularity": HOUR},
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
        if int(r[0]) + HOUR <= now  # closed candles only
    ]
    candles.sort(key=lambda x: x["ts"])
    return candles


def wilder_atr(candles: List[Dict], period: int = 24) -> Optional[float]:
    """ATR matching the backtest: running average with alpha 1/period over true range."""
    if len(candles) <= period:
        return None
    atr = None
    for i, k in enumerate(candles):
        if i == 0:
            tr = k["h"] - k["l"]
        else:
            pc = candles[i - 1]["c"]
            tr = max(k["h"] - k["l"], abs(k["h"] - pc), abs(k["l"] - pc))
        atr = tr if atr is None else atr + (tr - atr) / period
    return atr


def evaluate(candles: List[Dict], lookback: int = 168, atr_period: int = 24) -> BreakoutSignal:
    """Breakout decision on the most recent closed candle."""
    if len(candles) < lookback + 1:
        return BreakoutSignal(0, None, None, None, None, None, f"INSUFFICIENT_CANDLES_{len(candles)}")
    last = candles[-1]
    window = candles[-lookback - 1:-1]
    upper = max(k["h"] for k in window)
    lower = min(k["l"] for k in window)
    atr = wilder_atr(candles, atr_period)
    if atr is None or atr <= 0:
        return BreakoutSignal(0, None, last["ts"], last["c"], upper, lower, "NO_ATR")
    if last["c"] > upper:
        return BreakoutSignal(1, atr, last["ts"], last["c"], upper, lower, "BREAKOUT_UP")
    if last["c"] < lower:
        return BreakoutSignal(-1, atr, last["ts"], last["c"], upper, lower, "BREAKOUT_DOWN")
    return BreakoutSignal(0, atr, last["ts"], last["c"], upper, lower, "NO_BREAKOUT")


def initial_stop(entry: float, direction: int, atr: float, stop_atr: float) -> float:
    return entry - direction * stop_atr * atr


def exit_decision(side: str, entry: float, stop_loss: float, current_stop: Optional[float],
                  best_price: float, price: float, stop_atr: float, trail_atr: float):
    """Return (should_close, reason, new_stop).

    best_price is the most favourable price seen (high for longs, low for
    shorts). The stop only ever tightens.
    """
    direction = 1 if side == "long" else -1
    atr = abs(entry - stop_loss) / stop_atr if stop_atr > 0 else 0.0
    stop = current_stop if current_stop else stop_loss
    trail = best_price - direction * trail_atr * atr
    stop = max(stop, trail) if direction == 1 else min(stop, trail)
    hit = price <= stop if direction == 1 else price >= stop
    if hit:
        locked_profit = (stop > entry) if direction == 1 else (stop < entry)
        reason = "WB_TRAIL_STOP" if locked_profit else "WB_STOP"
        return True, reason, stop
    return False, "", stop


# ---------------------------------------------------------------------------
# Session filter
#
# Loss clustering (400d OKX hourly, 168h breakout, 2.5/2.0 ATR):
#   XRP  breakouts starting 22:00-09:59 UTC: PF 3.14 older 60% / 2.42 newer 40%
#        breakouts starting 10:00-21:59 UTC: ~break-even, carried the losses
#   SHIB same window: PF 1.55 / 1.57 (unfiltered SHIB is ~flat)
# Any 12h window starting 21:00-00:00 UTC holds on both halves; windows
# starting >=01:00 fail on the older half. 22:00 is the middle of the plateau.
# Replayed with the live module + shadowing (see decide_entry):
#   XRP  46 trades, PF 2.60 (older 3.19 / newer 2.05) vs unfiltered 1.56 / 1.72
#   SHIB 41 trades, PF 1.48 (older 1.42 / newer 1.57) vs unfiltered 1.13 / 1.18
# ---------------------------------------------------------------------------

def in_session(candle_ts: int, start_hour_utc: int, hours: int) -> bool:
    """True when the candle's UTC start hour lies in [start, start+hours)."""
    if hours >= 24:
        return True
    hour = (int(candle_ts) // HOUR) % 24
    return (hour - start_hour_utc) % 24 < hours


def _advance_shadow(shadow: Dict, candles: List[Dict], config) -> bool:
    """Walk an out-of-session "shadow" breakout forward over closed candles.

    Returns True while the shadow is still open. Same bar-level rules as the
    backtest: adverse extreme checked first, then best price and trail update,
    then the time exit.
    """
    side = shadow["side"]
    direction = 1 if side == "long" else -1
    for k in candles:
        if k["ts"] <= shadow["last_ts"]:
            continue
        worst = k["l"] if direction == 1 else k["h"]
        closed, _, shadow["stop"] = exit_decision(
            side, shadow["entry"], shadow["stop_loss"], shadow["stop"], shadow["best"], worst,
            config.wb_stop_atr, config.wb_trail_atr)
        if closed:
            return False
        shadow["best"] = max(shadow["best"], k["h"]) if direction == 1 else min(shadow["best"], k["l"])
        _, _, shadow["stop"] = exit_decision(
            side, shadow["entry"], shadow["stop_loss"], shadow["stop"], shadow["best"], k["c"],
            config.wb_stop_atr, config.wb_trail_atr)
        shadow["last_ts"] = k["ts"]
        if (k["ts"] - shadow["entry_ts"]) / HOUR >= config.wb_max_hold_hours:
            return False
    return True


def decide_entry(config, ticker: str, holder) -> Dict:
    """Full entry decision for a bot config carrying wb_* settings.

    Session filter with shadowing: a breakout outside the session is not
    traded, but it is tracked as a shadow position and blocks new entries
    until it would have exited. Simply skipping it frees the slot for later,
    weaker breakouts (replay: XRP PF 2.11, SHIB 1.09), while shadowing keeps
    the measured edge (XRP PF 2.60, SHIB 1.48; both halves better than
    unfiltered).

    `holder` keeps state: `_wb_last_candle_ts` (act once per candle) and
    `_wb_shadow` (in-memory; a restart simply drops it).
    """
    try:
        candles = fetch_hourly_candles(ticker)
    except Exception as e:  # noqa: BLE001
        return {"direction": 0, "reason": f"WB_CANDLES_UNAVAILABLE_{type(e).__name__}"}
    shadow = getattr(holder, "_wb_shadow", None)
    if shadow:
        if _advance_shadow(shadow, candles, config):
            return {"direction": 0, "reason": "WB_SHADOW_ACTIVE"}
        holder._wb_shadow = None
    sig = evaluate(candles, lookback=config.wb_lookback_hours)
    if sig.direction == 0:
        return {"direction": 0, "reason": f"WB_{sig.reason}", "signal": sig}
    if sig.candle_ts == getattr(holder, "_wb_last_candle_ts", None):
        return {"direction": 0, "reason": "WB_ALREADY_ACTED_THIS_CANDLE", "signal": sig}
    holder._wb_last_candle_ts = sig.candle_ts
    if not in_session(sig.candle_ts, config.wb_session_start_utc, config.wb_session_hours):
        stop = initial_stop(sig.close, sig.direction, sig.atr, config.wb_stop_atr)
        holder._wb_shadow = {
            "side": "long" if sig.direction == 1 else "short", "entry": sig.close,
            "stop_loss": stop, "stop": None, "best": sig.close,
            "entry_ts": sig.candle_ts, "last_ts": sig.candle_ts,
        }
        return {"direction": 0, "reason": "WB_OUTSIDE_SESSION_SHADOWED", "signal": sig}
    return {"direction": sig.direction, "reason": f"WEEKLY_BREAKOUT_{sig.reason}", "atr": sig.atr, "signal": sig}


def manage_open_position(trader, table: str, pos: Dict, price: float, now, tz) -> bool:
    """ATR stop + trailing stop + time exit. Returns True when closed."""
    from datetime import datetime

    cfg = trader.config
    entry = pos["entry_price"]
    best = pos.get("high_water_mark") or entry
    best = max(best, price) if pos["side"] == "long" else min(best, price)
    should_close, reason, new_stop = exit_decision(
        side=pos["side"], entry=entry, stop_loss=pos["stop_loss"],
        current_stop=pos.get("current_stop"), best_price=best, price=price,
        stop_atr=cfg.wb_stop_atr, trail_atr=cfg.wb_trail_atr,
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
            if (now - ot).total_seconds() / 3600 >= cfg.wb_max_hold_hours:
                return trader._close_position(pos, price, "MAX_HOLD_TIME")
        except (ValueError, TypeError):
            pass
    return False
