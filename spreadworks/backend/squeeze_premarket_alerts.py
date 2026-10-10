"""Premarket squeeze-hunt signal — daily scan + Discord alert.

PORTED from the standalone Render Cron Job `squeeze_premarket_cron/main.py`
(commit d32a7a78b, branch claude/fix-pnl-backtest-exit-close-column) into this
always-on backend, following the exact wiring pattern `gamma_alerts.py` uses
for the gamma/GEX squeeze signal: one APScheduler job, claimed via
`backend._dedup_ok` BEFORE any work happens (so replicas/redeploys cannot
double-scan or double-post), posted through `backend._send_webhook_sync`.

ONLY THE LIVE PATH IS PORTED. The cron file's five `*_BACKTEST_MODE` branches
(BACKTEST_MODE, PNL_BACKTEST_MODE, SAMEDAY_PNL_BACKTEST_MODE,
TRAIL_PNL_BACKTEST_MODE, OPTIONS_PNL_BACKTEST_MODE) are exploratory research
paths manually triggered on the old cron resource — they are NOT ported here
and stay exactly where they are (`squeeze_premarket_cron/main.py`, left in
place but no longer scheduled) for `dev/squeeze/research/PREREG.md` to keep
pointing at. Nothing in this module touches FAMILY #2, the gamma-regime
squeeze signal (`bots/gamma_regime.py`), or any backtest table.

Frozen rule (PREREG.md #3 / V3 — do not change without a new pre-registration):
  PREMARKET TURNOVER: sum(premarket volume 04:00:00-09:29:59 ET) /
      shares_outstanding >= 0.15
  PREMARKET MOVE: last premarket print vs. the prior-close proxy >= +10%
  FIRST ONLY: no qualifying signal for this symbol in the prior 30 calendar
      days.

OVEREXTENDED-NAME EXCLUSION (added on this port, loss-pattern finding from
this session's research — NOT yet reflected in the standalone cron file):
  of names that clear both floors above, those with premarket_move > 0.5
  (i.e. already +50% premarket) OR premarket_turnover > 5 (already 5x float
  changed hands premarket) are excluded from the signal and the Discord
  alert. This is the SAME "data quality / sane-population" shape as the
  cron's own `premarket_turnover <= 50` corrupt-share-count guard and the
  OPTIONS_PNL_BACKTEST_MODE population filter (`premarket_turnover <= 50 AND
  premarket_move < 0.25`) — reused judgment, not reinvented. A row excluded
  here is NOT written to `squeeze_premarket_signals` and is logged as
  `overextended` rather than silently dropped.

UNIVERSE: read from `squeeze_premarket_universe`, kept populated by a SEPARATE
local workstation sync job — unaffected by and out of scope for this port.
An empty universe logs a clear warning and the job exits cleanly, matching
the cron's own "expected right after a fresh deploy" convention.

WHY THETADATA PROXY, NOT TRADIER: the frozen V3 rule needs real premarket
NBBO (quote) data, which Tradier does not serve for this window. This talks
to the same Render-private `thetadata_proxy` service
(`spreadworks/thetadata_proxy/app.py`) over THETADATA_BASE_URL that
`market_structure.py` and the EMBER fleet already use — same env var, same
"private network only" convention, never a hardcoded hostname.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from csv import DictReader
from datetime import date, datetime, time as dtime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")  # the frozen rule's own session clock

# ---- Frozen rule (PREREG.md #3 / V3) — do not change without a new prereg ----
TURNOVER_FLOOR = 0.15
MOVE_FLOOR = 0.10
DEDUPE_DAYS = 30
PREMARKET_CUTOFF = dtime(4, 0, 0)    # 04:00:00 ET — start of the scored window
SESSION_END = "09:29:59"             # end of the scored window

# ---- Overextended-name exclusion (this session's loss-pattern finding) ----
OVEREXTENDED_MOVE_CAP = 0.5       # exclude premarket_move > 50%
OVEREXTENDED_TURNOVER_CAP = 5.0   # exclude premarket_turnover > 5x float

# ---- Infra config (not part of the frozen rule) ----
THETA_REQUEST_TIMEOUT_S = 30
HTTP_RETRIES = 2
HTTP_BACKOFF_S = 0.5
MAX_WORKERS = 25

SQUEEZE_DISCORD_WEBHOOK_ENV = "SQUEEZE_DISCORD_WEBHOOK"

# Set by register_squeeze_premarket_alerts once the job is actually attached.
_SCHEDULER: dict = {"ref": None}
PREMARKET_JOB_ID = "squeeze_premarket_scan"

UNIVERSE_TABLE = "squeeze_premarket_universe"
SIGNALS_TABLE = "squeeze_premarket_signals"
SCAN_LOG_TABLE = "squeeze_premarket_scan_log"


def _theta_base() -> str:
    value = os.getenv("THETADATA_BASE_URL", "").strip().rstrip("/")
    return f"http://{value}" if value and "://" not in value else value


def scheduled_jobs() -> dict:
    """Is the premarket scan job armed, and when does it next fire?

    Same "never run" disambiguation as gamma_alerts.scheduled_jobs() — a
    scheduler that never started and a job that simply has not reached its
    first firing both look like "never run" without this. Never raises.
    """
    sched = _SCHEDULER.get("ref")
    if sched is None:
        return {"registered": False, "jobs": {},
                "reason": "Premarket squeeze job is not armed — no scheduler was attached."}
    out: dict = {"registered": True, "jobs": {}, "reason": None}
    try:
        job = sched.get_job(PREMARKET_JOB_ID)
        nxt = getattr(job, "next_run_time", None) if job else None
        out["jobs"][PREMARKET_JOB_ID] = nxt.isoformat() if nxt else None
    except Exception as e:  # noqa: BLE001
        out["jobs"][PREMARKET_JOB_ID] = None
        out["reason"] = f"job lookup failed: {e}"
    return out


def ensure_tables(engine: Engine) -> None:
    """CREATE TABLE IF NOT EXISTS for the two tables this job shares with the
    retired cron (unchanged names/columns — other scripts, e.g.
    dev/squeeze/research/pull_premarket_signals.py, already read
    squeeze_premarket_signals), plus a NEW scan-log table owned solely by
    this module so /state can tell "job ran, found nothing" apart from "job
    never ran" — a zero-signal day is a legitimate outcome, not a failure.
    Auto-create on first use, same convention as every other table in this
    backend (common-mistakes.md #10) — a fresh deploy must never 500.
    """
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {UNIVERSE_TABLE} (
                symbol TEXT,
                shares_outstanding BIGINT,
                median20_volume BIGINT,
                as_of_date DATE,
                PRIMARY KEY (symbol)
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {SIGNALS_TABLE} (
                signal_date DATE,
                symbol TEXT,
                premarket_turnover DOUBLE PRECISION,
                premarket_move DOUBLE PRECISION,
                premarket_vol BIGINT,
                has_options BOOLEAN,
                suggested_entry_ask DOUBLE PRECISION,
                noted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (signal_date, symbol)
            )
        """))
        try:
            conn.execute(text(f"""
                ALTER TABLE {SIGNALS_TABLE}
                ADD COLUMN IF NOT EXISTS suggested_entry_ask DOUBLE PRECISION
            """))
        except Exception:                                      # noqa: BLE001
            pass
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {SCAN_LOG_TABLE} (
                run_date DATE PRIMARY KEY,
                universe_size INTEGER,
                checked INTEGER,
                errors INTEGER,
                no_data INTEGER,
                below_floor INTEGER,
                overextended_excluded INTEGER,
                candidates INTEGER,
                new_signals INTEGER,
                completed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))


