"""Replay option-mid loader.

Primary: helios_options_intraday minute bars (if populated).
Fallback: Black-Scholes synthetic mid via quant.bs.bs_price with sigma = vix/100.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass
from typing import Optional

import psycopg2

from quant.bs import bs_price

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerticalMids:
    long_mid: float
    short_mid: float
    debit: float


def load_minute_marks(
    *,
    trade_date: dt.date,
    expiration: dt.date,
    long_strike: float,
    short_strike: float,
    is_call: bool,
    db_url: Optional[str] = None,
) -> dict:
    """Return {minutes_since_open: debit} for the day, if available."""
    url = db_url or os.environ["DATABASE_URL"]
    side = "C" if is_call else "P"
    try:
        with psycopg2.connect(url) as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    SELECT
                        EXTRACT(EPOCH FROM (bar_time - (bar_time::date + INTERVAL '8 hours 30 minutes'))) / 60 AS minute,
                        strike, mid
                    FROM helios_options_intraday
                    WHERE bar_time::date = %s
                      AND expiration_date = %s
                      AND option_type = %s
                      AND strike IN (%s, %s)
                    ORDER BY bar_time ASC, strike ASC
                    """,
                    (trade_date, expiration, side, long_strike, short_strike),
                )
                rows = c.fetchall()
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        return {}
    except Exception:
        return {}
    if not rows:
        return {}

    by_minute = {}
    for minute, strike, mid in rows:
        bucket = by_minute.setdefault(int(minute), {})
        bucket[float(strike)] = float(mid)
    out = {}
    for minute, mids in by_minute.items():
        if long_strike in mids and short_strike in mids:
            out[minute] = mids[long_strike] - mids[short_strike]
    return out


def synthetic_vertical(
    *,
    spot: float,
    long_strike: float,
    short_strike: float,
    is_call: bool,
    t_years: float,
    sigma: float,
    r: float = 0.05,
) -> VerticalMids:
    long_p = bs_price(spot, long_strike, t_years, sigma, is_call, r)
    short_p = bs_price(spot, short_strike, t_years, sigma, is_call, r)
    debit = long_p - short_p
    return VerticalMids(long_mid=long_p, short_mid=short_p, debit=debit)
