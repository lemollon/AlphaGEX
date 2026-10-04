"""Reactive-momentum squeeze signal — LIVE two-leg (entry + exit) scanner.

PORTS the just-validated `REACTIVE_WIDE_FADE_PNL_BACKTEST_MODE` from the
standalone Render Cron Job (`squeeze_premarket_cron/main.py`) into this
always-on backend as a REPEATING intraday scan, following the same wiring
pattern `squeeze_premarket_alerts.py` uses for the (once-daily) premarket
signal: APScheduler job registration via `backend/__init__.py`,
`backend._dedup_ok`-style discipline where it still applies, posted through
`backend._send_webhook_sync`. That backtest mode showed +42.51 units / 3,076
trades / 630 symbols in `squeeze_reactive_wide_fade_pnl`, survives dropping
its single best symbol (+22.46) — see `dev/squeeze/research/PREREG.md` for
the research record. Nothing in this module touches FAMILY #2, PREREG.md,
the gamma-regime squeeze signal, or `squeeze_premarket_alerts.py`'s own
premarket-gated job — this is a NEW, separate live capability sitting
alongside it.

Frozen rule, ported verbatim from the backtest mode (do not change without a
new pre-registration):
  CANDIDATE UNIVERSE: `squeeze_premarket_universe` (SEC shares_outstanding x
      FINRA 20-day median volume population) — the SAME table
      `squeeze_premarket_alerts.py` already scans, reused via its own
      `load_universe()`, NOT recomputed here. NO premarket gate this time —
      every candidate is watched all regular session (09:30:00-16:00:00 ET).
  ENTRY TRIGGER (look-ahead-free, same discipline as the cron's
      `find_reactive_entry_trigger()`): the first regular-session 1-minute
      bar where (1) that bar's own close vs. the REAL prior-session close is
      >= REACTIVE_MOVE_FLOOR (+10%), AND (2) trailing 15-min $/min pace is
      >= MONEY_PACE_ACCEL_HIGH (1.25x) the whole-session-so-far $/min pace.
      Confirmed one minute after the bar's own timestamp (ThetaData's 1m
      bars are timestamped at interval START).
  EXIT TRIGGER: the first LATER bar where that same pace ratio fades to
      <= REACTIVE_WIDE_FADE_ACCEL_LOW (0.4x) — the wide-fade threshold this
      backtest mode proved better than the original 0.6x — or 16:00:00 ET
      if it never fades.
  FILLS: real NBBO ask at entry, real NBBO bid at exit (fade) or the real
      15:55:00-16:00:00 ET NBBO-bid window at EOD. Never a trade price,
      never a mid/mark.
  DEDUPE: 30 calendar days per symbol, same convention as the premarket
      signal.

ARCHITECTURAL DIFFERENCE FROM THE BACKTEST / THE PREMARKET JOB: the
premarket job runs ONCE before the open. This idea needs to run REPEATEDLY
during market hours to catch entries as they happen and to track which
symbols currently have an OPEN alerted position so a follow-up EXIT alert
can fire later. State lives in `squeeze_reactive_signals`
('open'/'closed' per symbol); the scan runs every 5 minutes, 09:30-16:00 ET
weekdays (scheduled via a wider cron window + an internal time-of-day gate,
see `register_squeeze_reactive_alerts()`).

WHY NOT SCAN THE FULL ~7,200-SYMBOL UNIVERSE EVERY 5 MINUTES, LITERALLY:
the private `thetadata_proxy` service fully serializes every call behind
ONE process-wide lock (`CLIENT_LOCK` in `thetadata_proxy/app.py` — the
underlying ThetaData client is a single long-lived connection, not safe for
concurrent use). Client-side thread pools do not add real throughput there;
7,200 individual per-symbol historical pulls, one every 5 minutes, would
either never finish inside its own window or starve every OTHER feature
that shares this proxy (GEX, options chains, market-structure capture).
So entry-candidate scanning is split into two stages:
  STAGE 1 (cheap, every tick): ONE bulk `/v3/stock/snapshot/ohlc` call per
      <=450-symbol batch (the proxy caps a single call at 500 names) across
      the whole universe (~16 batches) — gets each symbol's running
      intraday open/close in a handful of calls instead of thousands.
      Symbols already up >= PREFILTER_MOVE_FLOOR (5%, HALF the real 10%
      floor) from TODAY's OWN OPEN become the stage-2 shortlist.
      KNOWN TRADEOFF: this is a CHEAP PROXY, not the frozen rule — the real
      rule's move is vs. the previous session's close, not today's open.
      A name that gapped up hard at the open and only drifted a little
      further intraday could clear the real >=10%-from-prior-close floor
      while sitting under this >=5%-from-open screen, and would be missed
      until it drifts further. That failure mode is exactly the kind of
      premarket gap event the OTHER (premarket-gated) signal already
      targets; this reactive idea is aimed at momentum that BUILDS during
      the regular session (open near prior close, then runs), which the
      open-vs-now proxy tracks well. Accepted per task spec, which proposed
      this exact mitigation.
  STAGE 2 (real rule, bounded by the stage-1 shortlist + already-open
      positions only): one regular-session 1-minute OHLC pull per candidate
      (reused for the whole pace walk, same as the backtest), the real
      prior-close fetched once per symbol per day and cached in-process,
      and a real NBBO quote pull only for the rare candidate that actually
      fires an entry or exit this tick.

RUNTIME ESTIMATE (model-based — the private Render network cannot be
benchmarked from this dev workstation): stage 1 is ~16 serialized bulk
calls, each covering ~450 symbols; stage 2 is bounded by however many
symbols clear the 5% screen plus however many positions are already open,
typically expected to be a low double-digit to low hundreds count on an
active day, each needing one serialized historical pull. At even a
pessimistic ~1s per serialized call, stage 1 (~16s-60s) + stage 2 (a few
hundred calls, well under 5 minutes) fits the 5-minute cadence comfortably
in the typical case. The tail risk is a market-wide melt-up day where a
large fraction of the 7,200-symbol universe clears the cheap screen at
once, pushing stage 2 toward thousands of calls; `max_instances=1,
coalesce=True` (same convention `market_structure.py`'s per-minute capture
already uses) means an overrunning scan simply causes the next scheduled
tick to be skipped/coalesced rather than stacking — a degraded cadence on
that rare day, never a pile-up of overlapping scans.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dtime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .squeeze_premarket_alerts import (
    DEDUPE_DAYS,
    MONEY_PACE_ACCEL_HIGH,
    MONEY_PACE_RECENT_MINUTES,
    SQUEEZE_DISCORD_WEBHOOK_ENV,
    UNIVERSE_TABLE,
    _fetch_csv,
    _theta_base,
    load_universe,
)

logger = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")

# ---- Frozen rule (ported from REACTIVE_WIDE_FADE_PNL_BACKTEST_MODE) -------
REACTIVE_SESSION_START = "09:30:00"
REACTIVE_SESSION_END = "16:00:00"
REACTIVE_SESSION_START_T = dtime(9, 30, 0)
REACTIVE_SESSION_END_T = dtime(16, 0, 0)
REACTIVE_MOVE_FLOOR = 0.10            # intraday move from the real prior_close
REACTIVE_MIN_SESSION_MINUTES = 5
REACTIVE_QUOTE_WINDOW_SECONDS = 60
REACTIVE_WIDE_FADE_ACCEL_LOW = 0.4     # the proven-better wide-fade threshold

# EOD fallback exit — identical window/convention as the cron's
# fetch_sameday_exit_bid(): the last real NBBO bid strictly before 16:00:00
# ET, searched in the 15:55:00-16:00:00 ET window.
SAMEDAY_EXIT_WINDOW_START = "15:55:00"
SAMEDAY_EXIT_WINDOW_END = "16:00:00"
SAMEDAY_MARKET_CLOSE = dtime(16, 0, 0)

# ---- Stage-1 cheap pre-filter (NOT part of the frozen rule — see module
# docstring "WHY NOT SCAN ... LITERALLY") -----------------------------------
PREFILTER_MOVE_FLOOR = 0.05
SNAPSHOT_BATCH_SIZE = 450   # proxy hard-caps a single call at 500 symbols

# ---- Infra config ----------------------------------------------------------
MAX_WORKERS = 10            # the proxy serializes every call anyway (see
                            # module docstring) — this just lets stage-2
                            # workers overlap their own request-building
                            # overhead, not a throughput promise.
EOD_LOOKBACK_DAYS = 10       # calendar days back to find the last session close

_SCHEDULER: dict = {"ref": None}
REACTIVE_JOB_ID = "squeeze_reactive_scan"

SIGNALS_TABLE = "squeeze_reactive_signals"
SCAN_LOG_TABLE = "squeeze_reactive_scan_log"

# Per-process, per-(symbol, date) cache — real prior_close is deterministic
# once the previous session has closed, so a cache miss just costs one extra
# EOD call; a redeploy mid-day simply re-warms it for symbols touched after
# the restart. See module docstring for why this isn't a DB table.
_PRIOR_CLOSE_CACHE: dict[tuple[str, date], float] = {}


def ensure_tables(engine: Engine) -> None:
    """CREATE TABLE IF NOT EXISTS for this module's two tables. Natural
    (symbol, signal_date) primary key on the signals table — not a surrogate
    serial id — because the 30-day dedupe already guarantees at most one
    entry per symbol per day, and it keeps the DDL portable across Postgres
    (production) and SQLite (tests), same reasoning
    squeeze_premarket_alerts.py's SIGNALS_TABLE already applies."""
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {SIGNALS_TABLE} (
                symbol TEXT NOT NULL,
                signal_date DATE NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                entry_bar_time TIMESTAMP,
                entry_time TIMESTAMP,
                entry_ask DOUBLE PRECISION,
                entry_move DOUBLE PRECISION,
                prior_close DOUBLE PRECISION,
                exit_time TIMESTAMP,
                exit_bid DOUBLE PRECISION,
                exit_reason TEXT,
                raw_return DOUBLE PRECISION,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                PRIMARY KEY (symbol, signal_date)
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {SCAN_LOG_TABLE} (
                run_at TIMESTAMP NOT NULL PRIMARY KEY,
                universe_size INTEGER,
                prefilter_candidates INTEGER,
                prefilter_shortlist INTEGER,
                snapshot_batches INTEGER,
                snapshot_errors INTEGER,
                open_checked INTEGER,
                errors INTEGER,
                entries_opened INTEGER,
                exits_closed INTEGER,
                open_after INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))


