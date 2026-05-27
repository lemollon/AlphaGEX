"""
GEX Profile derived metrics (Trading-Volatility-style).

Pure functions — no FastAPI, no Tradier, no engine state — so they are
trivially unit-testable. Consumed by backend/api/routes/watchtower_routes.py.

NOTE: positioning pressure and structure balance are OUR transparent
approximations of TradingVolatility's proprietary scores, not 1:1 copies.
"""
from typing import Dict, List

# Scale at which |net_gex| is treated as a "full" 1.0 contribution.
# SPY net GEX commonly runs in the low billions; ~6e9 maps a strong day to ~1.0.
NET_GEX_SCALE = 6e9


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calculate_positioning_pressure(
    volume_pressure: float,
    net_gex: float,
    skew_ratio: float,
    net_score: int,
) -> Dict:
    """
    Positioning regime intensity, 0..100, plus a Bullish/Neutral/Bearish label.

    pressure_score = 100 * clamp(
        0.5*|volume_pressure| + 0.3*|net_gex_norm| + 0.2*|skew_norm|, 0, 1)
      where net_gex_norm = clamp(net_gex / NET_GEX_SCALE, -1, 1)
            skew_norm    = clamp(skew_ratio - 1.0, -1, 1)   # 1.0 == symmetric
    Label comes from the sign of net_score (the flow rating's net score).
    """
    net_gex_norm = _clamp(net_gex / NET_GEX_SCALE, -1.0, 1.0)
    skew_norm = _clamp(skew_ratio - 1.0, -1.0, 1.0)
    intensity = (
        0.5 * abs(volume_pressure)
        + 0.3 * abs(net_gex_norm)
        + 0.2 * abs(skew_norm)
    )
    pressure_score = int(round(100 * _clamp(intensity, 0.0, 1.0)))

    if net_score > 0:
        regime_label = "Bullish"
    elif net_score < 0:
        regime_label = "Bearish"
    else:
        regime_label = "Neutral"

    return {
        "regime_label": regime_label,
        "pressure_score": pressure_score,
        "call_vs_put_pressure": round(volume_pressure, 3),
        "summary": (
            f"{regime_label} • pressure {pressure_score}/100 "
            f"(call-vs-put {volume_pressure:+.3f})"
        ),
    }


def calculate_structure_balance(
    strikes: List[Dict],
    spot_price: float,
    expected_move: float,
    horizon_days: int = 7,
) -> Dict:
    """
    Compare resistance gamma (above spot) vs support gamma (below spot) within
    the ±1σ expected-move band.

      resist  = Σ |net_gamma| for spot < strike <= spot + expected_move
      support = Σ |net_gamma| for spot - expected_move <= strike < spot
      balance = (resist - support) / (resist + support)   # -1..+1, ~0 balanced

    `strikes` is a list of dicts with at least 'strike' and 'net_gamma'.
    When expected_move <= 0, fall back to a ±2% band around spot.
    """
    band = expected_move if expected_move and expected_move > 0 else spot_price * 0.02
    upper = spot_price + band
    lower = spot_price - band

    resist = 0.0
    support = 0.0
    for s in strikes:
        strike = s.get("strike")
        ng = s.get("net_gamma", 0.0) or 0.0
        if strike is None:
            continue
        if spot_price < strike <= upper:
            resist += abs(ng)
        elif lower <= strike < spot_price:
            support += abs(ng)

    denom = resist + support
    balance = round((resist - support) / denom, 4) if denom > 0 else 0.0

    if balance > 0.15:
        label = "Resistance-heavy"
    elif balance < -0.15:
        label = "Support-heavy"
    else:
        label = "Balanced"

    return {
        "balance": balance,
        "label": label,
        "resist_gamma": round(resist, 4),
        "support_gamma": round(support, 4),
        "horizon_days": horizon_days,
        "summary": (
            f"{label} ({balance:+.3f}) — support and resistance gamma "
            f"within the {horizon_days}-day expected range."
        ),
    }


def aggregate_net_gamma_by_strike(strike_lists: List[List[Dict]]) -> List[Dict]:
    """
    Sum net_gamma per strike across multiple expirations' strike lists.

    Returns a list of {'strike', 'net_gamma'} dicts sorted ascending by strike.
    """
    totals: Dict[float, float] = {}
    for strikes in strike_lists:
        for s in strikes:
            strike = s.get("strike")
            if strike is None:
                continue
            totals[strike] = totals.get(strike, 0.0) + (s.get("net_gamma", 0.0) or 0.0)
    return [
        {"strike": k, "net_gamma": round(v, 4)}
        for k, v in sorted(totals.items())
    ]
