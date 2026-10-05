"""CINDER — SPY 1DTE debit call spread, LIVE two-leg (entry + exit) scanner.

Mirrors `squeeze_reactive_alerts.py`'s exact architecture: APScheduler job
registration via `backend/__init__.py`, the same never-silently-blank
freshness/blocked-state API contract (`routes_cinder.py`'s `/state`), and
`backend._send_webhook_sync` for alerts. CINDER is a DIFFERENT, SEPARATE
signal from squeeze-reactive and from the gamma-regime squeeze signal — it
does not read or write their tables and nothing here edits
`squeeze_reactive_alerts.py`, `routes_squeeze_reactive.py`, `gamma_regime.py`,
`routes_squeeze.py`, `squeeze_intraday_alerts.py`, or their tables. It DOES
import `gamma_state` (gamma_regime.py) and `live_vix_ratio`
(routes_squeeze.py) rather than re-implement either.

BACKTEST RECORD (real NBBO fills throughout — this module implements an
already-decided strategy, it does not research a new one): 10 trades,
2024-2026, 90% win rate, +12.32 total units. Fills were scored ask-at-entry
on BOTH legs separately (never a true multi-leg combo fill) because
Robinhood's agentic order API rejects multi-leg tickets — see the
`robinhood-agentic-rejects-multi-leg-orders` memory finding. Legging the
real order is a LOCAL EXECUTION bot's concern (being built in parallel,
elsewhere, NOT this module) — this module is SIGNAL ONLY: it computes and
serves the entry strikes/debit and the live exit state so that bot can act
on it. Nothing here places an order.

ENTRY TRIGGER (all three required, evaluated once a day in a narrow window
around 11:30 AM ET):
  1. GEX:  the PRIOR session's net_gex_b (read via `gamma_regime.gamma_state`,
     which is itself prior-session-lagged by construction — never today's
     own chain) <= GEX_TRIGGER_B ($bn).
  2. VIX ratio: live VIX spot / max(trailing 20 sessions strictly before
     today) < VIX_RATIO_TRIGGER. The ratio math is `routes_squeeze.py`'s own
     `live_vix_ratio()`, imported and called as-is — not reimplemented.
  3. Term structure: VIX - VIX3M < 0 (normal contango, not backwardated).
     Both legs are read live from `sw_live_vol_indices`
     (`market_structure.py`'s `persist_vol()`/`fetch_vol_indices()` —
     columns `symbol, captured_at, price, source, source_timestamp,
     age_seconds, fresh, reason`). This is a NEW live dependency no existing
     squeeze signal uses. Missing or stale rows for EITHER symbol make this
     leg UNKNOWN, which blocks the trigger — never a silent pass.

Legs 2 and 3 share one live VIX read (`fetch_vol_reading(engine, "VIX")`) so
the module only costs one extra live quote beyond the VIX3M read.

COOLDOWN: no entry within COOLDOWN_DAYS calendar days of CINDER's own LAST
ENTRY (not last signal CHECK) — tracked off `MAX(signal_date)` in this
module's own `cinder_signals` table, which only ever gets a row on an
actual entry.

ENTRY INSTRUMENT: SPY 1DTE debit call spread — long the ATM call, short a
call STRIKE_WIDTH higher, same next-session expiry. Computed from one live
chain pull (`backend.bots.routes_helpers.LiveTradierChainProvider`, the same
chain-access pattern `gamma_regime.fetch_net_gex`/`trade_ticket` already
use) once the trigger and cooldown both clear, inside the entry window —
never outside it, and never more than once a day (the signal_date primary
key on `cinder_signals` plus the open-position guard both prevent a second
entry the same day).

EXIT: the checkpoint ladder from the backtest — spread value
(long_bid - short_ask, read from a fresh chain pull at the stored
expiration) checked on every remaining tick after entry and on the
expiration day's own morning ticks, target = 2.0x the entry debit. If never
touched, fall back to a close near 15:55-16:00 ET on the expiration day.
The CURRENT spread value and whether the target has fired are written to
`cinder_signals` on every tick the position is open (not only on close) so
`/api/spreadworks/cinder/state` can serve them live for the execution bot
to read, without that bot or this route needing its own chain pull.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, time as dtime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")

# ---- Frozen rule (ported from the backtest: 10 trades, 2024-2026, 90% WR,
# +12.32 total units) ------------------------------------------------------
GEX_TRIGGER_B = -10.0          # $bn, prior-session-lagged net_gex_b
VIX_RATIO_TRIGGER = 0.90
COOLDOWN_DAYS = 5
SPY_TICKER = "SPY"
STRIKE_WIDTH = 10.0            # short strike = ATM + $10
TARGET_MULTIPLE = 2.0          # exit target = 2.0x entry debit

SESSION_START_T = dtime(9, 30, 0)
SESSION_END_T = dtime(16, 0, 0)

# Entry is attempted once a day, in a narrow band around 11:30 AM ET (same
# "around 11:05/11:30 ET" entry-timing convention `gamma_regime.trade_ticket`
# already uses for its own sell ticket). A band rather than one instant so a
# single transient chain-pull failure at :30 gets one or two more tries
# before the window closes for the day -- never retried outside it.
ENTRY_WINDOW_START_T = dtime(11, 25, 0)
ENTRY_WINDOW_END_T = dtime(11, 35, 0)

# EOD fallback exit window on the EXPIRATION day -- identical convention to
# squeeze_reactive_alerts.py's own 15:55:00-16:00:00 ET fallback window.
EOD_FALLBACK_START_T = dtime(15, 55, 0)
EOD_FALLBACK_END_T = dtime(16, 0, 0)

# How old a sw_live_vol_indices row may be (vs NOW, not vs its own source
# timestamp -- that staleness is already baked into its `fresh` column at
# WRITE time, which says nothing about whether the capture job has since
# stopped) before this module refuses to trust it for the term-structure or
# VIX-ratio leg. market_structure.py's capture runs every minute during
# 08:00-15:59 CT weekdays; 15 minutes is >2x a missed-tick's worth of grace,
# the same cadence-miss tolerance squeeze_reactive/routes_squeeze_reactive
# already use for their own staleness gates.
VOL_READING_STALE_MINUTES = 15

CINDER_SIGNALS_TABLE = "cinder_signals"
CINDER_SCAN_LOG_TABLE = "cinder_scan_log"

CINDER_DISCORD_WEBHOOK_ENV = "CINDER_DISCORD_WEBHOOK"

_SCHEDULER: dict = {"ref": None}
CINDER_JOB_ID = "cinder_scan"


def ensure_cinder_tables(engine: Engine) -> None:
    """CREATE TABLE IF NOT EXISTS for both of this module's tables.

    `signal_date` is the natural primary key on the signals table, same
    "natural key, not a surrogate serial id" reasoning
    `squeeze_reactive_alerts.ensure_tables` already documents for its own
    SIGNALS_TABLE -- CINDER only ever writes ONE row per calendar day (the
    cooldown and the open-position guard both enforce that), so there is
    nothing a serial id would buy, and it keeps the DDL portable across
    Postgres (production) and SQLite (tests).
    """
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {CINDER_SIGNALS_TABLE} (
                signal_date DATE NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                entry_time TIMESTAMP,
                entry_spot DOUBLE PRECISION,
                long_strike DOUBLE PRECISION,
                short_strike DOUBLE PRECISION,
                expiration DATE,
                entry_debit DOUBLE PRECISION,
                current_spread_value DOUBLE PRECISION,
                target_hit BOOLEAN NOT NULL DEFAULT FALSE,
                last_checked_at TIMESTAMP,
                exit_time TIMESTAMP,
                exit_value DOUBLE PRECISION,
                exit_reason TEXT,
                raw_return DOUBLE PRECISION,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                PRIMARY KEY (signal_date)
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {CINDER_SCAN_LOG_TABLE} (
                run_at TIMESTAMP NOT NULL PRIMARY KEY,
                gex_b DOUBLE PRECISION,
                gex_pass BOOLEAN,
                vix_ratio DOUBLE PRECISION,
                vix_ratio_pass BOOLEAN,
                term_vix DOUBLE PRECISION,
                term_vix3m DOUBLE PRECISION,
                term_pass BOOLEAN,
                triggered BOOLEAN,
                cooldown_ok BOOLEAN,
                block_reason TEXT,
                entry_opened BOOLEAN NOT NULL DEFAULT FALSE,
                exit_closed BOOLEAN NOT NULL DEFAULT FALSE,
                errors INTEGER NOT NULL DEFAULT 0,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))


def scheduled_jobs() -> dict:
    """Same "never run" disambiguation as squeeze_reactive_alerts'
    scheduled_jobs() — never raises."""
    sched = _SCHEDULER.get("ref")
    if sched is None:
        return {"registered": False, "jobs": {},
                "reason": "CINDER job is not armed — no scheduler was attached."}
    out: dict = {"registered": True, "jobs": {}, "reason": None}
    try:
        job = sched.get_job(CINDER_JOB_ID)
        nxt = getattr(job, "next_run_time", None) if job else None
        out["jobs"][CINDER_JOB_ID] = nxt.isoformat() if nxt else None
    except Exception as e:  # noqa: BLE001
        out["jobs"][CINDER_JOB_ID] = None
        out["reason"] = f"job lookup failed: {e}"
    return out


def _as_datetime(value):
    """Same Postgres-datetime/SQLite-string normalization
    `squeeze_reactive_alerts._as_datetime` already applies — duplicated
    here (4 lines) rather than imported, so this module stays independent
    of that one's internals."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _as_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# ---- Cooldown / state ------------------------------------------------------