def scheduled_jobs() -> dict:
    """Same "never run" disambiguation as squeeze_premarket_alerts'
    scheduled_jobs() — never raises."""
    sched = _SCHEDULER.get("ref")
    if sched is None:
        return {"registered": False, "jobs": {},
                "reason": "Reactive squeeze job is not armed — no scheduler was attached."}
    out: dict = {"registered": True, "jobs": {}, "reason": None}
    try:
        job = sched.get_job(REACTIVE_JOB_ID)
        nxt = getattr(job, "next_run_time", None) if job else None
        out["jobs"][REACTIVE_JOB_ID] = nxt.isoformat() if nxt else None
    except Exception as e:  # noqa: BLE001
        out["jobs"][REACTIVE_JOB_ID] = None
        out["reason"] = f"job lookup failed: {e}"
    return out


# ---- Dedupe / state -------------------------------------------------------

def already_signaled_recently(engine: Engine, symbol: str, today: date) -> bool:
    """30 calendar-day dedupe per symbol — identical convention to
    squeeze_premarket_alerts.already_signaled_recently()."""
    cutoff = today - timedelta(days=DEDUPE_DAYS)
    with engine.begin() as conn:
        row = conn.execute(text(f"""
            SELECT count(*) FROM {SIGNALS_TABLE}
            WHERE symbol = :sym AND signal_date >= :cutoff
        """), {"sym": symbol, "cutoff": cutoff}).fetchone()
    return bool(row and row[0] > 0)


