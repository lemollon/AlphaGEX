"""SPIKE - a SEPARATE stock-buying sleeve, next to EMBER, in the same folder.
EMBER buys OPTIONS off the TradingVolatility scanner; SPIKE buys EQUITY
SHARES off its own intraday price/volume breakout signal, computed directly
from read-only squeeze.duckdb tables (never lottery_ledger -- that ledger
only gets a row once a day at the 14:45 CT sweep, and SPIKE's own ENTER tick
runs every 15 minutes all day; see load_enter_market_data()'s own docstring
for the exact table choice and why).

Modeled on ../ember/run_ember.py's architecture wherever it applies: .env
loading + flags (SPIKE_ARMED/SPIKE_DRY_RUN, same semantics as EMBER_ARMED/
EMBER_DRY_RUN), spike_state.json written atomically (tmp + os.replace, same
as EMBER's save_json), an order agent invoked as `claude -p SPIKE-PROMPT.md`
with the Robinhood MCP's EQUITY tools only (never options), a
build_allowlist() gate identical in shape to EMBER's own, and the same
pre/post log-tail comparison trick to detect whether the agent actually
produced a result this run. SPIKE never imports from or writes to
run_ember.py/order_state.json/.env's EMBER_* lines -- the only shared files
are ember_lock.py (generic, reused unmodified) and notify_spike.py (a
dedicated COPY of ember/notify.py with BOT="SPIKE", not a shared import, so
Discord identities never cross).

Architecture differences from EMBER (declared, same spirit as run_ember.py's
own "Deviations" section):
1. Two INDEPENDENT modes, each its own scheduled task, no shared daily
   "done" state and no internal clock dispatch: ENTER (intended every 15 min
   08:30-15:00 CT weekdays -- see DEPLOY-SPIKE.md) and MANAGE (intended once
   at 14:45 CT weekdays -- moved earlier than the 15:00 CT close so a
   day-10 time-exit is always a REGULAR-HOURS order, never after-hours).
   `--mode enter|manage` selects which one a given invocation runs; there
   is no RECONCILE/TRADE-style single dispatcher.
2. EMBER sizes off a fixed dollar cap (EMBER_MAX_COST_USD) and a fixed-
   percentage ENVELOPE cached ONCE A DAY by its own RECONCILE. SPIKE sizes
   off a PERCENTAGE OF THE LIVE ACCOUNT (SPIKE_SLOT_PCT), re-derived from a
   fresh `get_portfolio` EVERY ENTER TICK (not once a day, since ENTER now
   runs every 15 minutes and the account's own total_value moves as
   positions open/close intraday) -- `envelope_usd_from_pct()`/
   `spike_envelope_usage()`/`spike_envelope_fit_check()` below are the same
   SHAPE as EMBER's own envelope_usd_from_pct()/ember_envelope_usage()/
   ember_envelope_fit_check() (run_ember.py:615-631), copied not imported,
   re-derived live instead of day-cached.
3. SPIKE keeps its OWN 30-CALENDAR-DAY "first alert per symbol" dedupe
   (`seen` in spike_state.json) -- lottery_ledger's own 30-day dedupe is a
   DIFFERENT mechanism scoped to a different signal (the 14:45 sweep) and is
   never reused here.
4. A `pending` position state exists here that EMBER's option positions
   never need: a placed-but-unconfirmed equity BUY, tracked by `order_id`/
   `placed_at`, resolved by the NEXT tick (filled -> `open`, still unfilled
   past `PENDING_STALE_MINUTES` -> cancelled -> `no_fill`). This exists
   because ENTER now fires every 15 minutes and must never place a second
   order on a symbol still awaiting its first fill.
5. No sequenced-leg state machine at all -- every SPIKE order is a single
   equity leg (buy-to-open or sell-to-close), never a multi-leg options
   ticket, so none of EMBER's entry_leg_action()/exit_leg_action()/unwind
   machinery applies.
6. History for the intraday signal comes from a THREE-TIER fallback, not
   one table: `bars_pop.parquet` (current, but only covers a subset of
   today's intraday_tape symbols) first, `bars_hold` (a table, broader
   symbol coverage but stale as of this build) second, and -- for any
   symbol NEITHER local source can cover with >=20 sessions no more than
   `HISTORY_MAX_STALE_TRADING_DAYS` stale -- the AGENT itself pulls
   `get_equity_historicals` live. "No history" is never a reason to skip a
   candidate outright; it only changes WHERE the history comes from.
   `choose_history_source()` is the pure decision; `history_source`
   (`pop`/`hold`/`broker`) is recorded on every evaluated candidate and
   position.
7. Slot/envelope allocation happens LAST, not during candidate selection.
   Fix 1 (2026-09-17): an earlier build checked `occupied >= max_slots`
   INSIDE `select_enter_candidates()`'s own tape-order loop, so whichever
   symbols happened to appear FIRST in `intraday_tape` could reserve every
   slot before a later, genuinely better symbol was ever quote-checked.
   `select_enter_candidates()` now does NO slot gating at all -- every
   eligible symbol (local-history signal hits AND every `needs_broker`
   symbol, uncapped) proceeds to a live quote/spread check, then
   `rank_candidates()` sorts ALL spread-confirmed survivors by
   `dollar_volume` (today's price x day_volume off the tape) descending,
   THEN `allocate_slots()` walks that ranked list top-down applying slot
   capacity/ENVELOPE/buying-power -- a candidate that fails never blocks a
   later, higher-ranked one from being tried. `rank`/`dollar_volume` are
   recorded on every position.
8. The resting take-profit is placed on ENTER, not just MANAGE ("manage-
   lite", 2026-09-17): the +50% GTC sell must exist as soon as a buy
   fills, not sit unprotected for up to 6.5 hours until the next MANAGE
   run. Every ENTER tick now ALSO reconciles `pending_positions` (Step 1 --
   unchanged) and places a GTC TP sell for any `open` position missing a
   `tp_order_id` (`positions_needing_tp_order()`, same pure function
   MANAGE already used, now also threaded into `build_enter_signal()`).
   The day-10 TIME-EXIT stays ONLY in MANAGE -- ENTER never time-exits a
   position, it only ever reconciles pending fills and (re)confirms a TP
   rests on every open name.
9. A SECOND trigger, VOLUME-FIRST (VF, 2026-09-17, `SPIKE_VOLFIRST`):
   catches the volume surge BEFORE price confirms, instead of AFTER (the
   original "price" trigger). Evaluated on every ENTER tick for every
   in-band tape symbol that did NOT already fire the price rule THIS tick
   (`select_vf_candidates()`) -- SAME history sources, SAME 30-day `seen`
   dedupe, SAME spread gate/ranking/slots/envelope/sizing/TP/exit rules as
   the price trigger, just gated by `vf_signal_hit()` instead of
   `intraday_signal_hit()`, and requiring a SECOND ENTER tick's own reading
   of the same symbol's `day_volume` (`state["tape_prev"]`, updated every
   tick) for its own acceleration clause. `SPIKE_VOLFIRST=shadow` (the
   documented safe default) computes and logs everything but NEVER touches
   `seen`/slots/envelope and NEVER places an order (`shadow[]` in
   `spike_state.json`, agent-appended); `=live` merges VF hits into the
   SAME ranked/allocated candidate pool as price hits, through the SAME
   `build_allowlist()` gate (armed+live+sized) -- no separate order path;
   `=off` evaluates nothing. Every position/shadow-entry carries
   `trigger: "price"|"vf"`.

Usage:
  python run_spike.py --mode enter [--at ISO] [--dry-run]
  python run_spike.py --mode manage [--at ISO] [--dry-run]
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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import ember_lock

CT = ZoneInfo("America/Chicago")
CODE_DIR = Path(__file__).resolve().parent
HERE = Path(os.getenv("EMBER_SPIKE_DATA_DIR", str(CODE_DIR))).expanduser().resolve()
HERE.mkdir(parents=True, exist_ok=True)
STATE_FILE = HERE / "spike_state.json"
LOG_TXT = HERE / "spike-log.txt"
RUN_OUTPUT = HERE / "spike-run-output.log"
PROMPT_MD = CODE_DIR / "SPIKE-PROMPT.md"
ENV_FILE = HERE / ".env"
LOCK_FILE = HERE / "run_spike.lock"          # ember_lock.py reused unmodified, own lock file

# squeeze.duckdb / bars_pop.parquet belong to a different pipeline
# (dev/squeeze) -- READ ONLY, always opened with duckdb.connect(...,
# read_only=True) / read_parquet(). SPIKE never writes a byte to either.
SQUEEZE_DB = Path(os.getenv("EMBER_SPIKE_DB", str(HERE / "squeeze.duckdb")))
POP_PARQUET = Path(os.getenv("EMBER_SPIKE_POP_PARQUET", str(HERE / "bars_pop.parquet")))
POLYGON_BASE = os.getenv("POLYGON_BASE_URL", "https://api.polygon.io").rstrip("/")

ACCOUNT = "570892331"          # same Robinhood "Agentic" account every other bot in this
                                # folder/repo shares -- never point this bot at any other account.
MODES = ("enter", "manage")
PENDING_STALE_MINUTES = 30     # spec: cancel + no_fill an unfilled buy after this long
SEEN_DEDUPE_DAYS = 30          # spec: "first alert per symbol in 30 CALENDAR days"
BARS_HOLD_LOOKBACK = 20        # spec: need >= 20 prior sessions to compute med20
HISTORY_MAX_STALE_TRADING_DAYS = 3   # a local table's newest row must be within this many
                                      # trading sessions of today to count as "fresh" --
                                      # otherwise fall through to the next history source


# ---------------------------------------------------------------- trading-day math (pure)
# Weekday-only approximation, NOT a real NYSE holiday calendar (unlike
# run_ember.py's own hardcoded 2026 table) -- explicit task-spec allowance:
# "count trading days; weekdays are fine as the approximation, note it."
def is_trading_day(d: date) -> bool:
    return d.weekday() < 5


def trading_sessions_between(d1: date, d2: date) -> int:
    """Sessions strictly AFTER d1 through d2 inclusive -- same shape as
    run_ember.py's own trading_sessions_between(), weekday-only."""
    if d2 <= d1:
        return 0
    n = 0
    d = d1 + timedelta(days=1)
    while d <= d2:
        if is_trading_day(d):
            n += 1
        d += timedelta(days=1)
    return n


