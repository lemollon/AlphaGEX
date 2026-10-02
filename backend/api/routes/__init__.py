"""Active AlphaGEX API routes.

AlphaGEX runtime is intentionally limited to VALOR and active crypto perpetuals.
SpreadWorks and IronForge are separate protected projects and are not imported here.
"""

from . import tastytrade_routes
from . import valor_routes
from . import agape_eth_perp_routes
from . import agape_sol_perp_routes
from . import agape_avax_perp_routes
from . import agape_btc_perp_routes
from . import agape_xrp_perp_routes
from . import agape_doge_perp_routes
from . import agape_perpetuals_trades_routes
from . import perp_exit_optimizer_routes
from . import unified_metrics_routes

__all__ = [
    "tastytrade_routes",
    "valor_routes",
    "agape_eth_perp_routes",
    "agape_sol_perp_routes",
    "agape_avax_perp_routes",
    "agape_btc_perp_routes",
    "agape_xrp_perp_routes",
    "agape_doge_perp_routes",
    "agape_perpetuals_trades_routes",
    "perp_exit_optimizer_routes",
    "unified_metrics_routes",
]
