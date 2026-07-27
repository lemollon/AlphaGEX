"""UPDRAFT / BACKDRAFT — single-leg long 0DTE call on crowded put flow.

Both bots buy the same instrument (a SPY 0DTE call one strike OTM) and differ
only in what triggers them, so one module serves both via `mode`.

    UPDRAFT    flow_imb_30 <= flow_max   (0DTE tape is put-heavy)
           AND r30_bp      >= r30_min    (spot is UP over the last 30 min)

    BACKDRAFT  flow_imb_30 <  flow_max   (extreme put-heavy, ~2.1x calls)
           AND spot > put_wall           (above the live intraday put wall)

Economic rationale: both fade a put-buying crowd that the tape is running
over. UPDRAFT requires momentum confirmation, BACKDRAFT requires flow
extremity plus dealer-gamma support underneath. In research the two shared
ZERO entry minutes, so they are genuinely separate signals rather than one
trade wearing two hats.

Debit structure — entry_price is the call mid, max loss is the full premium.
This mirrors dip_buy (UNDERTOW) exactly so the executor, mark-to-market and
close paths work unchanged.

RESEARCH STATUS — READ BEFORE ARMING
------------------------------------
Full sample 2023-26: n=843, +15.92%/trade, t=3.30, 248 trades/yr, 4/4 years
positive, beats a time-of-day-matched placebo 30/30 (placebo -8.10%).
Held-out 2025-26: n=358, +12.83%, t=1.55 — the 95% CI is [-2.00%, +28.98%]
and INCLUDES ZERO. This is an UNCONFIRMED candidate. Paper only.

Entry timing: the edge is concentrated in the FIRST touch of a signal burst
(all 906 research signal-minutes gave +5.01%; first-touch-only gave +15.30%).
A 5-minute scan cadence was measured to retain 86% of the edge, which is why
this can run here at all — but only if it enters on the first qualifying
scan and then stands down. The scanner's one-entry-per-burst behaviour and
the `cooldown_min` parameter below both exist for that reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

# Both bots trade calls only. The put side was tested across a 4x4 threshold
# surface and REFUTED: 0 of 16 held-out cells positive, median -10.76%.
# SPY's upward drift makes long puts a losing base rate. Do not add a put leg.
SIDE = "call"

DEFAULT_PARAMS: dict[str, Any] = {
    # UPDRAFT gates (quantiles fitted on 2023-24 and frozen)
    "flow_max": -0.1378,      # flow_imb_30 must be <= this
    "r30_min": 19.23,         # 30-min return in bp must be >= this
    # BACKDRAFT gates
    "backdraft_flow_max": -0.35,
    "require_put_wall": True,
    # shared
    "strike_offset": 1,       # +1 strike OTM
    "hold_minutes": 45,       # UPDRAFT 45, BACKDRAFT 30 (set per bot)
    "min_option_price": 0.10,
    "max_spread_pct": 0.15,
    "cooldown_min": 45,       # do not re-enter the same burst
}


@dataclass(frozen=True)
class UpdraftSignal:
    ticker: str
    expiration: date
    strike: float
    call_mid: float
    spot: float
    mode: str
    flow_imb_30: float
    r30_bp: float | None
    put_wall: float | None
    hold_minutes: int

    def legs(self) -> list[dict[str, Any]]:
        return [{
            "strike": self.strike, "type": SIDE, "action": "buy",
            "quantity": 1, "expiration": self.expiration,
            "entry_price": self.call_mid,
        }]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "strike": self.strike, "spot": self.spot,
            "call_mid": self.call_mid, "flow_imb_30": self.flow_imb_30,
            "r30_bp": self.r30_bp, "put_wall": self.put_wall,
            "hold_minutes": self.hold_minutes,
        }


def _otm_call(chain: dict, spot: float, offset: int) -> dict | None:
    """The call `offset` strikes above spot.

    Research used off = round(strike - spot) on SPY's $1 0DTE grid, so the
    target strike is the nearest listed strike at or above spot + offset.
    """
    calls = [o for o in chain.get("options", []) if o.get("type") == SIDE]
    if not calls:
        return None
    target = spot + float(offset)
    at_or_above = [o for o in calls if float(o["strike"]) >= target]
    pool = at_or_above or calls
    return min(pool, key=lambda o: abs(float(o["strike"]) - target))


def build_updraft_signal(
    *,
    chain: dict[str, Any],
    today: date,
    params: dict[str, Any],
    mode: str = "updraft",
    diag: list[str] | None = None,
) -> UpdraftSignal | None:
    """Build a long-call signal, or return None with a reason in `diag`.

    `chain` must carry a "flow" block from flow_store.record_snapshot — the
    30-minute imbalance cannot be read from one snapshot because Tradier
    reports volume cumulatively.
    """
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    p = {**DEFAULT_PARAMS, **(params or {})}

    spot = float(chain.get("spot") or 0)
    if spot <= 0:
        return _reject("missing_spot")

    flow = chain.get("flow") or {}
    fi = flow.get("flow_imb_30")
    r30 = flow.get("r30_bp")
    if fi is None:
        return _reject(f"flow_unavailable: {flow.get('reason', 'no flow block')}")

    if mode == "updraft":
        if fi > float(p["flow_max"]):
            return _reject(
                f"flow_not_put_heavy: imb={fi:.4f} need<={float(p['flow_max']):.4f}")
        if r30 is None:
            return _reject("r30_unavailable")
        if r30 < float(p["r30_min"]):
            return _reject(
                f"no_updraft: r30={r30:.1f}bp need>={float(p['r30_min']):.1f}bp")
        put_wall = None
    elif mode == "backdraft":
        if fi >= float(p["backdraft_flow_max"]):
            return _reject(
                f"flow_not_extreme: imb={fi:.4f} "
                f"need<{float(p['backdraft_flow_max']):.4f}")
        put_wall = (chain.get("gex") or {}).get("put_wall")
        if bool(p["require_put_wall"]):
            if put_wall is None:
                return _reject("no_put_wall: gex unavailable")
            if spot <= float(put_wall):
                return _reject(
                    f"below_put_wall: spot={spot:.2f} wall={float(put_wall):.2f}")
    else:
        return _reject(f"unknown_mode: {mode}")

    call = _otm_call(chain, spot, int(p["strike_offset"]))
    if call is None:
        return _reject("no_call_strikes")
    bid = float(call.get("bid") or 0)
    ask = float(call.get("ask") or 0)
    mid = (bid + ask) / 2.0
    if mid < float(p["min_option_price"]):
        return _reject(f"price_too_low: mid={mid:.2f} "
                       f"min={float(p['min_option_price']):.2f}")
    spread_pct = (ask - bid) / mid if mid > 0 else 999.0
    if spread_pct > float(p["max_spread_pct"]):
        return _reject(f"spread_too_wide: {spread_pct:.3f} "
                       f"max={float(p['max_spread_pct']):.3f}")

    return UpdraftSignal(
        ticker=chain.get("ticker", "SPY"),
        expiration=chain.get("expiration") or today,
        strike=float(call["strike"]),
        call_mid=round(mid, 2),
        spot=spot,
        mode=mode,
        flow_imb_30=fi,
        r30_bp=r30,
        put_wall=float(put_wall) if put_wall is not None else None,
        hold_minutes=int(p["hold_minutes"]),
    )