def sessions_held(entry_date: str | date, today: date) -> int:
    d1 = entry_date if isinstance(entry_date, date) else date.fromisoformat(entry_date)
    return trading_sessions_between(d1, today)


def time_stop_due(entry_date: str | date, today: date, max_sessions: int) -> bool:
    return sessions_held(entry_date, today) >= max_sessions


# ---------------------------------------------------------------- config
@dataclass
class Cfg:
    armed: bool = False
    dry_run: bool = True
    claude_bin: str = "claude"
    slot_pct: float = 0.0          # SPIKE_SLOT_PCT -- % of live total_value per new position;
                                    # 0 (the safe default when .env is missing entirely) refuses
                                    # every candidate, same fail-closed convention as EMBER's
                                    # own buying_power_ok(None, ...).
    envelope_pct: float = 25.0     # SPIKE_ENVELOPE_PCT -- fixed % share of the live account,
                                    # same shape as EMBER's own ENVELOPE (run_ember.py:614-622),
                                    # re-derived every ENTER tick instead of day-cached (see
                                    # module docstring #2).
    max_slots: int = 5             # SPIKE_MAX_SLOTS -- max simultaneously open+dry+pending names
    spread_max: float = 0.02       # SPIKE_SPREAD_MAX -- (ask-bid)/ask ceiling
    px_min: float = 0.10           # SPIKE_PX_MIN
    px_max: float = 1.00           # SPIKE_PX_MAX
    tp_pct: float = 0.50           # SPIKE_TP -- tp_px = ask * (1 + tp_pct)
    max_sessions: int = 10         # SPIKE_MAX_SESSIONS -- time-stop, trading sessions held
    volfirst: str = "shadow"       # SPIKE_VOLFIRST -- shadow|live|off (safe default: shadow,
                                    # never guessed into "live" on a bad/missing value)
    vf_vol_mult: float = 3.0       # SPIKE_VF_VOL_MULT -- day_volume >= this x med20
    vf_min_move: float = -0.05     # SPIKE_VF_MIN_MOVE
    vf_max_move: float = 0.10      # SPIKE_VF_MAX_MOVE
    vf_accel: float = 1.5          # SPIKE_VF_ACCEL -- day_volume >= this x the SAME symbol's
                                    # own day_volume at the previous ENTER tick


def load_cfg(env_file: Path = ENV_FILE) -> Cfg:
    """Missing .env => every default above is the safe one (unarmed,
    dry-run, slot_pct 0 -- nothing tradeable). Same env-parsing shape as
    run_ember.py's load_cfg()."""
    env: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    env = {**env, **{k: v for k, v in os.environ.items() if k.startswith("SPIKE_")}}
    return Cfg(
        armed=env.get("SPIKE_ARMED", "0") == "1",
        dry_run=env.get("SPIKE_DRY_RUN", "1") != "0",
        claude_bin=env.get("SPIKE_CLAUDE_BIN", "claude"),
        slot_pct=float(env.get("SPIKE_SLOT_PCT", "0")),
        envelope_pct=float(env.get("SPIKE_ENVELOPE_PCT", "25")),
        max_slots=int(env.get("SPIKE_MAX_SLOTS", "5")),
        spread_max=float(env.get("SPIKE_SPREAD_MAX", "0.02")),
        px_min=float(env.get("SPIKE_PX_MIN", "0.10")),
        px_max=float(env.get("SPIKE_PX_MAX", "1.00")),
        tp_pct=float(env.get("SPIKE_TP", "0.50")),
        max_sessions=int(env.get("SPIKE_MAX_SESSIONS", "10")),
        volfirst=(env.get("SPIKE_VOLFIRST", "shadow").strip().lower()
                  if env.get("SPIKE_VOLFIRST", "shadow").strip().lower() in ("shadow", "live", "off")
                  else "shadow"),
        vf_vol_mult=float(env.get("SPIKE_VF_VOL_MULT", "3.0")),
        vf_min_move=float(env.get("SPIKE_VF_MIN_MOVE", "-0.05")),
        vf_max_move=float(env.get("SPIKE_VF_MAX_MOVE", "0.10")),
        vf_accel=float(env.get("SPIKE_VF_ACCEL", "1.5")),
    )


# ---------------------------------------------------------------- state I/O (same shape as EMBER)
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


def load_state() -> dict:
    d = load_json(STATE_FILE)
    d.setdefault("positions", [])
    d.setdefault("seen", {})
    d.setdefault("tape_prev", {})   # {symbol: day_volume at the LAST ENTER tick} -- VF's own
                                     # acceleration clause needs two looks; see select_vf_candidates()
    d.setdefault("shadow", [])      # VF shadow-mode log, agent-appended, never touched by Python
    return d


# ---------------------------------------------------------------- price-range / spread / sizing (pure)
def price_in_range(px: float | None, px_min: float, px_max: float) -> bool:
    """Inclusive on both ends, per spec. A missing/non-numeric px is never
    in range (never guessed)."""
    if px is None:
        return False
    return px_min <= px <= px_max


def spread_pct(bid: float | None, ask: float | None) -> float | None:
    """(ask - bid) / ask. None (never guessed) if ask/bid aren't usable."""
    if ask is None or ask <= 0 or bid is None:
        return None
    return (ask - bid) / ask


def quote_ok(bid: float | None, ask: float | None, spread_max: float) -> tuple[bool, str]:
    """Skip if bid <= 0, or spread_pct > spread_max -- spec's own two
    conditions."""
    if bid is None or bid <= 0:
        return False, "bid <= 0"
    sp = spread_pct(bid, ask)
    if sp is None:
        return False, "no usable ask"
    if sp > spread_max:
        return False, f"spread {sp:.4f} > max {spread_max:.4f}"
    return True, f"spread {sp:.4f}"


def size_qty(slot_usd: float | None, ask: float | None) -> int:
    """floor(slot_usd / ask); 0 (never guessed) if either input isn't
    usable."""
    if ask is None or ask <= 0 or slot_usd is None or slot_usd <= 0:
        return 0
    return math.floor(slot_usd / ask)


def tp_price(ask: float, tp_pct: float) -> float:
    return round(ask * (1 + tp_pct), 4)


def buying_power_ok(buying_power: float | None, slot_usd: float) -> tuple[bool, str]:
    """buying_power < slot_usd -> skip, per spec (no extra cushion, unlike
    EMBER's own $25 buffer -- the task spec states this check plainly)."""
    if buying_power is None:
        return False, "buying_power unknown"
    if buying_power < slot_usd:
        return False, f"buying_power ${buying_power:.2f} < slot ${slot_usd:.2f}"
    return True, "ok"


