"""EMBER - laptop driver for the TradingVolatility 2:1 risk/reward scanner
book (tools/ember.py's own candidate scanner, run separately every 30 min by
the `EMBER` scheduled task; this file is the SECOND stage of that same task,
appended to run right after the scan - see EMBER.cmd). Reads the newest tick
of tools/ember_ledger.jsonl (another agent owns ember.py and its ledger
schema - this file never writes it, only reads, defensively) and decides
whether to enter a new position or close an open one.

Modeled EXACTLY on ../call_diag/run_diag.py's architecture: .env loading +
flags, order_state.json, an append-only intents.log written by the agent (one
line before every order attempt), an order agent invoked as `claude -p
EMBER-PROMPT.md` with the Robinhood MCP only when a mode is due,
EMBER_ARMED/EMBER_DRY_RUN env flags gating the order-tool allowlist, the same
notify/halt conventions (a manual EMBER_HALTED override in .env - there is no
automatic per-leg halt here, unlike call_diag, because EMBER has no fixed
leg config to halt; see "Deviations" below), the same 2026 NYSE holiday
calendar for trading-session math, and the SAME sequenced-single-leg order
path: Robinhood REJECTS multi-leg tickets on this agentic account (verified
live 2026-09-10 on call_diag/IWM) - every structure with two legs (vertical,
pcs) is placed as the long leg first at the ASK, then the short leg at the
BID, and the long is unwound (sold back) immediately if the short is
refused/unfilled. `entry_leg_action()`/`exit_leg_action()` below are
call_diag's own functions with one added parameter (`has_short`) so a
single-leg structure (single/call - just a long buy, no short) reuses the
exact same state machine instead of a second one.

Deviations from call_diag/run_diag.py's architecture (declared, same spirit
as that file's own "Deviations from the task's spec" section in DEPLOY.md):
1. call_diag runs a fixed daily SAFETY -> RECONCILE -> ENTRY -> EXIT
   progression with ENTRY/EXIT each resolving "done" once per day. EMBER's
   scanner produces a fresh candidate list roughly every 30 minutes all day,
   and open positions must be checked against a live target/stop on every
   single tick, not just once - so EMBER has only two modes: RECONCILE
   (first tick of the day only, exactly like call_diag's) and TRADE (every
   tick thereafter, re-evaluating entries AND exits fresh each time; a no-op
   tick - nothing open, nothing eligible to enter - never calls the agent,
   the same "pure Python no-op" convention call_diag's SAFETY/EXIT use).
2. call_diag's RECONCILE only ever LOGS a mismatch, never corrects
   order_state.json. EMBER's spec explicitly calls for the opposite on one
   point: "drop state for vanished positions, log orphans" - so EMBER's
   RECONCILE closes (in Python's state, not the broker) any position this
   bot thought was open that the broker no longer shows, logging why, and
   logs (never touches) any live option position not in this bot's own book.
3. There is no per-leg halt here (call_diag's SAFETY mode auto-halts one
   leg_id when it catches an expiry-day escape) - EMBER has no fixed leg
   config to halt; EMBER_HALTED is a manual, global, .env-only switch, same
   as call_diag's DIAG_HALTED with no order_state-side companion.
4. Fills are logged to ember_fills.jsonl (JSONL, one line per leg-fill
   event, keyed by the scanner's own ticket key) instead of call_diag's
   ledger.csv (one row per CLOSED position) - the task spec asks for a fill
   log, not a closed-trade P&L ledger; the agent appends these lines
   directly (same as it writes order_state.json/intents.log/diag-log.txt),
   there is no Python-side CSV derivation step.

Every tick 08:30-16:40 CT weekdays (the scanner's own EMBER schtask window is
08:35-16:35 CT) this script decides RECONCILE or TRADE, keyed by trade date
in order_state.json:

  RECONCILE   First tick of the day. One agent run: pull
              get_option_positions and reconcile against order_state.json's
              own idea of what's open - drop (close, in our own state only)
              any position we show open that the broker doesn't, log any
              live position not in our book. Also caches get_portfolio's
              total_value and buying_power for TRADE's ENVELOPE check
              (mirrors call_diag's RECONCILE ENVELOPE step exactly).
  TRADE       Every tick after RECONCILE, 08:30-16:40 CT. Python computes,
              BEFORE the agent is ever invoked: (a) every currently OPEN
              position, handed to the agent so it can check today's live
              underlying quote against that position's own target/stop
              (Python cannot fetch a live quote - same split as call_diag's
              EXIT/ITM-guard), plus every DTE/time-stop exit reason Python
              CAN compute without a live quote (time_stop, short_dte,
              single_dte - see positions_due_for_exit_pure()); (b) a ranked,
              capacity- and ENVELOPE-checked list of at most
              EMBER_MAX_NEW_PER_TICK new entry candidates off the scanner's
              newest ledger tick (see select_entry_candidates()). If nothing
              is open AND nothing is entry-eligible, this is a pure no-op -
              no agent call, exactly like call_diag's SAFETY/EXIT no-ops.

Usage:
  python run_ember.py                        # scheduled tick
  python run_ember.py --at 2026-09-16T09:35 [--dry-run]
  python run_ember.py --once TRADE --dry-run [--force]
                                             # run exactly ONE tick of MODE now,
                                             # bypassing the clock. Calls the REAL
                                             # agent (no stub) -- --dry-run forces
                                             # EMBER_DRY_RUN=1 for this run regardless
                                             # of .env, so it can never place an
                                             # order.
  python run_ember.py --unit-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import ember_lock

CT = ZoneInfo("America/Chicago")
CODE_DIR = Path(__file__).resolve().parent
HERE = Path(os.getenv("EMBER_TVBOOK_DATA_DIR", str(CODE_DIR))).expanduser().resolve()
HERE.mkdir(parents=True, exist_ok=True)
ORDER_STATE = HERE / "order_state.json"
LOG_TXT = HERE / "ember-log.txt"
RUN_OUTPUT = HERE / "run-output.log"
INTENTS_LOG = HERE / "intents.log"
PROMPT_MD = CODE_DIR / "EMBER-PROMPT.md"
ENV_FILE = HERE / ".env"
LOCK_FILE = HERE / "run_ember.lock"     # Fix 3: overlap guard, see ember_lock.py

# The scanner (tools/ember.py) and its ledger/fills live in ironforge-data,
# a different repo/drive from this driver -- absolute paths, never relative.
IRONFORGE_TOOLS = Path(os.getenv("EMBER_TVBOOK_DATA_DIR", str(HERE)))
EMBER_LEDGER = IRONFORGE_TOOLS / "ember_ledger.jsonl"    # scanner's own output -- READ ONLY,
                                                          # another agent owns ember.py/this file
EMBER_FILLS = IRONFORGE_TOOLS / "ember_fills.jsonl"      # this bot's own fill log (write)

ACCOUNT = "570892331"            # Robinhood "Agentic" account, limited_margin + option_level_3,
                                  # same account call_diag/daily_cal/divhike all share -- never
                                  # point this bot at any other account.
FEE_PER_CONTRACT_DEFAULT = 0.04  # verified live on SPY 2-leg orders (daily_cal); reused as the
                                  # safe default until EMBER's own review_option_order previews
                                  # say otherwise, same convention as call_diag's own default.

# ---- clock (CT) ---------------------------------------------------------
WINDOW_START_CT = time(8, 30)
WINDOW_END_CT = time(16, 40)     # covers the EMBER schtask's own 08:35-16:35 CT run window
ENTRY_START_CT = time(9, 5)      # entries only 09:05-15:30 CT (task spec)
ENTRY_END_CT = time(15, 30)
EXIT_REPRICE_AFTER_MIN = 2       # unfilled after 2 minutes -> reprice once (call_diag's own
                                  # EXIT convention -- reprice_exit() below is unchanged)

RE_ENTRY_COOLDOWN_SESSIONS = 5   # no re-entry of a ticker closed within this many sessions

ONCE_MODES = ("RECONCILE", "TRADE")
MODE_STATE_KEY = {"RECONCILE": "reconcile"}   # TRADE has no daily "done" flag -- see module docstring

STRUCTURES_WITH_SHORT = ("vertical", "pcs")
KNOWN_STRUCTURES = ("single", "vertical", "pcs", "call")


# ---- NYSE holiday calendar, hardcoded for 2026 -- IDENTICAL table to -------
# call_diag/run_diag.py's own (copied, not imported, to keep this driver
# self-contained the same way call_diag is) -- session-count math (re-entry
# cooldown, time-stop) needs a real calendar, not a naive weekday walk.
NYSE_HOLIDAYS_2026 = frozenset({
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Washington's Birthday
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day (observed, 7/4 is a Saturday)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
})


def is_trading_day(d: date) -> bool:
    """Weekday AND not a hardcoded 2026 NYSE holiday. Dates outside 2026 get
    weekday-only treatment (documented limitation, same as call_diag's)."""
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS_2026


def trading_sessions_between(d1: date, d2: date) -> int:
    """Number of trading sessions strictly AFTER d1 through d2 inclusive --
    0 if d2 <= d1. Used for both the re-entry cooldown (sessions since a
    ticker closed) and the time-stop (sessions held since entry)."""
    if d2 <= d1:
        return 0
    n = 0
    d = d1 + timedelta(days=1)
    while d <= d2:
        if is_trading_day(d):
            n += 1
        d += timedelta(days=1)
    return n


def dte(expiry: date, today: date) -> int:
    return (expiry - today).days


# ---------------------------------------------------------------- config
@dataclass
class Cfg:
    armed: bool = False
    dry_run: bool = True
    halted_env: bool = False        # EMBER_HALTED in .env -- Leron's manual override, global.
                                     # No order_state-side companion (see module docstring #3).
    claude_bin: str = "claude"
    fee_per_contract: float = FEE_PER_CONTRACT_DEFAULT
    max_cost_usd: float = 200.0     # EMBER_MAX_COST_USD
    max_open: int = 2               # EMBER_MAX_OPEN -- total simultaneously open positions,
                                     # across every ticker (not per-ticker)
    max_new_per_tick: int = 1       # EMBER_MAX_NEW_PER_TICK
    time_stop_sessions: int = 7     # EMBER_TIME_STOP_SESSIONS
    close_dte: int = 3              # EMBER_CLOSE_DTE -- any short leg closes at/below this DTE
    max_ledger_age_min: int = 60    # EMBER_MAX_LEDGER_AGE_MIN -- a ledger tick older than this
                                     # (vs now) is STALE and never traded. The scanner runs every
                                     # 30 min right before this executor; if it crashed, the newest
                                     # rows are from an earlier cycle (or yesterday) and their
                                     # stop/target geometry no longer matches the tape. Raised from
                                     # 45 (Fix 4b, 2026-09-16) -- two missed scanner ticks (60 min)
                                     # should still trade on the last good tick, not just one.
    envelope_pct: float = 45.0      # EMBER_ENVELOPE_PCT -- fixed percentage share of the
                                     # Agentic account's live total_value (2026-09-10 ADR
                                     # buying-power-envelopes; see envelopes/envelopes.json).
                                     # Usage is measured from this bot's OWN reconciled
                                     # positions book (their stored cost_usd), never free
                                     # buying power -- same convention as call_diag.


def load_cfg(env_file: Path = ENV_FILE) -> Cfg:
    """Missing .env => every default is the safe one (unarmed, dry-run)."""
    env: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    env = {**env, **{k: v for k, v in os.environ.items() if k.startswith("EMBER_")}}
    return Cfg(
        armed=env.get("EMBER_ARMED", "0") == "1",
        dry_run=env.get("EMBER_DRY_RUN", "1") != "0",
        halted_env=env.get("EMBER_HALTED", "0") == "1",
        claude_bin=env.get("EMBER_CLAUDE_BIN", "claude"),
        fee_per_contract=float(env.get("EMBER_FEE_PER_CONTRACT", str(FEE_PER_CONTRACT_DEFAULT))),
        max_cost_usd=float(env.get("EMBER_MAX_COST_USD", "200")),
        max_open=int(env.get("EMBER_MAX_OPEN", "2")),
        max_new_per_tick=int(env.get("EMBER_MAX_NEW_PER_TICK", "1")),
        time_stop_sessions=int(env.get("EMBER_TIME_STOP_SESSIONS", "7")),
        close_dte=int(env.get("EMBER_CLOSE_DTE", "3")),
        envelope_pct=float(env.get("EMBER_ENVELOPE_PCT", "45")),
        max_ledger_age_min=int(env.get("EMBER_MAX_LEDGER_AGE_MIN", "60")),
    )


# ---------------------------------------------------------------- state I/O
def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(p: Path, d: dict) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)


