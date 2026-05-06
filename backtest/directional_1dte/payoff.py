"""Hold-to-expiration intrinsic-value payoff for vertical debit spreads."""


def compute_payoff(
    spread_type: str,
    long_strike: float,
    short_strike: float,
    spot_at_expiry: float,
) -> float:
    """Per-share payoff at expiration. Bounded by [0, abs(short_strike - long_strike)]."""
    if spread_type == "BULL_CALL":
        return max(0.0, min(spot_at_expiry, short_strike) - long_strike)
    if spread_type == "BEAR_PUT":
        return max(0.0, long_strike - max(spot_at_expiry, short_strike))
    raise ValueError(f"Unknown spread_type: {spread_type}")
