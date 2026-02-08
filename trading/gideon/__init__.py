"""
GIDEON - Aggressive Directional Spread Trading Bot
===================================================

GIDEON is an aggressive clone of SOLOMON with relaxed GEX wall filters
and trading parameters to give it more room to trade.

Key differences from SOLOMON:
- 10% wall filter (vs 3%) - trades far from walls
- 40% min win probability (vs 48%)
- 0.5 min R:R ratio (vs 0.8)
- 4% risk per trade (vs 2%)
- 10 max daily trades (vs 5)
- 5 max open positions (vs 3)
- $3 spread width (vs $2)
- 30% profit target (vs 50%)
- 70% stop loss (vs 50%)

Usage:
    from trading.gideon import GideonTrader
    trader = GideonTrader()
    result = trader.run_cycle()

Components:
    - models.py: Data classes (SpreadPosition, GideonConfig, etc.)
    - db.py: All database operations
    - signals.py: Signal generation (GEX, ML, Oracle)
    - executor.py: Order execution (paper/live)
    - trader.py: Main orchestrator
"""

from .models import (
    SpreadPosition,
    SpreadType,
    PositionStatus,
    GideonConfig,
    TradingMode,
    TradeSignal,
    DailySummary,
    CENTRAL_TZ,
)

from .db import GideonDatabase

from .signals import SignalGenerator

from .executor import OrderExecutor

from .trader import GideonTrader, run_icarus


__all__ = [
    # Models
    'SpreadPosition',
    'SpreadType',
    'PositionStatus',
    'GideonConfig',
    'TradingMode',
    'TradeSignal',
    'DailySummary',
    'CENTRAL_TZ',
    # Components
    'GideonDatabase',
    'SignalGenerator',
    'OrderExecutor',
    # Main
    'GideonTrader',
    'run_icarus',
]

__version__ = '1.0.0'
