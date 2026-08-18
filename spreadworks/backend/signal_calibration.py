"""Does the signal still work? — the decay monitor.

An edge is a depreciating asset. This repo has already watched one die in the
open (Cboe CNDR's iron-condor premium went +5.93% to -2.06% by decade), and
the two-stage watcher is a behavioural edge, which is exactly the kind that
erodes as behaviour changes. Shipping it without a way to notice that would be
the same mistake as shipping a bot with no drawdown limit.

WHY THIS IS NOT "WAIT AND SEE HOW THE LIVE ALERTS DO"

The watcher fires on roughly 8.7% of sessions (~22/yr). Judging it on live
firings alone would need ~2 years before the sample said anything, and would
say nothing at all in the meantime. But the INPUTS accumulate every single
session whether it fires or not: a 10:00 flow reading, a price tape, a close.
So the honest approach is to re-score the whole rule over an expanding window
every night and watch the rolling number, rather than waiting for alerts.

    seed  : 896 sessions of backtest (2023-01-03 -> 2026-08-11), committed CSV
    live  : one row appended per session from what production already stores
            (risk_flow_snapshots + risk_session_log + risk_confirm_state)

Nothing new is captured. The evaluation is a read over data the system already
writes, which is the only reason it can be trusted to keep running.

🚨 THE TRIPWIRES BELOW ARE PRE-REGISTERED — set 2026-08-18, BEFORE any live
firing existed, and deliberately expressed as inequalities against a
CONTEMPORANEOUS base rate rather than against the backtest's 63.2%. A threshold
picked after seeing the data is not a threshold, it is a rationalisation. The
same discipline as PROMOTION_QUIET_NEEDED on the squeeze tell.

FAIL-SAFE DIRECTION: on breach the pivot DISARMS. The alert can be wrong and
cost nothing; the pivot acting on a dead signal costs money. When the evidence
stops supporting the action, the action stops — not the other way round.
"""
from __future__ import annotations

import csv
import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import Column, Date, Float, Integer, String, text

from .db import Base, SessionLocal, engine

logger = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")
SEED_CSV = Path(__file__).resolve().parent / "data" / "signal_eval_baseline.csv"

# --- pre-registered, 2026-08-18 -------------------------------------------
WINDOW_MONTHS = 24          # rolling evaluation window
MIN_N = 25                  # below this the window says UNDERPOWERED, not PASS
ARM_Z = 1.5                 # must mirror routes_risk.CONFIRM_ARM_Z
# Stage 2 must beat the SAME-WINDOW unflagged base by more than noise. Using
# the contemporaneous base is what makes this robust to the whole market
# changing: if continuation rises everywhere, the bar rises with it.
DISARM_MARGIN = 0.0         # LCB must exceed base by this much
WARN_MARGIN = 0.05          # point estimate within 5pts of base -> warn
# Firing rate outside this band means the z threshold no longer selects what it
# was tuned to select — recalibrate the cut rather than trusting the rate.
RATE_LO, RATE_HI = 0.04, 0.16      # share of sessions armed (seed: 0.087)
STAGE1_MIN_LIFT = 1.50      # |move to close| >= 0.5% lift on armed days


class SignalEval(Base):
    """One row per session — the raw material for every number below."""
    __tablename__ = "sw_signal_eval"
    d = Column(Date, primary_key=True)
    pcz = Column(Float)             # stage-1 put/call mix z at 10:00 CT
    pvz = Column(Float)
    tvz = Column(Float)
    armed = Column(Integer)         # stage 1 passed
    ref_spot = Column(Float)        # 10:00 CT
    close_spot = Column(Float)
    fired_dir = Column(String(4))   # stage 2 confirmation, '' if none
    fired_spot = Column(Float)
    fired_min = Column(Integer)
    continued = Column(Integer)     # 1 if it kept going to the close
    move_pct = Column(Float)        # 10:00 -> close
    source = Column(String(8))      # 'seed' | 'live'


def _wilson_lcb(k: int, n: int, z: float = 1.96) -> float:
    """Lower bound of a 95% Wilson interval. Used instead of the raw rate so a
    small window cannot pass on luck — with n=10 the point estimate is nearly
    meaningless and the LCB says so."""
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d)


