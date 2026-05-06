"""Per-bot configuration for the SOLOMON / GIDEON 1DTE backtest.

Mirrors live production parameters from trading/solomon_v2/models.py
and trading/gideon/models.py. Risk and capital are research defaults.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    name: str
    ticker: str
    wall_filter_pct: float
    spread_width: int
    min_vix: float
    max_vix: float
    risk_per_trade: float
    starting_capital: float


SOLOMON = BotConfig(
    name="solomon",
    ticker="SPY",
    wall_filter_pct=1.0,
    spread_width=2,
    min_vix=12.0,
    max_vix=35.0,
    risk_per_trade=1000.0,
    starting_capital=100000.0,
)

GIDEON = BotConfig(
    name="gideon",
    ticker="SPY",
    wall_filter_pct=1.0,
    spread_width=3,
    min_vix=12.0,
    max_vix=30.0,
    risk_per_trade=1000.0,
    starting_capital=100000.0,
)

BOT_CONFIGS: dict[str, BotConfig] = {
    "solomon": SOLOMON,
    "gideon": GIDEON,
}
