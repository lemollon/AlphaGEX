"""
ATHENA V2 - Modular Directional Spread Trading Bot
====================================================

A clean rebuild of ATHENA with:
- Single source of truth (database)
- Modular architecture
- Clear separation of concerns

Usage:
    from trading.athena_v2 import ATHENATrader
    trader = ATHENATrader()
    result = trader.run_cycle()

Components:
    - models.py: Data classes (SpreadPosition, ATHENAConfig, etc.)
    - db.py: All database operations
    - signals.py: Signal generation (GEX, ML, Oracle)
    - executor.py: Order execution (paper/live)
    - trader.py: Main orchestrator
"""

from .models import (
    SpreadPosition,
    SpreadType,
    PositionStatus,
    ATHENAConfig,
    TradingMode,
    TradeSignal,
    DailySummary,
    CENTRAL_TZ,
)

from .db import ATHENADatabase

from .signals import SignalGenerator

from .executor import OrderExecutor

from .trader import ATHENATrader, run_athena_v2


__all__ = [
    # Models
    'SpreadPosition',
    'SpreadType',
    'PositionStatus',
    'ATHENAConfig',
    'TradingMode',
    'TradeSignal',
    'DailySummary',
    'CENTRAL_TZ',
    # Components
    'ATHENADatabase',
    'SignalGenerator',
    'OrderExecutor',
    # Main
    'ATHENATrader',
    'run_athena_v2',
]

__version__ = '2.0.0'
