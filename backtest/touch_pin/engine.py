"""Per-day orchestration: pull chain, build verticals, compute outcomes, return TradeRows."""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import List, Optional

from backtest.touch_pin.loader import (
    load_minute_chain, vix_close_prior_day, regime_label_at_open,
)
from backtest.touch_pin.vehicle import build_verticals
from backtest.touch_pin.implied import implied_pin_probabilities
from backtest.touch_pin.realized import compute_realized
from quant.walls import compute_intraday_walls

logger = logging.getLogger(__name__)


@dataclass
class TradeRow:
    trade_date: dt.date
    expiration_date: dt.date
    side: str
    long_K: float
    short_K: float
    width: float
    entry_mid: float
    exit_mid: float
    spot_5: float
    spot_close: float
    vix_close_prior: Optional[float]
    magnet_imbalance: float
    distance_pct: float
    regime_label: Optional[str]
    implied_method1: float
    implied_method2: float
    iv_long_strike: Optional[float]
    touched_during_day: int
    time_first_touch_minute: Optional[int]
    pnl_gross: float
    pnl_net: float
    slippage: float
    commission: float
    exit_skipped_reason: Optional[str]


def run_one_day(
    db_url_main: str,
    db_url_orat: str,
    trade_date: dt.date,
    target_minute: int = 5,
    exit_minute: int = 385,
    slippage_ticks_per_leg: int = 1,
    commission_per_leg: float = 1.30,
    expiration_date: Optional[dt.date] = None,
) -> List[TradeRow]:
    """Build trade rows for both sides on a single day. expiration defaults to T+1 business day."""
    if expiration_date is None:
        expiration_date = _next_business_day(trade_date)

    snap = load_minute_chain(db_url_main, trade_date, expiration_date, target_minute)
    if snap is None or not snap.chain:
        return []

    walls = compute_intraday_walls(
        db_url_main, trade_date, expiration_date,
        target_minute=target_minute, t_years_at_open=1.0/365.0,
    )
    if walls is None or walls.spot is None:
        return []

    spot_5 = walls.spot
    walls_dict = {"call_wall": walls.call_wall, "put_support": walls.put_support}

    pin_call, pin_put = build_verticals(snap.chain, walls_dict, spot_5, strike_step=1.0)

    magnet_imb = _magnet_imbalance(walls)
    vix_prior = vix_close_prior_day(db_url_orat, trade_date)
    regime = regime_label_at_open(db_url_main, trade_date)

    results: List[TradeRow] = []
    for spec in (pin_call, pin_put):
        if spec is None:
            continue
        probs = implied_pin_probabilities(spec, spot_5, t_years=1.0/365.0)
        if probs is None:
            continue
        outcome = compute_realized(
            db_url_main, trade_date, expiration_date, spec,
            exit_minute=exit_minute, entry_minute=target_minute,
        )
        if outcome is None:
            continue
        # Slippage: ticks/leg * $0.01 * 2 legs (per-share equivalent)
        slippage_ps = slippage_ticks_per_leg * 0.01 * 2
        slippage_dollars = slippage_ps * 100
        commission_dollars = commission_per_leg * 4  # 2 legs × open + close
        pnl_gross_dollars = outcome.pnl_gross * 100
        pnl_net = pnl_gross_dollars - slippage_dollars - commission_dollars
        distance_pct = abs(spec.long_K - spot_5) / spot_5 * 100.0

        results.append(TradeRow(
            trade_date=trade_date,
            expiration_date=expiration_date,
            side=spec.side,
            long_K=spec.long_K,
            short_K=spec.short_K,
            width=spec.width,
            entry_mid=spec.entry_mid,
            exit_mid=outcome.exit_mid,
            spot_5=spot_5,
            spot_close=outcome.spot_at_exit,
            vix_close_prior=vix_prior,
            magnet_imbalance=magnet_imb,
            distance_pct=distance_pct,
            regime_label=regime,
            implied_method1=probs.method_bs_d2,
            implied_method2=probs.method_price_over_width,
            iv_long_strike=probs.iv_long_strike,
            touched_during_day=outcome.touched_during_day,
            time_first_touch_minute=outcome.time_first_touch_minute,
            pnl_gross=pnl_gross_dollars,
            pnl_net=pnl_net,
            slippage=slippage_dollars,
            commission=commission_dollars,
            exit_skipped_reason=outcome.exit_skipped_reason,
        ))

    return results


def _magnet_imbalance(walls) -> float:
    """call_peak / put_peak — guard against zero put peak."""
    call_peaks = [s.call_gamma_oi for s in walls.by_strike if s.call_gamma_oi > 0]
    put_peaks = [s.put_gamma_oi for s in walls.by_strike if s.put_gamma_oi > 0]
    cp = max(call_peaks) if call_peaks else 0.0
    pp = max(put_peaks) if put_peaks else 0.0
    if pp <= 0:
        return 99.0
    return cp / pp


def _next_business_day(d: dt.date) -> dt.date:
    nxt = d + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return nxt
