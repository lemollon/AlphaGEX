"""DIVHIKE - laptop driver for idea #69's dividend-hike median-ratio drift
(tools/mr_book/PREREG_69.md + its AMENDMENT; out/GATE_69.md: cell A HALF1=FAIL,
HALF2=PASS, cell H FAIL both halves -- overall marginal FAIL. See README.md
before ever arming.)

Modeled on ../night_shift/run_night.py's architecture -- a Python driver
invoked every minute by a Windows scheduled task, a persistent
order_state.json, one line per run in divhike-log.txt, an append-only
intents.log (one line before every order attempt), an order agent invoked as
`claude -p DIVHIKE-PROMPT.md` with the Robinhood MCP only when a broker call
is actually needed, DIVHIKE_ARMED / DIVHIKE_DRY_RUN env flags gating the
order-tool allowlist, and the same "each mode runs at most once per day"
guard recorded in order_state.json.

Unlike Night Shift (one instrument, one position slot), this bot can hold up
to MAX_POSITIONS=3 tickers at once, each entered/exited on its own calendar
(the divhike RULE below), so order_state.json["positions"] is a dict keyed by
ticker, not a single slot. Also unlike Night Shift, the SCAN mode (Polygon
declaration discovery) needs no broker call at all -- it is pure Python, run
directly by this driver, never through the agent -- only RECONCILE / ENTER /
EXIT touch the Robinhood MCP.

THE RULE (must match tools/mr_book/gate_69_divhike_regular.py exactly; see
that file's own AMENDMENT docstring -- this is NOT re-derived here):
  event   = a cash dividend declaration whose amount is > 2.0x the MEDIAN of
            the ticker's previous up to 4 dividends with an ex-date in the
            prior 24 months (>=2 prior dividends required, else no event).
            A record whose OWN dividend_type is "SC" can never be the event
            itself; SC records ARE included in the median.
  entry   = close of the first session strictly AFTER declaration_date.
  exit    = close of T-1, the session before the ex-date. NEVER held across
            the ex-date. Unconditional -- no profit target, no stop.
  elig.   = at entry: close >= $2.00 and trailing-63-session median dollar
            volume >= $1,000,000.

RISK LIMITS (hard-coded constants below, enforced in PYTHON before every
order -- the agent only executes what Python has already sized and
approved):
  MAX_POSITIONS = 3 concurrent tickers.
  MAX_DOLLARS_PER_POSITION = $100.
  MAX_TOTAL_DOLLARS = $300 across all open divhike positions.
  ENVELOPE: never exceed DIVHIKE_ENVELOPE_PCT% of live account total_value
            (own .env, source of truth, mirrors calldiag/dailycal's own
            pattern -- registered read-only in ../envelopes/envelopes.json's
            "divhike" entry). Never trades if that pct is 0 (the shipped
            default). The TIGHTER of the envelope and the $300/$100 hard caps
            always wins.
  Never averages down, never re-enters a ticker already held, never places
  more than one order per ticker per day. Skips (and logs) any ticker whose
  fractional order the broker rejects.

MODES (mirrors Night Shift's once-per-window design; no continuous loop):
  RECONCILE  ~08:33 CT. Reads broker equity positions + portfolio total_value
             via the Robinhood MCP, floor-checks them against
             order_state.json["positions"], caches total_value for ENTER's
             sizing. Never trades.
  SCAN       ~15:10 CT. Pure Python: pulls Polygon's recent dividend
             declarations, applies THE RULE, writes/updates
             divhike_candidates.csv with planned entry/exit sessions. No
             broker call, no orders.
  ENTER      15:55-15:59 CT. For each candidate whose planned entry session
             is today: re-checks eligibility fresh, applies every risk limit
             in Python, and (if armed+live) places a market buy for the
             Python-computed dollar amount via the agent.
  EXIT       15:55-15:59 CT, decided BEFORE ENTER every tick so it always
             gets a chance to run even if ENTER is skipped for any reason.
             Sells the FULL quantity of every open position whose planned
             exit session is today. Retries each tick through the window; if
             still unsold when the window closes, logs a loud UNSOLD ALERT
             with the ticker and quantity and leaves the position open for a
             human (never silently cleared, never given up on quietly).

Usage:
  python run_divhike.py                          # scheduled tick
  python run_divhike.py --at 2026-09-12T15:10 [--dry-run]
  python run_divhike.py --once SCAN --dry-run
  python run_divhike.py --once ENTER --dry-run [--force]
                                             # run exactly ONE tick of MODE
                                             # now, bypassing the clock.
                                             # --dry-run forces
                                             # DIVHIKE_DRY_RUN=1 for this run
                                             # regardless of .env, so an
                                             # order tool is never in the
                                             # agent's allowlist; --force
                                             # re-runs a mode already
                                             # recorded today, dry-run only.
  python run_divhike.py --unit-test
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

CT = ZoneInfo("America/Chicago")
CODE_DIR = Path(__file__).resolve().parent
HERE = Path(os.getenv("EMBER_DIVHIKE_DATA_DIR", str(CODE_DIR))).expanduser().resolve()
HERE.mkdir(parents=True, exist_ok=True)
ORDER_STATE = HERE / "order_state.json"
LOG_TXT = HERE / "divhike-log.txt"
RUN_OUTPUT = HERE / "run-output.log"
LEDGER_CSV = HERE / "divhike-ledger.csv"
INTENTS_LOG = HERE / "intents.log"
CANDIDATES_CSV = HERE / "divhike_candidates.csv"
PROMPT_MD = CODE_DIR / "DIVHIKE-PROMPT.md"
ENV_FILE = HERE / ".env"
# tick.log is written by the .cmd scheduled-task wrapper's own stdout
# redirect, never by this file -- same split as night_shift/call_diag/daily_cal.

ENVELOPES_JSON = Path(os.getenv(
    "EMBER_ENVELOPES_JSON", str(HERE.parent / "envelopes" / "envelopes.json")
))  # registry only, read-only here

ACCOUNT = "570892331"           # Robinhood "Agentic" account -- never point this bot at any other.
POLYGON_BASE = os.getenv("POLYGON_BASE_URL", "https://api.polygon.io").rstrip("/")

# ---- THE RULE (must match gate_69_divhike_regular.py exactly, never "improved") -----------
RATIO_MIN = 2.0                 # event: amount > 2.0x the median denominator
PREV_LOOKBACK_MONTHS = 24       # prior dividends must have an ex-date in this window
MEDIAN_WINDOW_N = 4              # median of up to 4 previous dividends
MEDIAN_MIN_N = 2                 # at least 2 prior dividends required, else no event
PRICE_MIN = 2.0                  # eligibility: close >= $2.00 at entry
DOLVOL_MIN = 1_000_000.0         # eligibility: trailing-63-session median $ volume >= $1M
DOLVOL_LOOKBACK = 63

# ---- RISK LIMITS (hard-coded, enforced in Python before every order) ----------------------
MAX_POSITIONS = 3                    # concurrent tickers
MAX_DOLLARS_PER_POSITION = 100.00    # per new position
MAX_TOTAL_DOLLARS = 300.00           # across all open divhike positions
DEFAULT_ENVELOPE_PCT = 0.0           # shipped default -- 0 means NEVER trade until Leron sizes it

# ---- clock (CT) -----------------------------------------------------------------------------
RECONCILE_START_CT = time(8, 30)
RECONCILE_AT_CT = time(8, 33)
RECONCILE_END_CT = time(9, 0)

SCAN_START_CT = time(15, 10)
SCAN_END_CT = time(15, 11)

CLOSE_START_CT = time(15, 55)          # ENTER + EXIT window (task-specified clock)
CLOSE_CUTOFF_CT = time(15, 59)         # retry cutoff inside the window -- ALERT past this
CLOSE_END_CT = time(16, 0)

READ_TOOLS = [
    "Read", "Write", "Edit",
    "mcp__robinhood-trading__get_accounts",
    "mcp__robinhood-trading__get_portfolio",
    "mcp__robinhood-trading__get_equity_quotes",
    "mcp__robinhood-trading__get_equity_positions",
    "mcp__robinhood-trading__get_equity_orders",
    "mcp__robinhood-trading__review_equity_order",
]
ORDER_TOOLS = [
    "mcp__robinhood-trading__place_equity_order",
    "mcp__robinhood-trading__cancel_equity_order",
]

ONCE_MODES = ("RECONCILE", "SCAN", "ENTER", "EXIT")
MODE_STATE_KEY = {"RECONCILE": "reconcile", "SCAN": "scan", "ENTER": "enter", "EXIT": "exit"}


# ---------------------------------------------------------------- config
@dataclass
class Cfg:
    armed: bool = False
    dry_run: bool = True
    envelope_pct: float = DEFAULT_ENVELOPE_PCT
    claude_bin: str = "claude"


def load_cfg(env_file: Path = ENV_FILE) -> Cfg:
    """Missing .env => every default is the safe one (unarmed, dry-run, 0% envelope)."""
    env: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    env = {**env, **{k: v for k, v in os.environ.items() if k.startswith("DIVHIKE_")}}
    try:
        pct = float(env.get("DIVHIKE_ENVELOPE_PCT", str(DEFAULT_ENVELOPE_PCT)))
    except ValueError:
        pct = DEFAULT_ENVELOPE_PCT
    return Cfg(
        armed=env.get("DIVHIKE_ARMED", "0") == "1",
        dry_run=env.get("DIVHIKE_DRY_RUN", "1") != "0",
        envelope_pct=pct,
        claude_bin=env.get("DIVHIKE_CLAUDE_BIN", "claude"),
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


# ================================================================================================
# THE RULE -- pure functions, directly unit-testable, no I/O. The live SCAN below feeds these
# with real Polygon/yfinance data; nothing about the decision logic itself lives in the I/O layer.
# ================================================================================================
def median_ratio_rule(amount: float, own_type: str | None, prior_amounts: list[float]) -> dict:
    """prior_amounts: the ticker's dividend amounts (ANY type, SC included) with an ex-date
    strictly before the candidate's own ex-date and within PREV_LOOKBACK_MONTHS, already sorted
    ASCENDING by ex-date (oldest first) by the caller -- this function only takes the trailing
    MEDIAN_WINDOW_N of that list and never re-sorts by date itself. A record whose own
    dividend_type is 'SC' can never be the event -- checked first, unconditionally. SC records
    inside prior_amounts are NEVER excluded from the median by this function (the AMENDMENT: SC
    is barred from being the event, not from being part of the denominator)."""
    if own_type == "SC":
        return dict(event=False, reason="own_type_SC")
    last_n = prior_amounts[-MEDIAN_WINDOW_N:]
    n_used = len(last_n)
    if n_used < MEDIAN_MIN_N:
        return dict(event=False, reason="insufficient_prior_dividends", n_used=n_used)
    median = float(np.median(last_n))
    ratio = (amount / median) if median else float("nan")
    if not (ratio > RATIO_MIN):
        return dict(event=False, reason="ratio_below_2x", ratio=ratio, median=median, n_used=n_used)
    return dict(event=True, reason="SURVIVES", ratio=ratio, median=median, n_used=n_used)


def eligible_entry(close_px: float | None, trailing_dolvol_median: float | None) -> tuple[bool, str]:
    """close >= $2.00 and trailing-63-session median dollar volume >= $1,000,000, both at entry."""
    if close_px is None or not (close_px == close_px) or close_px < PRICE_MIN:
        return False, f"close {close_px} < ${PRICE_MIN:.2f}"
    if trailing_dolvol_median is None or not (trailing_dolvol_median == trailing_dolvol_median) \
            or trailing_dolvol_median < DOLVOL_MIN:
        return False, (f"trailing-{DOLVOL_LOOKBACK}-session median $ volume "
                        f"{trailing_dolvol_median} < ${DOLVOL_MIN:,.0f}")
    return True, "eligible"


def entry_session_after(decl_date: date, trading_days: list[date]) -> date | None:
    """First session strictly AFTER declaration_date. trading_days must be sorted ascending."""
    for d in trading_days:
        if d > decl_date:
            return d
    return None


def exit_session_before_ex(ex_date: date, trading_days: list[date]) -> date | None:
    """T-1: the session immediately before ex_date (never the ex-date itself). trading_days
    must be sorted ascending."""
    prior = [d for d in trading_days if d < ex_date]
    return prior[-1] if prior else None


# ---------------------------------------------------------------- risk limits (pure)
def sizing_for_entry(open_positions: dict, envelope_pct: float, total_value: float | None,
                      committed_today: float = 0.0) -> tuple[float, str]:
    """Dollar amount for ONE new position, the tighter of every limit: MAX_POSITIONS (0 if
    already full), the envelope (0 if pct<=0 or total_value unknown -- NEVER guessed),
    MAX_TOTAL_DOLLARS minus whatever is already open/committed today, and
    MAX_DOLLARS_PER_POSITION itself. `committed_today` lets ENTER size a SECOND/THIRD candidate
    in the same run against dollars already assigned to an earlier one in the same batch."""
    if len(open_positions) >= MAX_POSITIONS:
        return 0.0, f"MAX_POSITIONS ({MAX_POSITIONS}) already open"
    committed = sum(float(p.get("entry_dollar_amount") or 0.0) for p in open_positions.values()) \
        + committed_today
    if envelope_pct <= 0:
        return 0.0, "envelope pct is 0 -- never trade (Leron has not sized this bot yet)"
    if total_value is None:
        return 0.0, "total_value unavailable (RECONCILE never cached it) -- never guessed"
    envelope_budget = round(envelope_pct / 100.0 * total_value, 2)
    remaining_envelope = max(0.0, round(envelope_budget - committed, 2))
    remaining_total_cap = max(0.0, round(MAX_TOTAL_DOLLARS - committed, 2))
    dollars = min(MAX_DOLLARS_PER_POSITION, remaining_envelope, remaining_total_cap)
    if dollars <= 0:
        return 0.0, (f"no budget remaining (envelope_budget=${envelope_budget:.2f}, "
                      f"total_cap=${MAX_TOTAL_DOLLARS:.2f}, already committed=${committed:.2f})")
    return round(dollars, 2), "min(MAX_DOLLARS_PER_POSITION, remaining_envelope, remaining_total_dollars_cap)"


def build_entry_orders(candidates_today: list[dict], open_positions: dict, envelope_pct: float,
                        total_value: float | None, tickers_attempted_today: set[str]) -> tuple[list[dict], list[dict]]:
    """Deterministic Python sizing for every candidate whose planned entry is today. Returns
    (orders, skipped) -- orders is what ENTER will ask the agent to place, skipped carries the
    reason for every candidate this run refuses. Never re-enters a ticker already held, never
    more than one order per ticker per day, MAX_POSITIONS/MAX_TOTAL_DOLLARS/envelope enforced
    across the WHOLE batch (each accepted candidate reduces the next one's remaining budget)."""
    orders, skipped = [], []
    seen_this_batch: set[str] = set()
    for cand in candidates_today:
        t = cand["ticker"]
        if t in open_positions:
            skipped.append({"ticker": t, "reason": "already held -- never re-enter/average down"})
            continue
        if t in tickers_attempted_today or t in seen_this_batch:
            skipped.append({"ticker": t, "reason": "already attempted today -- one order per ticker per day"})
            continue
        # open_positions already reflects every order accepted earlier in THIS batch (see below)
        # -- no separate committed_today accumulator, or MAX_TOTAL_DOLLARS would be double-counted.
        dollars, why = sizing_for_entry(open_positions, envelope_pct, total_value)
        if dollars <= 0:
            skipped.append({"ticker": t, "reason": why})
            continue
        orders.append({"ticker": t, "dollars": dollars, "reason": why, "candidate": cand})
        seen_this_batch.add(t)
        # a filled order also "opens" a position for the purposes of MAX_POSITIONS/MAX_TOTAL_DOLLARS
        # on the next candidate in this same batch
        open_positions = {**open_positions, t: {"entry_dollar_amount": dollars}}
    return orders, skipped


def build_exit_orders(open_positions: dict, today: date, tickers_attempted_today: set[str]) -> list[dict]:
    """Every open position whose planned_exit_date is today, full quantity, one order per
    ticker. Never gated by any risk limit -- exits are always allowed."""
    orders = []
    for t, pos in open_positions.items():
        if t in tickers_attempted_today:
            continue
        planned_exit = pos.get("planned_exit_date")
        if planned_exit and str(planned_exit) == today.isoformat():
            orders.append({"ticker": t, "qty": pos.get("qty")})
    return orders


# ---------------------------------------------------------------- mode decision (pure)
def decide(now: datetime, day: dict) -> tuple[str | None, str]:
    """Pure: (mode, reason). day = order_state[today] (may be {}). Three disjoint daily windows
    -- RECONCILE (morning), SCAN (after the close), and the ENTER/EXIT close window -- rather
    than one continuous window. Inside the close window, EXIT is decided BEFORE ENTER every
    single tick, so it always gets a chance to run even if ENTER was skipped, failed, or already
    marked done for any reason -- their "done" flags are tracked completely independently."""
    t = now.time()
    if now.weekday() >= 5:
        return None, "weekend"

    if RECONCILE_START_CT <= t <= RECONCILE_END_CT:
        reconcile = day.get("reconcile") or {}
        if reconcile.get("done"):
            return None, "reconcile complete"
        if t < RECONCILE_AT_CT:
            return None, "before reconcile time"
        return "RECONCILE", "reconcile positions vs order_state, cache total_value"

    if SCAN_START_CT <= t <= SCAN_END_CT:
        scan = day.get("scan") or {}
        if scan.get("done"):
            return None, "scan complete"
        return "SCAN", "Polygon declaration scan, no orders"

    if CLOSE_START_CT <= t <= CLOSE_END_CT:
        exit_ = day.get("exit") or {}
        enter = day.get("enter") or {}
        if not exit_.get("done"):
            return "EXIT", "exit window -- decided before ENTER every tick"
        if not enter.get("done"):
            return "ENTER", "enter window"
        return None, "close window complete"

    return None, "outside window"


# ---------------------------------------------------------------- signal + prompt (agent modes)
def build_signal(now: datetime, mode: str, day: dict, order_state: dict, cfg: Cfg,
                  *, entry_orders: list[dict] | None = None,
                  exit_orders: list[dict] | None = None) -> dict:
    today_iso = now.date().isoformat()
    positions = order_state.get("positions") or {}
    sig = {
        "mode": mode, "now_ct": now.isoformat(timespec="seconds"), "today": today_iso,
        "account": ACCOUNT, "armed": int(cfg.armed), "dry_run": int(cfg.dry_run),
        "close_cutoff_ct": CLOSE_CUTOFF_CT.strftime("%H:%M"), "close_end_ct": CLOSE_END_CT.strftime("%H:%M"),
    }
    if mode == "RECONCILE":
        sig["known_positions"] = positions
    elif mode == "ENTER":
        sig["orders_to_place"] = entry_orders or []
    elif mode == "EXIT":
        sig["orders_to_place"] = exit_orders or []
    keys = day.setdefault("ref_ids", {})
    if mode in ("ENTER", "EXIT"):
        bucket = keys.setdefault(mode.lower(), {})
        for o in (entry_orders or []) if mode == "ENTER" else (exit_orders or []):
            bucket.setdefault(o["ticker"], str(uuid.uuid4()))
    sig["ref_ids"] = keys
    return sig


def render_prompt(sig: dict) -> str:
    tmpl = PROMPT_MD.read_text(encoding="utf-8")
    return tmpl.replace("__SIGNAL_JSON__", json.dumps(sig, indent=2))


def build_allowlist(cfg: Cfg) -> list[str]:
    tools = list(READ_TOOLS)
    if cfg.armed and not cfg.dry_run:
        tools += ORDER_TOOLS
    return tools


def run_agent(sig: dict, cfg: Cfg) -> int:
    tools = build_allowlist(cfg)
    prompt = render_prompt(sig)
    from ..xsp_flow_live import read_secret_environment
    bundled = CODE_DIR.parents[2] / "frontend" / "node_modules" / ".bin" / "claude"
    configured = cfg.claude_bin if cfg.claude_bin != "claude" else ""
    exe = configured or shutil.which("claude") or str(bundled)
    child_env = read_secret_environment()
    cmd = [exe, "-p", "--allowedTools", *tools]
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
        except FileNotFoundError as e:
            out.write(f"CLAUDE BINARY NOT FOUND: {e}\n")
            rc = 127
        out.write(f"===== {sig['mode']} run ended exit={rc} =====\n")
    return rc


def notify(tone: str, line: str) -> None:
    try:
        notifier = HERE.parent / "night_shift" / "notify.py"
        if notifier.exists():
            subprocess.run([sys.executable, str(notifier), tone, line], timeout=60, cwd=str(HERE))
    except Exception:
        pass


# ---------------------------------------------------------------- ledger
LEDGER_COLS = ["ticker", "entry_date", "entry_fill_price", "qty", "entry_dollar_amount",
               "exit_date", "exit_fill_price", "exit_dollar_amount", "pnl_usd", "dry_run"]


def append_ledger(row: dict) -> None:
    new = not LEDGER_CSV.exists()
    with LEDGER_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        if new:
            w.writeheader()
        w.writerow(row)


# ================================================================================================
# SCAN -- cloud-native Polygon discovery, no broker call and no workstation files.
# ================================================================================================
def _polygon_get(path_or_url: str, params: dict | None = None) -> dict:
    import requests

    api_key = os.getenv("POLYGON_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY is not configured")
    url = path_or_url if path_or_url.startswith("http") else f"{POLYGON_BASE}{path_or_url}"
    query = dict(params or {})
    query.setdefault("apiKey", api_key)
    response = requests.get(url, params=query, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Polygon returned a non-object response")
    return payload


def _polygon_pages(path: str, params: dict) -> list[dict]:
    rows: list[dict] = []
    payload = _polygon_get(path, params)
    while True:
        values = payload.get("results") or []
        if not isinstance(values, list):
            raise RuntimeError("Polygon results is not a list")
        rows.extend(row for row in values if isinstance(row, dict))
        next_url = payload.get("next_url")
        if not next_url:
            return rows
        payload = _polygon_get(str(next_url))


def _months_ago(d: date, months: int) -> date:
    year = d.year
    month = d.month - months
    while month <= 0:
        year -= 1
        month += 12
    import calendar
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _prior_dividends(ticker: str, ex_date: date) -> list[float]:
    rows = _polygon_pages("/v3/reference/dividends", {
        "ticker": ticker,
        "ex_dividend_date.gte": _months_ago(ex_date, PREV_LOOKBACK_MONTHS).isoformat(),
        "ex_dividend_date.lt": ex_date.isoformat(),
        "sort": "ex_dividend_date",
        "order": "asc",
        "limit": 1000,
    })
    ordered = sorted(
        (row for row in rows if row.get("ex_dividend_date") and row.get("cash_amount") is not None),
        key=lambda row: str(row["ex_dividend_date"]),
    )
    return [float(row["cash_amount"]) for row in ordered[-MEDIAN_WINDOW_N:]]


def _next_session(d: date) -> date:
    from .tv_book import is_trading_day
    candidate = d + timedelta(days=1)
    while not is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def _previous_session(d: date) -> date:
    from .tv_book import is_trading_day
    candidate = d - timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def scan_divhike(*, log=print) -> dict:
    """The daily SCAN job. Returns a summary dict; writes/updates divhike_candidates.csv.
    Idempotent on (ticker, declaration_date, ex_date). NEVER places an order."""
    import pandas as pd

    existing = pd.DataFrame()
    if CANDIDATES_CSV.exists():
        existing = pd.read_csv(CANDIDATES_CSV, dtype={"ticker": str})
    existing_keys = set(zip(existing.get("ticker", []), existing.get("declaration_date", []),
                             existing.get("ex_date", []))) if len(existing) else set()

    today = datetime.now(CT).date()
    raw = _polygon_pages("/v3/reference/dividends", {
        "declaration_date.gte": (today - timedelta(days=14)).isoformat(),
        "declaration_date.lte": today.isoformat(),
        "sort": "declaration_date",
        "order": "desc",
        "limit": 1000,
    })
    filtered = [row for row in raw if row.get("ticker") and row.get("cash_amount") is not None
                and row.get("declaration_date") and row.get("ex_dividend_date")
                and str(row.get("currency", "USD")).upper() == "USD"]
    log(f"SCAN | Polygon USD cash declarations: {len(filtered):,}/{len(raw):,}")

    new_rows, drop_counts = [], {"own_type_SC": 0, "insufficient_prior_dividends": 0, "ratio_below_2x": 0}
    for row in filtered:
        ticker = row["ticker"]
        decl_date = date.fromisoformat(str(row["declaration_date"])[:10])
        ex_date = date.fromisoformat(str(row["ex_dividend_date"])[:10])
        key_tuple = (str(ticker), decl_date.isoformat(), ex_date.isoformat())
        if key_tuple in existing_keys:
            continue
        own_type = row.get("dividend_type")
        prior_amounts = _prior_dividends(str(ticker), ex_date)
        r = median_ratio_rule(float(row["cash_amount"]), own_type, prior_amounts)
        if not r["event"]:
            drop_counts[r["reason"]] = drop_counts.get(r["reason"], 0) + 1
            continue

        planned_entry, planned_exit = _next_session(decl_date), _previous_session(ex_date)
        new_rows.append(dict(
            ticker=ticker, declaration_date=decl_date.isoformat(),
            ex_date=ex_date.isoformat(), amount=float(row["cash_amount"]),
            median_amount=r["median"], ratio=r["ratio"], n_used=r["n_used"], dividend_type=own_type,
            planned_entry_date=planned_entry.isoformat(),
            planned_exit_date=planned_exit.isoformat(),
            first_seen_utc=datetime.now(CT).isoformat(timespec="seconds"), status="candidate",
        ))
        existing_keys.add(key_tuple)

    log(f"SCAN | new #69 candidates (ratio>{RATIO_MIN:.1f}x median of up to {MEDIAN_WINDOW_N} "
        f"priors, >= {MEDIAN_MIN_N} required): {len(new_rows)}; dropped this scan: {drop_counts}")

    book = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True) if len(new_rows) else existing
    if not book.empty:
        book.to_csv(CANDIDATES_CSV, index=False)
    return {"n_new": len(new_rows), "n_total": len(book), "drop_counts": drop_counts}

def _entry_eligibility(ticker: str, today: date) -> tuple[bool, str, dict]:
    start = today - timedelta(days=120)
    payload = _polygon_get(
        f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{today.isoformat()}",
        {"adjusted": "true", "sort": "asc", "limit": 500},
    )
    bars = [row for row in (payload.get("results") or []) if isinstance(row, dict)]
    if not bars:
        return False, "Polygon returned no daily bars", {}
    last = bars[-1]
    last_date = datetime.fromtimestamp(float(last.get("t", 0)) / 1000, tz=timezone.utc).date()
    if last_date != today:
        return False, f"entry-day bar unavailable (latest={last_date})", {}
    close_px = float(last["c"]) if last.get("c") is not None else None
    dollar_volumes = [float(row["c"]) * float(row["v"])
                      for row in bars[-DOLVOL_LOOKBACK:]
                      if row.get("c") is not None and row.get("v") is not None]
    median_dollar_volume = float(np.median(dollar_volumes)) if len(dollar_volumes) >= DOLVOL_LOOKBACK else None
    ok, reason = eligible_entry(close_px, median_dollar_volume)
    return ok, reason, {"entry_close": close_px, "trailing_dolvol_median": median_dollar_volume}


# ---------------------------------------------------------------- main tick
def tick(now: datetime, cfg: Cfg, *, dry_run_cli: bool = False, forced_mode: str | None = None,
         force_rerun: bool = False) -> int:
    today = now.date().isoformat()
    order_state = load_json(ORDER_STATE)
    day = order_state.get(today) or {}

    if forced_mode:
        mode, why = forced_mode, "--once (manual, bypasses clock gating)"
        already = bool((day.get(MODE_STATE_KEY.get(mode, "")) or {}).get("done"))
        if already and not force_rerun:
            print(f"REFUSED: {mode} already recorded for today ({today}). Use --force to re-run (dry-run only).")
            return 2
        if already and force_rerun and not cfg.dry_run:
            print("REFUSED: --force only re-runs a recorded mode when dry_run is True. Refusing to re-fire a live mode.")
            return 2
    else:
        mode, why = decide(now, day)
    print(f"{now.isoformat(timespec='seconds')} CT | mode={mode} | {why} | "
          f"armed={int(cfg.armed)} dry_run={int(cfg.dry_run)} envelope_pct={cfg.envelope_pct}")
    if mode is None:
        return 0

    positions = order_state.get("positions") or {}

    # ---- SCAN: pure Python, never touches the broker, never calls the agent -------------------
    if mode == "SCAN":
        def _log(line):
            full = f"{now.isoformat(timespec='seconds')} CT | {line}"
            LOG_TXT.open("a", encoding="utf-8").write(full + "\n")
            print(full)
        try:
            summary = scan_divhike(log=_log)
            day["scan"] = {"done": True, "state": "ok", **summary}
        except SystemExit as e:
            day["scan"] = {"done": True, "state": "error", "reason": str(e)}
            _log(f"SCAN | ERROR: {e}")
            notify("bad", f"SCAN | ERROR: {e}")
        except Exception as e:  # noqa: BLE001
            day["scan"] = {"done": True, "state": "error", "reason": f"{type(e).__name__}: {e}"}
            _log(f"SCAN | ERROR: {type(e).__name__}: {e}")
            notify("bad", f"SCAN | ERROR: {type(e).__name__}: {e}")
        order_state[today] = day
        save_json(ORDER_STATE, order_state)
        return 0

    # ---- ENTER: Python sizes/approves every order BEFORE the agent is ever invoked ------------
    entry_orders = None
    if mode == "ENTER":
        import pandas as pd
        candidates_today = []
        eligibility_skips: list[dict] = []
        if CANDIDATES_CSV.exists():
            cdf = pd.read_csv(CANDIDATES_CSV, dtype={"ticker": str})
            candidates_today = cdf[cdf["planned_entry_date"] == today].to_dict("records")
        eligible_today = []
        for candidate in candidates_today:
            ticker = str(candidate["ticker"])
            try:
                eligible, reason, metrics = _entry_eligibility(ticker, now.date())
            except Exception as exc:  # noqa: BLE001
                eligible, reason, metrics = False, f"eligibility data error: {type(exc).__name__}: {exc}", {}
            if not eligible:
                eligibility_skips.append({"ticker": ticker, "reason": reason})
                continue
            eligible_today.append({**candidate, **metrics})
        attempted = set((day.get("enter") or {}).get("tickers_attempted") or [])
        entry_orders, skipped = build_entry_orders(eligible_today, positions, cfg.envelope_pct,
                                                     (day.get("total_value") or {}).get("value"), attempted)
        skipped = eligibility_skips + skipped
        for s in skipped:
            line = f"{now.isoformat(timespec='seconds')} CT | ENTER | SKIP {s['ticker']}: {s['reason']}"
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            print(line)
        if not entry_orders:
            day["enter"] = {"done": True, "state": "no_orders", "skipped": skipped}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = (f"{now.isoformat(timespec='seconds')} CT | ENTER | NO-OP: no candidate passed "
                    f"eligibility + every risk limit today")
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("good", line)
            if forced_mode:
                print(line)
            return 0
        if dry_run_cli:
            print("[--dry-run] ENTER would place these orders (Python-approved, agent never called):")
            print(json.dumps(entry_orders, indent=2, default=str))
            return 0

    # ---- EXIT: always attempted first in the close window, no risk-limit gate -----------------
    exit_orders = None
    if mode == "EXIT":
        attempted = set((day.get("exit") or {}).get("tickers_attempted") or [])
        exit_orders = build_exit_orders(positions, now.date(), attempted)
        if not exit_orders:
            day["exit"] = {"done": True, "state": "no_orders"}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = f"{now.isoformat(timespec='seconds')} CT | EXIT | no open position's exit session is today"
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("good", line)
            if forced_mode:
                print(line)
            return 0
        if dry_run_cli:
            print("[--dry-run] EXIT would place these orders (agent never called):")
            print(json.dumps(exit_orders, indent=2, default=str))
            return 0

    sig = build_signal(now, mode, day, order_state, cfg, entry_orders=entry_orders, exit_orders=exit_orders)
    order_state[today] = day
    if dry_run_cli:
        print("[--dry-run] would run the agent with signal:")
        print(json.dumps(sig, indent=2))
        return 0
    save_json(ORDER_STATE, order_state)

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
                    f"is empty or invalid in .env. No orders possible.")
        elif "CLAUDE BINARY NOT FOUND" in tail or rc == 127:
            line = f"{sig['now_ct']} CT | {mode} | claude CLI not found on PATH. No orders possible."
        else:
            line = (f"{sig['now_ct']} CT | {mode} | agent wrote no log line (claude exit={rc}) "
                    f"- check divhike/run-output.log")
        LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
        notify("bad", line)
        if forced_mode:
            print(line)
        # EXIT must never be silently swallowed -- if the agent produced nothing, retry next
        # tick is still possible (day["exit"]["done"] was never set True above), but log loudly
        # if we're past the retry cutoff.
        if mode == "EXIT" and now.time() >= CLOSE_CUTOFF_CT:
            qty_list = ", ".join(f"{o['ticker']}={o.get('qty')}" for o in (exit_orders or []))
            unsold = (f"{sig['now_ct']} CT | EXIT | UNSOLD ALERT: past {CLOSE_CUTOFF_CT.strftime('%H:%M')} "
                      f"CT cutoff, still unsold this run -- {qty_list}. HUMAN MUST INTERVENE.")
            LOG_TXT.open("a", encoding="utf-8").write(unsold + "\n")
            notify("bad", unsold)
            if forced_mode:
                print(unsold)
        return 1
    notify_tone = "bad" if any(w in post.lower() for w in ("error", "fail", "unsold", "alert", "mismatch")) \
        else ("trade" if any(w in post.upper() for w in ("BOUGHT", "SOLD")) else "good")
    notify(notify_tone, post)
    if forced_mode:
        print(post)

    order_state = load_json(ORDER_STATE)
    day = order_state.get(today) or {}
    key = MODE_STATE_KEY[mode]
    bucket = day.setdefault(key, {})
    if bucket.get("state") in ("filled", "no_fill", "cancelled", "giveup") or now.time() >= CLOSE_END_CT:
        bucket["done"] = True
    order_state[today] = day
    save_json(ORDER_STATE, order_state)

    # EXIT never gives up quietly: the agent DID run and write a log line above, but if its own
    # recorded state is still not a terminal fill/cancel past the retry cutoff, this is a real
    # unsold position -- loud ALERT with ticker+qty every time this happens, on top of whatever
    # the agent itself logged.
    if mode == "EXIT" and bucket.get("state") not in ("filled", "no_fill", "cancelled") \
            and now.time() >= CLOSE_CUTOFF_CT:
        qty_list = ", ".join(f"{o['ticker']}={o.get('qty')}" for o in (exit_orders or []))
        unsold = (f"{now.isoformat(timespec='seconds')} CT | EXIT | UNSOLD ALERT: past "
                  f"{CLOSE_CUTOFF_CT.strftime('%H:%M')} CT cutoff, state={bucket.get('state')!r} -- "
                  f"{qty_list or 'see run-output.log'}. HUMAN MUST INTERVENE.")
        LOG_TXT.open("a", encoding="utf-8").write(unsold + "\n")
        notify("bad", unsold)
        if forced_mode:
            print(unsold)

    return 0


