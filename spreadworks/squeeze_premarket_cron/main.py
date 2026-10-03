"""
Render Cron Job - PREMARKET squeeze scanner (PRE-REGISTRATION #3 / V3)

Frozen rule, see `dev/squeeze/research/PREREG.md`, section
"PRE-REGISTRATION #3 -- PREMARKET-TURNOVER VARIANT (V3)" (written 2026-10-02):

    PREMARKET TURNOVER: sum(premarket volume 04:00:00-09:29:59 ET) /
        shares_outstanding >= 0.15
    PREMARKET MOVE: last premarket print vs the prior session's official
        close >= +10%
    FIRST ONLY: no qualifying signal for this symbol in the prior 30
        calendar days.

SIGNAL ONLY for the turnover/move rule itself -- no exit or P&L is computed
and no trade is taken, same convention as the local
`research/premarket_velocity_scan.py` this mirrors.

LIVE-MODE ENTRY PRICE (added 2026-10-02)
-----------------------------------------
The pre-reg's own fill convention (PREREG.md "Entry / exit": "buy at the
first NBBO ask timestamped >= 09:30:00 ET") was previously gated on a
quote-level (bid/ask) pull that did not exist -- `stock/history/ohlc` is
TRADES only. The proxy now also exposes `/v3/stock/history/quote` (NBBO
bid/ask, same param conventions as the ohlc route). For every candidate that
clears both floors in LIVE mode (never in BACKTEST_MODE), `fetch_entry_ask()`
pulls that endpoint for the 09:30:00-09:31:00 ET window and takes the ASK of
the first quote timestamped >= 09:30:00 ET -- never a trade price, never a
mid/mark. If no usable quote surfaces in that 60s window, the price is
logged as missing and left NULL rather than guessed. This closes PREREG.md's
stated data gap for the ENTRY leg only; the EXIT leg (10th-session close)
and the spread-bound tradeability check remain a separate, not-yet-built
ledger and are out of scope here.

WHY THIS RUNS ON RENDER INSTEAD OF THE WORKSTATION
---------------------------------------------------
The local scanner talks to a Theta Terminal on the workstation
(http://127.0.0.1:25510) whose network path to ThetaData has been unreliable.
This job instead calls the Render-only `thetadata_proxy` PRIVATE service
(`spreadworks/thetadata_proxy/app.py`), which connects to ThetaData directly
over gRPC from Render's network and does not depend on the workstation at
all. It is reached over Render's private network via THETADATA_BASE_URL
(same env var/HTTP convention already used by `data/vix_minute_fetcher.py`
and `spark_flame_research_routes.py`), never with a hardcoded hostname.

UNIVERSE
--------
Read from `squeeze_premarket_universe`. That table is assumed to be kept
populated by a SEPARATE local sync job (out of scope for this task -- this
script only consumes it). If it is empty (e.g. a fresh deploy before the
first sync has run), this logs a clear warning and exits 0 rather than
crashing or paging anyone.

PRIOR CLOSE -- DATA-GAP CHOICE (documented per task spec)
----------------------------------------------------------
`squeeze_premarket_universe` has no `prior_close` column (see the frozen
schema below), so this uses the OTHER option offered by the task spec:
request a wider window than just the premarket session and take the last bar
strictly before 04:00:00 ET as a stand-in for "prior close". Concretely, one
HTTP call per symbol spans 00:00:00-09:29:59 ET; everything before 04:00:00
is the "prior close proxy" (typically a late overnight/extended-hours print,
NOT the literal 16:00 ET prior-session close), and 04:00:00-09:29:59 is the
turnover/move window the pre-reg actually specifies. This is a known
approximation -- the frozen rule calls for "the prior regular session's
official close" -- and is accepted here only because it is the simpler of
the two options the task spec allowed, and because this is a signal-only
scanner, not a scored ledger. Do not treat this proxy as implementing the
pre-reg's EOD-close definition.

HAS_OPTIONS
-----------
The local scanner's `option_probe.probe()` is a local-repo module with no
AlphaGEX equivalent and does more than this job needs (NBBO probing for a
fill that isn't being computed here). This job instead asks the proxy's own
`/v3/option/list/expirations` endpoint, once per candidate that already
cleared both floors (same "only call for the small candidate set" discipline
as the local script), and treats a non-empty expirations list as
`has_options = True`, a definite empty/no-data answer as `False`, and a
proxy error as `NULL` (unknown, not a negative).

THRESHOLDS (FROZEN 2026-10-02 -- do not change without a new pre-registration)

BACKTEST MODE (added 2026-10-02, EXPLORATORY / IN-SAMPLE, NOT this file's live
forward ledger)
----------------------------------------------------------------------------
When the env var `BACKTEST_MODE` is set (any truthy value), `main()` branches
to `run_backtest()` BEFORE anything else -- the weekend guard, the live
universe/signals read-write path, and the Discord alert are never reached.
This answers a different, narrower question than the live scanner: of the
ALREADY-KNOWN historical day-level ignition population FAMILY #1/#2 already
use (see `dev/squeeze/research/sync_premarket_backtest_queue.py`, which
copies FAMILY #2's `exit_study.py signals()` definition verbatim), how many
ALSO clear the frozen V3 premarket turnover/move floors that same day? It is
a coverage/lead-time study, not a P&L backtest -- there is no real premarket
NBBO quote data behind this, so per the standing fill-discipline rule NO fill,
entry price, or dollar return is computed or stored anywhere in this mode.

Reads `squeeze_premarket_backtest_queue` (symbol, event_date,
shares_outstanding, prior_close, day_close) instead of
`squeeze_premarket_universe`, calls the proxy with THAT ROW's own event_date
(never "today"), and writes to `squeeze_premarket_backtest_results` instead
of `squeeze_premarket_signals`. No Discord alert is ever sent in this mode --
a backtest ping would read as a live signal, which it is not.

This mode must NEVER run on the scheduled trigger -- only via a manual
"Trigger Run" on the Render cron job with `BACKTEST_MODE` set in that run's
environment. Do not set `BACKTEST_MODE` on the job's persistent env vars.

PNL BACKTEST MODE (added 2026-10-03, fill-honest P&L for PREREG #3 / V3)
----------------------------------------------------------------------------
When the env var `PNL_BACKTEST_MODE` is set (any truthy value), `main()`
branches to `run_pnl_backtest()` BEFORE anything else -- same isolation as
`BACKTEST_MODE` above, and mutually exclusive with it (checked in that order).
This answers the question `BACKTEST_MODE` deliberately does NOT: of the
signals in `squeeze_premarket_backtest_results` that already cleared the
frozen V3 turnover/move floors (`fired_v3 = true`), what did the PREREG.md
"Entry / exit" rule actually pay, with real fills?

Rule (frozen, PREREG.md PRE-REGISTRATION #3, "Entry / exit" + "Primary
metric" -- not re-derived here):
  ENTRY: the first NBBO ask timestamped >= 09:30:00 ET on event_date (via
    `/v3/stock/history/quote`, same convention as the live path's
    `fetch_entry_ask()` -- never a trade price, never a mid/mark).
  TRADEABLE: entry spread ((ask-bid)/ask at that same quote) <= 2%. A signal
    with no usable quote, or spread > 2%, still gets a row (for the
    robustness report) but is excluded from the primary metric.
  EXIT: the close of the 10th trading session after event_date (via
    `/v3/stock/history/eod`), no stop, no target.
  SLIPPAGE: 2% per side, same convention as
    `dev/squeeze/research/exit_study.py`/`exit_study2.py` (the squeeze-nimble
    cell): entry fill = ask * (1 + 0.02), exit fill = exit_close * (1 - 0.02).
  SIZING: 1 unit per signal, equal weight (not applied here -- this job
    writes per-trade returns; the equal-weight sum is computed by the
    reporting script, not this cron).

This needs the SAME private-network path as `BACKTEST_MODE` -- the proxy's
`/v3/stock/history/quote` and `/v3/stock/history/eod` endpoints are only
reachable from inside Render, never from the workstation (confirmed
2026-10-03, same constraint `research/sync_premarket_backtest_queue.py`
documents for `BACKTEST_MODE`). This mode must NEVER run on the scheduled
trigger -- only via a manual "Trigger Run" with `PNL_BACKTEST_MODE` set in
that run's environment. Do not set it on the job's persistent env vars.
Writes to `squeeze_premarket_v3_pnl`, a table of its own -- it never touches
`squeeze_premarket_backtest_results` (read-only here) or any FAMILY #2 table.
"""
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as clock_time, timedelta
from io import StringIO
from csv import DictReader
from zoneinfo import ZoneInfo

