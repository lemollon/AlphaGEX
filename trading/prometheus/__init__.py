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
from .executor import BoxSpreadExecutor
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
]
