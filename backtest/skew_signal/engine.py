"""Per-day orchestration: scan minutes 5..270, fire first qualifying signal."""
from __future__ import annotations

import datetime as dt
import logging
from collections import deque
from dataclasses import dataclass
from typing import List, Optional

import psycopg2

from backtest.skew_signal.loader import load_day_chain
from backtest.skew_signal.features import (
    MinuteFeatures, compute_charm_aggregate, compute_skew,
    estimate_spot, magnet_imbalance_proxy, solve_chain_iv,
)
from backtest.skew_signal.signal import decide_signal
from backtest.touch_pin.loader import vix_close_prior_day, regime_label_at_open
from quant.sim import simulate_intraday, MarkSeries

logger = logging.getLogger(__name__)

SCAN_START_MINUTE = 5
SCAN_END_MINUTE = 270
EOD_MINUTE = 385
SKEW_LOOKBACK_MINUTES = 15


@dataclass
class TradeRow:
    trade_date: dt.date
    expiration_date: dt.date
    action: str
    entry_minute: int
    long_K: float
    short_K: float
    width: float
    debit: float
    composite_z: float
    skew_25d_at_entry: float
    delta_skew_15m: float
    charm_used: float
    magnet_imbalance: float
    spot_at_entry: float
    vix_prior: Optional[float]
    regime_label: Optional[str]
    exit_minute: int
    exit_reason: str
    realized_pct: float
    pnl_gross: float
    pnl_net: float
    slippage: float
    commission: float


def _next_business_day(d: dt.date) -> dt.date:
    nxt = d + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return nxt


