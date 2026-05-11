"""HELIOS (display: JOSHUA) - 1DTE Directional Spread Bot API Routes.

Path prefix: /api/joshua/. All read endpoints query HeliosDatabase directly so
they never depend on Trader-class init (per common-mistakes.md rule 3).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Optional
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException

from trading.helios.db import HeliosDatabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/joshua", tags=["JOSHUA"])

CENTRAL_TZ = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# Helpers - all DB-only (no trader init)
# ---------------------------------------------------------------------------

def _db() -> HeliosDatabase:
    """Cheap factory; HeliosDatabase is a thin wrapper, no pooling cost."""
    return HeliosDatabase()


def _starting_capital(db: HeliosDatabase) -> float:
    """Always read from helios_paper_account, never hardcode."""
    try:
        return float(db.get_starting_capital() or 0.0)
    except Exception:
        return 0.0


def _realized_pnl(db: HeliosDatabase) -> float:
    try:
        return float(db.get_realized_pnl() or 0.0)
    except Exception:
        return 0.0


def _config_get(key: str) -> Optional[Any]:
    """Read a key from helios_config (JSONB)."""
    try:
        with psycopg2.connect(_db().db_url) as conn:
            with conn.cursor() as c:
                c.execute("SELECT value FROM helios_config WHERE key = %s", (key,))
                row = c.fetchone()
                return row[0] if row else None
    except Exception as e:
        logger.debug("HELIOS _config_get(%s) failed: %s", key, e)
        return None


def _config_set(key: str, value: Any) -> None:
    """Upsert a key into helios_config (JSONB)."""
    payload = json.dumps(value)
    with psycopg2.connect(_db().db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """
                INSERT INTO helios_config (key, value, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW()
                """,
                (key, payload),
            )


def _is_enabled() -> bool:
    val = _config_get("enabled")
    if val is None:
        return True  # default ON
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "on")
    return bool(val)


def _now_ct() -> dt.datetime:
    return dt.datetime.now(CENTRAL_TZ)


def _today_ct_iso() -> str:
    return _now_ct().strftime("%Y-%m-%d")


def _quote_mid(symbol: str) -> Optional[float]:
    """Best-effort live quote mid via Tradier; None on any failure."""
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        t = TradierDataFetcher()
        if hasattr(t, "get_option_quotes_batch"):
            quotes = t.get_option_quotes_batch([symbol])
            q = quotes.get(symbol) if quotes else None
            if q and q.get("bid") is not None and q.get("ask") is not None:
                return (float(q["bid"]) + float(q["ask"])) / 2.0
    except Exception as e:
        logger.debug("HELIOS _quote_mid(%s) failed: %s", symbol, e)
    return None


def _spread_mark(pos: dict) -> Optional[float]:
    """Live mark-to-close for a HELIOS debit spread; None if quotes unavailable."""
    long_sym = pos.get("long_symbol")
    short_sym = pos.get("short_symbol")
    if not long_sym or not short_sym:
        return None
    long_mid = _quote_mid(long_sym)
    short_mid = _quote_mid(short_sym)
    if long_mid is None or short_mid is None:
        return None
    return long_mid - short_mid


def _unrealized_pnl_for(pos: dict) -> float:
    """Compute (mark - debit) * 100 * contracts; 0.0 if quotes unavailable."""
    if not pos:
        return 0.0
    mark = _spread_mark(pos)
    if mark is None:
        return 0.0
    debit = float(pos.get("debit") or 0)
    contracts = int(pos.get("contracts") or 0)
    return (mark - debit) * 100.0 * contracts


def _last_heartbeat() -> Optional[str]:
    """Most recent helios_scan_activity timestamp, ISO in CT, or None."""
    try:
        with psycopg2.connect(_db().db_url) as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    SELECT cycle_at::timestamptz AT TIME ZONE 'America/Chicago'
                    FROM helios_scan_activity
                    ORDER BY cycle_at DESC
                    LIMIT 1
                    """
                )
                row = c.fetchone()
                if row and row[0]:
                    return row[0].isoformat()
    except Exception as e:
        logger.debug("HELIOS _last_heartbeat failed: %s", e)
    return None


