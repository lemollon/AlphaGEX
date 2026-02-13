"""
AGAPE-BTC - BTC Micro Futures Trading Bot

Named after the biblical Greek term for "unconditional love" (ἀγάπη),
AGAPE-BTC extends AGAPE's disciplined, data-driven crypto trading to Bitcoin.

AGAPE-BTC trades Micro Bitcoin Futures (/MBT) on CME via tastytrade,
using the same crypto market microstructure signals as AGAPE (ETH).

GEX → Crypto Signal Mapping (same as AGAPE):
    Gamma Regime     → Funding Rate regime
    Gamma Walls      → High OI clusters + Liquidation zones
    Flip Point       → Max Pain level
    Net GEX          → Crypto GEX from Deribit options
    Price Magnets    → Liquidation clusters
    Directional Bias → Long/Short ratio

Architecture mirrors AGAPE (ETH):
    models.py   → Config, Position, Signal dataclasses
    db.py       → PostgreSQL persistence layer
    signals.py  → Signal generation with Prophet integration
    executor.py → tastytrade /MBT order execution
    trader.py   → Main orchestrator (scan → signal → prophet → execute → log)
"""