# ---------------------------------------------------------------- live sizing off SLOT_PCT (pure)
def slot_usd_from_pct(pct: float, total_value: float | None) -> float | None:
    """slot_usd = total_value * SPIKE_SLOT_PCT / 100. None (never guessed,
    fails closed) if total_value was never read live this tick."""
    if total_value is None:
        return None
    return round((pct / 100.0) * total_value, 2)


def max_sleeve_exposure_pct(slot_pct: float, max_slots: int) -> float:
    """SPIKE_SLOT_PCT x SPIKE_MAX_SLOTS -- the theoretical ceiling on the
    sleeve's own share of the account if every slot were filled at once.
    Printed in every ENTER tick's first notify line, per spec."""
    return round(slot_pct * max_slots, 4)


# ---------------------------------------------------------------- ENVELOPE (pure, same shape as EMBER's)
# Copied from run_ember.py's own envelope_usd_from_pct()/ember_envelope_usage()/
# ember_envelope_fit_check() (run_ember.py:615-631) -- same math, re-derived
# LIVE every ENTER tick instead of cached once a day (module docstring #2).
def envelope_usd_from_pct(pct: float, total_value: float) -> float:
    return round((pct / 100.0) * total_value, 2)


def spike_envelope_usage(positions: list[dict]) -> float:
    """sum(qty * entry_px) over this bot's own OPEN + PENDING positions --
    'pending' counts too (an unfilled buy still reserves the capital until
    resolved, same reasoning as EMBER's own Fix 5 in-flight guard)."""
    return round(sum((p.get("qty") or 0) * (p.get("entry_px") or 0.0)
                      for p in positions if p.get("state") in ("open", "pending")), 2)


def spike_envelope_fit_check(envelope_usd: float, usage_usd: float, needed_usd: float) -> tuple[bool, float]:
    total = round(usage_usd + needed_usd, 2)
    return total <= envelope_usd, total


def envelope_capacity_ok(envelope_usd: float | None, usage_running: float,
                          slot_usd: float) -> tuple[bool, float]:
    """None envelope_usd (total_value never read live this tick) -> always
    refuse, fails closed -- same convention as run_ember.py's
    cap_entry_candidates(). Returns (fits, new_running_usage) so callers can
    thread a running total across several candidates in the SAME tick."""
    if envelope_usd is None:
        return False, usage_running
    fits, _ = spike_envelope_fit_check(envelope_usd, usage_running, slot_usd)
    if not fits:
        return False, usage_running
    return True, round(usage_running + slot_usd, 2)


# ---------------------------------------------------------------- intraday signal math (pure)
def pct_move(price: float | None, prior_close: float | None) -> float | None:
    if price is None or prior_close is None or prior_close <= 0:
        return None
    return price / prior_close - 1.0


def dollar_volume(price: float | None, day_volume: float | None) -> float | None:
    """price x day_volume, straight off the tape row -- NOT live data, used
    ONLY to rank candidates (highest first) before slot allocation. None
    (never guessed) if either input is missing."""
    if price is None or day_volume is None:
        return None
    return price * day_volume


def median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def med20_volume(prior_sessions: list[dict]) -> float | None:
    """`prior_sessions`: bars_hold rows for ONE symbol, strictly before
    today, any order. None (skip, never guessed) if fewer than
    BARS_HOLD_LOOKBACK (20) sessions carry a usable volume -- spec's own
    explicit rule."""
    vols = [r.get("volume") for r in prior_sessions if r.get("volume") is not None]
    if len(vols) < BARS_HOLD_LOOKBACK:
        return None
    return median(vols[-BARS_HOLD_LOOKBACK:])


def latest_prior_close(prior_sessions: list[dict]) -> float | None:
    """prior_sessions must be sorted OLDEST FIRST by the caller (same
    convention load_prior_sessions() returns) -- the last element is the
    most recent close before today."""
    if not prior_sessions:
        return None
    return prior_sessions[-1].get("close")


def latest_prior_volume(prior_sessions: list[dict]) -> float | None:
    """Same convention as latest_prior_close() -- the LAST FULL trading
    session's own total volume (NOT med20's 20-session median). VF's own
    'day_volume >= prior full session's volume' clause."""
    if not prior_sessions:
        return None
    return prior_sessions[-1].get("volume")


def intraday_signal_hit(price: float | None, prior_close: float | None, day_volume: float | None,
                         med20: float | None, px_min: float, px_max: float) -> tuple[bool, str]:
    """Spec's own three-part test, in the spec's own order:
    price/prior_close - 1 >= 0.10 AND day_volume >= 3*med20 AND
    SPIKE_PX_MIN <= price <= SPIKE_PX_MAX."""
    if price is None or prior_close is None or day_volume is None:
        return False, "missing price/prior_close/day_volume"
    if med20 is None or med20 <= 0:
        return False, "med20 volume unknown/zero"
    mv = pct_move(price, prior_close)
    if mv is None or mv < 0.10:
        return False, f"move {mv} < 0.10"
    if day_volume < 3 * med20:
        return False, f"day_volume {day_volume} < 3x med20 {med20}"
    if not price_in_range(price, px_min, px_max):
        return False, f"price {price} outside [{px_min}, {px_max}]"
    return True, "signal"


def build_signal_row(universe_row: dict, prior_sessions: list[dict], cfg: Cfg) -> tuple[dict | None, str]:
    """Pure: one intraday_tape universe row + a RESOLVED history list (from
    whichever source the caller already picked -- bars_pop.parquet,
    bars_hold, or the agent's own get_equity_historicals) -> a computed
    signal row on a hit, or (None, reason) on a miss. Callers only reach
    this with a NON-EMPTY, already-fresh `prior_sessions` (see
    choose_history_source()) -- select_enter_candidates() defers any symbol
    with no qualifying local history to the agent instead of calling this
    at all, so "fewer than 20 sessions" should not normally surface here."""
    symbol = universe_row.get("symbol")
    price = universe_row.get("price")
    day_volume = universe_row.get("vol")
    med20 = med20_volume(prior_sessions)
    if med20 is None:
        return None, "fewer than 20 prior sessions"
    prior_close = latest_prior_close(prior_sessions)
    hit, reason = intraday_signal_hit(price, prior_close, day_volume, med20, cfg.px_min, cfg.px_max)
    if not hit:
        return None, reason
    return {
        "symbol": symbol, "price": price, "prior_close": prior_close,
        "day_volume": day_volume, "med20_volume": med20,
        "pct_move": pct_move(price, prior_close),
    }, reason


# ---------------------------------------------------------------- VOLUME-FIRST (VF) signal math (pure)
def vf_signal_hit(day_volume: float | None, med20: float | None, prior_session_volume: float | None,
                   pct_move_val: float | None, prev_tick_volume: float | None, vol_mult: float,
                   min_move: float, max_move: float, accel: float) -> tuple[bool, str]:
    """VF ('volume-first') catches the volume surge BEFORE price confirms.
    ALL FOUR conditions, spec's own order:
      day_volume >= vol_mult x med20
      day_volume >= prior_session_volume (the LAST FULL session's own
        volume -- different from med20's 20-session MEDIAN)
      min_move <= pct_move <= max_move
      day_volume >= accel x prev_tick_volume (this SAME symbol's own
        day_volume at the PREVIOUS ENTER tick -- `prev_tick_volume=None`
        [no prior tick exists yet] NEVER satisfies this, per spec: 'VF
        needs two looks')."""
    if day_volume is None or med20 is None or med20 <= 0:
        return False, "med20 volume unknown/zero"
    if day_volume < vol_mult * med20:
        return False, f"day_volume {day_volume} < {vol_mult}x med20 {med20}"
    if prior_session_volume is None:
        return False, "prior session volume unknown"
    if day_volume < prior_session_volume:
        return False, f"day_volume {day_volume} < prior session volume {prior_session_volume}"
    if pct_move_val is None or not (min_move <= pct_move_val <= max_move):
        return False, f"pct_move {pct_move_val} outside [{min_move}, {max_move}]"
    if prev_tick_volume is None:
        return False, "no prior ENTER tick reading -- VF needs two looks"
    if day_volume < accel * prev_tick_volume:
        return False, f"day_volume {day_volume} < {accel}x prev tick volume {prev_tick_volume}"
    return True, "vf-signal"


