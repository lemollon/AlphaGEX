"""Load one 0DTE session's 1-min option bars + OI in a single DB pass."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Key = Tuple[float, str]  # (strike, right)

@dataclass
class DayChain:
    trade_date: dt.date
    bars: Dict[int, Dict[Key, Tuple[float, float]]] = field(default_factory=dict)
    oi: Dict[Key, int] = field(default_factory=dict)

    def minutes(self) -> List[int]:
        return sorted(self.bars.keys())

    def mid(self, minute: int, strike: float, right: str) -> Optional[float]:
        q = self.bars.get(minute, {}).get((strike, right))
        if not q:
            return None
        bid, ask = q
        if bid is None or ask is None or bid <= 0 or ask < bid:
            return None
        return (bid + ask) / 2.0

    def quote(self, minute: int, strike: float, right: str) -> Optional[Tuple[float, float]]:
        return self.bars.get(minute, {}).get((strike, right))


def bars_to_daychain(trade_date, rows, oi) -> DayChain:
    """rows: iterable of (minute:int, strike:float, right:str, bid:float, ask:float)."""
    day = DayChain(trade_date=trade_date, oi=dict(oi))
    for minute, strike, right, bid, ask in rows:
        day.bars.setdefault(int(minute), {})[(float(strike), right)] = (
            None if bid is None else float(bid),
            None if ask is None else float(ask),
        )
    return day


def load_day(conn, trade_date: dt.date, dte: int = 0) -> Optional[DayChain]:
    """Load the chain for one session. dte=0 -> same-day (0DTE) expiration
    (expiration_date = trade_date); dte=1 -> next-day (1DTE) expiration
    (expiration_date > trade_date)."""
    op = "=" if dte == 0 else ">"
    sql = f"""
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0 FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date {op} %s
        )
        SELECT EXTRACT(EPOCH FROM (b.bar_time - first_bar.t0))::int / 60 AS minute,
               b.strike, b."right", b.bid, b.ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date {op} %s
        ORDER BY minute, b.strike, b."right"
    """
    oi_sql = f"""
        SELECT strike, "right", open_interest FROM helios_options_oi
        WHERE trade_date = %s AND expiration_date {op} %s
    """
    cur = conn.cursor()
    cur.execute(sql, (trade_date, trade_date, trade_date, trade_date))
    rows = cur.fetchall()
    cur.execute(oi_sql, (trade_date, trade_date))
    oi = {(float(k), r): int(o) for k, r, o in cur.fetchall()}
    cur.close()
    if not rows:
        return None
    return bars_to_daychain(trade_date, rows, oi)
