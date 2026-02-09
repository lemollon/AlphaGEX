"""
VALOR - MES Futures Scalping Bot
====================================

Named after the legendary Greek hero known for strength and perseverance.

VALOR uses GEX (Gamma Exposure) signals to scalp MES (Micro E-mini S&P 500) futures:
- POSITIVE GAMMA: Mean reversion strategy - fade moves toward flip point
- NEGATIVE GAMMA: Momentum strategy - trade breakouts

Features:
- Trailing stops with breakeven activation
- Fixed Fractional position sizing with ATR adjustment
- Bayesian → ML win probability tracking
- 24/5 trading with n+1 GEX for overnight sessions
- Tastytrade API integration

Usage:
    from trading.valor import ValorTrader, run_valor_scan

    # Manual usage
    trader = ValorTrader()
    result = trader.run_scan()

    # Or use the scheduler entry point
    result = run_valor_scan()
"""

from .models import (
    FuturesPosition,
    FuturesSignal,
    ValorConfig,
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

from .db import ValorDatabase

from .signals import ValorSignalGenerator, get_gex_data_for_valor

from .executor import TastytradeExecutor

from .trader import ValorTrader, get_valor_trader, run_valor_scan

__all__ = [
    # Models
    'FuturesPosition',
    'FuturesSignal',
    'ValorConfig',
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
    'ValorDatabase',
    # Signals
    'ValorSignalGenerator',
    'get_gex_data_for_valor',
    # Executor
    'TastytradeExecutor',
    # Trader
    'ValorTrader',
    'get_valor_trader',
    'run_valor_scan',
]