def seed_from_csv() -> int:
    """Load the committed backtest rows. ON CONFLICT DO NOTHING, so it is
    idempotent and can never overwrite a live-scored session.

    🚨 Runs unconditionally on every boot, NOT behind an emptiness guard — the
    guarded version of this pattern on gamma_baseline let one stray row skip
    all 1,660 and left a percentile silently unusable for weeks.
    """
    if SessionLocal is None or not SEED_CSV.exists():
        return 0
    # 🚨 Create our own table first. `Base.metadata.create_all()` runs at boot
    # BEFORE this module is imported, so SignalEval is not yet registered on
    # the metadata when it fires — on a cold database the table would simply
    # never exist and the seed would fail with "no such table" every boot,
    # silently, leaving the decay monitor permanently blind. Caught by running
    # the seed against an empty database rather than assuming ordering.
    try:
        if engine is not None:
            Base.metadata.create_all(bind=engine, tables=[SignalEval.__table__])
    except Exception as e:      # noqa: BLE001
        logger.warning("[calib] table create failed: %r", e)
        return 0
    db = SessionLocal()
    n = 0
    try:
        with open(SEED_CSV, newline="") as f:
            for r in csv.DictReader(f):
                exists = db.get(SignalEval, date.fromisoformat(r["d"]))
                if exists:
                    continue
                db.add(SignalEval(
                    d=date.fromisoformat(r["d"]),
                    pcz=float(r["pcz"]) if r["pcz"] else None,
                    pvz=float(r["pvz"]) if r["pvz"] else None,
                    tvz=float(r["tvz"]) if r["tvz"] else None,
                    armed=int(r["armed"]),
                    ref_spot=float(r["ref_spot"]) if r["ref_spot"] else None,
                    close_spot=float(r["close_spot"]) if r["close_spot"] else None,
                    fired_dir=r["fired_dir"] or None,
                    fired_spot=float(r["fired_spot"]) if r["fired_spot"] else None,
                    fired_min=int(r["fired_min"]) if r["fired_min"] else None,
                    continued=int(r["continued"]) if r["continued"] != "" else None,
                    move_pct=float(r["move_pct"]) if r["move_pct"] else None,
                    source="seed"))
                n += 1
        db.commit()
    except Exception as e:      # noqa: BLE001
        db.rollback()
        logger.warning("[calib] seed failed: %r", e)
    finally:
        db.close()
    if n:
        logger.info("[calib] seeded %d evaluation rows", n)
    return n


def score_session(d: date) -> bool:
    """Append one completed session, scored exactly as production ran it.

    Reads only what the system already stores. Returns True if a row was
    written. Deliberately re-derives `continued` from the stored tape rather
    than trusting any in-memory state, so the record is reproducible from the
    database alone.
    """
    if SessionLocal is None:
        return False
    from .routes_risk import (RiskConfirmState, RiskSessionLog,
                              _flow_history, _pc_z, _z, _latest_snapshot)
    db = SessionLocal()
    try:
        if db.get(SignalEval, d):
            return False
        snap = _latest_snapshot(d)
        if snap is None:
            return False
        prior = [r for r in _flow_history() if r["d"] < d]
        pcz = _pc_z(snap, prior)
        pvz = _z(snap["putv"], [r["putv"] for r in prior])
        tvz = _z(snap["totv"], [r["totv"] for r in prior])

        cs = db.get(RiskConfirmState, d)
        tape = (db.query(RiskSessionLog)
                  .filter(RiskSessionLog.d == d)
                  .order_by(RiskSessionLog.minute_ct).all())
        ref = (cs.ref_spot if cs and cs.ref_spot else
               (tape[0].spot if tape else None))
        close = (cs.close_spot if cs and cs.close_spot else
                 (tape[-1].spot if tape else None))
        if ref is None or close is None:
            return False

        fdir = cs.fired_dir if cs else None
        cont = None
        if fdir and cs and cs.fired_spot:
            run = (close - cs.fired_spot) * (-1 if fdir == "DOWN" else 1)
            cont = 1 if run > 0 else 0
        db.add(SignalEval(
            d=d, pcz=pcz, pvz=pvz, tvz=tvz,
            armed=1 if (pcz or -9) > ARM_Z else 0,
            ref_spot=ref, close_spot=close, fired_dir=fdir,
            fired_spot=cs.fired_spot if cs else None,
            fired_min=cs.fired_at.hour * 60 + cs.fired_at.minute
                      if (cs and cs.fired_at) else None,
            continued=cont, move_pct=(close - ref) / ref * 100.0,
            source="live"))
        db.commit()
        logger.info("[calib] scored %s (armed=%s fired=%s cont=%s)",
                    d, (pcz or -9) > ARM_Z, fdir, cont)
        return True
    except Exception as e:      # noqa: BLE001
        db.rollback()
        logger.warning("[calib] score_session(%s) failed: %r", d, e)
        return False
    finally:
        db.close()