# ---------------------------------------------------------------- ledger parsing (pure)
def load_ledger_rows(path: Path | None = None) -> list[dict]:
    """Defensive: malformed JSON lines are skipped, never crash the tick
    (same skip-not-guess convention as call_diag's parse_legs()). This file
    NEVER writes tools/ember_ledger.jsonl -- another agent owns ember.py and
    its schema, which is still evolving; every field access on a row is a
    defensive .get(). `path` defaults to the CURRENT module-level
    EMBER_LEDGER, looked up at call time (not bound at import time) so tests
    can monkeypatch the module attribute and have it take effect."""
    if path is None:
        path = EMBER_LEDGER
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def newest_tick_rows(rows: list[dict]) -> list[dict]:
    """Every row sharing the max scan_time across `rows`. A row with no
    scan_time at all (an older/partial ember.py schema generation -- the
    real ledger has several mixed in) is never eligible to be "the newest
    tick" and is excluded here, not guessed into now."""
    timed = [r for r in rows if r.get("scan_time")]
    if not timed:
        return []
    max_t = max(r["scan_time"] for r in timed)
    return [r for r in timed if r["scan_time"] == max_t]


def fresh_tick_rows(rows: list[dict], now: datetime, max_age_min: int) -> tuple[list[dict], str | None]:
    """Pure: keep `rows` only if their (shared) scan_time is within
    `max_age_min` of `now`; otherwise return ([], reason). A scan_time that
    will not parse is treated as stale, never guessed fresh. A naive
    scan_time is read in `now`'s own timezone (ember.py writes CT-local
    naive ISO strings)."""
    if not rows:
        return [], None
    raw = rows[0].get("scan_time")
    try:
        st = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return [], f"ledger scan_time {raw!r} unparseable -> treated as stale"
    if st.tzinfo is None and now.tzinfo is not None:
        st = st.replace(tzinfo=now.tzinfo)
    elif st.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=st.tzinfo)
    age_min = (now - st).total_seconds() / 60.0
    if age_min > max_age_min:
        return [], f"ledger newest tick {raw} is {age_min:.0f} min old (> {max_age_min}) -> STALE, no entries"
    return rows, None


# ---------------------------------------------------------------- row field helpers (pure)
def chosen_opt_rr(row: dict) -> float | None:
    """The chosen structure's own option R:R field. single/call: opt_rr_7d
    (rr strategy) or call_rr_7d (bounce strategy), whichever is present;
    vertical: vert_rr; pcs: pcs_rr_stop. None (never guessed) for any other
    or missing structure."""
    structure = row.get("structure")
    if structure in ("single", "call"):
        v = row.get("opt_rr_7d")
        return v if v is not None else row.get("call_rr_7d")
    if structure == "vertical":
        return row.get("vert_rr")
    if structure == "pcs":
        return row.get("pcs_rr_stop")
    return None


def structure_cost_usd(row: dict) -> float | None:
    """Dollar cost of the chosen structure: debit*100 for single/vertical/
    call (already computed that way by ember.py's own cost_usd/call_cost_usd
    fields), or width*100 for pcs (the credit spread's own collateral, per
    the task spec -- pcs has no debit, it's a credit)."""
    structure = row.get("structure")
    if structure == "pcs":
        width = row.get("pcs_width")
        return round(width * 100, 2) if width is not None else None
    if structure == "call":
        return row.get("call_cost_usd")
    if structure in ("single", "vertical"):
        return row.get("cost_usd")
    return None