# ---------------------------------------------------------------- unit tests
def _unit_tests() -> int:
    # ---- THE RULE ----
    # OBDC artifact: candidate amount 0.37, immediate-previous 0.02 (old ratio 18.50x), but the
    # up-to-4 median (SC included) is 0.195 (priors sorted by date: 0.37, 0.195, 0.02) -> new
    # ratio 0.37/0.195 = 1.897 = 1.90x, which does NOT clear 2.0x -- REJECTED.
    r = median_ratio_rule(0.37, "CD", [0.37, 0.195, 0.02])
    assert r["event"] is False and r["reason"] == "ratio_below_2x", r
    assert round(r["ratio"], 2) == 1.90, r
    assert round(r["median"], 3) == 0.195, r
    old_ratio = 0.37 / 0.02
    assert round(old_ratio, 2) == 18.50

    # CCAP artifact: candidate amount 1.70, immediate-previous 0.15 (old ratio 11.33x), median of
    # priors [2.10, 2.10, 0.15] = 2.10 -> new ratio 1.70/2.10 = 0.81x -- REJECTED.
    r2 = median_ratio_rule(1.70, "CD", [2.10, 2.10, 0.15])
    assert r2["event"] is False and r2["reason"] == "ratio_below_2x", r2
    assert round(r2["ratio"], 2) == 0.81, r2
    old_ratio2 = 1.70 / 0.15
    assert round(old_ratio2, 2) == 11.33

    # own record typed SC can NEVER be the event, regardless of ratio
    r3 = median_ratio_rule(10.0, "SC", [1.0, 1.0, 1.0])
    assert r3["event"] is False and r3["reason"] == "own_type_SC"

    # SC records ARE included in the median (not excluded from the denominator)
    r4 = median_ratio_rule(3.0, "CD", [1.0, 1.0])   # median 1.0 -> ratio 3.0x, survives
    assert r4["event"] is True and round(r4["ratio"], 2) == 3.0
    # same priors, one of them SC-typed in reality -- median_ratio_rule takes amounts only, so
    # an SC prior contributes its amount to the median exactly like a CD prior would.
    r5 = median_ratio_rule(3.0, "CD", [1.0, 1.0])  # SC-typed prior is just another amount=1.0
    assert r5["event"] is True and r5["median"] == r4["median"]

    # fewer than 2 priors -> no event
    r6 = median_ratio_rule(5.0, "CD", [1.0])
    assert r6["event"] is False and r6["reason"] == "insufficient_prior_dividends"
    r7 = median_ratio_rule(5.0, "CD", [])
    assert r7["event"] is False and r7["reason"] == "insufficient_prior_dividends"

    # more than 4 priors -> only the trailing 4 (most recent) are used
    r8 = median_ratio_rule(100.0, "CD", [1000.0, 1.0, 1.0, 1.0, 1.0])  # oldest 1000 dropped
    assert r8["n_used"] == 4 and r8["median"] == 1.0

    # exactly at 2.0x is NOT "more than 2.0x" -- must strictly exceed
    r9 = median_ratio_rule(2.0, "CD", [1.0, 1.0])
    assert r9["event"] is False and r9["reason"] == "ratio_below_2x"

    # ---- eligibility ----
    ok, why = eligible_entry(2.00, 1_000_000.0)
    assert ok is True, why
    ok, why = eligible_entry(1.99, 1_000_000.0)
    assert ok is False and "close" in why
    ok, why = eligible_entry(5.0, 999_999.0)
    assert ok is False and "$ volume" in why
    ok, why = eligible_entry(None, 2_000_000.0)
    assert ok is False

    # ---- entry/exit session logic ----
    days = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 8)]
    assert entry_session_after(date(2026, 9, 1), days) == date(2026, 9, 2)
    assert entry_session_after(date(2026, 9, 8), days) is None
    assert exit_session_before_ex(date(2026, 9, 8), days) == date(2026, 9, 4)
    assert exit_session_before_ex(date(2026, 9, 1), days) is None

    # ---- risk limits ----
    d, why = sizing_for_entry({}, 100.0, 1000.0)
    assert d == 100.0, (d, why)  # per-position cap binds ($100 < $1000 envelope, $300 total)
    d, why = sizing_for_entry({}, 5.0, 1000.0)
    assert d == 50.0, (d, why)   # envelope binds (5% of 1000 = $50)
    d, why = sizing_for_entry({}, 0.0, 1000.0)
    assert d == 0.0 and "0" in why  # envelope pct 0 -- never trade
    d, why = sizing_for_entry({}, 50.0, None)
    assert d == 0.0 and "never guessed" in why
    open_full = {"A": {"entry_dollar_amount": 100.0}, "B": {"entry_dollar_amount": 100.0},
                 "C": {"entry_dollar_amount": 100.0}}
    d, why = sizing_for_entry(open_full, 100.0, 100_000.0)
    assert d == 0.0 and "MAX_POSITIONS" in why
    open_two = {"A": {"entry_dollar_amount": 100.0}, "B": {"entry_dollar_amount": 100.0}}
    d, why = sizing_for_entry(open_two, 100.0, 100_000.0)   # envelope huge, total cap binds: 300-200=100
    assert d == 100.0, (d, why)
    open_two_tight = {"A": {"entry_dollar_amount": 150.0}, "B": {"entry_dollar_amount": 100.0}}
    d, why = sizing_for_entry(open_two_tight, 100.0, 100_000.0)  # 300-250=50 remaining total cap
    assert d == 50.0, (d, why)
    d, why = sizing_for_entry({}, 100.0, 100_000.0, committed_today=280.0)  # 300-280=20 remaining
    assert d == 20.0, (d, why)

    # never re-enter a ticker already held / one order per ticker per day
    cands = [{"ticker": "OBDC", "declaration_date": "2026-09-10"}, {"ticker": "AAPL", "declaration_date": "2026-09-10"}]
    orders, skipped = build_entry_orders(cands, {"OBDC": {"entry_dollar_amount": 50.0}}, 100.0, 100_000.0, set())
    assert len(orders) == 1 and orders[0]["ticker"] == "AAPL"
    assert len(skipped) == 1 and skipped[0]["ticker"] == "OBDC" and "already held" in skipped[0]["reason"]
    orders2, skipped2 = build_entry_orders(cands, {}, 100.0, 100_000.0, {"OBDC"})
    assert len(orders2) == 1 and orders2[0]["ticker"] == "AAPL"
    assert skipped2[0]["ticker"] == "OBDC" and "one order per ticker per day" in skipped2[0]["reason"]

    # MAX_POSITIONS enforced across a single ENTER batch (3 candidates, only 3 total allowed)
    cands3 = [{"ticker": t} for t in ("A", "B", "C", "D")]
    orders3, skipped3 = build_entry_orders(cands3, {}, 100.0, 100_000.0, set())
    assert [o["ticker"] for o in orders3] == ["A", "B", "C"]
    assert skipped3[0]["ticker"] == "D" and "MAX_POSITIONS" in skipped3[0]["reason"]

    # exits are never gated by risk limits
    positions = {"OBDC": {"qty": 5.0, "planned_exit_date": "2026-09-12"},
                 "AAPL": {"qty": 2.0, "planned_exit_date": "2026-09-15"}}
    exits = build_exit_orders(positions, date(2026, 9, 12), set())
    assert len(exits) == 1 and exits[0]["ticker"] == "OBDC" and exits[0]["qty"] == 5.0

    # ---- decide(): window logic + EXIT-before-ENTER independence ----
    day0: dict = {}
    m, why = decide(datetime(2026, 9, 12, 8, 20, tzinfo=CT), day0)   # Saturday
    assert m is None and why == "weekend"
    m, why = decide(datetime(2026, 9, 11, 8, 20, tzinfo=CT), day0)
    assert m is None and why == "outside window"
    m, why = decide(datetime(2026, 9, 11, 8, 32, tzinfo=CT), day0)
    assert m is None and why == "before reconcile time"
    m, why = decide(datetime(2026, 9, 11, 8, 33, tzinfo=CT), day0)
    assert m == "RECONCILE"
    day1 = {"reconcile": {"done": True}}
    m, why = decide(datetime(2026, 9, 11, 9, 30, tzinfo=CT), day1)
    assert m is None and why == "outside window"
    m, why = decide(datetime(2026, 9, 11, 15, 10, tzinfo=CT), day1)
    assert m == "SCAN"
    day2 = {"reconcile": {"done": True}, "scan": {"done": True}}
    m, why = decide(datetime(2026, 9, 11, 15, 55, tzinfo=CT), day2)
    assert m == "EXIT"
    # EXIT already done, ENTER not -> ENTER runs
    day3 = {"reconcile": {"done": True}, "scan": {"done": True}, "exit": {"done": True}}
    m, why = decide(datetime(2026, 9, 11, 15, 56, tzinfo=CT), day3)
    assert m == "ENTER"
    # THE key invariant: ENTER already done/skipped -- EXIT still runs first if EXIT not done
    day4 = {"reconcile": {"done": True}, "scan": {"done": True},
            "enter": {"done": True, "state": "skipped", "reason": "whatever"}}
    m, why = decide(datetime(2026, 9, 11, 15, 57, tzinfo=CT), day4)
    assert m == "EXIT", (m, why)
    day5 = {"reconcile": {"done": True}, "scan": {"done": True},
            "exit": {"done": True}, "enter": {"done": True}}
    m, why = decide(datetime(2026, 9, 11, 15, 58, tzinfo=CT), day5)
    assert m is None and why == "close window complete"

    # ---- allowlist gate ----
    assert set(build_allowlist(Cfg(armed=False, dry_run=True))) == set(READ_TOOLS)
    assert set(build_allowlist(Cfg(armed=True, dry_run=True))) == set(READ_TOOLS)
    assert set(build_allowlist(Cfg(armed=False, dry_run=False))) == set(READ_TOOLS)
    assert set(build_allowlist(Cfg(armed=True, dry_run=False))) == set(READ_TOOLS) | set(ORDER_TOOLS)

    print("ALL UNIT TESTS PASSED")
    return 0


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--at", default=None, help="Override now as ISO datetime (CT)")
    ap.add_argument("--dry-run", action="store_true",
                     help="Without --once: decide + print the signal/orders; never touch state "
                          "or the agent. With --once: force DIVHIKE_DRY_RUN=1 for this run "
                          "regardless of .env.")
    ap.add_argument("--once", metavar="MODE", choices=ONCE_MODES, default=None,
                     help="Run exactly one tick of MODE right now, bypassing the clock.")
    ap.add_argument("--force", action="store_true",
                     help="With --once: re-run a mode already recorded for today. Refused unless dry_run is True.")
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
            return tick(now, cfg, dry_run_cli=a.dry_run, forced_mode=a.once, force_rerun=a.force)
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
    raise SystemExit(main())
