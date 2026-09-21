"""Render scheduler wrapper for the frozen ASTRA-3 real-money mirror."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import astra_live
from . import runtime as xsp_runtime
from .fleet_runtime import _acquire_lock, _release_lock


logger = logging.getLogger("spreadworks.ember.astra")
CT = ZoneInfo("America/Chicago")
STATUS_KEY = "ember.astra3-live.status"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _configured_live() -> bool:
    return (
        _env_bool("ASTRA_LIVE_ARMED")
        and not _env_bool("ASTRA_LIVE_DRY_RUN", True)
        and _env_bool("ASTRA_LIVE_FORWARD_GATE_OVERRIDE")
    )


def _hydrate_state() -> str:
    if astra_live.STATE_PATH.exists():
        return "disk"
    encoded = os.getenv("ASTRA_LIVE_STATE_B64", "").strip()
    if not encoded:
        if _configured_live():
            raise xsp_runtime.EmberRuntimeError(
                "live blocked: ASTRA state was not migrated to Render"
            )
        astra_live._atomic_json(  # noqa: SLF001
            astra_live.STATE_PATH,
            astra_live._default_state(astra_live.Config.load()),  # noqa: SLF001
        )
        return "fresh_safe"
    try:
        state = json.loads(base64.b64decode(encoded).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise xsp_runtime.EmberRuntimeError("invalid ASTRA state seed") from exc
    if not isinstance(state, dict) or state.get("account") != astra_live.ACCOUNT:
        raise xsp_runtime.EmberRuntimeError("ASTRA state seed account mismatch")
    astra_live._atomic_json(astra_live.STATE_PATH, state)  # noqa: SLF001
    return "seed"


def _last_log_line() -> str:
    if not astra_live.LOG_PATH.exists():
        return "not run"
    lines = astra_live.LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-1] if lines else "not run"


def _redact(value: str) -> str:
    value = re.sub(r"\b570892331\b", "***2331", value)
    value = re.sub(r"(?i)(order_id|ref_id)=\S+", r"\1=[redacted]", value)
    return value[-1200:]


def _record(mode: str, rc: int, source: str, error: str | None = None) -> None:
    state: dict[str, Any] = {}
    if astra_live.STATE_PATH.exists():
        try:
            state = json.loads(astra_live.STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    payload = {
        "configured_live": _configured_live(),
        "mode": mode,
        "return_code": rc,
        "updated_at": datetime.now(CT).isoformat(),
        "last_log": _redact(error or _last_log_line()),
        "hydrate_source": source,
        "kill_latched": bool(state.get("kill_latched")),
        "open_position_count": int(bool(state.get("active"))),
        "completed_trades": int((state.get("sleeve") or {}).get("completed_trades", 0)),
    }
    xsp_runtime._config_put(STATUS_KEY, json.dumps(payload, separators=(",", ":")))


def _validate_live() -> None:
    cfg = astra_live.Config.load()
    cfg.validate()
    if _configured_live() and cfg.max_contracts != 1:
        raise xsp_runtime.EmberRuntimeError(
            "live blocked: ASTRA remains one contract until its live gate passes"
        )


def _run(mode: str, args: list[str]) -> None:
    if not _env_bool("ASTRA_LIVE_ENABLED"):
        return
    strategy_lock = _acquire_lock("astra3-live")
    if strategy_lock is None:
        logger.info("[EMBER:astra3-live] skipped overlapping cycle")
        return
    agent_lock = None
    source = "unknown"
    try:
        _validate_live()
        source = _hydrate_state()
        agent_lock = _acquire_lock("agent-runtime", wait_seconds=10 * 60)
        if agent_lock is None:
            raise xsp_runtime.EmberRuntimeError("shared broker runner busy; lock wait expired")
        rc = int(astra_live.main(args))
        _record(mode, rc, source)
        logger.info("[EMBER:astra3-live] mode=%s live=%s rc=%s", mode, int(_configured_live()), rc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[EMBER:astra3-live] cycle blocked: %s", exc)
        try:
            _record(mode, 2, source, f"BLOCKED {type(exc).__name__}: {exc}")
        except Exception:  # noqa: BLE001
            logger.exception("[EMBER:astra3-live] failed to persist blocked status")
    finally:
        if agent_lock is not None:
            _release_lock(agent_lock, "agent-runtime")
        _release_lock(strategy_lock, "astra3-live")


def run_broker_audit() -> None:
    _run("BROKER_AUDIT", ["--broker-audit"])


def run_cycle() -> None:
    _run("AUTO", [])


def read_status() -> dict[str, Any]:
    raw = xsp_runtime._config_get(STATUS_KEY)
    try:
        status = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        status = {"last_log": "BLOCKED malformed status row", "return_code": 2}
    return {
        "enabled": _env_bool("ASTRA_LIVE_ENABLED"),
        "configured_live": _configured_live(),
        "runtime": "render",
        "last_run_at": status.get("updated_at"),
        "last_mode": status.get("mode"),
        "last_return_code": status.get("return_code"),
        "last_result": _redact(str(status.get("last_log", "not run"))),
        "state_source": status.get("hydrate_source"),
        "kill_latched": bool(status.get("kill_latched")),
        "open_position_count": int(status.get("open_position_count") or 0),
        "completed_trades": int(status.get("completed_trades") or 0),
        "maximum_contracts": int(os.getenv("ASTRA_LIVE_MAX_CONTRACTS", "1")),
        "forward_gate_override": _env_bool("ASTRA_LIVE_FORWARD_GATE_OVERRIDE"),
    }


def register(scheduler: Any) -> None:
    if not _env_bool("ASTRA_LIVE_ENABLED"):
        logger.info("[EMBER:astra3-live] module disabled")
        return
    scheduler.add_job(
        run_broker_audit,
        "date",
        run_date=datetime.now(CT) + timedelta(seconds=150),
        id="ember_astra3_live_preflight",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        run_cycle,
        "cron",
        day_of_week="mon-fri",
        hour="8-15",
        minute="*",
        second="5",
        timezone="America/Chicago",
        id="ember_astra3_live_cycle",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    logger.warning("[EMBER:astra3-live] registered configured_live=%s", int(_configured_live()))
