"""
TITAN - Aggressive SPX Iron Condor Trading Bot
===============================================

Named after the powerful primordial deities of Greek mythology.
TITAN is an aggressive version of PEGASUS that trades daily.

Usage:
    from trading.titan import TITANTrader
    trader = TITANTrader()
    result = trader.run_cycle()

Key differences from PEGASUS:
- Multiple trades per day (with 30min cooldown)
- Higher risk per trade (15% vs 10%)
- Lower win probability threshold (40% vs 50%)
- Closer strikes (0.8 SD vs 1.0 SD)
- Wider spreads ($12 vs $10)
- Faster profit taking (30% vs 50%)
- More positions allowed (10 vs 5)
- Higher VIX tolerance (40 vs 32)
"""

from .models import (
    IronCondorPosition,
    IronCondorSignal,
    PositionStatus,
    TITANConfig,
    TradingMode,
    StrategyPreset,
    STRATEGY_PRESETS,
    DailySummary,
    CENTRAL_TZ,
)

from .db import TITANDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor
from .trader import TITANTrader, run_titan

__all__ = [
    'IronCondorPosition',
    'IronCondorSignal',
    'PositionStatus',
    'TITANConfig',
    'TradingMode',
    'StrategyPreset',
    'STRATEGY_PRESETS',
    'DailySummary',
    'CENTRAL_TZ',
    'TITANDatabase',
    'SignalGenerator',
    'OrderExecutor',
    'TITANTrader',
    'run_titan',
]

__version__ = '1.0.0'
