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


class BulkLoaders:
    """Preload all data in 3 queries, serve from memory.

    For full-range backtests this is ~100x faster than connection-per-call:
    1239 trading days * 2 bots * 4 ORAT queries each = ~10k connections becomes 3.

    Memory budget: ~2-3M chain rows × ~50 bytes ≈ 150 MB.
    """

    def __init__(self, start: dt.date, end: dt.date, ticker: str = "SPY",
                 max_dte: int = 4):
        print(f"  bulk-loading SPY chains ({start} -> {end}, dte<={max_dte})...",
              flush=True)
        self._chains_by_date = self._load_all_chains(start, end, ticker, max_dte)
        print(f"  bulk-loading walls + vix...", flush=True)
        self._walls_by_date = self._load_all_walls(start, end, ticker)
        self._vix_by_date = self._load_all_vix(start, end)
        self._trading_days = sorted(self._chains_by_date.keys())
        print(f"  loaded {len(self._trading_days)} trading days, "
              f"{len(self._walls_by_date)} wall snapshots, "
              f"{len(self._vix_by_date)} vix readings.", flush=True)

    @staticmethod
    def _load_all_chains(start, end, ticker, max_dte):
        with _conn() as c:
            df = pd.read_sql(
                """
                SELECT trade_date, expiration_date, strike,
                       call_bid, call_ask, call_mid,
                       put_bid, put_ask, put_mid,
                       underlying_price, dte
                FROM orat_options_eod
                WHERE ticker = %s AND trade_date BETWEEN %s AND %s
                  AND dte BETWEEN 0 AND %s
                  AND expiration_date IS NOT NULL
                  AND strike IS NOT NULL
                """,
                c,
                params=(ticker, start, end, max_dte),
            )
        if df.empty:
            return {}
        # Normalize date columns to python date for dict-key lookup
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        df["expiration_date"] = pd.to_datetime(df["expiration_date"]).dt.date
        result = {}
        for d, group in df.groupby("trade_date", sort=False):
            chain = group.drop(columns=["trade_date"]).set_index(["expiration_date", "strike"])
            result[d] = chain
        return result

    @staticmethod
    def _load_all_walls(start, end, ticker):
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date, call_wall, put_wall, spot_close
                FROM gex_structure_daily
                WHERE symbol = %s AND trade_date BETWEEN %s AND %s
                """,
                (ticker, start, end),
            )
            rows = cur.fetchall()
        result = {}
        for r in rows:
            if r[1] is None or r[2] is None or r[3] is None:
                continue
            result[r[0]] = {
                "call_wall": float(r[1]),
                "put_wall": float(r[2]),
                "spot": float(r[3]),
            }
        return result

    @staticmethod
    def _load_all_vix(start, end):
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT trade_date, close FROM vix_history WHERE trade_date BETWEEN %s AND %s",
                (start, end),
            )
            return {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}

    def load_trading_days(self, start, end, ticker="SPY"):
        return [d for d in self._trading_days if start <= d <= end]

    def load_chain(self, d, ticker="SPY"):
        return self._chains_by_date.get(d, pd.DataFrame())

    def load_vix(self, d):
        return self._vix_by_date.get(d)

    def load_gex_walls(self, d, ticker="SPY"):
        return self._walls_by_date.get(d)