def row_expiry_iso(row: dict) -> str | None:
    """The chosen structure's own expiry. bounce rows carry it as `exp`
    directly; rr rows carry it as `flow_exp` (the option-leg expiry used for
    the options-volume pull, same expiry the structure was priced on) --
    ember.py has no separate top-level `exp` for rr rows as of this build.
    Prefer `exp` if a future ember.py schema adds it uniformly."""
    return row.get("exp") or row.get("flow_exp")


def has_short_leg(structure: str | None) -> bool:
    return structure in STRUCTURES_WITH_SHORT


def ticket_key(row: dict) -> tuple:
    """(ticker, scan_date, dir, strategy) -- ember.py's own NEW-SINCE-LAST-
    SCAN dedupe key (section F of its docstring); reused here as this bot's
    own idempotency key for ref_ids and the fills log."""
    return (row.get("ticker"), row.get("scan_date"), row.get("dir"), row.get("strategy"))


def ticket_id(row: dict) -> str:
    k = ticket_key(row)
    return "_".join(str(x) for x in k)


def schema_version_gap_count(rows: list[dict]) -> int:
    """Fix 7: count of ledger rows missing schema_version entirely, or on an
    older generation (< 2) -- informational only for the per-tick summary,
    never an additional rejection reason (ember.py's own `liquid` field is
    still the only gate)."""
    return sum(1 for r in rows if (r.get("schema_version") or 0) < 2)


# ---------------------------------------------------------------- ENTRY filter (pure)
def entry_row_eligible(row: dict, now: datetime, open_positions: list[dict],
                        closed_log: dict[str, str], cfg: Cfg) -> tuple[bool, str]:
    """Pure: is this scanner row eligible for a NEW entry right now? Checks
    are in the spec's own stated order. Every field access is a defensive
    .get() -- a row missing what it needs is never guessed into eligible."""
    ticker = row.get("ticker")
    if not ticker:
        return False, "missing ticker"
    if "liquid" not in row:
        return False, "schema: no liquid key"   # Fix 4c: older ember.py schema generation, not a liquidity fail
    if row.get("liquid") is not True:
        return False, "not liquid"
    stock_rr = row.get("stock_rr")
    if stock_rr is None or stock_rr < 2.0:
        return False, "stock_rr < 2.0"
    structure = row.get("structure")
    if structure not in KNOWN_STRUCTURES:
        return False, f"unknown structure {structure!r}"
    opt_rr = chosen_opt_rr(row)
    if opt_rr is None or opt_rr < 2.0:
        return False, "option R:R < 2.0"
    cost = structure_cost_usd(row)
    if cost is None or cost <= 0:
        return False, "cost unknown"
    if cost > cfg.max_cost_usd:
        return False, f"cost ${cost:.2f} > cap ${cfg.max_cost_usd:.2f}"
    if any(p.get("ticker") == ticker and p.get("state") == "open" for p in open_positions):
        return False, "already open on this ticker"
    closed_date = closed_log.get(ticker)
    if closed_date:
        sessions = trading_sessions_between(date.fromisoformat(closed_date), now.date())
        if sessions < RE_ENTRY_COOLDOWN_SESSIONS:
            return False, f"re-entry cooldown ({sessions}/{RE_ENTRY_COOLDOWN_SESSIONS} sessions since close)"
    t = now.time()
    if not (ENTRY_START_CT <= t <= ENTRY_END_CT):
        return False, "outside entry window (09:05-15:30 CT)"
    return True, "eligible"


def select_entry_candidates(rows: list[dict], positions: list[dict], closed_log: dict[str, str],
                             now: datetime, cfg: Cfg) -> list[dict]:
    """Every eligible row, ranked by stock_rr descending (spec's own tie-
    break rule) -- capacity/envelope capping happens in tick(), not here,
    since envelope capping needs a running usage total across the ranked
    list (same incremental pattern as call_diag's own ENTRY block)."""
    eligible = [r for r in rows if entry_row_eligible(r, now, positions, closed_log, cfg)[0]]
    eligible.sort(key=lambda r: -(r.get("stock_rr") or 0))
    return eligible


# ---------------------------------------------------------------- per-tick ineligibility summary (Fix 4c, pure)
# entry_row_eligible's reason strings carry row-specific numbers on three of
# them (unknown structure, cost cap, re-entry cooldown) -- bucketed to a
# fixed label here so the per-tick counts are stable/aggregable, not one
# unique bucket per row. Every label always appears in the summary (0 if
# unseen this tick) so an operator can see the full rejection shape at a
# glance, not just the reasons that happened to fire.
REJECTION_REASON_LABELS = (
    "missing ticker", "not liquid", "schema: no liquid key", "stock_rr < 2.0",
    "unknown structure", "option R:R < 2.0", "cost unknown", "cost cap",
    "already open on this ticker", "re-entry cooldown",
    "outside entry window (09:05-15:30 CT)",
)


def _reason_bucket(reason: str) -> str:
    if reason.startswith("unknown structure"):
        return "unknown structure"
    if reason.startswith("cost $") and "> cap" in reason:
        return "cost cap"
    if reason.startswith("re-entry cooldown"):
        return "re-entry cooldown"
    return reason


def ineligibility_summary(rows: list[dict], now: datetime, positions: list[dict],
                           closed_log: dict[str, str], cfg: Cfg) -> dict[str, int]:
    """Pure: fixed-label reason -> count of `rows` that are NOT
    entry_row_eligible right now. Every label in REJECTION_REASON_LABELS is
    present (0 if it never fired); an unrecognized reason string (future
    entry_row_eligible change) is still counted, under its own raw label."""
    counts: dict[str, int] = {label: 0 for label in REJECTION_REASON_LABELS}
    for row in rows:
        ok, reason = entry_row_eligible(row, now, positions, closed_log, cfg)
        if ok:
            continue
        bucket = _reason_bucket(reason)
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def format_ineligibility_summary(counts: dict[str, int]) -> str:
    if not counts:
        return "ineligible: none"
    return "ineligible: " + ", ".join(f"{k}={v}" for k, v in counts.items())


def closed_ticker_log(positions: list[dict]) -> dict[str, str]:
    """ticker -> most recent closed_date across every CLOSED position in the
    book -- the re-entry cooldown's own source of truth."""
    out: dict[str, str] = {}
    for p in positions:
        if p.get("state") != "closed":
            continue
        t = p.get("ticker")
        cd = (p.get("exit") or {}).get("closed_date")
        if not t or not cd:
            continue
        if t not in out or cd > out[t]:
            out[t] = cd
    return out


# ---------------------------------------------------------------- double-buy guard (Fix 5, pure)
# Robinhood's sequenced-single-leg order path (module docstring) means a NEW
# entry is not atomic -- a two-leg structure is a long order, then a short
# order, with real wall-clock time (and a real process) in between. If this
# script dies mid-leg, order_state.json's own `positions` list may not show
# the ticker as "open" yet even though an order is genuinely working at the
# broker. An `in_flight` record persisted BEFORE the agent is invoked closes
# that window: the ticker reads as "already open" (blocking re-selection)
# until a later tick observes a result (agent responded) or RECONCILE runs.
def in_flight_records(order_state: dict) -> dict[str, dict]:
    return order_state.get("in_flight") or {}


def start_in_flight(order_state: dict, ticker: str, structure: str | None,
                     started_at: str, row_scan_time: str | None) -> None:
    order_state.setdefault("in_flight", {})[ticker] = {
        "ticker": ticker, "structure": structure, "started_at": started_at,
        "row_scan_time": row_scan_time,
    }


def clear_in_flight(order_state: dict, ticker: str) -> None:
    order_state.get("in_flight", {}).pop(ticker, None)


def in_flight_as_positions(order_state: dict) -> list[dict]:
    """Synthetic 'open' position stand-ins, one per in-flight ticker, for
    feeding into entry_row_eligible's existing 'already open on this ticker'
    check -- no change needed to that function's own logic/signature."""
    return [{"ticker": t, "state": "open"} for t in in_flight_records(order_state)]


