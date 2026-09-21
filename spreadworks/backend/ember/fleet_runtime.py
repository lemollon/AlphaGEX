"""Durable Render scheduler for EMBER's non-XSP strategy fleet.

Every strategy keeps its original decision logic.  This layer supplies a
Render clock, persistent state hydration/mirroring, cross-process locking,
and a fail-closed live gate.  A migrated state snapshot is required before a
strategy may place orders; an empty first boot is never treated as proof that
the broker is flat.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import text as sa_text

from ..db import SessionLocal
from . import runtime as xsp_runtime
from .legacy import call_diag, divhike, night_shift, spike, tv_book


logger = logging.getLogger("spreadworks.ember.fleet")
CT = ZoneInfo("America/Chicago")


@dataclass(frozen=True)
class StrategySpec:
    name: str
    env_prefix: str
    state_path: Path
    log_path: Path
    default_state: dict[str, Any]
    runner: Callable[[datetime, Any, str | None], int]
    config_loader: Callable[[], Any]
    required_any: tuple[tuple[str, ...], ...] = ()
    aliases: tuple[str, ...] = ()

    @property
    def state_key(self) -> str:
        return f"ember.{self.name}.state"

    @property
    def status_key(self) -> str:
        return f"ember.{self.name}.status"

    @property
    def enabled_env(self) -> str:
        return f"EMBER_{self.env_prefix}_ENABLED"

    @property
    def live_env(self) -> str:
        return f"EMBER_{self.env_prefix}_LIVE"

    @property
    def seed_env(self) -> str:
        return f"EMBER_{self.env_prefix}_STATE_B64"

    @property
    def seed_key(self) -> str:
        return f"ember.{self.name}.seed_applied"


def _tick_runner(module: Any) -> Callable[[datetime, Any, str | None], int]:
    def run(now: datetime, cfg: Any, mode: str | None) -> int:
        return int(module.tick(
            now,
            cfg,
            forced_mode=mode,
            force_rerun=bool(mode == "RECONCILE" and cfg.dry_run),
        ))
    return run


def _spike_runner(now: datetime, cfg: Any, mode: str | None) -> int:
    if mode == "PREFLIGHT":
        return _broker_preflight("spike", spike.ACCOUNT, spike.HERE / "preflight.log")
    if mode == "MANAGE":
        return int(spike.run_manage(now, cfg))
    return int(spike.run_enter(now, cfg))


SPECS: dict[str, StrategySpec] = {
    "call_diag": StrategySpec(
        "call_diag", "CALLDIAG", call_diag.ORDER_STATE, call_diag.LOG_TXT,
        {"positions": [], "legs": {}}, _tick_runner(call_diag), call_diag.load_cfg,
    ),
    "night_shift": StrategySpec(
        "night_shift", "NIGHT", night_shift.ORDER_STATE, night_shift.LOG_TXT,
        {"position": None}, _tick_runner(night_shift), night_shift.load_cfg,
    ),
    "divhike": StrategySpec(
        "divhike", "DIVHIKE", divhike.ORDER_STATE, divhike.LOG_TXT,
        {"positions": {}}, _tick_runner(divhike), divhike.load_cfg,
        required_any=(("POLYGON_API_KEY",),),
    ),
    "tv_book": StrategySpec(
        "tv_book", "TVBOOK", tv_book.ORDER_STATE, tv_book.LOG_TXT,
        {"positions": [], "in_flight": {}}, _tick_runner(tv_book), tv_book.load_cfg,
        required_any=(("TV_API_KEY", "TRADING_VOLATILITY_API_KEY"), ("TRADIER_TOKEN",)),
        aliases=("rr", "bounce"),
    ),
    "spike": StrategySpec(
        "spike", "SPIKE", spike.STATE_FILE, spike.LOG_TXT,
        {"positions": [], "seen": {}, "shadow": [], "tape_prev": {}},
        _spike_runner, spike.load_cfg,
        required_any=(("POLYGON_API_KEY",), ("SPIKE_UNIVERSE",)),
    ),
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _acquire_lock(name: str) -> Any | None:
    if SessionLocal is None:
        raise xsp_runtime.EmberRuntimeError("DATABASE_URL is unavailable")
    db = SessionLocal()
    try:
        acquired = db.execute(
            sa_text("SELECT pg_try_advisory_lock(hashtext(:name))"),
            {"name": f"ember-fleet:{name}"},
        ).scalar_one()
        if not acquired:
            db.close()
            return None
        return db
    except Exception:
        db.close()
        raise


def _release_lock(db: Any, name: str) -> None:
    try:
        db.execute(
            sa_text("SELECT pg_advisory_unlock(hashtext(:name))"),
            {"name": f"ember-fleet:{name}"},
        )
    except Exception:  # noqa: BLE001
        logger.exception("[EMBER:%s] advisory unlock failed", name)
    finally:
        db.close()


def _decode_seed(value: str, spec: StrategySpec) -> dict[str, Any]:
    try:
        raw = base64.b64decode(value, validate=True)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise xsp_runtime.EmberRuntimeError(
            f"{spec.seed_env} is malformed"
        ) from exc
    if not isinstance(payload, dict):
        raise xsp_runtime.EmberRuntimeError(f"{spec.seed_env} must contain a JSON object")
    return payload


def _hydrate(spec: StrategySpec) -> str:
    disk_state: dict[str, Any] | None = None
    if spec.state_path.exists():
        try:
            loaded = json.loads(spec.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise xsp_runtime.EmberRuntimeError(
                f"{spec.name} disk state is malformed"
            ) from exc
        if not isinstance(loaded, dict):
            raise xsp_runtime.EmberRuntimeError(
                f"{spec.name} disk state must contain a JSON object"
            )
        disk_state = loaded

    raw = xsp_runtime._config_get(spec.state_key)
    database_state: dict[str, Any] | None = None
    if raw:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise xsp_runtime.EmberRuntimeError(
                f"{spec.name} database state is malformed"
            ) from exc
        if not isinstance(loaded, dict):
            raise xsp_runtime.EmberRuntimeError(
                f"{spec.name} database state must contain a JSON object"
            )
        database_state = loaded

    seed_text = os.getenv(spec.seed_env, "").strip()
    if seed_text:
        seed = _decode_seed(seed_text, spec)
        digest = hashlib.sha256(
            json.dumps(seed, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        applied = xsp_runtime._config_get(spec.seed_key)
        if applied != digest:
            for source_name, existing in (("disk", disk_state), ("database", database_state)):
                if existing is not None and existing not in (spec.default_state, seed):
                    raise xsp_runtime.EmberRuntimeError(
                        f"{spec.name} {source_name} state conflicts with migration seed"
                    )
            xsp_runtime._atomic_json(spec.state_path, seed)
            xsp_runtime._config_put(
                spec.state_key,
                json.dumps(seed, separators=(",", ":"), default=str),
            )
            xsp_runtime._config_put(spec.seed_key, digest)
            return "seed"

    if disk_state is not None:
        return "disk"
    if database_state is not None:
        state = database_state
        source = "database"
    else:
        state = spec.default_state
        source = "fresh_empty"
    xsp_runtime._atomic_json(spec.state_path, state)
    return source


def _last_line(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return lines[-1] if lines else ""


def _redact(text: str) -> str:
    text = re.sub(r"account[=: ]+\d+", "account=***2331", text, flags=re.I)
    text = re.sub(r"(?i)(?:order_id|long_order|short_order|entry_order_id)=\S+", "order=[redacted]", text)
    return text[-800:]


def _dependency_gaps(spec: StrategySpec) -> list[str]:
    gaps = []
    for alternatives in spec.required_any:
        if not any(os.getenv(name, "").strip() for name in alternatives):
            gaps.append("|".join(alternatives))
    return gaps


def _validate_live(spec: StrategySpec, live: bool, hydrate_source: str) -> None:
    xsp_runtime._validate_runtime(live)
    gaps = _dependency_gaps(spec)
    if gaps:
        raise xsp_runtime.EmberRuntimeError(
            f"missing required cloud data environment: {', '.join(gaps)}"
        )
    if live and hydrate_source == "fresh_empty":
        raise xsp_runtime.EmberRuntimeError(
            "live blocked: no migrated strategy-owned state snapshot"
        )


def _forced_cfg(spec: StrategySpec, live: bool) -> Any:
    cfg = spec.config_loader()
    return replace(cfg, armed=live, dry_run=not live)


def _mirror(spec: StrategySpec, mode: str, rc: int, source: str) -> None:
    state = spec.state_path.read_text(encoding="utf-8")
    parsed = json.loads(state)
    xsp_runtime._config_put(spec.state_key, json.dumps(parsed, separators=(",", ":"), default=str))
    xsp_runtime._config_put(
        spec.status_key,
        json.dumps({
            "strategy": spec.name,
            "configured_live": _env_bool(spec.live_env),
            "mode": mode,
            "return_code": rc,
            "updated_at": datetime.now(CT).isoformat(),
            "last_log": _last_line(spec.log_path),
            "hydrate_source": source,
            "dependency_gaps": _dependency_gaps(spec),
        }, separators=(",", ":")),
    )


def _record_blocked(spec: StrategySpec, mode: str, exc: Exception) -> None:
    try:
        xsp_runtime._config_put(
            spec.status_key,
            json.dumps({
                "strategy": spec.name,
                "configured_live": _env_bool(spec.live_env),
                "mode": mode,
                "return_code": 2,
                "updated_at": datetime.now(CT).isoformat(),
                "last_log": f"BLOCKED {type(exc).__name__}: {exc}",
                "dependency_gaps": _dependency_gaps(spec),
            }, separators=(",", ":")),
        )
    except Exception:  # noqa: BLE001
        logger.exception("[EMBER:%s] failed to persist blocked status", spec.name)


def _run(name: str, mode: str | None = None, *, scan_tv: bool = False) -> None:
    spec = SPECS[name]
    if not _env_bool(spec.enabled_env):
        return
    lock_db = _acquire_lock(name)
    if lock_db is None:
        logger.info("[EMBER:%s] skipped overlapping cycle", name)
        return
    label = mode or "AUTO"
    try:
        source = _hydrate(spec)
        live = _env_bool(spec.live_env)
        _validate_live(spec, live, source)
        cfg = _forced_cfg(spec, live)
        if scan_tv:
            _run_tv_scanner()
        agent_lock = _acquire_lock("agent-runtime")
        if agent_lock is None:
            raise xsp_runtime.EmberRuntimeError(
                "shared broker runner busy; next scheduled tick will retry"
            )
        try:
            rc = spec.runner(datetime.now(CT), cfg, mode)
        finally:
            _release_lock(agent_lock, "agent-runtime")
        _mirror(spec, label, rc, source)
        logger.info("[EMBER:%s] mode=%s live=%s rc=%s", name, label, int(live), rc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[EMBER:%s] cycle blocked: %s", name, exc)
        _record_blocked(spec, label, exc)
    finally:
        _release_lock(lock_db, name)


def _run_tv_scanner() -> None:
    output = tv_book.HERE / "scanner-output.log"
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "backend.ember.legacy.tv_scanner", "--live"]
    with output.open("a", encoding="utf-8") as stream:
        result = subprocess.run(
            cmd,
            cwd=str(Path(__file__).resolve().parents[2]),
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=25 * 60,
            check=False,
        )
    if result.returncode:
        raise xsp_runtime.EmberRuntimeError(
            f"TradingVolatility scanner exited {result.returncode}"
        )


def _broker_preflight(name: str, account: str, output: Path) -> int:
    """Verify Claude+Robinhood connectivity without supplying any order tool."""
    home = xsp_runtime._prepare_claude_home()
    del home
    bundled = Path(__file__).resolve().parents[2] / "frontend" / "node_modules" / ".bin" / "claude"
    prompt = (
        f"Read-only preflight for EMBER {name}. Call get_accounts and confirm account "
        f"{account} is present, then call get_equity_positions and get_option_positions. "
        "Do not place, cancel, import, or modify anything. Print one line beginning PREFLIGHT OK "
        "or PREFLIGHT BLOCKED and never print full account or order identifiers."
    )
    tools = [
        "mcp__robinhood-trading__get_accounts",
        "mcp__robinhood-trading__get_equity_positions",
        "mcp__robinhood-trading__get_option_positions",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as stream:
        result = subprocess.run(
            [str(bundled), "-p", "--allowedTools", *tools],
            cwd=str(output.parent), input=prompt, stdout=stream,
            stderr=subprocess.STDOUT, text=True, timeout=180,
            env=xsp_runtime.xsp_flow_live.read_secret_environment(), check=False,
        )
    return int(result.returncode)


def run_preflight(name: str) -> None:
    mode = "PREFLIGHT" if name == "spike" else "RECONCILE"
    _run(name, mode)


def run_call_diag() -> None:
    _run("call_diag")


def run_night_shift() -> None:
    _run("night_shift")


def run_divhike() -> None:
    _run("divhike")


def run_tv_book() -> None:
    _run("tv_book", scan_tv=True)


def run_spike_enter() -> None:
    _run("spike", "ENTER")


def run_spike_manage() -> None:
    _run("spike", "MANAGE")


def _state_count(name: str, state: Any) -> int:
    if not isinstance(state, dict):
        return 0
    positions = state.get("position") if name == "night_shift" else state.get("positions")
    if isinstance(positions, dict):
        return len(positions)
    if isinstance(positions, list):
        return sum(1 for p in positions if isinstance(p, dict) and p.get("state") != "closed")
    return int(bool(positions))


def read_status() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, spec in SPECS.items():
        raw = xsp_runtime._config_get(spec.status_key)
        state_raw = xsp_runtime._config_get(spec.state_key)
        try:
            status = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            status = {"last_log": "BLOCKED malformed status row", "return_code": 2}
        try:
            state = json.loads(state_raw) if state_raw else {}
        except json.JSONDecodeError:
            state = {}
        base = {
            "enabled": _env_bool(spec.enabled_env),
            "configured_live": _env_bool(spec.live_env),
            "runtime": "render",
            "last_run_at": status.get("updated_at"),
            "last_mode": status.get("mode"),
            "last_return_code": status.get("return_code"),
            "last_result": _redact(str(status.get("last_log", "not run"))),
            "state_source": status.get("hydrate_source"),
            "dependency_gaps": status.get("dependency_gaps", _dependency_gaps(spec)),
            "open_position_count": _state_count(name, state),
        }
        names = spec.aliases or (name,)
        result.extend([{"strategy": alias, **base} for alias in names])
    return result


def register(scheduler: Any) -> None:
    """Register enabled fleet jobs on the existing single Render service."""
    preflight_delay = 75
    for name, spec in SPECS.items():
        if not _env_bool(spec.enabled_env):
            logger.info("[EMBER:%s] module disabled", name)
            continue
        scheduler.add_job(
            run_preflight, "date",
            args=[name], run_date=datetime.now(CT) + timedelta(seconds=preflight_delay),
            id=f"ember_{name}_preflight", replace_existing=True, max_instances=1,
            misfire_grace_time=120,
        )
        preflight_delay += 75

    jobs = [
        ("night_shift", run_night_shift, {"hour": "8-9,14-15", "minute": "*", "second": "0"}),
        ("spike_enter", run_spike_enter, {"hour": "8-15", "minute": "0,15,30,45", "second": "10"}),
        ("spike_manage", run_spike_manage, {"hour": "14", "minute": "45", "second": "10"}),
        ("call_diag", run_call_diag, {"hour": "8-15", "minute": "*", "second": "20"}),
        ("divhike", run_divhike, {"hour": "8,15", "minute": "10,33,55-59", "second": "30"}),
        ("tv_book", run_tv_book, {"hour": "8-16", "minute": "5,35", "second": "40"}),
    ]
    for job_name, func, cron in jobs:
        spec_name = "spike" if job_name.startswith("spike_") else job_name
        if not _env_bool(SPECS[spec_name].enabled_env):
            continue
        scheduler.add_job(
            func, "cron", day_of_week="mon-fri", timezone="America/Chicago",
            id=f"ember_{job_name}_cycle", replace_existing=True, max_instances=1,
            coalesce=True, misfire_grace_time=60, **cron,
        )
        logger.warning(
            "[EMBER:%s] registered configured_live=%s",
            job_name, int(_env_bool(SPECS[spec_name].live_env)),
        )