def last_entry_date(engine: Engine) -> date | None:
    """The signal_date of CINDER's own most recent entry, or None if it has
    never fired. Every row in cinder_signals IS an entry (there is no
    row-without-an-entry state), so this is simply the newest row."""
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT MAX(signal_date) FROM {CINDER_SIGNALS_TABLE}"
        )).fetchone()
    if row is None or row[0] is None:
        return None
    return _as_date(row[0])


def cooldown_ok(last_date: date | None, today: date,
                cooldown_days: int = COOLDOWN_DAYS) -> bool:
    """Pure: no prior entry, or the prior entry is at least `cooldown_days`
    calendar days behind `today`. Keyed off the LAST ENTRY date, never off
    when the trigger was last merely checked."""
    if last_date is None:
        return True
    return (today - last_date).days >= cooldown_days


def load_open_position(engine: Engine) -> dict | None:
    """The single open CINDER position, if any. Cooldown (>=5 calendar days
    between entries) comfortably exceeds a 1DTE spread's hold time, so in
    practice there is never more than one -- this still only ever returns
    the single open row rather than assuming that invariant holds."""
    with engine.begin() as conn:
        row = conn.execute(text(f"""
            SELECT signal_date, entry_time, entry_spot, long_strike,
                   short_strike, expiration, entry_debit,
                   current_spread_value, target_hit
            FROM {CINDER_SIGNALS_TABLE} WHERE status = 'open'
            ORDER BY signal_date DESC LIMIT 1
        """)).fetchone()
    if row is None:
        return None
    return {
        "signal_date": _as_date(row[0]), "entry_time": _as_datetime(row[1]),
        "entry_spot": row[2], "long_strike": row[3], "short_strike": row[4],
        "expiration": _as_date(row[5]), "entry_debit": row[6],
        "current_spread_value": row[7], "target_hit": bool(row[8]),
    }