# ---------------------------------------------------------------- EXIT due (pure where possible)
def positions_due_for_exit_pure(positions: list[dict], today: date, cfg: Cfg) -> list[dict]:
    """Every OPEN position due a close for a reason Python CAN compute
    without a live quote: time_stop (sessions held >= cfg.time_stop_sessions),
    short_dte (a structure with a short leg, DTE <= cfg.close_dte), or
    single_dte (a single-leg structure, DTE <= 1). The price target/stop
    check needs a LIVE underlying quote, which Python doesn't have here --
    the agent applies that check itself against EVERY open position handed
    to it in the signal (see build_signal(), mirrors call_diag's own
    ITM-guard split). Returns each due position augmented with
    `exit_reasons`; does not mutate input."""
    due = []
    for p in positions:
        if p.get("state") != "open":
            continue
        reasons = []
        entry_date = p.get("entry_date")
        if entry_date:
            sessions = trading_sessions_between(date.fromisoformat(entry_date), today)
            if sessions >= cfg.time_stop_sessions:
                reasons.append("time_stop")
        exp = p.get("exp")
        structure = p.get("structure")
        if exp:
            d = dte(date.fromisoformat(exp), today)
            if has_short_leg(structure) and d <= cfg.close_dte:
                reasons.append("short_dte")
            if not has_short_leg(structure) and d <= 1:
                reasons.append("single_dte")
        if reasons:
            due.append({**p, "exit_reasons": reasons})
    return due


def price_target_stop_hit(position: dict, spot: float) -> bool:
    """long: spot >= target or spot <= stop. short: mirrored (spot <=
    target or spot >= stop). Missing target/stop/spot never triggers (never
    guessed)."""
    target, stop = position.get("target"), position.get("stop")
    if spot is None or target is None or stop is None:
        return False
    if position.get("dir") == "long":
        return spot >= target or spot <= stop
    if position.get("dir") == "short":
        return spot <= target or spot >= stop
    return False


# ---------------------------------------------------------------- fills (pure fill-price rule)
def long_fill_price(row_ask: float | None, live_ask: float | None) -> tuple[float | None, str]:
    """Long legs fill at the scanner row's own ask, UNLESS the live ask has
    moved -- if the live ask is within 5% above the row's ask, use the live
    ask (the market moved a little since the scan, still worth filling); if
    it's MORE than 5% above, skip the entry (edge has decayed, never chase
    further). A live ask at or below the row's ask always fills at the
    (better) live ask."""
    if row_ask is None or row_ask <= 0:
        return None, "no row ask"
    if live_ask is None or live_ask <= 0:
        return None, "no live ask"
    if live_ask <= row_ask * 1.05:
        return round(live_ask, 2), "ok"
    return None, f"live ask {live_ask} > 5% above row ask {row_ask}"


def buying_power_ok(buying_power: float | None, new_cost_usd: float,
                     buffer_usd: float = 25.0) -> tuple[bool, str]:
    """Live buying power must cover the new position's cost plus a $25
    buffer. buying_power=None (never fetched) always refuses -- same
    never-guess convention as call_diag's collateral_guard_ok()."""
    if buying_power is None:
        return False, "buying_power unknown (no portfolio read this run)"
    if buying_power < new_cost_usd + buffer_usd:
        return False, (f"buying_power ${buying_power:.2f} < cost ${new_cost_usd:.2f} "
                        f"+ ${buffer_usd:.2f} buffer")
    return True, "ok"


# ---------------------------------------------------------------- ENVELOPE check (pure)
# 2026-09-10 ADR buying-power-envelopes, same mechanism call_diag uses: a
# FIXED PERCENTAGE share of the Agentic account's live total_value, usage
# measured from THIS BOT's own reconciled positions book (their stored
# cost_usd -- already the structure's own dollar cost at entry, computed by
# structure_cost_usd() above), never free buying power.
def envelope_usd_from_pct(pct: float, total_value: float) -> float:
    return round((pct / 100.0) * total_value, 2)


def ember_envelope_usage(positions: list[dict]) -> float:
    return round(sum((p.get("cost_usd") or 0.0) for p in positions if p.get("state") == "open"), 2)


def ember_envelope_fit_check(envelope_usd: float, usage_usd: float, needed_usd: float) -> tuple[bool, float]:
    total = round(usage_usd + needed_usd, 2)
    return total <= envelope_usd, total


# ---------------------------------------------------------------- legging state machine (pure)
# Robinhood REJECTS multi-leg orders on this agentic account (verified live
# 2026-09-10, call_diag) -- every two-leg structure (vertical, pcs) is two
# SEQUENCED single-leg orders: BUY the long leg first, wait for it to FILL,
# THEN sell/short the second leg. A single-leg structure (single, call) has
# no short leg at all -- `has_short` selects which state machine applies,
# reusing call_diag's exact decision shape otherwise.
LEG_TERMINAL_BAD_STATES = ("no_fill", "rejected", "cancelled")


def entry_leg_action(long_state: str, short_state: str | None, has_short: bool = True) -> str:
    """Same decision shape as call_diag's entry_leg_action(), generalized
    with `has_short`: a single-leg structure goes straight from a filled
    long to POSITION_OPEN, `short_state` is ignored (pass None)."""
    if long_state == "not_placed":
        return "PLACE_LONG"
    if long_state == "pending":
        return "POLL_LONG"
    if long_state in LEG_TERMINAL_BAD_STATES:
        return "NO_ENTRY"
    if long_state != "filled":
        raise ValueError(f"unknown long_state {long_state!r}")
    if not has_short:
        return "POSITION_OPEN"
    if short_state == "not_placed":
        return "PLACE_SHORT"
    if short_state == "pending":
        return "POLL_SHORT"
    if short_state in LEG_TERMINAL_BAD_STATES:
        return "UNWIND_LONG"
    if short_state == "filled":
        return "POSITION_OPEN"
    if short_state == "unwound":
        return "LEG_UNWOUND"
    raise ValueError(f"unknown short_state {short_state!r}")


def exit_leg_action(short_state: str | None, long_state: str, has_short: bool = True) -> str:
    """Same decision shape as call_diag's exit_leg_action(): the SHORT
    closes FIRST (buy-to-close), then the LONG (sell-to-close). A
    single-leg structure has no short to close first -- pass short_state=None,
    `has_short=False`, and it goes straight to the long."""
    if has_short:
        if short_state == "open":
            return "CLOSE_SHORT"
        if short_state == "closing":
            return "POLL_SHORT_CLOSE"
        if short_state != "closed":
            raise ValueError(f"unknown short_state {short_state!r}")
    if long_state == "open":
        return "CLOSE_LONG"
    if long_state == "closing":
        return "POLL_LONG_CLOSE"
    if long_state == "closed":
        return "DONE"
    raise ValueError(f"unknown long_state {long_state!r}")


def is_half_open_position(position: dict) -> bool:
    """A position is HALF-OPEN when its long leg FILLED but the short leg
    never reached 'filled' while the position itself is still recorded
    'open' -- only meaningful for a two-leg structure (vertical/pcs); a
    single-leg structure can never be half-open (there is no short to be
    missing). Same reference check as call_diag's."""
    if not has_short_leg(position.get("structure")):
        return False
    legs = position.get("legs") or {}
    long_leg = legs.get("long") or {}
    short_leg = legs.get("short") or {}
    return (position.get("state") == "open"
            and long_leg.get("state") == "filled"
            and short_leg.get("state") != "filled")


# ---------------------------------------------------------------- repricing (pure, unchanged from call_diag)
def reprice_entry(mid_debit: float, step: float = 0.05) -> float:
    return round(mid_debit + step, 2)


def reprice_exit(mid_net: float, step: float) -> float:
    return round(mid_net - step, 2)


