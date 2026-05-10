"""Feature builder: per-minute IV chain, skew metrics, charm aggregation."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from backtest.skew_signal.loader import ChainBar
from quant.bs import bs_charm, bs_gamma, derive_spot_from_parity, implied_vol


@dataclass(frozen=True)
class StrikeIV:
    strike: float
    call_iv: Optional[float]
    put_iv: Optional[float]


@dataclass(frozen=True)
class Skew:
    skew_25d: float
    skew_slope: float
    atm_iv: float


@dataclass(frozen=True)
class CharmAggregate:
    charm_call_total: float
    charm_put_total: float


@dataclass(frozen=True)
class MinuteFeatures:
    spot: float
    vix_prior: Optional[float]
    skew_25d: float
    skew_slope: float
    delta_skew_15m: float
    charm_call_total: float
    charm_put_total: float
    magnet_imbalance: float
    regime_label: Optional[str]


def estimate_spot(chain: Dict[float, ChainBar], t_years: float) -> Optional[float]:
    candidates = []
    for k, cb in chain.items():
        if cb.call_valid() and cb.put_valid():
            candidates.append((cb.call_mid + cb.put_mid, k, cb.call_mid, cb.put_mid))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    _, k, cm, pm = candidates[0]
    return derive_spot_from_parity(cm, pm, k, t_years)


def solve_chain_iv(
    chain: Dict[float, ChainBar],
    spot: float,
    t_years: float,
) -> Dict[float, StrikeIV]:
    out: Dict[float, StrikeIV] = {}
    for k, cb in chain.items():
        c_iv = implied_vol(cb.call_mid, spot, k, t_years, is_call=True) if cb.call_valid() else None
        p_iv = implied_vol(cb.put_mid, spot, k, t_years, is_call=False) if cb.put_valid() else None
        out[k] = StrikeIV(strike=k, call_iv=c_iv, put_iv=p_iv)
    return out


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _call_delta(spot: float, strike: float, t_years: float, sigma: float, r: float = 0.05) -> float:
    if t_years <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    return _norm_cdf(d1)


def compute_skew(
    ivs: Dict[float, StrikeIV],
    spot: float,
    t_years: float,
    target_call_delta: float = 0.25,
    wing_call_delta: float = 0.10,
) -> Skew:
    valid_strikes = [(k, iv) for k, iv in ivs.items() if iv.call_iv and iv.put_iv]
    if not valid_strikes:
        return Skew(skew_25d=0.0, skew_slope=0.0, atm_iv=0.0)

    deltas = []
    for k, iv in valid_strikes:
        d = _call_delta(spot, k, t_years, iv.call_iv)
        deltas.append((k, iv, d))

    def at_delta(target):
        return min(deltas, key=lambda x: abs(x[2] - target))

    k25, iv25, d25 = at_delta(target_call_delta)
    k10, iv10, d10 = at_delta(wing_call_delta)
    atm_strike, iv_atm, _ = at_delta(0.50)

    skew_25d = (iv25.put_iv - iv25.call_iv) if iv25.put_iv and iv25.call_iv else 0.0
    skew_10d = (iv10.put_iv - iv10.call_iv) if iv10.put_iv and iv10.call_iv else 0.0
    slope = (skew_25d - skew_10d) / max(1e-6, target_call_delta - wing_call_delta)
    atm_iv = 0.5 * ((iv_atm.call_iv or 0.0) + (iv_atm.put_iv or 0.0))
    return Skew(skew_25d=skew_25d, skew_slope=slope, atm_iv=atm_iv)


def compute_charm_aggregate(
    chain: Dict[float, ChainBar],
    ivs: Dict[float, StrikeIV],
    spot: float,
    t_years: float,
) -> CharmAggregate:
    charm_call = 0.0
    charm_put = 0.0
    for k, cb in chain.items():
        iv = ivs.get(k)
        if iv is None:
            continue
        if iv.call_iv and k > spot:
            c = bs_charm(spot, k, t_years, iv.call_iv)
            charm_call += c * cb.call_oi
        if iv.put_iv and k < spot:
            c = bs_charm(spot, k, t_years, iv.put_iv)
            charm_put += c * cb.put_oi
    return CharmAggregate(charm_call_total=charm_call, charm_put_total=charm_put)


def magnet_imbalance_proxy(
    chain: Dict[float, ChainBar],
    ivs: Dict[float, StrikeIV],
    spot: float,
    t_years: float,
) -> float:
    """OI-weighted gamma proxy. Returns 99 if put-side has zero peak."""
    call_peak = 0.0
    put_peak = 0.0
    for k, cb in chain.items():
        iv = ivs.get(k)
        if iv is None:
            continue
        if iv.call_iv and cb.call_oi > 0 and k >= spot:
            g = bs_gamma(spot, k, t_years, iv.call_iv) * cb.call_oi * 100.0 * spot * spot * 0.01
            call_peak = max(call_peak, g)
        if iv.put_iv and cb.put_oi > 0 and k <= spot:
            g = bs_gamma(spot, k, t_years, iv.put_iv) * cb.put_oi * 100.0 * spot * spot * 0.01
            put_peak = max(put_peak, g)
    if put_peak <= 0:
        return 99.0
    return call_peak / put_peak