def report(today: date | None = None) -> dict:
    """The scorecard, plus a verdict against the pre-registered lines."""
    today = today or datetime.now(CT).date()
    cutoff = today - timedelta(days=int(WINDOW_MONTHS * 30.44))
    out: dict = {"window_months": WINDOW_MONTHS, "from": cutoff.isoformat(),
                 "to": today.isoformat(), "verdict": "UNKNOWN", "reasons": [],
                 "pre_registered": {
                     "set_on": "2026-08-18",
                     "disarm_if": "95% LCB of armed-day continuation <= the "
                                  "same-window unflagged base rate",
                     "warn_if": f"continuation within {WARN_MARGIN:.0%} of base, "
                                f"or stage-1 lift < {STAGE1_MIN_LIFT}x",
                     "recalibrate_if": f"armed share outside "
                                       f"{RATE_LO:.0%}-{RATE_HI:.0%} of sessions",
                 }}
    if SessionLocal is None:
        out["reasons"].append("no database")
        return out
    db = SessionLocal()
    try:
        rows = (db.query(SignalEval)
                  .filter(SignalEval.d >= cutoff, SignalEval.d <= today).all())
    except Exception as e:      # noqa: BLE001
        out["reasons"].append(f"query failed: {e!r}")
        return out
    finally:
        db.close()

    n = len(rows)
    out["sessions"] = n
    out["live_sessions"] = sum(1 for r in rows if r.source == "live")
    if n == 0:
        out["reasons"].append("no rows in window")
        return out

    armed = [r for r in rows if r.armed]
    out["armed"] = len(armed)
    out["armed_share"] = len(armed) / n

    fa = [r for r in armed if r.fired_dir and r.continued is not None]
    fu = [r for r in rows if not r.armed and r.fired_dir and r.continued is not None]
    out["n_armed_fired"] = len(fa)
    out["n_base_fired"] = len(fu)
    k = sum(r.continued for r in fa)
    out["continuation"] = (k / len(fa)) if fa else None
    out["continuation_lcb"] = _wilson_lcb(k, len(fa)) if fa else None
    out["base_continuation"] = (sum(r.continued for r in fu) / len(fu)) if fu else None

    # stage 1 — does an armed day still see a bigger move at all?
    big = lambda rs: (sum(1 for r in rs if abs(r.move_pct or 0) >= 0.5) / len(rs)) if rs else None
    a1, b1 = big(armed), big([r for r in rows if not r.armed])
    out["stage1_armed_bigmove"] = a1
    out["stage1_base_bigmove"] = b1
    out["stage1_lift"] = (a1 / b1) if (a1 and b1) else None

    # --- verdict against the pre-registered lines ---
    reasons = out["reasons"]
    if len(fa) < MIN_N:
        out["verdict"] = "UNDERPOWERED"
        reasons.append(f"only {len(fa)} armed firings in the window "
                       f"(need {MIN_N}); no conclusion either way")
        return out
    base = out["base_continuation"] or 0.0
    if out["continuation_lcb"] <= base + DISARM_MARGIN:
        out["verdict"] = "DISARM"
        reasons.append(f"continuation LCB {out['continuation_lcb']:.1%} has fallen "
                       f"to the unflagged base {base:.1%} — the gate no longer "
                       f"separates, so the pivot is acting on nothing")
    elif out["continuation"] - base < WARN_MARGIN:
        out["verdict"] = "WARN"
        reasons.append(f"continuation {out['continuation']:.1%} is only "
                       f"{(out['continuation']-base):.1%} above base {base:.1%}")
    else:
        out["verdict"] = "PASS"
    if out["stage1_lift"] is not None and out["stage1_lift"] < STAGE1_MIN_LIFT:
        if out["verdict"] == "PASS":
            out["verdict"] = "WARN"
        reasons.append(f"stage-1 lift {out['stage1_lift']:.2f}x is below "
                       f"{STAGE1_MIN_LIFT}x — the flag is selecting less well")
    if not (RATE_LO <= out["armed_share"] <= RATE_HI):
        if out["verdict"] == "PASS":
            out["verdict"] = "WARN"
        reasons.append(f"armed on {out['armed_share']:.1%} of sessions, outside "
                       f"the {RATE_LO:.0%}-{RATE_HI:.0%} band — the z threshold "
                       f"has drifted and the CUT needs re-deriving, not the rule")
    return out


def enforce(rep: dict) -> list[str]:
    """Act on a DISARM verdict by setting pivot_on_confirm = 0.

    🚨 Only ever disarms. Re-arming is a human decision: a signal that recovers
    on its own inside a rolling window is more likely to be noise than a
    resurrection, and an auto-rearm would flip the fail-safe direction.
    """
    if rep.get("verdict") != "DISARM" or engine is None:
        return []
    done = []
    for bot in ("ebb", "ebb_pm"):
        try:
            with engine.begin() as conn:
                r = conn.execute(text(
                    f"UPDATE {bot}_config SET pivot_on_confirm = 0 "
                    "WHERE id = 1 AND pivot_on_confirm = 1"))
                if r.rowcount:
                    done.append(bot)
        except Exception as e:      # noqa: BLE001
            logger.warning("[calib] disarm %s failed: %r", bot, e)
    if done:
        logger.warning("[calib] DISARMED pivot on %s", ", ".join(done))
    return done