def open_position(engine: Engine, signal_date: date, entry_time, entry_spot: float,
                  long_strike: float, short_strike: float, expiration: date,
                  entry_debit: float) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {CINDER_SIGNALS_TABLE}
                (signal_date, status, entry_time, entry_spot, long_strike,
                 short_strike, expiration, entry_debit, current_spread_value,
                 target_hit, last_checked_at)
            VALUES (:d, 'open', :et, :sp, :ls, :ss, :exp, :debit, :debit,
                    FALSE, :et)
        """), {"d": signal_date, "et": entry_time, "sp": entry_spot,
               "ls": long_strike, "ss": short_strike, "exp": expiration,
               "debit": entry_debit})


def update_open_position(engine: Engine, signal_date: date,
                         current_spread_value: float | None,
                         target_hit: bool, checked_at: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"""
            UPDATE {CINDER_SIGNALS_TABLE}
            SET current_spread_value = :v, target_hit = :th,
                last_checked_at = :ca
            WHERE signal_date = :d AND status = 'open'
        """), {"v": current_spread_value, "th": target_hit, "ca": checked_at,
               "d": signal_date})


def close_position(engine: Engine, signal_date: date, exit_time,
                   exit_value: float, exit_reason: str, raw_return: float) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"""
            UPDATE {CINDER_SIGNALS_TABLE}
            SET status = 'closed', exit_time = :et, exit_value = :ev,
                exit_reason = :reason, raw_return = :ret,
                closed_at = CURRENT_TIMESTAMP
            WHERE signal_date = :d
        """), {"et": exit_time, "ev": exit_value, "reason": exit_reason,
               "ret": raw_return, "d": signal_date})


def record_scan_log(engine: Engine, run_at: datetime, gex_b: float | None,
                    gex_pass: bool | None, vix_ratio: float | None,
                    vix_ratio_pass: bool | None, term_vix: float | None,
                    term_vix3m: float | None, term_pass: bool | None,
                    triggered: bool | None, cooldown_passed: bool | None,
                    block_reason: str | None, entry_opened: bool,
                    exit_closed: bool, errors: int) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {CINDER_SCAN_LOG_TABLE}
                (run_at, gex_b, gex_pass, vix_ratio, vix_ratio_pass, term_vix,
                 term_vix3m, term_pass, triggered, cooldown_ok, block_reason,
                 entry_opened, exit_closed, errors)
            VALUES (:ra, :gb, :gp, :vr, :vp, :tv, :t3, :tp, :tr, :co, :br,
                    :eo, :ec, :er)
        """), {"ra": run_at.replace(tzinfo=None), "gb": gex_b, "gp": gex_pass,
               "vr": vix_ratio, "vp": vix_ratio_pass, "tv": term_vix,
               "t3": term_vix3m, "tp": term_pass, "tr": triggered,
               "co": cooldown_passed, "br": block_reason, "eo": entry_opened,
               "ec": exit_closed, "er": errors})