def _as_datetime(value):
    """Postgres' driver hands TIMESTAMP columns back as native datetimes;
    SQLite (used by this module's tests) hands raw SQL queries back the
    stored string instead. Normalize so every caller downstream (the bar-
    index comparison in check_exit_position(), the alert copy's
    .strftime() calls) always sees a real datetime regardless of engine."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def load_open_positions(engine: Engine) -> dict[str, dict]:
    """symbol -> state for every currently-open reactive position,
    regardless of signal_date — a position that failed to resolve by EOD
    (e.g. the 15:55-16:00 ET NBBO pull came up empty) stays 'open' and keeps
    being checked on subsequent days until it resolves, rather than being
    silently dropped."""
    with engine.begin() as conn:
        rows = conn.execute(text(f"""
            SELECT symbol, signal_date, entry_bar_time, entry_time, entry_ask,
                   entry_move, prior_close
            FROM {SIGNALS_TABLE} WHERE status = 'open'
        """)).fetchall()
    out = {}
    for r in rows:
        out[r[0]] = {
            "symbol": r[0], "signal_date": r[1], "entry_bar_time": _as_datetime(r[2]),
            "entry_time": _as_datetime(r[3]), "entry_ask": r[4], "entry_move": r[5],
            "prior_close": r[6],
        }
    return out


def open_position(engine: Engine, symbol: str, today: date, entry_bar_time,
                   entry_time, entry_ask: float, entry_move: float,
                   prior_close: float) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {SIGNALS_TABLE}
                (symbol, signal_date, status, entry_bar_time, entry_time,
                 entry_ask, entry_move, prior_close)
            VALUES (:sym, :d, 'open', :ebt, :et, :ask, :mv, :pc)
        """), {"sym": symbol, "d": today, "ebt": entry_bar_time, "et": entry_time,
               "ask": entry_ask, "mv": entry_move, "pc": prior_close})


def close_position(engine: Engine, symbol: str, signal_date: date, exit_time,
                    exit_bid: float, exit_reason: str, raw_return: float) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"""
            UPDATE {SIGNALS_TABLE}
            SET status = 'closed', exit_time = :et, exit_bid = :bid,
                exit_reason = :reason, raw_return = :ret,
                closed_at = CURRENT_TIMESTAMP
            WHERE symbol = :sym AND signal_date = :d
        """), {"et": exit_time, "bid": exit_bid, "reason": exit_reason,
               "ret": raw_return, "sym": symbol, "d": signal_date})


