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
from . import notification_routes
from . import misc_routes
from . import alerts_routes
from . import setups_routes
from . import scanner_routes
from . import autonomous_routes
from . import psychology_routes
from . import ai_intelligence_routes
from . import wheel_routes
from . import export_routes
from . import ml_routes
from . import spx_backtest_routes
from . import ares_routes
from . import athena_routes
from . import pegasus_routes
from . import daily_manna_routes
from . import bot_reports_routes
from . import tastytrade_routes

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
    'notification_routes',
    'misc_routes',
    'alerts_routes',
    'setups_routes',
    'scanner_routes',
    'autonomous_routes',
    'psychology_routes',
    'ai_intelligence_routes',
    'wheel_routes',
    'export_routes',
    'ml_routes',
    'spx_backtest_routes',
    'ares_routes',
    'athena_routes',
    'pegasus_routes',
    'daily_manna_routes',
    'bot_reports_routes',
    'tastytrade_routes',
]
