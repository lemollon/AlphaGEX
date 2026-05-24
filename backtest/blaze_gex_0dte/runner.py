"""Drive one 0DTE DayChain through the real setups via replay_day."""
from __future__ import annotations
import datetime as dt
from typing import List, Optional

from backtest.joshua_replay.engine import replay_day, TradeOutcome
from trading.helios.models import JoshuaConfig
from .loader import DayChain, load_day
from .reconstruct import build_snapshots
from .providers import make_providers

def _minute_of(snapshot) -> int:
    ct = snapshot.snapshot_at - dt.timedelta(hours=5)
    open_t = ct.replace(hour=9, minute=30, second=0, microsecond=0)
    return int((ct - open_t).total_seconds() // 60)

def replay_daychain(day: DayChain, config: JoshuaConfig) -> List[TradeOutcome]:
    snaps = build_snapshots(day)
    if not snaps:
        return []
    _debit_min0, mark_provider = make_providers(day)

    def debit_estimator(snap, action) -> float:
        minute = _minute_of(snap)
        r = "C" if action.direction == "call" else "P"
        lq = day.quote(minute, float(action.long_strike), r)
        sq = day.quote(minute, float(action.short_strike), r)
        if not lq or not sq or lq[1] is None or sq[0] is None:
            return 0.0
        return max(0.0, lq[1] - sq[0])

    return replay_day(
        snaps, config=config,
        spot_mark_provider=mark_provider,
        debit_estimator=debit_estimator,
    )

def run_backtest(db_url: str, config: JoshuaConfig, start: dt.date, end: dt.date) -> List[TradeOutcome]:
    import psycopg2
    conn = psycopg2.connect(db_url)
    all_out: List[TradeOutcome] = []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT trade_date FROM helios_options_intraday "
            "WHERE expiration_date = trade_date AND trade_date BETWEEN %s AND %s ORDER BY trade_date",
            (start, end),
        )
        dates = [r[0] for r in cur.fetchall()]
        cur.close()
        for d in dates:
            day = load_day(conn, d)
            if day is None:
                continue
            all_out.extend(replay_daychain(day, config))
    finally:
        conn.close()
    return all_out
