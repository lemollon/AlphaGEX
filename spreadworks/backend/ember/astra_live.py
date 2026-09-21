"""ASTRA-3 live probation executor for Robinhood Agentic account 570892331.

The signal remains the deployed SpreadWorks ASTRA-3 paper ledger.  This local
process never computes or tunes a signal.  It mirrors a fresh paper OPEN into
an owned Robinhood SPY 0DTE call position, then mirrors the paper close.  Real broker
fills, not order acceptance, control ownership and live P&L.

Safety boundaries:
* exact account 570892331, exact paper-selected SPY call, quantity <= config cap
* current realized sleeve equity drives the frozen 25% debit budget
* one open position and one new trade per CT day
* trades 1-20 are one contract; passing the frozen live gate unlocks at most two
* promoted size falls back to one at an 8% realized-equity drawdown
* sell exactly this bot's confirmed own_qty, never the broker's total quantity
* broker state is authoritative for every unresolved order id
* any ownership/reconciliation mismatch latches the local kill switch
* forward-gate bypass is explicit and does not modify the paper gate

The Robinhood MCP is reached through a restricted headless Claude process.  The
model is only a typed broker-API adapter: Python selects the account, contract,
quantity, price ceiling, idempotency key, and state transition.  Each mutation
gets a separate read-only probe and a tightly scoped order call.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time as time_mod
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


CT = ZoneInfo("America/Chicago")
HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("ASTRA_LIVE_DATA_DIR", str(HERE / "astra"))).expanduser().resolve()
ENV_PATH = Path(os.getenv("ASTRA_LIVE_ENV_PATH", str(DATA_DIR / ".env"))).expanduser().resolve()
STATE_PATH = DATA_DIR / "state.json"
LOG_PATH = DATA_DIR / "astra-live.log"
INTENTS_PATH = DATA_DIR / "intents.log"
LOCK_PATH = DATA_DIR / "astra-live.lock"
NOTIFY_JSON = Path(r"C:\Users\lemol\dev\squeeze\research\notify.json")

ACCOUNT = "570892331"
TICKER = "SPY"
ROUND_TRIP_FEE = Decimal("0.70")
DD_THROTTLE_FRACTION = Decimal("0.08")
POST_PROMOTION_DD_FRACTION = Decimal("0.16")
MCP_CONFIG = json.dumps({
    "mcpServers": {
        "robinhood-trading": {
            "type": "http",
            "url": "https://agent.robinhood.com/mcp/trading",
        }
    }
}, separators=(",", ":"))

READ_PROBE_TOOLS = (
    "mcp__robinhood-trading__get_accounts",
    "mcp__robinhood-trading__get_portfolio",
    "mcp__robinhood-trading__get_option_instruments",
    "mcp__robinhood-trading__get_option_quotes",
    "mcp__robinhood-trading__get_option_positions",
    "mcp__robinhood-trading__get_option_orders",
)
ORDER_READ_TOOLS = (
    "mcp__robinhood-trading__get_option_orders",
    "mcp__robinhood-trading__get_option_positions",
)

BROKER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "action": {"type": "string"},
        "message": {"type": "string"},
        "account_ok": {"type": "boolean"},
        "buying_power": {"type": ["number", "null"]},
        "option_id": {"type": ["string", "null"]},
        "symbol": {"type": ["string", "null"]},
        "bid": {"type": ["number", "null"]},
        "ask": {"type": ["number", "null"]},
        "bid_size": {"type": ["number", "null"]},
        "ask_size": {"type": ["number", "null"]},
        "quote_updated_at": {"type": ["string", "null"]},
        "position_quantity": {"type": ["number", "null"]},
        "matching_open_order": {"type": "boolean"},
        "order_id": {"type": ["string", "null"]},
        "order_state": {"type": ["string", "null"]},
        "cumulative_quantity": {"type": ["number", "null"]},
        "average_price": {"type": ["number", "null"]},
        "placed": {"type": "boolean"},
        "cancelled": {"type": "boolean"},
        "hard_blocker": {"type": ["string", "null"]},
        "error": {"type": ["string", "null"]},
    },
    "required": [
        "ok", "action", "message", "account_ok", "buying_power",
        "option_id", "symbol", "bid", "ask", "bid_size", "ask_size",
        "quote_updated_at", "position_quantity", "matching_open_order",
        "order_id", "order_state", "cumulative_quantity", "average_price",
        "placed", "cancelled", "hard_blocker", "error",
    ],
    "additionalProperties": False,
}

TERMINAL_UNFILLED = {
    "cancelled", "canceled", "rejected", "failed", "voided", "expired",
}


class LockBusy(RuntimeError):
    pass
PENDING_STATES = {
    "queued", "confirmed", "pending", "unconfirmed", "partially_filled",
}


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_env(path: Path = ENV_PATH) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in os.environ.items():
        if key.startswith("ASTRA_LIVE_"):
            out[key] = value
    return out


def _clock(raw: str) -> time:
    return time.fromisoformat(raw)


@dataclass(frozen=True)
class Config:
    armed: bool
    dry_run: bool
    forward_gate_override: bool
    starting_equity: Decimal
    bp_pct: Decimal
    max_contracts: int
    cash_reserve: Decimal
    max_drawdown: Decimal
    daily_loss: Decimal
    max_live_trades: int
    max_trades_per_day: int
    max_adverse_slippage: Decimal
    max_spread_pct: Decimal
    max_quote_age_seconds: int
    max_signal_age_seconds: int
    entry_start_ct: time
    entry_cutoff_ct: time
    hard_exit_ct: time
    exit_depth_wait_minutes: int
    api_base: str
    claude_model: str
    claude_bin: str

    @classmethod
    def load(cls) -> "Config":
        e = _load_env()
        return cls(
            armed=_parse_bool(e.get("ASTRA_LIVE_ARMED")),
            dry_run=_parse_bool(e.get("ASTRA_LIVE_DRY_RUN"), True),
            forward_gate_override=_parse_bool(
                e.get("ASTRA_LIVE_FORWARD_GATE_OVERRIDE")),
            starting_equity=Decimal(e.get("ASTRA_LIVE_STARTING_EQUITY", "500")),
            bp_pct=Decimal(e.get("ASTRA_LIVE_BP_PCT", "0.25")),
            max_contracts=int(e.get("ASTRA_LIVE_MAX_CONTRACTS", "1")),
            cash_reserve=Decimal(e.get("ASTRA_LIVE_CASH_RESERVE", "20")),
            max_drawdown=Decimal(e.get("ASTRA_LIVE_MAX_DRAWDOWN", "80")),
            daily_loss=Decimal(e.get("ASTRA_LIVE_DAILY_LOSS", "80")),
            max_live_trades=int(e.get("ASTRA_LIVE_MAX_LIVE_TRADES", "20")),
            max_trades_per_day=int(
                e.get("ASTRA_LIVE_MAX_TRADES_PER_DAY", "1")),
            max_adverse_slippage=Decimal(
                e.get("ASTRA_LIVE_MAX_ADVERSE_SLIPPAGE", "0.01")),
            max_spread_pct=Decimal(e.get("ASTRA_LIVE_MAX_SPREAD_PCT", "0.15")),
            max_quote_age_seconds=int(
                e.get("ASTRA_LIVE_MAX_QUOTE_AGE_SECONDS", "90")),
            max_signal_age_seconds=int(
                e.get("ASTRA_LIVE_MAX_SIGNAL_AGE_SECONDS", "120")),
            entry_start_ct=_clock(e.get("ASTRA_LIVE_ENTRY_START_CT", "08:31")),
            entry_cutoff_ct=_clock(e.get("ASTRA_LIVE_ENTRY_CUTOFF_CT", "13:55")),
            hard_exit_ct=_clock(e.get("ASTRA_LIVE_HARD_EXIT_CT", "14:25")),
            exit_depth_wait_minutes=int(
                e.get("ASTRA_LIVE_EXIT_DEPTH_WAIT_MINUTES", "5")),
            api_base=e.get(
                "ASTRA_LIVE_API_BASE",
                "https://spreadworks-backend.onrender.com/api/spreadworks/bots/astra3",
            ).rstrip("/"),
            claude_model=e.get("ASTRA_LIVE_CLAUDE_MODEL", "haiku"),
            claude_bin=e.get(
                "ASTRA_LIVE_CLAUDE_BIN",
                str(HERE.parents[1] / "frontend" / "node_modules" / ".bin" / "claude"),
            ),
        )

    def validate(self) -> None:
        if self.starting_equity != Decimal("500"):
            raise ValueError("probation starting equity must remain exactly $500")
        if self.bp_pct != Decimal("0.25"):
            raise ValueError("frozen ASTRA-3 bp_pct must remain exactly 0.25")
        if self.max_contracts not in {1, 2}:
            raise ValueError("validated live quantity cap must be one or two")
        if self.max_trades_per_day != 1:
            raise ValueError("live probation is hard-capped at one new trade per day")
        if self.max_live_trades != 20:
            raise ValueError("live promotion gate must remain exactly 20 trades")
        if self.max_drawdown <= 0 or self.daily_loss <= 0:
            raise ValueError("loss limits must be positive dollar magnitudes")
        if self.entry_cutoff_ct >= self.hard_exit_ct:
            raise ValueError("entry cutoff must precede the 14:25 CT hard exit")


def _default_state(cfg: Config) -> dict[str, Any]:
    start = float(cfg.starting_equity)
    return {
        "version": 1,
        "account": ACCOUNT,
        "sleeve": {
            "starting_equity": start,
            "realized_pnl": 0.0,
            "equity": start,
            "high_water": start,
            "max_drawdown": 0.0,
            "completed_trades": 0,
            "promotion_state": "PROBATION",
            "promoted_at_ct": None,
            "daily_realized": {},
        },
        "processed_paper_positions": [],
        "active": None,
        "kill_latched": False,
        "kill_reason": None,
        "last_tick": None,
        "last_message": None,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _load_state(cfg: Config) -> dict[str, Any]:
    if not STATE_PATH.exists():
        state = _default_state(cfg)
        _atomic_json(STATE_PATH, state)
        return state
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"state unreadable: {exc}") from exc
    if state.get("version") != 1 or state.get("account") != ACCOUNT:
        raise RuntimeError("state version/account mismatch")
    sleeve = state.get("sleeve")
    if not isinstance(sleeve, dict):
        raise RuntimeError("state sleeve missing")
    sleeve.setdefault("promotion_state", "PROBATION")
    sleeve.setdefault("promoted_at_ct", None)
    return state


def _save_state(state: dict[str, Any], now: datetime, message: str) -> None:
    state["last_tick"] = now.isoformat(timespec="seconds")
    state["last_message"] = message
    _atomic_json(STATE_PATH, state)


def _append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line.rstrip() + "\n")


def _log(now: datetime, mode: str, message: str) -> str:
    line = f"{now.isoformat(timespec='seconds')} CT | {mode} | {message}"
    _append(LOG_PATH, line)
    print(line)
    upper = line.upper()
    bad_markers = ("MISMATCH", "KILLED", "| ERROR |")
    warning_markers = (
        "| ENTRY | NO-OP", "ENTRY CANCELLED UNFILLED",
        "ENTRY TERMINAL UNFILLED",
    )
    trade_markers = (
        " FILLED ", "BUY SUBMITTED", "SELL SUBMITTED", "PARTIAL FINAL",
    )
    if any(marker in upper for marker in (
            *bad_markers, *warning_markers, *trade_markers)):
        tone = (
            "bad" if any(marker in upper for marker in bad_markers)
            else "warn" if any(marker in upper for marker in warning_markers)
            else "trade"
        )
        _notify(tone, line)
    return line


def _notify(tone: str, headline: str) -> None:
    """Best-effort Discord/ntfy alert using the existing local notify config."""
    try:
        data = json.loads(NOTIFY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return
    webhook = str(data.get("discord_webhook") or "")
    topic = str(data.get("ntfy_topic") or "")
    emoji = {"bad": "⚠️", "warn": "🟨"}.get(tone, "📗")
    if webhook:
        payload = json.dumps({
            "username": "ASTRA-3 Bot",
            "content": f"{emoji} **ASTRA-3 live** — {headline}"[:1900],
        })
        try:
            subprocess.run(
                ["curl", "-s", "-o", os.devnull, "-m", "20",
                 "-H", "Content-Type: application/json", "-d", payload, webhook],
                timeout=30, check=False,
            )
        except Exception:
            pass
    if topic:
        try:
            subprocess.run(
                ["curl", "-s", "-o", os.devnull, "-m", "20",
                 "-H", "Title: ASTRA-3 live",
                 "-H", "Priority: high" if tone == "bad" else "Priority: default",
                 "-d", headline[:3000], f"https://ntfy.sh/{topic}"],
                timeout=30, check=False,
            )
        except Exception:
            pass


@contextmanager
def _single_instance():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise LockBusy("another ASTRA live tick is already running") from exc
        yield
    finally:
        if os.name == "nt":
            try:
                handle.seek(0)
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        handle.close()


def _api_get(cfg: Config, endpoint: str) -> dict[str, Any]:
    request = urllib.request.Request(
        cfg.api_base + endpoint,
        headers={"Accept": "application/json", "User-Agent": "astra-live/1"},
        method="GET",
    )
    last: Exception | None = None
    # 4 tries, 2/4/8s backoff (~14s total) — covers a Render deploy's brief
    # container-swap 502 gap without holding the 1-minute tick hostage. A
    # kill on an active position still fires if the outage genuinely
    # outlasts this window.
    backoffs = (2, 4, 8)
    for attempt in range(len(backoffs) + 1):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                body = json.loads(response.read().decode("utf-8"))
                if not isinstance(body, dict):
                    raise RuntimeError("API response is not an object")
                return body
        except (urllib.error.URLError, TimeoutError, OSError,
                json.JSONDecodeError, RuntimeError) as exc:
            last = exc
            if attempt < len(backoffs):
                time_mod.sleep(backoffs[attempt])
    raise RuntimeError(f"SpreadWorks {endpoint} unavailable: {last}")


def _as_decimal(value: Any, field: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} missing")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} invalid") from exc
    if not number.is_finite():
        raise ValueError(f"{field} invalid")
    return number


def _parse_timestamp(value: str | None, *, naive_utc: bool = True) -> datetime:
    if not value:
        raise ValueError("timestamp missing")
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc if naive_utc else CT)
    return parsed.astimezone(CT)


def _floor_cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _sleeve_equity(state: dict[str, Any]) -> Decimal:
    return _as_decimal(state["sleeve"]["equity"], "sleeve equity")


def _promotion_passes(cfg: Config, state: dict[str, Any]) -> bool:
    sleeve = state["sleeve"]
    return bool(
        int(sleeve["completed_trades"]) >= cfg.max_live_trades
        and _as_decimal(sleeve["realized_pnl"], "realized pnl") > 0
        and _as_decimal(sleeve["max_drawdown"], "max drawdown")
        >= -cfg.max_drawdown
    )


def _is_promoted(cfg: Config, state: dict[str, Any]) -> bool:
    return state["sleeve"].get("promotion_state") == "PROMOTED"


def _sizing_snapshot(cfg: Config, state: dict[str, Any]) -> dict[str, Any]:
    sleeve = state["sleeve"]
    equity = _sleeve_equity(state)
    high = _as_decimal(sleeve["high_water"], "high water")
    drawdown_pct = Decimal("0") if high <= 0 else (equity - high) / high
    promoted = _is_promoted(cfg, state)
    target = 1
    throttled = False
    if promoted:
        equity_units = max(1, int(equity // cfg.starting_equity))
        target = min(cfg.max_contracts, equity_units)
        if drawdown_pct <= -DD_THROTTLE_FRACTION and target > 1:
            target = 1
            throttled = True
    return {
        "promoted": promoted,
        "promotion_state": sleeve.get("promotion_state", "PROBATION"),
        "target_contracts": target,
        "drawdown_pct": drawdown_pct,
        "throttled": throttled,
    }


def _current_drawdown_limit(cfg: Config, state: dict[str, Any]) -> Decimal:
    if not _is_promoted(cfg, state):
        return cfg.max_drawdown
    high = _as_decimal(state["sleeve"]["high_water"], "high water")
    return (high * POST_PROMOTION_DD_FRACTION).quantize(Decimal("0.01"))


def _max_entry_ask(cfg: Config, state: dict[str, Any]) -> Decimal:
    budget = _sleeve_equity(state) * cfg.bp_pct
    if budget <= ROUND_TRIP_FEE:
        return Decimal("0")
    return _floor_cents((budget - ROUND_TRIP_FEE) / Decimal("100"))


def _paper_signal(position: dict[str, Any], now: datetime,
                  cfg: Config) -> dict[str, Any]:
    if position.get("ticker") != TICKER:
        raise ValueError("paper ticker is not SPY")
    if position.get("strategy") not in {"updraft", "backdraft"}:
        raise ValueError("paper strategy is not UPDRAFT/BACKDRAFT")
    if str(position.get("status", "OPEN")).upper() != "OPEN":
        raise ValueError("paper position is not OPEN")
    if int(position.get("contracts") or 0) < 1:
        raise ValueError("paper contracts below one")
    legs = position.get("legs")
    if not isinstance(legs, list) or len(legs) != 1:
        raise ValueError("paper position must have exactly one leg")
    leg = legs[0]
    if (leg.get("type") != "call" or leg.get("side") != "long"
            or leg.get("action") != "buy"):
        raise ValueError("paper leg is not a long call")
    expiry = str(leg.get("expiration") or "")
    if expiry != now.date().isoformat():
        raise ValueError("paper contract is not today's 0DTE")
    strike = _as_decimal(leg.get("strike"), "paper strike")
    ask = _as_decimal(leg.get("entry_price"), "paper entry ask")
    touch = int(leg.get("entry_touch_size") or 0)
    if strike <= 0 or ask <= 0 or touch < 1:
        raise ValueError("paper strike/ask/depth invalid")
    entry_time = _parse_timestamp(str(position.get("entry_time") or ""))
    age = (now - entry_time).total_seconds()
    if age < -30 or age > cfg.max_signal_age_seconds:
        raise ValueError(f"paper signal stale age={age:.0f}s")
    return {
        "paper_position_id": str(position["position_id"]),
        "strategy": str(position["strategy"]),
        "expiry": expiry,
        "strike": float(strike),
        "paper_entry_ask": float(ask),
        "paper_entry_touch_size": touch,
        "paper_entry_time_ct": entry_time.isoformat(timespec="seconds"),
    }


def _broker_call(cfg: Config, prompt: str, tools: tuple[str, ...],
                 *, timeout: int = 180) -> dict[str, Any]:
    from .xsp_flow_live import read_secret_environment

    command = [
        cfg.claude_bin, "-p", prompt,
        "--model", cfg.claude_model,
        "--restricted",
        "--strict-mcp-config",
        "--mcp-config", MCP_CONFIG,
        "--setting-sources", "user",
        "--disable-slash-commands",
        "--output-format", "json",
        "--json-schema", json.dumps(BROKER_SCHEMA, separators=(",", ":")),
        "--permission-mode", "dontAsk",
        "--allowedTools", *tools,
    ]
    try:
        result = subprocess.run(
            command, cwd=str(DATA_DIR), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            env=read_secret_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("broker adapter timed out") from exc
    if result.returncode != 0:
        tail = (result.stdout + "\n" + result.stderr)[-1200:].replace("\n", " ")
        raise RuntimeError(f"broker adapter exit={result.returncode}: {tail}")
    try:
        outer = json.loads(result.stdout)
        payload = outer.get("structured_output")
        if not isinstance(payload, dict):
            payload = json.loads(outer["result"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("broker adapter returned invalid structured output") from exc
    missing = set(BROKER_SCHEMA["required"]) - set(payload)
    if missing:
        raise RuntimeError(f"broker adapter omitted fields: {sorted(missing)}")
    return payload


def _base_prompt(action: str, now: datetime) -> str:
    return (
        "You are a deterministic Robinhood broker API adapter. This is real money. "
        "Do not infer a trade, alter a parameter, call any unlisted tool, or touch any "
        "account other than 570892331. Use the allowed tools exactly as instructed. "
        "Order acceptance is not a fill: report cumulative_quantity and average_price "
        "only from the broker order record. Never treat total broker inventory as bot "
        "ownership. Return only the required structured object. "
        f"ACTION={action}. NOW_CT={now.isoformat(timespec='seconds')}. "
    )


def _entry_probe(cfg: Config, signal: dict[str, Any], now: datetime) -> dict[str, Any]:
    prompt = _base_prompt("ENTRY_PROBE_READ_ONLY", now) + (
        "Do not review, place, or cancel an order. Call get_accounts and verify exact "
        "account 570892331 is active, agentic-accessible, limited_margin, option_level_3. "
        "Call get_portfolio for buying_power.buying_power. Resolve exactly one active, "
        "tradable SPY equity call with expiration " + signal["expiry"] + " and strike "
        + str(signal["strike"]) + ". Do not pass a tradability filter; inspect the returned "
        "instrument. Get its option quote. Paginate nonzero option positions and recent/open "
        "option orders. position_quantity is the total live quantity for this exact option_id, "
        "or 0. matching_open_order is true for any nonterminal order on this exact option_id. "
        "Return bid/ask, bid_size/ask_size, quote updated_at, symbol and option_id exactly. "
        "Set ok=false on missing fields, duplicates, stale/untradable contract, or mismatch."
    )
    return _broker_call(cfg, prompt, READ_PROBE_TOOLS)


def _place_order(cfg: Config, *, now: datetime, action: str, option_id: str,
                 side: str, effect: str, order_type: str, quantity: int,
                 ref_id: str, price: Decimal | None) -> dict[str, Any]:
    if action not in {"PLACE_ENTRY", "PLACE_EXIT"}:
        raise ValueError("invalid placement action")
    price_text = "no price" if price is None else f"price {price:.2f}"
    ownership_check = (
        "Immediately before review, call get_option_positions and get_option_orders. "
        "Refuse the BUY if this exact option_id has any nonzero position or any "
        "nonterminal order. "
        if side == "buy" else
        f"Immediately before review, call get_option_positions and get_option_orders. "
        f"Refuse the SELL unless this exact option_id has broker quantity at least "
        f"{quantity}, and refuse it if another nonterminal SELL-to-close already exists. "
    )
    prompt = _base_prompt(action, now) + ownership_check + (
        f"The deterministic controller authorizes exactly ONE SPY option order: account "
        f"570892331, underlying_type equity, chain_symbol SPY, option_id {option_id}, "
        f"one leg side {side}, position_effect {effect}, quantity {quantity}, type "
        f"{order_type}, {price_text}, time_in_force gfd, market_hours regular_hours, "
        f"ref_id {ref_id}. First call review_option_order with exactly those parameters. "
        "If review returns any hard blocker or the returned ticket differs, do not place. "
        "Otherwise call place_option_order once with the exact same parameters and ref_id. "
        "Then call get_option_orders for the returned order_id (or ref_id if response is "
        "ambiguous) and report broker state, cumulative_quantity, and average_price. "
        "Do not retry and do not place any other order."
    )
    tools = (
        "mcp__robinhood-trading__get_option_positions",
        "mcp__robinhood-trading__get_option_orders",
        "mcp__robinhood-trading__review_option_order",
        "mcp__robinhood-trading__place_option_order",
    )
    return _broker_call(cfg, prompt, tools)


def _order_reconcile(cfg: Config, active: dict[str, Any], now: datetime,
                     which: str) -> dict[str, Any]:
    order = active[which]
    order_id = order.get("order_id")
    locator = (f"exact order_id {order_id}" if order_id
               else f"exact ref_id {order['ref_id']} in the recent order list")
    prompt = _base_prompt(f"RECONCILE_{which.upper()}_READ_ONLY", now) + (
        f"Do not review, place, or cancel. Call get_option_orders for account 570892331 "
        f"and locate {locator}; the ref_id is {order['ref_id']}. Also call "
        f"get_option_positions for exact option_id "
        f"{active['entry']['option_id']}. Report order state, cumulative_quantity, "
        "average_price, and exact position_quantity. No order action is authorized."
    )
    return _broker_call(cfg, prompt, ORDER_READ_TOOLS)


def _cancel_order(cfg: Config, active: dict[str, Any], now: datetime,
                  which: str) -> dict[str, Any]:
    order = active[which]
    expected_qty = int(order.get("requested_qty") or 0)
    if expected_qty < 1:
        raise RuntimeError(f"{which} order missing requested quantity")
    prompt = _base_prompt(f"CANCEL_{which.upper()}", now) + (
        f"For account 570892331, first call get_option_orders for exact order_id "
        f"{order['order_id']}. If cumulative_quantity is already {expected_qty} or state "
        f"is filled, do not cancel. If nonterminal and cumulative_quantity is below "
        f"{expected_qty}, call "
        f"cancel_option_order exactly once for order_id {order['order_id']}, then call "
        f"get_option_orders again and call get_option_positions for exact option_id "
        f"{active['entry']['option_id']}. Report the authoritative final/current order "
        "state and exact remaining broker position_quantity. "
        "Do not place or review any order."
    )
    tools = (
        "mcp__robinhood-trading__get_option_orders",
        "mcp__robinhood-trading__get_option_positions",
        "mcp__robinhood-trading__cancel_option_order",
    )
    return _broker_call(cfg, prompt, tools)


def _exit_probe(cfg: Config, active: dict[str, Any], now: datetime) -> dict[str, Any]:
    prompt = _base_prompt("EXIT_PROBE_READ_ONLY", now) + (
        f"Do not review, place, or cancel. For account 570892331 and exact option_id "
        f"{active['entry']['option_id']}, call get_option_positions, get_option_quotes, "
        "and recent/open get_option_orders. position_quantity must be the broker's exact "
        "quantity for this option_id, or 0. matching_open_order is true only for a "
        "nonterminal SELL-to-close on this option_id. Return bid, ask, bid_size, ask_size "
        "and quote updated_at. No other contract is relevant."
    )
    tools = (
        "mcp__robinhood-trading__get_option_positions",
        "mcp__robinhood-trading__get_option_quotes",
        "mcp__robinhood-trading__get_option_orders",
    )
    return _broker_call(cfg, prompt, tools)


def _kill(state: dict[str, Any], reason: str) -> None:
    state["kill_latched"] = True
    state["kill_reason"] = reason


def _record_processed(state: dict[str, Any], paper_id: str) -> None:
    values = state.setdefault("processed_paper_positions", [])
    if paper_id not in values:
        values.append(paper_id)
    if len(values) > 200:
        del values[:-200]


def _entry_guards(cfg: Config, state: dict[str, Any], signal: dict[str, Any],
                  probe: dict[str, Any], now: datetime) -> tuple[bool, str, Decimal | None, int]:
    if not probe["ok"] or not probe["account_ok"]:
        return False, f"broker probe failed: {probe['error'] or probe['message']}", None, 0
    if probe["matching_open_order"]:
        return False, "matching option order already open", None, 0
    position_qty = _as_decimal(probe["position_quantity"] or 0, "position quantity")
    if position_qty != 0:
        return False, f"matching broker position already exists qty={position_qty}", None, 0
    bid = _as_decimal(probe["bid"], "bid")
    ask = _as_decimal(probe["ask"], "ask")
    ask_size = _as_decimal(probe["ask_size"], "ask_size")
    bp = _as_decimal(probe["buying_power"], "buying power")
    if bid <= 0 or ask <= 0 or ask < bid:
        return False, f"invalid market bid={bid} ask={ask}", None, 0
    if ask_size < 1:
        return False, f"insufficient displayed ask size={ask_size}", None, 0
    mid = (bid + ask) / Decimal("2")
    spread_pct = (ask - bid) / mid if mid > 0 else Decimal("999")
    if spread_pct > cfg.max_spread_pct:
        return False, f"wide market spread_pct={spread_pct:.4f}", None, 0
    quote_time = _parse_timestamp(probe["quote_updated_at"], naive_utc=False)
    quote_age = (now - quote_time).total_seconds()
    if quote_age < -30 or quote_age > cfg.max_quote_age_seconds:
        return False, f"stale quote age={quote_age:.0f}s", None, 0
    paper_ask = _as_decimal(signal["paper_entry_ask"], "paper ask")
    slippage_cap = _floor_cents(paper_ask + cfg.max_adverse_slippage)
    if ask > slippage_cap:
        return False, (
            f"debit over slippage cap ask={ask:.2f} "
            f"paper_slippage_cap={slippage_cap:.2f}"), None, 0
    sizing = _sizing_snapshot(cfg, state)
    target = int(sizing["target_contracts"])
    per_contract = ask * Decimal("100") + ROUND_TRIP_FEE
    sleeve_budget = _sleeve_equity(state) * cfg.bp_pct
    sleeve_capacity = int((sleeve_budget / per_contract).to_integral_value(
        rounding=ROUND_DOWN))
    depth_capacity = int(ask_size.to_integral_value(rounding=ROUND_DOWN))
    broker_budget = max(Decimal("0"), bp - cfg.cash_reserve)
    broker_capacity = int((broker_budget / per_contract).to_integral_value(
        rounding=ROUND_DOWN))
    quantity = min(target, sleeve_capacity, depth_capacity, broker_capacity)
    if quantity < 1:
        return False, (
            f"no executable quantity target={target} sleeve_capacity={sleeve_capacity} "
            f"depth_capacity={depth_capacity} broker_capacity={broker_capacity} "
            f"ask={ask:.2f} bp={bp:.2f}"), None, 0
    required = per_contract * quantity + cfg.cash_reserve
    if bp < required:
        return False, f"insufficient BP need={required:.2f} bp={bp:.2f}", None, 0
    if not probe["option_id"]:
        return False, "broker option_id missing", None, 0
    return True, (
        f"entry guards pass qty={quantity} target={target} ask={ask:.2f} "
        f"slippage_cap={slippage_cap:.2f} bp={bp:.2f} ask_size={ask_size} "
        f"promoted={int(sizing['promoted'])} throttled={int(sizing['throttled'])}"), ask, quantity


def _start_entry(cfg: Config, state: dict[str, Any], signal: dict[str, Any],
                 now: datetime) -> str:
    probe = _entry_probe(cfg, signal, now)
    try:
        passed, reason, price, quantity = _entry_guards(cfg, state, signal, probe, now)
    except (ValueError, TypeError) as exc:
        passed, reason, price, quantity = False, f"broker probe invalid: {exc}", None, 0
    paper_id = signal["paper_position_id"]
    if not passed:
        _record_processed(state, paper_id)
        return _log(now, "ENTRY", f"NO-OP {reason}; paper_id={paper_id}")
    assert price is not None
    assert 1 <= quantity <= cfg.max_contracts
    ref_id = str(uuid.uuid4())
    active = {
        "paper_position_id": paper_id,
        "signal": signal,
        "status": "entry_authorized",
        "detected_at_ct": now.isoformat(timespec="seconds"),
        "entry": {
            "option_id": probe["option_id"],
            "symbol": probe["symbol"],
            "ref_id": ref_id,
            "limit": float(price),
            "requested_qty": quantity,
            "filled_qty": 0,
            "order_id": None,
            "state": "authorized",
            "placed_at_ct": None,
            "own_qty": 0,
            "fill_price": None,
        },
        "exit": None,
        "exit_fills": [],
        "exit_trigger": None,
    }
    state["active"] = active
    _save_state(state, now, "entry authorization persisted before broker mutation")
    intent = (
        f"{now.isoformat(timespec='seconds')} CT | INTENT BUY SPY "
        f"{signal['expiry']} {signal['strike']}C qty={quantity} px={price:.2f} "
        f"ref={ref_id} paper_id={paper_id}"
    )
    _append(INTENTS_PATH, intent)
    if cfg.dry_run or not cfg.armed:
        _record_processed(state, paper_id)
        state["active"] = None
        return _log(now, "ENTRY", f"DRY-RUN would BUY {quantity} @ {price:.2f}; {reason}")
    result = _place_order(
        cfg, now=now, action="PLACE_ENTRY", option_id=str(probe["option_id"]),
        side="buy", effect="open", order_type="limit", quantity=quantity,
        ref_id=ref_id, price=price,
    )
    active = state["active"]
    if not result["placed"] or not result["order_id"]:
        blocker = result["hard_blocker"]
        if blocker and not result["placed"]:
            _record_processed(state, paper_id)
            state["active"] = None
            return _log(now, "ENTRY", f"NO-OP broker review blocked: {blocker}")
        active["status"] = "entry_uncertain"
        active["entry"].update({
            "order_id": result.get("order_id"),
            "state": result.get("order_state") or "unknown",
            "placed_at_ct": now.isoformat(timespec="seconds"),
        })
        _kill(state, (
            f"entry placement ambiguous ref_id={ref_id}: "
            f"{result['error'] or result['message']}"))
        return _log(now, "ENTRY", "MISMATCH entry placement ambiguous; KILLED pending reconcile")
    active["status"] = "entry_pending"
    active["entry"].update({
        "order_id": result["order_id"],
        "state": result["order_state"],
        "placed_at_ct": now.isoformat(timespec="seconds"),
    })
    return _log(
        now, "ENTRY",
        f"BUY submitted qty={quantity} limit={price:.2f} order_id={result['order_id']} "
        f"state={result['order_state']}; acceptance is not a fill",
    )


def _fill_quantity(result: dict[str, Any]) -> int:
    try:
        quantity = Decimal(str(result.get("cumulative_quantity") or 0))
    except Exception as exc:
        raise ValueError("invalid cumulative fill quantity") from exc
    if quantity < 0 or quantity != quantity.to_integral_value():
        raise ValueError(f"non-whole cumulative fill quantity={quantity}")
    return int(quantity)


def _fill_confirmed(result: dict[str, Any], expected_qty: int) -> bool:
    try:
        return (
            _fill_quantity(result) == expected_qty
            and Decimal(str(result.get("average_price"))) > 0
        )
    except Exception:
        return False


def _partial_fill_confirmed(result: dict[str, Any], expected_qty: int) -> bool:
    try:
        quantity = _fill_quantity(result)
        return 0 < quantity < expected_qty and Decimal(
            str(result.get("average_price"))) > 0
    except Exception:
        return False


def _adopt_entry_fill(active: dict[str, Any], result: dict[str, Any],
                      now: datetime) -> int:
    entry = active["entry"]
    requested = int(entry["requested_qty"])
    quantity = _fill_quantity(result)
    fill = _as_decimal(result["average_price"], "entry average price")
    if not 1 <= quantity <= requested:
        raise ValueError(
            f"entry cumulative quantity {quantity} outside requested {requested}")
    entry.update({
        "state": "filled" if quantity == requested else "partial_final",
        "filled_qty": quantity,
        "own_qty": quantity,
        "fill_price": float(fill),
        "filled_at_ct": now.isoformat(timespec="seconds"),
    })
    active["status"] = "open"
    return quantity


def _reconcile_entry(cfg: Config, state: dict[str, Any], now: datetime) -> str:
    active = state["active"]
    result = _order_reconcile(cfg, active, now, "entry")
    entry = active["entry"]
    requested = int(entry["requested_qty"])
    if _fill_confirmed(result, requested):
        fill = _as_decimal(result["average_price"], "entry average price")
        quantity = _adopt_entry_fill(active, result, now)
        return _log(
            now, "FILLCHECK",
            f"ENTRY FILLED own_qty={quantity} avg={fill:.2f} order_id={entry['order_id']}",
        )
    state_name = str(result.get("order_state") or "unknown").lower()
    entry["state"] = state_name
    if state_name in TERMINAL_UNFILLED:
        if _partial_fill_confirmed(result, requested):
            fill = _as_decimal(result["average_price"], "entry average price")
            quantity = _adopt_entry_fill(active, result, now)
            return _log(
                now, "FILLCHECK",
                f"ENTRY PARTIAL FINAL own_qty={quantity}/{requested} avg={fill:.2f} "
                f"state={state_name} order_id={entry['order_id']}",
            )
        _record_processed(state, active["paper_position_id"])
        state["active"] = None
        return _log(now, "FILLCHECK", f"entry terminal unfilled state={state_name}")
    placed_at = _parse_timestamp(entry["placed_at_ct"], naive_utc=False)
    age = (now - placed_at).total_seconds()
    if age >= 120:
        cancel = _cancel_order(cfg, active, now, "entry")
        if _fill_confirmed(cancel, requested):
            fill = _as_decimal(cancel["average_price"], "entry average price")
            quantity = _adopt_entry_fill(active, cancel, now)
            return _log(now, "FILLCHECK", (
                f"ENTRY FILLED during cancel check own_qty={quantity} avg={fill:.2f}"))
        cancel_state = str(cancel.get("order_state") or "unknown").lower()
        if cancel_state in TERMINAL_UNFILLED:
            if _partial_fill_confirmed(cancel, requested):
                fill = _as_decimal(cancel["average_price"], "entry average price")
                quantity = _adopt_entry_fill(active, cancel, now)
                return _log(now, "FILLCHECK", (
                    f"ENTRY PARTIAL FINAL after cancel own_qty={quantity}/{requested} "
                    f"avg={fill:.2f}"))
            entry["state"] = cancel_state
            _record_processed(state, active["paper_position_id"])
            state["active"] = None
            return _log(now, "FILLCHECK", "entry cancelled unfilled; signal not chased")
        _kill(state, f"entry cancel unresolved order_id={entry['order_id']} state={cancel_state}")
        active["status"] = "entry_uncertain"
        return _log(now, "FILLCHECK", f"MISMATCH entry cancel unresolved state={cancel_state}; KILLED")
    cumulative = _fill_quantity(result)
    if cumulative > requested:
        _kill(state, f"entry overfill cumulative={cumulative} requested={requested}")
        active["status"] = "entry_uncertain"
        return _log(now, "FILLCHECK", "MISMATCH entry overfill; KILLED")
    return _log(
        now, "FILLCHECK",
        f"entry pending state={state_name} cumulative={cumulative}/{requested} age={age:.0f}s",
    )


def _paper_exit(cfg: Config, active: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    if now.time() >= cfg.hard_exit_ct:
        return {"reason": "HARD_EXIT_1425", "detected_at_ct": now.isoformat(timespec="seconds")}
    positions = _api_get(cfg, "/positions").get("positions")
    if not isinstance(positions, list):
        raise RuntimeError("SpreadWorks positions payload invalid")
    if any(str(p.get("position_id")) == active["paper_position_id"] for p in positions):
        detected = _parse_timestamp(active["detected_at_ct"], naive_utc=False)
        if now - detected >= timedelta(minutes=35):
            return {"reason": "LOCAL_35M_FAILSAFE", "detected_at_ct": now.isoformat(timespec="seconds")}
        return None
    trades = _api_get(cfg, "/trades?limit=20").get("trades")
    if isinstance(trades, list):
        for trade in trades:
            if str(trade.get("position_id")) == active["paper_position_id"]:
                return {
                    "reason": "PAPER_" + str(trade.get("close_reason") or "CLOSED"),
                    "paper_close_price": trade.get("close_price"),
                    "paper_close_time": str(trade.get("close_time") or ""),
                    "detected_at_ct": now.isoformat(timespec="seconds"),
                }
    return {"reason": "PAPER_POSITION_MISSING", "detected_at_ct": now.isoformat(timespec="seconds")}


def _begin_exit(cfg: Config, state: dict[str, Any], now: datetime) -> str:
    active = state["active"]
    trigger = active["exit_trigger"]
    probe = _exit_probe(cfg, active, now)
    if not probe["ok"] or not probe["account_ok"]:
        return _log(now, "EXIT", f"broker probe failed: {probe['error'] or probe['message']}")
    broker_qty = _as_decimal(probe["position_quantity"] or 0, "position quantity")
    own_qty = Decimal(str(active["entry"]["own_qty"]))
    if (own_qty < 1 or own_qty > cfg.max_contracts
            or own_qty != own_qty.to_integral_value()):
        _kill(state, f"invalid own_qty={own_qty}")
        return _log(now, "EXIT", f"MISMATCH invalid own_qty={own_qty}; KILLED")
    quantity = int(own_qty)
    if broker_qty < own_qty:
        _kill(state, f"broker quantity {broker_qty} below own_qty {own_qty}")
        return _log(now, "EXIT", f"MISMATCH broker_qty={broker_qty} own_qty={own_qty}; KILLED")
    if probe["matching_open_order"]:
        _kill(state, "unowned matching open exit order")
        return _log(now, "EXIT", "MISMATCH matching sell order already exists; KILLED")
    bid = _as_decimal(probe["bid"] or 0, "bid")
    bid_size = _as_decimal(probe["bid_size"] or 0, "bid_size")
    hard = now.time() >= cfg.hard_exit_ct
    if not hard and (bid <= 0 or bid_size < own_qty):
        latched_at = trigger.get("depth_latched_at_ct")
        if not latched_at:
            trigger["depth_latched_at_ct"] = now.isoformat(timespec="seconds")
            trigger["trigger_bid"] = float(max(bid, Decimal("0")))
            return _log(now, "EXIT", f"depth latch bid={bid} size={bid_size} wait<=5m")
        waited = (now - _parse_timestamp(latched_at, naive_utc=False)).total_seconds() / 60
        if waited < cfg.exit_depth_wait_minutes:
            return _log(now, "EXIT", f"depth latch waiting {waited:.1f}m bid={bid} size={bid_size}")
        hard = True
        trigger["reason"] += "_DEPTH_TIMEOUT"
    order_type = "market" if hard or bid <= 0 else "limit"
    price: Decimal | None = None
    if order_type == "limit":
        trigger_bid = _as_decimal(trigger.get("trigger_bid", bid), "trigger bid")
        price = _floor_cents(min(bid, trigger_bid))
        if price <= 0:
            order_type = "market"
            price = None
    ref_id = str(uuid.uuid4())
    exit_order = {
        "ref_id": ref_id, "order_id": None, "state": "authorized",
        "requested_qty": quantity,
        "type": order_type, "limit": float(price) if price is not None else None,
        "placed_at_ct": None, "fill_price": None,
    }
    active["exit"] = exit_order
    active["status"] = "exit_authorized"
    _save_state(state, now, "exit authorization persisted before broker mutation")
    px_text = "MKT" if price is None else f"{price:.2f}"
    _append(
        INTENTS_PATH,
        f"{now.isoformat(timespec='seconds')} CT | INTENT SELL SPY "
        f"{active['signal']['expiry']} {active['signal']['strike']}C qty={quantity} "
        f"px={px_text} ref={ref_id} reason={trigger['reason']}",
    )
    if cfg.dry_run or not cfg.armed:
        return _log(now, "EXIT", f"DRY-RUN would SELL own_qty={quantity} px={px_text}")
    result = _place_order(
        cfg, now=now, action="PLACE_EXIT",
        option_id=active["entry"]["option_id"], side="sell", effect="close",
        order_type=order_type, quantity=quantity, ref_id=ref_id, price=price,
    )
    if not result["placed"] or not result["order_id"]:
        blocker = result["hard_blocker"]
        if blocker and not result["placed"]:
            active["exit"] = None
            active["status"] = "open"
            return _log(now, "EXIT", f"broker review blocked exit: {blocker}; retry next tick")
        exit_order.update({
            "order_id": result.get("order_id"),
            "state": result.get("order_state") or "unknown",
            "placed_at_ct": now.isoformat(timespec="seconds"),
        })
        active["status"] = "exit_uncertain"
        _kill(state, (
            f"exit placement ambiguous ref_id={ref_id}: "
            f"{result['error'] or result['message']}"))
        return _log(now, "EXIT", "MISMATCH exit placement ambiguous; KILLED pending reconcile")
    exit_order.update({
        "order_id": result["order_id"], "state": result["order_state"],
        "placed_at_ct": now.isoformat(timespec="seconds"),
    })
    active["status"] = "exit_pending"
    return _log(
        now, "EXIT",
        f"SELL submitted own_qty={quantity} px={px_text} order_id={result['order_id']} "
        f"state={result['order_state']}; acceptance is not a fill",
    )


def _record_exit_fill(active: dict[str, Any], result: dict[str, Any],
                      now: datetime) -> tuple[int, int, Decimal, int]:
    exit_order = active["exit"]
    requested = int(exit_order["requested_qty"])
    quantity = _fill_quantity(result)
    fill = _as_decimal(result["average_price"], "exit average price")
    own_before = int(active["entry"]["own_qty"])
    if not 1 <= quantity <= requested or quantity > own_before:
        raise ValueError(
            f"exit cumulative quantity {quantity} invalid for "
            f"requested={requested} own_qty={own_before}")
    active.setdefault("exit_fills", []).append({
        "quantity": quantity,
        "average_price": float(fill),
        "order_id": exit_order.get("order_id"),
        "filled_at_ct": now.isoformat(timespec="seconds"),
    })
    remaining = own_before - quantity
    active["entry"]["own_qty"] = remaining
    exit_order.update({
        "state": "filled" if quantity == requested else "partial_final",
        "filled_qty": quantity,
        "fill_price": float(fill),
        "filled_at_ct": now.isoformat(timespec="seconds"),
    })
    fills = active["exit_fills"]
    total_qty = sum(int(row["quantity"]) for row in fills)
    total_value = sum(
        Decimal(str(row["average_price"])) * int(row["quantity"])
        for row in fills
    )
    aggregate = total_value / total_qty
    return remaining, total_qty, aggregate, quantity


def _complete_trade(cfg: Config, state: dict[str, Any], now: datetime,
                    exit_fill: Decimal, quantity: int) -> str:
    active = state["active"]
    entry_fill = _as_decimal(active["entry"]["fill_price"], "entry fill")
    filled_qty = int(active["entry"].get("filled_qty") or 0)
    if quantity != filled_qty or quantity < 1:
        _kill(state, f"closed quantity {quantity} != entry filled_qty {filled_qty}")
        return _log(now, "FILLCHECK", "MISMATCH closed quantity; KILLED")
    pnl = quantity * (
        (exit_fill - entry_fill) * Decimal("100") - ROUND_TRIP_FEE)
    pnl = pnl.quantize(Decimal("0.01"))
    sleeve = state["sleeve"]
    realized = _as_decimal(sleeve["realized_pnl"], "realized pnl") + pnl
    equity = cfg.starting_equity + realized
    high = max(_as_decimal(sleeve["high_water"], "high water"), equity)
    drawdown = equity - high
    max_dd = min(_as_decimal(sleeve["max_drawdown"], "max drawdown"), drawdown)
    today_key = now.date().isoformat()
    daily = sleeve.setdefault("daily_realized", {})
    today_pnl = _as_decimal(daily.get(today_key, 0), "daily pnl") + pnl
    daily[today_key] = float(today_pnl)
    sleeve.update({
        "realized_pnl": float(realized), "equity": float(equity),
        "high_water": float(high), "max_drawdown": float(max_dd),
        "completed_trades": int(sleeve["completed_trades"]) + 1,
    })
    completed = int(sleeve["completed_trades"])
    _record_processed(state, active["paper_position_id"])
    active["exit"]["fill_price"] = float(exit_fill)
    active["exit"]["state"] = "filled"
    active["exit"]["filled_at_ct"] = now.isoformat(timespec="seconds")
    summary = {
        "paper_position_id": active["paper_position_id"],
        "quantity": quantity,
        "entry_fill": float(entry_fill), "exit_fill": float(exit_fill),
        "pnl": float(pnl), "equity": float(equity),
        "closed_at_ct": now.isoformat(timespec="seconds"),
    }
    state.setdefault("history", []).append(summary)
    state["history"] = state["history"][-100:]
    state["active"] = None
    if completed == cfg.max_live_trades:
        if _promotion_passes(cfg, state):
            sleeve["promotion_state"] = "PROMOTED"
            sleeve["promoted_at_ct"] = now.isoformat(timespec="seconds")
        else:
            sleeve["promotion_state"] = "FAILED"
            _kill(state, (
                f"20-trade promotion failed pnl={realized:.2f} "
                f"max_dd={max_dd:.2f}"))
    elif completed > cfg.max_live_trades and not _is_promoted(cfg, state):
        _kill(state, "post-probation trade without valid promotion")

    if completed <= cfg.max_live_trades:
        drawdown_limit = cfg.max_drawdown
        daily_limit = cfg.daily_loss
    else:
        drawdown_limit = (high * POST_PROMOTION_DD_FRACTION).quantize(
            Decimal("0.01"))
        daily_limit = drawdown_limit
    if drawdown <= -drawdown_limit:
        _kill(state, (
            f"live sleeve drawdown {drawdown:.2f} <= -{drawdown_limit:.2f}"))
    if today_pnl <= -daily_limit:
        _kill(state, f"daily realized {today_pnl:.2f} <= -{daily_limit:.2f}")
    killed = f" KILLED: {state['kill_reason']}" if state["kill_latched"] else ""
    promotion = f" promotion={sleeve.get('promotion_state', 'PROBATION')}"
    return _log(
        now, "FILLCHECK",
        f"EXIT FILLED qty={quantity} avg={exit_fill:.2f} pnl={pnl:+.2f} "
        f"sleeve_equity={equity:.2f} max_dd={max_dd:.2f}{promotion}{killed}",
    )


def _reconcile_exit(cfg: Config, state: dict[str, Any], now: datetime) -> str:
    active = state["active"]
    result = _order_reconcile(cfg, active, now, "exit")
    exit_order = active["exit"]
    expected = int(exit_order["requested_qty"])
    if _fill_confirmed(result, expected):
        try:
            remaining, total_qty, aggregate, _ = _record_exit_fill(
                active, result, now)
        except ValueError as exc:
            _kill(state, str(exc))
            active["status"] = "exit_uncertain"
            return _log(now, "FILLCHECK", f"MISMATCH {exc}; KILLED")
        if remaining != 0:
            _kill(state, f"full exit order left own_qty={remaining}")
            active["status"] = "exit_uncertain"
            return _log(now, "FILLCHECK", "MISMATCH full exit left quantity; KILLED")
        return _complete_trade(cfg, state, now, aggregate, total_qty)
    state_name = str(result.get("order_state") or "unknown").lower()
    exit_order["state"] = state_name
    cumulative = _fill_quantity(result)
    if cumulative > expected:
        _kill(state, f"exit overfill cumulative={cumulative} requested={expected}")
        active["status"] = "exit_uncertain"
        return _log(now, "FILLCHECK", "MISMATCH exit overfill; KILLED")
    broker_qty = _as_decimal(result.get("position_quantity") or 0, "position quantity")
    if state_name in TERMINAL_UNFILLED:
        if _partial_fill_confirmed(result, expected):
            remaining_expected = int(active["entry"]["own_qty"]) - cumulative
            if broker_qty < Decimal(remaining_expected):
                _kill(state, (
                    f"terminal partial exit broker_qty={broker_qty} below "
                    f"remaining own_qty={remaining_expected}"))
                active["status"] = "exit_uncertain"
                return _log(
                    now, "FILLCHECK",
                    "MISMATCH partial exit remaining quantity; KILLED")
            try:
                remaining, _, _, filled = _record_exit_fill(active, result, now)
            except ValueError as exc:
                _kill(state, str(exc))
                active["status"] = "exit_uncertain"
                return _log(now, "FILLCHECK", f"MISMATCH {exc}; KILLED")
            active["exit"] = None
            active["status"] = "open"
            return _log(now, "FILLCHECK", (
                f"EXIT PARTIAL FINAL sold={filled}/{expected} own_qty={remaining}; "
                "retry remainder next tick"))
        active["exit"] = None
        active["status"] = "open"
        return _log(now, "FILLCHECK", f"exit terminal unfilled state={state_name}; retry")
    own_qty = int(active["entry"]["own_qty"])
    minimum_expected_broker_qty = max(0, own_qty - cumulative)
    if broker_qty < Decimal(minimum_expected_broker_qty):
        _kill(state, (
            f"exit ownership unresolved: broker_qty={broker_qty}, order={exit_order['order_id']} "
            f"state={state_name}, cumulative={cumulative}/{expected}"))
        active["status"] = "exit_uncertain"
        return _log(now, "FILLCHECK", "MISMATCH position gone without confirmed exit fill; KILLED")
    placed_at = _parse_timestamp(exit_order["placed_at_ct"], naive_utc=False)
    age = (now - placed_at).total_seconds()
    if age < 60:
        return _log(now, "FILLCHECK", (
            f"exit pending state={state_name} cumulative={cumulative}/{expected} "
            f"age={age:.0f}s"))
    cancel = _cancel_order(cfg, active, now, "exit")
    if _fill_confirmed(cancel, expected):
        try:
            remaining, total_qty, aggregate, _ = _record_exit_fill(
                active, cancel, now)
        except ValueError as exc:
            _kill(state, str(exc))
            active["status"] = "exit_uncertain"
            return _log(now, "FILLCHECK", f"MISMATCH {exc}; KILLED")
        if remaining != 0:
            _kill(state, f"full cancelled exit left own_qty={remaining}")
            active["status"] = "exit_uncertain"
            return _log(now, "FILLCHECK", "MISMATCH cancelled exit left quantity; KILLED")
        return _complete_trade(cfg, state, now, aggregate, total_qty)
    cancel_state = str(cancel.get("order_state") or "unknown").lower()
    if cancel_state in TERMINAL_UNFILLED:
        if _partial_fill_confirmed(cancel, expected):
            cancel_broker_qty = _as_decimal(
                cancel.get("position_quantity") or 0, "position quantity")
            cancel_cumulative = _fill_quantity(cancel)
            remaining_expected = int(active["entry"]["own_qty"]) - cancel_cumulative
            if cancel_broker_qty < Decimal(remaining_expected):
                _kill(state, (
                    f"cancelled partial exit broker_qty={cancel_broker_qty} below "
                    f"remaining own_qty={remaining_expected}"))
                active["status"] = "exit_uncertain"
                return _log(
                    now, "FILLCHECK",
                    "MISMATCH cancelled partial remaining quantity; KILLED")
            try:
                remaining, _, _, filled = _record_exit_fill(active, cancel, now)
            except ValueError as exc:
                _kill(state, str(exc))
                active["status"] = "exit_uncertain"
                return _log(now, "FILLCHECK", f"MISMATCH {exc}; KILLED")
            active["exit"] = None
            active["status"] = "open"
            return _log(now, "FILLCHECK", (
                f"EXIT PARTIAL FINAL after cancel sold={filled}/{expected} "
                f"own_qty={remaining}; retry remainder next tick"))
        exit_order["state"] = cancel_state
        active["exit"] = None
        active["status"] = "open"
        return _log(now, "FILLCHECK", "exit cancelled unfilled; will reprice next tick")
    _kill(state, f"exit cancel unresolved order_id={exit_order['order_id']} state={cancel_state}")
    active["status"] = "exit_uncertain"
    return _log(now, "FILLCHECK", f"MISMATCH exit cancel unresolved state={cancel_state}; KILLED")


def _entry_allowed(cfg: Config, state: dict[str, Any], now: datetime,
                   status: dict[str, Any]) -> tuple[bool, str]:
    if not cfg.armed or cfg.dry_run:
        return False, f"not live armed armed={int(cfg.armed)} dry_run={int(cfg.dry_run)}"
    if not cfg.forward_gate_override:
        return False, "forward gate override is not explicitly set"
    if state.get("kill_latched"):
        return False, f"kill latched: {state.get('kill_reason')}"
    if now.weekday() >= 5:
        return False, "weekend"
    if not (cfg.entry_start_ct <= now.time() <= cfg.entry_cutoff_ct):
        return False, "outside live entry window"
    if status.get("enabled") is not True:
        return False, "ASTRA-3 paper scanner disabled"
    gate = status.get("forward_gate") or {}
    if gate.get("paper_only") is not True or gate.get("live_money_authorized") is not False:
        return False, "unexpected paper gate contract"
    completed = int(state["sleeve"]["completed_trades"])
    if completed >= cfg.max_live_trades and not _is_promoted(cfg, state):
        return False, "20-trade live promotion gate not passed"
    today_key = now.date().isoformat()
    entered_today = sum(
        1 for row in state.get("history", [])
        if str(row.get("closed_at_ct", "")).startswith(today_key)
    )
    active = state.get("active")
    if active and str(active.get("detected_at_ct", "")).startswith(today_key):
        entered_today += 1
    if entered_today >= cfg.max_trades_per_day:
        return False, "one-new-trade daily probation cap reached"
    sizing = _sizing_snapshot(cfg, state)
    return True, (
        f"live guards pass promotion={sizing['promotion_state']} "
        f"target_qty={sizing['target_contracts']} throttled={int(sizing['throttled'])}")


def _tick(cfg: Config, now: datetime) -> int:
    cfg.validate()
    state = _load_state(cfg)
    active = state.get("active")
    if active:
        status = active.get("status")
        if status in {"entry_authorized", "entry_pending", "entry_uncertain"}:
            line = _reconcile_entry(cfg, state, now)
        elif status == "open":
            if not active.get("exit_trigger"):
                active["exit_trigger"] = _paper_exit(cfg, active, now)
            if active.get("exit_trigger"):
                line = _begin_exit(cfg, state, now)
            else:
                line = _log(
                    now, "HOLD",
                    f"paper position remains open; own_qty={active['entry']['own_qty']}")
        elif status in {"exit_authorized", "exit_pending", "exit_uncertain"}:
            line = _reconcile_exit(cfg, state, now)
        else:
            _kill(state, f"unknown active status {status}")
            line = _log(now, "SAFETY", f"MISMATCH unknown active status={status}; KILLED")
        _save_state(state, now, line)
        return 0 if not state.get("kill_latched") else 2

    status_api = _api_get(cfg, "/status")
    allowed, reason = _entry_allowed(cfg, state, now, status_api)
    if not allowed:
        line = _log(now, "IDLE", reason)
        _save_state(state, now, line)
        return 0
    positions = _api_get(cfg, "/positions").get("positions")
    if not isinstance(positions, list):
        raise RuntimeError("SpreadWorks positions payload invalid")
    unseen = [
        p for p in positions
        if str(p.get("position_id")) not in state.get("processed_paper_positions", [])
    ]
    if not unseen:
        line = _log(now, "IDLE", "armed; no fresh ASTRA-3 paper position")
        _save_state(state, now, line)
        return 0
    if len(unseen) != 1:
        _kill(state, f"expected one unseen paper position, found {len(unseen)}")
        line = _log(now, "SAFETY", f"MISMATCH {len(unseen)} unseen paper positions; KILLED")
        _save_state(state, now, line)
        return 2
    try:
        signal = _paper_signal(unseen[0], now, cfg)
    except (ValueError, TypeError, KeyError) as exc:
        paper_id = str(unseen[0].get("position_id") or "unknown")
        _record_processed(state, paper_id)
        line = _log(now, "ENTRY", f"NO-OP invalid paper signal: {exc}; paper_id={paper_id}")
        _save_state(state, now, line)
        return 1
    line = _start_entry(cfg, state, signal, now)
    _save_state(state, now, line)
    return 0


def _audit(cfg: Config, now: datetime) -> int:
    cfg.validate()
    state = _load_state(cfg)
    sizing = _sizing_snapshot(cfg, state)
    status = _api_get(cfg, "/status")
    positions = _api_get(cfg, "/positions")
    print(json.dumps({
        "environment": "PRODUCTION_LIVE" if cfg.armed and not cfg.dry_run else "SAFE_NO_ORDER",
        "account": ACCOUNT,
        "armed": cfg.armed,
        "dry_run": cfg.dry_run,
        "forward_gate_override": cfg.forward_gate_override,
        "maximum_contracts": cfg.max_contracts,
        "promotion_state": sizing["promotion_state"],
        "promotion_passed": sizing["promoted"],
        "target_contracts_now": sizing["target_contracts"],
        "drawdown_pct_now": float(sizing["drawdown_pct"]),
        "drawdown_throttled": sizing["throttled"],
        "current_drawdown_limit": float(_current_drawdown_limit(cfg, state)),
        "starting_sleeve_equity": float(cfg.starting_equity),
        "current_sleeve_equity": state["sleeve"]["equity"],
        "max_entry_ask_now": float(_max_entry_ask(cfg, state)),
        "cash_reserve": float(cfg.cash_reserve),
        "kill_latched": state["kill_latched"],
        "kill_reason": state["kill_reason"],
        "active": state["active"],
        "paper_status": status,
        "paper_positions": positions.get("positions"),
        "now_ct": now.isoformat(timespec="seconds"),
    }, indent=2, sort_keys=True))
    return 0


def _broker_audit(cfg: Config, now: datetime) -> int:
    prompt = _base_prompt("BROKER_AUDIT_READ_ONLY", now) + (
        "Do not review, place, or cancel. Call get_accounts and verify exact account "
        "570892331 is active, agentic-accessible, limited_margin and option_level_3. "
        "Call get_portfolio and return buying_power. Call get_option_positions and "
        "get_option_orders; position_quantity is the sum of nonzero SPY 0DTE option "
        "positions and matching_open_order is true if any nonterminal SPY option order "
        "exists. This is a connection and eligibility audit only."
    )
    tools = (
        "mcp__robinhood-trading__get_accounts",
        "mcp__robinhood-trading__get_portfolio",
        "mcp__robinhood-trading__get_option_positions",
        "mcp__robinhood-trading__get_option_orders",
    )
    print(json.dumps(_broker_call(cfg, prompt, tools), indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true",
                        help="read local config/state and live paper API; no broker call")
    parser.add_argument("--broker-audit", action="store_true",
                        help="read-only Robinhood connection/eligibility audit")
    parser.add_argument("--now", help="ISO timestamp for read-only audit only")
    args = parser.parse_args(argv)
    cfg = Config.load()
    now = (datetime.fromisoformat(args.now).astimezone(CT)
           if args.now else datetime.now(CT))
    if args.now and not args.audit:
        raise SystemExit("--now is permitted only with --audit")
    try:
        with _single_instance():
            if args.audit:
                return _audit(cfg, now)
            if args.broker_audit:
                return _broker_audit(cfg, now)
            return _tick(cfg, now)
    except LockBusy as exc:
        print(str(exc))
        return 0
    except (RuntimeError, ValueError) as exc:
        line = _log(now, "ERROR", str(exc))
        try:
            state = _load_state(cfg)
            if state.get("active"):
                _kill(state, f"runtime error with active position: {exc}")
            _save_state(state, now, line)
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
