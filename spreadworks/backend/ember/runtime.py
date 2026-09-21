"""Register the durable EMBER XSP executor with SpreadWorks' scheduler.

The web service supplies only the clock.  The frozen signal, broker checks,
order sequencing, and idempotency keys remain owned by ``xsp_flow_live``.
Render live mode is refused unless both bot state and Claude MCP credentials
are located under the persistent-disk mount.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text as sa_text

from ..db import SessionLocal
from . import xsp_flow_live


logger = logging.getLogger("spreadworks.ember.runtime")
CT = ZoneInfo("America/Chicago")

STATE_DB_KEY = "ember.xsp-flow-v1.state"
STATUS_DB_KEY = "ember.xsp-flow-v1.status"
MCP_SERVER_NAME = "robinhood-trading"
MCP_SERVER_URL = "https://agent.robinhood.com/mcp/trading"
MCP_CREDENTIAL_KEY_DEFAULT = "robinhood-trading|5cbe81c78ff5ae58"


class EmberRuntimeError(RuntimeError):
    """A configuration or persistence fault that must fail closed."""


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _config_get(key: str) -> str | None:
    if SessionLocal is None:
        return None
    db = SessionLocal()
    try:
        return db.execute(
            sa_text("SELECT value FROM autonomous_config WHERE key = :key"),
            {"key": key},
        ).scalar_one_or_none()
    finally:
        db.close()


def _config_put(key: str, value: str) -> None:
    if SessionLocal is None:
        raise EmberRuntimeError("DATABASE_URL is unavailable")
    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO autonomous_config (key, value) VALUES (:key, :value) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            ),
            {"key": key, "value": value},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _acquire_cycle_lock(*, wait_seconds: float = 0) -> Any | None:
    """Return the session holding both XSP and fleet-wide broker locks."""
    if SessionLocal is None:
        raise EmberRuntimeError("DATABASE_URL is unavailable")
    db = SessionLocal()
    try:
        acquired = db.execute(
            sa_text("SELECT pg_try_advisory_lock(hashtext(:name))"),
            {"name": xsp_flow_live.BOT_ID},
        ).scalar_one()
        if not acquired:
            db.close()
            return None
        deadline = time.monotonic() + max(0, wait_seconds)
        while True:
            global_acquired = db.execute(
                sa_text("SELECT pg_try_advisory_lock(hashtext(:name))"),
                {"name": "ember-fleet:agent-runtime"},
            ).scalar_one()
            if global_acquired:
                break
            if time.monotonic() >= deadline:
                db.execute(
                    sa_text("SELECT pg_advisory_unlock(hashtext(:name))"),
                    {"name": xsp_flow_live.BOT_ID},
                )
                db.close()
                return None
            time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
        return db
    except Exception:
        db.close()
        raise


def _release_cycle_lock(db: Any) -> None:
    try:
        db.execute(
            sa_text("SELECT pg_advisory_unlock(hashtext(:name))"),
            {"name": "ember-fleet:agent-runtime"},
        )
        db.execute(
            sa_text("SELECT pg_advisory_unlock(hashtext(:name))"),
            {"name": xsp_flow_live.BOT_ID},
        )
    except Exception:  # noqa: BLE001
        logger.exception("[EMBER] failed to release advisory lock")
    finally:
        db.close()


def _credential_seed() -> dict[str, Any]:
    encoded = os.getenv("EMBER_CLAUDE_CREDENTIAL_B64", "").strip()
    if not encoded:
        raise EmberRuntimeError("EMBER_CLAUDE_CREDENTIAL_B64 is not configured")
    try:
        payload = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise EmberRuntimeError("Robinhood MCP credential seed is malformed") from exc
    if not isinstance(payload, dict):
        raise EmberRuntimeError("Claude credential seed is incomplete")
    claude_auth = payload.get("claudeAiOauth")
    oauth = payload.get("mcpOAuth")
    if not isinstance(claude_auth, dict) or not claude_auth.get("refreshToken"):
        raise EmberRuntimeError("Claude runtime credential seed is incomplete")
    if not isinstance(oauth, dict):
        raise EmberRuntimeError("Robinhood MCP credential seed is incomplete")
    robinhood = next(
        (
            value
            for value in oauth.values()
            if isinstance(value, dict) and value.get("serverName") == MCP_SERVER_NAME
        ),
        None,
    )
    required = {"serverName", "serverUrl", "accessToken", "refreshToken", "clientId"}
    if not isinstance(robinhood, dict) or not required.issubset(robinhood):
        raise EmberRuntimeError("Robinhood MCP credential seed is incomplete")
    if robinhood.get("serverName") != MCP_SERVER_NAME:
        raise EmberRuntimeError("Robinhood MCP credential seed has wrong serverName")
    if robinhood.get("serverUrl") != MCP_SERVER_URL:
        raise EmberRuntimeError("Robinhood MCP credential seed has wrong serverUrl")
    return payload


def _prepare_claude_home() -> Path:
    """Create only the Robinhood MCP config; never copy unrelated credentials."""
    home_text = os.getenv("EMBER_CLAUDE_HOME", "").strip()
    if not home_text:
        raise EmberRuntimeError("EMBER_CLAUDE_HOME is not configured")
    home = Path(home_text).expanduser().resolve()
    credential_path = home / ".claude" / ".credentials.json"
    config_path = home / ".claude.json"
    credential_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict[str, Any] = {}
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config = loaded
        except (OSError, json.JSONDecodeError) as exc:
            raise EmberRuntimeError("Claude MCP config is unreadable") from exc
    config.setdefault("mcpServers", {})[MCP_SERVER_NAME] = {
        "type": "http",
        "url": MCP_SERVER_URL,
    }
    _atomic_json(config_path, config)

    existing: dict[str, Any] = {}
    if credential_path.exists():
        try:
            loaded = json.loads(credential_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError) as exc:
            raise EmberRuntimeError("Claude MCP credentials are unreadable") from exc

    oauth = existing.setdefault("mcpOAuth", {})
    has_robinhood = any(
        isinstance(value, dict)
        and value.get("serverName") == MCP_SERVER_NAME
        and value.get("serverUrl") == MCP_SERVER_URL
        and value.get("refreshToken")
        for value in oauth.values()
    )
    has_claude_auth = bool(
        isinstance(existing.get("claudeAiOauth"), dict)
        and existing["claudeAiOauth"].get("refreshToken")
    )
    if not has_robinhood or not has_claude_auth:
        seed = _credential_seed()
        key = os.getenv(
            "EMBER_RH_MCP_CREDENTIAL_KEY", MCP_CREDENTIAL_KEY_DEFAULT
        ).strip()
        seeded_oauth = seed["mcpOAuth"]
        robinhood = next(
            value
            for value in seeded_oauth.values()
            if value.get("serverName") == MCP_SERVER_NAME
        )
        oauth[key] = robinhood
        existing["claudeAiOauth"] = seed["claudeAiOauth"]
        _atomic_json(credential_path, existing)
    try:
        credential_path.chmod(0o600)
    except OSError:
        pass
    return home


def _validate_runtime(live: bool) -> None:
    if os.getenv("RENDER", "").strip().lower() == "true" and live:
        data_dir = Path(os.getenv("EMBER_DATA_DIR", "")).as_posix()
        claude_home = Path(os.getenv("EMBER_CLAUDE_HOME", "")).as_posix()
        if not data_dir.startswith("/var/data/"):
            raise EmberRuntimeError("live state is not on the Render persistent disk")
        if not claude_home.startswith("/var/data/"):
            raise EmberRuntimeError("live MCP credentials are not on the Render persistent disk")
    _prepare_claude_home()


def _hydrate_state() -> None:
    if xsp_flow_live.STATE_PATH.exists():
        return
    encoded = _config_get(STATE_DB_KEY)
    if encoded:
        try:
            state = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise EmberRuntimeError("database state mirror is malformed") from exc
        _atomic_json(xsp_flow_live.STATE_PATH, state)
        return
    _atomic_json(
        xsp_flow_live.STATE_PATH,
        {"bot_id": xsp_flow_live.BOT_ID, "positions": [], "days": {}},
    )


def _mirror_state(mode: str, rc: int) -> None:
    state = xsp_flow_live.load_state()
    _config_put(STATE_DB_KEY, json.dumps(state, separators=(",", ":"), default=str))
    status = {
        "bot_id": xsp_flow_live.BOT_ID,
        "account": xsp_flow_live.ACCOUNT,
        "configured_live": _env_bool("EMBER_XSP_LIVE"),
        "mode": mode,
        "return_code": rc,
        "updated_at": datetime.now(CT).isoformat(),
        "last_log": xsp_flow_live.last_log_line(),
    }
    _config_put(STATUS_DB_KEY, json.dumps(status, separators=(",", ":")))


def _run(mode: str | None) -> None:
    if not _env_bool("EMBER_XSP_ENABLED"):
        return
    lock_db = _acquire_cycle_lock(wait_seconds=10 * 60)
    if lock_db is None:
        logger.info("[EMBER] skipped overlapping XSP cycle")
        return
    try:
        with xsp_flow_live.single_instance_lock():
            live = _env_bool("EMBER_XSP_LIVE")
            _validate_runtime(live)
            _hydrate_state()
            now_ct = datetime.now(CT)
            rc = xsp_flow_live.run_tick(now_ct, live=live, forced_mode=mode)
            _mirror_state(mode or "AUTO", rc)
        logger.info(
            "[EMBER] XSP cycle mode=%s live=%s rc=%s status=%s",
            mode or "AUTO",
            int(live),
            rc,
            xsp_flow_live.last_log_line(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[EMBER] XSP cycle blocked: %s", exc)
        try:
            _config_put(
                STATUS_DB_KEY,
                json.dumps(
                    {
                        "bot_id": xsp_flow_live.BOT_ID,
                        "configured_live": _env_bool("EMBER_XSP_LIVE"),
                        "mode": mode or "AUTO",
                        "return_code": 2,
                        "updated_at": datetime.now(CT).isoformat(),
                        "last_log": f"BLOCKED {type(exc).__name__}: {exc}",
                    },
                    separators=(",", ":"),
                ),
            )
        except Exception:  # noqa: BLE001
            logger.exception("[EMBER] failed to persist blocked status")
    finally:
        _release_cycle_lock(lock_db)


def run_preflight() -> None:
    _run("PREFLIGHT")


def run_cycle() -> None:
    _run(None)


def read_status() -> dict[str, Any]:
    raw = _config_get(STATUS_DB_KEY)
    state_raw = _config_get(STATE_DB_KEY)
    try:
        status = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        status = {"last_log": "BLOCKED malformed status row"}
    try:
        state = json.loads(state_raw) if state_raw else None
    except json.JSONDecodeError:
        state = None
    days = state.get("days", {}) if isinstance(state, dict) else {}
    today = days.get(datetime.now(CT).date().isoformat(), {}) if isinstance(days, dict) else {}
    entry = today.get("entry", {}) if isinstance(today, dict) else {}
    positions = state.get("positions", []) if isinstance(state, dict) else []
    open_position_count = sum(
        1
        for position in positions
        if isinstance(position, dict) and position.get("state") != "closed"
    )
    last_log = str(status.get("last_log", ""))
    last_log = re.sub(r"account=\d+", "account=***2331", last_log)
    last_log = re.sub(
        r"(?i)(?:long|short|unwind)_order=\S+",
        "order=[redacted]",
        last_log,
    )
    return {
        "enabled": _env_bool("EMBER_XSP_ENABLED"),
        "configured_live": _env_bool("EMBER_XSP_LIVE"),
        "bot_id": xsp_flow_live.BOT_ID,
        "last_run_at": status.get("updated_at"),
        "last_mode": status.get("mode"),
        "last_return_code": status.get("return_code"),
        "last_result": last_log,
        "today_entry_state": entry.get("state") if isinstance(entry, dict) else None,
        "open_position_count": open_position_count,
    }


def register(scheduler: Any) -> None:
    """Attach XSP Flow and the rest of EMBER to the Render scheduler."""
    if not _env_bool("EMBER_XSP_ENABLED"):
        logger.info("[EMBER] XSP module disabled")
    else:
        scheduler.add_job(
            run_preflight,
            "date",
            run_date=datetime.now(CT) + timedelta(seconds=10),
            id="ember_xsp_preflight",
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
            second="50",
            timezone="America/Chicago",
            id="ember_xsp_cycle",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )
        logger.warning(
            "[EMBER] XSP module registered configured_live=%s account=%s",
            int(_env_bool("EMBER_XSP_LIVE")),
            xsp_flow_live.ACCOUNT,
        )
    from .fleet_runtime import register as register_fleet
    register_fleet(scheduler)
    from .astra_runtime import register as register_astra
    register_astra(scheduler)
