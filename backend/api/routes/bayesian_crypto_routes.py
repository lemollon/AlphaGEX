"""
Bayesian Crypto Performance Tracker - API Routes.

Exposes the Bayesian edge-detection system for crypto trading strategies.
Answers the question: "Can you still make money in a choppy market?"

Endpoints:
  /status             - Tracker health and overview
  /strategies         - List all tracked strategies
  /estimate           - Current Bayesian win probability estimate
  /record-trade       - Feed a trade outcome
  /regime-breakdown   - Performance by market regime
  /choppy-metrics     - Small-gain strategy analysis (the $0.05/5min scenario)
  /equity-curve       - Historical equity with Bayesian confidence
  /daily-summary      - Daily aggregated performance
  /report             - Full comprehensive report
  /simulate           - Simulate the $0.05/5min scenario with Bayesian tracking
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bayesian-crypto", tags=["Bayesian Crypto Tracker"])

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Graceful imports
TRACKER_AVAILABLE = False
BayesianCryptoTracker = None
TradeOutcome = None
get_tracker = None
list_trackers = None
try:
    from quant.bayesian_crypto_tracker import (
        BayesianCryptoTracker,
        TradeOutcome,
        get_tracker,
        list_trackers,
        TimeWindow,
    )
    TRACKER_AVAILABLE = True
    logger.info("Bayesian Crypto Routes: Tracker loaded")
except ImportError as e:
    logger.warning(f"Bayesian Crypto Routes: Tracker not available: {e}")

DB_AVAILABLE = False
BayesianCryptoDatabase = None
_db_instance = None
try:
    from quant.bayesian_crypto_db import BayesianCryptoDatabase
    DB_AVAILABLE = True
    logger.info("Bayesian Crypto Routes: Database layer loaded")
except ImportError as e:
    logger.warning(f"Bayesian Crypto Routes: Database not available: {e}")


def _get_db():
    global _db_instance
    if not DB_AVAILABLE:
        return None
    if _db_instance is None:
        try:
            _db_instance = BayesianCryptoDatabase()
        except Exception as e:
            logger.error(f"Bayesian Crypto Routes: DB init failed: {e}")
            return None
    return _db_instance


def _get_or_load_tracker(strategy_name: str, starting_capital: float = 10.0):
    """Get a tracker, loading from DB if needed."""
    if not TRACKER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bayesian tracker module not available")

    tracker = get_tracker(strategy_name, starting_capital=starting_capital)

    # If tracker is fresh (no trades), try loading from DB
    if tracker.total_wins == 0 and tracker.total_losses == 0:
        db = _get_db()
        if db:
            state = db.load_tracker_state(strategy_name)
            if state:
                loaded = BayesianCryptoTracker.from_dict(state)
                # Replace the singleton
                from quant.bayesian_crypto_tracker import _trackers
                _trackers[strategy_name] = loaded
                return loaded

    return tracker


def _format_ct(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = datetime.now(CENTRAL_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S CT")


# ------------------------------------------------------------------
# Request/Response Models
# ------------------------------------------------------------------

class RecordTradeRequest(BaseModel):
    """Request to record a trade outcome."""
    trade_id: Optional[str] = Field(None, description="Unique trade ID (auto-generated if empty)")
    strategy_name: str = Field("crypto_default", description="Strategy name")
    symbol: str = Field("ETH", description="Trading symbol")
    side: str = Field(..., description="'long' or 'short'")
    entry_price: float = Field(..., description="Entry price")
    exit_price: float = Field(..., description="Exit price")
    pnl: float = Field(..., description="Realized P&L in USD")
    contracts: int = Field(1, description="Number of contracts")
    entry_time: Optional[str] = Field(None, description="ISO format entry time")
    exit_time: Optional[str] = Field(None, description="ISO format exit time")
    funding_regime: str = Field("UNKNOWN", description="Funding rate regime at trade time")
    leverage_regime: str = Field("UNKNOWN", description="Leverage regime")
    volatility_state: str = Field("NORMAL", description="Volatility state")
    ls_bias: str = Field("NEUTRAL", description="Long/short bias")


class SimulateRequest(BaseModel):
    """Request to simulate the choppy market scenario."""
    starting_capital: float = Field(10.0, description="Starting capital in USD")
    gain_per_interval: float = Field(0.05, description="Gain per interval in USD")
    interval_minutes: int = Field(5, description="Minutes per interval")
    hours: int = Field(168, description="Total hours to simulate (168 = 1 week)")
    win_rate: float = Field(0.55, description="Actual win rate (0-1)")
    loss_multiplier: float = Field(1.0, description="Loss size relative to gain (1.0 = symmetric)")


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/status")
async def bayesian_tracker_status():
    """Overall Bayesian crypto tracker system status."""
    if not TRACKER_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Bayesian crypto tracker module not loaded",
            "timestamp": _format_ct(),
        }

    strategies = list_trackers() if list_trackers else []
    db = _get_db()
    db_strategies = db.list_trackers() if db else []

    return {
        "status": "operational",
        "module_available": True,
        "database_available": DB_AVAILABLE,
        "active_strategies_in_memory": len(strategies),
        "strategies_in_db": len(db_strategies),
        "strategy_names": strategies,
        "db_strategies": db_strategies,
        "timestamp": _format_ct(),
    }


@router.get("/strategies")
async def list_strategies():
    """List all tracked strategies with summary stats."""
    db = _get_db()
    if db:
        strategies = db.list_trackers()
    else:
        strategies = []

    # Also include in-memory trackers not yet persisted
    if TRACKER_AVAILABLE and list_trackers:
        for name in list_trackers():
            if not any(s["strategy_name"] == name for s in strategies):
                tracker = get_tracker(name)
                est = tracker.get_estimate()
                strategies.append({
                    "strategy_name": name,
                    "starting_capital": tracker.starting_capital,
                    "bayesian_win_rate": round(est.mean, 4),
                    "total_trades": est.total_trades,
                    "cumulative_pnl": round(tracker.cumulative_pnl, 2),
                    "max_drawdown": round(tracker.max_drawdown, 2),
                    "source": "in_memory",
                })

    return {
        "strategies": strategies,
        "count": len(strategies),
        "timestamp": _format_ct(),
    }


@router.get("/estimate")
async def get_bayesian_estimate(
    strategy: str = Query("crypto_default", description="Strategy name"),
    starting_capital: float = Query(10.0, description="Starting capital"),
):
    """Get current Bayesian win probability estimate for a strategy."""
    tracker = _get_or_load_tracker(strategy, starting_capital)
    estimate = tracker.get_estimate()

    return {
        "strategy": strategy,
        "estimate": estimate.to_dict(),
        "interpretation": _interpret_estimate(estimate),
        "timestamp": _format_ct(),
    }


@router.post("/record-trade")
async def record_trade(req: RecordTradeRequest):
    """Record a trade outcome and update Bayesian estimates."""
    if not TRACKER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Tracker module not available")

    now = datetime.now(CENTRAL_TZ)
    trade_id = req.trade_id or f"trade_{uuid.uuid4().hex[:12]}"

    # Parse times
    entry_time = datetime.fromisoformat(req.entry_time) if req.entry_time else now - timedelta(minutes=5)
    exit_time = datetime.fromisoformat(req.exit_time) if req.exit_time else now

    hold_minutes = (exit_time - entry_time).total_seconds() / 60

    outcome = TradeOutcome(
        trade_id=trade_id,
        symbol=req.symbol,
        side=req.side,
        entry_price=req.entry_price,
        exit_price=req.exit_price,
        pnl=req.pnl,
        contracts=req.contracts,
        entry_time=entry_time,
        exit_time=exit_time,
        hold_duration_minutes=hold_minutes,
        funding_regime=req.funding_regime,
        leverage_regime=req.leverage_regime,
        volatility_state=req.volatility_state,
        ls_bias=req.ls_bias,
    )

    tracker = _get_or_load_tracker(req.strategy_name)
    estimate = tracker.record_trade(outcome)

    # Persist to DB
    db = _get_db()
    if db:
        db.save_trade(req.strategy_name, outcome)
        db.save_tracker_state(tracker)

        # Save equity snapshot
        equity = tracker.starting_capital + tracker.cumulative_pnl
        db.save_equity_snapshot(
            strategy_name=req.strategy_name,
            equity=equity,
            cumulative_pnl=tracker.cumulative_pnl,
            bayesian_win_rate=estimate.mean,
            edge_probability=estimate.edge_probability,
            total_trades=estimate.total_trades,
        )

    return {
        "status": "recorded",
        "trade_id": trade_id,
        "is_win": outcome.is_win,
        "pnl": outcome.pnl,
        "updated_estimate": estimate.to_dict(),
        "interpretation": _interpret_estimate(estimate),
        "timestamp": _format_ct(),
    }


@router.get("/regime-breakdown")
async def regime_breakdown(
    strategy: str = Query("crypto_default", description="Strategy name"),
):
    """Performance breakdown by crypto market regime."""
    tracker = _get_or_load_tracker(strategy)

    return {
        "strategy": strategy,
        "funding_regimes": tracker.get_regime_breakdown(),
        "volatility_states": tracker.get_volatility_breakdown(),
        "insight": _regime_insight(tracker),
        "timestamp": _format_ct(),
    }


@router.get("/choppy-metrics")
async def choppy_market_metrics(
    strategy: str = Query("crypto_default", description="Strategy name"),
):
    """
    Choppy market analysis - the core question.

    Maps to the scenario: $10 start, $0.05/5min, 24/7.
    Shows actual vs projected performance with Bayesian confidence.
    """
    tracker = _get_or_load_tracker(strategy)
    metrics = tracker.get_choppy_market_metrics()
    estimate = tracker.get_estimate()

    # The theoretical scenario for comparison
    theoretical = _calculate_theoretical(
        starting_capital=tracker.starting_capital,
        gain_per_interval=0.05,
        interval_minutes=5,
    )

    return {
        "strategy": strategy,
        "actual_metrics": metrics.to_dict(),
        "theoretical_comparison": theoretical,
        "bayesian_confidence": {
            "win_rate": round(estimate.mean, 4),
            "edge_probability": round(estimate.edge_probability, 4),
            "verdict": estimate.verdict.value,
            "trades_analyzed": estimate.total_trades,
        },
        "reality_check": _reality_check(metrics, estimate),
        "timestamp": _format_ct(),
    }


@router.get("/equity-curve")
async def equity_curve(
    strategy: str = Query("crypto_default", description="Strategy name"),
    days: int = Query(30, description="Number of days"),
):
    """Historical equity curve with Bayesian confidence overlay."""
    db = _get_db()
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    curve = db.get_equity_curve(strategy, days)

    return {
        "strategy": strategy,
        "days": days,
        "data_points": len(curve),
        "curve": curve,
        "timestamp": _format_ct(),
    }


@router.get("/trades")
async def get_trades(
    strategy: str = Query("crypto_default", description="Strategy name"),
    limit: int = Query(50, description="Max trades to return"),
    offset: int = Query(0, description="Offset for pagination"),
):
    """Get trade history for a strategy."""
    db = _get_db()
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    trades = db.get_trades(strategy, limit=limit, offset=offset)
    total = db.get_trade_count(strategy)

    return {
        "strategy": strategy,
        "trades": trades,
        "count": len(trades),
        "total": total,
        "timestamp": _format_ct(),
    }


@router.get("/daily-summary")
async def daily_summary(
    strategy: str = Query("crypto_default", description="Strategy name"),
    days: int = Query(30, description="Number of days"),
):
    """Daily aggregated performance summary."""
    db = _get_db()
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    summary = db.get_daily_summary(strategy, days)

    return {
        "strategy": strategy,
        "days": days,
        "daily_data": summary,
        "timestamp": _format_ct(),
    }


@router.get("/report")
async def full_report(
    strategy: str = Query("crypto_default", description="Strategy name"),
):
    """Comprehensive Bayesian performance report."""
    tracker = _get_or_load_tracker(strategy)
    report = tracker.get_full_report()

    return {
        "strategy": strategy,
        "report": report,
        "timestamp": _format_ct(),
    }


@router.post("/simulate")
async def simulate_choppy_market(req: SimulateRequest):
    """
    Simulate the choppy market scenario with Bayesian tracking.

    Default: $10 start, $0.05/5min, 55% win rate, 1 week.
    Shows how Bayesian confidence evolves over time.
    """
    import random

    total_intervals = int((req.hours * 60) / req.interval_minutes)
    tracker = BayesianCryptoTracker(
        strategy_name=f"simulation_{uuid.uuid4().hex[:8]}",
        starting_capital=req.starting_capital,
    )

    snapshots = []
    snapshot_interval = max(1, total_intervals // 100)  # ~100 data points

    for i in range(total_intervals):
        won = random.random() < req.win_rate
        if won:
            pnl = req.gain_per_interval
        else:
            pnl = -req.gain_per_interval * req.loss_multiplier

        now = datetime.now(CENTRAL_TZ) + timedelta(minutes=i * req.interval_minutes)

        outcome = TradeOutcome(
            trade_id=f"sim_{i}",
            symbol="ETH",
            side="long",
            entry_price=100.0,
            exit_price=100.0 + (pnl if won else -pnl),
            pnl=pnl,
            contracts=1,
            entry_time=now - timedelta(minutes=req.interval_minutes),
            exit_time=now,
            hold_duration_minutes=req.interval_minutes,
        )

        estimate = tracker.record_trade(outcome)

        if i % snapshot_interval == 0 or i == total_intervals - 1:
            snapshots.append({
                "interval": i,
                "equity": round(tracker.starting_capital + tracker.cumulative_pnl, 4),
                "cumulative_pnl": round(tracker.cumulative_pnl, 4),
                "bayesian_win_rate": round(estimate.mean, 4),
                "ci_lower": round(estimate.ci_lower, 4),
                "ci_upper": round(estimate.ci_upper, 4),
                "edge_probability": round(estimate.edge_probability, 4),
                "verdict": estimate.verdict.value,
                "kelly_fraction": round(estimate.kelly_fraction, 4),
            })

    final = tracker.get_estimate()

    return {
        "simulation": {
            "starting_capital": req.starting_capital,
            "gain_per_interval": req.gain_per_interval,
            "interval_minutes": req.interval_minutes,
            "hours": req.hours,
            "win_rate": req.win_rate,
            "total_intervals": total_intervals,
        },
        "results": {
            "final_equity": round(tracker.starting_capital + tracker.cumulative_pnl, 4),
            "total_pnl": round(tracker.cumulative_pnl, 4),
            "total_return_pct": round(
                (tracker.cumulative_pnl / max(1, tracker.starting_capital)) * 100, 2
            ),
            "actual_win_rate": round(
                tracker.total_wins / max(1, tracker.total_wins + tracker.total_losses), 4
            ),
            "bayesian_estimate": final.to_dict(),
            "max_drawdown": round(tracker.max_drawdown, 4),
            "streaks": tracker.streaks.to_dict(),
        },
        "evolution": snapshots,
        "reality_check": {
            "theoretical_pnl": round(
                total_intervals * req.gain_per_interval * (2 * req.win_rate - 1), 2
            ),
            "theoretical_return_pct": round(
                (total_intervals * req.gain_per_interval * (2 * req.win_rate - 1))
                / max(1, req.starting_capital) * 100, 2
            ),
            "note": (
                "At 55% win rate with symmetric payoffs, expected edge = 10% of intervals. "
                f"Expected P&L = {total_intervals} × ${req.gain_per_interval} × 0.10 = "
                f"${round(total_intervals * req.gain_per_interval * 0.10, 2)}"
            ),
        },
        "timestamp": _format_ct(),
    }


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def _interpret_estimate(estimate) -> Dict:
    """Human-readable interpretation of Bayesian estimate."""
    total = estimate.total_trades

    if total == 0:
        return {
            "summary": "No trades recorded yet. Feed trades to start Bayesian analysis.",
            "confidence_level": "none",
            "recommendation": "Record at least 10 trades for initial estimates.",
        }

    if total < 10:
        return {
            "summary": f"Cold start phase ({total}/10 trades). Estimates are unreliable.",
            "confidence_level": "very_low",
            "recommendation": f"Need {10 - total} more trades for initial reliability.",
        }

    if total < 30:
        confidence = "low"
        rec = f"Approaching statistical significance. {30 - total} more trades recommended."
    elif total < 100:
        confidence = "moderate"
        rec = "Building confidence. Continue tracking for tighter credible intervals."
    else:
        confidence = "high"
        rec = "Sufficient data for reliable Bayesian inference."

    verdict_messages = {
        "CONFIRMED_EDGE": "Strong statistical evidence of genuine edge. Strategy is profitable.",
        "PROBABLE_EDGE": "Edge likely real but needs more data to confirm at 95% confidence.",
        "INCONCLUSIVE": "Cannot determine if edge is real or noise. Keep trading and tracking.",
        "PROBABLY_NO_EDGE": "Evidence suggests no edge. Consider adjusting strategy.",
        "NO_EDGE": "Strong evidence of NO edge. Strategy is likely not profitable.",
    }

    return {
        "summary": verdict_messages.get(estimate.verdict.value, "Unknown"),
        "confidence_level": confidence,
        "win_rate_range": f"{estimate.ci_lower:.1%} - {estimate.ci_upper:.1%}",
        "edge_probability": f"{estimate.edge_probability:.1%} chance edge is real",
        "recommendation": rec,
    }


def _regime_insight(tracker) -> str:
    """Generate insight about regime performance."""
    if not tracker.regime_stats:
        return "No regime data yet. Trades need funding_regime context."

    best_regime = None
    best_wr = 0
    for name, stats in tracker.regime_stats.items():
        if stats.total_trades >= 3 and stats.win_rate > best_wr:
            best_wr = stats.win_rate
            best_regime = name

    if best_regime:
        return (
            f"Best performing regime: {best_regime} "
            f"({best_wr:.0%} win rate). "
            f"Consider concentrating trading in this regime."
        )
    return "Need more trades per regime for meaningful insight."


def _calculate_theoretical(
    starting_capital: float,
    gain_per_interval: float,
    interval_minutes: int,
) -> Dict:
    """Calculate the theoretical maximum (100% win rate) scenario."""
    intervals_per_hour = 60 / interval_minutes
    intervals_per_day = intervals_per_hour * 24
    intervals_per_week = intervals_per_day * 7

    weekly_profit = intervals_per_week * gain_per_interval

    return {
        "scenario": f"${gain_per_interval}/interval, every {interval_minutes}min, 24/7",
        "intervals_per_hour": int(intervals_per_hour),
        "intervals_per_day": int(intervals_per_day),
        "intervals_per_week": int(intervals_per_week),
        "weekly_profit_if_100pct_wins": round(weekly_profit, 2),
        "weekly_return_pct": round((weekly_profit / max(1, starting_capital)) * 100, 2),
        "annualized_return_pct": round(
            (weekly_profit / max(1, starting_capital)) * 52 * 100, 2
        ),
        "reality_note": (
            "100% win rate is impossible. At 55% win rate with symmetric payoffs, "
            f"expect ~${round(weekly_profit * 0.10, 2)}/week "
            f"({round((weekly_profit * 0.10 / max(1, starting_capital)) * 100, 1)}% return)."
        ),
    }


def _reality_check(metrics, estimate) -> Dict:
    """Reality check comparing actual vs theoretical performance."""
    checks = []

    # Annualized return sanity
    if metrics.annualized_return_pct > 500:
        checks.append({
            "flag": "EXTREME_RETURN",
            "message": (
                f"Annualized return of {metrics.annualized_return_pct:.0f}% is unrealistic "
                "for sustained performance. Likely overfitting or insufficient data."
            ),
        })

    # Sharpe ratio check
    if metrics.sharpe_ratio > 3.0:
        checks.append({
            "flag": "HIGH_SHARPE",
            "message": (
                f"Sharpe ratio of {metrics.sharpe_ratio:.2f} is suspiciously high. "
                "The best hedge funds target 2.0-3.0. Verify data quality."
            ),
        })

    # Drawdown warning
    if metrics.max_drawdown > metrics.starting_capital * 0.5:
        checks.append({
            "flag": "LARGE_DRAWDOWN",
            "message": (
                f"Max drawdown of ${metrics.max_drawdown:.2f} exceeds 50% of "
                f"starting capital (${metrics.starting_capital:.2f}). High risk of ruin."
            ),
        })

    # Edge confidence
    if estimate.total_trades >= 30 and estimate.edge_probability < 0.5:
        checks.append({
            "flag": "NO_STATISTICAL_EDGE",
            "message": (
                f"After {estimate.total_trades} trades, only {estimate.edge_probability:.0%} "
                "probability of real edge. Consider stopping or adjusting strategy."
            ),
        })

    if not checks:
        checks.append({
            "flag": "OK",
            "message": "No red flags detected. Continue monitoring.",
        })

    return {
        "checks": checks,
        "bottom_line": (
            "Yes, you can make money in a choppy market - "
            "IF the Bayesian tracker confirms a real edge (>80% edge probability)."
            if estimate.edge_probability >= 0.8 or estimate.total_trades < 10
            else "Edge not yet confirmed. Keep tracking to determine if your strategy has genuine alpha."
        ),
    }
