"""
PROMETHEUS - Box Spread Synthetic Borrowing Bot

Named after the Titan who brought fire (resources) to mankind.
PROMETHEUS provides synthetic capital through box spreads to fuel
Iron Condor volume strategies across ARES, TITAN, and PEGASUS.

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
    PrometheusConfig,
    BorrowingCostAnalysis,
    CapitalDeployment,
    BoxSpreadStatus,
    PositionStatus,
    TradingMode,
)
from .db import PrometheusDatabase
from .signals import BoxSpreadSignalGenerator
from .executor import (
    BoxSpreadExecutor,
    build_occ_symbol,
    get_box_spread_quotes,
    calculate_box_spread_mark_to_market,
)
from .trader import PrometheusTrader

__all__ = [
    # Models
    "BoxSpreadPosition",
    "BoxSpreadSignal",
    "PrometheusConfig",
    "BorrowingCostAnalysis",
    "CapitalDeployment",
    "BoxSpreadStatus",
    "PositionStatus",
    "TradingMode",
    # Core classes
    "PrometheusDatabase",
    "BoxSpreadSignalGenerator",
    "BoxSpreadExecutor",
    "PrometheusTrader",
    # Quote & MTM utilities
    "build_occ_symbol",
    "get_box_spread_quotes",
    "calculate_box_spread_mark_to_market",
]