def load_universe(engine: Engine) -> dict:
    """symbol -> shares_outstanding, for every symbol with a usable share
    count. An empty result is NOT an error — it means the separate local
    sync job has not populated the table yet (e.g. right after a fresh
    deploy), same as the retired cron's own convention."""
    with engine.begin() as conn:
        rows = conn.execute(text(f"""
            SELECT symbol, shares_outstanding FROM {UNIVERSE_TABLE}
            WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0
        """)).fetchall()
    return {r[0]: r[1] for r in rows}


def already_signaled_recently(engine: Engine, symbol: str, today: date) -> bool:
    """30 calendar-day dedupe per symbol — identical convention to the
    retired cron and the local V1-V3 scanners before it. The cutoff is
    computed in Python (not a Postgres-only `::DATE -` cast inline in the
    query) so the statement stays dialect-portable and unambiguous to
    SQLAlchemy's bind-parameter parser."""
    cutoff = today - timedelta(days=DEDUPE_DAYS)
    with engine.begin() as conn:
        row = conn.execute(text(f"""
            SELECT count(*) FROM {SIGNALS_TABLE}
            WHERE symbol = :sym AND signal_date >= :cutoff
        """), {"sym": symbol, "cutoff": cutoff}).fetchone()
    return bool(row and row[0] > 0)


