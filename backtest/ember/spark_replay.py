from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from backtest.ember.build import DayPath, evaluate_grid
from backtest.ember.data import load_day
from backtest.ember.engine import price_path
from backtest.ember.fills import FILL_ASK_CROSS, commission, signed_cashflow
from backtest.ember.models import DayChain, Leg, Position
from backtest.ember.policy import default_grid


@dataclass
class SparkTrade:
    """One of SPARK's actual recorded iron condors (its real strikes + outcome)."""
    trade_date: dt.date
    entry_minute: int          # minutes since 09:30 ET, from SPARK's open_time
    legs: List[Leg]            # SPARK's 4 real strikes: short put -1, long put +1, short call -1, long call +1
    contracts: int
    actual_pnl_per_contract: float   # SPARK's realized P&L / contracts
    actual_exit_reason: str


# DISTINCT ON dedupes multi-account copies of the same signal (same day+strikes).
_SPARK_SQL = """
    SELECT DISTINCT ON (open_date, put_short_strike, put_long_strike, call_short_strike, call_long_strike)
        open_date,
        (EXTRACT(EPOCH FROM (
            (open_time AT TIME ZONE 'America/New_York')
            - date_trunc('day', open_time AT TIME ZONE 'America/New_York')
            - INTERVAL '9 hours 30 minutes'
        )) / 60)::int AS entry_minute,
        put_short_strike::float8  AS put_short,
        put_long_strike::float8   AS put_long,
        call_short_strike::float8 AS call_short,
        call_long_strike::float8  AS call_long,
        contracts, realized_pnl, close_reason
    FROM spark_positions
    WHERE close_time IS NOT NULL
      AND open_date BETWEEN %s AND %s
      AND put_short_strike IS NOT NULL AND call_short_strike IS NOT NULL
      AND contracts > 0
    ORDER BY open_date, put_short_strike, put_long_strike, call_short_strike, call_long_strike, open_time
"""


def load_spark_trades(db_url: str, start: dt.date, end: dt.date) -> List[SparkTrade]:
    """Load SPARK's distinct closed iron condors in [start, end] from spark_positions."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(_SPARK_SQL, (start, end))
            rows = c.fetchall()
    trades: List[SparkTrade] = []
    for r in rows:
        ctr = int(r["contracts"]) or 1
        legs = [
            Leg(float(r["put_short"]), "P", -1),
            Leg(float(r["put_long"]), "P", 1),
            Leg(float(r["call_short"]), "C", -1),
            Leg(float(r["call_long"]), "C", 1),
        ]
        trades.append(SparkTrade(
            trade_date=r["open_date"],
            entry_minute=int(r["entry_minute"]),
            legs=legs,
            contracts=ctr,
            actual_pnl_per_contract=float(r["realized_pnl"] or 0.0) / ctr,
            actual_exit_reason=r["close_reason"] or "",
        ))
    return trades


def spark_day_path(chain: DayChain, trade: SparkTrade, fill: str = FILL_ASK_CROSS,
                   slippage: float = 0.03) -> Optional[DayPath]:
    """Reprice SPARK's actual IC from the minute chain at its entry minute (or the nearest
    minute at/after it). Returns None if the day/strikes aren't priceable (e.g. strikes outside
    the captured band) or the entry credit is non-positive."""
    if not chain.minutes:
        return None
    if trade.entry_minute in chain.minutes:
        entry_min = trade.entry_minute
    else:
        later = [m for m in chain.sorted_minutes if m >= trade.entry_minute]
        if not later:
            return None
        entry_min = later[0]
    quotes = chain.minutes[entry_min].quotes
    for leg in trade.legs:
        if (leg.strike, leg.right) not in quotes:
            return None  # SPARK's strike not captured in the data
    entry_credit = signed_cashflow(trade.legs, quotes, action="open", fill=fill, slippage=slippage)
    if entry_credit <= 0:
        return None
    pos = Position(legs=trade.legs, entry_minute=entry_min, entry_credit=entry_credit, contracts=1)
    path = price_path(chain, pos, fill, slippage)
    if not path:
        return None
    return DayPath(
        trade_date=trade.trade_date,
        entry_minute=entry_min,
        entry_credit=entry_credit,
        contracts=1,
        commission_dollars=commission(trade.legs, 1),
        is_oos=False,   # SPARK replay is one comparison set, not a train/OOS split
        path=path,
    )


def build_spark_paths(trades: List[SparkTrade], db_url: str,
                      fill: str = FILL_ASK_CROSS) -> Tuple[List[DayPath], List[SparkTrade], int]:
    """For each SPARK trade, load its day's chain once and reprice its real IC.
    Returns (paths, priced_trades, skipped_count). priced_trades aligns 1:1 with paths."""
    by_date: Dict[dt.date, List[SparkTrade]] = {}
    for t in trades:
        by_date.setdefault(t.trade_date, []).append(t)
    paths: List[DayPath] = []
    priced: List[SparkTrade] = []
    skipped = 0
    for d in sorted(by_date):
        chain = load_day(d, db_url)
        for t in by_date[d]:
            dp = spark_day_path(chain, t, fill)
            if dp is not None:
                paths.append(dp)
                priced.append(t)
            else:
                skipped += 1
    return paths, priced, skipped


def _spark_actual_summary(priced: List[SparkTrade]) -> dict:
    n = len(priced)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "ev_per_contract": 0.0, "total_pnl": 0.0}
    pnls = [t.actual_pnl_per_contract for t in priced]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": n,
        "win_rate": round(100.0 * wins / n, 2),
        "ev_per_contract": round(sum(pnls) / n, 4),
        "total_pnl": round(sum(pnls), 2),
    }


def compare_spark(priced: List[SparkTrade], paths: List[DayPath], grid=None) -> dict:
    """Compare SPARK's actual exits vs EMBER's exit-policy sweep over SPARK's REAL trades.
    `paths` is from build_spark_paths (is_oos=False, so evaluate_grid's in_sample bucket = all)."""
    grid = grid or default_grid()
    rows = evaluate_grid(paths, grid)               # each row: {policy, in_sample, oos}
    model = [{"policy": r["policy"], **r["in_sample"]} for r in rows]   # in_sample = all SPARK paths
    model_priceable = [m for m in model if m["n"] > 0]
    best = max(model_priceable, key=lambda m: m["ev_per_contract"]) if model_priceable else None
    spark_live = next((m for m in model if m["policy"] == "spark_live"), None)
    return {
        "spark_actual": _spark_actual_summary(priced),
        "ember_spark_live_config": spark_live,   # EMBER's flat PT30/SL0.5x on SPARK's real trades
        "ember_best": best,
        "top5": sorted(model_priceable, key=lambda m: -m["ev_per_contract"])[:5],
    }
