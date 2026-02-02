"""
HERACLES - MES Futures Scalping Bot
====================================

Named after the legendary Greek hero known for strength and perseverance.

HERACLES uses GEX (Gamma Exposure) signals to scalp MES (Micro E-mini S&P 500) futures:
- POSITIVE GAMMA: Mean reversion strategy - fade moves toward flip point
- NEGATIVE GAMMA: Momentum strategy - trade breakouts

Features:
- Trailing stops with breakeven activation
- Fixed Fractional position sizing with ATR adjustment
- Bayesian → ML win probability tracking
- 24/5 trading with n+1 GEX for overnight sessions
- Tastytrade API integration

Usage:
    from trading.heracles import HERACLESTrader, run_heracles_scan

    # Manual usage
    trader = HERACLESTrader()
    result = trader.run_scan()

    # Or use the scheduler entry point
    result = run_heracles_scan()
"""

from .models import (
    FuturesPosition,
    FuturesSignal,
    HERACLESConfig,
    TradeDirection,
    GammaRegime,
    PositionStatus,
    SignalSource,
    TradingMode,
    BayesianWinTracker,
    MES_POINT_VALUE,
    MES_TICK_SIZE,
    MES_TICK_VALUE,
)

from .db import HERACLESDatabase

from .signals import HERACLESSignalGenerator, get_gex_data_for_heracles

from .executor import TastytradeExecutor

from .trader import HERACLESTrader, get_heracles_trader, run_heracles_scan

__all__ = [
    # Models
    'FuturesPosition',
    'FuturesSignal',
    'HERACLESConfig',
    'TradeDirection',
    'GammaRegime',
    'PositionStatus',
    'SignalSource',
    'TradingMode',
    'BayesianWinTracker',
    'MES_POINT_VALUE',
    'MES_TICK_SIZE',
    'MES_TICK_VALUE',
    # Database
    'HERACLESDatabase',
    # Signals
    'HERACLESSignalGenerator',
    'get_gex_data_for_heracles',
    # Executor
    'TastytradeExecutor',
    # Trader
    'HERACLESTrader',
    'get_heracles_trader',
    'run_heracles_scan',
]