def _serialize_row(row: dict) -> dict:
    """Make psycopg2 dict rows JSON-friendly (Decimal/date/datetime → str/float)."""
    from decimal import Decimal
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (dt.datetime, dt.date)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 1. STATUS
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_status():
    """Bot status: config loaded, open positions count, paper balance, heartbeat."""
    try:
        db = _db()
        starting = _starting_capital(db)
        realized = _realized_pnl(db)
        open_pos = db.get_open_position()
        unrealized = _unrealized_pnl_for(open_pos) if open_pos else 0.0
        heartbeat = _last_heartbeat()
        now_ct = _now_ct()
        # Trading window 8:30 - 15:55 CT weekdays — matches trader._is_market_hours
        # (entry stops 5 min before EOD TIME_STOP at 15:55 CT)
        is_weekday = now_ct.weekday() < 5
        start_t = now_ct.replace(hour=8, minute=30, second=0, microsecond=0)
        end_t = now_ct.replace(hour=15, minute=55, second=0, microsecond=0)
        in_window = is_weekday and start_t <= now_ct < end_t

        return {
            "success": True,
            "data": {
                "bot": "JOSHUA",
                "internal_name": "HELIOS",
                "ticker": "SPY",
                "mode": "paper",
                "enabled": _is_enabled(),
                "config_loaded": True,
                "starting_capital": round(starting, 2),
                "realized_pnl": round(realized, 2),
                "unrealized_pnl": round(unrealized, 2),
                "current_equity": round(starting + realized + unrealized, 2),
                "open_positions": 1 if open_pos else 0,
                "trades_today": db.count_trades_today(),
                "in_trading_window": in_window,
                "trading_window": "08:30-15:55 CT",
                "current_time": now_ct.strftime("%Y-%m-%d %H:%M:%S CT"),
                "heartbeat": heartbeat,
            },
        }
    except Exception as e:
        logger.error("HELIOS status error: %s", e)
        return {"success": False, "error": str(e), "data": {
            "bot": "JOSHUA",
            "config_loaded": False,
            "open_positions": 0,
            "starting_capital": 0,
            "realized_pnl": 0,
            "heartbeat": None,
        }}


# ---------------------------------------------------------------------------
# 2. POSITIONS (max 1 by design)
# ---------------------------------------------------------------------------

