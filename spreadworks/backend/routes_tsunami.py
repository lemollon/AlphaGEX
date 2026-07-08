"""TSUNAMI dashboard API routes.

Per master spec section 10 + AlphaGEX bot-completeness pattern, every
trading bot exposes the same standard endpoint set so the dashboard
can render a uniform view. This module is TSUNAMI's implementation.

Endpoints (mirroring AlphaGEX bot-routes shape):
    GET  /api/tsunami/status                 platform + per-instance health
    GET  /api/tsunami/instances              5 LETF instances + config
    GET  /api/tsunami/positions              open positions across all
    GET  /api/tsunami/positions/{id}         single position with audit chain
    GET  /api/tsunami/equity-curve           historical cumulative P&L
    GET  /api/tsunami/equity-curve/intraday  today's equity snapshots
    GET  /api/tsunami/performance            win rate, P&L stats per instance
    GET  /api/tsunami/gate-failures          recent gate failures
    GET  /api/tsunami/scan-activity          recent entry/management cycle events
    GET  /api/tsunami/logs                   activity log feed
    GET  /api/tsunami/calibration            current calibration values + tags
    GET  /api/tsunami/kill-state             active kills
    GET  /api/tsunami/config                 current TsunamiConfig defaults

All routes are read-only. Mutations (kill clear, news flag) go through
the CLI modules per master spec sections 4-6, not the HTTP API.

All routes wrap DB calls in try/except so a single bad query doesn't
take down the whole module. Empty lists / null fields are returned
when there's no data yet (paper trading just started).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.bots.tsunami.db_compat import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tsunami", tags=["TSUNAMI"])

# Static instance list -- mirrors backend.bots.tsunami.configs.TSUNAMI_INSTANCES
# but kept inline so this route module doesn't depend on the trading
# package being importable from the API service.
_INSTANCES = [
    {"name": "TSUNAMI-MSTU", "letf_ticker": "MSTU", "underlying_ticker": "MSTR",
     "allocation_cap": 200.0, "paper_only": True},
    {"name": "TSUNAMI-TSLL", "letf_ticker": "TSLL", "underlying_ticker": "TSLA",
     "allocation_cap": 200.0, "paper_only": True},
    {"name": "TSUNAMI-NVDL", "letf_ticker": "NVDL", "underlying_ticker": "NVDA",
     "allocation_cap": 200.0, "paper_only": True},
    {"name": "TSUNAMI-CONL", "letf_ticker": "CONL", "underlying_ticker": "COIN",
     "allocation_cap": 150.0, "paper_only": True},
    {"name": "TSUNAMI-AMDL", "letf_ticker": "AMDL", "underlying_ticker": "AMD",
     "allocation_cap": 150.0, "paper_only": True},
]
_PLATFORM_CAP = 750.0
_ACCOUNT_CAPITAL = 5000.0


def _safe_query(sql: str, params: tuple = ()) -> list[tuple]:
    """Run a read-only SELECT and return rows. Empty list on any error
    so dashboard never crashes when a table is empty / missing."""
    try:
        conn = get_connection()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tsunami] DB connect failed: %r", exc)
        return []
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            return cur.fetchall() or []
        finally:
            cur.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tsunami] query failed: %r -- sql=%s", exc, sql[:80])
        return []
    finally:
        conn.close()


# ---- Status / Instances --------------------------------------------------

@router.get("/status")
def tsunami_status() -> dict[str, Any]:
    """Platform + per-instance health summary."""
    heartbeats = {
        row[0]: {
            "last_heartbeat": row[1].isoformat() if row[1] else None,
            "status": row[2], "scan_count": row[3], "trades_today": row[4],
        }
        for row in _safe_query(
            "SELECT bot_name, last_heartbeat, status, scan_count, trades_today "
            "FROM bot_heartbeats WHERE bot_name LIKE 'TSUNAMI-%'"
        )
    }
    open_counts = {
        row[0]: row[1]
        for row in _safe_query(
            "SELECT instance_name, COUNT(*) FROM tsunami_paper_positions "
            "WHERE state IN ('OPEN', 'MANAGING', 'CLOSING') "
            "GROUP BY instance_name"
        )
    }
    active_kills = {
        row[0]: {"trigger_id": row[1], "reason": row[2], "killed_at": row[3].isoformat() if row[3] else None}
        for row in _safe_query(
            "SELECT instance_name, trigger_id, reason, killed_at "
            "FROM tsunami_kill_state WHERE active = TRUE AND scope = 'INSTANCE'"
        )
    }
    platform_kill_rows = _safe_query(
        "SELECT trigger_id, reason, killed_at FROM tsunami_kill_state "
        "WHERE active = TRUE AND scope = 'PLATFORM' LIMIT 1"
    )
    platform_killed = bool(platform_kill_rows)

    instances_status = []
    for cfg in _INSTANCES:
        name = cfg["name"]
        hb = heartbeats.get(name, {})
        instances_status.append({
            "name": name,
            "letf_ticker": cfg["letf_ticker"],
            "underlying_ticker": cfg["underlying_ticker"],
            "allocation_cap": cfg["allocation_cap"],
            "paper_only": cfg["paper_only"],
            "last_heartbeat": hb.get("last_heartbeat"),
            "heartbeat_status": hb.get("status"),
            "scan_count": hb.get("scan_count", 0),
            "trades_today": hb.get("trades_today", 0),
            "open_position_count": open_counts.get(name, 0),
            "killed": name in active_kills,
            "kill_info": active_kills.get(name),
        })

    return {
        "platform_killed": platform_killed,
        "platform_kill_info": (
            {"trigger_id": platform_kill_rows[0][0],
             "reason": platform_kill_rows[0][1],
             "killed_at": platform_kill_rows[0][2].isoformat() if platform_kill_rows[0][2] else None}
            if platform_killed else None
        ),
        "platform_cap": _PLATFORM_CAP,
        "account_capital": _ACCOUNT_CAPITAL,
        "instance_count": len(_INSTANCES),
        "instances": instances_status,
    }


@router.get("/instances")
def tsunami_instances() -> dict[str, Any]:
    """All 5 LETF instances with config + counts."""
    return {"instances": _INSTANCES, "count": len(_INSTANCES)}


# ---- Positions -----------------------------------------------------------

@router.get("/positions")
def tsunami_positions(
    state: Optional[str] = Query(None, description="Filter by state: OPEN/MANAGING/CLOSING/CLOSED")
) -> dict[str, Any]:
    """Open positions across all instances. Filterable by state."""
    if state:
        rows = _safe_query(
            "SELECT position_id, instance_name, letf_ticker, underlying_ticker, "
            "state, opened_at, closed_at, expiration_date, "
            "short_put_strike, long_put_strike, long_call_strike, contracts, "
            "entry_short_put_mid, entry_long_put_mid, entry_long_call_mid, "
            "entry_put_spread_credit, entry_long_call_cost, entry_net_cost, "
            "defined_max_loss, realized_pnl, close_trigger_id "
            "FROM tsunami_paper_positions WHERE state = %s "
            "ORDER BY opened_at DESC LIMIT 200",
            (state.upper(),),
        )
    else:
        rows = _safe_query(
            "SELECT position_id, instance_name, letf_ticker, underlying_ticker, "
            "state, opened_at, closed_at, expiration_date, "
            "short_put_strike, long_put_strike, long_call_strike, contracts, "
            "entry_short_put_mid, entry_long_put_mid, entry_long_call_mid, "
            "entry_put_spread_credit, entry_long_call_cost, entry_net_cost, "
            "defined_max_loss, realized_pnl, close_trigger_id "
            "FROM tsunami_paper_positions "
            "WHERE state IN ('OPEN', 'MANAGING', 'CLOSING') "
            "ORDER BY opened_at DESC LIMIT 200"
        )

    positions = []
    for r in rows:
        positions.append({
            "position_id": r[0], "instance_name": r[1],
            "letf_ticker": r[2], "underlying_ticker": r[3],
            "state": r[4],
            "opened_at": r[5].isoformat() if r[5] else None,
            "closed_at": r[6].isoformat() if r[6] else None,
            "expiration_date": r[7].isoformat() if r[7] else None,
            "short_put_strike": float(r[8]) if r[8] is not None else None,
            "long_put_strike": float(r[9]) if r[9] is not None else None,
            "long_call_strike": float(r[10]) if r[10] is not None else None,
            "contracts": r[11],
            "entry_short_put_mid": float(r[12]) if r[12] is not None else None,
            "entry_long_put_mid": float(r[13]) if r[13] is not None else None,
            "entry_long_call_mid": float(r[14]) if r[14] is not None else None,
            "entry_put_spread_credit": float(r[15]) if r[15] is not None else None,
            "entry_long_call_cost": float(r[16]) if r[16] is not None else None,
            "entry_net_cost": float(r[17]) if r[17] is not None else None,
            "defined_max_loss": float(r[18]) if r[18] is not None else None,
            "realized_pnl": float(r[19]) if r[19] is not None else None,
            "close_trigger_id": r[20],
        })
    return {"positions": positions, "count": len(positions)}


@router.get("/positions/{position_id}")
def tsunami_position_detail(position_id: str) -> dict[str, Any]:
    """Single position with full audit chain replay."""
    pos_rows = _safe_query(
        "SELECT position_id, instance_name, state, opened_at, closed_at, "
        "short_put_strike, long_put_strike, long_call_strike, contracts, "
        "entry_net_cost, defined_max_loss, realized_pnl, close_trigger_id "
        "FROM tsunami_paper_positions WHERE position_id = %s",
        (position_id,),
    )
    if not pos_rows:
        raise HTTPException(status_code=404, detail="position not found")
    p = pos_rows[0]
    position = {
        "position_id": p[0], "instance_name": p[1], "state": p[2],
        "opened_at": p[3].isoformat() if p[3] else None,
        "closed_at": p[4].isoformat() if p[4] else None,
        "short_put_strike": float(p[5]) if p[5] is not None else None,
        "long_put_strike": float(p[6]) if p[6] is not None else None,
        "long_call_strike": float(p[7]) if p[7] is not None else None,
        "contracts": p[8],
        "entry_net_cost": float(p[9]) if p[9] is not None else None,
        "defined_max_loss": float(p[10]) if p[10] is not None else None,
        "realized_pnl": float(p[11]) if p[11] is not None else None,
        "close_trigger_id": p[12],
    }

    audit_rows = _safe_query(
        "SELECT id, timestamp, event_type, data FROM tsunami_trade_audit "
        "WHERE position_id = %s ORDER BY timestamp ASC",
        (position_id,),
    )
    audit_chain = []
    for a in audit_rows:
        data = a[3] if isinstance(a[3], dict) else (json.loads(a[3]) if a[3] else {})
        audit_chain.append({
            "id": a[0],
            "timestamp": a[1].isoformat() if a[1] else None,
            "event_type": a[2], "data": data,
        })
    return {"position": position, "audit_chain": audit_chain}


# ---- Equity curves -------------------------------------------------------

@router.get("/equity-curve")
def tsunami_equity_curve(
    scope: str = Query("PLATFORM", description="PLATFORM or INSTANCE"),
    instance: Optional[str] = Query(None, description="Required when scope=INSTANCE"),
    days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Historical equity curve. Reads from tsunami_equity_snapshots.

    Returns one point per snapshot in the window. Empty list when no
    snapshots exist yet (paper trading just started).
    """
    scope = scope.upper()
    if scope not in ("PLATFORM", "INSTANCE"):
        raise HTTPException(status_code=400, detail="scope must be PLATFORM or INSTANCE")
    if scope == "INSTANCE" and not instance:
        raise HTTPException(status_code=400, detail="instance required when scope=INSTANCE")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if scope == "PLATFORM":
        rows = _safe_query(
            "SELECT snapshot_at, starting_capital, cumulative_realized_pnl, "
            "unrealized_pnl, open_position_count, equity "
            "FROM tsunami_equity_snapshots "
            "WHERE scope = 'PLATFORM' AND snapshot_at >= %s "
            "ORDER BY snapshot_at ASC",
            (cutoff,),
        )
    else:
        rows = _safe_query(
            "SELECT snapshot_at, starting_capital, cumulative_realized_pnl, "
            "unrealized_pnl, open_position_count, equity "
            "FROM tsunami_equity_snapshots "
            "WHERE scope = 'INSTANCE' AND instance_name = %s "
            "AND snapshot_at >= %s ORDER BY snapshot_at ASC",
            (instance, cutoff),
        )

    points = [
        {
            "snapshot_at": r[0].isoformat() if r[0] else None,
            "starting_capital": float(r[1]) if r[1] is not None else None,
            "cumulative_realized_pnl": float(r[2]) if r[2] is not None else 0.0,
            "unrealized_pnl": float(r[3]) if r[3] is not None else 0.0,
            "open_position_count": r[4] or 0,
            "equity": float(r[5]) if r[5] is not None else None,
        }
        for r in rows
    ]
    return {
        "scope": scope, "instance": instance, "days": days,
        "points": points, "count": len(points),
    }


