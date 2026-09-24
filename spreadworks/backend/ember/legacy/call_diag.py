"""CALL DIAG - laptop driver for the multi-ticker call diagonal book
(PREREG_500S / PREREG_500V, tools/mr_book/ - pre-registered, NOT YET SCORED
on real fills as of 2026-09-09; see DEPLOY.md before ever arming).

Modeled EXACTLY on ../daily_cal/run_cal.py's architecture: a Python driver
invoked every minute by a Windows scheduled task (`CallDiag`, hidden wrapper),
a persistent order_state.json, one line per minute in tick.log (written by
the .cmd wrapper, not by this file), an append-only intents.log (one line
before every order attempt), an order agent invoked as `claude -p
DIAG-PROMPT.md` with the Robinhood MCP only when a mode is due, DIAG_ARMED /
DIAG_DRY_RUN env flags gating the order-tool allowlist, and the same
notify/halt conventions as daily_cal (a manual DIAG_HALTED override in .env,
plus an automatic per-LEG halt written into order_state.json - never .env -
that the bot never clears itself).

Unlike daily_cal (one SPY/XSP position at a time, one calendar per day), this
bot runs a BOOK of independent call-diagonal legs (DIAG_LEGS in .env - see
that variable's own comment), each with its own staggered entry schedule and
its own ladder of up to `max_lots` simultaneously open positions. There is no
VIX gate here - legs enter on a fixed session cadence (`stagger_k`), not a
volatility signal - so this file has no compute_gate()/GATE_FALLBACK
equivalent. Every mode is either a pure-Python no-op (nothing due - no agent
call, exactly like daily_cal's XSP no-guard no-op) or a live agent run.

Every minute 08:30-15:06 CT weekdays this script decides which of four modes
is due, keyed by trade date in order_state.json (idempotent - a second run in
the same mode does nothing new):

  SAFETY      08:31 CT, first thing every day. Python computes which OPEN
              positions have their FRONT leg expiring TODAY (never let a
              short call ride into its own expiration morning). If none,
              pure no-op, no agent call. If any, one agent run: close them
              immediately with a marketable limit and mark that LEG halted
              (order_state, never .env) - a leg that hit this needs a human
              look at why EXIT/the ITM guard didn't already close it
              yesterday.
  RECONCILE   08:33 CT. One agent run every day: pull get_option_positions +
              get_option_orders (placed_agent=agentic) and reconcile against
              order_state.json's own idea of what's open. Mirrors daily_cal's
              SETTLEMENT mode's role (a data-confirmation step, not a trade).
  ENTRY       08:35-08:45 CT. Python snapshots which configured legs are due
              an entry today (stagger cadence hit AND under max_lots AND not
              halted) into order_state - the snapshot never changes mid-day
              even if a later leg's own fill changes conditions. If nothing
              is due, pure no-op, no agent call (exactly like daily_cal's
              "gate did not fire" - nothing to do, no reason to spend an
              agent call). If something is due: one 2-leg debit order per due
              leg (sell front call, buy back call, same account, same
              ticker), agent polls each minute, reprices once at +$0.05 after
              3 minutes unfilled, cancels NO-ENTRY at 08:45 if still unfilled.
  EXIT        14:59-15:05 CT. Python recomputes, EVERY tick, which OPEN
              positions are due a close today - either their own
              `planned_exit_date` has arrived, OR (checked at every EXIT tick,
              any day, not just a position's own scheduled exit day) its
              front leg is ITM by more than $1.00 (early-assignment guard).
              If nothing is currently due, pure no-op. If something is due:
              one 2-leg close order per due position, agent polls, reprices
              once at -$0.05 after 2 minutes, replaces with a marketable
              limit (-$0.15 more) at 15:04. A position drops off the due list
              the moment its own `state` flips to "closed" - EXIT mode is
              "done" for the day exactly when the freshly recomputed due list
              is empty, so a position that turns ITM mid-window at 15:02 gets
              picked up the same run it happens, never deferred to tomorrow.

Collateral guard (agent-side, before ANY entry order, per leg - see
DIAG-PROMPT.md): the agent runs review_option_order FIRST. Robinhood NETS
this structure (verified live 2026-09-09 on IWM: sell 9/21 301C + buy 9/30
305C previewed at collateral $400 = (305-301) x $100, fee $0.08/2-leg order)
- so the EXPECTED collateral is `width x $100 + net_debit`. The agent refuses
or places nothing if the REPORTED collateral from review_option_order exceeds
that expected figure by more than $5 (Robinhood isn't netting the way it did
in the verified preview - something changed), or if buying power is under
1.5x the reported collateral. See collateral_guard_ok() below - this file
computes the expected number and the pass/fail; the agent supplies the live
reported collateral and buying power.

Back-leg expiry/strike search (agent-side, per leg - see DIAG-PROMPT.md):
verified live 2026-09-09 that non-monthly IWM expiries only list $5-wide
strikes above ~$265, so the FIRST listed expiry with dte >= back_dte_min does
not always list the exact strike `ks + width`. The agent searches forward
through every listed expiry with dte in [back_dte_min, back_dte_min + 10]
(ascending) for the first one that lists `ks + width` exactly - see
candidate_back_expiries()/select_back_expiry_with_strike() below. If none of
those expiries list it, the entry is SKIPPED (logged "back strike missing")
- the wing is never widened to make a strike exist.

Usage:
  python run_diag.py                        # scheduled tick
  python run_diag.py --at 2026-09-09T08:35 [--dry-run]
  python run_diag.py --once ENTRY --dry-run [--force]
                                             # run exactly ONE tick of MODE now,
                                             # bypassing the clock. Calls the REAL
                                             # agent (no stub) -- --dry-run forces
                                             # DIAG_DRY_RUN=1 for this run regardless
                                             # of .env, so it can never place an
                                             # order; --force re-runs a mode already
                                             # recorded today, dry-run only.
  python run_diag.py --reset-halt [--leg IWM_10_20]
                                             # clears a triggered per-leg halt (or,
                                             # without --leg, the global halt);
                                             # refuses unless .env DIAG_HALTED=0
  python run_diag.py --unit-test
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
CODE_DIR = Path(__file__).resolve().parent
HERE = Path(os.getenv("EMBER_CALLDIAG_DATA_DIR", str(CODE_DIR))).expanduser().resolve()
HERE.mkdir(parents=True, exist_ok=True)
ORDER_STATE = HERE / "order_state.json"
LOG_TXT = HERE / "diag-log.txt"
RUN_OUTPUT = HERE / "run-output.log"
LEDGER_CSV = HERE / "ledger.csv"
INTENTS_LOG = HERE / "intents.log"
PROMPT_MD = CODE_DIR / "DIAG-PROMPT.md"
ENV_FILE = HERE / ".env"
# tick.log is written by the .cmd scheduled-task wrapper's own stdout
# redirect (see CallDiag.cmd, `>> tick.log 2>&1`), never by this file directly
# - same split as daily_cal (run_cal.py never opens DailyCal's tick.log
# either).

ACCOUNT = "570892331"           # Robinhood "Agentic" account, limited_margin + option_level_3
FEE_PER_CONTRACT_DEFAULT = 0.04  # verified live on SPY 2-leg orders (daily_cal); reused here as
                                 # the safe default for equity-underlying diagonals until this
                                 # book's own review_option_order previews say otherwise.

# ---- clock (CT) -------------------------------------------------------
WINDOW_START_CT = time(8, 30)
SAFETY_AT_CT = time(8, 31)      # expiry-day-open guard: never hold a front leg into its own
                                 # expiration morning. Runs before RECONCILE/ENTRY every day.
RECONCILE_AT_CT = time(8, 33)
ENTRY_START_CT = time(8, 35)
ENTRY_REPRICE_AFTER_MIN = 3     # unfilled after 3 minutes -> replace at mid+$0.05, once
ENTRY_CUTOFF_CT = time(8, 45)   # still unfilled -> cancel, NO-ENTRY
EXIT_START_CT = time(14, 59)
EXIT_REPRICE_AFTER_MIN = 2      # unfilled after 2 minutes -> replace at mid-$0.05
EXIT_MARKET_AT_CT = time(15, 4) # still unfilled -> marketable limit (mid-$0.15 more)
WINDOW_END_CT = time(15, 6)

ITM_GUARD_USD = 1.00            # front call ITM by more than this -> early-assignment guard
BACK_EXPIRY_SEARCH_DAYS = 10    # search back_dte_min .. back_dte_min+10 for a listed back strike
COLLATERAL_TOLERANCE_USD = 5.0  # reported collateral may exceed width*100+net_debit by this much
BP_COLLATERAL_MULT = 1.5        # buying power must be >= this x reported collateral

# ---- IWM trailing-RV5 entry stand-down (pre-registered, 2026-09-24) --------
# Frozen rule from ironforge-data/out/clusters/CLUSTER_calldiag_iwm.py: stand
# down the IWM leg's own entry when the trailing 5-day annualized realized
# vol is AT OR BELOW this floor (low-vol trades in that study's first-half
# discovery half showed both worse mean pnl and a higher loss-cluster rate,
# frozen at the first-half median and confirmed on the held-out second
# half). Exits/open positions are never touched by this rule -- ENTRY only,
# and only the IWM ticker (the only enabled leg as of this build).
IWM_RV5_STANDDOWN_DEFAULT = 0.1781   # 17.81%, DIAG_IWM_RV5_STANDDOWN overrides
IWM_RV5_LOOKBACK = 5                 # 5 daily returns -> 6 trailing closes needed

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

ONCE_MODES = ("SAFETY", "RECONCILE", "ENTRY", "EXIT")
MODE_STATE_KEY = {"SAFETY": "safety", "RECONCILE": "reconcile", "ENTRY": "entry", "EXIT": "exit"}


# ---- NYSE holiday calendar, hardcoded for 2026 (this bot's own trading- ----
# session math needs a REAL calendar, unlike daily_cal's documented
# weekday-only stdlib limitation - planned_exit_date() below is "the last
# trading session strictly before expiry," and a naive weekday walk would get
# that wrong across a market holiday, e.g. Labor Day). Not exhaustive beyond
# 2026 - a position whose lifecycle crosses into 2027 will fall back to
# weekday-only math for any date past this table (see is_trading_day()).
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
    weekday-only treatment (documented limitation, same spirit as daily_cal's
    stdlib-only decide()) -- this bot's own DTE ranges (10-42) keep almost
    every entry/exit inside 2026 as of the 2026-09-09 build date."""
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS_2026


