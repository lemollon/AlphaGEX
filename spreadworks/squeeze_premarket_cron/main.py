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

SAMEDAY PNL BACKTEST MODE (added 2026-10-03, EXPLORATORY second look -- a new
question against the same historical population PNL_BACKTEST_MODE already
scored, NOT a confirmed result)
----------------------------------------------------------------------------
When the env var `SAMEDAY_PNL_BACKTEST_MODE` is set (any truthy value),
`main()` branches to `run_sameday_pnl_backtest()` BEFORE anything else --
same isolation as `BACKTEST_MODE`/`PNL_BACKTEST_MODE` above, checked after
both of those and mutually exclusive with them. This is deliberately a
SEPARATE mode/table from both -- neither existing mode's behavior changes.

This asks a different exit question than PNL_BACKTEST_MODE: instead of
holding 10 trading sessions, what does the SAME entry pay if closed out the
SAME DAY, at a real NBBO bid near the close -- never the trade-print close,
never a mark?

Two fixes applied here, both already diagnosed outside this file (not
re-derived):

  FIX 1 -- DATA QUALITY FILTER: `squeeze_premarket_backtest_results.
    premarket_turnover` can show physically impossible values (e.g. 214x,
    322x of float) from corrupt/stale `shares_outstanding` -- the identical
    bug the live scanner already guards against (see
    `dev/squeeze/research/live_velocity_screen.py`'s `if t > 50: continue
    # corrupt share count`). The queue query below applies the identical
    `premarket_turnover <= 50` cap.

  FIX 2 -- REAL SAME-DAY EXIT PRICE: exit at the last NBBO bid timestamped
    strictly before 16:00:00 ET, searched in the 15:55:00-16:00:00 ET
    lookback window via the same `/v3/stock/history/quote` endpoint used for
    the entry leg -- never the close print, never a mark.

Population: `load_sameday_pnl_queue()` joins the already-resolved
`squeeze_premarket_v3_pnl` rows (entry already computed there -- reused
as-is, not re-pulled) to `squeeze_premarket_backtest_results` on
(symbol, event_date), keeping only rows where `premarket_turnover <= 50`,
`tradeable = true`, and `exit_close IS NOT NULL` (i.e. already a clean,
fully-resolved row in the 10-day P&L). This is the same 266-row population
verified by hand against Postgres before this mode was built.

Rule:
  ENTRY: `entry_ask` as already computed in `squeeze_premarket_v3_pnl` --
    reused, not re-pulled.
  EXIT: the last NBBO bid timestamped < 16:00:00 ET, found in the
    15:55:00-16:00:00 ET window via `/v3/stock/history/quote`. If no usable
    bid surfaces in that window, the row is written with exit fields NULL
    and the reason is logged -- same fail-closed discipline as the entry-ask
    logic, never a guess.
  SLIPPAGE: identical mechanism/constant to PNL_BACKTEST_MODE's `PNL_SLIPPAGE`
    (2% per side: entry fill = entry_ask * (1 + slip), exit fill =
    exit_bid * (1 - slip)) -- reused for an apples-to-apples comparison, not
    reinvented.

This needs the same private-network path as `BACKTEST_MODE`/
`PNL_BACKTEST_MODE` -- `/v3/stock/history/quote` is only reachable from
inside Render. This mode must NEVER run on the scheduled trigger -- only via
a manual "Trigger Run" with `SAMEDAY_PNL_BACKTEST_MODE` set in that run's
environment. Do not set it on the job's persistent env vars.
Writes to `squeeze_premarket_v3_sameday_pnl`, a new table of its own -- it
never touches `squeeze_premarket_v3_pnl`, `squeeze_premarket_backtest_results`
(both read-only here), or any FAMILY #2 table.

This is a SECOND LOOK at the same historical population PNL_BACKTEST_MODE
already scored, not a fresh out-of-sample test -- label any result from this
mode EXPLORATORY, never a confirmed finding, until it clears its own
pre-registration.

TRAIL PNL BACKTEST MODE (added 2026-10-03, EXPLORATORY third look -- a THIRD,
structurally different exit question against the SAME historical population
PNL_BACKTEST_MODE and SAMEDAY_PNL_BACKTEST_MODE already scored, NOT a
confirmed result)
----------------------------------------------------------------------------
When the env var `TRAIL_PNL_BACKTEST_MODE` is set (any truthy value),
`main()` branches to `run_trail_pnl_backtest()` BEFORE anything else -- same
isolation as the three modes above, checked after all of them and mutually
exclusive with each. This is deliberately a SEPARATE mode/table -- none of
the other three modes' behavior changes.

PNL_BACKTEST_MODE holds 10 trading sessions; SAMEDAY_PNL_BACKTEST_MODE exits
at a real bid near the close of the SAME day. This mode asks a third
question: instead of a fixed exit time, what does the same entry pay under
an INTRADAY TRAILING STOP -- exit the first time price drops some percentage
below the running high since entry, simulated on real regular-session
1-minute bars?

Population: `load_trail_pnl_queue()` uses the IDENTICAL join/filter as
`load_sameday_pnl_queue()` (squeeze_premarket_v3_pnl joined to
squeeze_premarket_backtest_results on premarket_turnover <=
SAMEDAY_TURNOVER_CAP, tradeable = true, exit_close IS NOT NULL) -- the SAME
266-row population already scored twice. This is now a THIRD dependent look
at that exact set; any result is EXPLORATORY, not confirmed, same as the
mode above.

Data: day-0 REGULAR-SESSION (09:30:00-16:00:00 ET, never premarket)
1-minute OHLC bars via the already-deployed `/v3/stock/history/ohlc`
endpoint (`fetch_regular_session_bars()`) -- the same TRADES-only route
scan_symbol()/scan_symbol_backtest() already use, just pointed at the
regular session.

Rule:
  ENTRY: `entry_ask` as already computed in `squeeze_premarket_v3_pnl` --
    reused, not re-pulled, same convention as SAMEDAY_PNL_BACKTEST_MODE.
  TRIGGER: for each 1-minute bar in chronological order, the running peak
    is updated to the bar's HIGH, then the bar's LOW is checked against
    peak * (1 - trail_pct). The first bar whose low breaches that level
    triggers the stop. Three thresholds are tested in the SAME run, never
    just one: trail_pct in {10%, 15%, 20%} (`TRAIL_PCTS`), looped and
    written separately, tagged by `trail_pct_used` -- report all three,
    never cherry-pick the best after the fact.
  STOP FILL (the standing rule-0 honesty requirement -- "never score a fill
    you could not have gotten"): once triggered, the simulated fill is the
    CLOSE of the triggering bar, NOT the stop level itself. A real
    trailing-stop order fills at the next available price after the
    trigger, which can gap below the stop level on an illiquid microcap --
    the bar close is one extra bar of slippage beyond the stop level, a more
    honest stand-in than assuming a fill exactly at the stop price. This is
    still an approximation: the true NBBO bid at the exact trigger instant
    would be more rigorous, but pulling tick-level quote data for every bar
    of every trade is a much bigger pull than this pass -- left for a future,
    more rigorous look if any threshold here looks promising.
  NO-TRIGGER FILL: if no bar ever breaches the trailing level through
    16:00:00 ET, exit at the real NBBO bid near the close -- the SAME
    15:55:00-16:00:00 ET bid search SAMEDAY_PNL_BACKTEST_MODE already built
    (`fetch_sameday_exit_bid()`), reused/imported here, not rewritten.
  SLIPPAGE: identical mechanism/constant to PNL_BACKTEST_MODE's
    `PNL_SLIPPAGE` (2% per side), reused for an apples-to-apples comparison
    against the other two exit variants.

This needs the same private-network path as the other backtest modes --
`/v3/stock/history/ohlc` and `/v3/stock/history/quote` are only reachable
from inside Render. This mode must NEVER run on the scheduled trigger --
only via a manual "Trigger Run" with `TRAIL_PNL_BACKTEST_MODE` set in that
run's environment. Do not set it on the job's persistent env vars.
Writes to `squeeze_premarket_v3_trail_pnl`, a new table of its own -- it
never touches `squeeze_premarket_v3_pnl`, `squeeze_premarket_v3_sameday_pnl`,
or `squeeze_premarket_backtest_results` (all read-only here), or any
FAMILY #2 table.

This is a THIRD LOOK at the same historical population the other two PNL
modes already scored, not a fresh out-of-sample test -- label any result
from this mode EXPLORATORY, never a confirmed finding, until it clears its
own pre-registration. Report ALL THREE thresholds, not just whichever one
comes out positive.

OPTIONS PNL BACKTEST MODE (added 2026-10-03, EXPLORATORY new-instrument test
-- CALL OPTIONS instead of shares on the exact same signal, NOT a reslice of
the share-trade results)
----------------------------------------------------------------------------
When the env var `OPTIONS_PNL_BACKTEST_MODE` is set (any truthy value),
`main()` branches to `run_options_pnl_backtest()` BEFORE anything else --
same isolation as the four modes above, checked after all of them and
mutually exclusive with each. This is a SEPARATE mode/table -- none of the
other four modes' behavior changes.

The share-trade version of this signal (PNL_BACKTEST_MODE's 10-session hold)
returned a real but too-small +4%/year on a $500 account. This mode asks
whether buying the CALL OPTION on the same entry instead of the stock,
closed out the same day, produces a meaningfully bigger (but still honest)
number via leverage -- for the subset of names that actually have listed
options. This is genuinely new data (option quotes), not another cut of the
share-trade population.

Population: the frozen 37-row query (verified by hand against Postgres
before this mode was built):
    SELECT r.symbol, r.event_date, r.entry_ask
    FROM squeeze_premarket_v3_pnl r
    JOIN squeeze_premarket_backtest_results b
        ON r.symbol = b.symbol AND r.event_date = b.event_date
    WHERE r.tradeable AND r.exit_close IS NOT NULL
      AND b.premarket_turnover <= 50 AND b.premarket_move < 0.25
      AND b.premarket_turnover < 1
`entry_ask` here is the STOCK's entry ask, reused as-is (never re-pulled) --
only as the reference price used to pick the nearest-to-money strike below,
same "reuse, don't re-pull" discipline as every other PNL mode in this file.

Step 1 -- OPTIONS AVAILABILITY (verified per-row, not assumed): for every
(symbol, event_date) pair, `fetch_option_expirations()` calls the
already-deployed `/v3/option/list/expirations` endpoint (the SAME call
`probe_has_options()` makes for the live scanner) and caches the result per
symbol for the run. That endpoint returns ThetaData's FULL historical list
of expirations ever available for that root, not just currently-live ones,
so it is safe to use for a past `event_date`. A symbol with an empty/no-data
result is recorded with `fill_status = 'no_options'` and excluded from any
fill attempt -- expect many microcaps to land here; report the exact count,
don't guess it.

Step 2 -- ENTRY/EXIT (real-fill, same-day):
  EXPIRY: the nearest expiration in that symbol's list that is >= event_date
    + 7 calendar days (`OPTIONS_MIN_DTE_DAYS`) -- avoids 0-7 DTE, too close
    to the event, likely terrible liquidity/theta decay on a microcap. If no
    expiration clears that floor, `fill_status = 'no_expiry'`.
  ENTRY: at 09:30:00+ ET on event_date, the full call chain for that expiry
    is pulled via `/v3/option/history/quote` (strike='*', right='call',
    09:30:00-09:31:00 ET window -- same window convention as the live
    scanner's `fetch_entry_ask()`), and the strike whose quoted ASK is
    closest to the stock's own `entry_ask` (reused from the 37-row query) is
    selected. Buy at that contract's real ASK -- never a mark/mid. No usable
    quote in the window -> `fill_status = 'no_entry_quote'`.
  EXIT: the SAME contract's last real NBBO BID timestamped strictly before
    16:00:00 ET, searched in the 15:55:00-16:00:00 ET window (re-pulling the
    same endpoint for that expiry and filtering client-side for the chosen
    strike, since a specific-strike query string is not an established
    convention anywhere else in this file) -- the identical window/fail-
    closed discipline as `fetch_sameday_exit_bid()`. No usable bid ->
    `fill_status = 'no_exit_quote'`.
  RETURN: `raw_return = exit_bid / entry_ask - 1`, computed on the OPTION
    price itself. This is inherently leveraged vs. the underlying -- that IS
    the point of this test -- so no separate leverage multiplier is applied.
  SLIPPAGE / FILL CONVENTION: unlike every other PNL mode in this file, NO
    additional slippage constant (e.g. `PNL_SLIPPAGE`) is layered on top
    here. Options markets are already wider than stock, and entry ASK ->
    exit BID already charges the real bid/ask spread crossed at both ends --
    applying a flat 2% on top of that would double-charge the same cost.
    State this plainly in every result: `raw_return` here is already a
    real-fill number, not a before-slippage one.

`fill_status` values (also the resume key): 'no_options', 'no_expiry', and
'filled' are terminal -- never retried. 'probe_error', 'no_entry_quote', and
'no_exit_quote' are treated as still-pending (same "NULL exit_bid is
unresolved" resume convention as SAMEDAY_PNL_BACKTEST_MODE) so the next
Trigger Run automatically re-checks them.

This needs the same private-network path as every other backtest mode in
this file -- `/v3/option/list/expirations` and `/v3/option/history/quote`
are only reachable from inside Render. This mode must NEVER run on the
scheduled trigger -- only via a manual "Trigger Run" with
`OPTIONS_PNL_BACKTEST_MODE` set in that run's environment. Do not set it on
the job's persistent env vars.
Writes to `squeeze_premarket_v3_options_pnl`, a new table of its own -- it
never touches `squeeze_premarket_v3_pnl`, `squeeze_premarket_backtest_results`
(both read-only here), any of the other three PNL-mode tables, FAMILY #2, or
PREREG.md.

This is a NEW-INSTRUMENT test (option quotes, not a reslice of the share
trades) on a likely THIN population after the options-availability filter --
label any result EXPLORATORY, and if the filtered population lands in
single digits, report that honestly rather than stretching it into a claim.
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
# EXPLORATORY same-day-exit second look, see module docstring "SAMEDAY PNL
# BACKTEST MODE" section -- any truthy value. Must never be set on the
# scheduled trigger's persistent env, only on a manual "Trigger Run". Checked
# separately from (and after) BACKTEST_MODE/PNL_BACKTEST_MODE; never runs in
# the same invocation as either.
SAMEDAY_PNL_BACKTEST_MODE = os.getenv("SAMEDAY_PNL_BACKTEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
# EXPLORATORY intraday-trailing-stop third look, see module docstring "TRAIL
# PNL BACKTEST MODE" section -- any truthy value. Must never be set on the
# scheduled trigger's persistent env, only on a manual "Trigger Run". Checked
# separately from (and after) BACKTEST_MODE/PNL_BACKTEST_MODE/
# SAMEDAY_PNL_BACKTEST_MODE; never runs in the same invocation as any of them.
TRAIL_PNL_BACKTEST_MODE = os.getenv("TRAIL_PNL_BACKTEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
# EXPLORATORY new-instrument test (call options instead of shares), see
# module docstring "OPTIONS PNL BACKTEST MODE" section -- any truthy value.
# Must never be set on the scheduled trigger's persistent env, only on a
# manual "Trigger Run". Checked separately from (and after) BACKTEST_MODE/
# PNL_BACKTEST_MODE/SAMEDAY_PNL_BACKTEST_MODE/TRAIL_PNL_BACKTEST_MODE; never
# runs in the same invocation as any of them.
OPTIONS_PNL_BACKTEST_MODE = os.getenv("OPTIONS_PNL_BACKTEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")

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
    """(symbol, event_date) pairs that already have a FULLY resolved row in
    squeeze_premarket_v3_pnl -- same resume convention as
    load_resolved_backtest_keys() above, except a row with a NULL
    exit_close (entry or exit leg failed -- including every row written by
    the pre-fix last_trade/created column bug below) is treated as still
    unresolved, so the next Trigger Run automatically re-checks it and
    overwrites it via insert_pnl_result's ON CONFLICT DO UPDATE. No manual
    cleanup/DELETE needed."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT symbol, event_date FROM squeeze_premarket_v3_pnl "
            "WHERE exit_close IS NOT NULL"
        )
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
    (exit_close, exit_date, reason).

    The proxy's /v3/stock/history/eod rows carry no 'date' or 'timestamp'
    column -- the session date lives in 'last_trade' (falling back to
    'created'), the same convention already used by
    backend/ember/legacy/spike.py's _load_theta_history() against this same
    endpoint. Rows are also not guaranteed to arrive in chronological order,
    so they're sorted here before counting sessions, same as spike.py does."""
    start = event_date + timedelta(days=1)
    end = event_date + timedelta(days=PNL_EXIT_WINDOW_DAYS)
    url = f"{THETA_BASE}/v3/stock/history/eod"
    params = {"symbol": symbol, "start_date": start.isoformat(), "end_date": end.isoformat()}
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, f"proxy error fetching EOD closes: {detail}"
    if status == "no_data" or not rows:
        return None, None, "no EOD data in the 30 calendar-day window after event_date"

    sessions = []
    for row in rows:
        raw_ts = row.get("last_trade") or row.get("created") or ""
        try:
            session_date = date.fromisoformat(str(raw_ts)[:10])
            close = float(row["close"])
        except (KeyError, ValueError, TypeError):
            continue
        sessions.append((session_date, close))
    sessions.sort(key=lambda pair: pair[0])

    if len(sessions) < PNL_EXIT_SESSIONS:
        return None, None, (
            f"only {len(sessions)} usable trading sessions in the 30 calendar-day "
            f"window, need {PNL_EXIT_SESSIONS}"
        )
    exit_date, exit_close = sessions[PNL_EXIT_SESSIONS - 1]
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


# ===========================================================================
# SAMEDAY PNL BACKTEST MODE -- EXPLORATORY second look (same historical
# population PNL_BACKTEST_MODE already scored, different exit question), see
# module docstring "SAMEDAY PNL BACKTEST MODE" section. Everything below this
# line is only ever reached when `SAMEDAY_PNL_BACKTEST_MODE` is set; it must
# never run on the scheduled trigger, and never touches PNL_BACKTEST_MODE's
# or BACKTEST_MODE's tables.
# ===========================================================================

# FIX 1 (data quality): identical corrupt-share-count guard as the live
# scanner's `research/live_velocity_screen.py` (`if t > 50: continue #
# corrupt share count`), applied here as a ceiling on
# squeeze_premarket_backtest_results.premarket_turnover when building the
# queue.
SAMEDAY_TURNOVER_CAP = 50
# FIX 2 (real exit fill): last NBBO bid timestamped strictly before
# 16:00:00 ET, searched in this trailing window -- never the trade-print
# close, never a mark.
SAMEDAY_EXIT_WINDOW_START = "15:55:00"
SAMEDAY_EXIT_WINDOW_END = "16:00:00"
SAMEDAY_MARKET_CLOSE = clock_time(16, 0, 0)


def ensure_sameday_pnl_tables(conn) -> None:
    """CREATE TABLE IF NOT EXISTS for the sameday-PNL-backtest-only table.
    Called ONLY from run_sameday_pnl_backtest() -- a new table of its own,
    nothing overwritten in squeeze_premarket_v3_pnl or
    squeeze_premarket_backtest_results."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_premarket_v3_sameday_pnl (
                symbol TEXT,
                event_date DATE,
                entry_ask DOUBLE PRECISION,
                exit_bid DOUBLE PRECISION,
                exit_quote_time TIMESTAMPTZ,
                raw_return DOUBLE PRECISION,
                return_after_slippage DOUBLE PRECISION,
                checked_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, event_date)
            )
        """)
    conn.commit()


def load_sameday_pnl_queue(conn) -> list:
    """(symbol, event_date, entry_ask) for every signal in the clean 266-row
    population: already-resolved squeeze_premarket_v3_pnl rows (entry_ask
    reused as-is, never re-pulled) joined to squeeze_premarket_backtest_results
    on (symbol, event_date), kept only where premarket_turnover <=
    SAMEDAY_TURNOVER_CAP (FIX 1), tradeable = true, and exit_close IS NOT
    NULL -- i.e. the same join/filter verified by hand against Postgres
    before this mode was built."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.symbol, p.event_date, p.entry_ask
            FROM squeeze_premarket_v3_pnl p
            JOIN squeeze_premarket_backtest_results b
                ON b.symbol = p.symbol AND b.event_date = p.event_date
            WHERE b.premarket_turnover <= %s
              AND p.tradeable = true
              AND p.exit_close IS NOT NULL
            ORDER BY p.event_date, p.symbol
        """, [SAMEDAY_TURNOVER_CAP])
        return cur.fetchall()


def load_resolved_sameday_keys(conn) -> set:
    """(symbol, event_date) pairs that already have a FULLY resolved row in
    squeeze_premarket_v3_sameday_pnl -- same resume convention as
    load_resolved_pnl_keys(): a row with a NULL exit_bid (no usable bid found
    in the 15:55:00-16:00:00 ET window) is treated as still unresolved, so
    the next Trigger Run automatically re-checks it."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT symbol, event_date FROM squeeze_premarket_v3_sameday_pnl "
            "WHERE exit_bid IS NOT NULL"
        )
        return {(sym, ed) for sym, ed in cur.fetchall()}


def insert_sameday_pnl_result(conn, symbol: str, event_date: date, entry_ask,
                               exit_bid, exit_quote_time, raw_return,
                               return_after_slippage) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO squeeze_premarket_v3_sameday_pnl
                (symbol, event_date, entry_ask, exit_bid, exit_quote_time,
                 raw_return, return_after_slippage)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, event_date) DO UPDATE SET
                entry_ask = EXCLUDED.entry_ask,
                exit_bid = EXCLUDED.exit_bid,
                exit_quote_time = EXCLUDED.exit_quote_time,
                raw_return = EXCLUDED.raw_return,
                return_after_slippage = EXCLUDED.return_after_slippage,
                checked_at = now()
        """, [symbol, event_date, entry_ask, exit_bid, exit_quote_time,
              raw_return, return_after_slippage])
    conn.commit()


def fetch_sameday_exit_bid(symbol: str, event_date: date):
    """FIX 2: the last NBBO bid timestamped strictly before 16:00:00 ET,
    searched in the 15:55:00-16:00:00 ET window via the same
    `/v3/stock/history/quote` endpoint used for the entry leg -- never the
    trade-print close, never a mid/mark. Returns (bid, quote_time, reason):
    bid/quote_time are the LAST usable quote in that window (rows are sorted
    by timestamp here first, same defensive convention as
    fetch_tenth_session_close()'s EOD sort, since the proxy does not
    guarantee row order). If no usable bid surfaces, bid/quote_time are None
    and `reason` explains why -- the caller leaves the row's exit fields
    NULL rather than guessing, same fail-closed discipline as
    fetch_entry_ask()."""
    url = f"{THETA_BASE}/v3/stock/history/quote"
    params = {
        "symbol": symbol,
        "date": event_date.isoformat(),
        "start_time": SAMEDAY_EXIT_WINDOW_START,
        "end_time": SAMEDAY_EXIT_WINDOW_END,
        "interval": "1s",
        "venue": "utp_cta",
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


def scan_sameday_pair(symbol: str, event_date: date, entry_ask: float):
    """Stage-1 worker: pure HTTP, no DB access -- same discipline as
    scan_pnl_pair(). entry_ask is already resolved (reused from
    squeeze_premarket_v3_pnl), so only the exit leg is pulled here. Returns
    (status, payload):
      'exit_missing' - no usable bid in the 15:55:00-16:00:00 ET window
         (payload carries the reason only; the row is still written, exit
         fields left NULL).
      'ok'           - exit resolved (payload carries exit_bid/quote_time/
         raw_return/return_after_slippage).
    """
    exit_bid, exit_quote_time, exit_reason = fetch_sameday_exit_bid(symbol, event_date)
    if exit_bid is None:
        return "exit_missing", {"reason": exit_reason}

    raw_return = exit_bid / entry_ask - 1
    # Same slippage mechanism/constant as PNL_BACKTEST_MODE's PNL_SLIPPAGE
    # (2% per side) -- reused, not reinvented, for an apples-to-apples
    # comparison against the 10-day exit.
    return_after_slip = exit_bid * (1 - PNL_SLIPPAGE) / (entry_ask * (1 + PNL_SLIPPAGE)) - 1
    return "ok", dict(
        exit_bid=exit_bid, exit_quote_time=exit_quote_time,
        raw_return=raw_return, return_after_slippage=return_after_slip,
    )


def run_sameday_pnl_backtest() -> int:
    """RESUMABLE, same convention as run_pnl_backtest(): skips (symbol,
    event_date) pairs already written to squeeze_premarket_v3_sameday_pnl."""
    run_start = time.monotonic()
    log.info("=== squeeze premarket cron SAMEDAY PNL BACKTEST MODE (PREREG #3 "
              "/ V3, EXPLORATORY second look, same-day real-bid exit, not a "
              "confirmed result) ===")

    conn = get_db_connection()
    try:
        ensure_tables(conn)
        ensure_sameday_pnl_tables(conn)

        full_queue = load_sameday_pnl_queue(conn)
        if not full_queue:
            log.warning(
                "no clean rows found (premarket_turnover <= %s, tradeable, "
                "exit_close resolved) joining squeeze_premarket_v3_pnl to "
                "squeeze_premarket_backtest_results - nothing to score. Run "
                "PNL_BACKTEST_MODE first.", SAMEDAY_TURNOVER_CAP,
            )
            return 0

        resolved = load_resolved_sameday_keys(conn)
        queue = [row for row in full_queue if (row[0], row[1]) not in resolved]
        already_resolved = len(full_queue) - len(queue)
        log.info(
            "SAMEDAY PNL queue size: %d clean rows (turnover<=%s, tradeable, "
            "exit_close resolved), %d already resolved (skipped), %d pending "
            "(resume mode)",
            len(full_queue), SAMEDAY_TURNOVER_CAP, already_resolved, len(queue),
        )
        if not queue:
            log.info("nothing pending - every clean row already has a sameday result.")
            return 0

        checked = 0
        exit_missing = 0
        resolved_ok = 0
        by_key = {(sym, ed): ask for sym, ed, ask in queue}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(scan_sameday_pair, sym, ed, ask): (sym, ed)
                for sym, ed, ask in queue
            }
            for fut in as_completed(futures):
                sym, ed = futures[fut]
                entry_ask = by_key[(sym, ed)]
                try:
                    status, payload = fut.result()
                except Exception as exc:  # noqa: BLE001 - one worker must never kill the run
                    status, payload = "exit_missing", {"reason": repr(exc)}
                checked += 1

                if status == "exit_missing":
                    exit_missing += 1
                    log.warning("no usable same-day exit bid for %s %s: %s",
                                sym, ed, payload["reason"])
                    insert_sameday_pnl_result(conn, sym, ed, entry_ask, None, None, None, None)
                    continue

                resolved_ok += 1
                insert_sameday_pnl_result(
                    conn, sym, ed, entry_ask, payload["exit_bid"],
                    payload["exit_quote_time"], payload["raw_return"],
                    payload["return_after_slippage"],
                )

        elapsed = time.monotonic() - run_start
        log.info(
            "=== SAMEDAY PNL BACKTEST DONE: full_queue=%d already_resolved=%d "
            "pending=%d checked=%d exit_missing=%d resolved_ok=%d "
            "wall_clock=%.1fs ===",
            len(full_queue), already_resolved, len(queue), checked,
            exit_missing, resolved_ok, elapsed,
        )
        log.info(
            "Fill convention: ENTRY = entry_ask reused as-is from "
            "squeeze_premarket_v3_pnl; EXIT = last real NBBO bid timestamped "
            "< 16:00:00 ET, found in the 15:55:00-16:00:00 ET window (never "
            "the close print, never a mark); 2%% slippage per side "
            "(entry*(1+slip), exit*(1-slip)), same constant as "
            "PNL_BACKTEST_MODE. EXPLORATORY SECOND LOOK at the same "
            "historical population PNL_BACKTEST_MODE already scored -- query "
            "squeeze_premarket_v3_sameday_pnl for the primary metric and "
            "robustness report, label it exploratory, not confirmed."
        )
        return 0
    finally:
        conn.close()


# ===========================================================================
# TRAIL PNL BACKTEST MODE -- EXPLORATORY third look (same 266-row historical
# population PNL_BACKTEST_MODE and SAMEDAY_PNL_BACKTEST_MODE already scored,
# a third, structurally different exit question), see module docstring
# "TRAIL PNL BACKTEST MODE" section. Everything below this line is only ever
# reached when `TRAIL_PNL_BACKTEST_MODE` is set; it must never run on the
# scheduled trigger, and never touches PNL_BACKTEST_MODE's,
# SAMEDAY_PNL_BACKTEST_MODE's, or BACKTEST_MODE's tables.
# ===========================================================================

TRAIL_SESSION_START = "09:30:00"  # regular session, NOT premarket
TRAIL_SESSION_END = "16:00:00"
# Trailing-stop drawdown thresholds from the running peak since entry,
# tested in the SAME run per the task spec -- report all three separately,
# never cherry-pick the best one after the fact.
TRAIL_PCTS = (0.10, 0.15, 0.20)


def ensure_trail_pnl_tables(conn) -> None:
    """CREATE TABLE IF NOT EXISTS for the trailing-stop-backtest-only table.
    Called ONLY from run_trail_pnl_backtest() -- a new table of its own,
    nothing overwritten in squeeze_premarket_v3_pnl,
    squeeze_premarket_v3_sameday_pnl, or squeeze_premarket_backtest_results."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_premarket_v3_trail_pnl (
                symbol TEXT,
                event_date DATE,
                entry_ask DOUBLE PRECISION,
                trail_pct_used DOUBLE PRECISION,
                stop_triggered BOOLEAN,
                exit_price DOUBLE PRECISION,
                exit_time TIMESTAMPTZ,
                exit_reason TEXT,
                raw_return DOUBLE PRECISION,
                return_after_slippage DOUBLE PRECISION,
                checked_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, event_date, trail_pct_used)
            )
        """)
    conn.commit()


def load_trail_pnl_queue(conn) -> list:
    """(symbol, event_date, entry_ask) for every signal in the SAME clean
    266-row population SAMEDAY_PNL_BACKTEST_MODE already scored --
    load_sameday_pnl_queue()'s identical join/filter
    (squeeze_premarket_v3_pnl joined to squeeze_premarket_backtest_results on
    premarket_turnover <= SAMEDAY_TURNOVER_CAP, tradeable = true, exit_close
    IS NOT NULL), copied here rather than called so this mode stays fully
    self-contained and never has to change if the sameday query ever did --
    verified identical to load_sameday_pnl_queue() by inspection, not
    re-derived, for an apples-to-apples population across all three exit
    variants."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.symbol, p.event_date, p.entry_ask
            FROM squeeze_premarket_v3_pnl p
            JOIN squeeze_premarket_backtest_results b
                ON b.symbol = p.symbol AND b.event_date = p.event_date
            WHERE b.premarket_turnover <= %s
              AND p.tradeable = true
              AND p.exit_close IS NOT NULL
            ORDER BY p.event_date, p.symbol
        """, [SAMEDAY_TURNOVER_CAP])
        return cur.fetchall()


def load_resolved_trail_pairs(conn) -> set:
    """(symbol, event_date) pairs where EVERY TRAIL_PCTS threshold already
    has a FULLY resolved row (non-NULL exit_price) -- same resume
    convention as load_resolved_pnl_keys()/load_resolved_sameday_keys(),
    extended to "all three thresholds done" since this mode writes one row
    per threshold per pair. A pair with any threshold still NULL (no bars at
    all, or no triggered stop AND no usable EOD bid) is treated as still
    unresolved, so the next Trigger Run automatically re-checks the whole
    pair (and re-pulls bars once, re-simulating all three thresholds)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT symbol, event_date FROM squeeze_premarket_v3_trail_pnl
            WHERE exit_price IS NOT NULL
            GROUP BY symbol, event_date
            HAVING count(*) = %s
        """, [len(TRAIL_PCTS)])
        return {(sym, ed) for sym, ed in cur.fetchall()}


def insert_trail_pnl_result(conn, symbol: str, event_date: date, entry_ask,
                             trail_pct_used: float, stop_triggered, exit_price,
                             exit_time, exit_reason, raw_return,
                             return_after_slippage) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO squeeze_premarket_v3_trail_pnl
                (symbol, event_date, entry_ask, trail_pct_used, stop_triggered,
                 exit_price, exit_time, exit_reason, raw_return,
                 return_after_slippage)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, event_date, trail_pct_used) DO UPDATE SET
                entry_ask = EXCLUDED.entry_ask,
                stop_triggered = EXCLUDED.stop_triggered,
                exit_price = EXCLUDED.exit_price,
                exit_time = EXCLUDED.exit_time,
                exit_reason = EXCLUDED.exit_reason,
                raw_return = EXCLUDED.raw_return,
                return_after_slippage = EXCLUDED.return_after_slippage,
                checked_at = now()
        """, [symbol, event_date, entry_ask, trail_pct_used, stop_triggered,
              exit_price, exit_time, exit_reason, raw_return, return_after_slippage])
    conn.commit()


def fetch_regular_session_bars(symbol: str, event_date: date):
    """Day-0 regular-session (09:30:00-16:00:00 ET, NOT premarket) 1-minute
    OHLC bars via the already-deployed `/v3/stock/history/ohlc` endpoint --
    the SAME TRADES-only route scan_symbol()/scan_symbol_backtest() already
    use, pointed at the regular session instead of the premarket window.
    Returns (status, bars, detail): bars is a list of
    (timestamp, high, low, close) tuples sorted chronologically (the proxy
    does not guarantee row order -- same defensive sort as
    fetch_tenth_session_close()/fetch_sameday_exit_bid()). status/detail
    follow the same 'error'/'no_data'/'ok' convention as every other
    fetch_* helper in this file."""
    url = f"{THETA_BASE}/v3/stock/history/ohlc"
    params = {
        "symbol": symbol,
        "date": event_date.isoformat(),
        "start_time": TRAIL_SESSION_START,
        "end_time": TRAIL_SESSION_END,
        "interval": "1m",
        "venue": "utp_cta",
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
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
        except (KeyError, ValueError, TypeError):
            continue
        if high > 0 and low > 0 and close > 0:
            bars.append((ts, high, low, close))
    if not bars:
        return "no_data", None, None
    bars.sort(key=lambda bar: bar[0])
    return "ok", bars, None


def simulate_trailing_stop(entry_ask: float, bars: list, trail_pct: float):
    """Core trailing-stop simulation for ONE threshold over ONE day's bars.

    Tracks the running high (peak) since entry, starting at entry_ask itself
    (the real fill price, not the first bar's own open). For each bar in
    chronological order: the peak is updated to the bar's HIGH first, then
    the bar's LOW is checked against peak * (1 - trail_pct) -- the frozen
    trigger rule ("exit the first time price drops X% below the running
    high"). Using the bar's own high to update the peak before checking its
    own low is itself an approximation forced by 1-minute OHLC granularity
    (true intra-bar sequencing of the high vs. the low is unknown) -- noted
    here, not hidden.

    FILL CONVENTION (the task's explicit honesty requirement, standing rule
    0 "never score a fill you could not have gotten"): once the stop
    triggers, the simulated fill is the CLOSE of the triggering bar, NOT the
    stop level itself. A real trailing-stop order fills at the next
    available price after the trigger, which can gap below the stop level on
    an illiquid microcap -- the bar close is one bar of slippage beyond the
    stop level, a more honest (if still imperfect) stand-in than assuming a
    fill exactly at the stop price. The true NBBO bid at the exact trigger
    instant would be more rigorous still; that requires tick-level quote
    data for every bar of every trade, a much bigger pull, and is left for a
    future pass if this threshold looks promising.

    Returns (triggered: bool, fill_price: float|None, fill_time: datetime|None).
    """
    peak = entry_ask
    for ts, high, low, close in bars:
        peak = max(peak, high)
        stop_level = peak * (1 - trail_pct)
        if low <= stop_level:
            return True, close, ts
    return False, None, None


def scan_trail_pair(symbol: str, event_date: date, entry_ask: float):
    """Stage-1 worker: pure HTTP, no DB access -- same discipline as
    scan_pnl_pair()/scan_sameday_pair(). Pulls the day's regular-session
    bars ONCE and reuses them for all three TRAIL_PCTS thresholds (never
    three separate HTTP pulls per symbol/day). The EOD-bid fallback
    (fetch_sameday_exit_bid(), reused as-is from SAMEDAY_PNL_BACKTEST_MODE,
    NOT rewritten) is also pulled at most ONCE per symbol/day, only if at
    least one threshold needs it.

    Returns (status, payload):
      'error'    - bars fetch failed after retries (payload carries the
         detail dict only; no row is written, so the pair is retried next
         run -- same convention as every other mode's 'error' branch).
      'no_data'  - no usable regular-session bars at all (payload is None;
         every threshold gets a row with exit_reason='no_data').
      'ok'       - bars resolved (payload is a dict keyed by trail_pct of
         [triggered, exit_price, exit_time, exit_reason]).
    """
    bars_status, bars, detail = fetch_regular_session_bars(symbol, event_date)
    if bars_status == "error":
        return "error", detail
    if bars_status == "no_data":
        return "no_data", None

    per_threshold = {}
    need_eod_bid = False
    for pct in TRAIL_PCTS:
        triggered, fill_price, fill_time = simulate_trailing_stop(entry_ask, bars, pct)
        per_threshold[pct] = [triggered, fill_price, fill_time, "stop" if triggered else None]
        if not triggered:
            need_eod_bid = True

    if need_eod_bid:
        # Reused as-is from SAMEDAY_PNL_BACKTEST_MODE -- NOT rewritten. Same
        # 15:55:00-16:00:00 ET real-NBBO-bid search, never the close print,
        # never a mark.
        eod_bid, eod_time, eod_reason = fetch_sameday_exit_bid(symbol, event_date)
        for pct in TRAIL_PCTS:
            if per_threshold[pct][0]:  # already triggered on a stop
                continue
            if eod_bid is not None:
                per_threshold[pct][1] = eod_bid
                per_threshold[pct][2] = eod_time
                per_threshold[pct][3] = "eod_bid"
            else:
                log.warning(
                    "no usable EOD exit bid for %s %s trail_pct=%.0f%%: %s",
                    symbol, event_date, pct * 100, eod_reason,
                )
                per_threshold[pct][3] = "no_data"

    return "ok", per_threshold


def run_trail_pnl_backtest() -> int:
    """RESUMABLE, same convention as run_pnl_backtest()/
    run_sameday_pnl_backtest(): skips (symbol, event_date) pairs where every
    TRAIL_PCTS threshold already has a non-NULL exit_price."""
    run_start = time.monotonic()
    log.info("=== squeeze premarket cron TRAIL PNL BACKTEST MODE (PREREG #3 "
              "/ V3, EXPLORATORY third look, intraday trailing-stop exit, "
              "not a confirmed result) ===")

    conn = get_db_connection()
    try:
        ensure_tables(conn)
        ensure_trail_pnl_tables(conn)

        full_queue = load_trail_pnl_queue(conn)
        if not full_queue:
            log.warning(
                "no clean rows found (premarket_turnover <= %s, tradeable, "
                "exit_close resolved) joining squeeze_premarket_v3_pnl to "
                "squeeze_premarket_backtest_results - nothing to score. Run "
                "PNL_BACKTEST_MODE first.", SAMEDAY_TURNOVER_CAP,
            )
            return 0

        resolved_pairs = load_resolved_trail_pairs(conn)
        queue = [row for row in full_queue if (row[0], row[1]) not in resolved_pairs]
        already_resolved = len(full_queue) - len(queue)
        log.info(
            "TRAIL PNL queue size: %d clean rows (turnover<=%s, tradeable, "
            "exit_close resolved) x %d thresholds, %d pairs already fully "
            "resolved (skipped), %d pairs pending (resume mode)",
            len(full_queue), SAMEDAY_TURNOVER_CAP, len(TRAIL_PCTS),
            already_resolved, len(queue),
        )
        if not queue:
            log.info("nothing pending - every clean row already has a trail result for all thresholds.")
            return 0

        checked = 0
        errors = 0
        no_bars = 0
        by_threshold = {pct: {"stop": 0, "eod_bid": 0, "no_data": 0} for pct in TRAIL_PCTS}
        by_key = {(sym, ed): ask for sym, ed, ask in queue}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(scan_trail_pair, sym, ed, ask): (sym, ed)
                for sym, ed, ask in queue
            }
            for fut in as_completed(futures):
                sym, ed = futures[fut]
                entry_ask = by_key[(sym, ed)]
                try:
                    status, payload = fut.result()
                except Exception as exc:  # noqa: BLE001 - one worker must never kill the run
                    status, payload = "error", {
                        "http_status": None,
                        "exception_type": type(exc).__name__,
                        "exception_message": repr(exc),
                    }
                checked += 1

                if status == "error":
                    errors += 1
                    log.error(
                        "trail backtest FAILED symbol=%s event_date=%s "
                        "detail=%s -- not written, will retry next run",
                        sym, ed, payload,
                    )
                    continue

                if status == "no_data":
                    no_bars += 1
                    log.warning(
                        "no usable regular-session bars for %s %s - writing "
                        "no_data rows for all %d thresholds",
                        sym, ed, len(TRAIL_PCTS),
                    )
                    for pct in TRAIL_PCTS:
                        by_threshold[pct]["no_data"] += 1
                        insert_trail_pnl_result(
                            conn, sym, ed, entry_ask, pct, False, None, None,
                            "no_data", None, None,
                        )
                    continue

                for pct, (triggered, exit_price, exit_time, exit_reason) in payload.items():
                    if exit_price is None:
                        by_threshold[pct]["no_data"] += 1
                        raw_return = None
                        return_after_slip = None
                    else:
                        by_threshold[pct][exit_reason] += 1
                        raw_return = exit_price / entry_ask - 1
                        # Same slippage mechanism/constant as PNL_BACKTEST_MODE's
                        # PNL_SLIPPAGE (2% per side) -- reused, not reinvented,
                        # for an apples-to-apples comparison against the other
                        # two exit variants.
                        return_after_slip = (
                            exit_price * (1 - PNL_SLIPPAGE)
                            / (entry_ask * (1 + PNL_SLIPPAGE)) - 1
                        )
                    insert_trail_pnl_result(
                        conn, sym, ed, entry_ask, pct, triggered, exit_price,
                        exit_time, exit_reason, raw_return, return_after_slip,
                    )

        elapsed = time.monotonic() - run_start
        log.info(
            "=== TRAIL PNL BACKTEST DONE: full_queue=%d thresholds=%d "
            "already_resolved_pairs=%d pending_pairs=%d checked=%d errors=%d "
            "no_bars=%d wall_clock=%.1fs ===",
            len(full_queue), len(TRAIL_PCTS), already_resolved, len(queue),
            checked, errors, no_bars, elapsed,
        )
        for pct in TRAIL_PCTS:
            counts = by_threshold[pct]
            log.info(
                "  trail_pct=%.0f%%: stop=%d eod_bid=%d no_data=%d (this run "
                "only -- query squeeze_premarket_v3_trail_pnl for the full "
                "table/primary metric)",
                pct * 100, counts["stop"], counts["eod_bid"], counts["no_data"],
            )
        log.info(
            "Fill convention: ENTRY = entry_ask reused as-is from "
            "squeeze_premarket_v3_pnl; STOP TRIGGER = 1-minute regular-"
            "session (09:30-16:00 ET) bar LOW crosses peak*(1-trail_pct); "
            "STOP FILL = the CLOSE of the triggering bar (one bar of "
            "slippage beyond the stop level, never the stop price itself -- "
            "standing rule 0, a real stop can fill worse on an illiquid "
            "microcap); NO-TRIGGER FILL = real NBBO bid in the 15:55:00-"
            "16:00:00 ET window (fetch_sameday_exit_bid(), reused from "
            "SAMEDAY_PNL_BACKTEST_MODE); 2%% slippage per side on top of "
            "either fill, same PNL_SLIPPAGE constant as the other two "
            "variants. EXPLORATORY THIRD LOOK at the same 266-row historical "
            "population PNL_BACKTEST_MODE and SAMEDAY_PNL_BACKTEST_MODE "
            "already scored -- report ALL THREE thresholds, never just the "
            "best one, and label this exploratory, not confirmed."
        )
        return 0
    finally:
        conn.close()


# ===========================================================================
# OPTIONS PNL BACKTEST MODE -- EXPLORATORY new-instrument test (call options
# instead of shares on the exact same signal), see module docstring "OPTIONS
# PNL BACKTEST MODE" section. Everything below this line is only ever reached
# when `OPTIONS_PNL_BACKTEST_MODE` is set; it must never run on the scheduled
# trigger, and never touches any other mode's tables, FAMILY #2, or
# PREREG.md.
# ===========================================================================

# Avoid 0-7 DTE at entry -- too close to the event, likely terrible
# liquidity/theta decay on a microcap. See module docstring.
OPTIONS_MIN_DTE_DAYS = 7
# Same entry/exit window conventions as the live scanner's fetch_entry_ask()
# and SAMEDAY_PNL_BACKTEST_MODE's fetch_sameday_exit_bid() -- reused, not
# reinvented.
OPTIONS_ENTRY_WINDOW_START = "09:30:00"
OPTIONS_ENTRY_WINDOW_END = ENTRY_QUOTE_WINDOW_END  # "09:31:00"
OPTIONS_EXIT_WINDOW_START = SAMEDAY_EXIT_WINDOW_START  # "15:55:00"
OPTIONS_EXIT_WINDOW_END = SAMEDAY_EXIT_WINDOW_END      # "16:00:00"

# fill_status values that are terminal (never retried on the next Trigger
# Run) vs. still-pending (same "NULL exit_bid is unresolved" resume
# convention as SAMEDAY_PNL_BACKTEST_MODE).
OPTIONS_TERMINAL_STATUSES = {"no_options", "no_expiry", "filled"}


def ensure_options_pnl_tables(conn) -> None:
    """CREATE TABLE IF NOT EXISTS for the options-PNL-backtest-only table.
    Called ONLY from run_options_pnl_backtest() -- a new table of its own,
    nothing overwritten in squeeze_premarket_v3_pnl,
    squeeze_premarket_backtest_results, or any other PNL mode's table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_premarket_v3_options_pnl (
                symbol TEXT,
                event_date DATE,
                underlying_entry_ask DOUBLE PRECISION,
                option_symbol TEXT,
                strike DOUBLE PRECISION,
                expiration DATE,
                entry_ask DOUBLE PRECISION,
                entry_quote_time TIMESTAMPTZ,
                exit_bid DOUBLE PRECISION,
                exit_quote_time TIMESTAMPTZ,
                raw_return DOUBLE PRECISION,
                fill_status TEXT,
                checked_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, event_date)
            )
        """)
    conn.commit()


def load_options_pnl_queue(conn) -> list:
    """(symbol, event_date, entry_ask) for the frozen 37-row population --
    the EXACT query given in the task spec, verified by hand against
    Postgres before this mode was built. `entry_ask` is the STOCK's entry
    ask from squeeze_premarket_v3_pnl, reused as-is (never re-pulled) --
    only used below as the reference price for picking the nearest-to-money
    strike."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.symbol, r.event_date, r.entry_ask
            FROM squeeze_premarket_v3_pnl r
            JOIN squeeze_premarket_backtest_results b
                ON r.symbol = b.symbol AND r.event_date = b.event_date
            WHERE r.tradeable AND r.exit_close IS NOT NULL
              AND b.premarket_turnover <= 50 AND b.premarket_move < 0.25
              AND b.premarket_turnover < 1
            ORDER BY r.event_date, r.symbol
        """)
        return cur.fetchall()


def load_resolved_options_keys(conn) -> set:
    """(symbol, event_date) pairs whose fill_status is terminal -- see
    OPTIONS_TERMINAL_STATUSES. Rows stuck on a transient status
    ('probe_error', 'no_entry_quote', 'no_exit_quote') are treated as still
    unresolved, so the next Trigger Run automatically re-checks them -- same
    resume convention as every other PNL mode in this file."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT symbol, event_date FROM squeeze_premarket_v3_options_pnl "
            "WHERE fill_status = ANY(%s)",
            [list(OPTIONS_TERMINAL_STATUSES)],
        )
        return {(sym, ed) for sym, ed in cur.fetchall()}