# ---------------------------------------------------------------- RECONCILE (pure reference)
def reconcile_positions(known_positions: list[dict], live_open_keys: set,
                         today_iso: str) -> tuple[list[dict], list[str]]:
    """Pure reference decision for RECONCILE (the agent is the one that
    actually pulls get_option_positions and calls this; see EMBER-PROMPT.md).
    `live_open_keys` is whatever the broker actually shows open, as a set of
    opaque keys the agent builds from get_option_positions (e.g. (ticker,
    expiry, strike, right) tuples) that the agent also knows how to match
    against each known position's own legs. Unlike call_diag's RECONCILE
    (log-only), EMBER's own spec asks this mode to DROP state for a position
    we show open that the broker doesn't (close it in OUR OWN state only,
    reason "reconcile_vanished") and LOG (never touch) any live position not
    in our book (an orphan). Returns (updated_positions, log_lines); does
    not mutate input."""
    updated = []
    log_lines = []
    for p in known_positions:
        if p.get("state") != "open":
            updated.append(p)
            continue
        if p.get("id") not in live_open_keys:
            closed = {**p, "state": "closed",
                      "exit": {"closed_date": today_iso, "fill_net": 0.0,
                                "reasons": ["reconcile_vanished"], "done": True}}
            updated.append(closed)
            log_lines.append(f"RECONCILE | MISMATCH: {p.get('id')} {p.get('ticker')} recorded "
                              f"open, not found at broker -- dropped from open book")
        else:
            updated.append(p)
    return updated, log_lines


# ---------------------------------------------------------------- halt
def is_globally_halted(cfg: Cfg) -> bool:
    """EMBER_HALTED in .env only -- no order_state-side companion (see
    module docstring deviation #3)."""
    return bool(cfg.halted_env)


# ---------------------------------------------------------------- mode decision (pure)
def decide(now: datetime, day: dict, halted: bool) -> tuple[str | None, str]:
    if halted:
        return None, "HALTED (EMBER_HALTED=1)"
    if now.weekday() >= 5:
        return None, "weekend"
    t = now.time()
    if not (WINDOW_START_CT <= t <= WINDOW_END_CT):
        return None, "outside window"
    reconcile = day.get("reconcile") or {}
    if not reconcile.get("done"):
        return "RECONCILE", "first tick of day"
    return "TRADE", "entry/exit re-check"


# ---------------------------------------------------------------- ENTRY capacity capping (pure)
def cap_entry_candidates(ranked: list[dict], positions: list[dict], total_value: float | None,
                          cfg: Cfg) -> tuple[list[dict], float | None]:
    """Given a ranked (already entry_row_eligible-filtered) list and the
    current positions book, apply ENVELOPE + capacity (max_open,
    max_new_per_tick) incrementally -- mirrors call_diag's own ENTRY block
    exactly: a running usage total reserves capacity for candidates earlier
    in this same ranked list so two rows the same tick can't both "fit"
    against the same headroom. Returns (accepted, envelope_usd) --
    envelope_usd is None (and accepted always empty) when total_value was
    never cached, same fail-closed convention as call_diag's."""
    envelope_usd = envelope_usd_from_pct(cfg.envelope_pct, total_value) if total_value is not None else None
    usage_running = ember_envelope_usage(positions)
    open_n = sum(1 for p in positions if p.get("state") == "open")
    capacity = max(0, cfg.max_open - open_n)
    accepted: list[dict] = []
    for row in ranked:
        if len(accepted) >= min(cfg.max_new_per_tick, capacity):
            break
        need = structure_cost_usd(row) or 0.0
        if envelope_usd is None:
            continue  # ENVELOPE: total_value never cached -- refuse every candidate, never guessed
        fits, _ = ember_envelope_fit_check(envelope_usd, usage_running, need)
        if not fits:
            continue
        usage_running = round(usage_running + need, 2)
        accepted.append(row)
    return accepted, envelope_usd


# ---------------------------------------------------------------- signal + prompt
def build_signal(now: datetime, mode: str, day: dict, order_state: dict, cfg: Cfg,
                  accepted_candidates: list[dict] | None = None,
                  envelope_usd: float | None = None) -> dict:
    today_iso = now.date().isoformat()
    positions = order_state.get("positions") or []
    open_positions = [p for p in positions if p.get("state") == "open"]
    sig = {
        "mode": mode, "now_ct": now.isoformat(timespec="seconds"), "today": today_iso,
        "account": ACCOUNT, "armed": int(cfg.armed), "dry_run": int(cfg.dry_run),
        "entry_start_ct": ENTRY_START_CT.strftime("%H:%M"), "entry_end_ct": ENTRY_END_CT.strftime("%H:%M"),
        "max_cost_usd": cfg.max_cost_usd, "max_open": cfg.max_open,
        "max_new_per_tick": cfg.max_new_per_tick, "time_stop_sessions": cfg.time_stop_sessions,
        "close_dte": cfg.close_dte, "envelope_pct": cfg.envelope_pct,
        "fee_per_contract": cfg.fee_per_contract, "exit_reprice_after_min": EXIT_REPRICE_AFTER_MIN,
    }
    if mode == "RECONCILE":
        sig["known_open_positions"] = open_positions
    elif mode == "TRADE":
        sig["open_positions"] = open_positions
        due_pure = positions_due_for_exit_pure(positions, now.date(), cfg)
        sig["due_exits_precomputed"] = {p["id"]: p["exit_reasons"] for p in due_pure if p.get("id")}
        sig["entry_candidates"] = accepted_candidates or []
        sig["envelope_usd"] = envelope_usd
    keys = day.setdefault("ref_ids", {})
    if mode == "TRADE":
        for row in sig.get("entry_candidates", []):
            base = ticket_id(row)
            keys.setdefault(f"entry_{base}_long", f"{base}-long")
            keys.setdefault(f"entry_{base}_short", f"{base}-short")
            keys.setdefault(f"entry_{base}_unwind", f"{base}-unwind")
        for p in sig.get("open_positions", []):
            keys.setdefault(f"exit_{p['id']}_short", f"{p['id']}-exit-short")
            keys.setdefault(f"exit_{p['id']}_long", f"{p['id']}-exit-long")
    sig["ref_ids"] = keys
    return sig


def render_prompt(sig: dict) -> str:
    tmpl = PROMPT_MD.read_text(encoding="utf-8")
    return tmpl.replace("__SIGNAL_JSON__", json.dumps(sig, indent=2))


# ---------------------------------------------------------------- allowlist gate (pure)
READ_TOOLS = [
    "Read", "Write", "Edit",
    "mcp__robinhood-trading__get_accounts",
    "mcp__robinhood-trading__get_portfolio",
    "mcp__robinhood-trading__get_equity_quotes",
    "mcp__robinhood-trading__get_option_chains",
    "mcp__robinhood-trading__get_option_instruments",
    "mcp__robinhood-trading__get_option_quotes",
    "mcp__robinhood-trading__get_option_orders",
    "mcp__robinhood-trading__get_option_positions",
    "mcp__robinhood-trading__review_option_order",
]
ORDER_TOOLS = [
    "mcp__robinhood-trading__place_option_order",
    "mcp__robinhood-trading__cancel_option_order",
]


def build_allowlist(cfg: Cfg) -> list[str]:
    tools = list(READ_TOOLS)
    if cfg.armed and not cfg.dry_run:
        tools += ORDER_TOOLS
    return tools


def run_agent(sig: dict, cfg: Cfg) -> int:
    tools = build_allowlist(cfg)
    prompt = render_prompt(sig)
    from ..xsp_flow_live import build_claude_command, read_secret_environment
    bundled = CODE_DIR.parents[2] / "frontend" / "node_modules" / ".bin" / "claude"
    configured = cfg.claude_bin if cfg.claude_bin != "claude" else ""
    exe = configured or shutil.which("claude") or str(bundled)
    child_env = read_secret_environment()
    cmd = build_claude_command(exe, tools)
    with RUN_OUTPUT.open("a", encoding="utf-8") as out:
        out.write(f"===== {sig['mode']} run started {sig['now_ct']} armed={sig['armed']} "
                  f"dry_run={sig['dry_run']} =====\n")
        out.flush()
        try:
            rc = subprocess.run(cmd, cwd=str(HERE), input=prompt, stdout=out,
                                 stderr=subprocess.STDOUT, timeout=600,
                                 text=True, encoding="utf-8", env=child_env).returncode
        except subprocess.TimeoutExpired:
            out.write("TIMEOUT: claude -p exceeded 600s\n")
            rc = 124
        out.write(f"===== {sig['mode']} run ended exit={rc} =====\n")
    return rc