import psycopg2
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("squeeze_premarket_cron")

ET = ZoneInfo("America/New_York")

# ---- Frozen rule (PREREG.md #3 / V3) - do not change without a new prereg ----
TURNOVER_FLOOR = 0.15
MOVE_FLOOR = 0.10
DEDUPE_DAYS = 30
PREMARKET_CUTOFF = clock_time(4, 0, 0)   # 04:00:00 ET - start of the scored window
SESSION_END = "09:29:59"                 # end of the scored window

# ---- Infra config (not part of the frozen rule) ----
# EXPLORATORY backtest path, see module docstring "BACKTEST MODE" section --
# any truthy value. Must never be set on the scheduled trigger's persistent
# env, only on a manual "Trigger Run".
BACKTEST_MODE = os.getenv("BACKTEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
# EXPLORATORY fill-honest P&L path, see module docstring "PNL BACKTEST MODE"
# section -- any truthy value. Must never be set on the scheduled trigger's
# persistent env, only on a manual "Trigger Run". Checked separately from
# BACKTEST_MODE; the two never run in the same invocation.
PNL_BACKTEST_MODE = os.getenv("PNL_BACKTEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")

THETA_BASE = os.getenv("THETADATA_BASE_URL", "http://thetadata-proxy:10000").strip().rstrip("/")
if THETA_BASE and "://" not in THETA_BASE:
    THETA_BASE = f"http://{THETA_BASE}"

REQUEST_TIMEOUT_S = 10
# Read timeout for calls to the internal thetadata-proxy service specifically
# (both the live scan's and the backtest's _fetch_csv() calls share this path
# -- see _fetch_csv() below). Raised from 10s to 30s 2026-10-02: concurrent
# MAX_WORKERS=25 load was causing ~3% of backtest pulls to fail with
# ReadTimeout even though the proxy itself was healthy. Kept separate from
# REQUEST_TIMEOUT_S, which still governs the unrelated Discord webhook post.
THETA_REQUEST_TIMEOUT_S = 30
HTTP_RETRIES = 2
HTTP_BACKOFF_S = 0.5
MAX_WORKERS = 25

# Discord: a dedicated squeeze channel if one is ever set up, falling back to
# the platform-shared webhook already used by every other bot in this repo
# (RISK_ADVISOR_DISCORD_WEBHOOK / TSUNAMI_DISCORD_WEBHOOK_URL /
# INTRADAY_DISCORD_WEBHOOK_URL all resolve the same way -- see
# spreadworks/backend/bots/discord_alerts.py and risk_alerts.py).
SQUEEZE_DISCORD_WEBHOOK_ENV = "SQUEEZE_DISCORD_WEBHOOK"
PLATFORM_DISCORD_WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


def _discord_webhook_url() -> str:
    return (os.getenv(SQUEEZE_DISCORD_WEBHOOK_ENV, "").strip()
            or os.getenv(PLATFORM_DISCORD_WEBHOOK_ENV, "").strip())


def _discord_post(content: str) -> bool:
    url = _discord_webhook_url()
    if not url:
        log.warning(
            "No %s or %s set - skipping Discord alert: %s",
            SQUEEZE_DISCORD_WEBHOOK_ENV, PLATFORM_DISCORD_WEBHOOK_ENV, content,
        )
        return False
    try:
        resp = requests.post(url, json={"content": content}, timeout=REQUEST_TIMEOUT_S)
        if resp.status_code not in (200, 204):
            log.warning("Discord post failed status=%s body=%s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 - a dead webhook must never crash the scan
        log.warning("Discord post raised: %r", exc)
        return False


def get_db_connection():
    """Direct psycopg2 connection - standard AlphaGEX pattern (see
    database_adapter.py), simplified to a single connection since this is a
    short-lived one-shot cron run, not a long-lived pooled service."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Set it on the Render Cron Job resource."
        )
    conn = psycopg2.connect(database_url, connect_timeout=30)
    conn.autocommit = False
    return conn


def ensure_tables(conn) -> None:
    """CREATE TABLE IF NOT EXISTS for both tables this job owns - AlphaGEX's
    standard 'auto-create tables on first use' convention (see
    .claude/rules/common-mistakes.md #10), so a fresh deploy never 500s/crashes
    for a missing table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_premarket_universe (
                symbol TEXT,
                shares_outstanding BIGINT,
                median20_volume BIGINT,
                as_of_date DATE,
                PRIMARY KEY (symbol)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_premarket_signals (
                signal_date DATE,
                symbol TEXT,
                premarket_turnover DOUBLE PRECISION,
                premarket_move DOUBLE PRECISION,
                premarket_vol BIGINT,
                has_options BOOLEAN,
                suggested_entry_ask DOUBLE PRECISION,
                noted_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (signal_date, symbol)
            )
        """)
        # Migration for a table that already existed before suggested_entry_ask
        # was added (2026-10-02) -- CREATE TABLE IF NOT EXISTS above is a no-op
        # against an already-deployed table, so the column needs its own
        # idempotent ALTER (AlphaGEX auto-migrate convention, common-mistakes #10).
        cur.execute("""
            ALTER TABLE squeeze_premarket_signals
            ADD COLUMN IF NOT EXISTS suggested_entry_ask DOUBLE PRECISION
        """)
    conn.commit()


def load_universe(conn) -> dict:
    """symbol -> shares_outstanding, for every symbol with a usable share
    count. Empty result is NOT an error here - it means the separate sync
    job hasn't populated the table yet (e.g. right after a fresh deploy)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT symbol, shares_outstanding
            FROM squeeze_premarket_universe
            WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0
        """)
        return {sym: shares for sym, shares in cur.fetchall()}


def already_signaled_recently(conn, symbol: str, today: date) -> bool:
    """30 calendar-day dedupe per symbol, same convention as the local V3
    scanner and V1/V2 before it."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM squeeze_premarket_signals
            WHERE symbol = %s AND signal_date >= %s::DATE - %s
        """, [symbol, today, DEDUPE_DAYS])
        return cur.fetchone()[0] > 0


def insert_signal(conn, today: date, symbol: str, turnover: float, move: float,
                   vol: int, has_options, suggested_entry_ask) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO squeeze_premarket_signals
                (signal_date, symbol, premarket_turnover, premarket_move,
                 premarket_vol, has_options, suggested_entry_ask)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (signal_date, symbol) DO NOTHING
        """, [today, symbol, turnover, move, vol, has_options, suggested_entry_ask])
    conn.commit()


def _fetch_csv(url: str, params: dict):
    """GET with a capped retry/backoff budget. Returns (rows, status, detail):
    status is 'ok' (rows is a list of dict rows, possibly empty, detail is
    None), 'no_data' (a definite ThetaData negative - 404/403 from the proxy,
    not worth retrying, detail is None), or 'error' (timeout/connection
    failure/5xx after HTTP_RETRIES retries - an unanswered question, never
    conflated with a negative answer). For 'error', `detail` is a dict
    {"http_status": int|None, "exception_type": str|None,
    "exception_message": str|None} describing the LAST attempt's failure, so
    callers that need a per-row failure reason (e.g. the backtest path) don't
    have to re-derive it from a bare exception repr."""
    last_exc = None
    last_status_code = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=THETA_REQUEST_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - connection errors, timeouts
            last_exc = exc
            last_status_code = None
            if attempt < HTTP_RETRIES:
                time.sleep(HTTP_BACKOFF_S * (attempt + 1))
            continue
        if resp.status_code in (404, 403):
            return [], "no_data", None
        if resp.status_code == 200:
            rows = list(DictReader(StringIO(resp.text)))
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
    log.debug("fetch failed after retries url=%s params=%s detail=%s", url, params, detail)
    return None, "error", detail


def scan_symbol(symbol: str, shares_outstanding: int, today: date):
    """Stage-1 worker: pure HTTP fetch + turnover/move math, NO database
    access (DB connections are not meant to be hammered from many threads at
    once - same discipline as the local scanner's Stage 1/Stage 2 split).

    Returns (status, payload). status is one of 'error' (no answer after
    retries), 'no_data' (proxy had nothing for this symbol/date), 'below_floor'
    (checked, did not clear turnover/move), or 'candidate' (payload is the
    tuple Stage 2 needs for dedupe + options lookup + insert).
    """
    url = f"{THETA_BASE}/v3/stock/history/ohlc"
    params = {
        "symbol": symbol,
        "date": today.isoformat(),
        "start_time": "00:00:00",
        "end_time": SESSION_END,
        "interval": "1m",
        "venue": "utp_cta",
    }
    rows, status, _detail = _fetch_csv(url, params)
    if status == "error":
        return "error", None
    if status == "no_data" or not rows:
        return "no_data", None

    pre_cutoff_close = None
    premarket_vol = 0
    premarket_last_px = None
    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            close = float(row["close"])
            vol = int(float(row["volume"]))
        except (KeyError, ValueError, TypeError):
            continue
        if ts.time() < PREMARKET_CUTOFF:
            # Last bar before 04:00 ET = our prior-close proxy (see module
            # docstring "PRIOR CLOSE" section) - rows are already in
            # chronological order from the proxy, so the last one wins.
            if close and close > 0:
                pre_cutoff_close = close
            continue
        premarket_vol += vol
        if close and close > 0:
            premarket_last_px = close

    if premarket_vol == 0 or premarket_last_px is None:
        return "no_data", None

    turnover = premarket_vol / shares_outstanding
    if turnover < TURNOVER_FLOOR:
        return "below_floor", None
    if not pre_cutoff_close:
        # No usable prior-close proxy - can't score the move leg, treat as
        # below floor rather than crashing the sweep over one bad symbol.
        return "below_floor", None

    move = premarket_last_px / pre_cutoff_close - 1
    if move < MOVE_FLOOR:
        return "below_floor", None

    return "candidate", (symbol, turnover, move, premarket_vol)


def probe_has_options(symbol: str):
    """True/False/None - see module docstring 'HAS_OPTIONS' section. Only
    called for the (small) candidate set, same call-count discipline as the
    local scanner's option_probe stage."""
    url = f"{THETA_BASE}/v3/option/list/expirations"
    rows, status, _detail = _fetch_csv(url, {"symbol": symbol})
    if status == "no_data":
        return False
    if status == "error":
        return None
    return bool(rows)


ENTRY_QUOTE_OPEN = clock_time(9, 30, 0)
ENTRY_QUOTE_WINDOW_END = "09:31:00"  # 60s search window for the first NBBO
                                      # ask at/after the 09:30:00 ET open


def fetch_entry_ask(symbol: str, today: date):
    """LIVE MODE ONLY (see module docstring 'LIVE-MODE ENTRY PRICE' section).
    Returns (ask, quote_time, reason): ask/quote_time are the first NBBO ask
    timestamped >= 09:30:00 ET within a 60s window -- the pre-reg's frozen
    ENTRY fill convention, and the standing "buy at the ask, never a mark"
    rule. If no usable ask surfaces in that window, ask/quote_time are None
    and `reason` explains why, so the caller logs a clear skip instead of
    falling back to a trade price or a mid. Only called for the (small)
    candidate set, same call-count discipline as probe_has_options()."""
    url = f"{THETA_BASE}/v3/stock/history/quote"
    params = {
        "symbol": symbol,
        "date": today.isoformat(),
        "start_time": "09:30:00",
        "end_time": ENTRY_QUOTE_WINDOW_END,
        "interval": "1s",
        "venue": "utp_cta",
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


# ===========================================================================
# BACKTEST MODE -- EXPLORATORY / IN-SAMPLE, NOT the live forward ledger above.
# See module docstring "BACKTEST MODE" section. Everything below this line is
# only ever reached when `BACKTEST_MODE` is set; it must never run on the
# scheduled trigger.
# ===========================================================================

def ensure_backtest_tables(conn) -> None:
    """CREATE TABLE IF NOT EXISTS for the two backtest-only tables. Called
    ONLY from run_backtest(), never from the live path's ensure_tables(), so
    a live run never issues these extra statements."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_premarket_backtest_queue (
                symbol TEXT,
                event_date DATE,
                shares_outstanding BIGINT,
                prior_close DOUBLE PRECISION,
                day_close DOUBLE PRECISION,
                PRIMARY KEY (symbol, event_date)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_premarket_backtest_results (
                symbol TEXT,
                event_date DATE,
                premarket_turnover DOUBLE PRECISION,
                premarket_move DOUBLE PRECISION,
                premarket_vol BIGINT,
                fired_v3 BOOLEAN,
                full_day_move DOUBLE PRECISION,
                premarket_share_of_day_move DOUBLE PRECISION,
                checked_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, event_date)
            )
        """)
    conn.commit()


def load_backtest_queue(conn) -> list:
    """(symbol, event_date, shares_outstanding, prior_close, day_close) for
    every queued ignition event with a usable share count -- same NULL/>0
    guard as load_universe(), applied to the backtest queue instead."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT symbol, event_date, shares_outstanding, prior_close, day_close
            FROM squeeze_premarket_backtest_queue
            WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0
            ORDER BY event_date, symbol
        """)
        return cur.fetchall()


def load_resolved_backtest_keys(conn) -> set:
    """(symbol, event_date) pairs that already have a row in
    squeeze_premarket_backtest_results -- i.e. already resolved by a prior
    run_backtest() run, whether that row is a real scored result or a
    'no_data' row (both are a written, final answer). A pair is NOT in this
    set only if a prior run hit status == 'error' for it, since the error
    branch below never writes a results row. Used so a re-run only retries
    the pairs that actually failed last time instead of re-pulling the whole
    queue."""
    with conn.cursor() as cur:
        cur.execute("SELECT symbol, event_date FROM squeeze_premarket_backtest_results")
        return {(sym, ed) for sym, ed in cur.fetchall()}


def insert_backtest_result(conn, symbol: str, event_date: date, turnover, move,
                            vol, fired: bool, full_day_move, share_of_day_move) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO squeeze_premarket_backtest_results
                (symbol, event_date, premarket_turnover, premarket_move,
                 premarket_vol, fired_v3, full_day_move, premarket_share_of_day_move)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, event_date) DO UPDATE SET
                premarket_turnover = EXCLUDED.premarket_turnover,
                premarket_move = EXCLUDED.premarket_move,
                premarket_vol = EXCLUDED.premarket_vol,
                fired_v3 = EXCLUDED.fired_v3,
                full_day_move = EXCLUDED.full_day_move,
                premarket_share_of_day_move = EXCLUDED.premarket_share_of_day_move,
                checked_at = now()
        """, [symbol, event_date, turnover, move, vol, fired, full_day_move, share_of_day_move])
    conn.commit()


def scan_symbol_backtest(symbol: str, event_date: date):
    """Backtest-mode stage-1 worker: pulls ONLY the premarket window
    (04:00:00-09:29:59 ET) for event_date -- unlike the live scan_symbol(),
    it does NOT need the wider 00:00:00-start proxy window for a prior-close
    stand-in, because the queue row already carries a real prior-session
    close from `bars_hold`. That makes this backtest path's premarket_move
    closer to the frozen rule's literal "prior regular session's official
    close" than the live scanner's proxy is.

    Returns (status, premarket_vol, premarket_last_px, detail). status is
    'error' (no answer after retries), 'no_data' (no premarket print at all --
    a real coverage gap, not computed as a non-fire), or 'ok'. `detail` is
    None except when status == 'error', where it carries the
    {"http_status", "exception_type", "exception_message"} dict from
    `_fetch_csv()` so run_backtest() can log the real per-row failure reason
    instead of folding it into a bare aggregate count.
    """
    url = f"{THETA_BASE}/v3/stock/history/ohlc"
    params = {
        "symbol": symbol,
        "date": event_date.isoformat(),
        "start_time": PREMARKET_CUTOFF.strftime("%H:%M:%S"),
        "end_time": SESSION_END,
        "interval": "1m",
        "venue": "utp_cta",
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return "error", None, None, detail
    if status == "no_data" or not rows:
        return "no_data", None, None, None

    premarket_vol = 0
    premarket_last_px = None
    for row in rows:
        try:
            close = float(row["close"])
            vol = int(float(row["volume"]))
        except (KeyError, ValueError, TypeError):
            continue
        premarket_vol += vol
        if close and close > 0:
            premarket_last_px = close

    if premarket_vol == 0 or premarket_last_px is None:
        return "no_data", None, None, None
    return "ok", premarket_vol, premarket_last_px, None


def run_backtest() -> int:
    """RESUMABLE: skips (symbol, event_date) pairs already written to
    squeeze_premarket_backtest_results and only retries pairs still missing
    (prior 'error' rows, which never get a results row written -- see
    load_resolved_backtest_keys()). Each row that still fails after retries
    is logged individually with symbol/event_date/http_status/exception, not
    just folded into the final aggregate count."""
    run_start = time.monotonic()
    log.info("=== squeeze premarket cron BACKTEST MODE (PREREG #3 / V3, "
              "EXPLORATORY/IN-SAMPLE, not the live forward ledger) ===")

    conn = get_db_connection()
    try:
        ensure_tables(conn)
        ensure_backtest_tables(conn)

        full_queue = load_backtest_queue(conn)
        if not full_queue:
            log.warning(
                "squeeze_premarket_backtest_queue is empty - nothing to "
                "backtest. Run dev/squeeze/research/sync_premarket_backtest_queue.py "
                "first."
            )
            return 0

        # RESUME: skip (symbol, event_date) pairs that already have a row in
        # squeeze_premarket_backtest_results (prior 'ok' or 'no_data' run) and
        # only retry pairs that are queued but have no result yet (prior
        # 'error' run, or never run at all). Turns a re-run after partial
        # failures into "only the rows that failed last time" instead of
        # redoing the whole queue.
        resolved = load_resolved_backtest_keys(conn)
        queue = [row for row in full_queue if (row[0], row[1]) not in resolved]
        already_resolved = len(full_queue) - len(queue)
        log.info(
            "backtest queue size: %d (symbol, event_date) rows, %d already "
            "resolved (skipped), %d pending (resume mode)",
            len(full_queue), already_resolved, len(queue),
        )
        if not queue:
            log.info("nothing pending - every queued row already has a result.")
            return 0

        checked = 0
        errors = 0
        no_data = 0
        fired = 0
        by_key = {(sym, ed): (sh, pc, dc) for sym, ed, sh, pc, dc in queue}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(scan_symbol_backtest, sym, ed): (sym, ed)
                for sym, ed, _sh, _pc, _dc in queue
            }
            for fut in as_completed(futures):
                sym, ed = futures[fut]
                shares_outstanding, prior_close, day_close = by_key[(sym, ed)]
                try:
                    status, vol, last_px, detail = fut.result()
                except Exception as exc:  # noqa: BLE001 - one worker must never kill the run
                    status, vol, last_px = "error", None, None
                    detail = {
                        "http_status": None,
                        "exception_type": type(exc).__name__,
                        "exception_message": repr(exc),
                    }
                checked += 1
                if status == "error":
                    errors += 1
                    log.error(
                        "backtest FAILED symbol=%s event_date=%s http_status=%s "
                        "exception_type=%s exception_message=%s",
                        sym, ed,
                        (detail or {}).get("http_status"),
                        (detail or {}).get("exception_type"),
                        (detail or {}).get("exception_message"),
                    )
                    continue
                full_day_move = (
                    day_close / prior_close - 1 if prior_close else None
                )
                if status == "no_data":
                    no_data += 1
                    insert_backtest_result(conn, sym, ed, None, None, None,
                                            False, full_day_move, None)
                    continue
                turnover = vol / shares_outstanding
                move = (last_px / prior_close - 1) if prior_close else None
                is_fired = bool(
                    move is not None and turnover >= TURNOVER_FLOOR and move >= MOVE_FLOOR
                )
                share_of_day_move = (
                    move / full_day_move
                    if move is not None and full_day_move not in (None, 0)
                    else None
                )
                if is_fired:
                    fired += 1
                insert_backtest_result(conn, sym, ed, turnover, move, vol,
                                        is_fired, full_day_move, share_of_day_move)

        elapsed = time.monotonic() - run_start
        log.info(
            "=== BACKTEST DONE: full_queue=%d already_resolved=%d pending=%d "
            "checked=%d errors=%d no_premarket_print=%d fired_v3=%d "
            "wall_clock=%.1fs ===",
            len(full_queue), already_resolved, len(queue), checked, errors,
            no_data, fired, elapsed,
        )
        log.info(
            "EXPLORATORY/IN-SAMPLE result, not the live forward ledger. No "
            "fill, entry price, or P&L computed anywhere in this mode."
        )
        return 0
    finally:
        conn.close()


# ===========================================================================
# PNL BACKTEST MODE -- EXPLORATORY, fill-honest P&L for PREREG #3 / V3. See
# module docstring "PNL BACKTEST MODE" section. Everything below this line is
# only ever reached when `PNL_BACKTEST_MODE` is set; it must never run on the
# scheduled trigger.
# ===========================================================================

PNL_SLIPPAGE = 0.02   # per side, same convention as exit_study.py/exit_study2.py
PNL_SPREAD_MAX = 0.02  # tradeable ceiling, PREREG.md "Entry / exit"
PNL_EXIT_SESSIONS = 10  # "close of the 10th session after entry"
# Calendar-day window pulled from `/v3/stock/history/eod` to find the 10th
# TRADING session after event_date -- comfortably >= 10 sessions even across
# a long holiday run; ThetaData's EOD series already skips weekends/holidays,
# so counting rows IS counting trading sessions, no calendar math needed.
PNL_EXIT_WINDOW_DAYS = 30


def ensure_pnl_tables(conn) -> None:
    """CREATE TABLE IF NOT EXISTS for the PNL-backtest-only table. Called
    ONLY from run_pnl_backtest(), never from the live path or BACKTEST_MODE's
    ensure_backtest_tables() -- a separate table, nothing overwritten."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_premarket_v3_pnl (
                symbol TEXT,
                event_date DATE,
                entry_ask DOUBLE PRECISION,
                entry_spread DOUBLE PRECISION,
                tradeable BOOLEAN,
                exit_close DOUBLE PRECISION,
                exit_date DATE,
                raw_return DOUBLE PRECISION,
                return_after_slippage DOUBLE PRECISION,
                checked_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, event_date)
            )
        """)
    conn.commit()


def load_pnl_queue(conn) -> list:
    """(symbol, event_date) for every signal that already fired V3 in the
    EXPLORATORY coverage backtest -- the population PREREG.md's primary
    metric is scored over."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT symbol, event_date FROM squeeze_premarket_backtest_results
            WHERE fired_v3 = true
            ORDER BY event_date, symbol
        """)
        return cur.fetchall()


def load_resolved_pnl_keys(conn) -> set:
    """(symbol, event_date) pairs that already have a row in
    squeeze_premarket_v3_pnl -- same resume convention as
    load_resolved_backtest_keys() above."""
    with conn.cursor() as cur:
        cur.execute("SELECT symbol, event_date FROM squeeze_premarket_v3_pnl")
        return {(sym, ed) for sym, ed in cur.fetchall()}


def insert_pnl_result(conn, symbol: str, event_date: date, entry_ask, entry_spread,
                       tradeable, exit_close, exit_date, raw_return,
                       return_after_slippage) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO squeeze_premarket_v3_pnl
                (symbol, event_date, entry_ask, entry_spread, tradeable,
                 exit_close, exit_date, raw_return, return_after_slippage)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, event_date) DO UPDATE SET
                entry_ask = EXCLUDED.entry_ask,
                entry_spread = EXCLUDED.entry_spread,
                tradeable = EXCLUDED.tradeable,
                exit_close = EXCLUDED.exit_close,
                exit_date = EXCLUDED.exit_date,
                raw_return = EXCLUDED.raw_return,
                return_after_slippage = EXCLUDED.return_after_slippage,
                checked_at = now()
        """, [symbol, event_date, entry_ask, entry_spread, tradeable, exit_close,
              exit_date, raw_return, return_after_slippage])
    conn.commit()


