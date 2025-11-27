# Route modules for AlphaGEX API
#
# These modules are extracted from the monolithic main.py to improve maintainability.
# Each module handles a specific domain of the API.

from . import vix_routes
from . import spx_routes
from . import system_routes
from . import core_routes
from . import trader_routes
from . import backtest_routes
from . import database_routes
from . import gex_routes
from . import gamma_routes
from . import optimizer_routes
from . import ai_routes
from . import probability_routes

__all__ = [
    'vix_routes',
    'spx_routes',
    'system_routes',
    'core_routes',
    'trader_routes',
    'backtest_routes',
    'database_routes',
    'gex_routes',
    'gamma_routes',
    'optimizer_routes',
    'ai_routes',
    'probability_routes',
]
