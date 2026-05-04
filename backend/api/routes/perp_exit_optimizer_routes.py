"""
Admin route for the perp exit-rule optimizer.

POST /api/admin/perp-exit-optimizer/run     -> kicks off a background run, returns run_id
GET  /api/admin/perp-exit-optimizer/runs    -> list recent runs
GET  /api/admin/perp-exit-optimizer/result  -> latest finished run, or ?run_id=N for a specific one

Results live in `perp_exit_optimizer_runs` (auto-created on first POST).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/perp-exit-optimizer", tags=["AdminPerpExitOptimizer"])

OPTIMIZER_AVAILABLE = False
try:
    from backtest.perp_exit_optimizer import search_all, BOTS  # noqa: F401
    OPTIMIZER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Perp exit optimizer not importable: {e}")

get_connection = None
try:
    from database_adapter import get_connection
except ImportError:
    pass


_table_ready = False
_table_lock = threading.Lock()


def _ensure_table() -> None:
    global _table_ready
    if _table_ready or get_connection is None:
        return
    with _table_lock:
        if _table_ready:
            return
        conn = get_connection()
        if not conn:
            return
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS perp_exit_optimizer_runs (
                    id SERIAL PRIMARY KEY,
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    finished_at TIMESTAMP WITH TIME ZONE,
                    grid VARCHAR(20),
                    bot_filter VARCHAR(40),
                    status VARCHAR(20) DEFAULT 'running',
                    error TEXT,
                    result JSONB
                )
            """)
            conn.commit()
            cur.close()
            _table_ready = True
        except Exception as e:
            logger.error(f"perp_exit_optimizer_runs table create failed: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass


def _insert_run(grid: str, bot: Optional[str]) -> Optional[int]:
    _ensure_table()
    if get_connection is None:
        return None
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO perp_exit_optimizer_runs (grid, bot_filter, status) VALUES (%s, %s, 'running') RETURNING id",
            (grid, bot),
        )
        rid = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return rid
    except Exception as e:
        logger.error(f"perp_exit_optimizer_runs insert failed: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _finalize_run(run_id: int, result: dict | None, error: str | None) -> None:
    if get_connection is None or run_id is None:
        return
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE perp_exit_optimizer_runs SET finished_at = NOW(), status = %s, result = %s, error = %s WHERE id = %s",
            ("done" if error is None else "failed", json.dumps(result, default=str) if result else None, error, run_id),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"perp_exit_optimizer_runs finalize failed: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _do_run(run_id: int, grid: str, bot: Optional[str]) -> None:
    try:
        from backtest.perp_exit_optimizer import search_all
        result = search_all(level=grid, bot_filter=bot)
        _finalize_run(run_id, result, None)
    except Exception as e:
        logger.exception("perp exit optimizer background run failed")
        _finalize_run(run_id, None, str(e))


class RunRequest(BaseModel):
    grid: str = "coarse"
    bot: Optional[str] = None


# Map ticker -> (bot_name, autonomous_config key prefix). The bot's
# AgapeXxxPerpConfig.load_from_db reads `key LIKE '<prefix>%'` and strips
# the prefix to produce the attr name, so the keys we write here must
# match the dataclass attribute names exactly.
_BOT_KEY_PREFIX = {
    "XRP":  "agape_xrp_perp_",
    "BTC":  "agape_btc_perp_",
    "ETH":  "agape_eth_perp_",
    "SOL":  "agape_sol_perp_",
    "AVAX": "agape_avax_perp_",
    "DOGE": "agape_doge_perp_",
    "SHIB": "agape_shib_perp_",
    "SHIB_FUTURES": "agape_shib_futures_",
}

# Whitelist of exit-rule knobs the apply endpoint is allowed to change.
# Anything not in this set is rejected so the endpoint can't be used to
# muck with risk caps, sizing, or oracle gates.
_ALLOWED_KEYS = {
    "no_loss_activation_pct",
    "no_loss_trail_distance_pct",
    "no_loss_profit_target_pct",
    "max_unrealized_loss_pct",
    "no_loss_emergency_stop_pct",
    "max_hold_hours",
    "use_sar",
    "sar_trigger_pct",
    "sar_mfe_threshold_pct",
    "use_no_loss_trailing",
}


class ApplyRequest(BaseModel):
    bot: str                          # one of XRP / BTC / ETH / DOGE / SHIB
    config: dict[str, Any]            # subset of _ALLOWED_KEYS -> value
    note: Optional[str] = None


def _upsert_config(prefix: str, key: str, value: Any) -> bool:
    if get_connection is None:
        return False
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        full_key = f"{prefix}{key}"
        # autonomous_config schema: (key TEXT PRIMARY KEY, value TEXT)
        cur.execute(
            """
            INSERT INTO autonomous_config (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (full_key, str(value)),
        )
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"autonomous_config UPSERT failed for {prefix}{key}={value}: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.post("/apply")
async def apply_config(req: ApplyRequest):
    """Apply an exit-rule config to a live perp bot's autonomous_config rows.

    Only the keys in `_ALLOWED_KEYS` may be written. The change takes effect
    next time the bot's AgapeXxxPerpConfig.load_from_db runs — typically
    after the alphagex-trader worker restarts. Push a small commit to main
    to bounce the worker, or restart it manually on Render.
    """
    if not OPTIMIZER_AVAILABLE:
        raise HTTPException(status_code=500, detail="optimizer module not available")

    ticker = req.bot.upper().replace("AGAPE_", "").replace("_PERP", "")
    prefix = _BOT_KEY_PREFIX.get(ticker)
    if not prefix:
        raise HTTPException(status_code=400, detail=f"unknown bot {req.bot}")

    bad = [k for k in req.config if k not in _ALLOWED_KEYS]
    if bad:
        raise HTTPException(status_code=400, detail=f"keys not allowed: {bad}")
    if not req.config:
        raise HTTPException(status_code=400, detail="config is empty")

    written: dict[str, Any] = {}
    failed: dict[str, str] = {}
    for k, v in req.config.items():
        if _upsert_config(prefix, k, v):
            written[k] = v
        else:
            failed[k] = "upsert failed"

    return {
        "success": len(failed) == 0,
        "bot": ticker,
        "key_prefix": prefix,
        "written": written,
        "failed": failed,
        "note": req.note,
        "next_step": "Push a small commit to main (or manually redeploy alphagex-trader on Render) so the worker re-reads autonomous_config.",
    }


@router.get("/applied")
async def get_applied(bot: str):
    """Return current autonomous_config rows for a bot's exit-rule knobs."""
    ticker = bot.upper().replace("AGAPE_", "").replace("_PERP", "")
    prefix = _BOT_KEY_PREFIX.get(ticker)
    if not prefix:
        raise HTTPException(status_code=400, detail=f"unknown bot {bot}")
    if get_connection is None:
        raise HTTPException(status_code=500, detail="db unavailable")
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="db unavailable")
    try:
        cur = conn.cursor()
        like = f"{prefix}%"
        cur.execute("SELECT key, value FROM autonomous_config WHERE key LIKE %s ORDER BY key", (like,))
        rows = cur.fetchall()
        cur.close()
        applied = {row[0].replace(prefix, ""): row[1] for row in rows}
        # Filter to only exit-rule keys
        exit_only = {k: v for k, v in applied.items() if k in _ALLOWED_KEYS}
        return {"success": True, "bot": ticker, "applied_exit_keys": exit_only, "all_keys": applied}
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.post("/run")
async def run_optimizer(req: RunRequest, background: BackgroundTasks):
    if not OPTIMIZER_AVAILABLE:
        raise HTTPException(status_code=500, detail="optimizer module not available")
    if req.grid not in ("coarse", "fine"):
        raise HTTPException(status_code=400, detail="grid must be 'coarse' or 'fine'")
    run_id = _insert_run(req.grid, req.bot)
    if run_id is None:
        raise HTTPException(status_code=500, detail="could not create run record")
    background.add_task(_do_run, run_id, req.grid, req.bot)
    return {
        "success": True,
        "run_id": run_id,
        "grid": req.grid,
        "bot": req.bot,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "poll_url": f"/api/admin/perp-exit-optimizer/result?run_id={run_id}",
    }


@router.get("/runs")
async def list_runs(limit: int = Query(default=20, le=100)):
    _ensure_table()
    if get_connection is None:
        raise HTTPException(status_code=500, detail="db unavailable")
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="db unavailable")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, started_at, finished_at, grid, bot_filter, status, error FROM perp_exit_optimizer_runs ORDER BY id DESC LIMIT %s",
            (limit,),
        )
        rows = []
        for r in cur.fetchall():
            rows.append({
                "id": r[0],
                "started_at": r[1].isoformat() if r[1] else None,
                "finished_at": r[2].isoformat() if r[2] else None,
                "grid": r[3],
                "bot_filter": r[4],
                "status": r[5],
                "error": r[6],
            })
        cur.close()
        return {"success": True, "runs": rows}
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.get("/result")
async def get_result(run_id: Optional[int] = None):
    _ensure_table()
    if get_connection is None:
        raise HTTPException(status_code=500, detail="db unavailable")
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="db unavailable")
    try:
        cur = conn.cursor()
        if run_id is not None:
            cur.execute(
                "SELECT id, started_at, finished_at, grid, bot_filter, status, error, result FROM perp_exit_optimizer_runs WHERE id = %s",
                (run_id,),
            )
        else:
            cur.execute(
                "SELECT id, started_at, finished_at, grid, bot_filter, status, error, result FROM perp_exit_optimizer_runs WHERE status = 'done' ORDER BY id DESC LIMIT 1"
            )
        r = cur.fetchone()
        cur.close()
        if not r:
            raise HTTPException(status_code=404, detail="no run found")
        result = r[7]
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                pass
        return {
            "success": True,
            "run": {
                "id": r[0],
                "started_at": r[1].isoformat() if r[1] else None,
                "finished_at": r[2].isoformat() if r[2] else None,
                "grid": r[3],
                "bot_filter": r[4],
                "status": r[5],
                "error": r[6],
                "result": result,
            },
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
