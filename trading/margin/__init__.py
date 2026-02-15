"""
Unified Margin Management System for AlphaGEX.

Handles margin calculations across three market types:
  - Stock/Index Futures (CME: ES, NQ, /MBT, etc.)
  - Crypto Futures (CME crypto futures with expiry)
  - Crypto Perpetual Futures (no expiry, funding rate mechanics)

Modules:
  - margin_config: Market-type-aware configuration
  - margin_engine: Core margin calculations (13 metrics)
  - margin_monitor: Background polling, alerts, storage
"""

from trading.margin.margin_config import (
    MarketType,
    MarginMode,
    MarketConfig,
    BotMarginConfig,
    get_bot_margin_config,
    get_default_market_config,
    MARKET_DEFAULTS,
)

from trading.margin.margin_engine import MarginEngine

__all__ = [
    "MarketType",
    "MarginMode",
    "MarketConfig",
    "BotMarginConfig",
    "get_bot_margin_config",
    "get_default_market_config",
    "MARKET_DEFAULTS",
    "MarginEngine",
]
