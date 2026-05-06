"""ORAT postgres loaders. Read-only. Connection per call (no pool).

All functions return None for missing data rather than raising — the engine
records the absence as a categorized skip, never silently drops the day.
"""
import datetime as dt
import os
from typing import Optional

import pandas as pd
import psycopg2


def _conn():
    url = os.environ.get("ORAT_DATABASE_URL")
    if not url:
        raise RuntimeError("ORAT_DATABASE_URL not set")
    return psycopg2.connect(url)


def load_trading_days(start: dt.date, end: dt.date, ticker: str = "SPY") -> list[dt.date]:
    """Distinct trade_date for ticker between [start, end] inclusive."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT trade_date
            FROM orat_options_eod
            WHERE ticker = %s AND trade_date BETWEEN %s AND %s
            ORDER BY trade_date
            """,
            (ticker, start, end),
        )
        return [r[0] for r in cur.fetchall()]


def load_chain(trade_date: dt.date, ticker: str = "SPY") -> pd.DataFrame:
    """All option rows for ticker on trade_date, indexed by (expiration_date, strike)."""
    with _conn() as c:
        df = pd.read_sql(
            """
            SELECT trade_date, expiration_date, strike,
                   call_bid, call_ask, call_mid,
                   put_bid, put_ask, put_mid,
                   underlying_price, dte
            FROM orat_options_eod
            WHERE ticker = %s AND trade_date = %s
            """,
            c,
            params=(ticker, trade_date),
        )
    if df.empty:
        return df
    return df.set_index(["expiration_date", "strike"])


def load_vix(trade_date: dt.date) -> Optional[float]:
    """VIX close for trade_date or None."""
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT close FROM vix_history WHERE trade_date = %s", (trade_date,))
        row = cur.fetchone()
    return float(row[0]) if row else None


def load_gex_walls(trade_date: dt.date, ticker: str = "SPY") -> Optional[dict]:
    """Read precomputed call_wall, put_wall, spot_close from gex_structure_daily."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT call_wall, put_wall, spot_close
            FROM gex_structure_daily
            WHERE symbol = %s AND trade_date = %s
            """,
            (ticker, trade_date),
        )
        row = cur.fetchone()
    if not row or row[0] is None or row[1] is None or row[2] is None:
        return None
    return {
        "call_wall": float(row[0]),
        "put_wall": float(row[1]),
        "spot": float(row[2]),
    }
