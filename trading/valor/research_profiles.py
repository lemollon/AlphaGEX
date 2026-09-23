"""Research-only contract profiles for VALOR.

This module is intentionally not wired into the live trader.  It captures the
first evidence-based strategy split from the September 2026 paper run so the
research branch can test contract-specific behavior without changing production.
"""

from dataclasses import dataclass
from typing import Dict

from trading.valor.models import FUTURES_TICKERS


@dataclass(frozen=True)
class ValorResearchProfile:
    ticker: str
    entry_mode: str
    use_gex_direction: bool
    use_sar: bool
    min_hold_minutes: int
    notes: str


RESEARCH_PROFILES: Dict[str, ValorResearchProfile] = {
    "MES": ValorResearchProfile(
        ticker="MES",
        entry_mode="WALL_OR_REGIME_RESEARCH",
        use_gex_direction=False,
        use_sar=False,
        min_hold_minutes=0,
        notes=(
            "Current positive-gamma flip fade is one-sided SHORT and has negative "
            "5/15/30/60-minute raw edge. Do not simply reverse; test wall rejection, "
            "trend, and GEX-as-regime-only alternatives."
        ),
    ),
    "MNQ": ValorResearchProfile(
        ticker="MNQ",
        entry_mode="KEEP_DIRECTION_RESEARCH_EXIT",
        use_gex_direction=True,
        use_sar=False,
        min_hold_minutes=30,
        notes=(
            "LONG direction has positive raw forward edge, strongest at longer horizons. "
            "Research should preserve direction while replacing SAR / early no-loss exits."
        ),
    ),
    "MGC": ValorResearchProfile(
        ticker="MGC",
        entry_mode="CONTROL_CURRENT_GEX",
        use_gex_direction=True,
        use_sar=True,
        min_hold_minutes=0,
        notes=(
            "Profitable control instrument. Preserve current GEX logic initially and use "
            "it as the benchmark for changes elsewhere."
        ),
    ),
    "NG": ValorResearchProfile(
        ticker="NG",
        entry_mode="GEX_REGIME_ONLY",
        use_gex_direction=False,
        use_sar=False,
        min_hold_minutes=0,
        notes=(
            "UNG fixed-scale flip mapping is structurally mismatched to MNG and observed "
            "raw edge does not clear modeled costs. Test futures-native volatility / breakout "
            "logic with GEX only as a regime filter."
        ),
    ),
    "RTY": ValorResearchProfile(
        ticker="RTY",
        entry_mode="GEX_REGIME_ONLY",
        use_gex_direction=False,
        use_sar=False,
        min_hold_minutes=0,
        notes=(
            "Observed SHORT edge is small relative to transaction costs. Test IWM GEX as "
            "context while using futures-native wall/breakout/reversion triggers."
        ),
    ),
    "CL": ValorResearchProfile(
        ticker="CL",
        entry_mode="QUARANTINED_RESEARCH",
        use_gex_direction=False,
        use_sar=False,
        min_hold_minutes=0,
        notes="Keep quarantined until crude-specific price/event logic is backtested.",
    ),
}


def round_trip_cost_points(
    ticker: str,
    fee_per_contract: float = 3.0,
    slippage_ticks_each_side: float = 1.0,
) -> float:
    """Approximate points required to cover fees plus entry/exit slippage."""
    cfg = FUTURES_TICKERS[ticker]
    point_value = float(cfg["point_value"])
    tick_size = float(cfg["tick_size"])
    return (fee_per_contract / point_value) + (2.0 * slippage_ticks_each_side * tick_size)


def fee_aware_breakeven_stop(
    ticker: str,
    entry_price: float,
    direction: str,
    fee_per_contract: float = 3.0,
    slippage_ticks_each_side: float = 1.0,
) -> float:
    """Return a stop price that is approximately net-flat after modeled costs."""
    offset = round_trip_cost_points(
        ticker,
        fee_per_contract=fee_per_contract,
        slippage_ticks_each_side=slippage_ticks_each_side,
    )
    if direction.upper() == "LONG":
        return entry_price + offset
    if direction.upper() == "SHORT":
        return entry_price - offset
    raise ValueError(f"Unsupported direction: {direction}")
