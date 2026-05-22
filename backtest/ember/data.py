# backtest/ember/data.py
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from backtest.ember.dbutil import db_cursor
from quant.bs import DEFAULT_R, bs_delta, derive_spot_from_parity, implied_vol
from backtest.ember.models import DayChain, MinuteChain, Quote

# Minutes since 09:30 ET, computed in the America/New_York wall clock.
_DAY_ROWS_SQL = """
    SELECT
        (EXTRACT(EPOCH FROM (
            (bar_time AT TIME ZONE 'America/New_York')
            - date_trunc('day', bar_time AT TIME ZONE 'America/New_York')
            - INTERVAL '9 hours 30 minutes'
        )) / 60)::int AS minute,
        strike::float8 AS strike,
        "right"        AS right,
        bid::float8    AS bid,
        ask::float8    AS ask,
        close::float8  AS close
    FROM helios_options_intraday
    WHERE trade_date = %s
      AND (expiration_date - trade_date) = 1
    ORDER BY minute, strike
"""

_DATES_SQL = """
    SELECT DISTINCT trade_date
    FROM helios_options_intraday
    WHERE (expiration_date - trade_date) = 1
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date
"""

_RANGE_ROWS_SQL = """
    SELECT
        trade_date,
        (EXTRACT(EPOCH FROM (
            (bar_time AT TIME ZONE 'America/New_York')
            - date_trunc('day', bar_time AT TIME ZONE 'America/New_York')
            - INTERVAL '9 hours 30 minutes'
        )) / 60)::int AS minute,
        strike::float8 AS strike,
        "right"        AS right,
        bid::float8    AS bid,
        ask::float8    AS ask,
        close::float8  AS close
    FROM helios_options_intraday
    WHERE (expiration_date - trade_date) = 1
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, minute, strike
"""


def query_day_rows(trade_date: dt.date, db_url: str | None = None, *, conn=None) -> List[dict]:
    with db_cursor(db_url, conn, dict_rows=True) as c:
        c.execute(_DAY_ROWS_SQL, (trade_date,))
        return [dict(r) for r in c.fetchall()]


def query_range_rows(start: dt.date, end: dt.date, db_url: str) -> List[dict]:
    """All 1DTE rows in [start, end] in a single query (rows include trade_date)."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(_RANGE_ROWS_SQL, (start, end))
            return [dict(r) for r in c.fetchall()]


def list_trade_dates(db_url: str | None = None, start: dt.date = None, end: dt.date = None, *, conn=None) -> List[dt.date]:
    with db_cursor(db_url, conn) as c:
        c.execute(_DATES_SQL, (start, end))
        return [r[0] for r in c.fetchall()]


def t_years(trade_date: dt.date, expiration: dt.date, minute: int) -> float:
    """Calendar time from the given minute (09:30 ET + minute) to 16:00 ET on expiry, in years."""
    bar = dt.datetime.combine(trade_date, dt.time(9, 30)) + dt.timedelta(minutes=minute)
    expiry_close = dt.datetime.combine(expiration, dt.time(16, 0))
    seconds = (expiry_close - bar).total_seconds()
    return max(seconds, 0.0) / (365.0 * 24 * 3600)


def build_day_chain(trade_date: dt.date, expiration: dt.date, rows: List[dict]) -> DayChain:
    """Pure transform: rows -> DayChain. Derives spot per minute via put-call parity.

    A minute is kept only if it has at least one strike with BOTH a call and a put
    (needed to derive spot)."""
    by_minute: Dict[int, Dict[Tuple[float, str], Quote]] = {}
    for r in rows:
        minute = int(r["minute"])
        if minute < 0 or minute > 390:
            continue
        q = Quote(bid=float(r["bid"] or 0.0), ask=float(r["ask"] or 0.0), close=float(r["close"] or 0.0))
        by_minute.setdefault(minute, {})[(float(r["strike"]), r["right"])] = q

    minutes: Dict[int, MinuteChain] = {}
    for minute, quotes in by_minute.items():
        ty = t_years(trade_date, expiration, minute)
        # find strikes that have both C and P
        strikes = {k[0] for k in quotes}
        paired = [s for s in strikes if (s, "C") in quotes and (s, "P") in quotes]
        if not paired:
            continue
        atm = min(paired, key=lambda s: abs(quotes[(s, "C")].mid - quotes[(s, "P")].mid))
        spot = derive_spot_from_parity(
            quotes[(atm, "C")].mid, quotes[(atm, "P")].mid, atm, t_years=ty, r=DEFAULT_R
        )
        minutes[minute] = MinuteChain(minute=minute, spot=spot, quotes=quotes)

    return DayChain(trade_date=trade_date, expiration=expiration, minutes=minutes)


def build_day_chains_from_range(rows: List[dict]) -> Dict[dt.date, DayChain]:
    """Group range rows by trade_date and build one DayChain per day (expiry = day+1)."""
    by_date: Dict[dt.date, List[dict]] = {}
    for r in rows:
        by_date.setdefault(r["trade_date"], []).append(r)
    return {
        td: build_day_chain(td, td + dt.timedelta(days=1), day_rows)
        for td, day_rows in by_date.items()
    }


def delta_at(day: DayChain, minute: int, strike: float, right: str) -> Optional[float]:
    """Black-Scholes delta for one option at a minute, or None if IV won't solve."""
    mc = day.minutes.get(minute)
    if not mc:
        return None
    q = mc.quotes.get((strike, right))
    if not q:
        return None
    ty = t_years(day.trade_date, day.expiration, minute)
    is_call = right == "C"
    sigma = implied_vol(q.mid, mc.spot, strike, ty, is_call)
    if sigma is None:
        return None
    return bs_delta(mc.spot, strike, ty, sigma, is_call)


def load_day(trade_date: dt.date, db_url: str, expiration: Optional[dt.date] = None) -> DayChain:
    rows = query_day_rows(trade_date, db_url)
    exp = expiration or (trade_date + dt.timedelta(days=1))
    return build_day_chain(trade_date, exp, rows)