@router.get("/positions")
async def get_positions():
    """Current open position (max 1) with live unrealized P&L."""
    try:
        db = _db()
        pos = db.get_open_position()
        if not pos:
            return {"success": True, "data": [], "count": 0}
        row = _serialize_row(pos)
        mark = _spread_mark(pos)
        debit = float(pos.get("debit") or 0)
        contracts = int(pos.get("contracts") or 0)
        unrealized = ((mark - debit) * 100.0 * contracts) if mark is not None else None
        row["mark"] = round(mark, 4) if mark is not None else None
        row["unrealized_pnl"] = round(unrealized, 2) if unrealized is not None else None
        return {"success": True, "data": [row], "count": 1}
    except Exception as e:
        logger.error("HELIOS positions error: %s", e)
        return {"success": True, "data": [], "count": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# 3. EQUITY CURVE - cumulative running sum, no SQL date filter
# ---------------------------------------------------------------------------

@router.get("/equity-curve")
async def get_equity_curve():
    """Historical cumulative-PnL equity curve (all closed trades)."""
    try:
        db = _db()
        starting = _starting_capital(db)
        trades = db.all_closed_trades()  # oldest-first
        points = []
        running = 0.0
        # Seed point so chart always has at least 1 anchor
        if trades:
            first_ts = trades[0].get("close_time") or trades[0].get("open_time")
            if first_ts:
                seed_ts = first_ts.astimezone(CENTRAL_TZ) if hasattr(first_ts, "astimezone") and first_ts.tzinfo else first_ts
                points.append({
                    "timestamp": seed_ts.isoformat() if hasattr(seed_ts, "isoformat") else str(seed_ts),
                    "cumulative_pnl": 0.0,
                    "equity": round(starting, 2),
                    "trade_pnl": 0.0,
                    "position_id": None,
                })
        for t in trades:
            pnl = float(t.get("realized_pnl") or 0.0)
            running += pnl
            ts = t.get("close_time") or t.get("open_time")
            ts_ct = ts.astimezone(CENTRAL_TZ) if ts and hasattr(ts, "astimezone") and ts.tzinfo else ts
            points.append({
                "timestamp": ts_ct.isoformat() if ts_ct and hasattr(ts_ct, "isoformat") else (str(ts_ct) if ts_ct else None),
                "cumulative_pnl": round(running, 2),
                "equity": round(starting + running, 2),
                "trade_pnl": round(pnl, 2),
                "position_id": t.get("id"),
            })
        return {
            "success": True,
            "data": points,
            "count": len(points),
            "starting_capital": round(starting, 2),
            "total_pnl": round(running, 2),
        }
    except Exception as e:
        logger.error("HELIOS equity-curve error: %s", e)
        return {"success": True, "data": [], "count": 0, "starting_capital": 0,
                "total_pnl": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# 4. INTRADAY EQUITY CURVE - today's snapshots + live fallback
# ---------------------------------------------------------------------------

@router.get("/equity-curve/intraday")
async def get_intraday_equity_curve(date: Optional[str] = None):
    """Today's helios_equity_snapshots; live-snapshot fallback if empty."""
    db = _db()
    starting = _starting_capital(db)
    today = date or _today_ct_iso()
    now_ct = _now_ct()
    try:
        with psycopg2.connect(db.db_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT
                        snapshot_at::timestamptz AT TIME ZONE 'America/Chicago' AS ts_ct,
                        equity, cash, unrealized_pnl, open_position_count
                    FROM helios_equity_snapshots
                    WHERE DATE(snapshot_at::timestamptz AT TIME ZONE 'America/Chicago') = %s
                    ORDER BY snapshot_at ASC
                    """,
                    (today,),
                )
                snaps = [dict(r) for r in c.fetchall()]

        # Today's realized P&L (CT-bucketed)
        with psycopg2.connect(db.db_url) as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    SELECT COALESCE(SUM(realized_pnl), 0)
                    FROM helios_positions
                    WHERE status <> 'OPEN'
                      AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
                    """,
                    (today,),
                )
                row = c.fetchone()
                today_realized = float(row[0] or 0.0) if row else 0.0

        # Total realized through end of `today` (for prev-day baseline math)
        with psycopg2.connect(db.db_url) as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    SELECT COALESCE(SUM(realized_pnl), 0)
                    FROM helios_positions
                    WHERE status <> 'OPEN'
                      AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') <= %s
                    """,
                    (today,),
                )
                row = c.fetchone()
                total_realized_thru_today = float(row[0] or 0.0) if row else 0.0
        prev_day_realized = total_realized_thru_today - today_realized

        # Live unrealized (for fallback / final point)
        open_pos = db.get_open_position()
        live_unrealized = _unrealized_pnl_for(open_pos) if open_pos else 0.0
        open_count_live = 1 if open_pos else 0

        market_open_equity = round(starting + prev_day_realized, 2)
        data_points = [{
            "timestamp": f"{today}T08:30:00",
            "time": "08:30:00",
            "equity": market_open_equity,
            "cumulative_pnl": round(prev_day_realized, 2),
            "open_positions": 0,
            "unrealized_pnl": 0,
        }]
        all_eq = [market_open_equity]

        if snaps:
            for s in snaps:
                ts_ct = s["ts_ct"]
                eq = float(s.get("equity") or 0.0)
                unr = float(s.get("unrealized_pnl") or 0.0)
                cum = eq - starting
                all_eq.append(round(eq, 2))
                data_points.append({
                    "timestamp": ts_ct.isoformat() if ts_ct else None,
                    "time": ts_ct.strftime("%H:%M:%S") if ts_ct else None,
                    "equity": round(eq, 2),
                    "cumulative_pnl": round(cum, 2),
                    "open_positions": int(s.get("open_position_count") or 0),
                    "unrealized_pnl": round(unr, 2),
                })

        # Live snapshot fallback / final point - always append "now" if today
        if today == _today_ct_iso():
            current_equity = starting + total_realized_thru_today + live_unrealized
            all_eq.append(round(current_equity, 2))
            data_points.append({
                "timestamp": now_ct.isoformat(),
                "time": now_ct.strftime("%H:%M:%S"),
                "equity": round(current_equity, 2),
                "cumulative_pnl": round(total_realized_thru_today + live_unrealized - prev_day_realized, 2),
                "open_positions": open_count_live,
                "unrealized_pnl": round(live_unrealized, 2),
            })

        return {
            "success": True,
            "date": today,
            "bot": "JOSHUA",
            "data_points": data_points,
            "current_equity": all_eq[-1] if all_eq else market_open_equity,
            "day_pnl": round(today_realized + live_unrealized, 2),
            "day_realized": round(today_realized, 2),
            "day_unrealized": round(live_unrealized, 2),
            "starting_equity": market_open_equity,
            "starting_capital": round(starting, 2),
            "high_of_day": max(all_eq) if all_eq else market_open_equity,
            "low_of_day": min(all_eq) if all_eq else market_open_equity,
            "snapshots_count": len(snaps),
            "open_positions_count": open_count_live,
        }
    except Exception as e:
        logger.error("HELIOS intraday equity error: %s", e)
        return {
            "success": False,
            "error": str(e),
            "date": today,
            "bot": "JOSHUA",
            "data_points": [{
                "timestamp": now_ct.isoformat(),
                "time": now_ct.strftime("%H:%M:%S"),
                "equity": round(starting, 2),
                "cumulative_pnl": 0,
                "open_positions": 0,
                "unrealized_pnl": 0,
            }],
            "current_equity": round(starting, 2),
            "day_pnl": 0, "day_realized": 0, "day_unrealized": 0,
            "starting_equity": round(starting, 2),
            "starting_capital": round(starting, 2),
            "high_of_day": round(starting, 2),
            "low_of_day": round(starting, 2),
            "snapshots_count": 0, "open_positions_count": 0,
        }


# ---------------------------------------------------------------------------
# 5. PERFORMANCE - win rate, total P&L, by exit reason
# ---------------------------------------------------------------------------

@router.get("/performance")
async def get_performance():
    """Win rate, total P&L, breakdown by exit reason. Zeroes if no trades."""
    try:
        db = _db()
        starting = _starting_capital(db)
        with psycopg2.connect(db.db_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
                        COALESCE(SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END), 0) AS losses,
                        COALESCE(SUM(realized_pnl), 0) AS total_pnl,
                        COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
                        COALESCE(MAX(realized_pnl), 0) AS best_trade,
                        COALESCE(MIN(realized_pnl), 0) AS worst_trade
                    FROM helios_positions
                    WHERE status <> 'OPEN'
                    """
                )
                summary = dict(c.fetchone() or {})

                c.execute(
                    """
                    SELECT
                        COALESCE(exit_reason, 'UNKNOWN') AS exit_reason,
                        COUNT(*) AS trades,
                        COALESCE(SUM(realized_pnl), 0) AS total_pnl,
                        COALESCE(AVG(realized_pnl), 0) AS avg_pnl
                    FROM helios_positions
                    WHERE status <> 'OPEN'
                    GROUP BY exit_reason
                    ORDER BY total_pnl DESC
                    """
                )
                by_reason = [_serialize_row(dict(r)) for r in c.fetchall()]

        total = int(summary.get("total") or 0)
        wins = int(summary.get("wins") or 0)
        losses = int(summary.get("losses") or 0)
        total_pnl = float(summary.get("total_pnl") or 0.0)
        win_rate = round((wins / total) * 100.0, 1) if total else 0.0
        return_pct = round((total_pnl / starting) * 100.0, 2) if starting > 0 else 0.0
        return {
            "success": True,
            "data": {
                "total_trades": total,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(float(summary.get("avg_pnl") or 0.0), 2),
                "best_trade": round(float(summary.get("best_trade") or 0.0), 2),
                "worst_trade": round(float(summary.get("worst_trade") or 0.0), 2),
                "starting_capital": round(starting, 2),
                "return_pct": return_pct,
                "by_exit_reason": by_reason,
            },
        }
    except Exception as e:
        logger.error("HELIOS performance error: %s", e)
        return {"success": True, "data": {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "total_pnl": 0, "avg_pnl": 0, "best_trade": 0, "worst_trade": 0,
            "starting_capital": 0, "return_pct": 0, "by_exit_reason": [],
        }, "error": str(e)}


# ---------------------------------------------------------------------------
# 6. SCAN ACTIVITY (limit 100)
# ---------------------------------------------------------------------------

@router.get("/scan-activity")
async def get_scan_activity(limit: int = 100):
    """Recent helios_scan_activity rows (default 100)."""
    try:
        limit = max(1, min(int(limit or 100), 500))
        with psycopg2.connect(_db().db_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT
                        id,
                        cycle_at::timestamptz AT TIME ZONE 'America/Chicago' AS cycle_at_ct,
                        cycle_at,
                        outcome,
                        detail
                    FROM helios_scan_activity
                    ORDER BY cycle_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = [_serialize_row(dict(r)) for r in c.fetchall()]
        return {"success": True, "data": rows, "count": len(rows)}
    except Exception as e:
        logger.error("HELIOS scan-activity error: %s", e)
        return {"success": True, "data": [], "count": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# 7. SIGNALS (limit 100)
# ---------------------------------------------------------------------------

@router.get("/signals")
async def get_signals(limit: int = 100):
    """Recent helios_signals rows (default 100)."""
    try:
        limit = max(1, min(int(limit or 100), 500))
        with psycopg2.connect(_db().db_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT
                        id,
                        cycle_at::timestamptz AT TIME ZONE 'America/Chicago' AS cycle_at_ct,
                        cycle_at,
                        action, spread_type, long_strike, short_strike,
                        skip_reason, detail, spot, vix
                    FROM helios_signals
                    ORDER BY cycle_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = [_serialize_row(dict(r)) for r in c.fetchall()]
        return {"success": True, "data": rows, "count": len(rows)}
    except Exception as e:
        logger.error("HELIOS signals error: %s", e)
        return {"success": True, "data": [], "count": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# 8. TRADES - closed trade history (limit 200)
# ---------------------------------------------------------------------------

@router.get("/trades")
async def get_trades(limit: int = 200):
    """Closed trade history (default 200, newest first)."""
    try:
        limit = max(1, min(int(limit or 200), 1000))
        with psycopg2.connect(_db().db_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT
                        id, spread_type, long_symbol, short_symbol,
                        long_strike, short_strike, expiration_date,
                        contracts, debit, close_price, realized_pnl, exit_reason,
                        status,
                        open_time::timestamptz AT TIME ZONE 'America/Chicago' AS open_time_ct,
                        close_time::timestamptz AT TIME ZONE 'America/Chicago' AS close_time_ct,
                        open_time, close_time
                    FROM helios_positions
                    WHERE status <> 'OPEN'
                    ORDER BY COALESCE(close_time, open_time) DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = [_serialize_row(dict(r)) for r in c.fetchall()]
        return {"success": True, "data": rows, "count": len(rows)}
    except Exception as e:
        logger.error("HELIOS trades error: %s", e)
        return {"success": True, "data": [], "count": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# 9. TOGGLE - flip helios_config 'enabled'
# ---------------------------------------------------------------------------

@router.post("/toggle")
async def toggle_bot(active: Optional[bool] = None):
    """Toggle bot enabled flag in helios_config (key='enabled'). If `active` omitted, flips current state."""
    try:
        current = _is_enabled()
        new_state = bool(active) if active is not None else (not current)
        _config_set("enabled", new_state)
        return {"success": True, "data": {"enabled": new_state, "previous": current}}
    except Exception as e:
        logger.error("HELIOS toggle error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 10. FORCE-TRADE - manually trigger an entry cycle
# ---------------------------------------------------------------------------

@router.post("/force-trade")
async def force_trade():
    """Manually trigger one HELIOS entry cycle (best-effort; trader may be unavailable)."""
    try:
        # Construct a minimal trader using whatever data adapters are available.
        from trading.helios.models import HeliosConfig
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            tradier = TradierDataFetcher()
        except Exception as e:
            return {"success": False, "error": f"Tradier client unavailable: {e}"}

        gex_calc = None
        try:
            from data.gex_calculator import GexCalculator  # type: ignore
            gex_calc = GexCalculator()
        except Exception:
            pass

        vix_fetcher = None
        try:
            from data.unified_data_provider import get_price as _gp
            vix_fetcher = lambda: _gp("VIX")
        except Exception:
            pass

        prophet = None
        try:
            from quant.prophet_advisor import get_recommendation as _pa
            prophet = _pa
        except Exception:
            pass

        from trading.helios.trader import HeliosTrader
        trader = HeliosTrader(
            db=_db(),
            tradier=tradier,
            config=HeliosConfig(),
            gex_calculator=gex_calc,
            vix_fetcher=vix_fetcher,
            prophet_advisor=prophet,
        )
        trader.run_cycle()
        # Inspect what happened
        db = _db()
        latest_sig = None
        try:
            with psycopg2.connect(db.db_url) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                    c.execute("SELECT * FROM helios_signals ORDER BY cycle_at DESC LIMIT 1")
                    r = c.fetchone()
                    latest_sig = _serialize_row(dict(r)) if r else None
        except Exception:
            pass
        open_pos = db.get_open_position()
        return {
            "success": True,
            "data": {
                "latest_signal": latest_sig,
                "has_open_position": open_pos is not None,
                "open_position_id": open_pos.get("id") if open_pos else None,
            },
        }
    except Exception as e:
        logger.error("HELIOS force-trade error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 11/12. FORCE-CLOSE / EOD-CLOSE - close any open position at MTM
# ---------------------------------------------------------------------------

def _close_open_at_mtm(exit_reason: str) -> dict:
    db = _db()
    pos = db.get_open_position()
    if not pos:
        return {"success": True, "data": {"closed": False, "reason": "no_open_position"}}

    pid = int(pos["id"])
    debit = float(pos.get("debit") or 0.0)
    contracts = int(pos.get("contracts") or 0)
    mark = _spread_mark(pos)
    if mark is None:
        # fall back to entry debit so a stuck position still records correctly
        mark = debit
        method = "fallback_to_debit"
    else:
        method = "live_quote"
    realized_pnl = (mark - debit) * 100.0 * contracts

    from trading.helios.executor import close_paper
    try:
        close_paper(db=db, position_id=pid, mark_to_close=mark, exit_reason=exit_reason)
    except Exception as e:
        logger.error("HELIOS close_paper failed for pid=%s: %s", pid, e)
        raise HTTPException(status_code=500, detail=f"close_paper failed: {e}")

    return {
        "success": True,
        "data": {
            "closed": True,
            "position_id": pid,
            "mark_to_close": round(mark, 4),
            "realized_pnl": round(realized_pnl, 2),
            "exit_reason": exit_reason,
            "mark_method": method,
        },
    }


@router.post("/force-close")
async def force_close():
    """Close any open HELIOS position at MTM, exit_reason='MANUAL'."""
    try:
        return _close_open_at_mtm("MANUAL")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("HELIOS force-close error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/eod-close")
async def eod_close():
    """Close any open HELIOS position at MTM, exit_reason='EOD'."""
    try:
        return _close_open_at_mtm("EOD")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("HELIOS eod-close error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 13. DIAGNOSE-TRADE - latest signal's skip_reason + detail
# ---------------------------------------------------------------------------

@router.get("/diagnose-trade")
async def diagnose_trade():
    """Read latest helios_signals row, surface skip_reason + detail."""
    try:
        with psycopg2.connect(_db().db_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT
                        id, action, spread_type, long_strike, short_strike,
                        skip_reason, detail, spot, vix,
                        cycle_at::timestamptz AT TIME ZONE 'America/Chicago' AS cycle_at_ct,
                        cycle_at
                    FROM helios_signals
                    ORDER BY cycle_at DESC
                    LIMIT 1
                    """
                )
                row = c.fetchone()
        if not row:
            return {
                "success": True,
                "data": {
                    "available": False,
                    "message": "No HELIOS signals recorded yet.",
                    "action": None,
                    "skip_reason": None,
                    "detail": None,
                },
            }
        d = _serialize_row(dict(row))
        return {
            "success": True,
            "data": {
                "available": True,
                "action": d.get("action"),
                "spread_type": d.get("spread_type"),
                "long_strike": d.get("long_strike"),
                "short_strike": d.get("short_strike"),
                "skip_reason": d.get("skip_reason"),
                "detail": d.get("detail"),
                "spot": d.get("spot"),
                "vix": d.get("vix"),
                "cycle_at_ct": d.get("cycle_at_ct"),
                "signal_id": d.get("id"),
            },
        }
    except Exception as e:
        logger.error("HELIOS diagnose-trade error: %s", e)
        return {"success": True, "data": {
            "available": False, "message": str(e),
            "action": None, "skip_reason": None, "detail": None,
        }, "error": str(e)}