def prior_trading_session(d: date) -> date:
    p = d - timedelta(days=1)
    while not is_trading_day(p):
        p -= timedelta(days=1)
    return p


def planned_exit_date(front_expiry: date) -> date:
    """Last trading session strictly BEFORE the front leg's own expiry --
    never hold a front call into its own expiration day (SAFETY mode is the
    backstop if this is ever violated some other way)."""
    return prior_trading_session(front_expiry)


# ---------------------------------------------------------------- leg config
@dataclass(frozen=True)
class Leg:
    """One row of DIAG_LEGS: ticker:front_dte_min:back_dte_min:width:stagger_k:max_lots.
    max_lots=0 means the leg is configured but disabled -- it still advances
    its own session counter every trading day (so a later `.env` edit that
    raises max_lots above 0 doesn't suddenly think it's leg's "session 1"),
    it just never becomes entry-due while disabled."""
    ticker: str
    front_dte_min: int
    back_dte_min: int
    width: int
    stagger_k: int
    max_lots: int

    @property
    def leg_id(self) -> str:
        """Unique even when two legs share a ticker with different DTE
        windows (the default DIAG_LEGS has two SPY legs, 10/20 and 21/42)."""
        return f"{self.ticker}_{self.front_dte_min}_{self.back_dte_min}"

    @property
    def enabled(self) -> bool:
        return self.max_lots > 0


DEFAULT_LEGS = "IWM:10:20:1:3:2,SPY:10:20:1:3:0,SPY:21:42:1:3:0,QQQ:10:20:1:3:0"


def parse_legs(raw: str) -> list[Leg]:
    """Malformed rows (wrong field count, non-integer field) are skipped
    entirely rather than guessed at -- a typo in .env should silently disable
    that one row, never crash the tick or half-parse a leg with a wrong DTE."""
    legs: list[Leg] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) != 6:
            continue
        ticker, f_dte, b_dte, width, k, max_lots = parts
        try:
            legs.append(Leg(ticker=ticker.strip().upper(), front_dte_min=int(f_dte),
                             back_dte_min=int(b_dte), width=int(width), stagger_k=int(k),
                             max_lots=int(max_lots)))
        except ValueError:
            continue
    return legs


# ---------------------------------------------------------------- config
@dataclass
class Cfg:
    armed: bool = False
    dry_run: bool = True
    halted_env: bool = False        # DIAG_HALTED in .env -- Leron's manual override, global
    legs_raw: str = DEFAULT_LEGS
    fee_per_contract: float = FEE_PER_CONTRACT_DEFAULT
    claude_bin: str = "claude"
    envelope_pct: float = 22.0      # DIAG_ENVELOPE_PCT -- this bot's FIXED PERCENTAGE share
                                     # of the Agentic account's live total_value (2026-09-10
                                     # ADR buying-power-envelopes; updated same day from a
                                     # fixed dollar figure to a percentage so the envelope
                                     # grows with the account, and lot capacity is DERIVED from
                                     # it rather than a separate fixed lot cap). The dollar
                                     # envelope is computed fresh every ENTRY tick as
                                     # envelope_pct/100 x total_value, using the total_value
                                     # RECONCILE caches daily (order_state[today]["total_value"],
                                     # from get_portfolio -- same field every envelope bot uses).
                                     # Usage is measured from the bot's own reconciled positions
                                     # book (order_state["positions"], confirmed daily against
                                     # the broker by RECONCILE's get_option_positions pull),
                                     # never free buying power. See diag_envelope_usage()/
                                     # diag_envelope_fit_check()/envelope_usd_from_pct() below.
    iwm_rv5_standdown: float = IWM_RV5_STANDDOWN_DEFAULT  # DIAG_IWM_RV5_STANDDOWN override

    @property
    def legs(self) -> list[Leg]:
        return parse_legs(self.legs_raw)


