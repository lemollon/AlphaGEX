"""NIGHT SHIFT - Render-capable driver for the TQQQ overnight overlay.

PREREG_NIGHT / tools/mr_book/PREREG_NIGHT.md, GATE_NIGHT +
GATE_NIGHT_HELDOUT both PASS on TQQQ as of 2026-09-10; see DEPLOY.md before
ever arming.

The same driver can be invoked by the Render scheduler or a local task. It
uses persistent order_state.json, an append-only intents.log (one line before every
order attempt), an order agent invoked as `claude -p NIGHT-PROMPT.md` with the
Robinhood MCP only when a mode is due, NIGHT_ARMED / NIGHT_DRY_RUN env flags
gating the order-tool allowlist, and the same notify/halt conventions as
call_diag (a manual NIGHT_HALTED override in .env, plus this file's
own hard 09:00 CT give-up on an unsold position - see mode = NIGHT_SELL).

Unlike call_diag (options structures), this bot holds a single
EQUITY position (TQQQ only) bought with a dollar amount and sold by an EXACT
share count it tracked itself. There is no options chain, no strikes, no
multi-leg sequencing. Every mode is either a pure-Python no-op (nothing due)
or a live agent run.

Every minute 08:30-09:00 CT AND 14:59-15:01 CT weekdays this script decides
which of three modes is due, keyed by trade date in order_state.json
(idempotent -- a second run in the same mode does nothing new):

  RECONCILE   08:33 CT, first thing every morning. One agent run every day:
              pull get_portfolio (cache total_value for the afternoon's BUY
              sizing) and get_equity_positions (TQQQ) and reconcile the
              broker's TQQQ share count against this bot's OWN known position
              -- NEVER an exact-equality check, since the book bot on the
              devbox (leg "F") also holds TQQQ shares in the SAME account and
              those shares are fungible on the broker side; this bot can only
              confirm broker_qty >= its own known qty (a sanity floor), never
              that the broker's number belongs entirely to this bot. Mirrors
              call_diag's RECONCILE role (a data-confirmation step, not a
              trade) and its total_value cache convention exactly.
  NIGHT_SELL  08:34-08:36 CT normal window, then a forced retry ladder every
              tick until a hard 09:00 CT give-up (ALERT logged, both here and
              by the agent). Python recomputes every tick whether this bot has
              an OPEN position (order_state["position"] is not null); if not,
              pure no-op, no agent call. If it does, the agent sells EXACTLY
              `order_state["position"]["qty"]` shares -- the qty THIS bot's
              own buy filled, never "whatever TQQQ shares the account holds"
              (get_equity_positions is read by RECONCILE for the sanity floor
              above, never by NIGHT_SELL to decide how many shares to sell).
              This is the tested invariant that keeps the book bot's own TQQQ
              (leg F) untouched. NIGHT_HALTED never blocks this mode -- a halt
              blocks new risk (NIGHT_BUY), never the flatten-by-morning safety
              action.
  NIGHT_BUY   14:59-15:00 CT (the driver's own minute-granularity convention,
              same minute convention as the other EMBER close jobs -- the spec's
              "14:59:30" target is honored by aiming the order inside this
              single-minute window, not by sub-minute clock gating; see
              DEPLOY.md's declared deviations). Python supplies NIGHT's own
              envelope and the cached total_value from the morning RECONCILE;
              the agent pulls LIVE buying_power and computes:
              `min(NIGHT_ENVELOPE_PCT% x total_value, buying_power - $20)`.
              Missing total_value or buying_power fails closed. See
              buy_dollar_amount() below for the exact formula both this file
              and NIGHT-PROMPT.md follow. NIGHT_HALTED (or a position already
              open, which should never happen -- NIGHT_SELL should have
              flattened it that same morning) skips this mode with no agent
              call.

Usage:
  python run_night.py                        # scheduled tick
  python run_night.py --at 2026-09-11T14:59 [--dry-run]
  python run_night.py --once NIGHT_BUY --dry-run [--force]
                                             # run exactly ONE tick of MODE now,
                                             # bypassing the clock. Calls the REAL
                                             # agent (no stub) -- --dry-run forces
                                             # NIGHT_DRY_RUN=1 for this run regardless
                                             # of .env, so it can never place an
                                             # order; --force re-runs a mode already
                                             # recorded today, dry-run only.
  python run_night.py --reset-halt
                                             # clears a triggered halt; refuses
                                             # unless .env NIGHT_HALTED=0
  python run_night.py --unit-test
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
CODE_DIR = Path(__file__).resolve().parent
HERE = Path(os.getenv("EMBER_NIGHT_DATA_DIR", str(CODE_DIR))).expanduser().resolve()
HERE.mkdir(parents=True, exist_ok=True)
ORDER_STATE = HERE / "order_state.json"
LOG_TXT = HERE / "night-log.txt"
RUN_OUTPUT = HERE / "run-output.log"
LEDGER_CSV = HERE / "night-ledger.csv"
INTENTS_LOG = HERE / "intents.log"
PROMPT_MD = CODE_DIR / "NIGHT-PROMPT.md"
ENV_FILE = HERE / ".env"
# tick.log is written by the .cmd scheduled-task wrapper's own stdout
# redirect (see NightShiftTick.cmd), never by this file directly -- same
# split as call_diag/daily_cal.

ACCOUNT = "570892331"           # Robinhood "Agentic" account -- never point this bot at any other.
DEFAULT_TICKER = "TQQQ"         # PREREG_NIGHT: TQQQ PASSES both GATE_NIGHT and the held-out
                                 # 2010-2019 re-test; UPRO also passed the prereg but the task
                                 # scopes this bot to TQQQ only.
DEFAULT_BUFFER_USD = 20.0       # "$20" buying-power buffer from the spec, never traded through.
DEFAULT_ENVELOPE_PCT = 30.0     # Current standalone NIGHT sleeve allocation.

# ---- clock (CT) ---------------------------------------------------------
# Morning block: RECONCILE, then flatten any position this bot itself opened.
MORNING_START_CT = time(8, 30)
RECONCILE_AT_CT = time(8, 33)
SELL_START_CT = time(8, 34)
SELL_NORMAL_CUTOFF_CT = time(8, 37)   # "must be flat before 08:37 CT" -- ALERT every tick past this
SELL_GIVEUP_CT = time(9, 0)           # hard stop retrying automatically; ALERT; position left open
MORNING_END_CT = time(9, 0)

# Afternoon block: one dollar-based BUY, sized from NIGHT's own envelope.
AFTERNOON_START_CT = time(14, 59)     # minute-granularity convention (see module docstring)
BUY_CUTOFF_CT = time(15, 0)           # retry each tick through this minute, then give up
AFTERNOON_END_CT = time(15, 1)

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

ONCE_MODES = ("RECONCILE", "NIGHT_SELL", "NIGHT_BUY")
MODE_STATE_KEY = {"RECONCILE": "reconcile", "NIGHT_SELL": "sell", "NIGHT_BUY": "buy"}


# ---------------------------------------------------------------- config
@dataclass
class Cfg:
    armed: bool = False
    dry_run: bool = True
    halted_env: bool = False        # NIGHT_HALTED in .env -- Leron's manual override, global.
                                     # Blocks NIGHT_BUY only -- never NIGHT_SELL (a halt must
                                     # never trap the bot into MORE overnight risk than it
                                     # already has; flattening is always allowed).
    ticker: str = DEFAULT_TICKER
    buffer_usd: float = DEFAULT_BUFFER_USD
    envelope_pct: float = DEFAULT_ENVELOPE_PCT
    claude_bin: str = "claude"


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
    env = {**env, **{k: v for k, v in os.environ.items() if k.startswith("NIGHT_")}}
    return Cfg(
        armed=env.get("NIGHT_ARMED", "0") == "1",
        dry_run=env.get("NIGHT_DRY_RUN", "1") != "0",
        halted_env=env.get("NIGHT_HALTED", "0") == "1",
        ticker=(env.get("NIGHT_TICKER", DEFAULT_TICKER) or DEFAULT_TICKER).strip().upper(),
        buffer_usd=float(env.get("NIGHT_BUY_BUFFER_USD", str(DEFAULT_BUFFER_USD))),
        envelope_pct=float(env.get("NIGHT_ENVELOPE_PCT", str(DEFAULT_ENVELOPE_PCT))),
        claude_bin=env.get("NIGHT_CLAUDE_BIN", "claude"),
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


# ---------------------------------------------------------------- sizing (pure)
def buy_dollar_amount(night_envelope_usd: float | None, buying_power: float | None,
                      buffer_usd: float) -> tuple[float, str]:
    """Return the tighter of NIGHT's allocation and available buying power.

    Missing portfolio value or buying power fails closed; neither is guessed.
    """
    if buying_power is None:
        return 0.0, "buying_power unavailable (broker pull failed) -- NO-BUY, never guessed"
    if night_envelope_usd is None:
        return 0.0, "night_envelope_usd unavailable (total_value not cached) -- NO-BUY, never guessed"
    bp_minus_buffer = max(0.0, round(buying_power - buffer_usd, 2))
    return round(min(night_envelope_usd, bp_minus_buffer), 2), \
        "min(night_envelope_usd, buying_power - buffer)"


# ---------------------------------------------------------------- halt (pure)
def is_globally_halted(order_state: dict, cfg: Cfg) -> bool:
    return bool(cfg.halted_env) or bool((order_state.get("halt") or {}).get("active"))


# ---------------------------------------------------------------- mode decision (pure)
def decide(now: datetime, day: dict) -> tuple[str | None, str]:
    """Pure: (mode, reason). day = order_state[today] (may be {}). Two disjoint
    daily windows -- morning (RECONCILE -> NIGHT_SELL) and afternoon
    (NIGHT_BUY) -- rather than one continuous window like call_diag/daily_cal,
    since this bot has nothing to do mid-day. No market-holiday calendar
    consulted here (same documented stdlib-only limitation as call_diag's own
    decide()) -- a holiday resolves as "outside window" every tick, never a
    crash or a misfire, and RECONCILE/NIGHT_SELL/NIGHT_BUY simply never fire
    that day (no position was ever opened the trading day before a holiday
    without a corresponding sell morning, since holidays are always weekdays
    excluded from the SAME weekday-only gate real trading days pass through --
    a genuine market holiday that isn't also a weekend is NOT specially
    detected, a documented limitation, same spirit as call_diag/daily_cal)."""
    t = now.time()
    if now.weekday() >= 5:
        return None, "weekend"
    in_morning = MORNING_START_CT <= t <= MORNING_END_CT
    in_afternoon = AFTERNOON_START_CT <= t <= AFTERNOON_END_CT
    if not in_morning and not in_afternoon:
        return None, "outside window"

    if in_morning:
        reconcile = day.get("reconcile") or {}
        sell = day.get("sell") or {}
        if not reconcile.get("done"):
            if t < RECONCILE_AT_CT:
                return None, "before reconcile time"
            return "RECONCILE", "reconcile position vs order_state, cache total_value"
        if not sell.get("done"):
            if t < SELL_START_CT:
                return None, "reconcile done, before sell time"
            return "NIGHT_SELL", "sell window"
        return None, "morning complete"

    buy = day.get("buy") or {}
    if not buy.get("done"):
        if t < AFTERNOON_START_CT:
            return None, "before buy time"
        return "NIGHT_BUY", "buy window"
    return None, "afternoon complete"


# ---------------------------------------------------------------- signal + prompt
def build_signal(now: datetime, mode: str, day: dict, order_state: dict, cfg: Cfg) -> dict:
    today_iso = now.date().isoformat()
    position = order_state.get("position")
    sig = {
        "mode": mode, "now_ct": now.isoformat(timespec="seconds"), "today": today_iso,
        "account": ACCOUNT, "ticker": cfg.ticker, "armed": int(cfg.armed), "dry_run": int(cfg.dry_run),
        "buffer_usd": cfg.buffer_usd,
        "sell_start_ct": SELL_START_CT.strftime("%H:%M"),
        "sell_normal_cutoff_ct": SELL_NORMAL_CUTOFF_CT.strftime("%H:%M"),
        "sell_giveup_ct": SELL_GIVEUP_CT.strftime("%H:%M"),
        "buy_start_ct": AFTERNOON_START_CT.strftime("%H:%M"),
        "buy_cutoff_ct": BUY_CUTOFF_CT.strftime("%H:%M"),
    }
    if mode == "RECONCILE":
        sig["known_position"] = position
    elif mode == "NIGHT_SELL":
        # own_qty is the ENTIRE sell decision -- this bot's own filled buy qty,
        # never the broker's total TQQQ holding (which may also include the
        # book bot's "F" leg shares, same account, fungible). See module
        # docstring / DEPLOY.md for the invariant this protects.
        sig["own_qty"] = (position or {}).get("qty")
        sig["opened_date"] = (position or {}).get("opened_date")
        sig["entry_fill_price"] = (position or {}).get("entry_fill_price")
        sig["entry_dollar_amount"] = (position or {}).get("entry_dollar_amount")
    elif mode == "NIGHT_BUY":
        total_value = (day.get("total_value") or {}).get("value")
        night_envelope_usd = (
            round(cfg.envelope_pct / 100.0 * total_value, 2)
            if total_value is not None else None
        )
        sig.update({
            "night_envelope_pct": cfg.envelope_pct,
            "total_value": total_value, "total_value_as_of_ct": (day.get("total_value") or {}).get("as_of_ct"),
            "night_envelope_usd": night_envelope_usd,
        })
    keys = day.setdefault("ref_ids", {})
    if mode == "NIGHT_SELL":
        keys.setdefault("sell", str(uuid.uuid4()))
    if mode == "NIGHT_BUY":
        keys.setdefault("buy", str(uuid.uuid4()))
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
    # length limit call_diag/daily_cal's run_agent() documents (WinError 206).
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
                               "mismatch", "stale", "invalid", "timeout", "halted", "alert",
                               "no log line", "missing")):
        return "bad"
    if "dry-run" in low:
        return "good"
    if re.search(r"\|\s*(BUY|SELL|CYCLE)\b", line):
        return "trade"
    return "good"


# ---------------------------------------------------------------- ledger
LEDGER_COLS = ["date", "buy_fill_price", "buy_qty", "buy_dollar_amount",
               "sell_fill_price", "sell_qty", "sell_dollar_amount",
               "pnl_usd", "pnl_pct_of_account", "dry_run"]


def ledger_row(position: dict, sell: dict, *, dry_run: bool) -> dict | None:
    if sell.get("state") != "filled":
        return None
    buy_qty = position.get("qty")
    buy_price = position.get("entry_fill_price")
    buy_dollar = position.get("entry_dollar_amount")
    sell_qty = sell.get("filled_qty")
    sell_price = sell.get("fill_price")
    if None in (buy_qty, buy_price, buy_dollar, sell_qty, sell_price):
        return None
    sell_dollar = round(float(sell_qty) * float(sell_price), 2)
    pnl_usd = round(sell_dollar - float(buy_dollar), 2)
    total_value_at_buy = position.get("total_value_at_buy")
    pnl_pct = round(pnl_usd / float(total_value_at_buy) * 100, 4) if total_value_at_buy else None
    return {
        "date": position.get("opened_date"), "buy_fill_price": buy_price, "buy_qty": buy_qty,
        "buy_dollar_amount": buy_dollar, "sell_fill_price": sell_price, "sell_qty": sell_qty,
        "sell_dollar_amount": sell_dollar, "pnl_usd": pnl_usd, "pnl_pct_of_account": pnl_pct,
        "dry_run": int(dry_run),
    }


def append_ledger(row: dict) -> None:
    new = not LEDGER_CSV.exists()
    with LEDGER_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        if new:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------- envelope-sharing (pure)
def night_position_value(order_state: dict, live_price: float | None) -> float:
    """This bot's OWN dollar exposure right now -- qty x live price if a
    position is open, else 0.0. Read by ../envelopes/check_envelopes.py to
    position is open, else 0.0. Used by envelope audits; NIGHT now owns a
    standalone allocation rather than borrowing another bot's capacity."""
    position = order_state.get("position")
    if not position or live_price is None:
        return 0.0
    return round(float(position.get("qty") or 0.0) * float(live_price), 2)


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
                  "(NIGHT_DRY_RUN=1 in .env or --dry-run on the command line). Refusing to "
                  "re-fire a live mode.")
            return 2
    else:
        mode, why = decide(now, day)
    print(f"{now.isoformat(timespec='seconds')} CT | mode={mode} | {why} | "
          f"armed={int(cfg.armed)} dry_run={int(cfg.dry_run)} global_halted={int(global_halted)}")
    if mode is None:
        return 0

    position = order_state.get("position")
    t = now.time()

    # ---- NIGHT_SELL: pure-Python no-op if nothing is open; hard 09:00 give-up ----
    if mode == "NIGHT_SELL":
        if position is None:
            day["sell"] = {"done": True, "state": "skipped", "reason": "no open NIGHT position"}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = f"{now.isoformat(timespec='seconds')} CT | NIGHT_SELL | no open NIGHT position, nothing to sell"
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("good", line)
            if forced_mode:
                print(line)
            return 0
        if t >= SELL_GIVEUP_CT and not forced_mode:
            day["sell"] = {"done": True, "state": "giveup",
                            "reason": f"still open at {SELL_GIVEUP_CT.strftime('%H:%M')} CT give-up",
                            "qty": position["qty"]}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = (f"{now.isoformat(timespec='seconds')} CT | NIGHT_SELL | ALERT: giving up automated "
                     f"sell for today -- {position['qty']} shares {cfg.ticker} still open past "
                     f"{SELL_GIVEUP_CT.strftime('%H:%M')} CT give-up. NEVER holds past 09:00 "
                     f"automatically -- HUMAN MUST INTERVENE.")
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("bad", line)
            if forced_mode:
                print(line)
            return 1
        if t >= SELL_NORMAL_CUTOFF_CT:
            alert_line = (f"{now.isoformat(timespec='seconds')} CT | NIGHT_SELL | ALERT: still holding "
                           f"past {SELL_NORMAL_CUTOFF_CT.strftime('%H:%M')} CT deadline, retrying "
                           f"(give-up {SELL_GIVEUP_CT.strftime('%H:%M')} CT)")
            LOG_TXT.open("a", encoding="utf-8").write(alert_line + "\n")
            notify("bad", alert_line)
        # else fall through to the agent -- sells exactly position["qty"] shares.

    # ---- NIGHT_BUY: halt / already-open guard, pure Python, before the agent ----
    if mode == "NIGHT_BUY":
        if global_halted:
            day["buy"] = {"done": True, "state": "skipped", "reason": "HALTED"}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = f"{now.isoformat(timespec='seconds')} CT | NIGHT_BUY | NO-OP: HALTED, refusing entry, never calls the agent"
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("bad", line)
            if forced_mode:
                print(line)
            return 0
        if position is not None:
            day["buy"] = {"done": True, "state": "skipped",
                           "reason": (f"position already open (qty={position['qty']}, opened "
                                      f"{position.get('opened_date')}) -- refusing to buy on top "
                                      f"of an unsold position")}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = (f"{now.isoformat(timespec='seconds')} CT | NIGHT_BUY | ALERT: position already open "
                     f"(qty={position['qty']}) -- NIGHT_SELL should have flattened this morning. Refusing "
                     f"to double-buy.")
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("bad", line)
            if forced_mode:
                print(line)
            return 1
        if t >= AFTERNOON_END_CT and not forced_mode:
            day["buy"] = {"done": True, "state": "no_buy",
                           "reason": f"unresolved past {AFTERNOON_END_CT.strftime('%H:%M')} CT window close"}
            order_state[today] = day
            save_json(ORDER_STATE, order_state)
            line = f"{now.isoformat(timespec='seconds')} CT | NIGHT_BUY | NO-BUY: window closed unresolved"
            LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
            notify("bad", line)
            if forced_mode:
                print(line)
            return 1
        # else fall through to the agent.

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
                     f"- check night_shift/run-output.log")
        LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
        notify("bad", line)
        if forced_mode:
            print(line)
        return 1
    notify(tone_for(post), post)
    if forced_mode:
        print(post)

    # ---- post-agent bookkeeping: RECONCILE/NIGHT_SELL/NIGHT_BUY are marked --
    # "done" for the day only once the agent has actually resolved everything
    # it was handed -- read-back + fallback-completion pass, mirroring
    # call_diag/daily_cal's own read-back convention.
    order_state = load_json(ORDER_STATE)
    day = order_state.get(today) or {}
    if mode == "RECONCILE":
        day.setdefault("reconcile", {})["done"] = True
        order_state[today] = day
        save_json(ORDER_STATE, order_state)
    if mode == "NIGHT_SELL":
        sell = day.setdefault("sell", {})
        if sell.get("state") in ("filled", "no_fill", "cancelled") or now.time() >= SELL_GIVEUP_CT:
            sell["done"] = True
        order_state[today] = day
        save_json(ORDER_STATE, order_state)
    if mode == "NIGHT_BUY":
        buy = day.setdefault("buy", {})
        if buy.get("state") in ("filled", "no_fill", "cancelled") or now.time() >= BUY_CUTOFF_CT:
            buy["done"] = True
        order_state[today] = day
        save_json(ORDER_STATE, order_state)

    # ---- ledger: append a row + clear position the moment NIGHT_SELL fills ---
    order_state = load_json(ORDER_STATE)
    day = order_state.get(today) or {}
    if mode == "NIGHT_SELL":
        sell = day.get("sell") or {}
        position = order_state.get("position")
        if position and sell.get("state") == "filled" and not sell.get("ledgered"):
            row = ledger_row(position, sell, dry_run=cfg.dry_run)
            if row:
                append_ledger(row)
                sell["ledgered"] = True
                day["sell"] = sell
                order_state["position"] = None
                order_state[today] = day
                save_json(ORDER_STATE, order_state)
                cycle_line = (f"{now.isoformat(timespec='seconds')} CT | CYCLE | bought {row['buy_qty']} "
                               f"{cfg.ticker} @{row['buy_fill_price']} (${row['buy_dollar_amount']}) -> "
                               f"sold @{row['sell_fill_price']} (${row['sell_dollar_amount']}) | "
                               f"P&L ${row['pnl_usd']}"
                               + (f" ({row['pnl_pct_of_account']}% of account)" if row['pnl_pct_of_account'] is not None else "")
                               + f" | dry_run={row['dry_run']}")
                LOG_TXT.open("a", encoding="utf-8").write(cycle_line + "\n")
                notify("trade", cycle_line)

    return 0


