"""
AlphaGEX Trading Module

Core trading components including:
- Mixins: Position sizing, trade execution, position management, performance tracking
- Config: Centralized trading and strategy configuration
- Strategies: Iron condor, spreads, directional trades
- Factory functions for creating traders
"""

from .mixins import (
    PositionSizerMixin,
    TradeExecutorMixin,
    PositionManagerMixin,
    PerformanceTrackerMixin,
)


# Trader factory functions
def get_trader(symbol: str = 'SPY', capital: float = None):
    """
    Factory function to get a configured trader.

    Args:
        symbol: Trading symbol ('SPY', 'SPX', 'QQQ'). Default: 'SPY'
        capital: Starting capital. If None, uses defaults:
                 - SPY: $1,000,000
                 - SPX: $100,000,000
                 - QQQ: $1,000,000

    Returns:
        AutonomousPaperTrader configured for the symbol
    """
    from core.autonomous_paper_trader import AutonomousPaperTrader

    # Default capital based on symbol
    if capital is None:
        capital = {
            'SPY': 1_000_000,
            'SPX': 100_000_000,
            'QQQ': 1_000_000,
        }.get(symbol, 1_000_000)

    return AutonomousPaperTrader(symbol=symbol, capital=capital)


def get_spy_trader(capital: float = 1_000_000):
    """Get a SPY trader with default $1M capital."""
    return get_trader('SPY', capital)


def get_spx_trader(capital: float = 100_000_000):
    """Get an SPX trader with default $100M capital."""
    return get_trader('SPX', capital)


def get_qqq_trader(capital: float = 1_000_000):
    """Get a QQQ trader with default $1M capital."""
    return get_trader('QQQ', capital)


__all__ = [
    # Mixins
    'PositionSizerMixin',
    'TradeExecutorMixin',
    'PositionManagerMixin',
    'PerformanceTrackerMixin',
    # Factory functions
    'get_trader',
    'get_spy_trader',
    'get_spx_trader',
    'get_qqq_trader',
]