def load_cfg(env_file: Path = ENV_FILE) -> Cfg:
    """Missing .env => every default is the safe one (unarmed, dry-run, the
    committed DEFAULT_LEGS -- only IWM enabled)."""
    env: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    env = {**env, **{k: v for k, v in os.environ.items() if k.startswith("DIAG_")}}
    return Cfg(
        armed=env.get("DIAG_ARMED", "0") == "1",
        dry_run=env.get("DIAG_DRY_RUN", "1") != "0",
        halted_env=env.get("DIAG_HALTED", "0") == "1",
        legs_raw=env.get("DIAG_LEGS", DEFAULT_LEGS),
        fee_per_contract=float(env.get("DIAG_FEE_PER_CONTRACT", str(FEE_PER_CONTRACT_DEFAULT))),
        claude_bin=env.get("DIAG_CLAUDE_BIN", "claude"),
        envelope_pct=float(env.get("DIAG_ENVELOPE_PCT", "22")),
        iwm_rv5_standdown=float(env.get("DIAG_IWM_RV5_STANDDOWN", str(IWM_RV5_STANDDOWN_DEFAULT))),
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


# ---------------------------------------------------------------- DTE / expiry (pure)
def dte(expiry: date, today: date) -> int:
    return (expiry - today).days


def select_front_expiry(expirations: list[date], today: date, front_dte_min: int) -> date | None:
    """First listed expiry with dte >= front_dte_min. None if nothing listed
    that far out -- caller must refuse the entry, never guess an expiry."""
    for e in sorted(expirations):
        if dte(e, today) >= front_dte_min:
            return e
    return None


def candidate_back_expiries(expirations: list[date], today: date, back_dte_min: int,
                             front_expiry: date,
                             search_days: int = BACK_EXPIRY_SEARCH_DAYS) -> list[date]:
    """Ascending list of listed expiries with dte in
    [back_dte_min, back_dte_min + search_days], excluding the front expiry
    (the two must differ). Verified live 2026-09-09: IWM's non-monthly
    expiries only list $5-wide strikes above ~$265, so the FIRST such expiry
    does not always list the exact back strike -- the caller must search this
    whole window, not just take candidates[0]."""
    out = []
    for e in sorted(expirations):
        if e == front_expiry:
            continue
        d = dte(e, today)
        if back_dte_min <= d <= back_dte_min + search_days:
            out.append(e)
    return out


def select_back_expiry_with_strike(candidates: list[date],
                                    strikes_by_expiry: dict[date, list[float]],
                                    target_strike: float) -> date | None:
    """First candidate expiry (ascending) whose listed strikes include
    target_strike exactly. None if no candidate lists it -- the caller must
    SKIP the entry ("back strike missing"), never widen the wing to make a
    strike exist."""
    for e in candidates:
        strikes = strikes_by_expiry.get(e, [])
        if any(abs(s - target_strike) < 1e-9 for s in strikes):
            return e
    return None


# ---------------------------------------------------------------- EM / strikes (pure)
def em_from_quotes(call_mid: float, put_mid: float) -> float:
    return round(call_mid + put_mid, 4)


def nearest_strike(target: float, strikes: list[float]) -> float | None:
    """Nearest listed strike to target; ties break to the LOWER strike
    (deterministic, matches daily_cal's convention) -- used to find the ATM
    strike for the EM straddle, never for the short strike itself."""
    best = None
    best_d = None
    for s in sorted(strikes):
        d = abs(s - target)
        if best_d is None or d < best_d - 1e-9:
            best, best_d = s, d
    return best


def ceil_listed_strike(target: float, strikes: list[float]) -> float | None:
    """Nearest listed strike >= target. None if every listed strike is below
    target -- caller must refuse, never guess."""
    candidates = [s for s in strikes if s >= target - 1e-9]
    return min(candidates) if candidates else None


def short_strike(spot: float, em: float, strikes: list[float]) -> float | None:
    """ks = lowest listed call strike >= spot + EM."""
    return ceil_listed_strike(spot + em, strikes)


def long_strike_target(ks: float, width: int) -> float:
    """kb TARGET = ks + width -- pure arithmetic; select_back_expiry_with_strike()
    is what actually confirms a listed contract exists at this price."""
    return round(ks + width, 3)


# ---------------------------------------------------------------- stagger / session count (pure)
def is_entry_due_session(session_count: int, k: int) -> bool:
    """Entry-due sessions are 1, k+1, 2k+1, ... counted from the leg's first
    ever run (session_count=1). k<1 or session_count<1 is never due."""
    if session_count < 1 or k < 1:
        return False
    return (session_count - 1) % k == 0


def advance_session_counter(leg_state: dict, today_iso: str) -> dict:
    """Pure: given a leg's persisted {"session_count": int, "last_session_date":
    str|None}, returns the state advanced by exactly one session for
    `today_iso` -- idempotent (a second call with the same today_iso is a
    no-op) so the driver can call this on every ENTRY tick without
    double-counting a day."""
    if leg_state.get("last_session_date") == today_iso:
        return dict(leg_state)
    count = int(leg_state.get("session_count") or 0) + 1
    return {"session_count": count, "last_session_date": today_iso}


# ---------------------------------------------------------------- guard logic (pure)
def itm_guard_triggered(spot: float, ks: float, threshold: float = ITM_GUARD_USD) -> bool:
    """Front SHORT call is ITM by more than `threshold` -- early-assignment
    guard. (spot - ks) is the ITM amount for a call; > threshold, not >=, per
    spec ("ITM by more than $1.00")."""
    return (spot - ks) > threshold


def expiry_day_open_risk(today: date, front_expiry: date) -> bool:
    """True once `today` has reached the front leg's own expiry date --
    SAFETY mode's trigger to close immediately at 08:31, no matter how it got
    here (EXIT/the ITM guard should have already closed it the day before)."""
    return today >= front_expiry


# ---------------------------------------------------------------- IWM RV5 stand-down (pure)
def iwm_rv5(prior_closes: list[float]) -> float | None:
    """Trailing 5-day annualized realized vol from DAILY CLOSES, computed to
    match ironforge-data/out/clusters/CLUSTER_calldiag_iwm.py's own rv5_pct
    column EXACTLY (just without its final *100.0 -- this threshold is a
    fraction, 0.1781, not 17.81): that script builds `ret = spot.pct_change()`
    (simple, not log, returns) then `rv5_pct = ret.shift(1).rolling(5).std() *
    sqrt(252) * 100`, i.e. for the row dated `d` it is the stdev of the 5
    returns ending at `d-1` -- so `prior_closes` here must be the last 6
    CLOSES strictly before today, oldest-first, ending at the PRIOR trading
    session's close (never today's own -- ENTRY runs intraday, before today's
    close exists). `.std()` matches pandas' own default: sample stdev, ddof=1.
    Returns None (never guessed) if fewer than 6 closes are supplied."""
    if len(prior_closes) < IWM_RV5_LOOKBACK + 1:
        return None
    closes = prior_closes[-(IWM_RV5_LOOKBACK + 1):]
    rets = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


def iwm_standdown_check(prior_closes: list[float] | None,
                         threshold: float = IWM_RV5_STANDDOWN_DEFAULT) -> tuple[bool, str]:
    """Pure: (stand_down, reason). Fails CLOSED -- missing or insufficient
    closes always stands down (never guessed, never trades blind), same
    convention as every other guard in this file. `stand_down` is True (skip
    the entry) when rv5 <= threshold, per the frozen CLUSTER_calldiag_iwm.py
    rule (stand down on LOW realized vol, not high). Never touches exits or
    open positions -- ENTRY only."""
    if not prior_closes:
        return True, "STANDDOWN_IWM_RV5 unknown (no closes)"
    rv5 = iwm_rv5(prior_closes)
    if rv5 is None:
        return True, "STANDDOWN_IWM_RV5 unknown (fewer than 6 trailing closes)"
    if rv5 <= threshold:
        return True, f"STANDDOWN_IWM_RV5 {rv5:.4f}"
    return False, f"rv5 {rv5:.4f} > {threshold:.4f} (ok)"


def fetch_iwm_prior_closes(today: date, lookback: int = IWM_RV5_LOOKBACK + 1) -> list[float] | None:
    """Live daily closes for IWM strictly before `today`, oldest-first, via
    Tradier's `/v1/markets/history` (same TRADIER_TOKEN env var and request
    shape as tv_scanner.py's own `_tradier_json()` -- the existing Render
    fallback for market data in this repo). Returns None (fail closed, never
    guessed) on a missing token, a network/parse error, or fewer than
    `lookback` usable rows -- the caller must stand down, never trade blind
    on a data gap."""
    token = os.getenv("TRADIER_TOKEN", "").strip()
    if not token:
        return None
    start = today - timedelta(days=lookback * 3 + 10)  # generous window for weekends/holidays
    end = today - timedelta(days=1)
    query = urllib.parse.urlencode({"symbol": "IWM", "interval": "daily",
                                     "start": start.isoformat(), "end": end.isoformat()})
    req = urllib.request.Request(
        f"https://api.tradier.com/v1/markets/history?{query}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    days = ((payload or {}).get("history") or {}).get("day") or []
    if isinstance(days, dict):
        days = [days]
    today_iso = today.isoformat()
    try:
        rows = sorted(
            ((d.get("date"), float(d["close"])) for d in days
             if d.get("date") and d.get("close") is not None and d["date"] < today_iso),
            key=lambda r: r[0],
        )
    except (TypeError, ValueError):
        return None
    closes = [c for _, c in rows]
    if len(closes) < lookback:
        return None
    return closes[-lookback:]


# ---------------------------------------------------------------- collateral guard (pure)
def collateral_guard_ok(reported_collateral: float, width: int, net_debit: float,
                         buying_power: float | None,
                         tolerance: float = COLLATERAL_TOLERANCE_USD,
                         bp_mult: float = BP_COLLATERAL_MULT) -> tuple[bool, str]:
    """Verified live 2026-09-09 (IWM): Robinhood NETS this structure at
    collateral == width*$100 + net_debit (a 9/21 301C/9/30 305C preview came
    back at exactly (305-301)*100 = $400 collateral). `expected` is that
    formula; refuse if the LIVE reported collateral from review_option_order
    exceeds `expected` by more than `tolerance` (Robinhood isn't netting the
    way the verified preview showed -- something changed, don't trust it), or
    if buying_power is under `bp_mult` x the reported collateral.
    buying_power=None (never fetched) always refuses, same never-guess
    convention as daily_cal's diagonal FIT CHECK."""
    expected = width * 100.0 + net_debit
    if reported_collateral > expected + tolerance:
        return False, (f"collateral ${reported_collateral:.2f} exceeds expected "
                        f"${expected:.2f} (width*100+net_debit) by more than ${tolerance:.2f}")
    if buying_power is None:
        return False, "buying_power unknown (no portfolio read this run)"
    if buying_power < bp_mult * reported_collateral:
        return False, (f"buying_power ${buying_power:.2f} < {bp_mult}x collateral "
                        f"${reported_collateral:.2f}")
    return True, "ok"


# ---------------------------------------------------------------- legging state machine (pure)
# Robinhood REJECTS multi-leg orders outright on this agentic account -- verified
# live 2026-09-10 (place_option_order: "Multi-leg options orders aren't supported in
# Robinhood agentic accounts yet."; review_option_order previews fine, the rejection
# only appears at PLACE time). Every spread this bot trades is now placed as TWO
# sequenced single-leg orders: BUY the long (back/protective) leg first, wait for it
# to FILL, THEN sell-to-open the short leg. A short is never opened without its long
# already filled, and a short is never left without its long on the way out either
# -- see exit_leg_action() below. DIAG-PROMPT.md's ENTRY/EXIT/SAFETY sections are the
# reference IMPLEMENTATION (the actual MCP tool calls); these functions are the
# reference DECISION for what to do next given each leg's current state.
LEG_TERMINAL_BAD_STATES = ("no_fill", "rejected", "cancelled")


def entry_leg_action(long_state: str, short_state: str) -> str:
    """Pure decision for ENTRY's sequenced single-leg state machine. States are one
    of 'not_placed'|'pending'|'filled'|'no_fill'|'rejected'|'cancelled'|'unwound'.
    Returns exactly one next action; the caller does ONE of these per run:
      PLACE_LONG    - no long order exists yet -- buy it (limit at the ask)
      POLL_LONG     - long order is out -- check for a fill (reprice/cancel per policy)
      NO_ENTRY      - long never filled -- nothing was ever at risk, stop here
      PLACE_SHORT   - long FILLED, no short order yet -- review, guard, sell-to-open
      POLL_SHORT    - short order is out -- check for a fill
      UNWIND_LONG   - short was rejected/unfilled/cancelled -- sell the long back NOW
      POSITION_OPEN - both legs filled -- the spread exists, nothing more to do
      LEG_UNWOUND   - short failed and the long has already been sold back -- done
    """
    if long_state == "not_placed":
        return "PLACE_LONG"
    if long_state == "pending":
        return "POLL_LONG"
    if long_state in LEG_TERMINAL_BAD_STATES:
        return "NO_ENTRY"
    if long_state != "filled":
        raise ValueError(f"unknown long_state {long_state!r}")
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


def exit_leg_action(short_state: str, long_state: str) -> str:
    """Pure decision for EXIT/SAFETY's sequenced single-leg close: the SHORT closes
    FIRST (buy-to-close), then the LONG (sell-to-close) -- never the reverse, so a
    short is never left naked while its hedge is still open. States: one of
    'open'|'closing'|'closed'.
      CLOSE_SHORT      - short still open -- buy it to close (limit at the ask)
      POLL_SHORT_CLOSE - short's close order is out -- check for a fill
      CLOSE_LONG       - short CLOSED, long still open -- sell it to close (bid)
      POLL_LONG_CLOSE  - long's close order is out -- check for a fill
      DONE             - both legs closed
    """
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
    """A position is HALF-OPEN when its long leg FILLED but the short leg never
    reached 'filled' (still not_placed/pending, or terminally failed/unwound) while
    the position itself is still recorded 'open' -- normally ENTRY's own
    UNWIND_LONG step resolves this within the SAME agent run it happens; this only
    fires from a crash/restart mid-sequence. RECONCILE logs it (HALF-OPEN); SAFETY
    closes the long at the next EXIT window (see DIAG-PROMPT.md)."""
    legs = position.get("legs") or {}
    long_leg = legs.get("long") or {}
    short_leg = legs.get("short") or {}
    return (position.get("state") == "open"
            and long_leg.get("state") == "filled"
            and short_leg.get("state") != "filled")


def single_leg_collateral_guard_ok(reported_collateral: float, width: int, order_checks,
                                    tolerance: float = COLLATERAL_TOLERANCE_USD) -> tuple[bool, str]:
    """SHORT-LEG-ONLY guard for the second (sell-to-open) order in the sequenced
    pair -- replaces the old 2-leg net-debit collateral_guard_ok() for ENTRY (still
    used as-is nowhere now that ENTRY is single-leg, kept below for SAFETY/EXIT's own
    unaffected math). Refuse -- place NOTHING -- if the reported collateral exceeds
    width*$100 by more than `tolerance`, OR if review_option_order's own
    `order_checks` carries ANY alert (empty list/dict/None passes; anything else
    refuses). Unlike the 2-leg guard, there is no net_debit term: the long is already
    owned outright by the time this runs, so the short's own collateral is just the
    covered width."""
    if order_checks:
        return False, f"order_checks not empty: {order_checks}"
    expected = width * 100.0
    if reported_collateral > expected + tolerance:
        return False, (f"collateral ${reported_collateral:.2f} exceeds width*100 "
                        f"${expected:.2f} by more than ${tolerance:.2f}")
    return True, "ok"


# ---------------------------------------------------------------- repricing (pure)
def reprice_entry(mid_debit: float, step: float = 0.05) -> float:
    """Unfilled entry after 3 minutes -> pay $0.05 more (more aggressive to
    fill a debit order)."""
    return round(mid_debit + step, 2)


def reprice_exit(mid_net: float, step: float) -> float:
    """Unfilled exit after 2 minutes (step=0.05), or the 15:04 marketable
    replace (an ADDITIONAL step=0.15 on top of the first reprice) -- both
    subtract from the net (accept a smaller credit / pay more debit, i.e.
    more aggressive to close)."""
    return round(mid_net - step, 2)


# ---------------------------------------------------------------- due-list computation (pure)
def positions_open_count(positions: list[dict], leg_id: str) -> int:
    return sum(1 for p in positions if p.get("leg_id") == leg_id and p.get("state") == "open")


def leg_entry_due(leg: Leg, session_count: int, positions: list[dict], *,
                   leg_halted: bool = False, global_halted: bool = False) -> tuple[bool, str]:
    """Pure: is `leg` due an entry today, given its (already-advanced)
    session_count and the currently open positions book. Order of checks
    matches the spec's own priority (halts first, then config, then
    schedule, then capacity). Capital-based capacity (2026-09-10 ADR
    buying-power-envelopes) is NOT checked here -- it is a DYNAMIC,
    account-value-scaled check applied separately in tick()'s ENTRY block
    via diag_envelope_fit_check(), since it needs a live total_value this
    pure function has no access to. `leg.max_lots` (DIAG_LEGS) remains this
    leg's own static, strategy-level cap on simultaneously open positions."""
    if global_halted:
        return False, "HALTED (global)"
    if leg_halted:
        return False, "HALTED (leg)"
    if not leg.enabled:
        return False, "max_lots=0 (disabled)"
    if not is_entry_due_session(session_count, leg.stagger_k):
        return False, f"not an entry session (session {session_count}, k={leg.stagger_k})"
    open_n = positions_open_count(positions, leg.leg_id)
    if open_n >= leg.max_lots:
        return False, f"MAX_LOTS reached ({open_n}/{leg.max_lots})"
    return True, "due"


# ---------------------------------------------------------------- ENVELOPE check (pure)
# 2026-09-10, ADR buying-power-envelopes: this bot gets a FIXED PERCENTAGE
# share (DIAG_ENVELOPE_PCT, currently 22%) of the Agentic account's live
# total_value -- a dollar figure recomputed every ENTRY tick from the
# total_value RECONCILE caches daily, so it grows with the account instead
# of staying pinned to today's balance. Lot capacity is DERIVED from this
# (floor(envelope_usd / per-lot collateral need), applied incrementally as
# each due leg is checked), not a separately fixed lot count. Usage is
# measured from the bot's OWN reconciled positions book
# (order_state["positions"], confirmed daily against the broker by
# RECONCILE's get_option_positions pull) -- never from free buying power,
# which a different bot can consume entirely (2026-09-09 incident).
# GUARD/EXIT/SAFETY are never touched.
def envelope_usd_from_pct(pct: float, total_value: float) -> float:
    """Dollar envelope = pct/100 x total_value (get_portfolio's total_value
    -- the same number every envelope bot in this account uses, per the
    2026-09-10 ADR). Computed fresh from a same-day cache, never assumed
    stable across days."""
    return round((pct / 100.0) * total_value, 2)


def diag_position_collateral(width: int, qty: int, entry_fill_debit: float) -> float:
    """One open diagonal position's collateral: width x $100 x qty (the
    single short leg's collateral, verified live -- collateral_guard_ok()'s
    same formula) plus its actual net debit if any (a credit is clamped at
    0, never subtracted -- same convention as the collateral guard and
    daily_cal's diagonal_fit_check_stage2)."""
    return round(width * 100.0 * qty + max(entry_fill_debit, 0.0) * 100.0 * qty, 2)


def diag_envelope_usage(positions: list[dict]) -> float:
    """Sum of diag_position_collateral() over every OPEN position in the
    bot's reconciled book -- this IS the broker-measured usage, since
    RECONCILE confirms this list against get_option_positions every
    morning before ENTRY ever runs."""
    total = 0.0
    for p in positions:
        if p.get("state") != "open":
            continue
        total += diag_position_collateral(p.get("width", 0), p.get("qty", 1),
                                            p.get("entry_fill_debit", 0.0))
    return round(total, 2)


def diag_envelope_fit_check(envelope_usd: float, usage_usd: float, needed_usd: float) -> tuple[bool, float]:
    """fits = usage + needed <= envelope. Same (fits, total) shape as
    collateral_guard_ok()-family checks. `usage_usd` must come from
    diag_envelope_usage() -- never from cached buying power."""
    total = round(usage_usd + needed_usd, 2)
    return total <= envelope_usd, total


def positions_due_for_exit(positions: list[dict], today: date,
                            spot_by_ticker: dict[str, float]) -> list[dict]:
    """Every OPEN position whose planned_exit_date has arrived, OR whose
    front leg is ITM-guard-triggered RIGHT NOW (checked fresh every call, any
    day, not just a position's own scheduled exit day) -- both reasons can
    apply to the same position, both are recorded in `exit_reasons`. Returns
    each due position augmented with `exit_reasons`; does not mutate input."""
    due = []
    for p in positions:
        if p.get("state") != "open":
            continue
        reasons = []
        ped = p.get("planned_exit_date")
        if ped and date.fromisoformat(ped) <= today:
            reasons.append("planned")
        spot = spot_by_ticker.get(p.get("ticker"))
        ks = p.get("ks")
        if spot is not None and ks is not None and itm_guard_triggered(spot, ks):
            reasons.append("itm_guard")
        if reasons:
            due.append({**p, "exit_reasons": reasons})
    return due


def positions_at_expiry_open_risk(positions: list[dict], today: date) -> list[dict]:
    """Every OPEN position whose front leg expires TODAY -- SAFETY mode's
    trigger list."""
    out = []
    for p in positions:
        if p.get("state") != "open":
            continue
        fe = p.get("front_expiry")
        if fe and expiry_day_open_risk(today, date.fromisoformat(fe)):
            out.append(p)
    return out


# ---------------------------------------------------------------- halt (pure-ish, reads state)
def is_globally_halted(order_state: dict, cfg: Cfg) -> bool:
    return bool(cfg.halted_env) or bool((order_state.get("halt") or {}).get("active"))


def is_leg_halted(order_state: dict, leg_id: str) -> bool:
    return bool(((order_state.get("leg_halts") or {}).get(leg_id) or {}).get("active"))


# ---------------------------------------------------------------- mode decision (pure)
def decide(now: datetime, day: dict) -> tuple[str | None, str]:
    """Pure: (mode, reason). day = order_state[today] (may be {}). No market-
    holiday calendar consulted here (mirrors daily_cal's decide() -- safety
    on a holiday comes from downstream: nothing due, so ENTRY/EXIT/SAFETY all
    resolve as pure no-ops that same tick, never a crash or a misfire)."""
    t = now.time()
    if now.weekday() >= 5:
        return None, "weekend"
    if not (WINDOW_START_CT <= t <= WINDOW_END_CT):
        return None, "outside window"

    safety = day.get("safety") or {}
    reconcile = day.get("reconcile") or {}
    entry = day.get("entry") or {}
    exit_ = day.get("exit") or {}

    if not safety.get("done"):
        if t < SAFETY_AT_CT:
            return None, "before safety time"
        return "SAFETY", "expiry-day-open guard check"

    if not reconcile.get("done"):
        if t < RECONCILE_AT_CT:
            return None, "safety done, before reconcile time"
        return "RECONCILE", "reconcile positions/orders vs order_state"

    if not entry.get("done"):
        if t < ENTRY_START_CT:
            return None, "reconcile done, before entry time"
        return "ENTRY", "entry window"

    if not exit_.get("done"):
        if t < EXIT_START_CT:
            return None, "entry done, before exit time"
        return "EXIT", "exit window"

    return None, "day complete"


# ---------------------------------------------------------------- signal + prompt
def build_signal(now: datetime, mode: str, day: dict, order_state: dict, cfg: Cfg) -> dict:
    today_iso = now.date().isoformat()
    positions = order_state.get("positions") or []
    sig = {
        "mode": mode, "now_ct": now.isoformat(timespec="seconds"), "today": today_iso,
        "account": ACCOUNT, "armed": int(cfg.armed), "dry_run": int(cfg.dry_run),
        "entry_start_ct": ENTRY_START_CT.strftime("%H:%M"),
        "entry_reprice_after_min": ENTRY_REPRICE_AFTER_MIN,
        "entry_cutoff_ct": ENTRY_CUTOFF_CT.strftime("%H:%M"),
        "exit_start_ct": EXIT_START_CT.strftime("%H:%M"),
        "exit_reprice_after_min": EXIT_REPRICE_AFTER_MIN,
        "exit_market_at_ct": EXIT_MARKET_AT_CT.strftime("%H:%M"),
        "itm_guard_usd": ITM_GUARD_USD,
        "back_expiry_search_days": BACK_EXPIRY_SEARCH_DAYS,
        "collateral_tolerance_usd": COLLATERAL_TOLERANCE_USD,
        "bp_collateral_mult": BP_COLLATERAL_MULT,
        "fee_per_contract": cfg.fee_per_contract,
    }
    if mode == "SAFETY":
        sig["at_risk_positions"] = positions_at_expiry_open_risk(positions, now.date())
    elif mode == "RECONCILE":
        sig["known_open_positions"] = [p for p in positions if p.get("state") == "open"]
    elif mode == "ENTRY":
        due_ids = (day.get("entry") or {}).get("due_leg_ids") or []
        legs_by_id = {leg.leg_id: leg for leg in cfg.legs}
        due_legs = []
        for lid in due_ids:
            leg = legs_by_id.get(lid)
            if leg is None:
                continue
            leg_day = (day.get("entry") or {}).get(lid) or {}
            if leg_day.get("done"):
                continue
            due_legs.append({
                "leg_id": lid, "ticker": leg.ticker, "front_dte_min": leg.front_dte_min,
                "back_dte_min": leg.back_dte_min, "width": leg.width,
                "open_lots": positions_open_count(positions, lid),
                "max_lots": leg.max_lots,
            })
        sig["due_legs"] = due_legs
    elif mode == "EXIT":
        # positions_due_for_exit()'s ITM-guard half needs a LIVE spot per
        # ticker, which Python doesn't have here -- the agent is instructed
        # (DIAG-PROMPT.md) to pull get_equity_quotes for every distinct
        # ticker among open_positions and apply itm_guard_triggered() /
        # positions_due_for_exit() itself using those live spots, merging the
        # result with `due_position_ids_planned` below (never guessing a spot
        # in Python). Every open position is handed over so the agent can run
        # that check on all of them, not just the ones already date-due.
        open_positions = [p for p in positions if p.get("state") == "open"]
        sig["open_positions"] = open_positions
        sig["due_position_ids_planned"] = [
            p["id"] for p in open_positions
            if p.get("planned_exit_date") and date.fromisoformat(p["planned_exit_date"]) <= now.date()
        ]
    # Every order is now single-leg (Robinhood rejects multi-leg orders on this
    # account, verified live 2026-09-10) -- one ref_id per LEG PER SIDE of the
    # sequence, not one per leg/position overall.
    keys = day.setdefault("ref_ids", {})
    if mode == "ENTRY":
        for lid in sig.get("due_legs", []):
            base = lid["leg_id"]
            keys.setdefault(f"entry_{base}_long", str(uuid.uuid4()))
            keys.setdefault(f"entry_{base}_short", str(uuid.uuid4()))
            keys.setdefault(f"entry_{base}_unwind", str(uuid.uuid4()))
    if mode == "EXIT":
        for p in sig.get("open_positions", []):
            keys.setdefault(f"exit_{p['id']}_short", str(uuid.uuid4()))
            keys.setdefault(f"exit_{p['id']}_long", str(uuid.uuid4()))
    if mode == "SAFETY":
        for p in sig.get("at_risk_positions", []):
            keys.setdefault(f"safety_{p['id']}_short", str(uuid.uuid4()))
            keys.setdefault(f"safety_{p['id']}_long", str(uuid.uuid4()))
    sig["ref_ids"] = keys
    return sig


def render_prompt(sig: dict) -> str:
    tmpl = PROMPT_MD.read_text(encoding="utf-8")
    return tmpl.replace("__SIGNAL_JSON__", json.dumps(sig, indent=2))


# ---------------------------------------------------------------- allowlist gate (pure)
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
    # Prompt over STDIN, never argv -- same Windows CreateProcess command-line
    # length limit daily_cal's run_agent() documents (WinError 206).
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
    """A trade word only counts right after the `| MODE | ` separator (e.g.
    `| OPEN IWM ...`, `| CLOSE ...`, `| SOLD ...`, `| MARKET-CLOSE ...`) --
    NOT a bare substring match, because plain English log lines legitimately
    contain the word "open" (e.g. RECONCILE's "N open positions confirmed")
    without any money having moved."""
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


# ---------------------------------------------------------------- ledger
LEDGER_COLS = ["trade_date", "leg_id", "ticker", "front_expiry", "back_expiry", "ks", "kb",
               "width", "qty", "entry_date", "entry_fill_debit", "exit_fill_net",
               "pnl_fill_to_fill", "fees_est", "dry_run", "exit_reasons"]


def position_pnl(entry_fill_debit: float, exit_fill_net: float, qty: int,
                  fee_per_contract: float, fees_contracts: int = 4) -> float:
    """entry_fill_debit is always a positive debit paid (per spec, ENTRY is
    always a net-debit order). exit_fill_net follows the same sign
    convention as daily_cal's diagonal fill_debit: positive = a debit PAID to
    close, negative = a credit RECEIVED to close. pnl = (what we collected)
    minus (what we paid) minus fees: collected/paid nets to
    -(exit_fill_net) - entry_fill_debit, in dollars per contract, x100 x qty.
    fees_contracts defaults to 4 (2 legs to open, 2 legs to close) -- a
    position that also tripped an early SAFETY/ITM close still only trades
    those same 4 legs once each, so 4 is correct for every normal lifecycle
    (no separate "guard" leg exists in this structure, unlike daily_cal's
    calendar which can additionally trigger a 5th buy-to-close leg)."""
    gross = round((-(exit_fill_net) - entry_fill_debit) * 100 * qty, 2)
    fees = round(fee_per_contract * fees_contracts * qty, 4)
    return round(gross - fees, 2)


def ledger_row(position: dict, *, fee_per_contract: float = 0.0) -> dict | None:
    if position.get("state") != "closed":
        return None
    exit_ = position.get("exit") or {}
    entry_debit = position.get("entry_fill_debit")
    exit_net = exit_.get("fill_net")
    if entry_debit is None or exit_net is None:
        return None
    qty = int(position.get("qty") or 1)
    pnl = position_pnl(float(entry_debit), float(exit_net), qty, fee_per_contract)
    return {
        "trade_date": exit_.get("closed_date"), "leg_id": position.get("leg_id"),
        "ticker": position.get("ticker"), "front_expiry": position.get("front_expiry"),
        "back_expiry": position.get("back_expiry"), "ks": position.get("ks"),
        "kb": position.get("kb"), "width": position.get("width"), "qty": qty,
        "entry_date": position.get("entry_date"), "entry_fill_debit": entry_debit,
        "exit_fill_net": exit_net, "pnl_fill_to_fill": pnl,
        "fees_est": round(fee_per_contract * 4 * qty, 4),
        "dry_run": int(bool(position.get("dry_run"))),
        "exit_reasons": ",".join(exit_.get("reasons") or []),
    }


def append_ledger(row: dict) -> None:
    import csv
    new = not LEDGER_CSV.exists()
    with LEDGER_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        if new:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------- main tick
def tick(now: datetime, cfg: Cfg, *, dry_run_cli: bool = False, forced_mode: str | None = None,
         force_rerun: bool = False) -> int:
    today = now.date().isoformat()
    order_state = load_json(ORDER_STATE)
    day = order_state.get(today) or {}
    global_halted = is_globally_halted(order_state, cfg)

    if forced_mode:
        mode, why = forced_mode, "--once (manual, bypasses clock gating)"
        already = bool((day.get(MODE_STATE_KEY.get(mode, "")) or {}).get("done"))
        if already and not force_rerun:
            print(f"REFUSED: {mode} already recorded for today ({today}). "
                  f"Use --force to re-run (dry-run only).")
            return 2
        if already and force_rerun and not cfg.dry_run:
            print("REFUSED: --force only re-runs a recorded mode when dry_run is True "
                  "(DIAG_DRY_RUN=1 in .env or --dry-run on the command line). Refusing to "
                  "re-fire a live mode.")
            return 2
    else:
        mode, why = decide(now, day)
    print(f"{now.isoformat(timespec='seconds')} CT | mode={mode} | {why} | "
          f"armed={int(cfg.armed)} dry_run={int(cfg.dry_run)} global_halted={int(global_halted)}")
    if mode is None:
        return 0

    positions = order_state.get("positions") or []

    # ---- SAFETY: pure Python no-op if nothing is at expiry-day-open risk ----
    if mode == "SAFETY":
        at_risk = positions_at_expiry_open_risk(positions, now.date())
        if not at_risk:
            day["safety"] = {"done": True, "count": 0}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = (f"{now.isoformat(timespec='seconds')} CT | SAFETY | no positions at "
                     f"expiry-day-open risk")
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("good", line)
            if forced_mode:
                print(line)
            return 0
        # else fall through to the agent below -- at_risk positions get closed
        # and their legs halted; day["safety"]["done"] is set by this run
        # unconditionally (a single-shot market-order close, not a poll loop).

    # ---- ENTRY: snapshot due legs ONCE per day, before the agent is ever ---
    # invoked. Session counters advance here too (idempotent per leg per day)
    # -- this happens even on a day nothing is due, so a leg's cadence keeps
    # counting.
    if mode == "ENTRY":
        legs_state = order_state.setdefault("legs", {})
        for leg in cfg.legs:
            legs_state[leg.leg_id] = advance_session_counter(
                legs_state.get(leg.leg_id) or {}, today)
        order_state["legs"] = legs_state
        entry_day = day.setdefault("entry", {})
        if "due_leg_ids" not in entry_day:
            due_ids = []
            # ---- ENVELOPE: Python-only, before the agent is ever invoked ----
            # (2026-09-10 ADR buying-power-envelopes; PERCENTAGE-based so the
            # envelope grows with the account). Usage is measured from this
            # bot's own reconciled positions book (broker-confirmed by
            # RECONCILE every morning), never free buying power. total_value
            # is RECONCILE's own same-day cache (get_portfolio, the same
            # field every envelope bot uses) -- missing it fails EVERY leg
            # closed, never guessed. Running usage total reserves capacity
            # for legs earlier in this same due-list so two legs due the
            # same day can't both "fit" against the same headroom.
            total_value = (day.get("total_value") or {}).get("value")
            env_usage_running = diag_envelope_usage(positions)
            envelope_usd = (envelope_usd_from_pct(cfg.envelope_pct, total_value)
                             if total_value is not None else None)
            iwm_prior_closes = None
            iwm_prior_closes_fetched = False
            for leg in cfg.legs:
                sc = legs_state[leg.leg_id]["session_count"]
                leg_halted = is_leg_halted(order_state, leg.leg_id)
                due, reason = leg_entry_due(leg, sc, positions, leg_halted=leg_halted,
                                             global_halted=global_halted)
                # IWM RV5 stand-down (pre-registered 2026-09-24, CLUSTER_calldiag_iwm.py):
                # checked right after schedule/capacity, before the envelope check --
                # a market-state gate, never touching exits or open positions. Only
                # fetches the live closes once per tick, and only if an IWM leg is
                # actually otherwise due (never spends a network call for nothing).
                if due and leg.ticker == "IWM":
                    if not iwm_prior_closes_fetched:
                        iwm_prior_closes = fetch_iwm_prior_closes(now.date())
                        iwm_prior_closes_fetched = True
                    standdown, sd_reason = iwm_standdown_check(iwm_prior_closes, cfg.iwm_rv5_standdown)
                    if standdown:
                        due = False
                        reason = sd_reason
                if due:
                    env_needed = round(leg.width * 100.0, 2)
                    if envelope_usd is None:
                        due = False
                        reason = "ENVELOPE: total_value never cached (RECONCILE didn't run/cache it today)"
                    else:
                        env_fits, env_total = diag_envelope_fit_check(envelope_usd,
                                                                        env_usage_running, env_needed)
                        if not env_fits:
                            due = False
                            reason = (f"ENVELOPE: usage ${env_usage_running:.2f} + need "
                                      f"${env_needed:.2f} > ${envelope_usd:.2f}")
                        else:
                            env_usage_running = round(env_usage_running + env_needed, 2)
                if due:
                    due_ids.append(leg.leg_id)
                else:
                    entry_day[leg.leg_id] = {"done": True, "state": "skipped", "skipped": reason}
                    if reason.startswith("ENVELOPE:") or reason.startswith("STANDDOWN_IWM_RV5"):
                        line = (f"{now.isoformat(timespec='seconds')} CT | ENTRY | NO-OP: "
                                 f"{reason} (leg={leg.leg_id}); refusing entry, never calls "
                                 f"the agent for this leg")
                        LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
                        notify("bad", line)
            entry_day["due_leg_ids"] = due_ids
            day["entry"] = entry_day
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
        due_ids = entry_day.get("due_leg_ids") or []
        unresolved = [lid for lid in due_ids if not (entry_day.get(lid) or {}).get("done")]
        if not unresolved:
            entry_day["done"] = True
            day["entry"] = entry_day
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = (f"{now.isoformat(timespec='seconds')} CT | ENTRY | no legs due today"
                    if not due_ids else
                    f"{now.isoformat(timespec='seconds')} CT | ENTRY | all due legs resolved")
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("good", line)
            if forced_mode:
                print(line)
            return 0
        # else fall through to the agent with the unresolved due legs

    # ---- EXIT: recomputed fresh every tick -- nothing due is a pure no-op --
    if mode == "EXIT":
        open_positions = [p for p in positions if p.get("state") == "open"]
        due_planned = [p["id"] for p in open_positions
                       if p.get("planned_exit_date")
                       and date.fromisoformat(p["planned_exit_date"]) <= now.date()]
        # The ITM-guard half needs a LIVE spot per ticker -- Python cannot
        # compute it without calling the broker, so a position is treated as
        # "possibly due" for the agent to check itself whenever ANY position
        # is open; if genuinely nothing is open, this is a pure no-op.
        if not open_positions:
            day["exit"] = {"done": True, "count": 0}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = f"{now.isoformat(timespec='seconds')} CT | EXIT | no open positions"
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("good", line)
            if forced_mode:
                print(line)
            return 0
        # else fall through to the agent with every open position (it applies
        # the live-spot ITM check itself, per DIAG-PROMPT.md) plus the
        # planned-date list this driver already knows.

    sig = build_signal(now, mode, day, order_state, cfg)
    order_state[today] = day
    if dry_run_cli:
        print("[--dry-run] would run the agent with signal:")
        print(json.dumps(sig, indent=2))
        return 0
    save_json(ORDER_STATE, order_state)  # ref_ids + snapshots persist before the agent runs

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
                     f"- check call_diag/run-output.log")
        LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
        notify("bad", line)
        if forced_mode:
            print(line)
        return 1
    notify(tone_for(post), post)
    if forced_mode:
        print(post)

    # ---- post-agent bookkeeping: SAFETY/ENTRY/EXIT are marked "done" for ---
    # the day only once the agent has actually resolved everything it was
    # handed. The agent itself is instructed (DIAG-PROMPT.md) to write these
    # exact keys, so this is a read-back + fallback-completion pass, mirroring
    # daily_cal's own read-back convention after run_agent().
    order_state = load_json(ORDER_STATE)
    day = order_state.get(today) or {}
    if mode == "SAFETY":
        day.setdefault("safety", {})["done"] = True
        order_state[today] = day
        save_json(ORDER_STATE, order_state)
    if mode == "ENTRY":
        entry_day = day.setdefault("entry", {})
        due_ids = entry_day.get("due_leg_ids") or []
        if all((entry_day.get(lid) or {}).get("done") for lid in due_ids) or now.time() >= ENTRY_CUTOFF_CT:
            entry_day["done"] = True
        order_state[today] = day
        save_json(ORDER_STATE, order_state)
    if mode == "EXIT":
        positions = order_state.get("positions") or []
        still_open = [p for p in positions if p.get("state") == "open"]
        if not still_open or now.time() >= EXIT_MARKET_AT_CT:
            day.setdefault("exit", {})["done"] = True
        order_state[today] = day
        save_json(ORDER_STATE, order_state)

    # ---- ledger: append a row for every position that closed and hasn't ----
    # been ledgered yet.
    order_state = load_json(ORDER_STATE)
    positions = order_state.get("positions") or []
    changed = False
    for p in positions:
        if p.get("state") == "closed" and not p.get("ledgered"):
            row = ledger_row(p, fee_per_contract=cfg.fee_per_contract)
            if row:
                append_ledger(row)
                p["ledgered"] = True
                changed = True
    if changed:
        order_state["positions"] = positions
        save_json(ORDER_STATE, order_state)

    return 0


def reset_halt(cfg: Cfg, leg_id: str | None = None) -> int:
    """Manual-only. Refuses unless .env already has DIAG_HALTED=0. Without
    --leg, clears the GLOBAL halt; with --leg, clears only that leg's
    automatic halt (order_state["leg_halts"][leg_id]) -- the bot never clears
    either itself."""
    if cfg.halted_env:
        print("REFUSED: .env still has DIAG_HALTED=1. Set DIAG_HALTED=0 first.")
        return 2
    order_state = load_json(ORDER_STATE)
    if leg_id:
        leg_halts = order_state.setdefault("leg_halts", {})
        leg_halts[leg_id] = {"active": False}
        order_state["leg_halts"] = leg_halts
        msg = f"leg halt cleared for {leg_id}"
    else:
        order_state["halt"] = {"active": False}
        msg = "global halt cleared"
    save_json(ORDER_STATE, order_state)
    line = f"{datetime.now(CT).isoformat(timespec='seconds')} CT | RESET | {msg}"
    LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
    print(msg)
    return 0


# ---------------------------------------------------------------- unit tests
def _unit_tests() -> int:
    # ---- leg parsing ----
    legs = parse_legs(DEFAULT_LEGS)
    assert len(legs) == 4
    iwm = legs[0]
    assert iwm.ticker == "IWM" and iwm.front_dte_min == 10 and iwm.back_dte_min == 20
    assert iwm.width == 1 and iwm.stagger_k == 3 and iwm.max_lots == 2
    assert iwm.enabled is True
    assert iwm.leg_id == "IWM_10_20"
    spy_legs = [l for l in legs if l.ticker == "SPY"]
    assert len(spy_legs) == 2
    assert spy_legs[0].leg_id != spy_legs[1].leg_id  # 10/20 vs 21/42, distinct ids
    assert all(not l.enabled for l in legs if l.ticker != "IWM")
    assert parse_legs("BAD:1:2") == []          # wrong field count -> skipped
    assert parse_legs("BAD:x:2:1:3:2") == []    # non-integer field -> skipped
    assert parse_legs("") == []

    # ---- expiry selection: first listed with dte >= min ----
    today = date(2026, 9, 9)
    exps = [date(2026, 9, 11), date(2026, 9, 18), date(2026, 9, 25), date(2026, 10, 2)]
    assert select_front_expiry(exps, today, 10) == date(2026, 9, 25)  # dte 2,9,16,23 -> first>=10 is 16
    assert select_front_expiry(exps, today, 0) == date(2026, 9, 11)
    assert select_front_expiry(exps, today, 999) is None

    # ---- back expiry candidate search + strike existence ----
    front = date(2026, 9, 25)  # dte 16
    back_exps = [date(2026, 9, 25), date(2026, 10, 2), date(2026, 10, 9), date(2026, 10, 16)]
    # dte: 16(=front, excluded), 23, 30, 37
    cands = candidate_back_expiries(back_exps, today, back_dte_min=20, front_expiry=front,
                                     search_days=10)
    assert cands == [date(2026, 10, 2), date(2026, 10, 9)]  # dte 23,30 in [20,30]; 37 excluded
    strikes_by_exp = {date(2026, 10, 2): [300, 304, 308], date(2026, 10, 9): [300, 305, 310]}
    assert select_back_expiry_with_strike(cands, strikes_by_exp, 305) == date(2026, 10, 9)
    assert select_back_expiry_with_strike(cands, strikes_by_exp, 999) is None  # never listed -> skip

    # ---- EM / strike selection ----
    assert em_from_quotes(1.10, 1.05) == 2.15
    strikes = [295, 298, 300, 301, 302, 305, 310]
    assert nearest_strike(300.4, strikes) == 300
    assert nearest_strike(300.5, [300, 301]) == 300  # tie -> lower
    assert ceil_listed_strike(300.6, strikes) == 301
    assert ceil_listed_strike(311, strikes) is None
    ks = short_strike(spot=298.5, em=2.4, strikes=strikes)  # target 300.9 -> ceil 301
    assert ks == 301
    assert long_strike_target(301, 4) == 305

    # ---- stagger / session counter ----
    assert is_entry_due_session(1, 3) is True
    assert is_entry_due_session(2, 3) is False
    assert is_entry_due_session(3, 3) is False
    assert is_entry_due_session(4, 3) is True   # k+1
    assert is_entry_due_session(7, 3) is True   # 2k+1
    assert is_entry_due_session(0, 3) is False
    assert is_entry_due_session(1, 0) is False  # k<1 never due
    st = {}
    st = advance_session_counter(st, "2026-09-09")
    assert st == {"session_count": 1, "last_session_date": "2026-09-09"}
    st_same_day = advance_session_counter(st, "2026-09-09")
    assert st_same_day == st  # idempotent, same day
    st2 = advance_session_counter(st, "2026-09-10")
    assert st2 == {"session_count": 2, "last_session_date": "2026-09-10"}

    # ---- leg_entry_due: halts, disabled, schedule, capacity, in that order ----
    leg = Leg("IWM", 10, 20, 1, 3, 2)
    assert leg_entry_due(leg, 1, [])[0] is True
    assert leg_entry_due(leg, 1, [], global_halted=True) == (False, "HALTED (global)")
    assert leg_entry_due(leg, 1, [], leg_halted=True) == (False, "HALTED (leg)")
    disabled = Leg("SPY", 10, 20, 1, 3, 0)
    assert leg_entry_due(disabled, 1, [])[0] is False
    assert leg_entry_due(leg, 2, [])[0] is False  # not a due session
    full = [{"leg_id": "IWM_10_20", "state": "open"}, {"leg_id": "IWM_10_20", "state": "open"}]
    assert leg_entry_due(leg, 1, full) == (False, "MAX_LOTS reached (2/2)")
    one_open = [{"leg_id": "IWM_10_20", "state": "open"}]
    assert leg_entry_due(leg, 1, one_open)[0] is True

    # ---- planned exit date: last trading session strictly before expiry ----
    assert is_trading_day(date(2026, 9, 7)) is False   # Labor Day
    assert is_trading_day(date(2026, 9, 8)) is True
    assert planned_exit_date(date(2026, 9, 21)) == date(2026, 9, 18)  # Mon -> prior Fri
    assert planned_exit_date(date(2026, 9, 8)) == date(2026, 9, 4)    # Tue after Labor Day -> prior Fri
    assert prior_trading_session(date(2026, 9, 9)) == date(2026, 9, 8)

    # ---- ITM safety trigger ----
    assert itm_guard_triggered(spot=302.5, ks=301) is True   # +1.50 > $1.00
    assert itm_guard_triggered(spot=301.9, ks=301) is False  # +0.90, not > $1.00
    assert itm_guard_triggered(spot=301.0, ks=301) is False  # exactly ATM, not ITM
    assert itm_guard_triggered(spot=299.0, ks=301) is False  # OTM

    # ---- expiry-day-open risk ----
    assert expiry_day_open_risk(date(2026, 9, 25), date(2026, 9, 25)) is True
    assert expiry_day_open_risk(date(2026, 9, 24), date(2026, 9, 25)) is False
    assert expiry_day_open_risk(date(2026, 9, 26), date(2026, 9, 25)) is True  # overdue is still risk

    # ---- due-list helpers over a positions book ----
    positions = [
        {"id": "p1", "leg_id": "IWM_10_20", "ticker": "IWM", "state": "open",
         "planned_exit_date": "2026-09-08", "ks": 310, "front_expiry": "2026-09-25"},
        {"id": "p2", "leg_id": "IWM_10_20", "ticker": "IWM", "state": "open",
         "planned_exit_date": "2026-09-30", "ks": 295, "front_expiry": "2026-09-09"},
        {"id": "p3", "leg_id": "SPY_10_20", "ticker": "SPY", "state": "closed",
         "planned_exit_date": "2026-09-01", "ks": 640, "front_expiry": "2026-09-02"},
    ]
    due = positions_due_for_exit(positions, date(2026, 9, 9), {"IWM": 302.5, "SPY": 650})
    due_ids = {d["id"]: d["exit_reasons"] for d in due}
    assert due_ids["p1"] == ["planned"]                       # date passed, not ITM
    assert set(due_ids["p2"]) == {"itm_guard"}                # spot 302.5 > 295+1
    assert "p3" not in due_ids                                # already closed, excluded
    at_risk = positions_at_expiry_open_risk(positions, date(2026, 9, 9))
    assert [p["id"] for p in at_risk] == ["p2"]                # front_expiry == today, still open

    # ---- collateral guard: verified-live IWM formula, width*100+net_debit ----
    ok, reason = collateral_guard_ok(reported_collateral=400.0, width=4, net_debit=0.0,
                                      buying_power=1000.0)
    assert ok is True and reason == "ok"
    ok2, reason2 = collateral_guard_ok(reported_collateral=420.0, width=4, net_debit=0.0,
                                        buying_power=1000.0)  # 420 > 400+5
    assert ok2 is False and "exceeds expected" in reason2
    ok3, reason3 = collateral_guard_ok(reported_collateral=400.0, width=4, net_debit=0.0,
                                        buying_power=500.0)   # 500 < 1.5*400=600
    assert ok3 is False and "buying_power" in reason3
    ok4, reason4 = collateral_guard_ok(reported_collateral=400.0, width=4, net_debit=0.0,
                                        buying_power=None)
    assert ok4 is False and "unknown" in reason4
    # net_debit shifts the expected floor
    ok5, _ = collateral_guard_ok(reported_collateral=405.0, width=4, net_debit=5.0,
                                  buying_power=1000.0)  # expected = 405, 405<=405+5
    assert ok5 is True

    # ---- repricing ----
    assert reprice_entry(1.05) == 1.10
    assert reprice_exit(0.50, 0.05) == 0.45
    assert reprice_exit(-0.90, 0.05) == -0.95   # a credit gets LESS generous, more aggressive
    assert reprice_exit(0.45, 0.15) == 0.30

    # ---- legging state machine: sequenced single-leg ENTRY/EXIT (Robinhood ---
    # rejects multi-leg orders on this agentic account, verified live 2026-09-10)
    assert entry_leg_action("not_placed", "not_placed") == "PLACE_LONG"
    assert entry_leg_action("pending", "not_placed") == "POLL_LONG"
    assert entry_leg_action("no_fill", "not_placed") == "NO_ENTRY"
    assert entry_leg_action("rejected", "not_placed") == "NO_ENTRY"
    assert entry_leg_action("filled", "not_placed") == "PLACE_SHORT"
    assert entry_leg_action("filled", "pending") == "POLL_SHORT"
    assert entry_leg_action("filled", "rejected") == "UNWIND_LONG"        # short rejected -> unwind
    assert entry_leg_action("filled", "no_fill") == "UNWIND_LONG"         # short unfilled -> unwind
    assert entry_leg_action("filled", "filled") == "POSITION_OPEN"        # both filled -> position
    assert entry_leg_action("filled", "unwound") == "LEG_UNWOUND"
    try:
        entry_leg_action("bogus", "not_placed")
        assert False, "unknown long_state must raise"
    except ValueError:
        pass

    # ---- exit sequencing: short closes FIRST, then long ----
    assert exit_leg_action("open", "open") == "CLOSE_SHORT"
    assert exit_leg_action("closing", "open") == "POLL_SHORT_CLOSE"
    assert exit_leg_action("closed", "open") == "CLOSE_LONG"              # short gone -> now the long
    assert exit_leg_action("closed", "closing") == "POLL_LONG_CLOSE"
    assert exit_leg_action("closed", "closed") == "DONE"
    try:
        exit_leg_action("bogus", "open")
        assert False, "unknown short_state must raise"
    except ValueError:
        pass

    # ---- half-open detection ----
    assert is_half_open_position({"state": "open",
                                   "legs": {"long": {"state": "filled"}, "short": {"state": "rejected"}}})
    assert is_half_open_position({"state": "open",
                                   "legs": {"long": {"state": "filled"}, "short": {"state": "not_placed"}}})
    assert not is_half_open_position({"state": "open",
                                       "legs": {"long": {"state": "filled"}, "short": {"state": "filled"}}})
    assert not is_half_open_position({"state": "closed",
                                       "legs": {"long": {"state": "filled"}, "short": {"state": "rejected"}}})
    assert not is_half_open_position({"state": "open", "legs": {"long": {"state": "not_placed"}}})

    # ---- single-leg collateral guard (SHORT leg only, no net_debit term) ----
    ok6, reason6 = single_leg_collateral_guard_ok(reported_collateral=100.0, width=1, order_checks=None)
    assert ok6 is True and reason6 == "ok"
    ok7, reason7 = single_leg_collateral_guard_ok(reported_collateral=106.0, width=1, order_checks=None)
    assert ok7 is False and "exceeds width*100" in reason7               # 106 > 100+5
    ok8, reason8 = single_leg_collateral_guard_ok(reported_collateral=100.0, width=1,
                                                    order_checks=["ALERT: something"])
    assert ok8 is False and "order_checks not empty" in reason8
    ok9, _ = single_leg_collateral_guard_ok(reported_collateral=100.0, width=1, order_checks=[])
    assert ok9 is True                                                    # empty list passes
    ok10, _ = single_leg_collateral_guard_ok(reported_collateral=100.0, width=1, order_checks={})
    assert ok10 is True                                                   # empty dict passes

    # ---- allowlist gate ----
    unarmed = build_allowlist(Cfg(armed=False, dry_run=True))
    armed_dry = build_allowlist(Cfg(armed=True, dry_run=True))
    armed_live = build_allowlist(Cfg(armed=True, dry_run=False))
    for tools in (unarmed, armed_dry):
        assert "mcp__robinhood-trading__place_option_order" not in tools
        assert "mcp__robinhood-trading__cancel_option_order" not in tools
    assert "mcp__robinhood-trading__place_option_order" in armed_live
    assert "mcp__robinhood-trading__cancel_option_order" in armed_live

    # ---- decide(): mode timing ----
    d = datetime(2026, 9, 9, 8, 30, tzinfo=CT)  # Wednesday
    assert decide(d.replace(hour=8, minute=29), {})[0] is None       # before window
    assert decide(d.replace(hour=8, minute=31), {})[0] == "SAFETY"
    assert decide(d.replace(hour=8, minute=30), {})[0] is None       # before safety time
    safety_done = {"safety": {"done": True}}
    assert decide(d.replace(hour=8, minute=32), safety_done)[0] is None   # before reconcile
    assert decide(d.replace(hour=8, minute=33), safety_done)[0] == "RECONCILE"
    recon_done = {**safety_done, "reconcile": {"done": True}}
    assert decide(d.replace(hour=8, minute=34), recon_done)[0] is None    # before entry
    assert decide(d.replace(hour=8, minute=35), recon_done)[0] == "ENTRY"
    entry_done = {**recon_done, "entry": {"done": True}}
    assert decide(d.replace(hour=14, minute=58), entry_done)[0] is None   # before exit
    assert decide(d.replace(hour=14, minute=59), entry_done)[0] == "EXIT"
    all_done = {**entry_done, "exit": {"done": True}}
    assert decide(d.replace(hour=15, minute=0), all_done)[0] is None      # day complete
    weekend = datetime(2026, 9, 12, 8, 33, tzinfo=CT)
    assert decide(weekend, {})[0] is None
    assert decide(d.replace(hour=15, minute=7), {})[0] is None            # after window

    # ---- ledger P&L ----
    closed_pos = {"state": "closed", "leg_id": "IWM_10_20", "ticker": "IWM",
                  "front_expiry": "2026-09-25", "back_expiry": "2026-10-09",
                  "ks": 301, "kb": 305, "width": 4, "qty": 1, "entry_date": "2026-09-09",
                  "entry_fill_debit": 1.05, "dry_run": False,
                  "exit": {"closed_date": "2026-09-18", "fill_net": -0.30, "reasons": ["planned"]}}
    row = ledger_row(closed_pos, fee_per_contract=0.04)
    assert row is not None
    assert row["pnl_fill_to_fill"] == position_pnl(1.05, -0.30, 1, 0.04)
    assert round((0.30 - 1.05) * 100 - 0.04 * 4, 2) == row["pnl_fill_to_fill"]
    assert ledger_row({"state": "open"}) is None

    # ---- IWM RV5 stand-down: threshold boundary, prior-close-only, missing data ----
    flat = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]   # zero vol -> rv5 == 0.0
    assert iwm_rv5(flat) == 0.0
    assert iwm_rv5([100.0] * 5) is None                 # only 5 closes -> 4 returns, insufficient
    up = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0]      # alternating +1%/-0.99%, nonzero rv5
    rv5_up = iwm_rv5(up)
    assert rv5_up is not None and rv5_up > 0.0
    # boundary: rv5 <= threshold stands down, rv5 > threshold does not (spec's own "<=")
    standdown_at, reason_at = iwm_standdown_check(flat, threshold=0.0)
    assert standdown_at is True and reason_at == "STANDDOWN_IWM_RV5 0.0000"
    standdown_below, _ = iwm_standdown_check(flat, threshold=0.01)
    assert standdown_below is True                       # 0.0 <= 0.01
    standdown_above, reason_above = iwm_standdown_check(up, threshold=0.0001)
    assert standdown_above is False and "ok" in reason_above   # rv5_up > tiny threshold
    # prior-close-only: only the LAST 6 elements of a longer list matter -- extra
    # leading closes (which would represent same-day/extra data) must never change
    # the result, since the caller is contracted to hand over exactly the closes
    # ending at the prior session (never today's own).
    padded = [999.0, 999.0] + up
    assert iwm_rv5(padded) == rv5_up
    # missing data always fails closed -- never trades blind
    assert iwm_standdown_check(None) == (True, "STANDDOWN_IWM_RV5 unknown (no closes)")
    assert iwm_standdown_check([]) == (True, "STANDDOWN_IWM_RV5 unknown (no closes)")
    assert iwm_standdown_check([100.0] * 5)[0] is True   # too few closes -> stand down
    assert "fewer than 6" in iwm_standdown_check([100.0] * 5)[1]
    # default threshold: rv5 exactly at 0.1781 stands down, just above does not
    at_default, _ = iwm_standdown_check(flat, threshold=IWM_RV5_STANDDOWN_DEFAULT)
    assert at_default is True

    print("unit tests: OK")
    return 0


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--at", default=None, help="Override now as ISO datetime (CT)")
    ap.add_argument("--dry-run", action="store_true",
                     help="Without --once: decide + print the signal; do not run the agent or "
                          "touch state. With --once: force DIAG_DRY_RUN=1 for this run regardless "
                          "of .env.")
    ap.add_argument("--once", metavar="MODE", choices=ONCE_MODES, default=None,
                     help="Run exactly one tick of MODE right now, bypassing the clock.")
    ap.add_argument("--force", action="store_true",
                     help="With --once: re-run a mode already recorded for today. Refused unless "
                          "dry_run is True.")
    ap.add_argument("--reset-halt", action="store_true",
                     help="Clear a triggered halt. Refuses unless .env DIAG_HALTED=0.")
    ap.add_argument("--leg", default=None, metavar="LEG_ID",
                     help="With --reset-halt: clear only this leg's automatic halt instead of "
                          "the global halt.")
    ap.add_argument("--unit-test", action="store_true")
    a = ap.parse_args()
    if a.unit_test:
        return _unit_tests()
    cfg = load_cfg()
    if a.reset_halt:
        return reset_halt(cfg, leg_id=a.leg)
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
    raise SystemExit(main())