def record_scan_log(engine: Engine, run_at: datetime, universe_size: int,
                     prefilter_candidates: int, prefilter_shortlist: int,
                     snapshot_batches: int, snapshot_errors: int,
                     open_checked: int, errors: int, entries_opened: int,
                     exits_closed: int, open_after: int) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {SCAN_LOG_TABLE}
                (run_at, universe_size, prefilter_candidates, prefilter_shortlist,
                 snapshot_batches, snapshot_errors, open_checked, errors,
                 entries_opened, exits_closed, open_after)
            VALUES (:ra, :u, :pc, :ps, :sb, :se, :oc, :e, :eo, :ec, :oa)
        """), {"ra": run_at.replace(tzinfo=None), "u": universe_size,
               "pc": prefilter_candidates, "ps": prefilter_shortlist,
               "sb": snapshot_batches, "se": snapshot_errors, "oc": open_checked,
               "e": errors, "eo": entries_opened, "ec": exits_closed, "oa": open_after})


# ---- Real prior_close (per symbol per day, cached) ------------------------

def fetch_prior_close(symbol: str, today: date):
    """Real previous-session close via `/v3/stock/history/eod` — same
    endpoint + row-shape discipline as the cron's
    fetch_tenth_session_close()/backend/ember/legacy/spike.py's
    _load_theta_history() against this same endpoint: the session date
    lives in 'last_trade' (falling back to 'created'), never a 'date'
    column, and rows are not guaranteed to arrive in chronological order.
    Looks back EOD_LOOKBACK_DAYS calendar days and takes the most recent
    session strictly before `today`. Returns (prior_close, reason)."""
    start = today - timedelta(days=EOD_LOOKBACK_DAYS)
    end = today - timedelta(days=1)
    url = f"{_theta_base()}/v3/stock/history/eod"
    params = {"symbol": symbol, "start_date": start.isoformat(), "end_date": end.isoformat()}
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, f"proxy error fetching EOD closes: {detail}"
    if status == "no_data" or not rows:
        return None, f"no EOD data in the {EOD_LOOKBACK_DAYS}-calendar-day lookback window"

    sessions = []
    for row in rows:
        raw_ts = row.get("last_trade") or row.get("created") or ""
        try:
            session_date = date.fromisoformat(str(raw_ts)[:10])
            close = float(row["close"])
        except (KeyError, ValueError, TypeError):
            continue
        if close > 0:
            sessions.append((session_date, close))
    if not sessions:
        return None, "no usable close in the lookback window"
    sessions.sort(key=lambda pair: pair[0])
    return sessions[-1][1], None


def get_cached_prior_close(symbol: str, today: date):
    key = (symbol, today)
    if key in _PRIOR_CLOSE_CACHE:
        return _PRIOR_CLOSE_CACHE[key], None
    price, reason = fetch_prior_close(symbol, today)
    if price is not None:
        _PRIOR_CLOSE_CACHE[key] = price
    return price, reason


# ---- Stage 1: cheap bulk pre-filter ---------------------------------------

def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def prefilter_candidates(symbols: list[str]):
    """Cheap stage-1 screen over `symbols` — see module docstring "WHY NOT
    SCAN ... LITERALLY". Returns (shortlist: set[str], batches: int,
    errors: int)."""
    shortlist: set[str] = set()
    batches = 0
    errors = 0
    for batch in _chunks(symbols, SNAPSHOT_BATCH_SIZE):
        batches += 1
        url = f"{_theta_base()}/v3/stock/snapshot/ohlc"
        params = {"symbol": ",".join(batch), "venue": "utp_cta"}
        rows, status, detail = _fetch_csv(url, params)
        if status == "error":
            errors += 1
            logger.warning("[SqueezeReactive] snapshot batch failed (%d symbols): %s",
                           len(batch), detail)
            continue
        if status == "no_data" or not rows:
            continue
        for row in rows:
            try:
                sym = str(row["symbol"]).strip().upper()
                open_px = float(row["open"])
                close_px = float(row["close"])
            except (KeyError, ValueError, TypeError):
                continue
            if open_px > 0 and (close_px / open_px - 1) >= PREFILTER_MOVE_FLOOR:
                shortlist.add(sym)
    return shortlist, batches, errors


# ---- Stage 2: the frozen rule, ported verbatim from the backtest mode ----

def fetch_reactive_session_bars(symbol: str, event_date: date, end_time: str):
    """ONE regular-session 1-minute OHLC pull, (timestamp, close, volume)
    tuples sorted chronologically — line-for-line the same shape as the
    cron's fetch_reactive_session_bars(), parametrized by `end_time` instead
    of a fixed 16:00:00 so a live call only ever asks for bars that have
    already printed ("now", not the full session)."""
    url = f"{_theta_base()}/v3/stock/history/ohlc"
    params = {
        "symbol": symbol, "date": event_date.isoformat(),
        "start_time": REACTIVE_SESSION_START, "end_time": end_time,
        "interval": "1m", "venue": "utp_cta",
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return "error", None, detail
    if status == "no_data" or not rows:
        return "no_data", None, None

    bars = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            close = float(row["close"])
            vol = int(float(row["volume"]))
        except (KeyError, ValueError, TypeError):
            continue
        if close and close > 0:
            bars.append((ts, close, vol))
    if not bars:
        return "no_data", None, None
    bars.sort(key=lambda bar: bar[0])
    return "ok", bars, None


def _reactive_pace_series(bars: list):
    """Line-for-line the same sliding-window walk as the cron's
    _reactive_pace_series() — see that function's docstring for the full
    reasoning. Yields (index, timestamp, close, accel)."""
    if not bars:
        return
    session_open = bars[0][0].replace(hour=9, minute=30, second=0, microsecond=0)
    cum_dollar_vol = 0.0
    recent_dollar_vol = 0.0
    lo = 0
    for i, (ts, close, vol) in enumerate(bars):
        dv = close * vol
        cum_dollar_vol += dv
        recent_dollar_vol += dv
        window_start = ts - timedelta(minutes=MONEY_PACE_RECENT_MINUTES)
        while lo < i and bars[lo][0] <= window_start:
            recent_dollar_vol -= bars[lo][1] * bars[lo][2]
            lo += 1

        elapsed_minutes = (ts - session_open).total_seconds() / 60.0 + 1.0
        if elapsed_minutes < REACTIVE_MIN_SESSION_MINUTES or cum_dollar_vol <= 0:
            yield i, ts, close, None
            continue

        rate_before = cum_dollar_vol / elapsed_minutes
        if rate_before <= 0:
            yield i, ts, close, None
            continue

        window_lo_ts = bars[lo][0] if lo <= i else ts
        recent_minutes = max((ts - window_lo_ts).total_seconds() / 60.0 + 1.0, 1.0)
        rate_now = recent_dollar_vol / recent_minutes
        yield i, ts, close, rate_now / rate_before


def find_reactive_entry_trigger(bars: list, prior_close):
    """Line-for-line the same look-ahead-free walk as the cron's
    find_reactive_entry_trigger(). Returns (index, confirm_time) or
    (None, None)."""
    if not bars or not prior_close or prior_close <= 0:
        return None, None
    for i, ts, close, accel in _reactive_pace_series(bars):
        if accel is None:
            continue
        move = close / prior_close - 1
        if move >= REACTIVE_MOVE_FLOOR and accel >= MONEY_PACE_ACCEL_HIGH:
            return i, ts + timedelta(minutes=1)
    return None, None


def find_reactive_wide_fade_exit(bars: list, entry_index: int):
    """Line-for-line the same walk as the cron's
    find_reactive_wide_fade_exit() — ONLY the fade threshold differs from
    the original (0.6x): accel <= REACTIVE_WIDE_FADE_ACCEL_LOW (0.4x), the
    threshold this backtest mode proved better."""
    for i, ts, close, accel in _reactive_pace_series(bars):
        if i <= entry_index:
            continue
        if accel is not None and accel <= REACTIVE_WIDE_FADE_ACCEL_LOW:
            return i, ts + timedelta(minutes=1)
    return None, None


def fetch_reactive_quote(symbol: str, event_date: date, confirm_time: datetime, side: str):
    """First usable real NBBO `side` ('ask' or 'bid') timestamped at/after
    `confirm_time`, searched in a REACTIVE_QUOTE_WINDOW_SECONDS window —
    line-for-line the same as the cron's fetch_reactive_quote(). Returns
    (price, quote_time, reason); never a trade price, never a mid/mark."""
    window_end = confirm_time + timedelta(seconds=REACTIVE_QUOTE_WINDOW_SECONDS)
    url = f"{_theta_base()}/v3/stock/history/quote"
    params = {
        "symbol": symbol, "date": event_date.isoformat(),
        "start_time": confirm_time.strftime("%H:%M:%S"),
        "end_time": window_end.strftime("%H:%M:%S"),
        "interval": "1s", "venue": "utp_cta",
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, f"proxy error fetching NBBO quote: {detail}"
    if status == "no_data" or not rows:
        return None, None, (
            f"no NBBO quote data for the {confirm_time.strftime('%H:%M:%S')}-"
            f"{window_end.strftime('%H:%M:%S')} ET window"
        )

    confirm_t = confirm_time.time()
    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            price = float(row[side])
        except (KeyError, ValueError, TypeError):
            continue
        if ts.time() < confirm_t:
            continue
        if price and price > 0:
            return price, ts, None
    return None, None, (
        f"no quote with a usable {side} at/after {confirm_t} within the "
        f"{REACTIVE_QUOTE_WINDOW_SECONDS}s window"
    )


def fetch_sameday_exit_bid(symbol: str, event_date: date):
    """The last real NBBO bid strictly before 16:00:00 ET, searched in the
    15:55:00-16:00:00 ET window — line-for-line the same as the cron's
    fetch_sameday_exit_bid(). Returns (bid, quote_time, reason)."""
    url = f"{_theta_base()}/v3/stock/history/quote"
    params = {
        "symbol": symbol, "date": event_date.isoformat(),
        "start_time": SAMEDAY_EXIT_WINDOW_START, "end_time": SAMEDAY_EXIT_WINDOW_END,
        "interval": "1s", "venue": "utp_cta",
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, f"proxy error fetching NBBO quote: {detail}"
    if status == "no_data" or not rows:
        return None, None, "no NBBO quote data for the 15:55:00-16:00:00 ET window"

    parsed = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            bid = float(row["bid"])
        except (KeyError, ValueError, TypeError):
            continue
        if ts.time() >= SAMEDAY_MARKET_CLOSE:
            continue
        if bid and bid > 0:
            parsed.append((ts, bid))

    if not parsed:
        return None, None, (
            "no quote with a usable bid strictly before 16:00:00 ET within "
            "the 15:55:00-16:00:00 ET window"
        )
    parsed.sort(key=lambda pair: pair[0])
    exit_time, exit_bid = parsed[-1]
    return exit_bid, exit_time, None


# ---- Stage-2 workers (pure HTTP, no DB access) -----------------------------

def check_entry_candidate(symbol: str, today: date, now_et: datetime):
    """Returns (status, payload):
      'no_prior_close' - no real previous-session close surfaced (payload
          carries the reason). Retried next scan.
      'error'          - the bars pull failed after retries.
      'no_entry'       - no usable regular-session bars yet, or the walk
          never found a qualifying trigger minute (as of `now_et`).
      'too_early'      - a trigger fired on the LAST bar of a still-forming
          minute; the NBBO confirm window would reach into the future.
          Retried next scan, never a permanent miss.
      'no_entry_quote' - a trigger minute fired but no usable NBBO ask has
          surfaced yet. Retried next scan (live mode has no terminal
          failure state for this leg — unlike the backtest, which must
          record one for auditability against a fixed historical day).
      'entry'          - entry resolved (payload carries entry_bar_time,
          entry_time, entry_ask, entry_move, prior_close).
    """
    prior_close, reason = get_cached_prior_close(symbol, today)
    if prior_close is None:
        return "no_prior_close", {"reason": reason}

    bars_status, bars, detail = fetch_reactive_session_bars(
        symbol, today, now_et.strftime("%H:%M:%S"))
    if bars_status == "error":
        return "error", detail
    if bars_status == "no_data":
        return "no_entry", None

    entry_index, entry_confirm_time = find_reactive_entry_trigger(bars, prior_close)
    if entry_index is None:
        return "no_entry", None

    if entry_confirm_time.time() >= now_et.time():
        return "too_early", None

    entry_ask, entry_quote_time, entry_reason = fetch_reactive_quote(
        symbol, today, entry_confirm_time, "ask")
    if entry_ask is None:
        logger.info("[SqueezeReactive] entry trigger for %s but no usable ask "
                    "yet (%s) -- retrying next scan", symbol, entry_reason)
        return "no_entry_quote", None

    move = bars[entry_index][1] / prior_close - 1
    return "entry", dict(
        entry_bar_time=bars[entry_index][0], entry_time=entry_quote_time,
        entry_ask=entry_ask, entry_move=move, prior_close=prior_close,
    )


def check_exit_position(symbol: str, open_row: dict, today: date, now_et: datetime):
    """Returns (status, payload):
      'pending' - not time to exit yet (still running, or the exit/EOD
          quote leg hasn't surfaced a usable price yet). Retried next scan;
          the position stays 'open'.
      'error'   - the bars pull failed after retries.
      'exit'    - exit resolved (payload carries exit_time, exit_bid,
          exit_reason, raw_return).
    """
    entry_bar_time = open_row["entry_bar_time"]
    is_eod = now_et.time() >= REACTIVE_SESSION_END_T
    end_time = SAMEDAY_EXIT_WINDOW_END if is_eod else now_et.strftime("%H:%M:%S")

    bars_status, bars, detail = fetch_reactive_session_bars(symbol, today, end_time)
    exit_index = None
    exit_confirm_time = None
    if bars_status == "error" and not is_eod:
        return "error", detail
    if bars_status == "ok":
        entry_index = next((i for i, b in enumerate(bars) if b[0] >= entry_bar_time), None)
        if entry_index is not None:
            exit_index, exit_confirm_time = find_reactive_wide_fade_exit(bars, entry_index)

    if exit_index is not None and exit_confirm_time.time() < now_et.time():
        exit_bid, exit_quote_time, exit_detail = fetch_reactive_quote(
            symbol, today, exit_confirm_time, "bid")
        if exit_bid is not None:
            raw_return = exit_bid / open_row["entry_ask"] - 1
            return "exit", dict(exit_time=exit_quote_time, exit_bid=exit_bid,
                                exit_reason="faded", raw_return=raw_return)
        logger.info("[SqueezeReactive] fade exit for %s but no usable bid yet "
                   "(%s) -- retrying next scan", symbol, exit_detail)
        return "pending", None

    if is_eod:
        exit_bid, exit_quote_time, exit_detail = fetch_sameday_exit_bid(symbol, today)
        if exit_bid is not None:
            raw_return = exit_bid / open_row["entry_ask"] - 1
            return "exit", dict(exit_time=exit_quote_time, exit_bid=exit_bid,
                                exit_reason="eod", raw_return=raw_return)
        logger.warning("[SqueezeReactive] EOD exit for %s has no usable NBBO "
                       "bid (%s) -- position stays open, retried next scan",
                       symbol, exit_detail)
        return "pending", None

    return "pending", None


# ---- Full scan --------------------------------------------------------------

def run_reactive_scan(engine: Engine, now_et: datetime) -> dict:
    """The full blocking scan: self-gated to the 09:30-16:00 ET regular
    session, universe -> stage-1 prefilter -> stage-2 entry/exit checks ->
    DB writes -> scan log. Run inside `asyncio.to_thread` by the scheduled
    job, same convention as squeeze_premarket_alerts.run_premarket_scan().
    Returns a summary dict plus `entries_opened`/`exits_closed` lists the
    caller needs to build Discord alerts.
    """
    ensure_tables(engine)
    today = now_et.date()

    if not (REACTIVE_SESSION_START_T <= now_et.time() <= REACTIVE_SESSION_END_T):
        return {"reason": "outside the 09:30:00-16:00:00 ET regular session",
                "entries_opened": [], "exits_closed": []}

    universe = load_universe(engine)
    if not universe:
        return {"reason": f"{UNIVERSE_TABLE} is empty",
                "entries_opened": [], "exits_closed": []}

    open_rows = load_open_positions(engine)
    open_symbols = set(open_rows)
    candidate_symbols = [s for s in universe if s not in open_symbols]

    shortlist, snapshot_batches, snapshot_errors = prefilter_candidates(candidate_symbols)

    entries_opened = []
    exits_closed = []
    errors = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        entry_futures = {pool.submit(check_entry_candidate, sym, today, now_et): sym
                         for sym in shortlist}
        exit_futures = {pool.submit(check_exit_position, sym, row, today, now_et): sym
                        for sym, row in open_rows.items()}

        for fut in as_completed(entry_futures):
            sym = entry_futures[fut]
            try:
                status, payload = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[SqueezeReactive] entry check failed for %s: %r", sym, exc)
                status, payload = "error", None
            if status == "error":
                errors += 1
            elif status == "entry":
                if already_signaled_recently(engine, sym, today):
                    continue
                open_position(engine, sym, today, **payload)
                entries_opened.append({"symbol": sym, **payload})

        for fut in as_completed(exit_futures):
            sym = exit_futures[fut]
            try:
                status, payload = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[SqueezeReactive] exit check failed for %s: %r", sym, exc)
                status, payload = "error", None
            if status == "error":
                errors += 1
            elif status == "exit":
                row = open_rows[sym]
                close_position(engine, sym, row["signal_date"], **payload)
                exits_closed.append({"symbol": sym, "entry_ask": row["entry_ask"],
                                     "entry_time": row["entry_time"], **payload})

    open_after = len(open_rows) - len(exits_closed) + len(entries_opened)
    record_scan_log(engine, now_et, len(universe), len(candidate_symbols),
                    len(shortlist), snapshot_batches, snapshot_errors,
                    len(open_rows), errors, len(entries_opened), len(exits_closed),
                    open_after)

    return {
        "reason": None, "universe_size": len(universe),
        "prefilter_candidates": len(candidate_symbols), "shortlist": len(shortlist),
        "snapshot_batches": snapshot_batches, "snapshot_errors": snapshot_errors,
        "open_before": len(open_rows), "open_after": open_after, "errors": errors,
        "entries_opened": entries_opened, "exits_closed": exits_closed,
    }


# ---- Discord alert copy -----------------------------------------------------

def _build_entry_alert(hit: dict) -> str:
    return (
        f"**{hit['symbol']}** ENTRY — reactive momentum\n"
        f"+{hit['entry_move'] * 100:.0f}% vs prior close (${hit['prior_close']:.2f}), "
        f"money pace ACCELERATING\n"
        f"ask ~{hit['entry_time'].strftime('%H:%M:%S')} ET: ${hit['entry_ask']:.2f}\n"
        "_squeeze reactive-momentum (wide-fade), no premarket gate, regular "
        "session only_"
    )


def _build_exit_alert(hit: dict) -> str:
    ret_pct = hit["raw_return"] * 100
    reason_label = {"faded": "money pace FADED", "eod": "16:00:00 ET close"}.get(
        hit["exit_reason"], hit["exit_reason"])
    arrow = "\U0001f7e2" if ret_pct >= 0 else "\U0001f534"
    return (
        f"**{hit['symbol']}** EXIT — {reason_label}\n"
        f"bid ~{hit['exit_time'].strftime('%H:%M:%S')} ET: ${hit['exit_bid']:.2f} "
        f"(entry ${hit['entry_ask']:.2f})\n"
        f"{arrow} realized: {ret_pct:+.1f}% (ask-to-bid, real NBBO both legs)\n"
        "_squeeze reactive-momentum (wide-fade)_"
    )


def register_squeeze_reactive_alerts(scheduler, app) -> None:
    """Attach the reactive scan job to the existing APScheduler.

    Scheduled every 5 minutes, 08:00-15:55 CT weekdays — a wider cron window
    than the real 09:30-16:00 ET (08:30-15:00 CT) regular session so a
    single `minute="*/5"` cron expression can express it (APScheduler cron
    triggers can't combine a `:30`-aligned start with a plain `*/5` minute
    field across an hour boundary in one expression); `run_reactive_scan()`
    self-gates on `now_et.time()` and simply returns a no-op `reason` for
    the handful of ticks outside the real window, same "cheap no-op outside
    the window" convention `_is_trading_day()` checks already use elsewhere
    in this file. `max_instances=1, coalesce=True` reuses the exact
    interval-capture discipline `market_structure.py`'s per-minute job
    already applies (see that module for precedent) — this is NOT a
    once-daily job, so `backend._dedup_ok()` (keyed per CALENDAR DAY) is
    deliberately NOT used here: claiming it once would block every
    subsequent tick for the rest of the day. Cross-replica double-posting
    protection is therefore the same as `market_structure.py`'s per-minute
    capture has today (none beyond max_instances=1 per process) — if
    SpreadWorks is ever scaled to multiple replicas this job would need the
    same fix that job would.
    """
    from .db import engine
    from . import _send_webhook_sync

    if scheduler is None:
        logger.warning("[SqueezeReactive] no scheduler — reactive scan job disabled")
        return

    try:
        ensure_tables(engine)
    except Exception as e:  # noqa: BLE001
        logger.warning("[SqueezeReactive] ensure_tables failed: %r", e)

    def _webhook_url() -> str:
        return (os.getenv(SQUEEZE_DISCORD_WEBHOOK_ENV, "").strip()
                or os.getenv("DISCORD_WEBHOOK_URL", "").strip())

    async def scan_reactive_squeeze():
        try:
            now_ct = datetime.now(CT)
            if now_ct.weekday() >= 5:
                return

            now_et = datetime.now(ET)
            summary = await asyncio.to_thread(run_reactive_scan, engine, now_et)

            if summary.get("reason"):
                logger.debug("[SqueezeReactive] scan skipped: %s", summary["reason"])
                return

            logger.info(
                "[SqueezeReactive] DONE: universe=%d prefilter_candidates=%d "
                "shortlist=%d snapshot_batches=%d snapshot_errors=%d "
                "open_before=%d open_after=%d errors=%d entries=%d exits=%d",
                summary["universe_size"], summary["prefilter_candidates"],
                summary["shortlist"], summary["snapshot_batches"],
                summary["snapshot_errors"], summary["open_before"],
                summary["open_after"], summary["errors"],
                len(summary["entries_opened"]), len(summary["exits_closed"]),
            )

            webhook = _webhook_url()
            for hit in summary["entries_opened"]:
                content = _build_entry_alert(hit)
                await asyncio.to_thread(
                    _send_webhook_sync,
                    {"description": content, "color": 0x00E676,
                     "footer": {"text": "squeeze-reactive (wide-fade) · ENTRY · "
                                        "signal-only, advisory only"}},
                    webhook)
            for hit in summary["exits_closed"]:
                content = _build_exit_alert(hit)
                color = 0x00E676 if hit["raw_return"] >= 0 else 0xFF1744
                await asyncio.to_thread(
                    _send_webhook_sync,
                    {"description": content, "color": color,
                     "footer": {"text": "squeeze-reactive (wide-fade) · EXIT · "
                                        "signal-only, advisory only"}},
                    webhook)
        except Exception as e:  # noqa: BLE001
            logger.warning("[SqueezeReactive] scan_reactive_squeeze failed: %r", e)

    scheduler.add_job(scan_reactive_squeeze, "cron", day_of_week="mon-fri",
                      hour="8-15", minute="*/5", timezone=CT, id=REACTIVE_JOB_ID,
                      coalesce=True, max_instances=1, misfire_grace_time=120,
                      replace_existing=True)

    _SCHEDULER["ref"] = scheduler
    logger.info("[SqueezeReactive] registered: every 5 min, 08:00-15:55 CT "
               "weekdays (self-gated to the 09:30-16:00 ET regular session)")