# ---- Live VIX / VIX3M leg (sw_live_vol_indices) ----------------------------

def fetch_vol_reading(engine: Engine, symbol: str) -> dict | None:
    """Latest `sw_live_vol_indices` row for `symbol`, or None if the symbol
    has never been captured. Table/columns are `market_structure.py`'s own
    (`persist_vol`/`fetch_vol_indices`, VOL_TABLE = "sw_live_vol_indices"):
    symbol, captured_at, price, source, source_timestamp, age_seconds,
    fresh, reason. Never raises -- a query failure reads as "no row",
    which the term-structure/VIX-ratio checks already treat as UNKNOWN."""
    try:
        with engine.begin() as conn:
            row = conn.execute(text(
                "SELECT price, captured_at, fresh FROM sw_live_vol_indices "
                "WHERE symbol = :s ORDER BY captured_at DESC LIMIT 1"
            ), {"s": symbol}).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("[CINDER] fetch_vol_reading(%s) failed: %r", symbol, e)
        return None
    if row is None or row[0] is None:
        return None
    return {"symbol": symbol, "price": float(row[0]),
            "captured_at": _as_datetime(row[1]), "fresh": bool(row[2])}


def vol_reading_is_usable(reading: dict | None, now_utc: datetime,
                          max_age_minutes: int = VOL_READING_STALE_MINUTES) -> bool:
    """Pure: a row counts as usable only if it exists, was fresh when
    captured, AND the capture itself is recent against `now_utc` -- a job
    that stopped running hours ago must not silently keep passing this gate
    off its last good row."""
    if reading is None or reading.get("captured_at") is None:
        return False
    if not reading.get("fresh"):
        return False
    captured_at = reading["captured_at"]
    if captured_at.tzinfo is not None:
        captured_at = captured_at.astimezone(tz=None).replace(tzinfo=None)
    age_min = (now_utc.replace(tzinfo=None) - captured_at).total_seconds() / 60.0
    return 0 <= age_min <= max_age_minutes


def term_structure_leg(vix_reading: dict | None, vix3m_reading: dict | None,
                       now_utc: datetime) -> dict:
    """Pure: VIX - VIX3M < 0 (normal contango) from two already-fetched
    `sw_live_vol_indices` readings. Either reading missing or stale ->
    `pass` is None (UNKNOWN/BLOCK), never a silent pass -- same "missing
    history blocks, it does not read as neutral" doctrine
    `gamma_regime.gamma_state` already applies to its own leg.
    """
    vix_ok = vol_reading_is_usable(vix_reading, now_utc)
    vix3m_ok = vol_reading_is_usable(vix3m_reading, now_utc)
    if not vix_ok or not vix3m_ok:
        missing = []
        if not vix_ok:
            missing.append("VIX")
        if not vix3m_ok:
            missing.append("VIX3M")
        return {"vix": vix_reading.get("price") if vix_reading else None,
                "vix3m": vix3m_reading.get("price") if vix3m_reading else None,
                "term": None, "pass": None,
                "reason": f"{'/'.join(missing)} reading missing or stale in "
                          "sw_live_vol_indices"}
    vix = vix_reading["price"]
    vix3m = vix3m_reading["price"]
    term = vix - vix3m
    return {"vix": vix, "vix3m": vix3m, "term": term, "pass": bool(term < 0),
            "reason": None}


