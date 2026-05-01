"""GOLIATH data-fetching adapters (Tradier + TV + yfinance).

The calibration package (trading/goliath/calibration/) handles the
historical 90d pulls that feed Phase 1.5. This package is the per-cycle
runtime data path: pulls option chains from Tradier, GEX from TV,
underlying spots from yfinance, and assembles a MarketSnapshot for the
engine.
"""
from .tradier_snapshot import build_market_snapshot

__all__ = ["build_market_snapshot"]