def _build_mark_series(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    long_K: float,
    short_K: float,
    is_call: bool,
    entry_minute: int,
    exit_minute: int,
) -> MarkSeries:
    sql = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT EXTRACT(EPOCH FROM (b.bar_time - first_bar.t0))::int / 60 AS minute_idx,
               b.strike, b."right", b.bid, b.ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time >= first_bar.t0 + (%s * INTERVAL '1 minute')
          AND b.bar_time <= first_bar.t0 + (%s * INTERVAL '1 minute')
          AND (b.strike = %s OR b.strike = %s)
        ORDER BY minute_idx, b.strike, b."right"
    """
    leg = "C" if is_call else "P"
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (trade_date, expiration_date,
                          trade_date, expiration_date,
                          entry_minute, exit_minute,
                          long_K, short_K))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    by_minute: dict = {}
    for m, k, r, b, a in rows:
        m = int(m); k = float(k)
        by_minute.setdefault(m, {}).setdefault(k, {})[r] = (
            float(b) if b is not None else 0.0,
            float(a) if a is not None else 0.0,
        )

    marks: dict = {}
    for m, legs in by_minute.items():
        long_q = legs.get(long_K, {}).get(leg)
        short_q = legs.get(short_K, {}).get(leg)
        if not long_q or not short_q:
            continue
        lb, la = long_q
        sb, sa = short_q
        if lb <= 0 or sa <= 0:
            continue
        marks[m] = lb - sa
    return MarkSeries(marks=marks)


def run_one_day(
    *,
    db_url_main: str,
    db_url_orat: str,
    trade_date: dt.date,
    theta_skew: float = 0.005,
    theta_charm: float = 50.0,
    magnet_threshold: float = 1.3,
    pt_pct: float = 20.0,
    sl_pct: float = 30.0,
    trailing_activate_pct: float = 5.0,
    trailing_stop_pct: float = 8.0,
    slippage_ticks_per_leg: int = 1,
    commission_per_leg: float = 1.30,
) -> List[TradeRow]:
    expiration_date = _next_business_day(trade_date)
    vix_prior = vix_close_prior_day(db_url_orat, trade_date)
    regime = regime_label_at_open(db_url_main, trade_date)

    # Single fat query for the entire day's bars (was 266 round-trips per day).
    day_chain = load_day_chain(db_url_main, trade_date, expiration_date)
    if not day_chain:
        return []

    skew_history: deque = deque(maxlen=SKEW_LOOKBACK_MINUTES + 1)

    for minute in range(SCAN_START_MINUTE, SCAN_END_MINUTE + 1):
        chain = day_chain.get(minute)
        if chain is None or len(chain) < 5:
            skew_history.append(None)
            continue
        spot = estimate_spot(chain, t_years=1/365)
        if spot is None or spot <= 0:
            skew_history.append(None)
            continue
        ivs = solve_chain_iv(chain, spot, t_years=1/365)
        skew = compute_skew(ivs, spot, t_years=1/365)
        skew_history.append(skew.skew_25d)

        if len(skew_history) <= SKEW_LOOKBACK_MINUTES:
            continue
        prior = skew_history[0]
        if prior is None:
            continue
        delta_skew = skew.skew_25d - prior
        charm = compute_charm_aggregate(chain, ivs, spot, t_years=1/365)
        magnet = magnet_imbalance_proxy(chain, ivs, spot, t_years=1/365)

        feats = MinuteFeatures(
            spot=spot, vix_prior=vix_prior,
            skew_25d=skew.skew_25d, skew_slope=skew.skew_slope,
            delta_skew_15m=delta_skew,
            charm_call_total=charm.charm_call_total,
            charm_put_total=charm.charm_put_total,
            magnet_imbalance=magnet,
            regime_label=regime,
        )
        sig = decide_signal(feats, theta_skew=theta_skew, theta_charm=theta_charm,
                            magnet_threshold=magnet_threshold)
        if sig.action == "NONE":
            continue

        is_call = sig.action == "BULL"
        all_strikes = sorted(chain.keys())
        atm_strike = min(all_strikes, key=lambda k: abs(k - spot))
        long_K = atm_strike
        short_K = long_K + 1.0 if is_call else long_K - 1.0
        if short_K not in chain:
            continue
        long_cb = chain[long_K]; short_cb = chain[short_K]
        if is_call and (not long_cb.call_valid() or not short_cb.call_valid()):
            continue
        if not is_call and (not long_cb.put_valid() or not short_cb.put_valid()):
            continue
        long_mid = long_cb.call_mid if is_call else long_cb.put_mid
        short_mid = short_cb.call_mid if is_call else short_cb.put_mid
        debit = long_mid - short_mid
        if debit <= 0 or debit >= 1.0:
            continue

        bars = _build_mark_series(
            db_url_main, trade_date, expiration_date,
            long_K, short_K, is_call,
            entry_minute=minute, exit_minute=EOD_MINUTE,
        )
        out = simulate_intraday(
            debit=debit, entry_minute=minute, eod_minute=EOD_MINUTE, bars=bars,
            pt_pct=pt_pct, sl_pct=sl_pct,
            trailing_activate_pct=trailing_activate_pct, trailing_stop_pct=trailing_stop_pct,
        )

        slippage_ps = slippage_ticks_per_leg * 0.01 * 2
        slippage_dollars = slippage_ps * 100
        commission_dollars = commission_per_leg * 4
        pnl_gross_dollars = out.realized_pct / 100.0 * debit * 100
        pnl_net = pnl_gross_dollars - slippage_dollars - commission_dollars

        return [TradeRow(
            trade_date=trade_date, expiration_date=expiration_date,
            action=sig.action, entry_minute=minute,
            long_K=long_K, short_K=short_K, width=1.0, debit=debit,
            composite_z=sig.composite_z, skew_25d_at_entry=skew.skew_25d,
            delta_skew_15m=delta_skew,
            charm_used=charm.charm_call_total if is_call else charm.charm_put_total,
            magnet_imbalance=magnet, spot_at_entry=spot,
            vix_prior=vix_prior, regime_label=regime,
            exit_minute=out.exit_minute, exit_reason=out.exit_reason,
            realized_pct=out.realized_pct,
            pnl_gross=pnl_gross_dollars, pnl_net=pnl_net,
            slippage=slippage_dollars, commission=commission_dollars,
        )]

    return []