def insert_signal(engine: Engine, today: date, symbol: str, turnover: float,
                   move: float, vol: int, has_options, suggested_entry_ask) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {SIGNALS_TABLE}
                (signal_date, symbol, premarket_turnover, premarket_move,
                 premarket_vol, has_options, suggested_entry_ask)
            VALUES (:d, :sym, :t, :m, :v, :ho, :ask)
            ON CONFLICT (signal_date, symbol) DO NOTHING
        """), {"d": today, "sym": symbol, "t": turnover, "m": move, "v": vol,
               "ho": has_options, "ask": suggested_entry_ask})


def record_scan_log(engine: Engine, today: date, universe_size: int, checked: int,
                     errors: int, no_data: int, below_floor: int,
                     overextended_excluded: int, candidates: int,
                     new_signals: int) -> None:
    """One row per run, regardless of hits — this is the "the job actually
    completed" marker /state's capture_health compares against the dedup
    ledger's claim, same shape as gamma_regime.capture_health()."""
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {SCAN_LOG_TABLE}
                (run_date, universe_size, checked, errors, no_data,
                 below_floor, overextended_excluded, candidates, new_signals)
            VALUES (:d, :u, :c, :e, :nd, :bf, :oe, :cand, :ns)
            ON CONFLICT (run_date) DO UPDATE SET
                universe_size = EXCLUDED.universe_size,
                checked = EXCLUDED.checked, errors = EXCLUDED.errors,
                no_data = EXCLUDED.no_data, below_floor = EXCLUDED.below_floor,
                overextended_excluded = EXCLUDED.overextended_excluded,
                candidates = EXCLUDED.candidates, new_signals = EXCLUDED.new_signals,
                completed_at = CURRENT_TIMESTAMP
        """), {"d": today, "u": universe_size, "c": checked, "e": errors,
               "nd": no_data, "bf": below_floor, "oe": overextended_excluded,
               "cand": candidates, "ns": new_signals})


def _fetch_csv(url: str, params: dict):
    """GET with a capped retry/backoff budget — ported verbatim from the
    cron's `_fetch_csv()`. Returns (rows, status, detail): 'ok' (rows is a
    list of dict rows, possibly empty), 'no_data' (a definite ThetaData
    negative — 404/403, not worth retrying), or 'error' (timeout/connection
    failure/5xx after HTTP_RETRIES retries — an unanswered question, never
    conflated with a negative answer)."""
    last_exc = None
    last_status_code = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=THETA_REQUEST_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            last_status_code = None
            if attempt < HTTP_RETRIES:
                time.sleep(HTTP_BACKOFF_S * (attempt + 1))
            continue
        if resp.status_code in (404, 403):
            return [], "no_data", None
        if resp.status_code == 200:
            rows = list(DictReader(io.StringIO(resp.text)))
            return rows, "ok", None
        last_status_code = resp.status_code
        last_exc = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if attempt < HTTP_RETRIES:
            time.sleep(HTTP_BACKOFF_S * (attempt + 1))
    detail = {
        "http_status": last_status_code,
        "exception_type": type(last_exc).__name__ if last_exc else None,
        "exception_message": str(last_exc) if last_exc else None,
    }
    logger.debug("[SqueezePremarket] fetch failed after retries url=%s params=%s detail=%s",
                 url, params, detail)
    return None, "error", detail


def scan_symbol(symbol: str, shares_outstanding: int, today: date):
    """Stage-1 worker: pure HTTP fetch + turnover/move math, no DB access —
    ported verbatim from the cron's `scan_symbol()`, PLUS the overextended-
    name exclusion (see module docstring).

    Returns (status, payload). status is 'error', 'no_data', 'below_floor',
    'overextended' (cleared both floors but excluded by the loss-pattern
    filter), or 'candidate' (payload is the tuple the alert stage needs)."""
    theta_base = _theta_base()
    url = f"{theta_base}/v3/stock/history/ohlc"
    params = {
        "symbol": symbol, "date": today.isoformat(),
        "start_time": "00:00:00", "end_time": SESSION_END,
        "interval": "1m", "venue": "utp_cta",
    }
    rows, status, _detail = _fetch_csv(url, params)
    if status == "error":
        return "error", None
    if status == "no_data" or not rows:
        return "no_data", None

    pre_cutoff_close = None
    premarket_vol = 0
    premarket_last_px = None
    premarket_dollar_vol = 0.0
    premarket_last_ts = None
    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            close = float(row["close"])
            vol = int(float(row["volume"]))
        except (KeyError, ValueError, TypeError):
            continue
        if ts.time() < PREMARKET_CUTOFF:
            if close and close > 0:
                pre_cutoff_close = close
            continue
        premarket_vol += vol
        if close and close > 0:
            premarket_last_px = close
            premarket_dollar_vol += close * vol
            premarket_last_ts = ts

    if premarket_vol == 0 or premarket_last_px is None:
        return "no_data", None

    turnover = premarket_vol / shares_outstanding
    if turnover < TURNOVER_FLOOR:
        return "below_floor", None
    if not pre_cutoff_close:
        return "below_floor", None

    move = premarket_last_px / pre_cutoff_close - 1
    if move < MOVE_FLOOR:
        return "below_floor", None

    if move > OVEREXTENDED_MOVE_CAP or turnover > OVEREXTENDED_TURNOVER_CAP:
        return "overextended", None

    return "candidate", (symbol, turnover, move, premarket_vol,
                          premarket_dollar_vol, premarket_last_ts)


def probe_has_options(symbol: str):
    """True/False/None — ported verbatim. Only called for the (small)
    candidate set, same call-count discipline as the retired cron."""
    theta_base = _theta_base()
    url = f"{theta_base}/v3/option/list/expirations"
    rows, status, _detail = _fetch_csv(url, {"symbol": symbol})
    if status == "no_data":
        return False
    if status == "error":
        return None
    return bool(rows)


ENTRY_QUOTE_OPEN = dtime(9, 30, 0)
ENTRY_QUOTE_WINDOW_END = "09:31:00"


def fetch_entry_ask(symbol: str, today: date):
    """First NBBO ask timestamped >= 09:30:00 ET within a 60s window —
    ported verbatim from the cron's `fetch_entry_ask()`. Never a trade
    price, never a mid/mark; a miss leaves the ask NULL with a reason."""
    theta_base = _theta_base()
    url = f"{theta_base}/v3/stock/history/quote"
    params = {
        "symbol": symbol, "date": today.isoformat(),
        "start_time": "09:30:00", "end_time": ENTRY_QUOTE_WINDOW_END,
        "interval": "1s", "venue": "utp_cta",
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, f"proxy error fetching NBBO quote: {detail}"
    if status == "no_data" or not rows:
        return None, None, "no NBBO quote data for the 09:30:00-09:31:00 ET window"

    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            ask = float(row["ask"])
        except (KeyError, ValueError, TypeError):
            continue
        if ts.time() < ENTRY_QUOTE_OPEN:
            continue
        if ask and ask > 0:
            return ask, ts, None
    return None, None, "no quote with a usable ask price at/after 09:30:00 ET within the 60s window"


# ---- LIVE MONEY PACE (ported verbatim from commit d32a7a78b) --------------
MONEY_PACE_RECENT_MINUTES = 15
MONEY_PACE_ACCEL_HIGH = 1.25
MONEY_PACE_ACCEL_LOW = 0.6


def fetch_recent_dollar_flow(symbol: str, today: date, now_et: datetime,
                              window_minutes: int = MONEY_PACE_RECENT_MINUTES):
    """Trailing `window_minutes` of 1-minute OHLC bars ending at the current
    ET wall-clock time — ported verbatim. Clamped to never reach back before
    PREMARKET_CUTOFF (04:00:00 ET)."""
    theta_base = _theta_base()
    premarket_start_et = datetime.combine(today, PREMARKET_CUTOFF, tzinfo=ET)
    start_dt = max(now_et - timedelta(minutes=window_minutes), premarket_start_et)
    if start_dt >= now_et:
        return None, None, "signal fired at/before premarket start - no recent window yet"
    url = f"{theta_base}/v3/stock/history/ohlc"
    params = {
        "symbol": symbol, "date": today.isoformat(),
        "start_time": start_dt.strftime("%H:%M:%S"),
        "end_time": now_et.strftime("%H:%M:%S"),
        "interval": "1m", "venue": "utp_cta",
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, f"proxy error fetching recent window: {detail}"
    if status == "no_data" or not rows:
        return None, None, "no bars in the trailing window"

    dollar_vol = 0.0
    for row in rows:
        try:
            close = float(row["close"])
            vol = int(float(row["volume"]))
        except (KeyError, ValueError, TypeError):
            continue
        if close and close > 0 and vol:
            dollar_vol += close * vol

    elapsed_minutes = (now_et - start_dt).total_seconds() / 60.0
    return dollar_vol, elapsed_minutes, None


def money_pace_tag(symbol: str, today: date, now_et: datetime,
                    premarket_dollar_vol, premarket_minutes):
    """ACCELERATING/FADING/STEADY/None — ported verbatim from commit
    d32a7a78b. Decision-support only; never gates whether the signal fires."""
    if not premarket_minutes or premarket_minutes < 5 or not premarket_dollar_vol:
        return None
    recent_dv, recent_minutes, reason = fetch_recent_dollar_flow(symbol, today, now_et)
    if recent_dv is None or not recent_minutes:
        logger.info("[SqueezePremarket] money pace unavailable for %s: %s", symbol, reason)
        return None
    rate_before = premarket_dollar_vol / premarket_minutes
    if rate_before <= 0:
        return None
    rate_now = recent_dv / recent_minutes
    accel = rate_now / rate_before
    if accel >= MONEY_PACE_ACCEL_HIGH:
        return "ACCELERATING"
    if accel <= MONEY_PACE_ACCEL_LOW:
        return "FADING"
    return "STEADY"


def run_premarket_scan(engine: Engine, today: date) -> dict:
    """The full blocking scan: universe -> ThreadPoolExecutor scan -> dedupe
    -> has_options -> entry ask -> insert -> scan log. Run inside
    `asyncio.to_thread` by the scheduled job, same convention as
    gamma_alerts.capture_gamma's `_run()`. Returns a summary dict plus the
    `hits` list the caller needs to build Discord alerts (money-pace tag is
    computed by the caller, since it depends on wall-clock "now").
    """
    ensure_tables(engine)
    universe = load_universe(engine)
    if not universe:
        logger.warning(
            "[SqueezePremarket] %s is empty - nothing to scan. Expected before "
            "the separate local sync job has populated it at least once.",
            UNIVERSE_TABLE)
        return {"universe_size": 0, "checked": 0, "errors": 0, "no_data": 0,
                "below_floor": 0, "overextended_excluded": 0, "candidates": 0,
                "new_signals": 0, "hits": [],
                "reason": f"{UNIVERSE_TABLE} is empty"}

    checked = errors = no_data = below_floor = overextended = 0
    candidates = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scan_symbol, sym, shares, today): sym
                   for sym, shares in universe.items()}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                status, payload = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[SqueezePremarket] worker exception for %s: %r", sym, exc)
                status, payload = "error", None
            checked += 1
            if status == "error":
                errors += 1
            elif status == "no_data":
                no_data += 1
            elif status == "below_floor":
                below_floor += 1
            elif status == "overextended":
                overextended += 1
            elif status == "candidate":
                candidates.append(payload)

    logger.info(
        "[SqueezePremarket] pull complete: %d/%d checked (%d errors, %d no "
        "premarket print, %d below floor, %d overextended-excluded), %d cleared",
        checked, len(universe), errors, no_data, below_floor, overextended,
        len(candidates))

    hits = []
    for symbol, turnover, move, vol, premarket_dollar_vol, premarket_last_ts in candidates:
        if already_signaled_recently(engine, symbol, today):
            continue
        has_options = probe_has_options(symbol)
        entry_ask, entry_quote_time, entry_skip_reason = fetch_entry_ask(symbol, today)
        if entry_ask is None:
            logger.warning("[SqueezePremarket] no usable 09:30:00 ET NBBO ask "
                           "for %s: %s", symbol, entry_skip_reason)
        insert_signal(engine, today, symbol, turnover, move, vol, has_options, entry_ask)
        hits.append({"symbol": symbol, "turnover": turnover, "move": move,
                     "vol": vol, "has_options": has_options, "entry_ask": entry_ask,
                     "entry_quote_time": entry_quote_time,
                     "premarket_dollar_vol": premarket_dollar_vol,
                     "premarket_last_ts": premarket_last_ts})

    record_scan_log(engine, today, len(universe), checked, errors, no_data,
                    below_floor, overextended, len(candidates), len(hits))

    return {"universe_size": len(universe), "checked": checked, "errors": errors,
           "no_data": no_data, "below_floor": below_floor,
           "overextended_excluded": overextended, "candidates": len(candidates),
           "new_signals": len(hits), "hits": hits, "reason": None}


def _build_alert_lines(hit: dict, today: date, now_et: datetime) -> str:
    """One Discord message per new signal — same copy/shape as the retired
    cron's Discord post, including the live money-pace line."""
    opt_tag = {True: "OPTIONS", False: "no opts", None: "opts?"}[hit["has_options"]]
    if hit["entry_ask"] is not None:
        price_line = f"ask ~{hit['entry_quote_time'].strftime('%H:%M:%S')} ET: ${hit['entry_ask']:.2f}"
    else:
        price_line = ("ask MISSING - no NBBO quote at/after 09:30:00 ET within "
                      "60s (not a trade price, not a mark)")

    premarket_minutes = None
    if hit["premarket_last_ts"] is not None:
        premarket_start_dt = datetime.combine(today, PREMARKET_CUTOFF)
        premarket_minutes = (hit["premarket_last_ts"] - premarket_start_dt).total_seconds() / 60.0
    pace_tag = money_pace_tag(hit["symbol"], today, now_et,
                              hit["premarket_dollar_vol"], premarket_minutes)

    lines = [
        f"**{hit['symbol']}** premarket turnover {hit['turnover'] * 100:.0f}% of float, "
        f"+{hit['move'] * 100:.0f}% premarket move  [{opt_tag}]",
        price_line,
    ]
    if pace_tag == "ACCELERATING":
        lines.append("Money: ACCELERATING")
    elif pace_tag == "FADING":
        lines.append("Money: FADING - may already be done")
    elif pace_tag == "STEADY":
        lines.append("Money: STEADY")
    lines.append(f"_PREREG #3 (V3), signal-only, no exit/P&L computed - {today}_")
    return "\n".join(lines)


