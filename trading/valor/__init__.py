"""
VALOR - Multi-Instrument Micro Futures Scalping Bot
=====================================================

Named after the legendary Greek hero known for strength and perseverance.

VALOR uses GEX (Gamma Exposure) signals from proxy ETFs to scalp micro futures:
- MES (Micro S&P 500) via SPY GEX
- MNQ (Micro Nasdaq 100) via QQQ GEX
- RTY (Micro Russell 2000) via IWM GEX
- CL  (Micro Crude Oil - MCL) via USO GEX
- NG  (Micro Natural Gas - MNG) via UNG GEX
- MGC (Micro Gold) via GLD GEX

Strategy:
- POSITIVE GAMMA: Mean reversion strategy - fade moves toward flip point
- NEGATIVE GAMMA: Momentum strategy - trade breakouts

Features:
- Per-instrument proxy ETF GEX data with proper scaling
- Per-instrument GEX cache for overnight trading
- Next-expiration GEX logic (daily for SPY/QQQ/IWM, 2-3x/week for USO/UNG/GLD)
- Per-instrument daily loss limits ($2K per instrument, $6K combined)
- Correlation-aware exposure logging
- Trailing stops with breakeven activation
- Fixed Fractional position sizing with ATR adjustment
- Bayesian → ML win probability tracking
- 24/5 trading with n+1 GEX for overnight sessions

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
    FUTURES_TICKERS,
    DEFAULT_VALOR_TICKERS,
    EXPIRATION_SCHEDULES,
    get_ticker_config,
    get_ticker_point_value,
    get_front_month_symbol,
    get_next_gex_expiration,
    get_proxy_etf,
)

from .db import ValorDatabase

from .signals import ValorSignalGenerator, get_gex_data_for_valor

from .executor import TastytradeExecutor

from .trader import ValorTrader, get_valor_trader, run_valor_scan

from .margin_manager import (
    ValorMarginManager,
    MarginZone,
    VALOR_MARGIN_REQUIREMENTS,
    get_margin_requirement,
)

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
    'FUTURES_TICKERS',
    'DEFAULT_VALOR_TICKERS',
    'EXPIRATION_SCHEDULES',
    'get_ticker_config',
    'get_ticker_point_value',
    'get_front_month_symbol',
    'get_next_gex_expiration',
    'get_proxy_etf',
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
    # Margin Manager
    'ValorMarginManager',
    'MarginZone',
    'VALOR_MARGIN_REQUIREMENTS',
    'get_margin_requirement',
]
