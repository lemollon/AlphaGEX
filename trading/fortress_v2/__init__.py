"""
FORTRESS V2 - Modular Iron Condor Trading Bot for SPY
===================================================

A clean rebuild of FORTRESS with:
- Single source of truth (database)
- Modular architecture
- Clear separation of concerns

FORTRESS trades SPY Iron Condors (Bull Put + Bear Call spreads).
One trade per day, 0DTE options.

Usage:
    from trading.fortress_v2 import FortressTrader
    trader = FortressTrader()
    result = trader.run_cycle()

Components:
    - models.py: Data classes (IronCondorPosition, FortressConfig, etc.)
    - db.py: All database operations
    - signals.py: Signal generation (GEX, Prophet, SD-based)
    - executor.py: Order execution (paper/live)
    - trader.py: Main orchestrator
"""

from .models import (
    IronCondorPosition,
    IronCondorSignal,
    PositionStatus,
    FortressConfig,
    TradingMode,
    StrategyPreset,
    STRATEGY_PRESETS,
    DailySummary,
    CENTRAL_TZ,
)

from .db import FortressDatabase

from .signals import SignalGenerator

from .executor import OrderExecutor

from .trader import FortressTrader, run_fortress_v2


__all__ = [
    # Models
    'IronCondorPosition',
    'IronCondorSignal',
    'PositionStatus',
    'FortressConfig',
    'TradingMode',
    'StrategyPreset',
    'STRATEGY_PRESETS',
    'DailySummary',
    'CENTRAL_TZ',
    # Components
    'FortressDatabase',
    'SignalGenerator',
    'OrderExecutor',
    # Main
    'FortressTrader',
    'run_fortress_v2',
]

__version__ = '2.0.0'
