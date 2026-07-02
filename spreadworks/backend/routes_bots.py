"""SpreadWorks bot API routes: /api/spreadworks/bots/{bot}/*"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
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

    # Sum of MTM P&L across all OPEN positions (paper-mark from latest scan).
    unrealized = sum(float(p.get("mtm_pnl") or 0) for p in opens)

    # Today P&L = realized P&L from trades closed during today's CT session.
    # Computed in Python so the SQL is dialect-portable (SQLite tests +
    # production Postgres both treat TIMESTAMP columns as naive datetimes).
    now_ct = datetime.now(CT)
    day_start_ct = now_ct.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_ct = day_start_ct + timedelta(days=1)
    # Strip tzinfo before binding — TIMESTAMP columns are stored naive.
    day_start = day_start_ct.replace(tzinfo=None)
    day_end = day_end_ct.replace(tzinfo=None)

    with ENGINE.begin() as conn:
        last = conn.execute(text(
            f"SELECT MAX(scan_time) AS s FROM {bot_table(bot, 'scan_activity')}"
        )).mappings().first()
        today = conn.execute(text(
            f"SELECT COALESCE(SUM(realized_pnl), 0) AS p "
            f"FROM {bot_table(bot, 'closed_trades')} "
            "WHERE close_time >= :s AND close_time < :e"
        ), {"s": day_start, "e": day_end}).mappings().first()

    return {
        "bot": bot,
        "display": BOT_REGISTRY[bot]["display"],
        "strategy": BOT_REGISTRY[bot]["strategy"],
        "enabled": bool(cfg["enabled"]),
        "open_positions": len(opens),
        "equity": float(equity),
        "starting_capital": float(cfg["starting_capital"]),
        "today_pnl": float(today["p"] or 0),
        "unrealized_pnl": float(unrealized),
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


# Non-intraday equity-curve windows, in days. Anything not listed here ("all")
# returns the full series with no lower bound.
_EQUITY_WINDOW_DAYS = {"1d": 1, "1w": 7, "1m": 30, "3m": 90}


def _downsample_rows(rows: list, cap: int = 600) -> list:
    """Evenly thin a long series to <=cap points for the chart, always keeping the
    last (most recent) point so the tip of the curve is accurate."""
    n = len(rows)
    if n <= cap:
        return rows
    stride = n / cap
    out = [rows[int(i * stride)] for i in range(cap)]
    if out[-1] is not rows[-1]:
        out.append(rows[-1])
    return out


@router.get("/{bot}/equity-curve")
def get_equity_curve(bot: str, window: str = "all"):
    """Equity curve over the selected `window` (1d/1w/1m/3m, or "all").

    Sourced from the dense per-scan `equity_snapshots` series — NOT the sparse
    `closed_trades` ledger, which stays empty until a bot closes >=2 trades and so
    left every non-intraday window blank. Cutoff is computed in Python (CT-naive) to
    keep the SQL dialect-portable, matching get_status. `pnl` is mark-to-market total
    (equity - starting_capital), consistent with the intraday card."""
    _validate(bot)
    cfg = load_config(ENGINE, bot)
    sc = float(cfg["starting_capital"])
    st = bot_table(bot, "equity_snapshots")
    w = (window or "all").lower()
    where = ""
    params: dict[str, Any] = {}
    if w in _EQUITY_WINDOW_DAYS:
        cutoff = (datetime.now(CT) - timedelta(days=_EQUITY_WINDOW_DAYS[w])).replace(tzinfo=None)
        where = "WHERE snapshot_time >= :cutoff "
        params["cutoff"] = cutoff
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT snapshot_time, equity FROM {st} {where}ORDER BY snapshot_time"
        ), params).mappings().all()
    curve = [{"time": str(r["snapshot_time"]), "equity": float(r["equity"]),
              "pnl": float(r["equity"]) - sc} for r in _downsample_rows(rows)]
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
    entry_days: str | None = None
    allow_stacking: bool | None = None
    max_concurrent_positions: int | None = None
    min_credit: float | None = None


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
    # Force window: temporarily widen entry hours AND clear entry_days so
    # day-of-week gated bots (e.g. MEADOW = mon/fri) can be forced outside
    # their normal window. Restore both fields after the scan.
    cfg = load_config(ENGINE, bot)
    t = bot_table(bot, "config")
    with ENGINE.begin() as conn:
        conn.execute(text(
            f"UPDATE {t} SET entry_start_ct='00:00', entry_end_ct='23:59', "
            f"entry_days='' WHERE id=1"
        ))
    try:
        result = run_scan_cycle(
            engine=ENGINE, bot=bot, now_ct=now,
            chain_provider=provider, event_blackout=False,
        )
    finally:
        with ENGINE.begin() as conn:
            conn.execute(text(
                f"UPDATE {t} SET entry_start_ct=:s, entry_end_ct=:e, "
                f"entry_days=:d WHERE id=1"
            ), {"s": cfg["entry_start_ct"], "e": cfg["entry_end_ct"],
                "d": cfg.get("entry_days") or ""})
    return result


class AdjustBody(BaseModel):
    pt_target_pnl: float | None = None
    sl_target_pnl: float | None = None


@router.post("/{bot}/positions/{position_id}/adjust")
def adjust_position(bot: str, position_id: str, body: AdjustBody):
    """Update a position's PT and/or SL targets in place.

    Setting pt_target_pnl flips pt_override=TRUE so the scanner's time-of-day
    ladder (iron_butterfly / iron_condor) stops resetting the value on the
    next tick.

    sl_target_pnl is stored as an absolute MAGNITUDE on the position row.
    decide_exit() compares mtm_pnl <= -abs(sl_target_pnl), so the sign of
    the value the client sends doesn't matter — we normalize to abs() here.
    """
    _validate(bot)
    if body.pt_target_pnl is None and body.sl_target_pnl is None:
        raise HTTPException(400, "Provide at least one of pt_target_pnl / sl_target_pnl")

    t = bot_table(bot, "positions")
    with ENGINE.begin() as conn:
        row = conn.execute(text(
            f"SELECT position_id, pt_target_pnl, sl_target_pnl FROM {t} "
            "WHERE position_id=:p AND status='OPEN'"
        ), {"p": position_id}).mappings().first()
        if row is None:
            raise HTTPException(404, f"No OPEN position {position_id}")

        sets = []
        params: dict[str, Any] = {"p": position_id}
        if body.pt_target_pnl is not None:
            sets.append("pt_target_pnl = :pt")
            sets.append("pt_override = TRUE")
            params["pt"] = float(body.pt_target_pnl)
        if body.sl_target_pnl is not None:
            sets.append("sl_target_pnl = :sl")
            # Normalize to magnitude — decide_exit uses -abs(sl) internally.
            params["sl"] = abs(float(body.sl_target_pnl))

        conn.execute(text(
            f"UPDATE {t} SET {', '.join(sets)} WHERE position_id = :p"
        ), params)

        updated = conn.execute(text(
            f"SELECT pt_target_pnl, sl_target_pnl, pt_override FROM {t} "
            "WHERE position_id=:p"
        ), {"p": position_id}).mappings().first()

    return {
        "position_id": position_id,
        "pt_target_pnl": float(updated["pt_target_pnl"]),
        "sl_target_pnl": float(updated["sl_target_pnl"]),
        "pt_override": bool(updated["pt_override"]),
    }


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


@router.post("/{bot}/reset")
def post_reset(bot: str, confirm: bool = False):
    """Wipe a paper bot's trade data back to its starting-capital baseline.

    Deletes ALL rows from {bot}_positions, {bot}_closed_trades, and
    {bot}_equity_snapshots. The config row ({bot}_config) and the scanner
    activity log ({bot}_scan_activity) are preserved. Equity is computed as
    starting_capital + realized + unrealized, so clearing positions and
    closed trades returns the account to starting_capital automatically.

    Guarded by confirm=true. These are paper-only bots, so there are no
    broker side effects — but this is destructive (mirrors common-mistakes
    rule #19: prefer reconcile over reset), hence the explicit gate.
    """
    _validate(bot)
    if not confirm:
        raise HTTPException(
            400,
            "Pass confirm=true to reset. Destructive: wipes all positions, "
            "closed trades, and equity snapshots (config + scan log kept).",
        )
    deleted: dict[str, int] = {}
    with ENGINE.begin() as conn:
        for short in ("positions", "closed_trades", "equity_snapshots"):
            t = bot_table(bot, short)
            res = conn.execute(text(f"DELETE FROM {t}"))
            deleted[short] = int(res.rowcount or 0)
    cfg = load_config(ENGINE, bot)
    equity = account_equity(ENGINE, bot)
    logger.info("RESET %s — deleted %s, equity now %.2f", bot, deleted, float(equity))
    return {
        "bot": bot,
        "reset": True,
        "deleted": deleted,
        "starting_capital": float(cfg["starting_capital"]),
        "equity": float(equity),
    }


@router.get("/{bot}/positions/{position_id}/payoff")
def get_position_payoff(bot: str, position_id: str):
    """At-expiration (or modeled, for time-dependent strategies) payoff curve
    for a single bot position. Mirrors /positions/{id}/payoff in routes.py but
    targets the per-bot table layout (legs stored as JSON in {bot}_positions).
    """
    _validate(bot)
    # Lazy import to avoid a circular dep with routes.py at module load.
    from .routes import _scan_pnl_profile, RISK_FREE_RATE, CREDIT_STRATEGIES

    t_pos = bot_table(bot, "positions")
    t_cls = bot_table(bot, "closed_trades")
    with ENGINE.begin() as conn:
        row = conn.execute(text(
            f"SELECT position_id, strategy, legs, entry_price, contracts, "
            f"max_profit, max_loss, ticker FROM {t_pos} WHERE position_id=:p"
        ), {"p": position_id}).mappings().first()
        if row is None:
            row = conn.execute(text(
                f"SELECT position_id, strategy, legs, entry_price, contracts, "
                f"NULL AS max_profit, NULL AS max_loss, ticker FROM {t_cls} "
                "WHERE position_id=:p"
            ), {"p": position_id}).mappings().first()
    if row is None:
        raise HTTPException(404, f"Position not found: {position_id}")

    legs = json.loads(row["legs"]) if isinstance(row["legs"], str) else row["legs"]
    strategy = row["strategy"]
    entry_price = float(row["entry_price"])
    n = int(row["contracts"])

    # entry_cost convention mirrors routes.position_payoff:
    # credit strategies → negative; debit strategies → positive.
    entry_cost = -entry_price if strategy in CREDIT_STRATEGIES else entry_price

    def _leg(side: str, opt_type: str) -> dict | None:
        for lg in legs:
            if lg.get("side") == side and lg.get("type") == opt_type:
                return lg
        return None

    sigma = 0.20
    r = RISK_FREE_RATE

    if strategy == "iron_butterfly":
        lp = float(_leg("long", "put")["strike"])
        lc = float(_leg("long", "call")["strike"])
        # body strike — short put and short call share the same strike
        short_strike = float(_leg("short", "call")["strike"])
        exp = _leg("short", "call")["expiration"]
        profile = _scan_pnl_profile(
            "iron_butterfly", short_strike,
            {"lp": lp, "short": short_strike, "lc": lc},
            {"exp": exp},
            r, sigma, entry_cost, n,
        )
    elif strategy == "long_butterfly":
        # Single-type 1-2-1 long fly. Both wings are the SAME type as the body,
        # so _leg(side, type) can't tell the lower wing from the upper — resolve
        # by strike ordering instead. Reuses the existing "butterfly" payoff
        # model (buy 1 lower, sell 2 middle, buy 1 upper).
        opt_type = legs[0].get("type", "call")
        long_strikes = sorted(float(lg["strike"]) for lg in legs if lg.get("side") == "long")
        short_strikes = [float(lg["strike"]) for lg in legs if lg.get("side") == "short"]
        lower = long_strikes[0]
        upper = long_strikes[-1]
        middle = short_strikes[0]  # body sold twice — both rows share this strike
        exp = legs[0]["expiration"]
        profile = _scan_pnl_profile(
            "butterfly", middle,
            {"lower": lower, "middle": middle, "upper": upper,
             "is_call": opt_type == "call"},
            {"exp": exp},
            r, sigma, entry_cost, n,
        )
    elif strategy == "double_calendar":
        short_call = _leg("short", "call")
        short_put = _leg("short", "put")
        long_call = _leg("long", "call")
        ps = float(short_put["strike"])
        cs = float(short_call["strike"])
        S = (ps + cs) / 2
        profile = _scan_pnl_profile(
            "double_calendar", S,
            {"ps": ps, "cs": cs},
            {"front": short_call["expiration"], "back": long_call["expiration"]},
            r, sigma, entry_cost, n,
        )
    elif strategy in ("double_diagonal", "double_diagonal_credit"):
        # Credit and debit double diagonals share identical payoff geometry —
        # only the entry_cost sign differs, and that's already handled above
        # via CREDIT_STRATEGIES. Route both through the double_diagonal model.
        short_call = _leg("short", "call")
        short_put = _leg("short", "put")
        long_call = _leg("long", "call")
        long_put = _leg("long", "put")
        sp = float(short_put["strike"])
        sc = float(short_call["strike"])
        lp = float(long_put["strike"])
        lc = float(long_call["strike"])
        S = (sp + sc) / 2
        profile = _scan_pnl_profile(
            "double_diagonal", S,
            {"lp": lp, "sp": sp, "sc": sc, "lc": lc},
            {"short": short_call["expiration"], "long": long_call["expiration"]},
            r, sigma, entry_cost, n,
        )
    elif strategy == "iron_condor":
        short_call = _leg("short", "call")
        short_put = _leg("short", "put")
        long_call = _leg("long", "call")
        long_put = _leg("long", "put")
        sp = float(short_put["strike"])
        sc = float(short_call["strike"])
        lp = float(long_put["strike"])
        lc = float(long_call["strike"])
        S = (sp + sc) / 2
        profile = _scan_pnl_profile(
            "iron_condor", S,
            {"lp": lp, "sp": sp, "sc": sc, "lc": lc},
            {"exp": short_call["expiration"]},
            r, sigma, entry_cost, n,
        )
    elif strategy in ("bull_call_spread", "bear_call_spread",
                      "bull_put_spread", "bear_put_spread"):
        # Two-leg vertical spread (UNDERTOW debit / DELTA credit). Single option
        # type, one long + one short strike — resolve long/short by side rather
        # than by strike so all four directional variants route through the same
        # intrinsic model.
        long_leg = next(lg for lg in legs if lg.get("side") == "long")
        short_leg = next(lg for lg in legs if lg.get("side") == "short")
        is_call = legs[0].get("type") == "call"
        long_k = float(long_leg["strike"])
        short_k = float(short_leg["strike"])
        S = (long_k + short_k) / 2
        profile = _scan_pnl_profile(
            "vertical", S,
            {"long": long_k, "short": short_k, "is_call": is_call},
            {"exp": long_leg["expiration"]},
            r, sigma, entry_cost, n,
        )
    elif strategy == "pin_drift_combo":
        # Legs are stored in build order (see PinDriftComboSignal.legs()):
        #   0 fly lower, 1-2 fly body (x2), 3 fly upper,
        #   4 call-cal front short, 5 call-cal back long,
        #   6 put-cal front short, 7 put-cal back long.
        fly_type = legs[0].get("type", "call")
        lower = float(legs[0]["strike"])
        middle = float(legs[1]["strike"])
        upper = float(legs[3]["strike"])
        call_cal = float(legs[4]["strike"])
        put_cal = float(legs[6]["strike"])
        front_exp = legs[0]["expiration"]
        back_exp = legs[5]["expiration"]
        profile = _scan_pnl_profile(
            "pin_drift_combo", middle,
            {"lower": lower, "middle": middle, "upper": upper,
             "is_call": fly_type == "call", "call_cal": call_cal, "put_cal": put_cal},
            {"front": front_exp, "back": back_exp},
            r, sigma, entry_cost, n,
        )
    else:
        raise HTTPException(400, f"Unsupported strategy for payoff: {strategy}")

    # Prefer stored max_profit/max_loss so the chart's headline matches the
    # card display (per-contract * contracts already baked in at open time).
    stored_mp = row["max_profit"]
    stored_ml = row["max_loss"]
    max_profit = float(stored_mp) if stored_mp is not None else profile["max_profit"]
    max_loss = float(stored_ml) if stored_ml is not None else profile["max_loss"]

    return {
        "position_id": position_id,
        "strategy": strategy,
        "ticker": row["ticker"],
        "pnl_curve": profile["pnl_curve"],
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakevens": {
            "lower": profile["lower_breakeven"],
            "upper": profile["upper_breakeven"],
        },
    }


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


@router.get("/{bot}/watchlist")
def get_watchlist(bot: str):
    """Read-only universe watchlist for the vertical-spread bots (UNDERTOW /
    DELTA). Per tracked name: live signal status + the exact candidate spread
    when a setup is firing. 400 for non-universe bots."""
    _validate(bot)
    meta = BOT_REGISTRY[bot]
    if not (meta.get("universe") and meta.get("vertical_mode")):
        raise HTTPException(400, f"{bot} is not a universe bot")
    from .bots.scanner import (
        evaluate_universe_watchlist, ticker_eval_to_row, pick_would_open,
    )
    from .bots.routes_helpers import build_live_chain_provider
    cfg = load_config(ENGINE, bot)
    now = datetime.now(CT)
    provider = build_live_chain_provider()
    evals = evaluate_universe_watchlist(
        engine=ENGINE, bot=bot, meta=meta, cfg=cfg, now_ct=now,
        chain_provider=provider,
    )
    winner = pick_would_open(evals)  # the one row the live scanner would open
    return {
        "bot": bot,
        "mode": meta.get("vertical_mode"),
        "as_of_ct": now.replace(tzinfo=None).isoformat(timespec="seconds"),
        "universe": list(meta["universe"]),
        "rows": [ticker_eval_to_row(e, would_open=(e is winner)) for e in evals],
    }


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
