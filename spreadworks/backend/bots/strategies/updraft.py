"""UPDRAFT / BACKDRAFT — single-leg long 0DTE call on crowded put flow.

Both bots buy the same instrument (a SPY 0DTE call one strike OTM) and differ
only in what triggers them, so one module serves both via `mode`.

    UPDRAFT    flow_imb_30 <= flow_max   (0DTE tape is put-heavy)
           AND r30_bp      >= r30_min    (spot is UP over the last 30 min)

    BACKDRAFT  flow_imb_30 <  flow_max   (extreme put-heavy, ~2.1x calls)
           AND spot > put_wall           (above the live intraday put wall)

    REVERSAL   hourly RSI(14) closes back ABOVE 30 after being below
                                         (a CONFIRMED hourly reversal)

    EM_BREACH  the session's move from open first crosses BELOW
               -em_frac x the ATM-straddle expected move  (buys a PUT:
               the day broke its priced range -> downside CONTINUATION)

    AFTERBURN  the session return is a STRONG CLOSE (>= afterburn_min_ret_pct,
               TRAIN q80 = +0.52%) near the bell -> buy a 1DTE call and hold
               OVERNIGHT (front_dte=1; the wall-clock hold_minutes timer lands
               the exit at ~08:31 CT next morning). Overnight momentum
               continuation; the only leg that holds past the close.

Economic rationale: UPDRAFT and BACKDRAFT both fade a put-buying crowd that
the tape is running over — UPDRAFT requires momentum confirmation, BACKDRAFT
requires flow extremity plus dealer-gamma support underneath. REVERSAL is a
different mechanism entirely: a multi-day hourly oversold state resolving
upward. In research all three shared ZERO entry minutes, so they are
genuinely separate signals rather than one trade wearing three hats.

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
    # REVERSAL gates
    "rsi_threshold": 30.0,    # cross back ABOVE this = the trigger
    "rsi_period": 14,
    # EM_BREACH gates
    "em_frac": 0.8,           # breach depth, FIXED A PRIORI in research
    # skip days whose OPEN already priced a catalyst (TRAIN q90 = 0.75%):
    # the edge is in UNPRICED surprises; measured NEGATIVE above this.
    "max_open_straddle_pct": 0.75,
    # AFTERBURN gate — session return must be at least this (TRAIN q80).
    # Dose-response is MONOTONE above it (q70<q80<q90 at every strike).
    "afterburn_min_ret_pct": 0.52,
    # shared
    "strike_offset": 1,       # +1 strike OTM (REVERSAL uses 0 = ATM)
    "hold_minutes": 45,       # UPDRAFT 45, BACKDRAFT 30, REVERSAL 45
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
    flow_imb_30: float | None       # None for REVERSAL — it has no flow gate
    r30_bp: float | None
    put_wall: float | None
    hold_minutes: int
    rsi: float | None = None        # REVERSAL only, for the audit trail
    prev_rsi: float | None = None
    side: str = "call"              # EM_BREACH buys a put; everyone else calls
    em_move_pct: float | None = None
    em_straddle_pct: float | None = None
    # Fields the executor requires of every signal (see executor.open_position):
    # .debit, .contracts, .max_profit, .max_loss, .pt_target_pnl, .sl_target_pnl
    debit: float = 0.0            # premium paid per contract (== call_mid)
    contracts: int = 0
    max_profit: float = 0.0       # per contract, cosmetic headline
    max_loss: float = 0.0         # per contract == debit * 100
    pt_target_pnl: float = 0.0    # $ total — deliberately unreachable
    sl_target_pnl: float = 0.0    # $ total — the -50% stop

    def legs(self) -> list[dict[str, Any]]:
        # expiration MUST be an ISO string: legs are JSON-serialised into
        # the positions table and the scanner reads it back with
        # date.fromisoformat(legs[0]["expiration"]).
        exp = self.expiration
        exp_s = exp.isoformat() if hasattr(exp, "isoformat") else str(exp)
        return [{
            "strike": self.strike, "type": self.side, "action": "buy",
            "side": "long", "quantity": 1, "expiration": exp_s,
            "entry_price": self.call_mid,
        }]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "strike": self.strike, "spot": self.spot,
            "call_mid": self.call_mid, "flow_imb_30": self.flow_imb_30,
            "r30_bp": self.r30_bp, "put_wall": self.put_wall,
            "hold_minutes": self.hold_minutes,
            "rsi": self.rsi, "prev_rsi": self.prev_rsi,
        }


def _pick_option(chain: dict, spot: float, offset: int, right: str) -> dict | None:
    """Nearest listed strike to the target for `right` ('call' or 'put').

    Calls target spot + offset (offset 1 = 1 OTM above); puts target
    spot - offset (offset 1 = 1 OTM below). offset 0 = ATM for both.
    """
    pool = [o for o in chain.get("options", []) if o.get("type") == right]
    if not pool:
        return None
    target = spot + float(offset) if right == "call" else spot - float(offset)
    return min(pool, key=lambda o: abs(float(o["strike"]) - target))


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
    config: dict[str, Any] | None = None,
    equity: float = 10000.0,
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
    # REVERSAL does not read flow at all — its trigger is the hourly RSI
    # cross. Demanding a flow block here would blind it whenever flow_store
    # has not yet accumulated 30 minutes, which has nothing to do with its
    # signal.
    if mode in ("updraft", "backdraft") and fi is None:
        return _reject(f"flow_unavailable: {flow.get('reason', 'no flow block')}")

    if mode == "updraft":
        if fi > float(p["flow_max"]):
            return _reject(
                f"flow_not_put_heavy: imb={fi:.4f} need<={float(p['flow_max']):.4f}")
        if r30 is None:
            # Normal between 08:31 and 09:00 CT: the volume window truncates
            # at the open but the 30-minute return does not, so BACKDRAFT is
            # live in that half hour and UPDRAFT is not (flow_store docstring).
            return _reject(
                f"r30_unavailable: {flow.get('r30_reason') or 'no r30'}")
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
    elif mode == "reversal":
        # MUST be the recovery CROSS, never "RSI is currently low". Buying
        # into an oversold tape was measured at -3.87% (SPY) / -3.74% (XSP);
        # waiting for the cross back up gives +10.68% / +12.58%. The sign
        # flips on this distinction, so the flag is computed in flow_store
        # and only the cross is honoured here.
        rsi = chain.get("rsi") or {}
        if rsi.get("rsi") is None:
            return _reject(
                f"rsi_unavailable: {rsi.get('reason') or 'no rsi block'}")
        if not rsi.get("recovery_cross"):
            return _reject(
                f"no_rsi_recovery: rsi={float(rsi['rsi']):.1f} "
                f"prev={rsi.get('prev_rsi')} "
                f"(need prev<{float(p['rsi_threshold']):.0f}<=rsi)")
        put_wall = None
    elif mode == "em_breach":
        # The day must have JUST broken below -em_frac x its priced move.
        # Research: continuation (+6-13%/trade), beats a time-matched placebo
        # by +28-42pts, and it is the documented exception to "long puts
        # always lose" — the drift objection is suspended once the day has
        # already broken its priced range.
        em = chain.get("em") or {}
        day_open = em.get("day_open")
        if not day_open:
            return _reject(
                f"em_unavailable: {em.get('reason') or 'no em block'}")
        from ..flow_store import atm_straddle_pct
        straddle = atm_straddle_pct(chain.get("options") or [], spot)
        if straddle is None or straddle <= 0:
            return _reject("no_straddle: cannot price the expected move")
        move_pct = 100.0 * (spot / float(day_open) - 1.0)
        frac = float(p["em_frac"])
        if move_pct >= -frac * straddle:
            return _reject(f"no_breach: move={move_pct:+.2f}% "
                           f"need<{-frac * straddle:.2f}%")
        # catalyst filter: skip days whose OPEN priced a big move. Unknown
        # open straddle degrades to the UNCONDITIONAL (headline) version.
        open_str = em.get("open_straddle_pct")
        if open_str is not None and float(open_str) >= float(p["max_open_straddle_pct"]):
            return _reject(f"catalyst_priced: open_straddle={float(open_str):.2f}% "
                           f">= {float(p['max_open_straddle_pct']):.2f}%")
        # FIRST TOUCH ONLY: if the previous snapshot was already breached the
        # move is stale (BACKDRAFT precedent: later minutes chase). Unknown
        # prior state rejects — miss a day rather than take a stale entry.
        ps, pstr = em.get("prev_spot"), em.get("prev_straddle_pct")
        if ps is not None:
            if pstr is None:
                return _reject("prev_breach_unknown: prior snapshot has no straddle")
            prev_move = 100.0 * (float(ps) / float(day_open) - 1.0)
            if prev_move < -frac * float(pstr):
                return _reject(f"not_first_touch: already breached at prior "
                               f"scan (prev_move={prev_move:+.2f}%)")
        put_wall = None
    elif mode in ("afterburn", "weekender"):
        # WEEKENDER is AFTERBURN's Friday twin: same close-momentum gate
        # machinery, but afterburn_min_ret_pct is set to -99 in its registry
        # entry (UNCONDITIONAL — research showed ALL Fridays positive both
        # periods, the strong-close split had only n=30) and the hold spans
        # the weekend (front_dte=3, hold_minutes=3936 -> Monday ~08:31 CT).
        # Strong close -> overnight 1DTE call. 9/9 research cells positive in
        # both periods, monotone in the threshold, 4/4 years. Entry window is
        # the last minutes of the session (registry: 14:50-14:59 CT), so the
        # day's return is effectively final when this gate is read.
        em = chain.get("em") or {}
        day_open = em.get("day_open")
        if not day_open:
            return _reject(
                f"em_unavailable: {em.get('reason') or 'no em block'}")
        move_pct = 100.0 * (spot / float(day_open) - 1.0)
        need = float(p["afterburn_min_ret_pct"])
        if move_pct < need:
            return _reject(f"weak_close: move={move_pct:+.2f}% "
                           f"need>={need:.2f}%")
        put_wall = None
    else:
        return _reject(f"unknown_mode: {mode}")

    right = "put" if mode == "em_breach" else SIDE
    call = _pick_option(chain, spot, int(p["strike_offset"]), right)
    if call is None:
        return _reject(f"no_{right}_strikes")
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

    # --- sizing, mirroring dip_buy so the executor sees a familiar shape ---
    cfg = config or {}
    debit = round(mid, 4)
    max_loss_per = debit * 100.0        # long call: max loss IS the premium
    bp_pct = float(cfg.get("bp_pct", 0.02))
    raw = int((equity * bp_pct) // max_loss_per) if max_loss_per > 0 else 0
    cap = int(cfg.get("max_contracts") or 0)
    contracts = min(raw, cap) if cap > 0 else raw
    if contracts < 1:
        return _reject(f"size_zero: equity={equity:.0f} bp={bp_pct:.3f} "
                       f"max_loss_per={max_loss_per:.0f}")

    # pt_pct is deliberately unreachable (registry sets 99.0) — the timer is
    # the exit. sl_pct 0.50 gives the researched -50% stop on premium.
    pt_pct = float(cfg.get("pt_pct", 9.9999))   # NUMERIC(5,4) ceiling
    sl_pct = float(cfg.get("sl_pct", 0.50))

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
        rsi=(chain.get("rsi") or {}).get("rsi"),
        prev_rsi=(chain.get("rsi") or {}).get("prev_rsi"),
        side=right,
        em_move_pct=(100.0 * (spot / float((chain.get("em") or {}).get("day_open"))
                              - 1.0)
                     if mode in ("em_breach", "afterburn", "weekender")
                     else None),
        em_straddle_pct=(straddle if mode == "em_breach" else None),
        debit=debit,
        contracts=contracts,
        max_profit=pt_pct * max_loss_per,
        max_loss=max_loss_per,
        pt_target_pnl=pt_pct * max_loss_per * contracts,
        sl_target_pnl=sl_pct * max_loss_per * contracts,
    )
