"""Strike selection and chain debit lookup for vertical debit spreads."""
from typing import Optional


def select_strikes(spot: float, direction: str, width: int) -> tuple[float, float]:
    """ATM long, OTM short. Mirrors solomon_v2/signals.py:calculate_spread_strikes."""
    long_strike = float(round(spot))
    if direction == "BULLISH":
        return long_strike, long_strike + width
    if direction == "BEARISH":
        return long_strike, long_strike - width
    raise ValueError(f"Unknown direction: {direction}")


def lookup_debit(chain, expiration, long_strike, short_strike, spread_type) -> Optional[dict]:
    """Return {debit, long_mid, short_mid, long_bid, long_ask, short_bid, short_ask}
    or None if either strike is missing or bid>ask data corruption."""
    try:
        long_row = chain.loc[(expiration, long_strike)]
        short_row = chain.loc[(expiration, short_strike)]
    except KeyError:
        return None

    if spread_type == "BULL_CALL":
        bid_col, ask_col, mid_col = "call_bid", "call_ask", "call_mid"
    elif spread_type == "BEAR_PUT":
        bid_col, ask_col, mid_col = "put_bid", "put_ask", "put_mid"
    else:
        return None

    long_bid, long_ask, long_mid = long_row[bid_col], long_row[ask_col], long_row[mid_col]
    short_bid, short_ask, short_mid = short_row[bid_col], short_row[ask_col], short_row[mid_col]

    # Reject corrupt rows where bid > ask
    if long_bid is not None and long_ask is not None and float(long_bid) > float(long_ask):
        return None
    if short_bid is not None and short_ask is not None and float(short_bid) > float(short_ask):
        return None
    if long_mid is None or short_mid is None:
        return None

    debit = float(long_mid) - float(short_mid)
    return {
        "debit": debit,
        "long_mid": float(long_mid),
        "short_mid": float(short_mid),
        "long_bid": float(long_bid) if long_bid is not None else None,
        "long_ask": float(long_ask) if long_ask is not None else None,
        "short_bid": float(short_bid) if short_bid is not None else None,
        "short_ask": float(short_ask) if short_ask is not None else None,
    }
