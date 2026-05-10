"""Two-method implied probability that the wall pin is hit.

Method 1 (bs_d2): solve IV at the long strike, compute P(S_T >= long_K) for
                  PIN-CALL or P(S_T <= long_K) for PIN-PUT via Black-Scholes
                  Φ(d2) — the risk-neutral probability of expiring in the money.

Method 2 (price_over_width): for a debit vertical, max payoff = width.
                  P_implied ≈ entry_mid / width  — the market's implied
                  probability of full payoff (heuristic, not strictly RN).

The two methods diverge when there's significant IV skew between the long
and short strikes; both are reported.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from backtest.touch_pin.vehicle import VerticalSpec
from quant.bs import implied_vol


@dataclass(frozen=True)
class ImpliedProbs:
    method_bs_d2: float
    method_price_over_width: float
    iv_long_strike: Optional[float]


def implied_pin_probabilities(
    spec: VerticalSpec,
    spot: float,
    t_years: float,
    r: float = 0.05,
) -> Optional[ImpliedProbs]:
    """Return both implied probability methods. Falls back to method 2 if IV solver fails."""
    method2 = max(0.0, min(1.0, spec.entry_mid / spec.width)) if spec.width > 0 else 0.0

    long_mid = 0.5 * (spec.long_bid + spec.long_ask)
    is_call = (spec.side == "PIN-CALL")
    iv = implied_vol(long_mid, spot, spec.long_K, t_years, is_call=is_call, r=r)
    if iv is None:
        method1 = method2
    else:
        if t_years <= 0 or iv <= 0 or spot <= 0:
            return ImpliedProbs(method_bs_d2=method2, method_price_over_width=method2, iv_long_strike=iv)
        sqrt_t = math.sqrt(t_years)
        d1 = (math.log(spot / spec.long_K) + (r + 0.5 * iv * iv) * t_years) / (iv * sqrt_t)
        d2 = d1 - iv * sqrt_t
        if is_call:
            method1 = _norm_cdf(d2)
        else:
            method1 = _norm_cdf(-d2)

    return ImpliedProbs(
        method_bs_d2=method1,
        method_price_over_width=method2,
        iv_long_strike=iv,
    )


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