def fetch_entry_quote_for_date(symbol: str, event_date: date):
    """Same 60s-window NBBO search as the live path's `fetch_entry_ask()`,
    parametrized by a historical `event_date` instead of "today", and
    returning the paired bid alongside the ask so the caller can score the
    entry spread. Returns (ask, bid, quote_time, reason)."""
    url = f"{THETA_BASE}/v3/stock/history/quote"
    params = {
        "symbol": symbol,
        "date": event_date.isoformat(),
        "start_time": "09:30:00",
        "end_time": ENTRY_QUOTE_WINDOW_END,
        "interval": "1s",
        "venue": "utp_cta",
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, None, f"proxy error fetching NBBO quote: {detail}"
    if status == "no_data" or not rows:
        return None, None, None, "no NBBO quote data for the 09:30:00-09:31:00 ET window"

    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            ask = float(row["ask"])
        except (KeyError, ValueError, TypeError):
            continue
        if ts.time() < ENTRY_QUOTE_OPEN:
            continue
        if ask and ask > 0:
            try:
                bid = float(row["bid"])
            except (KeyError, ValueError, TypeError):
                bid = None
            return ask, bid, ts, None
    return None, None, None, "no quote with a usable ask price at/after 09:30:00 ET within the 60s window"


def fetch_tenth_session_close(symbol: str, event_date: date):
    """EXIT leg (PREREG.md: "sell at the close of the 10th session after
    entry"). Pulls daily EOD closes for the PNL_EXIT_WINDOW_DAYS calendar
    days after event_date and takes the 10th row by position. Returns
    (exit_close, exit_date, reason)."""
    start = event_date + timedelta(days=1)
    end = event_date + timedelta(days=PNL_EXIT_WINDOW_DAYS)
    url = f"{THETA_BASE}/v3/stock/history/eod"
    params = {"symbol": symbol, "start_date": start.isoformat(), "end_date": end.isoformat()}
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, f"proxy error fetching EOD closes: {detail}"
    if status == "no_data" or not rows:
        return None, None, "no EOD data in the 30 calendar-day window after event_date"
    if len(rows) < PNL_EXIT_SESSIONS:
        return None, None, (
            f"only {len(rows)} trading sessions available in the 30 calendar-day "
            f"window, need {PNL_EXIT_SESSIONS}"
        )
    row10 = rows[PNL_EXIT_SESSIONS - 1]
    try:
        exit_close = float(row10["close"])
    except (KeyError, ValueError, TypeError):
        return None, None, "10th-session row has no usable close"
    exit_date_raw = row10.get("date") or row10.get("timestamp") or ""
    try:
        exit_date = date.fromisoformat(str(exit_date_raw)[:10])
    except ValueError:
        return None, None, f"10th-session row has an unparseable date: {exit_date_raw!r}"
    return exit_close, exit_date, None


def scan_pnl_pair(symbol: str, event_date: date):
    """Stage-1 worker: pure HTTP, no DB access -- same discipline as
    scan_symbol_backtest(). Returns (status, payload):
      'entry_missing' - no usable NBBO ask at all (payload carries the reason
         only; the row is still written, all-NULL except symbol/event_date).
      'exit_missing'  - entry resolved but the 10th-session close did not
         (payload carries ask/spread/tradeable plus the reason).
      'ok'            - both legs resolved (payload carries every column).
    Spread and tradeability are computed here so a missing/zero bid never
    silently passes the <=2% gate."""
    ask, bid, _quote_time, entry_reason = fetch_entry_quote_for_date(symbol, event_date)
    if ask is None:
        return "entry_missing", {"reason": entry_reason}

    entry_spread = (ask - bid) / ask if (bid and bid > 0) else None
    tradeable = bool(entry_spread is not None and entry_spread <= PNL_SPREAD_MAX)

    exit_close, exit_date, exit_reason = fetch_tenth_session_close(symbol, event_date)
    if exit_close is None:
        return "exit_missing", {
            "ask": ask, "spread": entry_spread, "tradeable": tradeable,
            "reason": exit_reason,
        }

    raw_return = exit_close / ask - 1
    # 2% slippage per side, same convention as exit_study.py/exit_study2.py
    # (the squeeze-nimble cell): entry inflated by (1+slip), exit deflated by
    # (1-slip) -- see PNL_SLIPPAGE above.
    return_after_slip = exit_close * (1 - PNL_SLIPPAGE) / (ask * (1 + PNL_SLIPPAGE)) - 1
    return "ok", dict(
        entry_ask=ask, entry_spread=entry_spread, tradeable=tradeable,
        exit_close=exit_close, exit_date=exit_date,
        raw_return=raw_return, return_after_slippage=return_after_slip,
    )


def run_pnl_backtest() -> int:
    """RESUMABLE, same convention as run_backtest(): skips (symbol,
    event_date) pairs already written to squeeze_premarket_v3_pnl."""
    run_start = time.monotonic()
    log.info("=== squeeze premarket cron PNL BACKTEST MODE (PREREG #3 / V3, "
              "fill-honest P&L, EXPLORATORY, not the live forward ledger) ===")

    conn = get_db_connection()
    try:
        ensure_tables(conn)
        ensure_pnl_tables(conn)

        full_queue = load_pnl_queue(conn)
        if not full_queue:
            log.warning(
                "no fired_v3=true rows in squeeze_premarket_backtest_results - "
                "nothing to score. Run BACKTEST_MODE first."
            )
            return 0

        resolved = load_resolved_pnl_keys(conn)
        queue = [row for row in full_queue if tuple(row) not in resolved]
        already_resolved = len(full_queue) - len(queue)
        log.info(
            "PNL queue size: %d fired_v3 rows, %d already resolved (skipped), "
            "%d pending (resume mode)",
            len(full_queue), already_resolved, len(queue),
        )
        if not queue:
            log.info("nothing pending - every fired_v3 row already has a PNL result.")
            return 0

        checked = 0
        entry_missing = 0
        exit_missing = 0
        tradeable = 0
        not_tradeable = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(scan_pnl_pair, sym, ed): (sym, ed)
                for sym, ed in queue
            }
            for fut in as_completed(futures):
                sym, ed = futures[fut]
                try:
                    status, payload = fut.result()
                except Exception as exc:  # noqa: BLE001 - one worker must never kill the run
                    status, payload = "entry_missing", {"reason": repr(exc)}
                checked += 1

                if status == "entry_missing":
                    entry_missing += 1
                    log.warning("no usable NBBO ask for %s %s: %s", sym, ed, payload["reason"])
                    insert_pnl_result(conn, sym, ed, None, None, False, None, None, None, None)
                    continue

                if status == "exit_missing":
                    exit_missing += 1
                    log.warning("no usable 10th-session close for %s %s: %s",
                                sym, ed, payload["reason"])
                    if payload["tradeable"]:
                        tradeable += 1
                    else:
                        not_tradeable += 1
                    insert_pnl_result(conn, sym, ed, payload["ask"], payload["spread"],
                                       payload["tradeable"], None, None, None, None)
                    continue

                if payload["tradeable"]:
                    tradeable += 1
                else:
                    not_tradeable += 1
                insert_pnl_result(
                    conn, sym, ed, payload["entry_ask"], payload["entry_spread"],
                    payload["tradeable"], payload["exit_close"], payload["exit_date"],
                    payload["raw_return"], payload["return_after_slippage"],
                )

        elapsed = time.monotonic() - run_start
        log.info(
            "=== PNL BACKTEST DONE: full_queue=%d already_resolved=%d pending=%d "
            "checked=%d entry_missing=%d exit_missing=%d tradeable=%d "
            "not_tradeable=%d wall_clock=%.1fs ===",
            len(full_queue), already_resolved, len(queue), checked,
            entry_missing, exit_missing, tradeable, not_tradeable, elapsed,
        )
        log.info(
            "Fill convention: ENTRY = first NBBO ask >= 09:30:00 ET; EXIT = "
            "close of the 10th trading session after entry; 2%% slippage per "
            "side (entry*(1+slip), exit*(1-slip)); tradeable requires entry "
            "spread <= 2%%. EXPLORATORY result -- query squeeze_premarket_v3_pnl "
            "for the primary metric and robustness report."
        )
        return 0
    finally:
        conn.close()


