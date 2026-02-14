"""
AGAPE-BTC-PERP - BTC Perpetual Contract Trading Bot

Named after the biblical Greek term for "unconditional love" (agape),
AGAPE-BTC-PERP extends AGAPE's disciplined, data-driven crypto trading
to Bitcoin perpetual contracts (BTC-PERP).

Unlike AGAPE-BTC which trades CME Micro Bitcoin Futures (/MBT) via tastytrade,
AGAPE-BTC-PERP trades perpetual contracts that never expire and are available
24/7/365. No exchange maintenance windows, no contract rollovers, no expiration.

Key Perpetual Contract Differences:
    - 24/7/365 trading (no CME schedule, no daily maintenance)
    - No contract expiration or rollover
    - Uses quantity (float BTC) not contracts (int)
    - P&L = (current_price - entry_price) * quantity * direction
    - No tastytrade integration - pure crypto-native execution
    - Supports both LONG and SHORT via perpetual mechanism

BTC-PERP Specifications:
    - Ticker: BTC
    - Instrument: BTC-PERP
    - Exchange: perpetual
    - Starting Capital: $25,000
    - Default Quantity: 0.001 BTC (~$80 notional at $80,000)
    - Min Quantity: 0.00001 BTC
    - Max Quantity: 1.0 BTC
    - Tick Size: $0.01
    - Max Open Positions: 3

GEX -> Crypto Signal Mapping (same as AGAPE):
    Gamma Regime     -> Funding Rate regime
    Gamma Walls      -> High OI clusters + Liquidation zones
    Flip Point       -> Max Pain level
    Net GEX          -> Crypto GEX from Deribit options
    Price Magnets    -> Liquidation clusters
    Directional Bias -> Long/Short ratio

Architecture mirrors AGAPE (ETH/BTC):
    models.py   -> Config, Position, Signal dataclasses
    db.py       -> PostgreSQL persistence layer
    signals.py  -> Signal generation with Prophet integration
    executor.py -> Paper/live perpetual order execution
    trader.py   -> Main orchestrator (scan -> signal -> prophet -> execute -> log)
"""