@router.get("/equity-curve/intraday")
def tsunami_equity_curve_intraday(
    scope: str = Query("PLATFORM"),
    instance: Optional[str] = Query(None),
) -> dict[str, Any]:
    """Today's equity snapshots. UTC-day window.

    Per AlphaGEX bot-completeness rule: intraday charts must always have
    at least 2 points. If only one snapshot exists today, falls back to
    the most recent snapshot from yesterday so a line can still be drawn.
    """
    scope = scope.upper()
    if scope not in ("PLATFORM", "INSTANCE"):
        raise HTTPException(status_code=400, detail="scope must be PLATFORM or INSTANCE")
    if scope == "INSTANCE" and not instance:
        raise HTTPException(status_code=400, detail="instance required when scope=INSTANCE")

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if scope == "PLATFORM":
        rows = _safe_query(
            "SELECT snapshot_at, equity, unrealized_pnl, open_position_count "
            "FROM tsunami_equity_snapshots WHERE scope = 'PLATFORM' "
            "AND snapshot_at >= %s ORDER BY snapshot_at ASC",
            (today_start,),
        )
        prior_rows = _safe_query(
            "SELECT snapshot_at, equity, unrealized_pnl, open_position_count "
            "FROM tsunami_equity_snapshots WHERE scope = 'PLATFORM' "
            "AND snapshot_at < %s ORDER BY snapshot_at DESC LIMIT 1",
            (today_start,),
        ) if len(rows) < 2 else []
    else:
        rows = _safe_query(
            "SELECT snapshot_at, equity, unrealized_pnl, open_position_count "
            "FROM tsunami_equity_snapshots WHERE scope = 'INSTANCE' "
            "AND instance_name = %s AND snapshot_at >= %s "
            "ORDER BY snapshot_at ASC",
            (instance, today_start),
        )
        prior_rows = _safe_query(
            "SELECT snapshot_at, equity, unrealized_pnl, open_position_count "
            "FROM tsunami_equity_snapshots WHERE scope = 'INSTANCE' "
            "AND instance_name = %s AND snapshot_at < %s "
            "ORDER BY snapshot_at DESC LIMIT 1",
            (instance, today_start),
        ) if len(rows) < 2 else []

    combined = list(prior_rows) + list(rows)
    points = [
        {
            "snapshot_at": r[0].isoformat() if r[0] else None,
            "equity": float(r[1]) if r[1] is not None else None,
            "unrealized_pnl": float(r[2]) if r[2] is not None else 0.0,
            "open_position_count": r[3] or 0,
        }
        for r in combined
    ]
    return {
        "scope": scope, "instance": instance,
        "points": points, "count": len(points),
        "fallback_used": bool(prior_rows),
    }