def build_vf_signal_row(universe_row: dict, prior_sessions: list[dict], prev_tick_volume: float | None,
                         cfg: Cfg) -> tuple[dict | None, str]:
    """VF companion to build_signal_row() -- SAME resolved history list,
    the VF test instead of the price test. Missing/insufficient local
    history (`prior_sessions` empty) -> 'fewer than 20 prior sessions',
    same convention as build_signal_row()."""
    symbol = universe_row.get("symbol")
    price = universe_row.get("price")
    day_volume = universe_row.get("vol")
    med20 = med20_volume(prior_sessions)
    if med20 is None:
        return None, "fewer than 20 prior sessions"
    prior_close = latest_prior_close(prior_sessions)
    prior_volume = latest_prior_volume(prior_sessions)
    mv = pct_move(price, prior_close)
    hit, reason = vf_signal_hit(day_volume, med20, prior_volume, mv, prev_tick_volume,
                                 cfg.vf_vol_mult, cfg.vf_min_move, cfg.vf_max_move, cfg.vf_accel)
    if not hit:
        return None, reason
    return {
        "symbol": symbol, "price": price, "prior_close": prior_close,
        "day_volume": day_volume, "med20_volume": med20, "prior_volume": prior_volume,
        "pct_move": mv, "prev_tick_volume": prev_tick_volume,
    }, reason


# ---------------------------------------------------------------- history-source fallback (pure)
def sessions_available_and_fresh(rows: list[dict], today: date,
                                  max_stale_days: int = HISTORY_MAX_STALE_TRADING_DAYS) -> bool:
    """True if `rows` (any one history source, any order) carries >=20
    sessions AND its most recent `date` is within `max_stale_days` TRADING
    sessions of `today`. A source that's merely present but stale (like
    bars_hold at build time) never counts as usable."""
    if len(rows) < BARS_HOLD_LOOKBACK:
        return False
    dated = sorted((r.get("date") for r in rows if r.get("date") is not None))
    if not dated:
        return False
    last = dated[-1]
    if isinstance(last, str):
        last = date.fromisoformat(last)
    return trading_sessions_between(last, today) <= max_stale_days


def choose_history_source(pop_rows: list[dict], hold_rows: list[dict], today: date
                           ) -> tuple[list[dict], str]:
    """Pure, spec's own stated order: bars_pop.parquet first, bars_hold
    fallback, `([], "broker")` sentinel if NEITHER has >=20 fresh sessions
    -- the caller then hands that symbol to the agent's own
    get_equity_historicals instead of skipping it ('nothing may be skipped
    for no history if the broker can supply it')."""
    if sessions_available_and_fresh(pop_rows, today):
        return pop_rows, "pop"
    if sessions_available_and_fresh(hold_rows, today):
        return hold_rows, "hold"
    return [], "broker"


# ---------------------------------------------------------------- 30-day seen-dedupe (pure)
def is_recently_seen(symbol: str, seen: dict[str, str], today: date, days: int = SEEN_DEDUPE_DAYS) -> bool:
    """True if `symbol` fired a signal within the last `days` CALENDAR days
    -- SPIKE's OWN dedupe (never lottery_ledger's, a different mechanism
    scoped to a different signal)."""
    last = seen.get(symbol)
    if not last:
        return False
    try:
        last_d = date.fromisoformat(last)
    except ValueError:
        return False
    return (today - last_d).days < days


def record_seen(seen: dict[str, str], symbol: str, today: date) -> dict[str, str]:
    """Pure: returns an UPDATED COPY of `seen` with symbol -> today (never
    regresses an existing, newer date backward). Recorded the MOMENT a
    signal fires, regardless of whether a position is later actually
    opened (spec's own words: 'skipped even if it was skipped for spread at
    the time')."""
    out = dict(seen)
    prev = out.get(symbol)
    if not prev or date.fromisoformat(prev) < today:
        out[symbol] = today.isoformat()
    return out


# ---------------------------------------------------------------- idempotency / slot capacity (pure)
def occupied_slot_count(positions: list[dict]) -> int:
    """open + dry + pending all consume a slot -- capital/attention is
    already committed in every one of those states."""
    return sum(1 for p in positions if p.get("state") in ("open", "dry", "pending"))


def is_symbol_blocked(symbol: str, positions: list[dict]) -> bool:
    """A symbol already open, dry, or pending is never re-entered -- spec's
    own three-state idempotency list."""
    return any(p.get("symbol") == symbol and p.get("state") in ("open", "dry", "pending")
               for p in positions)


def select_enter_candidates(universe: list[dict], history_by_symbol: dict[str, tuple[list[dict], str]],
                             positions: list[dict], seen: dict[str, str], today: date, cfg: Cfg,
                             prev_tick_volume: dict[str, float] | None = None
                             ) -> tuple[list[dict], list[dict], dict[str, str], list[tuple[str, str]]]:
    """Pure orchestration, spec's own stated order: price band -> resolve
    history source -> compute the signal (local sources only) -> 30-day
    seen-dedupe (recorded the moment it fires) -> open/dry/pending
    idempotency. **NO slot-capacity check happens here at all** -- that
    was Fix 1's exact bug (an early symbol reserving a slot before it had
    even been quote-checked could starve a later, better symbol out of
    ever being evaluated). Slot/envelope allocation happens LAST, in
    `allocate_slots()`, only after every signal-positive candidate has
    been ranked by `dollar_volume` (see module docstring #7).
    `history_by_symbol[symbol]` is `(rows, source)` from
    choose_history_source() -- a `source == "broker"` symbol has NO local
    history and is deferred to `needs_broker` (the agent resolves the
    signal itself via get_equity_historicals, ALWAYS, never capped) rather
    than skipped. Both `local_positive` and `needs_broker` rows carry their
    own `dollar_volume` (price x day_volume off the tape -- no live data
    needed for this). `needs_broker` entries ALSO carry `prev_tick_volume`
    (from `prev_tick_volume`, `select_vf_candidates()`'s own per-tick cache)
    so the agent's ONE get_equity_historicals pull can check BOTH the price
    rule AND (VF, module docstring #9) the volume-first rule from the SAME
    response -- see SPIKE-PROMPT.md Step 2b. Returns (local_positive rows,
    needs_broker rows, updated `seen` copy, skip (symbol, reason) tuples);
    never mutates any input."""
    prev_tick_volume = prev_tick_volume or {}
    seen_out = dict(seen)
    local_positive: list[dict] = []
    needs_broker: list[dict] = []
    skips: list[tuple[str, str]] = []
    for urow in universe:
        symbol = urow.get("symbol")
        if not symbol:
            continue
        price = urow.get("price")
        if not price_in_range(price, cfg.px_min, cfg.px_max):
            skips.append((symbol, f"price {price} outside [{cfg.px_min}, {cfg.px_max}]"))
            continue
        dv = dollar_volume(price, urow.get("vol"))
        rows, source = history_by_symbol.get(symbol, ([], "broker"))

        if source == "broker":
            if is_symbol_blocked(symbol, positions):
                skips.append((symbol, "already open/dry/pending"))
                continue
            needs_broker.append({"symbol": symbol, "price": price, "day_volume": urow.get("vol"),
                                  "dollar_volume": dv, "prev_tick_volume": prev_tick_volume.get(symbol)})
            continue

        row, reason = build_signal_row(urow, rows, cfg)
        if row is None:
            skips.append((symbol, f"{reason} ({source})"))
            continue
        if is_recently_seen(symbol, seen_out, today):
            skips.append((symbol, f"seen within {SEEN_DEDUPE_DAYS} days ({seen_out.get(symbol)})"))
            continue
        seen_out = record_seen(seen_out, symbol, today)
        if is_symbol_blocked(symbol, positions):
            skips.append((symbol, "already open/dry/pending"))
            continue
        row["history_source"] = source
        row["dollar_volume"] = dv
        row["trigger"] = "price"
        local_positive.append(row)
    return local_positive, needs_broker, seen_out, skips


