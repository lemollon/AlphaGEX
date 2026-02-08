"""
SOLOMON V2 - Modular Directional Spread Trading Bot
====================================================

A clean rebuild of SOLOMON with:
- Single source of truth (database)
- Modular architecture
- Clear separation of concerns

Usage:
    from trading.solomon_v2 import SolomonTrader
    trader = SolomonTrader()
    result = trader.run_cycle()

Components:
    - models.py: Data classes (SpreadPosition, SolomonConfig, etc.)
    - db.py: All database operations
    - signals.py: Signal generation (GEX, ML, Prophet)
    - executor.py: Order execution (paper/live)
    - trader.py: Main orchestrator
"""

from .models import (
    SpreadPosition,
    SpreadType,
    PositionStatus,
    SolomonConfig,
    TradingMode,
    TradeSignal,
    DailySummary,
    CENTRAL_TZ,
)

from .db import SolomonDatabase

from .signals import SignalGenerator

from .executor import OrderExecutor

from .trader import SolomonTrader, run_solomon_v2


__all__ = [
    # Models
    'SpreadPosition',
    'SpreadType',
    'PositionStatus',
    'SolomonConfig',
    'TradingMode',
    'TradeSignal',
    'DailySummary',
    'CENTRAL_TZ',
    # Components
    'SolomonDatabase',
    'SignalGenerator',
    'OrderExecutor',
    # Main
    'SolomonTrader',
    'run_solomon_v2',
]

__version__ = '2.0.0'
