"""Shared dip/rip setup detection for the vertical-spread bots.

Reuses UNDERTOW's dip_buy indicators. A BULLISH "dip" = oversold pullback in an
uptrend. A BEARISH "rip" = overbought bounce in a downtrend. All thresholds are
starting hypotheses (spec §0).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Any

from .dip_buy import closed_bars, sma, rsi

DEFAULT_SETUP_PARAMS: dict[str, Any] = {
    "lookback_n": 5,
    "dip_threshold": 0.03,
    "rsi_period": 2,
    "rsi_oversold": 10,
    "rsi_overbought": 90,
    "use_rsi_confirm": True,
    "use_trend_gate": True,
    "sma_period": 20,
}


@dataclass
class Setup:
    direction: str
    setup: str
    magnitude_pct: float
    reference_level: float
    rsi_value: float | None
    sma_value: float | None
    spot: float


def detect_setup(*, spot: float, history: list[dict[str, Any]], today: date,
                 params: dict[str, Any], diag: list[str] | None = None) -> Setup | None:
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    n = int(params["lookback_n"]); sma_period = int(params["sma_period"])
    rsi_period = int(params["rsi_period"])
    need = max(n, sma_period, rsi_period + 1)
    bars = closed_bars(history, today)
    if len(bars) < need:
        return _reject(f"insufficient_history: have={len(bars)} need={need}")
    if spot <= 0:
        return _reject("missing_spot")

    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    ref_high = max(highs[-n:]); ref_low = min(lows[-n:])
    rsi_value = rsi(closes, rsi_period)
    sma_value = sma(closes, sma_period)
    thr = float(params["dip_threshold"])

    dip_pct = (ref_high - spot) / ref_high if ref_high > 0 else 0.0
    rip_pct = (spot - ref_low) / ref_low if ref_low > 0 else 0.0

    if dip_pct >= thr:
        if params.get("use_rsi_confirm") and (rsi_value is None or rsi_value >= float(params["rsi_oversold"])):
            return _reject(f"dip_rsi_not_oversold: rsi={rsi_value}")
        if params.get("use_trend_gate") and (sma_value is None or spot <= sma_value):
            return _reject(f"dip_below_sma: spot={spot:.2f} sma={sma_value}")
        return Setup("bullish", "dip", round(dip_pct, 4), round(ref_high, 4),
                     rsi_value, sma_value, spot)

    if rip_pct >= thr:
        if params.get("use_rsi_confirm") and (rsi_value is None or rsi_value <= float(params["rsi_overbought"])):
            return _reject(f"rip_rsi_not_overbought: rsi={rsi_value}")
        if params.get("use_trend_gate") and (sma_value is None or spot >= sma_value):
            return _reject(f"rip_above_sma: spot={spot:.2f} sma={sma_value}")
        return Setup("bearish", "rip", round(rip_pct, 4), round(ref_low, 4),
                     rsi_value, sma_value, spot)

    return _reject(f"no_setup: dip={dip_pct:.3f} rip={rip_pct:.3f} min={thr:.3f}")