def vix_ratio_leg(vix_reading: dict | None, now_utc: datetime) -> dict:
    """Pure-ish: routes_squeeze.live_vix_ratio() does its own DB read
    (the trailing-20-session max), so this still touches the DB once, but
    the decision logic itself -- is the ratio below VIX_RATIO_TRIGGER -- is
    a one-line comparison. A missing/stale live VIX reading blocks rather
    than silently passing, same as every other leg here."""
    if not vol_reading_is_usable(vix_reading, now_utc):
        return {"vix_now": vix_reading.get("price") if vix_reading else None,
                "ratio": None, "pass": None,
                "reason": "VIX reading missing or stale in sw_live_vol_indices"}
    vix_now = vix_reading["price"]
    from .routes_squeeze import live_vix_ratio
    ratio = live_vix_ratio(vix_now)
    if ratio is None:
        return {"vix_now": vix_now, "ratio": None, "pass": None,
                "reason": "insufficient trailing VIX history for live_vix_ratio"}
    return {"vix_now": vix_now, "ratio": ratio,
            "pass": bool(ratio < VIX_RATIO_TRIGGER), "reason": None}


def gex_leg(engine: Engine, asof: date) -> dict:
    """Prior-session net_gex_b via gamma_regime.gamma_state -- reused, not
    reimplemented. None means BLOCK (gamma_state's own "unknown is not
    safe" doctrine), never a silent pass."""
    from .bots.gamma_regime import gamma_state
    st = gamma_state(engine, asof)
    b = st.get("net_gex_b")
    passed = None if b is None else bool(b <= GEX_TRIGGER_B)
    return {"net_gex_b": b, "pass": passed, "prior_date": st.get("prior_date"),
            "reason": st.get("reason")}


def evaluate_entry_trigger(engine: Engine, asof: date, now_utc: datetime) -> dict:
    """All three legs, combined. `triggered` is True only if every leg
    actually passed; it is None (BLOCKED, not NEUTRAL) the moment any leg
    is unknown, and False if every leg resolved but at least one failed."""
    gex = gex_leg(engine, asof)
    vix_reading = fetch_vol_reading(engine, "VIX")
    vix3m_reading = fetch_vol_reading(engine, "VIX3M")
    vratio = vix_ratio_leg(vix_reading, now_utc)
    term = term_structure_leg(vix_reading, vix3m_reading, now_utc)

    legs = (gex["pass"], vratio["pass"], term["pass"])
    if any(p is None for p in legs):
        triggered = None
        reasons = [l["reason"] for l, p in
                   zip((gex, vratio, term), legs) if p is None and l["reason"]]
        reason = "; ".join(reasons) or "a leg is unknown"
    else:
        triggered = all(legs)
        reason = None if triggered else "not every leg passed"

    return {"triggered": triggered, "reason": reason, "gex": gex,
            "vix_ratio": vratio, "term_structure": term}


# ---- Entry: live chain pull + strike selection -----------------------------

def fetch_entry_chain(today: date) -> dict | None:
    """One live SPY 1DTE chain pull -- same chain-access pattern
    `gamma_regime.fetch_net_gex`/`trade_ticket` already use. Returns the
    provider's `get_chain()` payload (spot, options, expiration) or None on
    any failure."""
    from .bots.routes_helpers import build_live_chain_provider
    try:
        return build_live_chain_provider().get_chain(ticker=SPY_TICKER, dte=1,
                                                      today=today)
    except Exception as e:  # noqa: BLE001
        logger.warning("[CINDER] fetch_entry_chain failed: %r", e)
        return None


def _calls_by_strike(options: list[dict]) -> dict[float, dict]:
    out: dict[float, dict] = {}
    for o in options or []:
        if str(o.get("type") or "").lower() != "call":
            continue
        try:
            strike = float(o["strike"])
        except (KeyError, TypeError, ValueError):
            continue
        out[strike] = o
    return out


