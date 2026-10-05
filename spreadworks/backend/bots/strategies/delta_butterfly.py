"""MONARCH — delta-targeted symmetric ATM butterfly, SPY 0DTE.

Forward/paper validation of two UNCONFIRMED cells surfaced by TRIAGE 29
(dev/meltup/triage29_wing_delta_sweep.py, PREREG_TRIAGE29_WING_DELTA_SWEEP.md /
RESULT_TRIAGE29_WING_DELTA_SWEEP.md): a symmetric ATM butterfly whose wings are
targeted at a FIXED DELTA rather than a fixed %-distance-from-spot (long_butterfly
/ RIVER / SURGE / RIPPLE / SPLASH) or a gamma-magnet-centered body. Two wing
targets are paper-traded side by side under the `monarch_a` (0.05 delta) and
`monarch_b` (0.25 delta) bot IDs in registry.py. Both backtested point estimates'
bootstrap CIs cross zero on the 2025-26 holdout — this module exists to find out
whether the lead is real on live quotes, not because the backtest already proved
it. Do not treat a paper win streak here as confirmation on its own; see the
MONARCH memory notes for the full backtest caveats this is meant to resolve.

Construction (frozen, matches the backtest's build_day_ladder() exactly):
  - body = the listed call strike NEAREST to spot at scan time (nearest-strike
    tie broken toward the LOWER strike, same as triage29's K_mid pick). This is
    NOT a gamma-magnet center.
  - wings = the call strike whose delta is closest to `wing_delta_target`
    (within DELTA_TOL), mirrored for the lower wing so the fly stays symmetric.
  - type: calls only on both sides (the backtest never tested puts).
  - fill: REAL NBBO, no mid, no modeled slippage. Wings are bought at ASK,
    the body is sold (x2) at BID — literally
        debit = (ask_low + ask_high - 2*bid_mid) * 100
    per contract, identical to triage29.build_day_ladder(). The scanner must
    call open_position(..., mid_fill=False) for this strategy so the
    executor's simulated half-spread is never layered on top of a debit that
    already crossed the real book.
  - VIX gate: mid-tercile ONLY. Cutoffs are FROZEN from the original fit
    window (2023-01-01..2024-12-31, VIX close at 10:30 ET, read from
    ironforge-data/warehouse/vix_minute.duckdb) — see MONARCH_VIX_Q1/Q2
    below. Reproduce with triage29_wing_delta_sweep.vix_tercile_cutoffs().
    The live gate reads the chain's current VIX snapshot at scan time (the
    registry's narrow entry window approximates "at 10:30 ET"); this is a
    live quote, not the frozen historical 10:30:00 bar, and is flagged as
    such in the forward-test report.
  - hold: to same-day cash settlement. registry.py sets settle_at_expiry=True
    and pt_ladder=False for both monarch bots — no stop, no profit target,
    exactly the RIPPLE/SPLASH convention. decide_exit() never evaluates PT/SL
    for a settle_at_expiry bot; the position rides to the scanner's own
    settlement pass, which prices intrinsic value off the official close
    (see scanner._settlement_value) — the live equivalent of "reverse
    direction at settlement, real intrinsic value at expiry, not a market
    order."

Delta source: Tradier's own per-contract greeks (LiveTradierChainProvider
requests `greeks=true` already) when present on a strike — the real
broker-computed delta, which is more realistic for a LIVE/forward bot than
re-deriving one from a historical quote. Falls back to a Black-Scholes delta
implied from the live mid price (same method triage29 used on historical
quotes — invert for sigma, r=0, q=0 — but via plain bisection instead of
scipy.brentq so this module adds no new dependency) only when Tradier serves
no greeks for a strike. This IS a deliberate, documented difference from
triage29's purely-historical methodology; it is flagged in the forward-test
report, not silently introduced.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

# Frozen on the fit window (2023-01-01..2024-12-31), VIX close at 10:30 ET,
# ironforge-data/warehouse/vix_minute.duckdb. Reproduced 2026-10-05 via
# triage29_wing_delta_sweep.vix_tercile_cutoffs() — do not re-tune these on
# live data; a cutoff refit on the forward period would be look-ahead.
MONARCH_VIX_Q1 = 14.176666666666666
MONARCH_VIX_Q2 = 17.66

# Same tolerance band triage29 used when matching a strike's delta to the
# target.
DELTA_TOL = 0.05

# Fallback-only: used when a strike carries no Tradier greeks and this module
# must imply its own delta from the live mid. r=0, q=0, matching triage29.
_RISK_FREE = 0.0


@dataclass
class DeltaButterflySignal:
    ticker: str
    expiration: str
    body_strike: int
    lower_strike: int
    upper_strike: int
    lower_ask: float
    body_bid: float
    upper_ask: float
    debit: float               # per contract, net debit paid (> 0)
    contracts: int
    max_profit: float          # per contract, $
    max_loss: float            # per contract, $  (== debit * 100)
    wing_width: int            # body to wing distance (symmetric)
    wing_delta_target: float   # 0.05 or 0.25 — which MONARCH cell this is
    realized_delta: float      # the wing's actual delta at selection time
    vix_at_entry: float
    pt_target_pnl: float       # $ total — unreachable by construction, see below
    sl_target_pnl: float       # $ total — unreachable by construction, see below

    def legs(self) -> list[dict[str, Any]]:
        # Body sold twice -> four legs, same shape as long_butterfly's, so
        # settlement/MTM/payoff-chart code that is generic over leg shape
        # (scanner._settlement_value, routes_bots.position_payoff) needs no
        # strategy-specific branch beyond "this is a debit structure."
        return [
            {"side": "long", "type": "call", "strike": self.lower_strike,
             "expiration": self.expiration, "entry_price": self.lower_ask},
            {"side": "short", "type": "call", "strike": self.body_strike,
             "expiration": self.expiration, "entry_price": self.body_bid},
            {"side": "short", "type": "call", "strike": self.body_strike,
             "expiration": self.expiration, "entry_price": self.body_bid},
            {"side": "long", "type": "call", "strike": self.upper_strike,
             "expiration": self.expiration, "entry_price": self.upper_ask},
        ]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_call_price(S: float, K: float, T: float, sigma: float) -> float:
    if sigma <= 0 or T <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _norm_cdf(d1) - K * _norm_cdf(d2)


def _bs_call_delta(S: float, K: float, T: float, sigma: float) -> float:
    if sigma <= 0 or T <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1)


def _implied_delta_from_mid(S: float, K: float, T: float, mid: float) -> float | None:
    """Bisection for implied vol, then BS delta. No scipy — stdlib only.

    Returns None if the mid is at/below intrinsic (no solvable vol) or the
    search never brackets a root.
    """
    intrinsic = max(S - K, 0.0)
    if mid <= intrinsic or T <= 0:
        return None
    lo, hi = 1e-4, 3.0
    f_lo = _bs_call_price(S, K, T, lo) - mid
    f_hi = _bs_call_price(S, K, T, hi) - mid
    if f_lo > 0 or f_hi < 0:
        return None
    for _ in range(60):
        mid_sigma = (lo + hi) / 2.0
        f_mid = _bs_call_price(S, K, T, mid_sigma) - mid
        if abs(f_mid) < 1e-6:
            lo = hi = mid_sigma
            break
        if f_mid > 0:
            hi = mid_sigma
        else:
            lo = mid_sigma
    sigma = (lo + hi) / 2.0
    return _bs_call_delta(S, K, T, sigma)


def _option_delta(opt: dict[str, Any], spot: float, T: float) -> float | None:
    """Real Tradier greeks first; BS-implied-from-mid fallback (see module
    docstring — this is the one documented deviation from triage29)."""
    d = opt.get("delta")
    if d is not None:
        try:
            d = float(d)
            if math.isfinite(d) and 0.0 <= d <= 1.0:
                return d
        except (TypeError, ValueError):
            pass
    bid, ask = float(opt.get("bid") or 0), float(opt.get("ask") or 0)
    if ask <= bid or bid <= 0:
        return None
    mid = (bid + ask) / 2.0
    return _implied_delta_from_mid(spot, float(opt["strike"]), T, mid)


def _calls_by_strike(chain: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for o in chain.get("options") or []:
        if o.get("type") != "call":
            continue
        try:
            k = int(o["strike"])
        except (KeyError, TypeError, ValueError):
            continue
        bid, ask = float(o.get("bid") or 0), float(o.get("ask") or 0)
        if ask <= 0 or ask <= bid:
            continue
        out[k] = o
    return out


def _time_to_close(now_ct: datetime | None) -> float:
    """Fraction-of-a-trading-year to the 15:00 CT (16:00 ET) close, matching
    triage29's T_ENTRY convention (minutes-to-close / 390 / 252). Falls back
    to triage29's own fixed 10:30 ET entry value when `now_ct` is unavailable
    (e.g. a bot-preview call with no live clock)."""
    if now_ct is None:
        return (330.0 / 390.0) / 252.0
    close_ct = datetime.combine(now_ct.date(), time(15, 0), tzinfo=now_ct.tzinfo)
    minutes_left = max(1.0, (close_ct - now_ct).total_seconds() / 60.0)
    return (minutes_left / 390.0) / 252.0


def build_delta_butterfly_signal(
    *,
    chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    now_ct: datetime | None = None,
    diag: list[str] | None = None,
) -> DeltaButterflySignal | None:
    """Build a MONARCH delta-targeted butterfly signal, or return None.

    `diag` collects a human-readable rejection reason (surfaced into
    scan_activity.reason), same convention as long_butterfly.
    """
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    spot = float(chain.get("spot") or 0)
    if spot <= 0:
        return _reject("missing_spot")

    vix = float(chain.get("vix") or 0)
    if not (MONARCH_VIX_Q1 < vix <= MONARCH_VIX_Q2):
        return _reject(
            f"vix_outside_mid_tercile: vix={vix:.2f} "
            f"band=({MONARCH_VIX_Q1:.2f},{MONARCH_VIX_Q2:.2f}]"
        )

    calls = _calls_by_strike(chain)
    if not calls:
        return _reject("no_valid_calls")

    strikes = sorted(calls)
    min_dist = min(abs(k - spot) for k in strikes)
    tied = [k for k in strikes if abs(k - spot) == min_dist]
    body = min(tied)  # tie-break toward the lower strike, matches triage29

    wing_delta_target = float(config.get("wing_delta_target", 0.05))
    T = _time_to_close(now_ct)

    candidates = []
    for k in strikes:
        if k <= body:
            continue
        d = _option_delta(calls[k], spot, T)
        if d is None:
            continue
        dist = abs(d - wing_delta_target)
        if dist <= DELTA_TOL:
            candidates.append((dist, k, d))
    if not candidates:
        return _reject(
            f"no_wing_within_tolerance: body={body} target={wing_delta_target} "
            f"tol={DELTA_TOL}"
        )
    candidates.sort(key=lambda c: c[0])
    _, upper_strike, realized_delta = candidates[0]
    offset = upper_strike - body
    lower_strike = body - offset

    body_opt = calls.get(body)
    lower_opt = calls.get(lower_strike)
    upper_opt = calls.get(upper_strike)
    if body_opt is None or lower_opt is None:
        return _reject(
            f"strike_missing: body={body} lower={lower_strike} upper={upper_strike}"
        )

    body_bid = float(body_opt["bid"])
    lower_ask = float(lower_opt["ask"])
    upper_ask = float(upper_opt["ask"])
    if body_bid <= 0 or lower_ask <= 0 or upper_ask <= 0:
        return _reject("non_positive_quote")

    # REAL NBBO cross — wings at ASK, body at BID (x2). No mid, ever.
    debit = round(lower_ask + upper_ask - 2.0 * body_bid, 4)
    wing_width = offset
    if wing_width <= 0:
        return _reject(f"degenerate_wings: body={body} offset={offset}")
    if debit <= 0:
        return _reject(f"non_positive_debit: debit={debit:.2f}")

    max_loss_per = debit * 100.0
    max_profit_per = (wing_width - debit) * 100.0
    if max_profit_per <= 0:
        return _reject(
            f"non_positive_max_profit: wing={wing_width} debit={debit:.2f}"
        )

    bp_pct = float(config.get("bp_pct", 0.20))
    raw_max_contracts = int(config.get("max_contracts", 1) or 0)
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    contracts = (
        max(0, raw_contracts) if raw_max_contracts <= 0
        else max(0, min(raw_max_contracts, raw_contracts))
    )
    if contracts < 1:
        return _reject(
            f"sizing_below_one: equity={equity:.0f} bp_pct={bp_pct} "
            f"max_loss_per={max_loss_per:.0f}"
        )

    # Unreachable by construction, same convention as RIPPLE/SPLASH/TIDE: the
    # hold is to cash settlement, no intraday stop or target. decide_exit()
    # never reaches these for a settle_at_expiry bot, but they are set to the
    # documented "no stop" sentinels so the config UI never implies a live one.
    pt_pct = float(config.get("pt_pct", 1.0))
    sl_pct = float(config.get("sl_pct", 3.0))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_loss_per * contracts

    return DeltaButterflySignal(
        ticker=chain.get("ticker", "SPY"),
        expiration=chain["expiration"],
        body_strike=body,
        lower_strike=lower_strike,
        upper_strike=upper_strike,
        lower_ask=lower_ask,
        body_bid=body_bid,
        upper_ask=upper_ask,
        debit=debit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        wing_width=wing_width,
        wing_delta_target=wing_delta_target,
        realized_delta=float(realized_delta),
        vix_at_entry=vix,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
    )
