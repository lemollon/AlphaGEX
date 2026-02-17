"""
GRACE - Paper Trading 1DTE Iron Condor Bot
==========================================

Clone of FAITH with key differences:
- 1DTE options (for side-by-side comparison with FAITH's 2DTE)
- Paper trading only (real Tradier data, no order execution)
- $5,000 simulated starting capital
- Max 1 trade per day
- 30% profit target (day trade, close same day)
- PDT compliance (max 3 day trades per rolling 5 business days)
- Symmetric wing enforcement
"""

from .trader import GraceTrader
from .models import GraceConfig, TradingMode

__all__ = ['GraceTrader', 'GraceConfig', 'TradingMode']