def select_vf_candidates(universe: list[dict], history_by_symbol: dict[str, tuple[list[dict], str]],
                          price_hit_symbols: set[str], prev_tick_volume: dict[str, float],
                          positions: list[dict], seen: dict[str, str], today: date, cfg: Cfg
                          ) -> tuple[list[dict], dict[str, str], list[tuple[str, str]]]:
    """VF ('volume-first', module docstring #9) companion to
    select_enter_candidates() -- LOCAL-history symbols only; a
    `source == 'broker'` symbol is left to the agent, which checks price
    FIRST then VF off the SAME single get_equity_historicals pull already
    queued in `needs_broker` (see that function's own docstring) --
    duplicating a second broker call here would defeat "same history
    source". `cfg.volfirst == 'off'` -> nothing evaluated at all (returns
    empty). Skips: price-band failures (already logged by
    select_enter_candidates()) and any symbol in `price_hit_symbols`
    ("did not already fire the price rule", spec's own words -- the set of
    symbols select_enter_candidates() already accepted LOCALLY this tick).

    **shadow mode** (`cfg.volfirst == 'shadow'`, the safe default): NEVER
    touches `seen` or the open/dry/pending idempotency check -- spec's own
    words, "so the price rule can still buy the name later." Every VF hit
    is returned regardless of existing state; the caller (run_enter) never
    lets a shadow-mode result reach `allocate_slots()`.

    **live mode**: identical dedupe/idempotency shape to
    select_enter_candidates() -- a VF fire records `seen` exactly like a
    price fire. Returns (local_positive rows, each tagged `trigger: "vf"`,
    updated `seen` copy [unchanged in shadow mode], skip tuples); never
    mutates any input."""
    if cfg.volfirst == "off":
        return [], dict(seen), []
    shadow = cfg.volfirst == "shadow"
    seen_out = dict(seen)
    local_positive: list[dict] = []
    skips: list[tuple[str, str]] = []
    for urow in universe:
        symbol = urow.get("symbol")
        if not symbol or symbol in price_hit_symbols:
            continue
        price = urow.get("price")
        if not price_in_range(price, cfg.px_min, cfg.px_max):
            continue
        rows, source = history_by_symbol.get(symbol, ([], "broker"))
        if source == "broker":
            continue   # resolved by the agent off the SAME needs_broker entry (price rule's own)
        prev_vol = prev_tick_volume.get(symbol)
        row, reason = build_vf_signal_row(urow, rows, prev_vol, cfg)
        if row is None:
            skips.append((symbol, f"VF: {reason} ({source})"))
            continue
        if not shadow:
            if is_recently_seen(symbol, seen_out, today):
                skips.append((symbol, f"VF: seen within {SEEN_DEDUPE_DAYS} days ({seen_out.get(symbol)})"))
                continue
            seen_out = record_seen(seen_out, symbol, today)
            if is_symbol_blocked(symbol, positions):
                skips.append((symbol, "VF: already open/dry/pending"))
                continue
        row["history_source"] = source
        row["dollar_volume"] = dollar_volume(price, urow.get("vol"))
        row["trigger"] = "vf"
        local_positive.append(row)
    return local_positive, seen_out, skips


# ---------------------------------------------------------------- rank + allocate (pure, Fix 1)
def rank_candidates(candidates: list[dict]) -> list[dict]:
    """Pure: `candidates` (any mix of local_positive/needs_broker-resolved
    rows -- both carry `dollar_volume`) sorted by `dollar_volume`
    DESCENDING (today's price x day_volume off the tape, never live data),
    each returned as a NEW dict augmented with `rank` (1-based). A
    candidate with `dollar_volume` missing/None sorts LAST, never guessed
    high. Does not mutate any input dict."""
    def sort_key(c: dict) -> tuple[bool, float]:
        dv = c.get("dollar_volume")
        return (dv is None, -(dv or 0.0))
    ranked = sorted(candidates, key=sort_key)
    return [{**c, "rank": i + 1} for i, c in enumerate(ranked)]


def allocate_slots(ranked: list[dict], *, occupied: int, max_slots: int,
                    envelope_usd: float | None, usage_usd: float, slot_usd: float | None,
                    buying_power: float | None) -> tuple[list[dict], list[tuple[str, str]]]:
    """Pure: walk `ranked` (already rank-assigned, dollar_volume descending
    -- see `rank_candidates()`) TOP DOWN, allocating a slot to each
    candidate that fits (qty>=1 at `slot_usd`/its own `ask`, remaining slot
    capacity, ENVELOPE headroom, buying power) -- a candidate that fails
    ANY check is skipped and the NEXT-ranked candidate is still tried
    (never stops early, so one bad candidate can never starve a later,
    better one). Each candidate dict must already carry its own live `ask`
    (set by the caller after the spread gate, before calling this). Returns
    (accepted rows, each with `qty` set; skip (symbol, reason) tuples).
    Never mutates any input."""
    accepted: list[dict] = []
    skips: list[tuple[str, str]] = []
    usage_running = usage_usd
    slots_used = occupied
    for c in ranked:
        symbol = c.get("symbol")
        rank = c.get("rank")
        if slots_used >= max_slots:
            skips.append((symbol, f"open slots >= max_slots ({max_slots}) at rank {rank}"))
            continue
        qty = size_qty(slot_usd, c.get("ask"))
        if qty < 1:
            skips.append((symbol, f"qty < 1 at slot_usd=${slot_usd} ask={c.get('ask')} (rank {rank})"))
            continue
        fits, new_usage = envelope_capacity_ok(envelope_usd, usage_running, slot_usd or 0.0)
        if not fits:
            skips.append((symbol, f"ENVELOPE usage ${usage_running} + slot ${slot_usd} "
                                   f"> envelope ${envelope_usd} (rank {rank})"))
            continue
        bp_ok, bp_reason = buying_power_ok(buying_power, slot_usd or 0.0)
        if not bp_ok:
            skips.append((symbol, f"{bp_reason} (rank {rank})"))
            continue
        usage_running = new_usage
        slots_used += 1
        accepted.append({**c, "qty": qty})
    return accepted, skips


# ---------------------------------------------------------------- Discord-compact skip formatting (pure)
def format_skip_line(symbol: str, reason: str) -> str:
    """Full detail -- spike-log.txt (local file) ONLY, never sent to
    Discord directly."""
    return f"SPIKE | ENTER | SKIP {symbol}: {reason}"


def compact_skip(symbol: str, reason: str) -> str:
    """One short token per skip for the collapsed Discord summary line --
    the detailed reason stays in spike-log.txt via format_skip_line()."""
    r = reason.lower()
    m = re.search(r"spread ([\d.]+) > max", r)
    if m:
        return f"SKIP {symbol} spread {float(m.group(1)) * 100:.0f}%"
    if "bid <= 0" in r or "no usable ask" in r:
        return f"SKIP {symbol} no bid/ask"
    if "qty < 1" in r:
        return f"SKIP {symbol} too small"
    if "envelope" in r:
        return f"SKIP {symbol} envelope full"
    if "buying_power" in r:
        return f"SKIP {symbol} low bp"
    if "already open" in r:
        return f"SKIP {symbol} blocked"
    if "max_slots" in r:
        return f"SKIP {symbol} slots full"
    if "seen within" in r:
        return f"SKIP {symbol} seen"
    if "move" in r or "day_volume" in r or "outside" in r:
        return f"SKIP {symbol} no-signal"
    if "prior sessions" in r:
        return f"SKIP {symbol} no-hist"
    return f"SKIP {symbol} skip"


def build_skip_summary(skips: list[tuple[str, str]], max_items: int = 12) -> str:
    """Compact, Discord-safe summary of every LOCAL (Python-level) skip this
    tick, joined ' | ', capped at `max_items` with a '+N more' tail."""
    if not skips:
        return "no skips"
    tokens = [compact_skip(sym, reason) for sym, reason in skips]
    if len(tokens) > max_items:
        return " | ".join(tokens[:max_items]) + f" | +{len(tokens) - max_items} more"
    return " | ".join(tokens)


# ---------------------------------------------------------------- position builders / state transitions (pure)
def build_position(row: dict, *, entry_bid: float | None, entry_ask: float, qty: int,
                    slot_pct: float, slot_usd: float, total_value: float,
                    tp_pct: float, entry_date: date, signal_time: str, state: str,
                    history_source: str, rank: int | None = None,
                    dollar_volume: float | None = None, order_id: str | None = None,
                    placed_at: str | None = None, trigger: str = "price") -> dict:
    """One spike_state.json position row -- schema per the task spec, plus
    the sizing-provenance fields (slot_pct/slot_usd/total_value), the
    pending-tracking fields (order_id/placed_at), `history_source`
    (`pop`/`hold`/`broker` -- which table/source the prior-close/med20 came
    from), `rank`/`dollar_volume` (Fix 1: this position's own allocation
    rank and the tape dollar-volume it was ranked on), and `trigger`
    (`"price"`/`"vf"` -- which signal fired it, module docstring #9) the
    later spec revisions added. `state` is 'pending' (armed+live, order
    just placed) or 'dry' (unarmed/dry-run -- everything computed, nothing
    placed)."""
    sprd = spread_pct(entry_bid, entry_ask)
    return {
        "state": state, "symbol": row.get("symbol"),
        "entry_date": entry_date.isoformat(), "signal_time": signal_time,
        "entry_px": entry_ask, "entry_bid": entry_bid, "entry_ask": entry_ask,
        "entry_spread_pct": sprd, "qty": qty,
        "slot_pct": slot_pct, "slot_usd": slot_usd, "total_value": total_value,
        "cost_usd": round(qty * entry_ask, 2),
        "tp_px": tp_price(entry_ask, tp_pct), "tp_order_id": None,
        "order_id": order_id, "placed_at": placed_at, "history_source": history_source,
        "rank": rank, "dollar_volume": dollar_volume, "trigger": trigger,
        "exit_date": None, "exit_px": None, "exit_reason": None,
        "source_row": row,
    }