def select_entry_strikes(chain: dict | None,
                         width: float = STRIKE_WIDTH) -> dict:
    """Pure: given a `get_chain()`-shaped payload, pick the ATM long call
    (nearest strike to spot) and the short call `width` higher, and read
    both legs' live bid/ask straight from the chain's own options list.
    Entry debit is ask(long) - bid(short) -- the real NBBO fill convention,
    legged separately because the live execution bot cannot place a true
    multi-leg combo (Robinhood's agentic API rejects them).

    Returns {"long_strike", "short_strike", "long_ask", "short_bid",
    "entry_debit", "spot", "expiration", "reason"}. `reason` is set (and
    every price field is None) on any failure -- missing chain, no spot, no
    exact strike `width` higher, or a non-positive quote on either leg --
    so the caller retries next tick inside the entry window rather than
    recording a fabricated ticket.
    """
    out = {"long_strike": None, "short_strike": None, "long_ask": None,
           "short_bid": None, "entry_debit": None, "spot": None,
           "expiration": None, "reason": None}
    if not chain or not chain.get("options") or not chain.get("spot"):
        out["reason"] = "no live chain available"
        return out

    spot = float(chain["spot"])
    calls = _calls_by_strike(chain["options"])
    if not calls:
        out["reason"] = "no call strikes in the live chain"
        return out

    long_strike = min(calls, key=lambda s: abs(s - spot))
    short_strike = long_strike + width
    if short_strike not in calls:
        out["reason"] = (f"no ${width:.0f}-wide short strike ({short_strike}) "
                         "available in the live chain")
        return out

    long_leg, short_leg = calls[long_strike], calls[short_strike]
    long_ask = float(long_leg.get("ask") or 0)
    short_bid = float(short_leg.get("bid") or 0)
    if long_ask <= 0 or short_bid < 0:
        out["reason"] = "no usable live ask/bid on one or both legs yet"
        return out

    out.update({
        "long_strike": long_strike, "short_strike": short_strike,
        "long_ask": long_ask, "short_bid": short_bid,
        "entry_debit": round(long_ask - short_bid, 4), "spot": spot,
        "expiration": _as_date(chain.get("expiration")), "reason": None,
    })
    return out


# ---- Exit: live chain pull + spread value ----------------------------------

def fetch_exit_chain(expiration: date, today: date) -> dict | None:
    """The same expiration's chain, read from `today`'s perspective -- dte
    is however many calendar days remain until `expiration` (0 on the
    expiration day itself, 1 the day before). Same provider/pattern as
    `fetch_entry_chain`. Returns None on any failure."""
    from .bots.routes_helpers import build_live_chain_provider
    dte = max((expiration - today).days, 0)
    try:
        return build_live_chain_provider().get_chain(ticker=SPY_TICKER, dte=dte,
                                                      today=today)
    except Exception as e:  # noqa: BLE001
        logger.warning("[CINDER] fetch_exit_chain failed: %r", e)
        return None


def spread_value_from_chain(chain: dict | None, long_strike: float,
                            short_strike: float,
                            expected_expiration: date | None = None) -> dict:
    """Pure: spread value = long_bid - short_ask (the real closing fill on
    each leg: sell the long call at its bid, buy back the short call at its
    ask). Returns {"value", "long_bid", "short_ask", "reason"}; `reason` is
    set and `value` is None on a missing chain, a missing strike, a
    non-positive quote on either leg, or an expiration that no longer
    matches the one this position was opened against (the chain drifted to
    a different expiry, which must not be silently priced as this one)."""
    out = {"value": None, "long_bid": None, "short_ask": None, "reason": None}
    if not chain or not chain.get("options"):
        out["reason"] = "no live chain available"
        return out
    if expected_expiration is not None:
        chain_exp = _as_date(chain.get("expiration"))
        if chain_exp != expected_expiration:
            out["reason"] = (f"live chain expiration {chain_exp} does not match "
                             f"this position's {expected_expiration}")
            return out

    calls = _calls_by_strike(chain["options"])
    long_leg, short_leg = calls.get(long_strike), calls.get(short_strike)
    if long_leg is None or short_leg is None:
        out["reason"] = "one or both strikes missing from the live chain"
        return out

    long_bid = float(long_leg.get("bid") or 0)
    short_ask = float(short_leg.get("ask") or 0)
    if long_bid < 0 or short_ask <= 0:
        out["reason"] = "no usable live bid/ask on one or both legs yet"
        return out

    out.update({"value": round(long_bid - short_ask, 4), "long_bid": long_bid,
               "short_ask": short_ask, "reason": None})
    return out


def check_exit(engine: Engine, open_row: dict, today: date, now_et: datetime):
    """Returns (status, payload):
      'pending' - spread value updated (or left alone on a quote miss), the
          position stays open.
      'closed'  - the target fired or the expiration-day EOD fallback
          window resolved it (payload carries exit_time, exit_value,
          exit_reason, raw_return).
    """
    chain = fetch_exit_chain(open_row["expiration"], today)
    sv = spread_value_from_chain(chain, open_row["long_strike"],
                                 open_row["short_strike"], open_row["expiration"])

    target = open_row["entry_debit"] * TARGET_MULTIPLE
    target_hit = sv["value"] is not None and sv["value"] >= target
    if sv["value"] is not None:
        update_open_position(engine, open_row["signal_date"], sv["value"],
                             target_hit, now_et.replace(tzinfo=None))

    if target_hit:
        raw_return = sv["value"] / open_row["entry_debit"] - 1
        return "closed", dict(exit_time=now_et.replace(tzinfo=None),
                              exit_value=sv["value"], exit_reason="target_2x",
                              raw_return=raw_return)

    is_expiration_day = today == open_row["expiration"]
    in_eod_window = EOD_FALLBACK_START_T <= now_et.time() <= EOD_FALLBACK_END_T
    if is_expiration_day and in_eod_window and sv["value"] is not None:
        raw_return = sv["value"] / open_row["entry_debit"] - 1
        return "closed", dict(exit_time=now_et.replace(tzinfo=None),
                              exit_value=sv["value"], exit_reason="eod_fallback",
                              raw_return=raw_return)

    if sv["reason"]:
        logger.info("[CINDER] exit check for %s: %s -- retrying next scan",
                   open_row["signal_date"], sv["reason"])
    return "pending", None


