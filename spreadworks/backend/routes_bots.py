"""SpreadWorks bot API routes: /api/spreadworks/bots/{bot}/*"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .bots.db import bot_table, load_config
from .bots.executor import account_equity, list_open_positions
from .bots.registry import BOT_REGISTRY, list_bots
from .db import engine as _global_engine

logger = logging.getLogger("spreadworks.routes_bots")
router = APIRouter(prefix="/api/spreadworks/bots", tags=["SpreadWorks Bots"])

# Tests override this via monkeypatch
ENGINE: Engine = _global_engine
CT = ZoneInfo("America/Chicago")


def _validate(bot: str) -> None:
    if bot not in BOT_REGISTRY:
        raise HTTPException(404, f"Unknown bot: {bot}")


@router.get("/{bot}/status")
def get_status(bot: str):
    _validate(bot)
    cfg = load_config(ENGINE, bot)
    opens = list_open_positions(ENGINE, bot)
    equity = account_equity(ENGINE, bot)
    with ENGINE.begin() as conn:
        last = conn.execute(text(
            f"SELECT MAX(scan_time) AS s FROM {bot_table(bot, 'scan_activity')}"
        )).mappings().first()
    return {
        "bot": bot,
        "display": BOT_REGISTRY[bot]["display"],
        "strategy": BOT_REGISTRY[bot]["strategy"],
        "enabled": bool(cfg["enabled"]),
        "open_positions": len(opens),
        "equity": float(equity),
        "starting_capital": float(cfg["starting_capital"]),
        "last_scan_at": str(last["s"]) if last["s"] else None,
    }


@router.get("/{bot}/positions")
def get_positions(bot: str):
    _validate(bot)
    rows = list_open_positions(ENGINE, bot)
    for r in rows:
        r["legs"] = json.loads(r["legs"]) if isinstance(r["legs"], str) else r["legs"]
    return {"positions": rows}


@router.get("/{bot}/position-monitor")
def get_position_monitor(bot: str):
    return get_positions(bot)


@router.get("/{bot}/equity-curve")
def get_equity_curve(bot: str):
    _validate(bot)
    t = bot_table(bot, "closed_trades")
    cfg = load_config(ENGINE, bot)
    sc = float(cfg["starting_capital"])
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT close_time, realized_pnl FROM {t} ORDER BY close_time"
        )).mappings().all()
    curve = []
    cum = 0.0
    for r in rows:
        cum += float(r["realized_pnl"])
        curve.append({"time": str(r["close_time"]), "equity": sc + cum, "pnl": cum})
    return {"curve": curve, "starting_capital": sc}


@router.get("/{bot}/equity-curve/intraday")
def get_equity_intraday(bot: str):
    _validate(bot)
    t = bot_table(bot, "equity_snapshots")
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT snapshot_time, equity, unrealized_pnl, realized_pnl_today, "
            f"open_positions FROM {t} WHERE DATE(snapshot_time) = DATE(CURRENT_TIMESTAMP) "
            "ORDER BY snapshot_time"
        )).mappings().all()
    return {"snapshots": [dict(r) for r in rows]}


@router.get("/{bot}/trades")
def get_trades(bot: str, limit: int = 100):
    _validate(bot)
    t = bot_table(bot, "closed_trades")
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT * FROM {t} ORDER BY close_time DESC LIMIT :n"
        ), {"n": limit}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["legs"] = json.loads(d["legs"]) if isinstance(d["legs"], str) else d["legs"]
        out.append(d)
    return {"trades": out}


@router.get("/{bot}/performance")
def get_performance(bot: str):
    _validate(bot)
    t = bot_table(bot, "closed_trades")
    with ENGINE.begin() as conn:
        r = conn.execute(text(
            f"SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins, "
            "SUM(realized_pnl) AS total, "
            "AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) AS avg_win, "
            "AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) AS avg_loss "
            f"FROM {t}"
        )).mappings().first()
    n = int(r["n"] or 0)
    wins = int(r["wins"] or 0)
    return {
        "trades": n,
        "wins": wins,
        "win_rate": (wins / n) if n else 0,
        "total_pnl": float(r["total"] or 0),
        "avg_win": float(r["avg_win"] or 0),
        "avg_loss": float(r["avg_loss"] or 0),
    }


@router.get("/{bot}/daily-perf")
def get_daily_perf(bot: str, days: int = 30):
    _validate(bot)
    t = bot_table(bot, "closed_trades")
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT DATE(close_time) AS d, SUM(realized_pnl) AS pnl, COUNT(*) AS n "
            f"FROM {t} GROUP BY DATE(close_time) ORDER BY d DESC LIMIT :n"
        ), {"n": days}).mappings().all()
    return {"days": [dict(r) for r in rows]}


@router.get("/{bot}/config")
def get_config(bot: str):
    _validate(bot)
    return load_config(ENGINE, bot)


class ConfigUpdate(BaseModel):
    starting_capital: float | None = None
    enabled: bool | None = None
    max_contracts: int | None = None
    bp_pct: float | None = None
    sd_mult: float | None = None
    pt_pct: float | None = None
    sl_pct: float | None = None
    entry_start_ct: str | None = None
    entry_end_ct: str | None = None
    eod_close_ct: str | None = None
    discord_alerts: bool | None = None
    delta_skew: int | None = None
    use_gex_walls: bool | None = None


@router.post("/{bot}/config")
def post_config(bot: str, body: ConfigUpdate):
    _validate(bot)
    t = bot_table(bot, "config")
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not updates:
        return load_config(ENGINE, bot)
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["bot_id"] = 1
    with ENGINE.begin() as conn:
        conn.execute(text(
            f"UPDATE {t} SET {set_clause}, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = :bot_id"
        ), updates)
    return load_config(ENGINE, bot)


@router.post("/{bot}/toggle")
def post_toggle(bot: str):
    _validate(bot)
    t = bot_table(bot, "config")
    with ENGINE.begin() as conn:
        cur = conn.execute(text(f"SELECT enabled FROM {t} WHERE id=1")).scalar()
        new = not bool(cur)
        conn.execute(text(f"UPDATE {t} SET enabled = :e WHERE id=1"), {"e": new})
    return {"bot": bot, "enabled": new}


@router.post("/{bot}/force-trade")
def post_force_trade(bot: str):
    _validate(bot)
    # Trigger one immediate scan cycle bypassing the entry window check
    from .bots.scanner import run_scan_cycle
    from .bots.routes_helpers import build_live_chain_provider
    provider = build_live_chain_provider()
    now = datetime.now(CT)
    # Force window: temporarily widen the window by saving/restoring config
    cfg = load_config(ENGINE, bot)
    t = bot_table(bot, "config")
    with ENGINE.begin() as conn:
        conn.execute(text(
            f"UPDATE {t} SET entry_start_ct='00:00', entry_end_ct='23:59' WHERE id=1"
        ))
    try:
        result = run_scan_cycle(
            engine=ENGINE, bot=bot, now_ct=now,
            chain_provider=provider, event_blackout=False,
        )
    finally:
        with ENGINE.begin() as conn:
            conn.execute(text(
                f"UPDATE {t} SET entry_start_ct=:s, entry_end_ct=:e WHERE id=1"
            ), {"s": cfg["entry_start_ct"], "e": cfg["entry_end_ct"]})
    return result


@router.post("/{bot}/force-close")
def post_force_close(bot: str, position_id: str):
    _validate(bot)
    from .bots.executor import close_position, list_open_positions, compute_mtm
    from .bots.routes_helpers import build_live_chain_provider
    opens = list_open_positions(ENGINE, bot)
    pos = next((p for p in opens if p["position_id"] == position_id), None)
    if pos is None:
        raise HTTPException(404, f"No OPEN position {position_id}")
    provider = build_live_chain_provider()
    legs = json.loads(pos["legs"]) if isinstance(pos["legs"], str) else pos["legs"]
    mids = provider.get_leg_mids(ticker=pos["ticker"], legs=legs)
    mtm_value, _ = compute_mtm(
        strategy=pos["strategy"], legs=legs,
        entry_price=float(pos["entry_price"]),
        contracts=int(pos["contracts"]), leg_mids=mids,
    )
    realized = close_position(ENGINE, bot, position_id,
                              close_value=mtm_value, close_reason="FORCE",
                              now=datetime.now(CT))
    return {"position_id": position_id, "realized_pnl": realized}


@router.get("/{bot}/logs")
@router.get("/{bot}/scan-activity")
def get_scan_activity(bot: str, limit: int = 200):
    _validate(bot)
    t = bot_table(bot, "scan_activity")
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT * FROM {t} ORDER BY scan_time DESC LIMIT :n"
        ), {"n": limit}).mappings().all()
    return {"rows": [dict(r) for r in rows]}


@router.get("")
def list_all_bots():
    """GET /api/spreadworks/bots — overview of all bots."""
    out = []
    for bot in list_bots():
        try:
            out.append(get_status(bot))
        except Exception as e:
            out.append({"bot": bot, "error": str(e)[:200]})
    return {"bots": out}