def notify(tone: str, line: str) -> None:
    try:
        notifier = HERE / "notify.py"
        if notifier.exists():
            subprocess.run([sys.executable, str(notifier), tone, line], timeout=60, cwd=str(HERE))
    except Exception:
        pass


def tone_for(line: str) -> str:
    low = line.lower()
    if any(w in low for w in ("error", "fail", "reject", "unauth", "cannot", "unreachable",
                               "mismatch", "stale", "invalid", "timeout", "halted",
                               "no log line", "missing")):
        return "bad"
    if "dry-run" in low:
        return "good"
    if re.search(r"\|\s*(OPEN|CLOSE|SOLD|MARKET-CLOSE|BUY|SELL)\b", line):
        return "trade"
    return "good"


# ---------------------------------------------------------------- main tick
def _run_mode(now: datetime, cfg: Cfg, mode: str, order_state: dict, day: dict, *,
              dry_run_cli: bool = False, forced_mode: str | None = None) -> int:
    """Runs one mode (RECONCILE or TRADE) to completion against an already-
    loaded order_state/day: builds the signal, invokes the agent (unless
    dry_run_cli), and does post-agent bookkeeping. Factored out of tick() so
    Fix 4a's RECONCILE -> TRADE continuation can run TRADE a second time in
    the SAME invocation without duplicating this body."""
    today = now.date().isoformat()
    positions = order_state.get("positions") or []
    accepted, envelope_usd = [], None

    if mode == "TRADE":
        ledger_rows, stale_reason = fresh_tick_rows(newest_tick_rows(load_ledger_rows()), now, cfg.max_ledger_age_min)
        if stale_reason:
            LOG_TXT.open("a", encoding="utf-8").write(
                f"{now.isoformat(timespec='seconds')} CT | TRADE | {stale_reason}\n")
        open_positions = [p for p in positions if p.get("state") == "open"]
        closed_log = closed_ticker_log(positions)
        # Fix 5: an in-flight ticker (an entry order this bot is still
        # placing, possibly from a tick that crashed mid-leg) reads as
        # "already open" for ENTRY purposes only -- the real `positions`
        # book used for exits/envelope/capacity is untouched by this.
        eligibility_positions = open_positions + in_flight_as_positions(order_state)
        ranked = select_entry_candidates(ledger_rows, eligibility_positions, closed_log, now, cfg)
        # Fix 4c/7: one summary line per tick -- why rows didn't make it, and
        # how many are still on an older ember.py ledger schema generation.
        counts = ineligibility_summary(ledger_rows, now, eligibility_positions, closed_log, cfg)
        schema_gap_n = schema_version_gap_count(ledger_rows)
        summary_line = (f"{now.isoformat(timespec='seconds')} CT | TRADE | {format_ineligibility_summary(counts)} "
                         f"| schema_version<2: {schema_gap_n}")
        print(summary_line)
        LOG_TXT.open("a", encoding="utf-8").write(summary_line + "\n")
        total_value = (day.get("total_value") or {}).get("value")
        accepted, envelope_usd = cap_entry_candidates(ranked, positions, total_value, cfg)
        # Pure no-op (no agent call) only when NOTHING is open (nothing to
        # exit-check) AND no scanner row survived ranking + envelope/capacity
        # capping -- mirrors call_diag's SAFETY/EXIT no-op convention. Uses
        # the FINAL `accepted` list, not the pre-envelope `ranked` one, so a
        # candidate that's eligible but doesn't fit the envelope never
        # triggers an agent call on its own.
        if not open_positions and not accepted:
            line = f"{now.isoformat(timespec='seconds')} CT | TRADE | nothing open, nothing eligible to enter"
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("good", line)
            if forced_mode:
                print(line)
            return 0
        # Fix 5: persist an in-flight record for every accepted candidate
        # BEFORE the agent is ever invoked -- if this process dies mid-leg,
        # the record survives in order_state.json (saved below) and blocks
        # re-selection of the same ticker on the next tick.
        for row in accepted:
            start_in_flight(order_state, row.get("ticker"), row.get("structure"),
                             now.isoformat(timespec="seconds"), row.get("scan_time"))

    sig = build_signal(now, mode, day, order_state, cfg, accepted, envelope_usd)
    order_state[today] = day
    if dry_run_cli:
        print("[--dry-run] would run the agent with signal:")
        print(json.dumps(sig, indent=2))
        return 0
    save_json(ORDER_STATE, order_state)  # ref_ids + snapshots (+ in_flight) persist before the agent runs

    if forced_mode:
        print(f"[--once {mode}] armed={int(cfg.armed)} dry_run={int(cfg.dry_run)} -- "
              f"calling the real agent (claude -p), no stub...")
    pre = LOG_TXT.read_text(encoding="utf-8").splitlines()[-1] if LOG_TXT.exists() else ""
    rc = run_agent(sig, cfg)
    post = LOG_TXT.read_text(encoding="utf-8").splitlines()[-1] if LOG_TXT.exists() else ""
    if not post or post == pre:
        tail = RUN_OUTPUT.read_text(encoding="utf-8", errors="replace")[-4000:]
        if "Failed to authenticate" in tail or "OAuth" in tail:
            line = (f"{sig['now_ct']} CT | {mode} | CLAUDE AUTH FAILED - CLAUDE_CODE_OAUTH_TOKEN "
                     f"is empty or invalid in .env. Run `claude` once interactively to re-login. "
                     f"No orders possible.")
        else:
            line = (f"{sig['now_ct']} CT | {mode} | agent wrote no log line (claude exit={rc}) "
                     f"- check ember/run-output.log")
        LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
        notify("bad", line)
        if forced_mode:
            print(line)
        return 1
    notify(tone_for(post), post)
    if forced_mode:
        print(post)

    # ---- post-agent bookkeeping: RECONCILE is marked "done" for the day ----
    # once the agent has resolved it; TRADE has no daily "done" flag (see
    # module docstring #1) -- it simply re-evaluates next tick.
    order_state2 = load_json(ORDER_STATE)
    day2 = order_state2.get(today) or {}
    if mode == "RECONCILE":
        day2.setdefault("reconcile", {})["done"] = True
        order_state2[today] = day2
        # Fix 5(ii): RECONCILE re-syncs the positions book from the broker --
        # any in-flight record left over from a crashed prior tick is stale
        # by definition once the real open-positions truth has been re-read.
        order_state2["in_flight"] = {}
        save_json(ORDER_STATE, order_state2)
    elif mode == "TRADE" and accepted:
        # Fix 5(i): reached only once post != pre, i.e. the agent produced a
        # parsed result (fill or refusal) for this tick's candidates -- clear
        # their in-flight records now that the outcome is known.
        for row in accepted:
            clear_in_flight(order_state2, row.get("ticker"))
        save_json(ORDER_STATE, order_state2)

    return 0