def mark_closed(position: dict, *, exit_date: date, exit_px: float, reason: str) -> dict:
    """Pure: an UPDATED COPY with state 'closed' and the exit fields filled
    in -- never mutates the input (same convention as run_ember.py's own
    reconcile_positions())."""
    return {**position, "state": "closed", "exit_date": exit_date.isoformat(),
            "exit_px": exit_px, "exit_reason": reason}


def resolve_pending_filled(position: dict, *, fill_qty: int, fill_px: float) -> dict:
    """A 'pending' buy confirmed filled -- becomes 'open' at its REAL fill
    qty/price (which may differ slightly from the placed limit)."""
    return {**position, "state": "open", "qty": fill_qty, "entry_px": fill_px,
            "cost_usd": round(fill_qty * fill_px, 2), "order_id": None}


def resolve_pending_stale(position: dict) -> dict:
    """A 'pending' buy still unfilled past PENDING_STALE_MINUTES -- the
    agent cancels the live order, this just records the outcome."""
    return {**position, "state": "no_fill", "order_id": None}


def pending_positions(positions: list[dict]) -> list[dict]:
    return [p for p in positions if p.get("state") == "pending"]


def pending_is_stale(position: dict, now: datetime, stale_minutes: int = PENDING_STALE_MINUTES) -> bool:
    """True once a 'pending' position's own buy order has been unfilled for
    >= stale_minutes since it was placed. Missing/unparseable placed_at is
    treated as NOT stale (never guessed) -- the agent still resolves it via
    a live get_equity_orders read either way."""
    placed_at = position.get("placed_at")
    if not placed_at:
        return False
    try:
        placed = datetime.fromisoformat(placed_at)
    except ValueError:
        return False
    if placed.tzinfo is None and now.tzinfo is not None:
        placed = placed.replace(tzinfo=now.tzinfo)
    elif placed.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=placed.tzinfo)
    return (now - placed).total_seconds() / 60.0 >= stale_minutes


def positions_due_for_time_exit(positions: list[dict], today: date, cfg: Cfg) -> list[dict]:
    return [p for p in positions if p.get("state") == "open" and p.get("entry_date")
            and time_stop_due(p["entry_date"], today, cfg.max_sessions)]


def positions_needing_tp_order(positions: list[dict]) -> list[dict]:
    return [p for p in positions if p.get("state") == "open" and not p.get("tp_order_id")]


def reconcile_mismatches(state_symbols: set[str], broker_symbols: set[str]) -> list[str]:
    """Pure: report-only, NEVER auto-fixed (spec's own words)."""
    lines = []
    for s in sorted(state_symbols - broker_symbols):
        lines.append(f"MISMATCH: {s} recorded open in spike_state.json, not found at broker")
    for s in sorted(broker_symbols - state_symbols):
        lines.append(f"MISMATCH: unrecognized live equity position {s} -- not in spike_state.json")
    return lines


# ---------------------------------------------------------------- squeeze.duckdb / bars_pop.parquet reads (impure, untested)
def _load_history_rows(con, source_sql: str, symbols: list[str], today: date,
                        lookback: int = BARS_HOLD_LOOKBACK) -> dict[str, list[dict]]:
    """One windowed query against `source_sql` (a table name like
    `bars_hold`, or a table-function expression like `read_parquet(...)`):
    up to `lookback` most recent rows per symbol, strictly before `today`,
    returned OLDEST FIRST per symbol (matches latest_prior_close()'s own
    convention). `symbols` empty -> {} without touching the DB."""
    if not symbols:
        return {}
    df = con.execute(
        f"""
        SELECT symbol, date, close, volume FROM (
            SELECT symbol, date, close, volume,
                   row_number() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM {source_sql}
            WHERE symbol = ANY(?) AND date < ?
        ) WHERE rn <= ?
        """, [symbols, today.isoformat(), lookback]).fetchdf()
    if not df.empty:
        df["date"] = df["date"].apply(lambda d: d.date() if hasattr(d, "date") else d)
    out: dict[str, list[dict]] = {}
    for sym, grp in df.groupby("symbol"):
        out[str(sym)] = grp.sort_values("date").to_dict("records")
    return out


def load_enter_market_data(today: date, db_path: Path = SQUEEZE_DB, pop_path: Path = POP_PARQUET
                            ) -> tuple[list[dict], dict[str, tuple[list[dict], str]]]:
    """One read-only DB session: (today's newest-tick-per-symbol row from
    `intraday_tape`, {symbol: (rows, source) already resolved via
    choose_history_source()}).

    Universe table choice (recon, 2026-09-17): `lottery_ledger` only gets a
    row once a day (the 14:45 CT sweep) -- wrong shape for a 15-minute-
    cadence ENTER. Of the two remaining candidates, `watch_events` is
    itself a PRE-FILTERED alert log (event_type in vol_exceed/move/
    new_high, built on ANOTHER bot's own thresholds/baseline price, not
    SPIKE's own); `intraday_tape` is the raw per-ticker tape (price,
    cumulative day `vol`, no event logic of its own) SPIKE computes its OWN
    10%-move/3x-volume signal from -- chosen for that reason. `intraday_tape`
    is itself a curated watchlist, not the full market (~38 names on
    2026-09-17), a real coverage limit of this data source, not a bug here.

    History table choice: bars_pop.parquet (current, ~15/38 of today's
    symbols on 2026-09-17) is tried FIRST, bars_hold (broader symbol
    coverage, but stale at build time) SECOND, per HISTORY_MAX_STALE_
    TRADING_DAYS. A symbol neither covers gets `([], "broker")` -- the
    caller (select_enter_candidates()) defers it to the agent's own
    get_equity_historicals instead of skipping it.
    """
    if os.getenv("RENDER", "").strip().lower() == "true" or \
            os.getenv("SPIKE_DATA_SOURCE", "").strip().lower() == "polygon":
        return _load_polygon_enter_market_data()

    import duckdb
    if not db_path.exists():
        return [], {}
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        udf = con.execute(
            """
            SELECT t.* FROM intraday_tape t
            INNER JOIN (SELECT symbol, max(ts) AS max_ts FROM intraday_tape
                        WHERE trade_date = ? GROUP BY symbol) m
              ON t.symbol = m.symbol AND t.ts = m.max_ts
            WHERE t.trade_date = ?
            """, [today.isoformat(), today.isoformat()]).fetchdf()
        universe = udf.to_dict("records")
        symbols = [r.get("symbol") for r in universe if r.get("symbol")]

        hold_by_symbol = _load_history_rows(con, "bars_hold", symbols, today)

        pop_by_symbol: dict[str, list[dict]] = {}
        if pop_path.exists():
            pop_literal = str(pop_path).replace("\\", "/")
            pop_by_symbol = _load_history_rows(con, f"read_parquet('{pop_literal}')", symbols, today)

        history_by_symbol: dict[str, tuple[list[dict], str]] = {
            sym: choose_history_source(pop_by_symbol.get(sym, []), hold_by_symbol.get(sym, []), today)
            for sym in symbols
        }
    finally:
        con.close()
    return universe, history_by_symbol


