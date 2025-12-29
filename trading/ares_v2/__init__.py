"""
ARES V2 - Modular Iron Condor Trading Bot for SPY
===================================================

A clean rebuild of ARES with:
- Single source of truth (database)
- Modular architecture
- Clear separation of concerns

ARES trades SPY Iron Condors (Bull Put + Bear Call spreads).
One trade per day, 0DTE options.

Usage:
    from trading.ares_v2 import ARESTrader
    trader = ARESTrader()
    result = trader.run_cycle()

Components:
    - models.py: Data classes (IronCondorPosition, ARESConfig, etc.)
    - db.py: All database operations
    - signals.py: Signal generation (GEX, Oracle, SD-based)
    - executor.py: Order execution (paper/live)
    - trader.py: Main orchestrator
"""

from .models import (
    IronCondorPosition,
    IronCondorSignal,
    PositionStatus,
    ARESConfig,
    TradingMode,
    StrategyPreset,
    STRATEGY_PRESETS,
    DailySummary,
    CENTRAL_TZ,
)

from .db import ARESDatabase

from .signals import SignalGenerator

from .executor import OrderExecutor

from .trader import ARESTrader, run_ares_v2


__all__ = [
    # Models
    'IronCondorPosition',
    'IronCondorSignal',
    'PositionStatus',
    'ARESConfig',
    'TradingMode',
    'StrategyPreset',
    'STRATEGY_PRESETS',
    'DailySummary',
    'CENTRAL_TZ',
    # Components
    'ARESDatabase',
    'SignalGenerator',
    'OrderExecutor',
    # Main
    'ARESTrader',
    'run_ares_v2',
]

__version__ = '2.0.0'
