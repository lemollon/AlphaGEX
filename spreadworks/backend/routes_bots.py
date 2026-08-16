"""SpreadWorks bot API routes: /api/spreadworks/bots/{bot}/*"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
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

    # Mark-to-market equity — what the account is worth RIGHT NOW, including
    # open positions. `equity` above is realized-only (starting_capital +
    # closed P&L); it deliberately stays that way because scanner.py sizes
    # positions off it and must not lever up on unrealized marks. But the UI
    # was reading that realized-only number for its "Account Equity" tile,
    # so the tile sat frozen all session while the equity CURVE beneath it
    # (written by _write_equity_snapshot, which DOES add unrealized) moved —
    # they disagreed by exactly the open-position P&L and it read as lag.
    # Same formula as the snapshot writer so tile and curve now agree.
    equity_mtm = float(equity) + unrealized

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
        "equity_mtm": float(equity_mtm),
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
    drift_offset: int | None = None
    # The VIX decay gate ceiling. Was settable only by raw SQL until 2026-08-15,
    # which is how ebb sat at NULL with no way to correct it from the operator
    # surface. 0 disables the gate (scanner.py gates on `ceiling > 0`); there is
    # deliberately no way to write NULL back, since NULL means "never configured"
    # and the startup backfill would just refill it.
    vix_decay_max: float | None = None


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
    if any(m is None for m in mids):
        # Missing leg quote — a fresh mark would be garbage. Force-close at
        # the last stored mark instead of a phantom price.
        mtm_value = float(pos["mtm_value"] or 0.0)
    else:
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


# ── /fleet-stats — one aggregated call for the Fleet page's risk/trades/
# equity/concentration widgets. Module-level cache (60s TTL) so 23-bot polls
# from multiple open tabs don't hammer every {bot}_positions/closed_trades/
# equity_snapshots table on every request.
_FLEET_STATS_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_FLEET_STATS_TTL = 60


def _parse_legs(raw: Any) -> list[dict]:
    """Defensive TEXT-JSON parse — bad/missing legs skip rather than 500."""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _date_str(v: Any) -> str:
    """Dialect-portable date-of-timestamp -> 'YYYY-MM-DD' (Postgres returns a
    datetime, SQLite in tests may return a string)."""
    if hasattr(v, "date"):
        return v.date().isoformat()
    return str(v)[:10]


def _bot_health(bot: str, bands: dict[str, float]) -> dict[str, Any]:
    """Rolling-window health check against pre-registered bands (EBB,
    registry #23b) — a decaying edge should demote itself rather than keep
    opening. Only called for bots whose registry entry carries `health_bands`.
    Never raises — a query hiccup reads as "warming_up" rather than sinking
    the whole fleet card (this bot's slice is otherwise already wrapped by
    the caller, but health specifically must not turn a working card red).
    """
    t_cls = bot_table(bot, "closed_trades")
    try:
        with ENGINE.begin() as conn:
            rows = conn.execute(text(
                f"SELECT realized_pnl, entry_price FROM {t_cls} "
                "ORDER BY close_time DESC LIMIT 120"
            )).mappings().all()
    except Exception as e:                                     # noqa: BLE001
        logger.warning(f"[{bot}] health query failed: {e}")
        return {"status": "warming_up", "roll60": None, "roll120": None,
                "credit20": None, "bands": bands}

    n = len(rows)
    roll60 = sum(float(r["realized_pnl"] or 0) for r in rows[:60]) if n >= 60 else None
    roll120 = sum(float(r["realized_pnl"] or 0) for r in rows[:120]) if n >= 120 else None
    # entry_price stores the net CREDIT received for a credit vertical
    # (executor.open_position: entry_price = signal.credit) — $/share, so
    # x100 for $/lot.
    credit20 = (sum(float(r["entry_price"] or 0) for r in rows[:20]) / 20.0 * 100.0
                if n >= 20 else None)

    if ((n >= 60 and roll60 <= bands["demote_roll60"])
            or (n >= 120 and roll120 <= bands["demote_roll120"])
            or (n >= 20 and credit20 < bands["min_credit20"])):
        status = "DEGRADED"
    elif n >= 60 and roll60 <= bands["watch_roll60"]:
        status = "WATCH"
    elif n < 60:
        status = "warming_up"
    else:
        status = "SHARP"

    return {"status": status, "roll60": roll60, "roll120": roll120,
            "credit20": credit20, "bands": bands}


def _bot_fleet_stats(bot: str, now_ct: datetime) -> tuple[dict[str, Any], list[dict]]:
    """One bot's slice of /fleet-stats. Raises on any failure — the caller
    wraps this per-bot so one broken bot can't 500 the whole page. Returns
    (stats, open_rows) — open_rows feeds the fleet-wide concentration/
    all_paper rollup so a raise here also keeps that bot out of those.
    """
    today_ct = now_ct.date()
    t_pos = bot_table(bot, "positions")
    t_cls = bot_table(bot, "closed_trades")
    t_eq = bot_table(bot, "equity_snapshots")

    # Same CT-wall-clock-stripped-to-naive convention as get_status's
    # today_pnl window (this module, above) — TIMESTAMP columns are naive.
    c7 = (now_ct - timedelta(days=7)).replace(tzinfo=None)
    c30 = (now_ct - timedelta(days=30)).replace(tzinfo=None)
    eq_cutoff = (now_ct - timedelta(days=30)).replace(tzinfo=None)

    with ENGINE.begin() as conn:
        open_rows = [dict(r) for r in conn.execute(text(
            f"SELECT account_label, max_loss, legs, ticker, strategy FROM {t_pos} "
            "WHERE status='OPEN'"
        )).mappings().all()]

        trades_row = conn.execute(text(
            f"SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins, "
            "COALESCE(SUM(CASE WHEN close_time >= :c7 THEN realized_pnl ELSE 0 END), 0) AS pnl_7d, "
            "COALESCE(SUM(CASE WHEN close_time >= :c30 THEN realized_pnl ELSE 0 END), 0) AS pnl_30d "
            f"FROM {t_cls}"
        ), {"c7": c7, "c30": c30}).mappings().first()

        eq_rows = conn.execute(text(
            f"SELECT snapshot_time, equity FROM {t_eq} "
            "WHERE snapshot_time >= :c ORDER BY snapshot_time"
        ), {"c": eq_cutoff}).mappings().all()

    # ── account + risk ──────────────────────────────────────────────
    account = str(open_rows[0]["account_label"]) if open_rows else "paper"
    open_max_loss = None
    if open_rows:
        open_max_loss = sum(
            float(r["max_loss"]) for r in open_rows if r["max_loss"] is not None
        )
    nearest_dte = None
    for r in open_rows:
        for lg in _parse_legs(r.get("legs")):
            exp_str = lg.get("expiration") if isinstance(lg, dict) else None
            if not exp_str:
                continue
            try:
                exp_d = date.fromisoformat(str(exp_str)[:10])
            except ValueError:
                continue
            dte = (exp_d - today_ct).days
            if nearest_dte is None or dte < nearest_dte:
                nearest_dte = dte

    # ── trades (over ALL closed trades) ─────────────────────────────
    n = int(trades_row["n"] or 0)
    wins = int(trades_row["wins"] or 0)
    win_rate = (wins / n) if n else None

    # ── equity series — last snapshot per day, last 30 calendar days ──
    # `equity` as written by scanner._write_equity_snapshot is already
    # starting_capital + cumulative_realized + unrealized — i.e. already
    # mark-to-market, so no unrealized_pnl add-back is needed here.
    day_map: dict[str, float] = {}
    for r in eq_rows:
        day_map[_date_str(r["snapshot_time"])] = float(r["equity"])
    equity_series = [{"d": d, "equity": day_map[d]} for d in sorted(day_map)]

    drawdown_pct = None
    if len(equity_series) >= 2:
        vals = [p["equity"] for p in equity_series]
        peak = max(vals)
        last = vals[-1]
        drawdown_pct = (peak - last) / peak if peak else 0.0

    last_session = None
    today_str = today_ct.isoformat()
    before_today = [p["d"] for p in equity_series if p["d"] < today_str]
    if len(before_today) >= 2:
        last_d, prior_d = before_today[-1], before_today[-2]
        last_session = {"d": last_d, "pnl": day_map[last_d] - day_map[prior_d]}

    stats = {
        "account": account,
        "risk": {"open_max_loss": open_max_loss, "nearest_dte": nearest_dte},
        "trades": {
            "n": n, "wins": wins, "win_rate": win_rate,
            "pnl_7d": float(trades_row["pnl_7d"] or 0),
            "pnl_30d": float(trades_row["pnl_30d"] or 0),
        },
        "equity_series": equity_series,
        "drawdown_pct": drawdown_pct,
        "last_session": last_session,
    }

    health_bands = (BOT_REGISTRY.get(bot) or {}).get("health_bands")
    if health_bands:
        stats["health"] = _bot_health(bot, health_bands)

    return stats, open_rows


def _fleet_equity_curve(bots_out: dict[str, Any]) -> list[dict]:
    """Per-day sum of each bot's MTM daily equity, forward-filling a bot's
    last known value on days it lacks a snapshot. Only days where at least
    one bot has (real or forward-filled) data are included."""
    per_bot_days: dict[str, dict[str, float]] = {}
    for bot, s in bots_out.items():
        if "error" in s:
            continue
        per_bot_days[bot] = {p["d"]: p["equity"] for p in s.get("equity_series") or []}

    all_dates = sorted({d for days in per_bot_days.values() for d in days})
    curve: list[dict] = []
    last_seen: dict[str, float] = {}
    for d in all_dates:
        day_sum = 0.0
        any_data = False
        for bot, days in per_bot_days.items():
            if d in days:
                last_seen[bot] = days[d]
            if bot in last_seen:
                day_sum += last_seen[bot]
                any_data = True
        if any_data:
            curve.append({"d": d, "equity": day_sum})
    return curve


@router.get("/fleet-stats")
def get_fleet_stats():
    """GET /api/spreadworks/bots/fleet-stats — aggregated risk, trade history,
    equity curves, drawdown, and cross-bot concentration for the Fleet page,
    in one request (mirrors the perf rule that killed 23x/page-load fan-out
    for the card grid — see useFleet.js). Cached 60s.
    """
    now = time.time()
    cached = _FLEET_STATS_CACHE
    if cached["payload"] is not None and now - cached["ts"] < _FLEET_STATS_TTL:
        return cached["payload"]

    now_ct = datetime.now(CT)
    bots_out: dict[str, Any] = {}
    all_open_positions: list[dict] = []

    for bot in list_bots():
        try:
            stats, open_rows = _bot_fleet_stats(bot, now_ct)
            bots_out[bot] = stats
            all_open_positions.extend(open_rows)
        except Exception as e:
            bots_out[bot] = {"bot": bot, "error": str(e)}

    conc_map: dict[str, dict[str, Any]] = {}
    for p in all_open_positions:
        ticker = p.get("ticker") or "?"
        entry = conc_map.setdefault(ticker, {
            "ticker": ticker, "n_positions": 0, "open_max_loss": 0.0, "strategies": set(),
        })
        entry["n_positions"] += 1
        if p.get("max_loss") is not None:
            entry["open_max_loss"] += float(p["max_loss"])
        if p.get("strategy"):
            entry["strategies"].add(p["strategy"])
    concentration = [
        {"ticker": v["ticker"], "n_positions": v["n_positions"],
         "open_max_loss": v["open_max_loss"], "strategies": sorted(v["strategies"])}
        for v in conc_map.values()
    ]

    all_paper = not any(
        (p.get("account_label") or "paper") != "paper" for p in all_open_positions
    )

    payload = {
        "bots": bots_out,
        "fleet": {
            "equity_curve": _fleet_equity_curve(bots_out),
            "concentration": concentration,
            "all_paper": all_paper,
        },
        "generated_at": now_ct.isoformat(),
    }
    cached["ts"] = now
    cached["payload"] = payload
    return payload
