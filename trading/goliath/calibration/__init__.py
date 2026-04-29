"""GOLIATH Phase 1.5 calibration package.

Modules:
    data_fetch          — TV /series + yfinance with parquet caching
    wall_concentration  — Metric 1: wall threshold validation        (Step 3)
    tracking_error      — Metric 2: TE fudge factor validation       (Step 4)
    vol_drag            — Metric 3: drag coefficient validation      (Step 5)
    vol_window          — Metric 4: realized vol window sensitivity  (Step 6)

Each metric module exposes ``calibrate(data, config) -> Result`` per the
Module Contracts section of the v2 recovery doc.
"""
from __future__ import annotations

from .data_fetch import (
    LETF_PAIRS,
    LOOKBACK_DAYS,
    fetch_all_universe,
    fetch_gex_history,
    fetch_price_history,
)

__all__ = [
    "LETF_PAIRS",
    "LOOKBACK_DAYS",
    "fetch_all_universe",
    "fetch_gex_history",
    "fetch_price_history",
]
