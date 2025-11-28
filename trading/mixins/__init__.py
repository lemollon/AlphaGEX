"""
Autonomous Trader Module - Decomposed Components

This module contains the decomposed components of the autonomous paper trader:
- PositionSizerMixin: Kelly criterion position sizing calculations
- TradeExecutorMixin: Strategy execution (iron condor, spreads, etc.)
- PositionManagerMixin: Exit logic, position updates
- PerformanceTrackerMixin: Equity snapshots, statistics

The main AutonomousPaperTrader class combines all these mixins.
"""

from .position_sizer import PositionSizerMixin
from .trade_executor import TradeExecutorMixin
from .position_manager import PositionManagerMixin
from .performance_tracker import PerformanceTrackerMixin

__all__ = [
    'PositionSizerMixin',
    'TradeExecutorMixin',
    'PositionManagerMixin',
    'PerformanceTrackerMixin',
]