def register_squeeze_premarket_alerts(scheduler, app) -> None:
    """Attach the premarket squeeze-scan job to the existing APScheduler.

    Scheduled once on weekday mornings at 08:15 CT (09:15 ET) — 15 minutes
    of margin before the 09:30 ET cash open, same "finish comfortably before
    the open" reasoning the retired cron's own schedule used.
    """
    from .db import engine
    from . import _dedup_ok, _send_webhook_sync

    if scheduler is None:
        logger.warning("[SqueezePremarket] no scheduler — premarket scan job disabled")
        return

    try:
        ensure_tables(engine)
    except Exception as e:  # noqa: BLE001
        logger.warning("[SqueezePremarket] ensure_tables failed: %r", e)

    def _webhook_url() -> str:
        return (os.getenv(SQUEEZE_DISCORD_WEBHOOK_ENV, "").strip()
                or os.getenv("DISCORD_WEBHOOK_URL", "").strip())

    async def scan_premarket_squeeze():
        """08:15 CT weekdays: scan the universe, write new signals, alert on
        each. Claims the dedup slot BEFORE doing any work — same "claim the
        slot, then do the work" discipline as gamma_alerts.capture_gamma, so
        a redeploy or extra replica cannot double-scan or double-post."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            if not _dedup_ok(PREMARKET_JOB_ID, fire_date=now.date()):
                return

            today_et = datetime.now(ET).date()
            summary = await asyncio.to_thread(run_premarket_scan, engine, today_et)

            if summary.get("reason"):
                logger.info("[SqueezePremarket] scan skipped: %s", summary["reason"])
                return

            logger.info(
                "[SqueezePremarket] DONE: universe=%d checked=%d errors=%d "
                "no_data=%d below_floor=%d overextended_excluded=%d "
                "candidates=%d new_signals=%d",
                summary["universe_size"], summary["checked"], summary["errors"],
                summary["no_data"], summary["below_floor"],
                summary["overextended_excluded"], summary["candidates"],
                summary["new_signals"])

            webhook = _webhook_url()
            now_et = datetime.now(ET)
            for hit in summary["hits"]:
                content = _build_alert_lines(hit, today_et, now_et)
                await asyncio.to_thread(_send_webhook_sync,
                                        {"description": content, "color": 0xFBBF24,
                                         "footer": {"text": "squeeze-premarket (PREREG #3/V3) · "
                                                            "signal-only, advisory only"}},
                                        webhook)
        except Exception as e:  # noqa: BLE001
            logger.warning("[SqueezePremarket] scan_premarket_squeeze failed: %r", e)

    scheduler.add_job(scan_premarket_squeeze, "cron", day_of_week="mon-fri",
                      hour=8, minute=15, timezone=CT, id=PREMARKET_JOB_ID,
                      coalesce=True, max_instances=1, replace_existing=True)

    _SCHEDULER["ref"] = scheduler
    logger.info("[SqueezePremarket] registered: premarket scan 08:15 CT (09:15 ET)")