def _load_polygon_enter_market_data() -> tuple[list[dict], dict[str, tuple[list[dict], str]]]:
    """Cloud-native SPIKE tape.

    Polygon supplies current price and cumulative day volume for the same
    curated universe the workstation used.  yfinance supplies completed daily
    bars for the 20-session median tests.  Both the price trigger and the
    volume-first trigger therefore retain their original Python gates without
    a workstation database.
    """
    import requests

    api_key = os.getenv("POLYGON_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY is not configured")
    symbols = sorted({value.strip().upper() for value in
                      os.getenv("SPIKE_UNIVERSE", "").split(",") if value.strip()})
    if not symbols:
        raise RuntimeError("SPIKE_UNIVERSE is not configured")
    response = requests.get(
        f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers",
        params={"apiKey": api_key, "tickers": ",".join(symbols)}, timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    tickers = payload.get("tickers") or []
    if not isinstance(tickers, list):
        raise RuntimeError("Polygon snapshot tickers is not a list")
    universe: list[dict] = []
    for item in tickers:
        if not isinstance(item, dict):
            continue
        symbol = item.get("ticker")
        if str(symbol).upper() not in symbols:
            continue
        day = item.get("day") or {}
        previous = item.get("prevDay") or {}
        trade = item.get("lastTrade") or {}
        minute = item.get("min") or {}
        price = trade.get("p") or minute.get("c") or day.get("c")
        prior_close = previous.get("c")
        volume = day.get("v")
        try:
            price_f, prior_f, volume_f = float(price), float(prior_close), float(volume)
        except (TypeError, ValueError):
            continue
        if prior_f <= 0:
            continue
        universe.append({
            "symbol": str(symbol), "price": price_f, "vol": volume_f,
            "prior_close": prior_f,
        })
    universe.sort(key=lambda row: float(row["price"]) * float(row["vol"]), reverse=True)
    history = _load_cloud_history(symbols, date.today())
    return universe, history


def _load_cloud_history(symbols: list[str], today: date) -> dict[str, tuple[list[dict], str]]:
    """Fetch completed daily bars once per day; fail individual names to broker fallback."""
    import yfinance as yf

    cache = HERE / f"cloud_history_{today.isoformat()}.json"
    if cache.exists():
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and set(symbols).issubset(payload):
                return {symbol: (payload.get(symbol) or [], "cloud")
                        if sessions_available_and_fresh(payload.get(symbol) or [], today)
                        else ([], "broker") for symbol in symbols}
        except (OSError, json.JSONDecodeError):
            pass
    result: dict[str, tuple[list[dict], str]] = {}
    cache_payload: dict[str, list[dict]] = {}
    for symbol in symbols:
        rows: list[dict] = []
        try:
            frame = yf.Ticker(symbol).history(period="3mo", interval="1d", auto_adjust=False)
            for stamp, row in frame.iterrows():
                bar_date = stamp.date()
                if bar_date >= today:
                    continue
                close = row.get("Close")
                volume = row.get("Volume")
                if close is None or volume is None:
                    continue
                rows.append({"symbol": symbol, "date": bar_date.isoformat(),
                             "close": float(close), "volume": float(volume)})
        except Exception:  # noqa: BLE001
            rows = []
        cache_payload[symbol] = rows
        result[symbol] = (rows, "cloud") if sessions_available_and_fresh(rows, today) else ([], "broker")
    save_json(cache, cache_payload)
    return result


# ---------------------------------------------------------------- signal + prompt + agent (same shape as EMBER)
READ_TOOLS = [
    "Read", "Write", "Edit",
    "mcp__robinhood-trading__get_accounts",
    "mcp__robinhood-trading__get_portfolio",
    "mcp__robinhood-trading__get_equity_quotes",
    "mcp__robinhood-trading__get_equity_positions",
    "mcp__robinhood-trading__get_equity_orders",
    "mcp__robinhood-trading__get_equity_historicals",   # broker-side history fallback (needs_broker
                                                          # candidates -- see SPIKE-PROMPT.md); a READ
                                                          # tool, always available regardless of arm state
    "mcp__robinhood-trading__review_equity_order",
]
ORDER_TOOLS = [
    "mcp__robinhood-trading__place_equity_order",
    "mcp__robinhood-trading__cancel_equity_order",
]


def build_allowlist(cfg: Cfg) -> list[str]:
    """Order tools are added ONLY when armed AND not dry-run AND a real slot
    size is configured (SPIKE_SLOT_PCT > 0) -- the third gate is SPIKE's own
    extra safety beyond EMBER's two-flag pattern, per the task spec. No
    option tool is ever on this allowlist -- SPIKE trades equities only."""
    tools = list(READ_TOOLS)
    if cfg.armed and not cfg.dry_run and cfg.slot_pct > 0:
        tools += ORDER_TOOLS
    return tools


def render_prompt(sig: dict) -> str:
    tmpl = PROMPT_MD.read_text(encoding="utf-8")
    return tmpl.replace("__SIGNAL_JSON__", json.dumps(sig, indent=2))


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
                  f"dry_run={sig['dry_run']} slot_pct={sig['slot_pct']} =====\n")
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
        notifier = HERE / "notify_spike.py"
        if notifier.exists():
            subprocess.run([sys.executable, str(notifier), tone, line], timeout=60, cwd=str(HERE))
    except Exception:
        pass


def tone_for(line: str) -> str:
    low = line.lower()
    if any(w in low for w in ("error", "fail", "reject", "unauth", "cannot", "unreachable",
                               "mismatch", "invalid", "timeout", "no log line", "missing")):
        return "bad"
    if "dry-run" in low:
        return "good"
    if re.search(r"\|\s*(BUY|SELL|SOLD|FILLED)\b", line):
        return "trade"
    return "good"


def _log(line: str) -> None:
    print(line)
    LOG_TXT.open("a", encoding="utf-8").write(line + "\n")


# ---------------------------------------------------------------- ENTER / MANAGE signal builders
def build_enter_signal(now: datetime, cfg: Cfg, local_positive: list[dict], needs_broker: list[dict],
                        state: dict, vf_candidates: list[dict] | None = None) -> dict:
    """`candidates` (local_positive) and `needs_broker` are NEITHER
    slot-checked NOR quote-checked yet (Fix 1) -- every symbol that passed
    the price band + local signal + dedupe + idempotency checks is
    included, uncapped. The agent resolves `needs_broker`'s own history/
    signal, pulls a live quote + spread gate for BOTH lists combined, THEN
    ranks the survivors by `dollar_volume` and allocates slots/envelope
    top-down (`rank_candidates()`/`allocate_slots()` are the exact
    reference logic -- see SPIKE-PROMPT.md). `vf_candidates` (module
    docstring #9) are LOCAL-history VF hits, tagged `trigger: "vf"` -- in
    `volfirst_mode == "shadow"` the agent must NEVER merge these into the
    real candidate/allocation pool (see `volfirst_mode`); in `"live"` they
    merge in exactly like `candidates`."""
    today_iso = now.date().isoformat()
    positions = state.get("positions") or []
    return {
        "mode": "ENTER", "now_ct": now.isoformat(timespec="seconds"), "today": today_iso,
        "account": ACCOUNT, "armed": int(cfg.armed), "dry_run": int(cfg.dry_run),
        "slot_pct": cfg.slot_pct, "envelope_pct": cfg.envelope_pct, "max_slots": cfg.max_slots,
        "max_sleeve_exposure_pct": max_sleeve_exposure_pct(cfg.slot_pct, cfg.max_slots),
        "spread_max": cfg.spread_max, "px_min": cfg.px_min, "px_max": cfg.px_max,
        "tp_pct": cfg.tp_pct, "max_sessions": cfg.max_sessions,
        "pending_stale_minutes": PENDING_STALE_MINUTES,
        "open_slots_used": occupied_slot_count(positions),
        "pending_positions": pending_positions(positions),
        "needing_tp_order": [p.get("symbol") for p in positions_needing_tp_order(positions)],
                                         # "manage-lite" (module docstring #8): every open position
                                         # missing a tp_order_id gets its resting GTC TP placed THIS
                                         # tick, not just at the 14:45 CT MANAGE run
        "candidates": local_positive,   # signal-positive, LOCAL history (pop/hold), trigger=price --
                                         # NOT yet quote-checked, spread-checked, ranked, or allocated
        "needs_broker": needs_broker,   # symbols with NO qualifying local history -- the agent
                                         # pulls get_equity_historicals itself for EVERY one (never
                                         # capped), 404 -> not_tradeable/skip, else checks price FIRST
                                         # then VF (SAME pull) -- see SPIKE-PROMPT.md Step 2b
        "volfirst_mode": cfg.volfirst,  # "shadow"|"live"|"off" -- module docstring #9
        "vf_vol_mult": cfg.vf_vol_mult, "vf_min_move": cfg.vf_min_move,
        "vf_max_move": cfg.vf_max_move, "vf_accel": cfg.vf_accel,
        "vf_candidates": vf_candidates or [],   # LOCAL-history VF hits, trigger=vf -- same
                                                 # not-yet-quote-checked state as `candidates`
    }