def reset_halt(cfg: Cfg) -> int:
    """Manual-only. Refuses unless .env already has NIGHT_HALTED=0. Clears
    order_state["halt"] -- the bot never clears it itself."""
    if cfg.halted_env:
        print("REFUSED: .env still has NIGHT_HALTED=1. Set NIGHT_HALTED=0 first.")
        return 2
    order_state = load_json(ORDER_STATE)
    order_state["halt"] = {"active": False}
    save_json(ORDER_STATE, order_state)
    line = f"{datetime.now(CT).isoformat(timespec='seconds')} CT | RESET | global halt cleared"
    LOG_TXT.open("a", encoding="utf-8").write(line + "\n")
    print("global halt cleared")
    return 0


# ---------------------------------------------------------------- unit tests
def _unit_tests() -> int:
    # ---- buy sizing ----
    amt, why = buy_dollar_amount(150.0, 500.0, 20.0)
    assert amt == 150.0, (amt, why)          # 30% envelope is the binding constraint
    amt2, why2 = buy_dollar_amount(150.0, 120.0, 20.0)
    assert amt2 == 100.0, (amt2, why2)       # buying_power - buffer is binding
    amt3, why3 = buy_dollar_amount(None, 300.0, 20.0)
    assert amt3 == 0.0 and "never guessed" in why3
    amt4, why4 = buy_dollar_amount(150.0, None, 20.0)
    assert amt4 == 0.0 and "never guessed" in why4
    amt5, _ = buy_dollar_amount(150.0, 10.0, 20.0)
    assert amt5 == 0.0                        # buying_power below buffer -> never negative

    # ---- decide(): window logic ----
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
    m, why = decide(datetime(2026, 9, 11, 8, 33, 30, tzinfo=CT), day1)
    assert m is None and "before sell time" in why
    m, why = decide(datetime(2026, 9, 11, 8, 34, tzinfo=CT), day1)
    assert m == "NIGHT_SELL"
    day2 = {"reconcile": {"done": True}, "sell": {"done": True}}
    m, why = decide(datetime(2026, 9, 11, 8, 50, tzinfo=CT), day2)
    assert m is None and why == "morning complete"
    m, why = decide(datetime(2026, 9, 11, 11, 0, tzinfo=CT), day2)
    assert m is None and why == "outside window"
    m, why = decide(datetime(2026, 9, 11, 14, 58, tzinfo=CT), day2)
    assert m is None and why == "outside window"   # AFTERNOON_START_CT is the window's own lower bound
    m, why = decide(datetime(2026, 9, 11, 14, 59, tzinfo=CT), day2)
    assert m == "NIGHT_BUY"
    day3 = {"reconcile": {"done": True}, "sell": {"done": True}, "buy": {"done": True}}
    m, why = decide(datetime(2026, 9, 11, 15, 0, 30, tzinfo=CT), day3)
    assert m is None and why == "afternoon complete"

    # ---- sell-only-own-qty invariant: signal carries ONLY this bot's own qty --
    order_state_own = {"position": {"qty": 4.321, "opened_date": "2026-09-10",
                                     "entry_fill_price": 80.5, "entry_dollar_amount": 348.0}}
    cfg = Cfg()
    sig = build_signal(datetime(2026, 9, 11, 8, 35, tzinfo=CT), "NIGHT_SELL", {}, order_state_own, cfg)
    assert sig["own_qty"] == 4.321
    assert "broker_qty" not in sig and "total_qty" not in sig  # never a broker-wide figure
    # Even a much larger simulated broker-side holding (as if F's shares were
    # mixed in) must never change what NIGHT_SELL is told to sell -- own_qty
    # is derived ONLY from order_state["position"], never from any broker
    # positions total, which this function doesn't even accept as an argument.
    order_state_with_f = {"position": {"qty": 4.321, "opened_date": "2026-09-10",
                                        "entry_fill_price": 80.5, "entry_dollar_amount": 348.0},
                           "_simulated_broker_total_tqqq_including_F_leg": 9999.0}
    sig2 = build_signal(datetime(2026, 9, 11, 8, 35, tzinfo=CT), "NIGHT_SELL", {}, order_state_with_f, cfg)
    assert sig2["own_qty"] == 4.321

    sig_flat = build_signal(datetime(2026, 9, 11, 8, 35, tzinfo=CT), "NIGHT_SELL", {}, {"position": None}, cfg)
    assert sig_flat["own_qty"] is None

    # ---- allowlist gate ----
    assert set(build_allowlist(Cfg(armed=False, dry_run=True))) == set(READ_TOOLS)
    assert set(build_allowlist(Cfg(armed=True, dry_run=True))) == set(READ_TOOLS)  # dry-run wins
    assert set(build_allowlist(Cfg(armed=False, dry_run=False))) == set(READ_TOOLS)  # unarmed wins
    assert set(build_allowlist(Cfg(armed=True, dry_run=False))) == set(READ_TOOLS) | set(ORDER_TOOLS)

    # ---- ledger math ----
    pos = {"opened_date": "2026-09-10", "qty": 4.0, "entry_fill_price": 87.0,
           "entry_dollar_amount": 348.0, "total_value_at_buy": 696.0}
    sell = {"state": "filled", "filled_qty": 4.0, "fill_price": 90.0}
    row = ledger_row(pos, sell, dry_run=False)
    assert row is not None
    assert row["sell_dollar_amount"] == 360.0
    assert row["pnl_usd"] == 12.0
    assert row["pnl_pct_of_account"] == round(12.0 / 696.0 * 100, 4)
    assert ledger_row(pos, {"state": "pending"}, dry_run=False) is None

    # ---- envelope-sharing (own position value, never F's) ----
    assert night_position_value({"position": None}, 90.0) == 0.0
    assert night_position_value({"position": {"qty": 4.0}}, 90.0) == 360.0
    assert night_position_value({"position": {"qty": 4.0}}, None) == 0.0

    # ---- halt ----
    assert is_globally_halted({}, Cfg(halted_env=True)) is True
    assert is_globally_halted({"halt": {"active": True}}, Cfg(halted_env=False)) is True
    assert is_globally_halted({}, Cfg(halted_env=False)) is False

    print("ALL UNIT TESTS PASSED")
    return 0


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--at", default=None, help="Override now as ISO datetime (CT)")
    ap.add_argument("--dry-run", action="store_true",
                     help="Without --once: decide + print the signal; do not run the agent or "
                          "touch state. With --once: force NIGHT_DRY_RUN=1 for this run regardless "
                          "of .env.")
    ap.add_argument("--once", metavar="MODE", choices=ONCE_MODES, default=None,
                     help="Run exactly one tick of MODE right now, bypassing the clock.")
    ap.add_argument("--force", action="store_true",
                     help="With --once: re-run a mode already recorded for today. Refused unless "
                          "dry_run is True.")
    ap.add_argument("--reset-halt", action="store_true",
                     help="Clear a triggered halt. Refuses unless .env NIGHT_HALTED=0.")
    ap.add_argument("--unit-test", action="store_true")
    a = ap.parse_args()
    if a.unit_test:
        return _unit_tests()
    cfg = load_cfg()
    if a.reset_halt:
        return reset_halt(cfg)
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
