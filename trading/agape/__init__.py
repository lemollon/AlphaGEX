"""
AGAPE - ETH Micro Futures Trading Bot

Named after the biblical Greek term for "unconditional love" (ἀγάπη),
AGAPE represents steadfast commitment to disciplined, data-driven
crypto trading.

AGAPE trades Micro Ether Futures (/MET) on CME via tastytrade,
using crypto market microstructure signals as the equivalent of
GEX-based analysis used by the equity bots.

GEX → Crypto Signal Mapping:
    Gamma Regime     → Funding Rate regime
    Gamma Walls      → High OI clusters + Liquidation zones
    Flip Point       → Max Pain level
    Net GEX          → Crypto GEX from Deribit options
    Price Magnets    → Liquidation clusters
    Directional Bias → Long/Short ratio

Architecture mirrors FORTRESS V2:
    models.py   → Config, Position, Signal dataclasses
    db.py       → PostgreSQL persistence layer
    signals.py  → Signal generation with Oracle integration
    executor.py → tastytrade /MET order execution
    trader.py   → Main orchestrator (scan → signal → oracle → execute → log)
"""