def build_manage_signal(now: datetime, cfg: Cfg, state: dict) -> dict:
    today = now.date()
    positions = state.get("positions") or []
    open_positions = [p for p in positions if p.get("state") == "open"]
    due_time = positions_due_for_time_exit(positions, today, cfg)
    needing_tp = positions_needing_tp_order(positions)
    return {
        "mode": "MANAGE", "now_ct": now.isoformat(timespec="seconds"), "today": today.isoformat(),
        "account": ACCOUNT, "armed": int(cfg.armed), "dry_run": int(cfg.dry_run),
        "max_sessions": cfg.max_sessions,
        "open_positions": open_positions,
        "due_time_exits": [p.get("symbol") for p in due_time],
        "needing_tp_order": [p.get("symbol") for p in needing_tp],
        "pending_positions": pending_positions(positions),   # leftover from the day's last ENTER
                                                               # tick -- ENTER won't run again until
                                                               # tomorrow, so MANAGE is the last
                                                               # chance to reconcile these today.
        "pending_stale_minutes": PENDING_STALE_MINUTES,
    }


def _invoke_agent(mode: str, sig: dict, cfg: Cfg) -> int:
    """Runs the agent and does the same pre/post LOG_TXT tail-comparison
    EMBER's own _run_mode() uses to detect whether the agent actually wrote
    a result this run."""
    pre = LOG_TXT.read_text(encoding="utf-8").splitlines()[-1] if LOG_TXT.exists() else ""
    rc = run_agent(sig, cfg)
    post = LOG_TXT.read_text(encoding="utf-8").splitlines()[-1] if LOG_TXT.exists() else ""
    if not post or post == pre:
        tail = RUN_OUTPUT.read_text(encoding="utf-8", errors="replace")[-4000:] if RUN_OUTPUT.exists() else ""
        if "Failed to authenticate" in tail or "OAuth" in tail:
            line = (f"{sig['now_ct']} CT | SPIKE | {mode} | CLAUDE AUTH FAILED - "
                     f"CLAUDE_CODE_OAUTH_TOKEN is empty or invalid. No orders possible.")
        else:
            line = (f"{sig['now_ct']} CT | SPIKE | {mode} | agent wrote no log line "
                     f"(claude exit={rc}) - check ember/spike-run-output.log")
        LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
        notify("bad", line)
        return 1
    notify(tone_for(post), post)
    return 0


# ---------------------------------------------------------------- ENTER
def run_enter(now: datetime, cfg: Cfg, *, dry_run_cli: bool = False) -> int:
    """Discord volume is capped at exactly TWO Python-authored lines per
    tick (a header + a compact skip summary), regardless of how many
    candidates were evaluated -- every per-candidate detail still goes to
    spike-log.txt via _log()/format_skip_line(), just never to Discord
    directly. A third line (the agent's OWN single final log line, via
    _invoke_agent's tail-diff notify) is added only when the agent actually
    ran and did something (a real order, a dry-run log, or its own
    end-of-run skip summary)."""
    today = now.date()
    ts = now.isoformat(timespec="seconds")

    # Header -- always the FIRST line, every tick, per spec.
    header = (f"{ts} CT | SPIKE | ENTER | slot_pct={cfg.slot_pct}% x max_slots={cfg.max_slots} "
              f"-> max sleeve exposure {max_sleeve_exposure_pct(cfg.slot_pct, cfg.max_slots)}% of account")
    _log(header)

    if not is_trading_day(today):
        line = f"{ts} CT | SPIKE | ENTER | not a trading day (weekend) -- no-op"
        _log(line)
        notify(tone_for(header), header)
        notify(tone_for(line), line)
        return 0

    state = load_state()
    positions = state.get("positions") or []
    seen = state.get("seen") or {}
    prev_tick_volume = state.get("tape_prev") or {}

    # "manage-lite" (module docstring #8): pending-fill reconciliation and
    # missing-TP detection must happen EVERY tick, even one with an empty
    # tape or zero new candidates -- a just-filled buy's resting TP must
    # never wait for the next candidate to show up, let alone for the
    # 14:45 CT MANAGE run.
    pending = pending_positions(positions)
    needing_tp = positions_needing_tp_order(positions)

    universe, history_by_symbol = load_enter_market_data(today)
    accepted: list[dict] = []
    needs_broker: list[dict] = []
    vf_local: list[dict] = []
    skips: list[tuple[str, str]] = []
    if universe:
        accepted, needs_broker, seen_out, skips = select_enter_candidates(
            universe, history_by_symbol, positions, seen, today, cfg, prev_tick_volume)

        # VF (module docstring #9) -- evaluated for every in-band symbol
        # that did NOT already fire the price rule locally this tick.
        price_hit_symbols = {r.get("symbol") for r in accepted}
        vf_local, seen_out, vf_skips = select_vf_candidates(
            universe, history_by_symbol, price_hit_symbols, prev_tick_volume,
            positions, seen_out, today, cfg)
        skips = skips + vf_skips

        for sym, reason in skips:
            _log(format_skip_line(sym, reason))   # full detail -- LOCAL LOG ONLY, never notified
        state["seen"] = seen_out
        state["tape_prev"] = {r.get("symbol"): r.get("vol") for r in universe if r.get("symbol")}
        if not dry_run_cli:
            save_json(STATE_FILE, state)   # persist seen/tape_prev BEFORE the agent ever runs, so
                                            # a crash mid-run never re-fires the same symbol next tick
        summary_line = f"{ts} CT | SPIKE | ENTER | {build_skip_summary(skips)}"
    else:
        summary_line = f"{ts} CT | SPIKE | ENTER | no tape rows for {today.isoformat()}"
    _log(summary_line)
    notify(tone_for(header), header)
    notify(tone_for(summary_line), summary_line)

    if not accepted and not needs_broker and not vf_local and not pending and not needing_tp:
        return 0

    sig = build_enter_signal(now, cfg, accepted, needs_broker, state, vf_local)
    if dry_run_cli:
        print(json.dumps(sig, indent=2))
        return 0
    return _invoke_agent("ENTER", sig, cfg)


# ---------------------------------------------------------------- MANAGE
def run_manage(now: datetime, cfg: Cfg, *, dry_run_cli: bool = False) -> int:
    today = now.date()
    ts = now.isoformat(timespec="seconds")

    if not is_trading_day(today):
        line = f"{ts} CT | SPIKE | MANAGE | not a trading day (weekend) -- no-op"
        _log(line); notify(tone_for(line), line)
        return 0

    state = load_state()
    positions = state.get("positions") or []
    open_positions = [p for p in positions if p.get("state") == "open"]
    pending = pending_positions(positions)
    if not open_positions and not pending:
        line = f"{ts} CT | SPIKE | MANAGE | nothing open, nothing pending -- no-op"
        _log(line); notify(tone_for(line), line)
        return 0

    sig = build_manage_signal(now, cfg, state)
    if dry_run_cli:
        print(json.dumps(sig, indent=2))
        return 0
    return _invoke_agent("MANAGE", sig, cfg)


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=MODES, required=True)
    ap.add_argument("--at", default=None, help="Override now as ISO datetime (CT)")
    ap.add_argument("--dry-run", action="store_true",
                     help="Print the computed signal; never invoke the agent or touch state "
                          "(other than the seen-dedupe write on ENTER, skipped too).")
    a = ap.parse_args()
    cfg = load_cfg()
    now = (datetime.fromisoformat(a.at).replace(tzinfo=CT) if a.at else datetime.now(CT))
    try:
        if a.mode == "enter":
            return run_enter(now, cfg, dry_run_cli=a.dry_run)
        return run_manage(now, cfg, dry_run_cli=a.dry_run)
    except Exception as e:  # noqa: BLE001 -- never retry-loop; log and exit non-zero
        line = f"{now.isoformat(timespec='seconds')} CT | SPIKE | ERROR | {type(e).__name__}: {e}"
        try:
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
        except Exception:
            pass
        print(line, file=sys.stderr)
        return 1


if __name__ == "__main__":
    if not ember_lock.acquire_lock(LOCK_FILE):
        raise SystemExit(0)
    try:
        raise SystemExit(main())
    finally:
        ember_lock.release_lock(LOCK_FILE)
