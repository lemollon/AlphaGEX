"""Per-instance and platform sizing limits per master spec section 5.

Account assumptions (master spec section 5):
    Starting capital                : $5,000
    Per-trade risk                  : 1.5%% = $75
    Per-instance (MSTU/TSLL/NVDL)   : $200 each (higher-IV LETFs)
    Per-instance (CONL/AMDL)        : $150 each (lower-volume LETFs)
    Platform total cap              : $750 (15%% of capital)
    Max concurrent positions        : 3 (enforced separately by Gate G10)
    Hard cap per trade              : 2 contracts

V0.3 todo V3-8: convert these absolute-dollar caps to percentage-of-
allocated-capital so sizing scales when capital base grows beyond
the v0.2 research-scale $5K starting point.
"""
from __future__ import annotations

ACCOUNT_STARTING_CAPITAL = 5000.0
PER_TRADE_RISK_PCT = 0.015  # 1.5%%

INSTANCE_ALLOCATIONS: dict[str, float] = {
    "MSTU": 200.0,
    "TSLL": 200.0,
    "NVDL": 200.0,
    "CONL": 150.0,
    "AMDL": 150.0,
}

PLATFORM_TOTAL_CAP = 750.0
HARD_CAP_PER_TRADE = 2


def per_trade_risk_dollars() -> float:
    """1.5%% of starting capital -- the per-trade max-loss budget."""
    return PER_TRADE_RISK_PCT * ACCOUNT_STARTING_CAPITAL


def instance_cap(letf_ticker: str) -> float:
    """Return the per-instance dollar cap for the given LETF, or 0 if unknown."""
    return INSTANCE_ALLOCATIONS.get(letf_ticker.upper(), 0.0)
