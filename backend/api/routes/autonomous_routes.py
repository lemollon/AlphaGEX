"""
Autonomous Trader API routes - Logs, competition, backtests, risk, and ML status.
"""

from fastapi import APIRouter, HTTPException

from database_adapter import get_connection

router = APIRouter(prefix="/api/autonomous", tags=["Autonomous Trader"])


@router.get("/logs")
async def get_autonomous_logs(limit: int = 100):
    """Get autonomous trader activity logs"""
    try:
        import pandas as pd

        conn = get_connection()
        logs = pd.read_sql_query(f"""
            SELECT * FROM autonomous_trader_logs
            ORDER BY timestamp DESC
            LIMIT {int(limit)}
        """, conn)
        conn.close()

        return {"success": True, "data": logs.to_dict('records') if not logs.empty else []}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/competition/leaderboard")
async def get_competition_leaderboard():
    """Get strategy competition leaderboard"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT
                strategy,
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(realized_pnl) as total_pnl,
                AVG(realized_pnl) as avg_pnl
            FROM autonomous_closed_trades
            GROUP BY strategy
            ORDER BY total_pnl DESC
        """)

        leaderboard = []
        for row in c.fetchall():
            total = row[1] or 0
            wins = row[2] or 0
            leaderboard.append({
                'strategy': row[0],
                'total_trades': total,
                'wins': wins,
                'win_rate': round(wins / total * 100, 1) if total > 0 else 0,
                'total_pnl': round(float(row[3] or 0), 2),
                'avg_pnl': round(float(row[4] or 0), 2)
            })

        conn.close()
        return {"success": True, "leaderboard": leaderboard}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/backtests/all-patterns")
async def get_all_pattern_backtests():
    """Get backtest results for all patterns"""
    try:
        import pandas as pd

        conn = get_connection()
        results = pd.read_sql_query("""
            SELECT * FROM backtest_results
            ORDER BY timestamp DESC
            LIMIT 100
        """, conn)
        conn.close()

        return {"success": True, "data": results.to_dict('records') if not results.empty else []}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/risk/status")
async def get_risk_status():
    """Get current risk management status"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get open positions value
        c.execute("SELECT COALESCE(SUM(entry_price * contracts * 100), 0) FROM autonomous_open_positions")
        exposure = float(c.fetchone()[0] or 0)

        # Get unrealized P&L
        c.execute("SELECT COALESCE(SUM(unrealized_pnl), 0) FROM autonomous_open_positions")
        unrealized = float(c.fetchone()[0] or 0)

        # Get config
        c.execute("SELECT value FROM autonomous_config WHERE key = 'capital'")
        row = c.fetchone()
        capital = float(row[0]) if row else 1000000

        conn.close()

        return {
            "success": True,
            "risk_status": {
                "total_exposure": round(exposure, 2),
                "unrealized_pnl": round(unrealized, 2),
                "capital": capital,
                "exposure_pct": round(exposure / capital * 100, 2) if capital > 0 else 0
            }
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/risk/metrics")
async def get_risk_metrics():
    """Get detailed risk metrics"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get latest equity snapshot
        c.execute("""
            SELECT max_drawdown_pct, sharpe_ratio, win_rate
            FROM autonomous_equity_snapshots
            ORDER BY snapshot_date DESC, snapshot_time DESC
            LIMIT 1
        """)
        row = c.fetchone()

        metrics = {
            'max_drawdown_pct': round(float(row[0] or 0), 2) if row else 0,
            'sharpe_ratio': round(float(row[1] or 0), 2) if row else 0,
            'win_rate': round(float(row[2] or 0), 1) if row else 0
        }

        conn.close()
        return {"success": True, "metrics": metrics}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/ml/model-status")
async def get_ml_model_status():
    """Get ML model training status"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT model_name, accuracy, last_trained, training_samples
            FROM ml_models
            ORDER BY last_trained DESC
            LIMIT 5
        """)

        models = []
        for row in c.fetchall():
            models.append({
                'model_name': row[0],
                'accuracy': round(float(row[1] or 0), 3),
                'last_trained': str(row[2]) if row[2] else None,
                'training_samples': row[3]
            })

        conn.close()
        return {"success": True, "models": models}

    except Exception as e:
        return {"success": False, "error": str(e), "models": []}


@router.get("/ml/predictions/recent")
async def get_recent_ml_predictions():
    """Get recent ML predictions"""
    try:
        import pandas as pd

        conn = get_connection()
        predictions = pd.read_sql_query("""
            SELECT * FROM ml_predictions
            ORDER BY timestamp DESC
            LIMIT 20
        """, conn)
        conn.close()

        return {"success": True, "data": predictions.to_dict('records') if not predictions.empty else []}

    except Exception as e:
        return {"success": False, "error": str(e), "data": []}
