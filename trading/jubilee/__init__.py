"""
JUBILEE - Box Spread Synthetic Borrowing Bot

Named after the Samson who brought fire (resources) to mankind.
JUBILEE provides synthetic capital through box spreads to fuel
Iron Condor volume strategies across FORTRESS, SAMSON, and ANCHOR.

Key Features:
- Synthetic borrowing via box spreads at near risk-free rates
- Capital deployment to IC bots for volume scaling
- Enhanced transparency for strategy education
- Full audit trail of borrowing costs vs IC returns
- PRODUCTION Tradier quotes for realistic paper trading
- Real-time mark-to-market with actual market prices
"""

from .models import (
    BoxSpreadPosition,
    BoxSpreadSignal,
    JubileeConfig,
    BorrowingCostAnalysis,
    CapitalDeployment,
    BoxSpreadStatus,
    PositionStatus,
    TradingMode,
)
from .db import JubileeDatabase
from .signals import BoxSpreadSignalGenerator
from .executor import (
    BoxSpreadExecutor,
    build_occ_symbol,
    get_box_spread_quotes,
    calculate_box_spread_mark_to_market,
)
from .trader import JubileeTrader

__all__ = [
    # Models
    "BoxSpreadPosition",
    "BoxSpreadSignal",
    "JubileeConfig",
    "BorrowingCostAnalysis",
    "CapitalDeployment",
    "BoxSpreadStatus",
    "PositionStatus",
    "TradingMode",
    # Core classes
    "JubileeDatabase",
    "BoxSpreadSignalGenerator",
    "BoxSpreadExecutor",
    "JubileeTrader",
    # Quote & MTM utilities
    "build_occ_symbol",
    "get_box_spread_quotes",
    "calculate_box_spread_mark_to_market",
]
