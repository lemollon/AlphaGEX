"""
PEGASUS - SPX Iron Condor Trading Bot
=======================================

Named after the divine winged horse.
PEGASUS trades SPX Iron Condors with $10 spreads.

Usage:
    from trading.pegasus import PEGASUSTrader
    trader = PEGASUSTrader()
    result = trader.run_cycle()

Key differences from ARES (SPY):
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
    PEGASUSConfig,
    TradingMode,
    StrategyPreset,
    STRATEGY_PRESETS,
    DailySummary,
    CENTRAL_TZ,
)

from .db import PEGASUSDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor
from .trader import PEGASUSTrader, run_pegasus

__all__ = [
    'IronCondorPosition',
    'IronCondorSignal',
    'PositionStatus',
    'PEGASUSConfig',
    'TradingMode',
    'StrategyPreset',
    'STRATEGY_PRESETS',
    'DailySummary',
    'CENTRAL_TZ',
    'PEGASUSDatabase',
    'SignalGenerator',
    'OrderExecutor',
    'PEGASUSTrader',
    'run_pegasus',
]

__version__ = '1.0.0'