# ---- Full scan --------------------------------------------------------------

def run_cinder_scan(engine: Engine, now_et: datetime) -> dict:
    """The full blocking scan: self-gated to the 09:30-16:00 ET regular
    session. Checks/updates an open position's exit state every tick;
    attempts a new entry only inside the 11:25-11:35 ET window, only with no
    position already open, and only once the cooldown and all three trigger
    legs pass. Run inside `asyncio.to_thread` by the scheduled job, same
    convention as `squeeze_reactive_alerts.run_reactive_scan`.
    """
    ensure_cinder_tables(engine)
    today = now_et.date()
    now_utc = now_et.astimezone(ZoneInfo("UTC"))

    if not (SESSION_START_T <= now_et.time() <= SESSION_END_T):
        return {"reason": "outside the 09:30:00-16:00:00 ET regular session",
                "entries_opened": [], "exits_closed": []}

    entries_opened: list[dict] = []
    exits_closed: list[dict] = []
    errors = 0
    trig: dict = {"triggered": None, "reason": None,
                  "gex": {}, "vix_ratio": {}, "term_structure": {}}
    cooldown_passed: bool | None = None
    block_reason: str | None = None

    open_row = load_open_position(engine)
    if open_row is not None:
        try:
            status, payload = check_exit(engine, open_row, today, now_et)
        except Exception as e:  # noqa: BLE001
            logger.warning("[CINDER] check_exit failed: %r", e)
            status, payload = "error", None
            errors += 1
        if status == "closed":
            close_position(engine, open_row["signal_date"], **payload)
            exits_closed.append({"signal_date": open_row["signal_date"],
                                 "entry_debit": open_row["entry_debit"],
                                 "long_strike": open_row["long_strike"],
                                 "short_strike": open_row["short_strike"],
                                 **payload})
    else:
        in_entry_window = ENTRY_WINDOW_START_T <= now_et.time() <= ENTRY_WINDOW_END_T
        if in_entry_window:
            last_date = last_entry_date(engine)
            cooldown_passed = cooldown_ok(last_date, today)
            if not cooldown_passed:
                block_reason = (f"cooldown active -- last entry {last_date}, "
                               f"{COOLDOWN_DAYS}-calendar-day minimum")
            else:
                try:
                    trig = evaluate_entry_trigger(engine, today, now_utc)
                except Exception as e:  # noqa: BLE001
                    logger.warning("[CINDER] evaluate_entry_trigger failed: %r", e)
                    trig = {"triggered": None, "reason": f"trigger error: {e}",
                           "gex": {}, "vix_ratio": {}, "term_structure": {}}
                    errors += 1
                if trig["triggered"] is True:
                    chain = fetch_entry_chain(today)
                    entry = select_entry_strikes(chain)
                    if entry["reason"]:
                        block_reason = entry["reason"]
                        logger.info("[CINDER] entry trigger fired but %s -- "
                                   "retrying next scan", entry["reason"])
                    else:
                        open_position(engine, today, now_et.replace(tzinfo=None),
                                     entry["spot"], entry["long_strike"],
                                     entry["short_strike"], entry["expiration"],
                                     entry["entry_debit"])
                        entries_opened.append({"signal_date": today, **entry})
                else:
                    block_reason = trig["reason"]

    try:
        record_scan_log(
            engine, now_et, trig["gex"].get("net_gex_b"), trig["gex"].get("pass"),
            trig["vix_ratio"].get("ratio"), trig["vix_ratio"].get("pass"),
            trig["term_structure"].get("vix"), trig["term_structure"].get("vix3m"),
            trig["term_structure"].get("pass"), trig.get("triggered"),
            cooldown_passed, block_reason, bool(entries_opened),
            bool(exits_closed), errors)
    except Exception as e:  # noqa: BLE001
        logger.warning("[CINDER] record_scan_log failed: %r", e)

    return {"reason": None, "triggered": trig.get("triggered"),
            "block_reason": block_reason, "cooldown_ok": cooldown_passed,
            "errors": errors, "entries_opened": entries_opened,
            "exits_closed": exits_closed}