def insert_options_pnl_result(conn, symbol: str, event_date: date, underlying_entry_ask,
                               option_symbol, strike, expiration, entry_ask,
                               entry_quote_time, exit_bid, exit_quote_time,
                               raw_return, fill_status: str) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO squeeze_premarket_v3_options_pnl
                (symbol, event_date, underlying_entry_ask, option_symbol, strike,
                 expiration, entry_ask, entry_quote_time, exit_bid,
                 exit_quote_time, raw_return, fill_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, event_date) DO UPDATE SET
                underlying_entry_ask = EXCLUDED.underlying_entry_ask,
                option_symbol = EXCLUDED.option_symbol,
                strike = EXCLUDED.strike,
                expiration = EXCLUDED.expiration,
                entry_ask = EXCLUDED.entry_ask,
                entry_quote_time = EXCLUDED.entry_quote_time,
                exit_bid = EXCLUDED.exit_bid,
                exit_quote_time = EXCLUDED.exit_quote_time,
                raw_return = EXCLUDED.raw_return,
                fill_status = EXCLUDED.fill_status,
                checked_at = now()
        """, [symbol, event_date, underlying_entry_ask, option_symbol, strike,
              expiration, entry_ask, entry_quote_time, exit_bid, exit_quote_time,
              raw_return, fill_status])
    conn.commit()


def fetch_option_expirations(symbol: str):
    """FULL historical list of expirations ThetaData has for this root --
    the SAME call probe_has_options() already makes, see module docstring
    'Step 1' section. Safe to use for a past event_date because the endpoint
    is not scoped to "currently listed" -- it returns everything ThetaData
    has ever had data for. Returns (expirations, status): status is 'ok'
    (expirations is a sorted list of date objects, possibly empty if parsing
    failed), 'no_data' (a definite negative -- no options ever), or 'error'
    (unanswered question, not a negative)."""
    url = f"{THETA_BASE}/v3/option/list/expirations"
    rows, status, _detail = _fetch_csv(url, {"symbol": symbol})
    if status == "error":
        return [], "error"
    if status == "no_data" or not rows:
        return [], "no_data"
    out = []
    for row in rows:
        try:
            out.append(date.fromisoformat(str(row["expiration"])[:10]))
        except (KeyError, ValueError, TypeError):
            continue
    if not out:
        return [], "no_data"
    return sorted(out), "ok"


def pick_nearest_expiration(expirations: list, event_date: date):
    """Nearest expiration >= event_date + OPTIONS_MIN_DTE_DAYS calendar days
    -- see module docstring 'EXPIRY' rule. None if nothing clears the
    floor."""
    floor = event_date + timedelta(days=OPTIONS_MIN_DTE_DAYS)
    candidates = [exp for exp in expirations if exp >= floor]
    return min(candidates) if candidates else None


def fetch_entry_call(symbol: str, event_date: date, expiration: date,
                      underlying_entry_ask: float):
    """ENTRY leg -- see module docstring 'ENTRY' rule. Pulls the full call
    chain for `expiration` in the 09:30:00-09:31:00 ET window via
    /v3/option/history/quote (strike='*'), keeps the FIRST usable ask at/
    after 09:30:00 ET per strike, and picks the strike closest to
    `underlying_entry_ask`. Returns (strike, ask, quote_time, reason): on
    failure strike/ask/quote_time are None and `reason` explains why -- same
    fail-closed discipline as fetch_entry_ask(), never a guess."""
    url = f"{THETA_BASE}/v3/option/history/quote"
    params = {
        "symbol": symbol,
        "expiration": expiration.isoformat(),
        "strike": "*",
        "right": "call",
        "interval": "1s",
        "date": event_date.isoformat(),
        "start_time": OPTIONS_ENTRY_WINDOW_START,
        "end_time": OPTIONS_ENTRY_WINDOW_END,
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, None, f"proxy error fetching entry option chain: {detail}"
    if status == "no_data" or not rows:
        return None, None, None, "no option quote data for the 09:30:00-09:31:00 ET window"

    by_strike: dict[float, tuple] = {}
    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            strike = float(row["strike"])
            ask = float(row["ask"])
        except (KeyError, ValueError, TypeError):
            continue
        if ts.time() < ENTRY_QUOTE_OPEN:
            continue
        if not (ask and ask > 0):
            continue
        existing = by_strike.get(strike)
        if existing is None or ts < existing[0]:
            by_strike[strike] = (ts, ask)

    if not by_strike:
        return None, None, None, (
            "no call strike with a usable ask at/after 09:30:00 ET within "
            "the 09:30:00-09:31:00 ET window"
        )

    nearest_strike = min(by_strike, key=lambda s: abs(s - underlying_entry_ask))
    quote_time, ask = by_strike[nearest_strike]
    return nearest_strike, ask, quote_time, None


def fetch_exit_call_bid(symbol: str, event_date: date, expiration: date, strike: float):
    """EXIT leg -- see module docstring 'EXIT' rule. Re-pulls the full call
    chain for `expiration` in the 15:55:00-16:00:00 ET window and filters
    client-side for `strike` (a specific-strike query string is not an
    established convention anywhere else in this file, so the wildcard chain
    is reused and filtered instead of guessing a format). Returns
    (bid, quote_time, reason) -- same fail-closed discipline as
    fetch_sameday_exit_bid()."""
    url = f"{THETA_BASE}/v3/option/history/quote"
    params = {
        "symbol": symbol,
        "expiration": expiration.isoformat(),
        "strike": "*",
        "right": "call",
        "interval": "1s",
        "date": event_date.isoformat(),
        "start_time": OPTIONS_EXIT_WINDOW_START,
        "end_time": OPTIONS_EXIT_WINDOW_END,
    }
    rows, status, detail = _fetch_csv(url, params)
    if status == "error":
        return None, None, f"proxy error fetching exit option chain: {detail}"
    if status == "no_data" or not rows:
        return None, None, "no option quote data for the 15:55:00-16:00:00 ET window"

    parsed = []
    for row in rows:
        try:
            row_strike = float(row["strike"])
            ts = datetime.fromisoformat(row["timestamp"])
            bid = float(row["bid"])
        except (KeyError, ValueError, TypeError):
            continue
        if abs(row_strike - strike) > 1e-6:
            continue
        if ts.time() >= SAMEDAY_MARKET_CLOSE:
            continue
        if bid and bid > 0:
            parsed.append((ts, bid))

    if not parsed:
        return None, None, (
            "no quote with a usable bid for the chosen strike strictly before "
            "16:00:00 ET within the 15:55:00-16:00:00 ET window"
        )
    parsed.sort(key=lambda pair: pair[0])
    exit_time, exit_bid = parsed[-1]
    return exit_bid, exit_time, None


def scan_options_pair(symbol: str, event_date: date, underlying_entry_ask: float):
    """Stage-1 worker: pure HTTP, no DB access -- same discipline as every
    other scan_*_pair() in this file. Returns (fill_status, payload); see
    module docstring 'fill_status values' section for the full state
    machine."""
    expirations, probe_status = fetch_option_expirations(symbol)
    if probe_status == "error":
        return "probe_error", {"reason": "proxy error fetching expirations list"}
    if probe_status == "no_data" or not expirations:
        return "no_options", {}

    expiration = pick_nearest_expiration(expirations, event_date)
    if expiration is None:
        return "no_expiry", {}

    strike, entry_ask, entry_quote_time, entry_reason = fetch_entry_call(
        symbol, event_date, expiration, underlying_entry_ask)
    if entry_ask is None:
        return "no_entry_quote", {"expiration": expiration, "reason": entry_reason}

    exit_bid, exit_quote_time, exit_reason = fetch_exit_call_bid(
        symbol, event_date, expiration, strike)
    if exit_bid is None:
        return "no_exit_quote", {
            "expiration": expiration, "strike": strike, "entry_ask": entry_ask,
            "entry_quote_time": entry_quote_time, "reason": exit_reason,
        }

    # No separate slippage multiplier -- entry ASK -> exit BID already
    # charges the real bid/ask spread crossed at both ends. See module
    # docstring 'SLIPPAGE / FILL CONVENTION' section.
    raw_return = exit_bid / entry_ask - 1
    option_symbol = f"{symbol}_{expiration.isoformat()}_C{strike:g}"
    return "filled", dict(
        option_symbol=option_symbol, strike=strike, expiration=expiration,
        entry_ask=entry_ask, entry_quote_time=entry_quote_time,
        exit_bid=exit_bid, exit_quote_time=exit_quote_time, raw_return=raw_return,
    )


def run_options_pnl_backtest() -> int:
    """RESUMABLE, same convention as every other PNL mode in this file:
    skips (symbol, event_date) pairs already resolved to a terminal
    fill_status in squeeze_premarket_v3_options_pnl."""
    run_start = time.monotonic()
    log.info("=== squeeze premarket cron OPTIONS PNL BACKTEST MODE "
              "(EXPLORATORY new-instrument test, call options instead of "
              "shares on the frozen 37-row signal, not a confirmed result) ===")

    conn = get_db_connection()
    try:
        ensure_tables(conn)
        ensure_options_pnl_tables(conn)

        full_queue = load_options_pnl_queue(conn)
        if not full_queue:
            log.warning(
                "no rows found for the frozen 37-row options population "
                "query joining squeeze_premarket_v3_pnl to "
                "squeeze_premarket_backtest_results - nothing to score. Run "
                "PNL_BACKTEST_MODE first."
            )
            return 0

        resolved = load_resolved_options_keys(conn)
        queue = [row for row in full_queue if (row[0], row[1]) not in resolved]
        already_resolved = len(full_queue) - len(queue)
        log.info(
            "OPTIONS PNL queue size: %d rows (frozen 37-row population), %d "
            "already resolved (skipped), %d pending (resume mode)",
            len(full_queue), already_resolved, len(queue),
        )
        if not queue:
            log.info("nothing pending - every row already has a terminal options result.")
            return 0

        checked = 0
        by_status = {
            "filled": 0, "no_options": 0, "no_expiry": 0,
            "no_entry_quote": 0, "no_exit_quote": 0, "probe_error": 0,
        }
        by_key = {(sym, ed): ask for sym, ed, ask in queue}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(scan_options_pair, sym, ed, ask): (sym, ed)
                for sym, ed, ask in queue
            }
            for fut in as_completed(futures):
                sym, ed = futures[fut]
                underlying_entry_ask = by_key[(sym, ed)]
                try:
                    status, payload = fut.result()
                except Exception as exc:  # noqa: BLE001 - one worker must never kill the run
                    status, payload = "probe_error", {"reason": repr(exc)}
                checked += 1
                by_status[status] = by_status.get(status, 0) + 1

                if status in ("no_options", "no_expiry", "probe_error"):
                    if status != "probe_error":
                        log.info("%s for %s %s", status, sym, ed)
                    else:
                        log.warning("options probe error for %s %s: %s",
                                    sym, ed, payload.get("reason"))
                    insert_options_pnl_result(
                        conn, sym, ed, underlying_entry_ask, None, None, None,
                        None, None, None, None, None, status,
                    )
                    continue

                if status == "no_entry_quote":
                    log.warning("no usable entry call quote for %s %s (expiry %s): %s",
                                sym, ed, payload.get("expiration"), payload["reason"])
                    insert_options_pnl_result(
                        conn, sym, ed, underlying_entry_ask, None, None,
                        payload.get("expiration"), None, None, None, None,
                        None, status,
                    )
                    continue

                if status == "no_exit_quote":
                    log.warning("no usable exit call bid for %s %s (expiry %s, strike %s): %s",
                                sym, ed, payload.get("expiration"), payload.get("strike"),
                                payload["reason"])
                    insert_options_pnl_result(
                        conn, sym, ed, underlying_entry_ask, None, payload.get("strike"),
                        payload.get("expiration"), payload.get("entry_ask"),
                        payload.get("entry_quote_time"), None, None, None, status,
                    )
                    continue

                # status == "filled"
                insert_options_pnl_result(
                    conn, sym, ed, underlying_entry_ask, payload["option_symbol"],
                    payload["strike"], payload["expiration"], payload["entry_ask"],
                    payload["entry_quote_time"], payload["exit_bid"],
                    payload["exit_quote_time"], payload["raw_return"], status,
                )

        elapsed = time.monotonic() - run_start
        log.info(
            "=== OPTIONS PNL BACKTEST DONE: full_queue=%d already_resolved=%d "
            "pending=%d checked=%d filled=%d no_options=%d no_expiry=%d "
            "no_entry_quote=%d no_exit_quote=%d probe_error=%d wall_clock=%.1fs ===",
            len(full_queue), already_resolved, len(queue), checked,
            by_status["filled"], by_status["no_options"], by_status["no_expiry"],
            by_status["no_entry_quote"], by_status["no_exit_quote"],
            by_status["probe_error"], elapsed,
        )
        log.info(
            "Fill convention: ENTRY = real ASK of the call strike nearest the "
            "stock's own entry_ask (reused from squeeze_premarket_v3_pnl), "
            "nearest expiry >= event_date+7 calendar days, bought in the "
            "09:30:00-09:31:00 ET window; EXIT = same contract's real BID in "
            "the 15:55:00-16:00:00 ET window, same day; raw_return = "
            "exit_bid/entry_ask - 1 on the OPTION price itself (inherently "
            "leveraged vs. the underlying -- no separate leverage multiplier "
            "applied); NO additional slippage constant layered on top -- ask-"
            "to-bid already charges the real spread crossed at both ends. "
            "EXPLORATORY new-instrument test (option quotes, not a reslice of "
            "the share trades) -- query squeeze_premarket_v3_options_pnl "
            "grouped by fill_status for the options-availability count, and "
            "WHERE fill_status = 'filled' for the primary metric and "
            "robustness report (remove best symbol, remove best month). "
            "Label any result exploratory, not confirmed, and report the "
            "population size honestly if it lands in single digits."
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
    if SAMEDAY_PNL_BACKTEST_MODE:
        return run_sameday_pnl_backtest()
    if TRAIL_PNL_BACKTEST_MODE:
        return run_trail_pnl_backtest()
    if OPTIONS_PNL_BACKTEST_MODE:
        return run_options_pnl_backtest()
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