# ---- Performance ---------------------------------------------------------

@router.get("/performance")
def tsunami_performance(
    instance: Optional[str] = Query(None, description="Filter to one instance"),
    days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Win rate, P&L stats per instance. Computed from closed positions."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if instance:
        rows = _safe_query(
            "SELECT instance_name, realized_pnl, close_trigger_id "
            "FROM tsunami_paper_positions "
            "WHERE state = 'CLOSED' AND closed_at >= %s "
            "AND instance_name = %s",
            (cutoff, instance),
        )
    else:
        rows = _safe_query(
            "SELECT instance_name, realized_pnl, close_trigger_id "
            "FROM tsunami_paper_positions "
            "WHERE state = 'CLOSED' AND closed_at >= %s",
            (cutoff,),
        )

    by_instance: dict[str, dict[str, Any]] = {}
    for cfg in _INSTANCES:
        if instance and cfg["name"] != instance:
            continue
        by_instance[cfg["name"]] = {
            "instance_name": cfg["name"],
            "trades": 0, "wins": 0, "losses": 0, "scratches": 0,
            "total_pnl": 0.0, "avg_pnl": 0.0, "best": 0.0, "worst": 0.0,
            "win_rate": None,
            "trigger_breakdown": {},
        }

    for name, pnl, trig in rows:
        bucket = by_instance.setdefault(name, {
            "instance_name": name,
            "trades": 0, "wins": 0, "losses": 0, "scratches": 0,
            "total_pnl": 0.0, "avg_pnl": 0.0, "best": 0.0, "worst": 0.0,
            "win_rate": None, "trigger_breakdown": {},
        })
        pnl_f = float(pnl) if pnl is not None else 0.0
        bucket["trades"] += 1
        bucket["total_pnl"] += pnl_f
        if pnl_f > 0:
            bucket["wins"] += 1
        elif pnl_f < 0:
            bucket["losses"] += 1
        else:
            bucket["scratches"] += 1
        bucket["best"] = max(bucket["best"], pnl_f)
        bucket["worst"] = min(bucket["worst"], pnl_f)
        if trig:
            bucket["trigger_breakdown"][trig] = bucket["trigger_breakdown"].get(trig, 0) + 1

    for bucket in by_instance.values():
        if bucket["trades"]:
            bucket["avg_pnl"] = bucket["total_pnl"] / bucket["trades"]
            decided = bucket["wins"] + bucket["losses"]
            bucket["win_rate"] = (bucket["wins"] / decided) if decided else None

    platform_total = sum(b["total_pnl"] for b in by_instance.values())
    platform_trades = sum(b["trades"] for b in by_instance.values())
    platform_wins = sum(b["wins"] for b in by_instance.values())
    platform_losses = sum(b["losses"] for b in by_instance.values())
    platform_decided = platform_wins + platform_losses
    return {
        "days": days,
        "instance_filter": instance,
        "platform": {
            "trades": platform_trades,
            "total_pnl": platform_total,
            "win_rate": (platform_wins / platform_decided) if platform_decided else None,
            "avg_pnl": (platform_total / platform_trades) if platform_trades else 0.0,
        },
        "instances": list(by_instance.values()),
    }


# ---- Diagnostics: gate failures / scan activity / logs -------------------

@router.get("/gate-failures")
def tsunami_gate_failures(
    letf: Optional[str] = Query(None, description="Filter to one LETF ticker"),
    gate: Optional[str] = Query(None, description="Filter to one gate id (G01..G10)"),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Recent gate failures for diagnostic review (master spec section 9.3)."""
    where, params = ["1=1"], []
    if letf:
        where.append("letf_ticker = %s"); params.append(letf.upper())
    if gate:
        where.append("failed_gate = %s"); params.append(gate.upper())
    sql = (
        "SELECT id, timestamp, letf_ticker, underlying_ticker, failed_gate, "
        "failure_outcome, gates_passed_before_failure, attempted_structure, "
        "failure_reason, context FROM tsunami_gate_failures "
        f"WHERE {' AND '.join(where)} ORDER BY timestamp DESC LIMIT %s"
    )
    params.append(limit)
    rows = _safe_query(sql, tuple(params))
    failures = []
    for r in rows:
        gp = r[6] if isinstance(r[6], (list, dict)) else (json.loads(r[6]) if r[6] else [])
        struct = r[7] if isinstance(r[7], (list, dict)) else (json.loads(r[7]) if r[7] else None)
        ctx = r[9] if isinstance(r[9], (list, dict)) else (json.loads(r[9]) if r[9] else {})
        failures.append({
            "id": r[0],
            "timestamp": r[1].isoformat() if r[1] else None,
            "letf_ticker": r[2], "underlying_ticker": r[3],
            "failed_gate": r[4], "failure_outcome": r[5],
            "gates_passed_before_failure": gp,
            "attempted_structure": struct,
            "failure_reason": r[8], "context": ctx,
        })
    return {"failures": failures, "count": len(failures)}


@router.get("/scan-activity")
def tsunami_scan_activity(
    instance: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Recent entry/management cycle events from the audit log.

    Surfaces ENTRY_EVAL + MANAGEMENT_EVAL rows so the dashboard can render
    a 'what did the bot just look at?' feed even when no trades fire.
    """
    if instance:
        rows = _safe_query(
            "SELECT id, timestamp, instance, event_type, position_id, data "
            "FROM tsunami_trade_audit "
            "WHERE instance = %s AND event_type IN ('ENTRY_EVAL', 'MANAGEMENT_EVAL') "
            "ORDER BY timestamp DESC LIMIT %s",
            (instance, limit),
        )
    else:
        rows = _safe_query(
            "SELECT id, timestamp, instance, event_type, position_id, data "
            "FROM tsunami_trade_audit "
            "WHERE event_type IN ('ENTRY_EVAL', 'MANAGEMENT_EVAL') "
            "ORDER BY timestamp DESC LIMIT %s",
            (limit,),
        )
    events = []
    for r in rows:
        data = r[5] if isinstance(r[5], dict) else (json.loads(r[5]) if r[5] else {})
        events.append({
            "id": r[0],
            "timestamp": r[1].isoformat() if r[1] else None,
            "instance": r[2], "event_type": r[3],
            "position_id": r[4], "data": data,
        })
    return {"events": events, "count": len(events)}


@router.get("/logs")
def tsunami_logs(
    event_type: Optional[str] = Query(None,
        description="ENTRY_EVAL, ENTRY_FILLED, MANAGEMENT_EVAL, EXIT_FILLED"),
    instance: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    """Activity log feed across all event types."""
    where, params = ["1=1"], []
    if event_type:
        where.append("event_type = %s"); params.append(event_type.upper())
    if instance:
        where.append("instance = %s"); params.append(instance)
    sql = (
        "SELECT id, timestamp, instance, event_type, position_id, data "
        "FROM tsunami_trade_audit "
        f"WHERE {' AND '.join(where)} ORDER BY timestamp DESC LIMIT %s"
    )
    params.append(limit)
    rows = _safe_query(sql, tuple(params))
    entries = []
    for r in rows:
        data = r[5] if isinstance(r[5], dict) else (json.loads(r[5]) if r[5] else {})
        entries.append({
            "id": r[0],
            "timestamp": r[1].isoformat() if r[1] else None,
            "instance": r[2], "event_type": r[3],
            "position_id": r[4], "data": data,
        })
    return {"entries": entries, "count": len(entries)}


# ---- Config / calibration / kill-state -----------------------------------

# Phase 1.5 calibration values (single source of truth = backend.bots.tsunami.models
# defaults; mirrored here so the API service doesn't need to import the
# trading package). Update both places in lockstep.
_CALIBRATION = {
    "wall_concentration_threshold": {
        "value": 2.0, "spec_default": 2.0,
        "tag": "CALIB-SANITY-OK",
        "notes": "Real-data 90d pull confirmed 2.0x median is a tight-but-fireable threshold across all 5 pairs.",
    },
    "tracking_error_fudge": {
        "value": 0.1, "spec_default": 0.1,
        "tag": "CALIB-OK",
        "notes": "TE band of L*sigma*sqrt(t)*sqrt(2/3)*0.1 brackets observed LETF tracking variance for 4/5 pairs.",
    },
    "drag_coefficient": {
        "value": 1.0, "spec_default": 1.0,
        "tag": "CALIB-BLOCK",
        "notes": (
            "Theoretical drag formula misspecified during trending markets "
            "(positive autocorrelation reduces drag). v0.3 backlog: "
            "V03-DRAG-AUTOCORR replace formula with autocorr-aware estimator. "
            "Current 1.0 is conservative for paper-trading."
        ),
    },
    "realized_vol_window_days": {
        "value": 20, "spec_default": 30,
        "tag": "CALIB-ADJUST",
        "notes": (
            "20d window beat 30d on 4/5 pairs in residual-SD comparison. "
            "MSTU preferred 30d but margin was inside known vol_window.py "
            "math-bug noise floor (tracked under V03-DRAG-AUTOCORR)."
        ),
    },
}


@router.get("/calibration")
def tsunami_calibration() -> dict[str, Any]:
    """Current Phase 1.5 calibration values + decision tags.

    Static snapshot of the defaults baked into backend.bots.tsunami.models.
    Updated whenever a calibration re-run lands a new spec default.
    """
    return {
        "phase": "1.5",
        "last_calibrated": "2026-04-30",   # date of step 9 real-data pull
        "parameters": _CALIBRATION,
    }


@router.get("/kill-state")
def tsunami_kill_state() -> dict[str, Any]:
    """Active and historical kill switches.

    Active rows = scope-level kill in effect right now. Recent history
    (cleared rows from the last 30d) is included so the dashboard can
    show 'this instance was killed yesterday for T7' context.
    """
    active_rows = _safe_query(
        "SELECT scope, instance_name, trigger_id, reason, context, killed_at "
        "FROM tsunami_kill_state WHERE active = TRUE "
        "ORDER BY killed_at DESC"
    )
    history_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    history_rows = _safe_query(
        "SELECT scope, instance_name, trigger_id, reason, killed_at, "
        "cleared_at, cleared_by FROM tsunami_kill_state "
        "WHERE active = FALSE AND cleared_at >= %s "
        "ORDER BY cleared_at DESC LIMIT 50",
        (history_cutoff,),
    )

    active = []
    for r in active_rows:
        ctx = r[4] if isinstance(r[4], dict) else (json.loads(r[4]) if r[4] else {})
        active.append({
            "scope": r[0], "instance_name": r[1],
            "trigger_id": r[2], "reason": r[3], "context": ctx,
            "killed_at": r[5].isoformat() if r[5] else None,
        })
    history = [
        {
            "scope": r[0], "instance_name": r[1],
            "trigger_id": r[2], "reason": r[3],
            "killed_at": r[4].isoformat() if r[4] else None,
            "cleared_at": r[5].isoformat() if r[5] else None,
            "cleared_by": r[6],
        }
        for r in history_rows
    ]
    return {
        "active": active, "active_count": len(active),
        "platform_killed": any(a["scope"] == "PLATFORM" for a in active),
        "killed_instances": [a["instance_name"] for a in active if a["scope"] == "INSTANCE"],
        "history": history,
    }


@router.get("/config")
def tsunami_config() -> dict[str, Any]:
    """Current TsunamiConfig defaults + global platform settings.

    Mirrors backend.bots.tsunami.models.TsunamiConfig + global_config.GlobalConfig.
    Read-only -- mutations go through the CLI (master spec section 4-6).
    """
    return {
        "global": {
            "account_capital": _ACCOUNT_CAPITAL,
            "platform_cap": _PLATFORM_CAP,
            "max_concurrent_positions": 3,
            "paper_only": True,
            "bot_guard_tag_prefix": "TSUNAMI",
        },
        "instance_defaults": {
            "leverage": 2.0,
            "wall_concentration_threshold": 2.0,
            "tracking_error_fudge": 0.1,
            "drag_coefficient": 1.0,
            "realized_vol_window_days": 20,
        },
        "instances": _INSTANCES,
        "phase": "1.5",
    }


# ---- Admin: one-shot cycle trigger ---------------------------------------
#
# Per master spec the entry cycle fires Monday 10:30 ET on alphagex-trader.
# When a deploy lands mid-week (or the prior Monday's cycle aborted before
# completing all 5 instances) we need a way to re-run the cycle on demand
# without waiting until next Monday. This admin endpoint runs the same
# Runner the trader uses, in-process on alphagex-api, against the live DB.
# Paper-only by configuration; no live broker calls are possible because
# every InstanceConfig has paper_only=True.
@router.post("/admin/run-entry-cycle")
def admin_run_entry_cycle() -> dict[str, Any]:
    """Run one TSUNAMI entry cycle synchronously and return the summary.

    Same wiring as scheduler/tsunami_scheduler.py: Tradier snapshot fetcher
    + paper broker executor. Calls every non-killed instance once.
    """
    try:
        from backend.bots.tsunami.broker.paper_executor import paper_broker_executor
        from backend.bots.tsunami.data.tradier_snapshot import build_market_snapshot
        from backend.bots.tsunami.engine import TsunamiEngine, PlatformContext as PC
        from backend.bots.tsunami.main import Runner
    except ImportError as exc:
        logger.exception("[tsunami admin] import failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"tsunami import failed: {exc!r}")

    def _platform_fetcher(instances) -> "PC":
        total_count = sum(inst.open_count for inst in instances.values())
        total_dollars = sum(inst.open_dollars_at_risk() for inst in instances.values())
        return PC(open_position_count=total_count, open_dollars_at_risk=total_dollars)

    runner = Runner(
        engine=TsunamiEngine(),
        snapshot_fetcher=build_market_snapshot,
        platform_fetcher=_platform_fetcher,
        broker_executor=paper_broker_executor,
        dry_run=False,
    )
    cycle = runner.run_entry_cycle()
    return {
        "instances_evaluated": cycle.instances_evaluated,
        "entries_approved": cycle.entries_approved,
        "entries_filled": cycle.entries_filled,
        "skips": cycle.skips,
    }


@router.post("/admin/run-management-cycle")
def admin_run_management_cycle() -> dict[str, Any]:
    """Run one TSUNAMI management cycle synchronously and return the summary.

    Mirrors admin_run_entry_cycle but evaluates triggers on open positions
    rather than evaluating new entries.
    """
    try:
        from backend.bots.tsunami.broker.paper_executor import paper_broker_executor
        from backend.bots.tsunami.data.tradier_snapshot import build_market_snapshot
        from backend.bots.tsunami.engine import TsunamiEngine, PlatformContext as PC
        from backend.bots.tsunami.main import Runner
    except ImportError as exc:
        logger.exception("[tsunami admin] import failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"tsunami import failed: {exc!r}")

    def _platform_fetcher(instances) -> "PC":
        total_count = sum(inst.open_count for inst in instances.values())
        total_dollars = sum(inst.open_dollars_at_risk() for inst in instances.values())
        return PC(open_position_count=total_count, open_dollars_at_risk=total_dollars)

    runner = Runner(
        engine=TsunamiEngine(),
        snapshot_fetcher=build_market_snapshot,
        platform_fetcher=_platform_fetcher,
        broker_executor=paper_broker_executor,
        dry_run=False,
    )
    cycle = runner.run_management_cycle()
    return {
        "instances_evaluated": cycle.instances_evaluated,
        "triggers_fired": cycle.triggers_fired,
        "skips": cycle.skips,
    }


# ---- TSUNAMI-TREND (LETF trend engine, 2026-07-03) -------------------------

@router.get("/trend/status")
def tsunami_trend_status() -> dict[str, Any]:
    """Book, cash, P&L, and last trades for the LETF trend engine.

    2026-07-08: equity/book used to mark held shares at avg_cost (their
    entry price), not the current quote -- so unrealized P&L on open
    positions was invisible (always $0) and the page had no today/total
    realized P&L fields at all, unlike every other bot's /status. Marks
    now come from a live Tradier quote per held name (same source
    trend_engine.run_rebalance/mark_intraday_equity use), matching the
    other bots' "equity = cash + mark-to-market book" convention.
    """
    from backend.bots.tsunami.data import tradier_client

    book_rows = _safe_query(
        "SELECT letf, shares, avg_cost, updated_at FROM tsunami_trend_book"
        " WHERE shares > 0 ORDER BY letf")
    cash_rows = _safe_query("SELECT cash FROM tsunami_trend_cash WHERE id=1")
    trades = _safe_query(
        "SELECT ts, letf, side, shares, price, reason, realized_pnl"
        " FROM tsunami_trend_trades ORDER BY ts DESC LIMIT 25")
    realized_total_rows = _safe_query(
        "SELECT COALESCE(SUM(realized_pnl), 0) FROM tsunami_trend_trades"
        " WHERE realized_pnl IS NOT NULL")
    # "Today" in CT, matching the platform convention (routes_bots.py) --
    # realized P&L from SELL fills that closed during today's CT session.
    today_realized_rows = _safe_query(
        "SELECT COALESCE(SUM(realized_pnl), 0) FROM tsunami_trend_trades"
        " WHERE realized_pnl IS NOT NULL"
        " AND (ts AT TIME ZONE 'America/Chicago')::date"
        "     = (NOW() AT TIME ZONE 'America/Chicago')::date")

    # Never read the latest PLATFORM snapshot for equity/cash: that table
    # still holds the OLD options-engine snapshots (starting_capital
    # $5,000), which made the page show "$5,000 account equity" while the
    # trend engine actually runs on $500 (START_CASH). Operator 2026-07-04:
    # TSUNAMI uses $500, full stop.
    _cash = float(cash_rows[0][0]) if cash_rows else None

    book_out, market_value, cost_basis = [], 0.0, 0.0
    for letf, shares, avg_cost, updated_at in book_rows:
        shares = int(shares)
        avg_cost = float(avg_cost)
        quote = tradier_client.get_quote(letf)
        last = float((quote or {}).get("last") or (quote or {}).get("close") or 0) or avg_cost
        market_value += shares * last
        cost_basis += shares * avg_cost
        book_out.append({
            "letf": letf, "shares": shares, "avg_cost": avg_cost,
            "last": round(last, 4), "unrealized_pnl": round(shares * (last - avg_cost), 2),
            "updated_at": str(updated_at),
        })

    equity = round(_cash + market_value, 2) if _cash is not None else None
    return {
        "engine": "TSUNAMI-TREND (LETF vol-managed MA50)",
        "cash": _cash,
        "equity": equity,
        "starting_capital": 500.0,
        "unrealized_pnl": round(market_value - cost_basis, 2),
        "today_pnl": float(today_realized_rows[0][0]) if today_realized_rows else 0.0,
        "realized_pnl": float(realized_total_rows[0][0]) if realized_total_rows else 0.0,
        "book": book_out,
        "recent_trades": [{"ts": str(r[0]), "letf": r[1], "side": r[2],
                           "shares": int(r[3]), "price": float(r[4]), "reason": r[5],
                           "realized_pnl": float(r[6]) if r[6] is not None else None}
                          for r in trades],
    }


@router.get("/trend/universe")
def tsunami_trend_universe() -> dict[str, Any]:
    """All 16 instruments in the universe with the latest signal state --
    not just currently-held names. Answers "why isn't X being bought":
    trending Y/N, price vs its own 50d MA, target vs held shares, and the
    reason text from the most recent rebalance cycle. Backed by
    tsunami_trend_signals, written once per instrument per cycle
    regardless of outcome (added 2026-07-08 -- before this there was no
    persisted record of the universe beyond currently-held names)."""
    from backend.bots.tsunami.trend_engine import PAIRS

    rows = _safe_query(
        "SELECT DISTINCT ON (letf) letf, ts, price, ma50, rv20, trending,"
        " target_weight, target_shares, held_shares, action, reason"
        " FROM tsunami_trend_signals ORDER BY letf, ts DESC")
    by_letf = {r[0]: r for r in rows}
    out = []
    for _, letf in PAIRS:
        r = by_letf.get(letf)
        if r is None:
            out.append({
                "letf": letf, "ts": None, "price": None, "ma50": None, "rv20": None,
                "trending": None, "target_weight": None, "target_shares": None,
                "held_shares": None, "action": None, "reason": "no rebalance cycle yet",
            })
            continue
        out.append({
            "letf": r[0], "ts": str(r[1]),
            "price": float(r[2]) if r[2] is not None else None,
            "ma50": float(r[3]) if r[3] is not None else None,
            "rv20": float(r[4]) if r[4] is not None else None,
            "trending": r[5],
            "target_weight": float(r[6]) if r[6] is not None else None,
            "target_shares": r[7], "held_shares": r[8],
            "action": r[9], "reason": r[10],
        })
    return {"instruments": out}


@router.get("/trend/trades")
def tsunami_trend_trades(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    """Full trade history (the /trend/status embed is capped at 25 for the
    KPI page; this is the dedicated Trade History tab's data source)."""
    rows = _safe_query(
        "SELECT ts, letf, side, shares, price, reason, realized_pnl"
        " FROM tsunami_trend_trades ORDER BY ts DESC LIMIT %s", (limit,))
    return {
        "trades": [{"ts": str(r[0]), "letf": r[1], "side": r[2],
                    "shares": int(r[3]), "price": float(r[4]), "reason": r[5],
                    "realized_pnl": float(r[6]) if r[6] is not None else None}
                   for r in rows],
    }


@router.get("/trend/logs")
def tsunami_trend_logs(limit: int = Query(300, ge=1, le=2000)) -> dict[str, Any]:
    """Chronological feed of every per-instrument decision each rebalance
    cycle made (BUY/SELL/HOLD/FLAT/NO_SIGNAL/NO_QUOTE) -- the Logs tab."""
    rows = _safe_query(
        "SELECT ts, letf, action, reason, price, target_shares, held_shares"
        " FROM tsunami_trend_signals ORDER BY ts DESC LIMIT %s", (limit,))
    return {
        "logs": [{"ts": str(r[0]), "letf": r[1], "action": r[2], "reason": r[3],
                  "price": float(r[4]) if r[4] is not None else None,
                  "target_shares": r[5], "held_shares": r[6]}
                 for r in rows],
    }


@router.get("/trend/equity-curve")
def tsunami_trend_equity_curve() -> dict[str, Any]:
    """TREND-engine equity history for the page's equity chart. Filters to the trend engine's own
    snapshots (starting_capital = $500) so the retired options-engine rows ($5,000 era, same
    PLATFORM scope) can't pollute the curve. One point per snapshot, oldest first."""
    rows = _safe_query(
        "SELECT snapshot_at, equity FROM tsunami_equity_snapshots"
        " WHERE scope='PLATFORM' AND starting_capital=500"
        " ORDER BY snapshot_at ASC")
    return {
        "start_cash": 500.0,
        "points": [{"date": str(r[0])[:10], "ts": str(r[0]), "equity": float(r[1])}
                   for r in rows or []],
    }


@router.post("/admin/trend-rebalance")
def admin_trend_rebalance() -> dict[str, Any]:
    """Manually trigger one TSUNAMI-TREND rebalance cycle (paper)."""
    try:
        from backend.bots.tsunami.trend_engine import ensure_trend_tables, run_rebalance
        ensure_trend_tables()
        return {"status": "ok", **{k: v for k, v in run_rebalance().items()}}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"trend rebalance failed: {exc!r}")


_cmp_cache: dict[str, Any] = {"ts": 0.0, "data": None}


@router.get("/trend/comparison")
def tsunami_trend_comparison(days: int = 180) -> dict[str, Any]:
    """Time-series comparison: TSUNAMI equity vs each instrument, indexed to 100.

    Feeds the dashboard's comparison chart (replaces the options-era
    structures chart). Instrument closes come from Tradier daily history;
    the TSUNAMI line from tsunami_equity_snapshots. 10-minute cache —
    11 Tradier calls per refresh otherwise.
    """
    import time as _time
    if _cmp_cache["data"] is not None and _time.time() - _cmp_cache["ts"] < 600:
        return _cmp_cache["data"]

    from backend.bots.tsunami.data import tradier_client
    from backend.bots.tsunami.trend_engine import PAIRS, START_CASH

    days = max(30, min(days, 400))
    series: dict[str, dict[str, float]] = {}
    for _, letf in PAIRS:
        hist = tradier_client.get_daily_history(letf, days=days)
        if not hist:
            continue
        base = float(hist[0]["close"])
        if base <= 0:
            continue
        series[letf] = {str(h["date"]): round(100.0 * float(h["close"]) / base, 2)
                        for h in hist if h.get("close")}

    eq_rows = _safe_query(
        "SELECT snapshot_at::date, MAX(equity) FROM tsunami_equity_snapshots"
        " WHERE scope='PLATFORM' GROUP BY 1 ORDER BY 1")
    tsunami = {str(r[0]): round(100.0 * float(r[1]) / START_CASH, 2) for r in eq_rows}

    all_dates = sorted(set().union(tsunami.keys(), *[s.keys() for s in series.values()]))
    points = []
    for d in all_dates:
        row: dict[str, Any] = {"date": d}
        if d in tsunami:
            row["TSUNAMI"] = tsunami[d]
        for letf, s in series.items():
            if d in s:
                row[letf] = s[d]
        points.append(row)

    book = _safe_query("SELECT letf, shares FROM tsunami_trend_book WHERE shares > 0")
    data = {
        "tickers": [l for _, l in PAIRS],
        "inverse": ["SBIT", "ETHD", "SMST", "SPXS", "SQQQ"],
        "held": [r[0] for r in book],
        "points": points,
    }
    _cmp_cache.update(ts=_time.time(), data=data)
    return data