# ---- Discord alert copy -----------------------------------------------------

def _build_entry_alert(hit: dict) -> str:
    return (
        f"**CINDER** ENTRY — SPY 1DTE debit call spread\n"
        f"Long ${hit['long_strike']:.0f}C / Short ${hit['short_strike']:.0f}C, "
        f"exp {hit['expiration']}\n"
        f"Debit: ${hit['entry_debit']:.2f} (spot ${hit['spot']:.2f})\n"
        "_signal-only, advisory only -- a separate local execution bot reads "
        "this to place the real legs_"
    )


def _build_exit_alert(hit: dict) -> str:
    ret_pct = hit["raw_return"] * 100
    reason_label = {"target_2x": "2.0x target hit",
                    "eod_fallback": "EOD fallback (expiration day)"}.get(
        hit["exit_reason"], hit["exit_reason"])
    arrow = "\U0001f7e2" if ret_pct >= 0 else "\U0001f534"
    return (
        f"**CINDER** EXIT — {reason_label}\n"
        f"Spread value ${hit['exit_value']:.2f} (entry debit "
        f"${hit['entry_debit']:.2f})\n"
        f"{arrow} realized: {ret_pct:+.1f}%\n"
        "_signal-only, advisory only_"
    )


def register_cinder_alerts(scheduler, app) -> None:
    """Attach the CINDER scan job to the existing APScheduler.

    Same wiring as `squeeze_reactive_alerts.register_squeeze_reactive_alerts`:
    a wide 08:00-15:55 CT cron window (`run_cinder_scan` self-gates on the
    real 09:30-16:00 ET regular session), `max_instances=1, coalesce=True`.
    """
    from .db import engine
    from . import _send_webhook_sync

    if scheduler is None:
        logger.warning("[CINDER] no scheduler — CINDER scan job disabled")
        return

    try:
        ensure_cinder_tables(engine)
    except Exception as e:  # noqa: BLE001
        logger.warning("[CINDER] ensure_cinder_tables failed: %r", e)

    def _webhook_url() -> str:
        return (os.getenv(CINDER_DISCORD_WEBHOOK_ENV, "").strip()
                or os.getenv("DISCORD_WEBHOOK_URL", "").strip())

    async def scan_cinder():
        import asyncio
        try:
            now_ct = datetime.now(CT)
            if now_ct.weekday() >= 5:
                return

            now_et = datetime.now(ET)
            summary = await asyncio.to_thread(run_cinder_scan, engine, now_et)

            if summary.get("reason"):
                logger.debug("[CINDER] scan skipped: %s", summary["reason"])
                return

            logger.info(
                "[CINDER] DONE: triggered=%s block_reason=%s cooldown_ok=%s "
                "errors=%d entries=%d exits=%d", summary.get("triggered"),
                summary.get("block_reason"), summary.get("cooldown_ok"),
                summary["errors"], len(summary["entries_opened"]),
                len(summary["exits_closed"]))

            webhook = _webhook_url()
            for hit in summary["entries_opened"]:
                content = _build_entry_alert(hit)
                await asyncio.to_thread(
                    _send_webhook_sync,
                    {"description": content, "color": 0x00E676,
                     "footer": {"text": "CINDER · ENTRY · signal-only, advisory only"}},
                    webhook)
            for hit in summary["exits_closed"]:
                content = _build_exit_alert(hit)
                color = 0x00E676 if hit["raw_return"] >= 0 else 0xFF1744
                await asyncio.to_thread(
                    _send_webhook_sync,
                    {"description": content, "color": color,
                     "footer": {"text": "CINDER · EXIT · signal-only, advisory only"}},
                    webhook)
        except Exception as e:  # noqa: BLE001
            logger.warning("[CINDER] scan_cinder failed: %r", e)

    scheduler.add_job(scan_cinder, "cron", day_of_week="mon-fri",
                      hour="8-15", minute="*/5", timezone=CT, id=CINDER_JOB_ID,
                      coalesce=True, max_instances=1, misfire_grace_time=120,
                      replace_existing=True)

    _SCHEDULER["ref"] = scheduler
    logger.info("[CINDER] registered: every 5 min, 08:00-15:55 CT weekdays "
               "(self-gated to the 09:30-16:00 ET regular session, entry "
               "attempted only in the 11:25-11:35 ET window)")
