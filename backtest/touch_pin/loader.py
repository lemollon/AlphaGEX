"""Load minute-chain quote bars + OI + same-day context for the touch_pin harness.

For (trade_date, expiration_date, target_minute), pulls the minute bar at
target_minute (offset from the first bar of the day) and pivots calls/puts
into per-strike ChainEntry rows. Pulls the single OI snapshot for that
(T, T+1) pair.

Anti-look-ahead helpers vix_close_prior_day() and regime_label_at_open()
use cutoffs strictly before the entry minute.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Dict, Optional

import psycopg2

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChainEntry:
    strike: float
    call_bid: float
    call_ask: float
    put_bid: float
    put_ask: float
    call_volume: int = 0
    put_volume: int = 0
    call_oi: int = 0
    put_oi: int = 0

    @property
    def call_mid(self) -> float:
        return 0.5 * (self.call_bid + self.call_ask)

    @property
    def put_mid(self) -> float:
        return 0.5 * (self.put_bid + self.put_ask)

    def call_valid(self) -> bool:
        return self.call_bid > 0 and self.call_ask > 0 and self.call_ask >= self.call_bid

    def put_valid(self) -> bool:
        return self.put_bid > 0 and self.put_ask > 0 and self.put_ask >= self.put_bid


@dataclass(frozen=True)
class MinuteSnapshot:
    trade_date: dt.date
    expiration_date: dt.date
    target_minute: int
    bar_time: Optional[dt.datetime]
    chain: Dict[float, ChainEntry]


def load_minute_chain(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    target_minute: int,
) -> Optional[MinuteSnapshot]:
    """Pull the chain at (trade_date, expiration, target_minute) plus OI.

    Returns None if no bars exist for that minute.
    """
    chain_rows = _query_chain_at_minute(db_url, trade_date, expiration_date, target_minute)
    if not chain_rows:
        return None
    oi_rows = _query_oi(db_url, trade_date, expiration_date)
    return _pivot(trade_date, expiration_date, target_minute, chain_rows, oi_rows)


def _query_chain_at_minute(db_url, trade_date, expiration_date, target_minute):
    sql = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT strike, "right", bar_time, bid, ask, volume
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time = first_bar.t0 + (%s * INTERVAL '1 minute')
        ORDER BY strike, "right"
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (trade_date, expiration_date,
                          trade_date, expiration_date, target_minute))
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def _query_oi(db_url, trade_date, expiration_date):
    sql = """
        SELECT strike, "right", open_interest
        FROM helios_options_oi
        WHERE trade_date = %s AND expiration_date = %s
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (trade_date, expiration_date))
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def _pivot(trade_date, expiration_date, target_minute, chain_rows, oi_rows):
    by_strike: Dict[float, dict] = {}
    bar_time: Optional[dt.datetime] = None
    for strike, right, bt, bid, ask, volume in chain_rows:
        bar_time = bt if bar_time is None else bar_time
        k = float(strike)
        e = by_strike.setdefault(k, {
            "call_bid": 0.0, "call_ask": 0.0,
            "put_bid": 0.0, "put_ask": 0.0,
            "call_volume": 0, "put_volume": 0,
        })
        bid_v = float(bid) if bid is not None else 0.0
        ask_v = float(ask) if ask is not None else 0.0
        vol_v = int(volume) if volume is not None else 0
        if right == "C":
            e["call_bid"] = bid_v
            e["call_ask"] = ask_v
            e["call_volume"] = vol_v
        else:
            e["put_bid"] = bid_v
            e["put_ask"] = ask_v
            e["put_volume"] = vol_v

    oi_by_strike: Dict[float, dict] = {}
    for strike, right, oi in oi_rows:
        k = float(strike)
        oi_e = oi_by_strike.setdefault(k, {"call_oi": 0, "put_oi": 0})
        if right == "C":
            oi_e["call_oi"] = int(oi)
        else:
            oi_e["put_oi"] = int(oi)

    chain: Dict[float, ChainEntry] = {}
    for k, q in by_strike.items():
        oi = oi_by_strike.get(k, {"call_oi": 0, "put_oi": 0})
        chain[k] = ChainEntry(
            strike=k,
            call_bid=q["call_bid"], call_ask=q["call_ask"],
            put_bid=q["put_bid"], put_ask=q["put_ask"],
            call_volume=q["call_volume"], put_volume=q["put_volume"],
            call_oi=oi["call_oi"], put_oi=oi["put_oi"],
        )

    return MinuteSnapshot(
        trade_date=trade_date,
        expiration_date=expiration_date,
        target_minute=target_minute,
        bar_time=bar_time,
        chain=chain,
    )


def vix_close_prior_day(db_url: str, trade_date: dt.date) -> Optional[float]:
    """Prior-day VIX close (anti-look-ahead) from vix_history."""
    sql = """
        SELECT close
        FROM vix_history
        WHERE trade_date < %s
        ORDER BY trade_date DESC
        LIMIT 1
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (trade_date,))
        row = cur.fetchone()
        cur.close()
        return float(row[0]) if row else None
    finally:
        conn.close()


def regime_label_at_open(db_url: str, trade_date: dt.date) -> Optional[str]:
    """Latest regime_signals row with timestamp <= T 13:30 UTC (= EDT open).

    13:30 UTC is BEFORE both EDT 09:30 (= 13:30 UTC) and EST 09:30 (= 14:30 UTC),
    so this cutoff never leaks future state on day T regardless of DST.
    """
    cutoff = dt.datetime.combine(trade_date, dt.time(13, 30))
    sql = """
        SELECT primary_regime_type
        FROM regime_signals
        WHERE timestamp <= %s
        ORDER BY timestamp DESC
        LIMIT 1
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (cutoff,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    finally:
        conn.close()