def tick(now: datetime, cfg: Cfg, *, dry_run_cli: bool = False, forced_mode: str | None = None,
         force_rerun: bool = False) -> int:
    today = now.date().isoformat()
    order_state = load_json(ORDER_STATE)
    day = order_state.get(today) or {}
    halted = is_globally_halted(cfg)

    if forced_mode:
        mode, why = forced_mode, "--once (manual, bypasses clock gating)"
        if forced_mode == "RECONCILE":
            already = bool((day.get("reconcile") or {}).get("done"))
            if already and not force_rerun:
                print(f"REFUSED: RECONCILE already recorded for today ({today}). "
                      f"Use --force to re-run (dry-run only).")
                return 2
            if already and force_rerun and not cfg.dry_run:
                print("REFUSED: --force only re-runs a recorded mode when dry_run is True "
                      "(EMBER_DRY_RUN=1 in .env or --dry-run on the command line). Refusing "
                      "to re-fire a live mode.")
                return 2
    else:
        mode, why = decide(now, day, halted)
    print(f"{now.isoformat(timespec='seconds')} CT | mode={mode} | {why} | "
          f"armed={int(cfg.armed)} dry_run={int(cfg.dry_run)} halted={int(halted)}")
    if mode is None:
        return 0

    rc = _run_mode(now, cfg, mode, order_state, day, dry_run_cli=dry_run_cli, forced_mode=forced_mode)

    # Fix 4a: a RECONCILE that completes successfully (rc==0, not a
    # --dry-run preview) during the entry window continues straight into
    # TRADE in the SAME invocation -- RECONCILE is always the first tick of
    # the day, and without this the day's first real entry opportunity would
    # wait for the next scheduled tick (up to 30 min later) instead of using
    # the freshest ledger tick right now.
    if mode == "RECONCILE" and rc == 0 and not dry_run_cli and ENTRY_START_CT <= now.time() <= ENTRY_END_CT:
        order_state = load_json(ORDER_STATE)   # pick up whatever RECONCILE's agent just wrote
        day = order_state.get(today) or {}
        print(f"{now.isoformat(timespec='seconds')} CT | mode=TRADE | continuing after RECONCILE "
              f"(inside entry window) | armed={int(cfg.armed)} dry_run={int(cfg.dry_run)} halted={int(halted)}")
        rc = _run_mode(now, cfg, "TRADE", order_state, day, dry_run_cli=dry_run_cli, forced_mode=None)

    return rc