def main() -> int:
    run_start = time.monotonic()
    if BACKTEST_MODE:
        return run_backtest()
    if PNL_BACKTEST_MODE:
        return run_pnl_backtest()
    today = datetime.now(ET).date()
    log.info("=== squeeze premarket cron (PREREG #3 / V3) - %s ===", today)

    if datetime.now(ET).weekday() >= 5 and "--force" not in sys.argv:
        log.info("weekend (ET) - skipping")
        return 0

    conn = get_db_connection()
    try:
        ensure_tables(conn)

        universe = load_universe(conn)
        if not universe:
            log.warning(
                "squeeze_premarket_universe is empty - nothing to scan. "
                "This is expected before the separate local sync job has "
                "populated it at least once; exiting cleanly, not an error."
            )
            return 0

        log.info("universe size: %d symbols", len(universe))

        checked = 0
        errors = 0
        no_data = 0
        below_floor = 0
        candidates = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(scan_symbol, sym, shares, today): sym
                for sym, shares in universe.items()
            }
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    status, payload = fut.result()
                except Exception as exc:  # noqa: BLE001 - one worker must never kill the run
                    log.warning("worker exception for %s: %r", sym, exc)
                    status, payload = "error", None
                checked += 1
                if status == "error":
                    errors += 1
                elif status == "no_data":
                    no_data += 1
                elif status == "below_floor":
                    below_floor += 1
                elif status == "candidate":
                    candidates.append(payload)

        log.info(
            "pull complete: %d/%d checked (%d errors, %d no premarket print, "
            "%d below floor), %d cleared both floors",
            checked, len(universe), errors, no_data, below_floor, len(candidates),
        )

        hits = []
        for symbol, turnover, move, vol in candidates:
            if already_signaled_recently(conn, symbol, today):
                continue
            has_options = probe_has_options(symbol)
            entry_ask, entry_quote_time, entry_skip_reason = fetch_entry_ask(symbol, today)
            if entry_ask is None:
                log.warning("no usable 09:30:00 ET NBBO ask for %s: %s",
                            symbol, entry_skip_reason)
            insert_signal(conn, today, symbol, turnover, move, vol, has_options, entry_ask)
            hits.append((symbol, turnover, move, vol, has_options, entry_ask, entry_quote_time))

        elapsed = time.monotonic() - run_start
        log.info(
            "=== DONE: universe=%d checked=%d errors=%d no_data=%d "
            "below_floor=%d candidates=%d new_signals=%d wall_clock=%.1fs ===",
            len(universe), checked, errors, no_data, below_floor,
            len(candidates), len(hits), elapsed,
        )

        for symbol, turnover, move, vol, has_options, entry_ask, entry_quote_time in hits:
            opt_tag = {True: "OPTIONS", False: "no opts", None: "opts?"}[has_options]
            if entry_ask is not None:
                price_line = (
                    f"ask ~{entry_quote_time.strftime('%H:%M:%S')} ET: ${entry_ask:.2f}"
                )
            else:
                price_line = (
                    "ask MISSING - no NBBO quote at/after 09:30:00 ET "
                    "within 60s (not a trade price, not a mark)"
                )
            msg = (
                f"**{symbol}** premarket turnover {turnover * 100:.0f}% of float, "
                f"+{move * 100:.0f}% premarket move  [{opt_tag}]\n"
                f"{price_line}\n"
                f"_PREREG #3 (V3), signal-only, no exit/P&L computed - "
                f"{today}_"
            )
            _discord_post(msg)

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log.exception("squeeze premarket cron failed: %s", exc)
        _discord_post(f"\U0001F6A8 Squeeze premarket cron failed: {exc}")
        raise
