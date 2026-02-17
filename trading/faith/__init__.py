"""
FAITH - Paper Trading 2DTE Iron Condor Bot
==========================================

Clone of FORTRESS with key differences:
- 2DTE options (more premium than 0DTE)
- Paper trading only (real Tradier data, no order execution)
- $5,000 simulated starting capital
- Max 1 trade per day
- 30% profit target (day trade, close same day)
- PDT compliance (max 3 day trades per rolling 5 business days)
- Symmetric wing enforcement
"""

from .trader import FaithTrader
from .models import FaithConfig, TradingMode

__all__ = ['FaithTrader', 'FaithConfig', 'TradingMode']
