"""
AGAPE-SHIB-PERP - SHIB Perpetual Contract Trading Bot

Named after the biblical Greek term for "unconditional love" (agape),
AGAPE-SHIB-PERP extends AGAPE's disciplined, data-driven crypto trading to
SHIB perpetual contracts.

AGAPE-SHIB-PERP trades SHIB-PERP perpetual contracts 24/7,
using crypto market microstructure signals as GEX equivalents.

Key differences from futures (AGAPE-XRP, AGAPE-BTC):
    - No contract expiration (perpetual)
    - Funding rate payments every 8 hours
    - 24/7/365 trading (no CME hours restriction)
    - Quantity-based sizing (SHIB units, not contracts)

GEX -> Crypto Signal Mapping (same as AGAPE family):
    Gamma Regime     -> Funding Rate regime
    Gamma Walls      -> High OI clusters + Liquidation zones
    Flip Point       -> Max Pain level
    Net GEX          -> Crypto GEX from Deribit options
    Price Magnets    -> Liquidation clusters
    Directional Bias -> Long/Short ratio

Architecture mirrors AGAPE (ETH):
    models.py   -> Config, Position, Signal dataclasses
    db.py       -> PostgreSQL persistence layer
    signals.py  -> Signal generation with Prophet integration
    executor.py -> Perpetual contract order execution
    trader.py   -> Main orchestrator (scan -> signal -> prophet -> execute -> log)
"""
