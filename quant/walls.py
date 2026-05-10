"""Compute intraday GEX walls from helios_options_intraday + helios_options_oi.

For a given (trade_date, expiration_date, minute), pulls the full strike chain
at that minute, computes per-strike gamma * OI, and identifies the call wall
(largest call gamma above spot) and put support (largest put gamma below spot).

This is the same wall mechanic that 0DTE traders watch live — but reconstructed
from historical data instead of relying on a snapshot from yesterday's close.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psycopg2

from quant.bs import bs_gamma, derive_spot_from_parity, implied_vol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrikeGamma:
    strike: float
    call_gamma_oi: float  # gamma per contract * call OI * 100 (contract multiplier)
    put_gamma_oi: float
    net_gamma: float


@dataclass(frozen=True)
class Walls:
    spot: float
    call_wall: Optional[float]    # strike with largest call gamma above spot
    put_support: Optional[float]  # strike with largest put gamma below spot
    flip_point: Optional[float]   # strike where net gamma flips sign
    by_strike: List[StrikeGamma]


def _load_chain_at_minute(
    conn,
    trade_date: dt.date,
    expiration_date: dt.date,
    target_minute: int,
) -> Dict[Tuple[float, str], Tuple[float, float]]:
    """Return {(strike, right): (mid_price, time_to_close)} for all strikes at
    the bar closest to target_minute on trade_date.

    Anchors minute 0 to the FIRST bar of the day (typical 9:30 ET / 8:30 CT).
    target_minute=0 means use the open bars; target_minute=60 = ~10:30 ET, etc.
    """
    sql = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS first_t
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT strike, "right", bar_time, bid, ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time = first_bar.first_t + (%s * INTERVAL '1 minute')
          AND b.bid IS NOT NULL AND b.ask IS NOT NULL
        ORDER BY strike, "right"
    """
    cur = conn.cursor()
    cur.execute(sql, (trade_date, expiration_date, trade_date, expiration_date, target_minute))
    rows = cur.fetchall()
    cur.close()

    out: Dict[Tuple[float, str], Tuple[float, float]] = {}
    for strike, right, bar_time, bid, ask in rows:
        if bid is None or ask is None or bid <= 0 or ask <= bid:
            continue
        mid = (float(bid) + float(ask)) / 2.0
        out[(float(strike), right)] = (mid, 0.0)  # t_years filled in by caller
    return out


def _load_oi_for_chain(
    conn,
    trade_date: dt.date,
    expiration_date: dt.date,
) -> Dict[Tuple[float, str], int]:
    """{(strike, right): open_interest} for the chain on trade_date."""
    sql = """
        SELECT strike, "right", open_interest
        FROM helios_options_oi
        WHERE trade_date = %s AND expiration_date = %s
    """
    cur = conn.cursor()
    cur.execute(sql, (trade_date, expiration_date))
    out = {(float(k), r): int(oi) for k, r, oi in cur.fetchall()}
    cur.close()
    return out


def _estimate_spot_from_chain(
    chain: Dict[Tuple[float, str], Tuple[float, float]],
    t_years: float,
) -> Optional[float]:
    """Use put-call parity at the most ATM strike that has both legs.

    Picks the strike where call_mid + put_mid is smallest (= closest to ATM,
    where extrinsic is minimized for both legs).
    """
    strikes_with_both = []
    for k, _ in chain.keys():
        if (k, "C") in chain and (k, "P") in chain:
            cm = chain[(k, "C")][0]
            pm = chain[(k, "P")][0]
            strikes_with_both.append((cm + pm, k, cm, pm))
    if not strikes_with_both:
        return None
    strikes_with_both.sort(key=lambda x: x[0])
    _, k, cm, pm = strikes_with_both[0]
    return derive_spot_from_parity(cm, pm, k, t_years)


def compute_intraday_walls(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    target_minute: int = 0,
    t_years_at_open: float = 1.0 / 365.0,
) -> Optional[Walls]:
    """Build the wall structure for one (trade_date, expiration, minute).

    `t_years_at_open` is the time-to-expiry in years AT the target minute. For
    a 1DTE (expiring next session), it's roughly 1/365. For 0DTE same-day it's
    the remaining hours / (8760).

    Returns None if no usable chain exists.
    """
    conn = psycopg2.connect(db_url)
    try:
        chain = _load_chain_at_minute(conn, trade_date, expiration_date, target_minute)
        if not chain:
            return None
        oi = _load_oi_for_chain(conn, trade_date, expiration_date)
    finally:
        conn.close()

    if not chain or not oi:
        return None

    spot = _estimate_spot_from_chain(chain, t_years_at_open)
    if spot is None or spot <= 0:
        return None

    by_strike: Dict[float, Dict[str, float]] = {}
    for (strike, right), (mid, _) in chain.items():
        contracts = oi.get((strike, right), 0)
        if contracts <= 0:
            continue
        is_call = right == "C"
        iv = implied_vol(mid, spot, strike, t_years_at_open, is_call)
        if iv is None:
            continue
        gamma_per_share = bs_gamma(spot, strike, t_years_at_open, iv)
        # gamma * OI * 100 (contract multiplier) * spot * spot * 0.01
        # = dollar gamma per 1% spot move; common GEX convention
        dollar_gamma = gamma_per_share * contracts * 100.0 * spot * spot * 0.01
        by_strike.setdefault(strike, {"C": 0.0, "P": 0.0})
        by_strike[strike]["C" if is_call else "P"] += dollar_gamma

    if not by_strike:
        return None

    strikes_list: List[StrikeGamma] = []
    for k in sorted(by_strike.keys()):
        cg = by_strike[k]["C"]
        pg = by_strike[k]["P"]
        strikes_list.append(StrikeGamma(strike=k, call_gamma_oi=cg, put_gamma_oi=pg, net_gamma=cg - pg))

    # Wall identification — largest gamma on each side of spot
    call_above = [s for s in strikes_list if s.strike >= spot and s.call_gamma_oi > 0]
    put_below = [s for s in strikes_list if s.strike <= spot and s.put_gamma_oi > 0]

    call_wall = max(call_above, key=lambda s: s.call_gamma_oi).strike if call_above else None
    put_support = max(put_below, key=lambda s: s.put_gamma_oi).strike if put_below else None

    # Flip point — strike where cumulative net gamma crosses zero
    flip = None
    cumulative = 0.0
    for s in strikes_list:
        new = cumulative + s.net_gamma
        if cumulative <= 0 < new or cumulative >= 0 > new:
            flip = s.strike
            break
        cumulative = new

    return Walls(spot=spot, call_wall=call_wall, put_support=put_support, flip_point=flip, by_strike=strikes_list)
