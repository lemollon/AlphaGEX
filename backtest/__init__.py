"""Backtesting framework for AlphaGEX trading system."""

from .backtest_framework import BacktestResults, Trade
from .autonomous_backtest_engine import PatternBacktester, get_backtester

__all__ = [
    'BacktestResults',
    'Trade',
    'PatternBacktester',
    'get_backtester',
]