# ---------------------------------------------------------------- unit tests
def _unit_tests() -> int:
    # ---- trading calendar ----
    assert is_trading_day(date(2026, 9, 7)) is False   # Labor Day
    assert is_trading_day(date(2026, 9, 8)) is True
    assert trading_sessions_between(date(2026, 9, 4), date(2026, 9, 8)) == 1   # only 9/8 (Fri->weekend->Labor Day->Tue)
    assert trading_sessions_between(date(2026, 9, 9), date(2026, 9, 9)) == 0
    assert trading_sessions_between(date(2026, 9, 9), date(2026, 9, 8)) == 0   # d2 <= d1

    # ---- ledger parsing ----
    rows = [
        {"ticker": "A", "scan_time": "2026-09-16T09:35:00"},
        {"ticker": "B", "scan_time": "2026-09-16T10:05:00"},
        {"ticker": "C", "scan_time": "2026-09-16T10:05:00"},
        {"ticker": "D"},  # no scan_time -- never "newest"
    ]
    newest = newest_tick_rows(rows)
    assert {r["ticker"] for r in newest} == {"B", "C"}
    assert newest_tick_rows([]) == []
    assert newest_tick_rows([{"ticker": "X"}]) == []  # no scan_time anywhere

    # ---- chosen_opt_rr / structure_cost_usd / row_expiry_iso ----
    assert chosen_opt_rr({"structure": "single", "opt_rr_7d": 2.5}) == 2.5
    assert chosen_opt_rr({"structure": "single", "call_rr_7d": 3.0}) == 3.0  # falls back
    assert chosen_opt_rr({"structure": "call", "call_rr_7d": 2.1}) == 2.1
    assert chosen_opt_rr({"structure": "vertical", "vert_rr": 2.2}) == 2.2
    assert chosen_opt_rr({"structure": "pcs", "pcs_rr_stop": 2.3}) == 2.3
    assert chosen_opt_rr({"structure": "bogus"}) is None
    assert chosen_opt_rr({}) is None

    assert structure_cost_usd({"structure": "single", "cost_usd": 150.0}) == 150.0
    assert structure_cost_usd({"structure": "vertical", "cost_usd": 90.0}) == 90.0
    assert structure_cost_usd({"structure": "call", "call_cost_usd": 120.0}) == 120.0
    assert structure_cost_usd({"structure": "pcs", "pcs_width": 2.0}) == 200.0
    assert structure_cost_usd({"structure": "pcs"}) is None
    assert structure_cost_usd({"structure": "bogus"}) is None

    assert row_expiry_iso({"exp": "2026-10-16"}) == "2026-10-16"
    assert row_expiry_iso({"flow_exp": "2026-10-23"}) == "2026-10-23"
    assert row_expiry_iso({"exp": "2026-10-16", "flow_exp": "2026-10-23"}) == "2026-10-16"
    assert row_expiry_iso({}) is None

    assert has_short_leg("vertical") is True
    assert has_short_leg("pcs") is True
    assert has_short_leg("single") is False
    assert has_short_leg("call") is False
    assert has_short_leg(None) is False

    assert ticket_key({"ticker": "AAPL", "scan_date": "2026-09-16", "dir": "long", "strategy": "rr"}) == \
        ("AAPL", "2026-09-16", "long", "rr")
    assert ticket_id({"ticker": "AAPL", "scan_date": "2026-09-16", "dir": "long", "strategy": "rr"}) == \
        "AAPL_2026-09-16_long_rr"

    # ---- entry filter ----
    now = datetime(2026, 9, 16, 10, 0, tzinfo=CT)
    good_row = {"ticker": "AAPL", "liquid": True, "stock_rr": 2.5, "structure": "single",
                "opt_rr_7d": 2.2, "cost_usd": 150.0}
    cfg = Cfg()
    assert entry_row_eligible(good_row, now, [], {}, cfg) == (True, "eligible")
    assert entry_row_eligible({**good_row, "liquid": False}, now, [], {}, cfg)[0] is False
    assert entry_row_eligible({**good_row, "liquid": None}, now, [], {}, cfg)[0] is False
    assert entry_row_eligible({**good_row, "stock_rr": 1.9}, now, [], {}, cfg)[0] is False
    assert entry_row_eligible({**good_row, "structure": "bogus"}, now, [], {}, cfg)[0] is False
    assert entry_row_eligible({**good_row, "opt_rr_7d": 1.5}, now, [], {}, cfg)[0] is False
    assert entry_row_eligible({**good_row, "cost_usd": 250.0}, now, [], {}, cfg)[0] is False
    assert entry_row_eligible({**good_row, "cost_usd": None}, now, [], {}, cfg)[0] is False
    open_pos = [{"ticker": "AAPL", "state": "open"}]
    assert entry_row_eligible(good_row, now, open_pos, {}, cfg) == (False, "already open on this ticker")
    closed_log = {"AAPL": "2026-09-15"}  # 1 session ago -- under the 5-session cooldown
    ok, reason = entry_row_eligible(good_row, now, [], closed_log, cfg)
    assert ok is False and "cooldown" in reason
    closed_log_old = {"AAPL": "2026-09-01"}  # well past 5 sessions
    assert entry_row_eligible(good_row, now, [], closed_log_old, cfg)[0] is True
    outside = datetime(2026, 9, 16, 8, 45, tzinfo=CT)
    assert entry_row_eligible(good_row, outside, [], {}, cfg) == (False, "outside entry window (09:05-15:30 CT)")

    ranked_in = [good_row, {**good_row, "ticker": "MSFT", "stock_rr": 3.5}]
    ranked = select_entry_candidates(ranked_in, [], {}, now, cfg)
    assert [r["ticker"] for r in ranked] == ["MSFT", "AAPL"]  # ranked by stock_rr desc

    assert closed_ticker_log([
        {"ticker": "AAPL", "state": "closed", "exit": {"closed_date": "2026-09-10"}},
        {"ticker": "AAPL", "state": "closed", "exit": {"closed_date": "2026-09-14"}},
        {"ticker": "MSFT", "state": "open"},
    ]) == {"AAPL": "2026-09-14"}

    # ---- exit due (pure half) ----
    positions = [
        {"id": "p1", "ticker": "AAPL", "state": "open", "entry_date": "2026-09-01",
         "structure": "vertical", "exp": "2026-09-18"},   # time_stop + short_dte both fire
        {"id": "p2", "ticker": "MSFT", "state": "open", "entry_date": "2026-09-15",
         "structure": "single", "exp": "2026-09-17"},     # single_dte fires (dte<=1)
        {"id": "p3", "ticker": "NVDA", "state": "open", "entry_date": "2026-09-15",
         "structure": "single", "exp": "2026-10-01"},     # nothing pure fires
        {"id": "p4", "ticker": "TSLA", "state": "closed"},
    ]
    today = date(2026, 9, 16)
    due = positions_due_for_exit_pure(positions, today, cfg)
    due_by_id = {d["id"]: set(d["exit_reasons"]) for d in due}
    assert due_by_id["p1"] == {"time_stop", "short_dte"}
    assert due_by_id["p2"] == {"single_dte"}
    assert "p3" not in due_by_id
    assert "p4" not in due_by_id

    assert price_target_stop_hit({"dir": "long", "target": 100, "stop": 90}, 101) is True
    assert price_target_stop_hit({"dir": "long", "target": 100, "stop": 90}, 89) is True
    assert price_target_stop_hit({"dir": "long", "target": 100, "stop": 90}, 95) is False
    assert price_target_stop_hit({"dir": "short", "target": 90, "stop": 100}, 89) is True
    assert price_target_stop_hit({"dir": "short", "target": 90, "stop": 100}, 101) is True
    assert price_target_stop_hit({"dir": "short", "target": 90, "stop": 100}, 95) is False
    assert price_target_stop_hit({"dir": "long", "target": None, "stop": 90}, 95) is False

    # ---- fills / fill-price rule ----
    assert long_fill_price(1.00, 1.03) == (1.03, "ok")
    assert long_fill_price(1.00, 1.05) == (1.05, "ok")   # exactly 5% -- still ok
    assert long_fill_price(1.00, 0.95) == (0.95, "ok")   # better than the row -- always ok
    px, reason = long_fill_price(1.00, 1.10)
    assert px is None and "5%" in reason
    assert long_fill_price(None, 1.00) == (None, "no row ask")
    assert long_fill_price(1.00, None) == (None, "no live ask")

    ok, reason = buying_power_ok(500.0, 200.0)
    assert ok is True and reason == "ok"
    ok2, reason2 = buying_power_ok(200.0, 200.0)  # 200 < 200+25
    assert ok2 is False and "buying_power" in reason2
    ok3, reason3 = buying_power_ok(None, 200.0)
    assert ok3 is False and "unknown" in reason3

    # ---- ENVELOPE ----
    assert envelope_usd_from_pct(45.0, 1000.0) == 450.0
    assert ember_envelope_usage([{"state": "open", "cost_usd": 150.0},
                                  {"state": "closed", "cost_usd": 999.0}]) == 150.0
    assert ember_envelope_usage([]) == 0.0
    fits, total = ember_envelope_fit_check(450.0, 150.0, 200.0)
    assert fits is True and total == 350.0
    fits2, total2 = ember_envelope_fit_check(450.0, 300.0, 200.0)
    assert fits2 is False and total2 == 500.0

    # ---- legging state machine (with has_short) ----
    assert entry_leg_action("not_placed", "not_placed") == "PLACE_LONG"
    assert entry_leg_action("filled", "not_placed") == "PLACE_SHORT"
    assert entry_leg_action("filled", "rejected") == "UNWIND_LONG"
    assert entry_leg_action("filled", "filled") == "POSITION_OPEN"
    assert entry_leg_action("filled", None, has_short=False) == "POSITION_OPEN"
    assert entry_leg_action("not_placed", None, has_short=False) == "PLACE_LONG"
    assert entry_leg_action("no_fill", "not_placed") == "NO_ENTRY"
    try:
        entry_leg_action("bogus", "not_placed")
        assert False
    except ValueError:
        pass

    assert exit_leg_action("open", "open") == "CLOSE_SHORT"
    assert exit_leg_action("closed", "open") == "CLOSE_LONG"
    assert exit_leg_action("closed", "closed") == "DONE"
    assert exit_leg_action(None, "open", has_short=False) == "CLOSE_LONG"
    assert exit_leg_action(None, "closed", has_short=False) == "DONE"

    assert is_half_open_position({"state": "open", "structure": "vertical",
                                   "legs": {"long": {"state": "filled"}, "short": {"state": "rejected"}}}) is True
    assert is_half_open_position({"state": "open", "structure": "single",
                                   "legs": {"long": {"state": "filled"}}}) is False  # no short exists at all

    # ---- reconcile ----
    known = [{"id": "p1", "ticker": "AAPL", "state": "open"}, {"id": "p2", "ticker": "MSFT", "state": "open"}]
    updated, logs = reconcile_positions(known, live_open_keys={"p1"}, today_iso="2026-09-16")
    p2_after = next(p for p in updated if p["id"] == "p2")
    assert p2_after["state"] == "closed"
    assert p2_after["exit"]["reasons"] == ["reconcile_vanished"]
    p1_after = next(p for p in updated if p["id"] == "p1")
    assert p1_after["state"] == "open"
    assert any("p2" in l and "MISMATCH" in l for l in logs)

    # ---- halt / decide ----
    assert is_globally_halted(Cfg(halted_env=True)) is True
    assert is_globally_halted(Cfg(halted_env=False)) is False
    d = datetime(2026, 9, 16, 9, 0, tzinfo=CT)  # Wednesday
    assert decide(d, {}, halted=True)[0] is None
    assert decide(d, {}, halted=False)[0] == "RECONCILE"
    recon_done = {"reconcile": {"done": True}}
    assert decide(d, recon_done, halted=False)[0] == "TRADE"
    weekend = datetime(2026, 9, 19, 9, 0, tzinfo=CT)
    assert decide(weekend, {}, halted=False)[0] is None
    outside_window = d.replace(hour=17, minute=0)
    assert decide(outside_window, recon_done, halted=False)[0] is None

    # ---- allowlist gate ----
    unarmed = build_allowlist(Cfg(armed=False, dry_run=True))
    armed_dry = build_allowlist(Cfg(armed=True, dry_run=True))
    armed_live = build_allowlist(Cfg(armed=True, dry_run=False))
    for tools in (unarmed, armed_dry):
        assert "mcp__robinhood-trading__place_option_order" not in tools
        assert "mcp__robinhood-trading__cancel_option_order" not in tools
    assert "mcp__robinhood-trading__place_option_order" in armed_live
    assert "mcp__robinhood-trading__cancel_option_order" in armed_live

    # ---- repricing ----
    assert reprice_entry(1.05) == 1.10
    assert reprice_exit(0.50, 0.05) == 0.45

    print("unit tests: OK")
    return 0


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--at", default=None, help="Override now as ISO datetime (CT)")
    ap.add_argument("--dry-run", action="store_true",
                     help="Without --once: decide + print the signal; do not run the agent or "
                          "touch state. With --once: force EMBER_DRY_RUN=1 for this run "
                          "regardless of .env.")
    ap.add_argument("--once", metavar="MODE", choices=ONCE_MODES, default=None,
                     help="Run exactly one tick of MODE right now, bypassing the clock.")
    ap.add_argument("--force", action="store_true",
                     help="With --once RECONCILE: re-run a mode already recorded for today. "
                          "Refused unless dry_run is True. TRADE has no daily done-state to force.")
    ap.add_argument("--unit-test", action="store_true")
    a = ap.parse_args()
    if a.unit_test:
        return _unit_tests()
    cfg = load_cfg()
    now = (datetime.fromisoformat(a.at).replace(tzinfo=CT) if a.at else datetime.now(CT))
    try:
        if a.once:
            if a.dry_run:
                cfg = replace(cfg, dry_run=True)
            return tick(now, cfg, forced_mode=a.once, force_rerun=a.force)
        return tick(now, cfg, dry_run_cli=a.dry_run)
    except Exception as e:  # noqa: BLE001 -- never retry-loop; log and exit non-zero
        line = f"{now.isoformat(timespec='seconds')} CT | ERROR | {type(e).__name__}: {e}"
        try:
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
        except Exception:
            pass
        print(line, file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Fix 3: overlap guard -- always on (this driver has no --cached-style
    # no-op mode the way the scanner does). Always released in the finally,
    # including an uncaught exception out of main().
    if not ember_lock.acquire_lock(LOCK_FILE):
        raise SystemExit(0)
    try:
        raise SystemExit(main())
    finally:
        ember_lock.release_lock(LOCK_FILE)
