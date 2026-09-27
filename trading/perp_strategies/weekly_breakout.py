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
