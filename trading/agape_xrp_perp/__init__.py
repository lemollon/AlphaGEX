"""
AGAPE-XRP-PERP - XRP Perpetual Contract Trading Bot

Named after the biblical Greek term for "unconditional love" (agape),
AGAPE-XRP-PERP extends AGAPE's disciplined, data-driven crypto trading
to XRP perpetual contracts (perps).

Unlike the CME-based AGAPE-XRP futures bot, AGAPE-XRP-PERP trades
perpetual contracts with NO expiration date, 24/7/365 availability,
and quantity-based position sizing (float XRP units instead of integer contracts).

Key Perpetual Differences:
    - No CME / tastytrade integration (exchange-agnostic perpetuals)
    - 24/7/365 trading: no daily maintenance, no weekend closures
    - No contract expiration or roll management
    - Position sizing uses `quantity` (float XRP) not `contracts` (int)
    - P&L formula: (current_price - entry_price) * quantity * direction
    - Position ID prefix: "AGAPE-XRP-PERP-"
    - Starting capital: $9,000
    - Default quantity: 100.0 XRP

GEX -> Crypto Signal Mapping (same as AGAPE family):
    Gamma Regime     -> Funding Rate regime
    Gamma Walls      -> High OI clusters + Liquidation zones
    Flip Point       -> Max Pain level
    Net GEX          -> Crypto GEX from Deribit options
    Price Magnets    -> Liquidation clusters
    Directional Bias -> Long/Short ratio

Architecture mirrors AGAPE-XRP (Futures):
    models.py   -> Config, Position, Signal dataclasses (quantity-based)
    db.py       -> PostgreSQL persistence layer (quantity FLOAT columns)
    signals.py  -> Signal generation with Prophet integration
    executor.py -> Paper/live perpetual order execution (no tastytrade)
    trader.py   -> Main orchestrator (scan -> signal -> prophet -> execute -> log)
"""
