"""Compute realized outcome of a vertical from entry minute to exit_minute.

For each minute between entry+1 and exit_minute:
  - record whether spot has crossed the long strike at any point
  - record the FIRST minute spot crossed (NULL if never)

At exit_minute (default 385 = 15:55 ET):
  - read mid_long(385) and mid_short(385) from helios_options_intraday
  - exit_mid = mid_long - mid_short
  - pnl_gross = exit_mid - entry_mid

Spot per minute is derived from put-call parity at the long strike when both
legs are valid; otherwise the minute is skipped for touch detection.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional

import psycopg2

from backtest.touch_pin.vehicle import VerticalSpec
from quant.bs import derive_spot_from_parity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RealizedOutcome:
    exit_mid: float
    exit_long_bid: float
    exit_long_ask: float
    exit_short_bid: float
    exit_short_ask: float
    touched_during_day: int
    time_first_touch_minute: Optional[int]
    spot_at_exit: float
    exit_skipped_reason: Optional[str]
    pnl_gross: float


def compute_realized(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    spec: VerticalSpec,
    exit_minute: int = 385,
    entry_minute: int = 5,
) -> Optional[RealizedOutcome]:
    """Walk minute bars from entry+1 to exit_minute, detect touch, compute exit."""
    sql_bars = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT (EXTRACT(EPOCH FROM (b.bar_time - first_bar.t0))::int / 60) AS minute_idx,
               b.strike, b."right", b.bid, b.ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time > first_bar.t0 + (%s * INTERVAL '1 minute')
          AND b.bar_time <= first_bar.t0 + (%s * INTERVAL '1 minute')
          AND (b.strike = %s OR b.strike = %s)
        ORDER BY b.bar_time, b.strike, b."right"
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql_bars, (
            trade_date, expiration_date,
            trade_date, expiration_date,
            entry_minute, exit_minute,
            spec.long_K, spec.short_K,
        ))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    if not rows:
        return None

    by_minute: dict = {}
    for minute_idx, strike, right, bid, ask in rows:
        m = int(minute_idx)
        by_minute.setdefault(m, {}).setdefault(float(strike), {})[right] = (
            float(bid) if bid is not None else 0.0,
            float(ask) if ask is not None else 0.0,
        )

    is_call_side = (spec.side == "PIN-CALL")

    touched = 0
    first_touch_minute: Optional[int] = None
    spot_at_exit = 0.0
    exit_skipped_reason: Optional[str] = None

    for m in sorted(by_minute.keys()):
        legs = by_minute[m]
        long_legs = legs.get(spec.long_K, {})
        if "C" in long_legs and "P" in long_legs:
            cb, ca = long_legs["C"]
            pb, pa = long_legs["P"]
            if cb > 0 and ca > 0 and pb > 0 and pa > 0:
                cm = 0.5 * (cb + ca)
                pm = 0.5 * (pb + pa)
                spot_m = derive_spot_from_parity(cm, pm, spec.long_K, t_years=1/365)
                if is_call_side:
                    crossed = spot_m >= spec.long_K
                else:
                    crossed = spot_m <= spec.long_K
                if crossed and first_touch_minute is None:
                    touched = 1
                    first_touch_minute = m

    exit_legs = by_minute.get(exit_minute, {})
    long_q = exit_legs.get(spec.long_K, {})
    short_q = exit_legs.get(spec.short_K, {})
    leg_key = "C" if is_call_side else "P"
    if leg_key not in long_q or leg_key not in short_q:
        exit_skipped_reason = f"missing {leg_key} leg quotes at minute {exit_minute}"
        for back in range(1, 6):
            alt_legs = by_minute.get(exit_minute - back, {})
            alt_long = alt_legs.get(spec.long_K, {})
            alt_short = alt_legs.get(spec.short_K, {})
            if leg_key in alt_long and leg_key in alt_short:
                long_q = alt_long
                short_q = alt_short
                exit_skipped_reason = f"fell back to minute {exit_minute - back}"
                break

    if leg_key not in long_q or leg_key not in short_q:
        return None

    lb, la = long_q[leg_key]
    sb, sa = short_q[leg_key]
    if lb <= 0 or la <= 0 or sb <= 0 or sa <= 0:
        return None
    long_mid = 0.5 * (lb + la)
    short_mid = 0.5 * (sb + sa)
    exit_mid = long_mid - short_mid

    if "C" in long_q and "P" in long_q:
        cb_x, ca_x = long_q["C"]
        pb_x, pa_x = long_q["P"]
        if cb_x > 0 and pb_x > 0:
            spot_at_exit = derive_spot_from_parity(
                0.5 * (cb_x + ca_x), 0.5 * (pb_x + pa_x), spec.long_K, t_years=0.5/365,
            )

    pnl_gross = exit_mid - spec.entry_mid

    return RealizedOutcome(
        exit_mid=exit_mid,
        exit_long_bid=lb, exit_long_ask=la,
        exit_short_bid=sb, exit_short_ask=sa,
        touched_during_day=touched,
        time_first_touch_minute=first_touch_minute,
        spot_at_exit=spot_at_exit,
        exit_skipped_reason=exit_skipped_reason,
        pnl_gross=pnl_gross,
    )
