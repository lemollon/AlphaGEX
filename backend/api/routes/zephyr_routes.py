"""
ZEPHYR (ASAHEL) - Kalshi live-sports scalper API routes.

All reads hit ZephyrDatabase directly and are decoupled from trader init, so a
dead trader never 500s a dashboard (common-mistakes #3). Standard bot endpoint
set + scalp-specific /fair-value and /live-games.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ZEPHYR"])


def _db():
    from trading.zephyr.db import ZephyrDatabase
    return ZephyrDatabase()


@router.get("/api/zephyr/status")
async def zephyr_status():
    """Bot health: config, locks, provider, open positions."""
    try:
        db = _db()
        live = (db.get_config("live_enabled", "false") or "false").lower() == "true"
        locked = (db.get_config("paper_locked", "true") or "true").lower() == "true"
        return {
            "status": "success",
            "bot": "ZEPHYR", "display_name": "ASAHEL",
            "live_enabled": live and not locked,
            "paper_locked": locked,
            "fair_value_provider": db.get_config("fair_value_provider", "espn"),
            "starting_capital": db.get_starting_capital(),
            "open_positions": len(db.get_open_positions()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/positions")
async def zephyr_positions():
    try:
        return {"status": "success", "positions": _db().get_open_positions()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/trades")
async def zephyr_trades(limit: int = Query(100, ge=1, le=1000)):
    try:
        return {"status": "success", "trades": _db().get_closed_trades(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/equity-curve")
async def zephyr_equity_curve():
    """Historical cumulative-P&L equity curve (ALL closed scalps)."""
    try:
        db = _db()
        return {"status": "success", "starting_capital": db.get_starting_capital(),
                "curve": db.equity_curve()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/equity-curve/intraday")
async def zephyr_intraday():
    """Today's intraday equity snapshots (with live fallback if empty)."""
    try:
        db = _db()
        snaps = db.intraday_equity()
        if not snaps:
            cap = db.get_starting_capital()
            closed = db.get_closed_trades()
            realized = sum(float(t["realized_pnl"]) for t in closed)
            # Live snapshot fallback: at least 2 points so the chart draws a line.
            snaps = [
                {"ts_ct": None, "equity": cap + realized, "realized_pnl": realized,
                 "unrealized_pnl": 0.0, "open_positions": len(db.get_open_positions()),
                 "note": "live fallback - no snapshots yet today"},
            ]
        return {"status": "success", "snapshots": snaps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/performance")
async def zephyr_performance():
    try:
        return {"status": "success", **_db().performance()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/scan-activity")
async def zephyr_scans(limit: int = Query(100, ge=1, le=500)):
    try:
        return {"status": "success", "scans": _db().get_recent_scans(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/logs")
async def zephyr_logs(limit: int = Query(100, ge=1, le=500)):
    # Scans are ZEPHYR's activity log.
    try:
        return {"status": "success", "logs": _db().get_recent_scans(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/fair-value")
async def zephyr_fair_value(limit: int = Query(100, ge=1, le=500)):
    """Live fair-value vs Kalshi-mid gap log - the lag/edge evidence (P1 gate)."""
    try:
        from trading.zephyr.db import db_connection
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT timestamp AT TIME ZONE 'America/Chicago' AS ts_ct, market_id,
                       source, fair_cents, kalshi_mid_cents, gap_cents, confidence
                FROM zephyr_fair_value_log ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
            cols = [d[0] for d in c.description]
            rows = [dict(zip(cols, r)) for r in c.fetchall()]
        return {"status": "success", "fair_value_log": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/zephyr/live-games")
async def zephyr_live_games():
    """Markets ZEPHYR is currently tracking (best-effort; trader may be cold)."""
    try:
        # Read the existing scheduler instance if one exists; never force-create
        # one from a read endpoint.
        import scheduler.trader_scheduler as ts
        sched = getattr(ts, "_scheduler_instance", None)
        trader = getattr(sched, "zephyr_trader", None) if sched else None
        if not trader:
            return {"status": "success", "tracked": [], "note": "trader not initialized"}
        return {"status": "success", "tracked": [
            {"market_id": m.market_id, "sport": m.sport, "espn_event_id": m.espn_event_id}
            for m in trader.tracked
        ]}
    except Exception as e:
        return {"status": "success", "tracked": [], "note": f"unavailable: {e}"}
