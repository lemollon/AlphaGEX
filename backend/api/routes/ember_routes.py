"""
EMBER backtester routes.

Build cache + instant exit-policy evaluation for the 1DTE SPY Iron Condor.

POST /api/ember/build              -> start or retrieve a path build (cached by params)
GET  /api/ember/build/{build_id}  -> poll build status
POST /api/ember/evaluate           -> instant policy evaluation against a completed build
"""

from __future__ import annotations

import os
import threading
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backtest.ember.build import BuildCancelled, build_paths, evaluate_grid, evaluate_policy
from backtest.ember.dbutil import open_build_connection
from backtest.ember.cache import (
    build_key,
    create_pending,
    ensure_tables,
    get_build,
    is_cancel_requested,
    load_paths,
    reap_stale_builds,
    request_cancel,
    set_canceled,
    set_completed,
    set_failed,
    set_progress,
)
from backtest.ember.policy import SPARK_BASELINE, ExitPolicy, default_grid

router = APIRouter(prefix="/api/ember", tags=["Ember"])


def _get_db_url() -> str:
    return os.environ["DATABASE_URL"]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    start: str                      # "YYYY-MM-DD"
    end: str                        # "YYYY-MM-DD"
    entry_minute: int = 30
    short_delta: float = 0.16
    wing_width: float = 5.0
    fill: str = "ask_cross"         # ask_cross | mid | mid_slip


class EvaluateRequest(BaseModel):
    build_id: str
    profit_target_pct: Optional[float] = None
    stop_loss_mult: Optional[float] = None
    time_stop_minute: Optional[int] = None
    trail_activation_pct: Optional[float] = None
    trail_giveback_pct: Optional[float] = None
    min_hold_minutes: int = 5


# ---------------------------------------------------------------------------
# Pure helper (unit-testable without heavy deps)
# ---------------------------------------------------------------------------

def _policy_from_params(body) -> ExitPolicy:
    """Build an ExitPolicy from any object with the EvaluateRequest attributes."""
    return ExitPolicy(
        name="custom",
        profit_target_pct=body.profit_target_pct,
        stop_loss_mult=body.stop_loss_mult,
        time_stop_minute=body.time_stop_minute,
        trail_activation_pct=body.trail_activation_pct,
        trail_giveback_pct=body.trail_giveback_pct,
        min_hold_minutes=body.min_hold_minutes,
    )


# ---------------------------------------------------------------------------
# Background thread worker
# ---------------------------------------------------------------------------

def _run_build(db_url: str, build_id: str, params: dict) -> None:
    """Executed in a daemon thread. Runs build_paths, then persists the result.

    Opens ONE autocommit connection for the full build loop so that a 567-day
    build uses ~1 connection instead of ~1,100 short-lived ones."""
    bid = build_id
    conn = None
    try:
        conn = open_build_connection(db_url)
        start = date.fromisoformat(params["start"])
        end = date.fromisoformat(params["end"])

        set_progress(db_url, bid, 0, "Queued — starting…", conn=conn)

        paths = build_paths(
            start,
            end,
            entry_minute=params["entry_minute"],
            short_delta=params["short_delta"],
            wing_width=params["wing_width"],
            fill=params["fill"],
            db_url=db_url,
            conn=conn,
            progress_cb=lambda done, total, msg: set_progress(
                db_url, bid, int(100 * done / total) if total else 0, msg, conn=conn
            ),
            should_cancel=lambda: is_cancel_requested(db_url, bid, conn=conn),
        )
        set_completed(db_url, bid, paths)   # transient connection, once — fine
    except BuildCancelled:
        set_canceled(db_url, bid)
    except Exception as exc:
        set_failed(db_url, bid, str(exc))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/build")
async def start_build(body: BuildRequest):
    """
    Enqueue a path build (or return immediately if already cached/running).

    Returns build_id and status. Poll GET /api/ember/build/{build_id} for progress.
    """
    try:
        db_url = _get_db_url()
        params = {
            "start": body.start,
            "end": body.end,
            "entry_minute": body.entry_minute,
            "short_delta": body.short_delta,
            "wing_width": body.wing_width,
            "fill": body.fill,
        }
        ensure_tables(db_url)
        reap_stale_builds(db_url)
        bid = build_key(params)

        existing = get_build(db_url, bid)

        if existing and existing["status"] == "completed":
            return {
                "build_id": bid,
                "status": "completed",
                "cached": True,
                "n_days": existing.get("n_days"),
            }

        if existing and existing["status"] in ("pending", "running"):
            # Reap already demoted genuinely stale builds to failed, so this
            # is a live in-flight build — return its current status as-is.
            return {
                "build_id": bid,
                "status": existing["status"],
                "cached": False,
            }

        # None / failed / canceled — create fresh and launch.
        create_pending(db_url, bid, params)
        threading.Thread(
            target=_run_build,
            args=(db_url, bid, params),
            daemon=True,
        ).start()

        return {"build_id": bid, "status": "pending", "cached": False}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/build/{build_id}")
async def get_build_status(build_id: str):
    """Poll build status and progress."""
    try:
        db_url = _get_db_url()
        record = get_build(db_url, build_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Build {build_id!r} not found")
        return record
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/build/{build_id}/cancel")
async def cancel_build(build_id: str):
    """Request cancellation of an in-flight build."""
    try:
        db_url = _get_db_url()
        ok = request_cancel(db_url, build_id)
        if not ok:
            # Not pending/running — already finished, canceled, or unknown.
            existing = get_build(db_url, build_id)
            status = existing["status"] if existing else "not_found"
            raise HTTPException(status_code=409, detail=f"build not cancelable (status: {status})")
        return {"build_id": build_id, "status": "canceling"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/evaluate")
async def evaluate(body: EvaluateRequest):
    """
    Instantly evaluate a custom exit policy (plus the SPARK baseline and full grid)
    against a completed build's cached day-paths.
    """
    try:
        db_url = _get_db_url()

        record = get_build(db_url, body.build_id)
        if record is None:
            raise HTTPException(status_code=404, detail="build not found")
        if record["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"build not ready: {record['status']}",
            )

        paths = load_paths(db_url, body.build_id)
        chosen = _policy_from_params(body)

        return {
            "chosen": evaluate_policy(paths, chosen),
            "baseline": evaluate_policy(paths, SPARK_BASELINE),
            "grid": evaluate_grid(paths, default_grid()),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
