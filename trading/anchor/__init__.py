"""
ANCHOR - SPX Iron Condor Trading Bot
=======================================

Named after the divine winged horse.
ANCHOR trades SPX Iron Condors with $10 spreads.

Usage:
    from trading.anchor import AnchorTrader
    trader = AnchorTrader()
    result = trader.run_cycle()

Key differences from FORTRESS (SPY):
- Ticker: SPX
- Spread width: $10 (vs $2)
- Strike increments: $5 (vs $1)
- Option symbols: SPXW for weeklies
- Cash-settled (European style)
"""

from .models import (
    IronCondorPosition,
    IronCondorSignal,
    PositionStatus,
    AnchorConfig,
    TradingMode,
    StrategyPreset,
    STRATEGY_PRESETS,
    DailySummary,
    CENTRAL_TZ,
)

from .db import AnchorDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor
from .trader import AnchorTrader, run_anchor

__all__ = [
    'IronCondorPosition',
    'IronCondorSignal',
    'PositionStatus',
    'AnchorConfig',
    'TradingMode',
    'StrategyPreset',
    'STRATEGY_PRESETS',
    'DailySummary',
    'CENTRAL_TZ',
    'AnchorDatabase',
    'SignalGenerator',
    'OrderExecutor',
    'AnchorTrader',
    'run_anchor',
]

__version__ = '1.0.0'
