# trading/agape_shared/regime_classifier.py
"""Stateless market-regime classifier for AGAPE perp/futures bots.

Returns one of CHOP / TREND / UNKNOWN given a snapshot dict-or-object that
exposes `combined_signal`, `combined_confidence`, and `crypto_gex_regime`.
See docs/superpowers/specs/2026-05-05-regime-aware-perp-exits-design.md §1.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class Regime(str, Enum):
    CHOP = "chop"
    TREND = "trend"
    UNKNOWN = "unknown"


_TREND_CONFIDENCES = {"MEDIUM", "HIGH"}
_DIRECTIONAL_SIGNALS = {"LONG", "SHORT"}


def _get(snap: Any, key: str):
    if isinstance(snap, dict):
        return snap.get(key)
    return getattr(snap, key, None)


def classify_regime(snap: Any) -> Regime:
    sig = _get(snap, "combined_signal")
    conf = _get(snap, "combined_confidence")
    gex = _get(snap, "crypto_gex_regime")

    if sig in _DIRECTIONAL_SIGNALS and conf in _TREND_CONFIDENCES:
        return Regime.TREND
    if sig == "RANGE_BOUND":
        return Regime.CHOP
    if sig in _DIRECTIONAL_SIGNALS:  # remaining: LOW confidence
        return Regime.CHOP
    if sig is None:
        if gex == "NEGATIVE":
            return Regime.TREND
        if gex == "POSITIVE":
            return Regime.CHOP
    return Regime.UNKNOWN
