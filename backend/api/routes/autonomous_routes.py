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
        logs = pd.read_sql_query("""
            SELECT * FROM autonomous_trader_logs
            ORDER BY timestamp DESC
            LIMIT %s
        """, conn, params=(int(limit),))
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
        return {"success": True, "data": leaderboard, "leaderboard": leaderboard}

    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


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

        risk_data = {
            "total_exposure": round(exposure, 2),
            "unrealized_pnl": round(unrealized, 2),
            "capital": capital,
            "exposure_pct": round(exposure / capital * 100, 2) if capital > 0 else 0,
            "max_drawdown_pct": 0,  # Will be calculated from equity snapshots
            "daily_loss_limit_pct": 2.0,
            "daily_loss_remaining": capital * 0.02,
            "risk_level": "LOW" if (exposure / capital * 100 if capital > 0 else 0) < 20 else "MEDIUM" if (exposure / capital * 100 if capital > 0 else 0) < 50 else "HIGH"
        }
        return {
            "success": True,
            "data": risk_data,
            "risk_status": risk_data  # Backwards compat
        }

    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@router.get("/risk/metrics")
async def get_risk_metrics():
    """Get detailed risk metrics"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get latest equity snapshot
        c.execute("""
            SELECT drawdown_pct, cumulative_pnl, equity
            FROM autonomous_equity_snapshots
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = c.fetchone()

        # Calculate win rate from closed trades
        c.execute("""
            SELECT COUNT(*), SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)
            FROM autonomous_closed_trades
        """)
        trade_stats = c.fetchone()
        total_trades = trade_stats[0] or 0
        wins = trade_stats[1] or 0
        win_rate = round((wins / total_trades * 100), 1) if total_trades > 0 else 0

        metrics = {
            'max_drawdown_pct': round(float(row[0] or 0), 2) if row else 0,
            'sharpe_ratio': 0,  # Not tracked in database
            'win_rate': win_rate,
            'total_trades': total_trades,
            'wins': wins,
            'losses': total_trades - wins
        }

        conn.close()
        return {"success": True, "data": metrics, "metrics": metrics}

    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@router.get("/ml/model-status")
async def get_ml_model_status():
    """Get ML model training status"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT model_name, accuracy, created_at, training_samples
            FROM ml_models
            ORDER BY created_at DESC
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

        # Add overall status for frontend
        model_status = {
            "models": models,
            "total_models": len(models),
            "latest_model": models[0] if models else None,
            "is_trained": len(models) > 0,
            "needs_training": len(models) == 0
        }
        return {"success": True, "data": model_status, "models": models}

    except Exception as e:
        return {"success": False, "error": str(e), "data": {"models": [], "is_trained": False}, "models": []}


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


@router.get("/positions")
async def get_autonomous_positions(status: str = "open"):
    """Get positions (open, closed, or all)"""
    try:
        conn = get_connection()
        c = conn.cursor()

        positions = []

        if status in ("open", "all"):
            c.execute("""
                SELECT id, symbol, strategy, strike, option_type, contracts,
                       entry_price, current_price, unrealized_pnl, entry_date,
                       'open' as status
                FROM autonomous_open_positions
                ORDER BY entry_date DESC
            """)
            for row in c.fetchall():
                positions.append({
                    'id': row[0],
                    'symbol': row[1],
                    'strategy': row[2],
                    'strike': float(row[3]) if row[3] else 0,
                    'option_type': row[4],
                    'contracts': row[5],
                    'entry_price': float(row[6]) if row[6] else 0,
                    'current_price': float(row[7]) if row[7] else 0,
                    'pnl': float(row[8]) if row[8] else 0,
                    'entry_date': str(row[9]) if row[9] else None,
                    'status': 'open'
                })

        if status in ("closed", "all"):
            c.execute("""
                SELECT id, symbol, strategy, strike, option_type, contracts,
                       entry_price, exit_price, realized_pnl, entry_date,
                       'closed' as status
                FROM autonomous_closed_trades
                ORDER BY COALESCE(exit_date, entry_date) DESC
                LIMIT 50
            """)
            for row in c.fetchall():
                positions.append({
                    'id': row[0],
                    'symbol': row[1],
                    'strategy': row[2],
                    'strike': float(row[3]) if row[3] else 0,
                    'option_type': row[4],
                    'contracts': row[5],
                    'entry_price': float(row[6]) if row[6] else 0,
                    'exit_price': float(row[7]) if row[7] else 0,
                    'pnl': float(row[8]) if row[8] else 0,
                    'entry_date': str(row[9]) if row[9] else None,
                    'status': 'closed'
                })

        conn.close()
        return {"success": True, "data": positions, "positions": positions}

    except Exception as e:
        return {"success": False, "error": str(e), "positions": []}


@router.get("/orphaned-orders")
async def get_orphaned_orders(include_resolved: bool = False):
    """
    Get orphaned orders across all bots that need manual intervention.

    Orphaned orders occur when:
    - One leg of a spread closes but the other fails
    - Order fills but DB update fails
    - Rollback of a spread fails
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        if include_resolved:
            c.execute("""
                SELECT id, bot_name, order_id, order_type, ticker, expiration, strikes,
                       contracts, reason, error_details, resolved, resolved_at, created_at
                FROM orphaned_orders
                ORDER BY created_at DESC
                LIMIT 100
            """)
        else:
            c.execute("""
                SELECT id, bot_name, order_id, order_type, ticker, expiration, strikes,
                       contracts, reason, error_details, resolved, resolved_at, created_at
                FROM orphaned_orders
                WHERE resolved = FALSE
                ORDER BY created_at DESC
            """)

        orders = []
        for row in c.fetchall():
            orders.append({
                'id': row[0],
                'bot_name': row[1],
                'order_id': row[2],
                'order_type': row[3],
                'ticker': row[4],
                'expiration': str(row[5]) if row[5] else None,
                'strikes': row[6],
                'contracts': row[7],
                'reason': row[8],
                'error_details': row[9],
                'resolved': row[10],
                'resolved_at': str(row[11]) if row[11] else None,
                'created_at': str(row[12]) if row[12] else None
            })

        conn.close()
        return {
            "success": True,
            "data": orders,
            "count": len(orders),
            "unresolved_count": len([o for o in orders if not o['resolved']])
        }

    except Exception as e:
        return {"success": False, "error": str(e), "data": [], "count": 0}


@router.get("/partial-close-positions")
async def get_partial_close_positions():
    """
    Get positions in partial_close state across all bots.

    Partial close occurs when one leg of a multi-leg position closes
    but the other leg(s) fail to close, leaving a partial position.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        positions = []

        # Check ARES positions
        try:
            c.execute("""
                SELECT position_id, ticker, expiration, 'ARES' as bot_name,
                       close_reason, close_time, realized_pnl
                FROM ares_positions
                WHERE status = 'partial_close'
                ORDER BY COALESCE(close_time, open_time) DESC
            """)
            for row in c.fetchall():
                positions.append({
                    'position_id': row[0],
                    'ticker': row[1],
                    'expiration': str(row[2]) if row[2] else None,
                    'bot_name': row[3],
                    'close_reason': row[4],
                    'close_time': str(row[5]) if row[5] else None,
                    'realized_pnl': float(row[6]) if row[6] else 0
                })
        except Exception:
            pass  # Table might not exist yet

        # Check ATHENA positions
        try:
            c.execute("""
                SELECT position_id, ticker, expiration, 'ATHENA' as bot_name,
                       close_reason, close_time, realized_pnl
                FROM athena_positions
                WHERE status = 'partial_close'
                ORDER BY COALESCE(close_time, open_time) DESC
            """)
            for row in c.fetchall():
                positions.append({
                    'position_id': row[0],
                    'ticker': row[1],
                    'expiration': str(row[2]) if row[2] else None,
                    'bot_name': row[3],
                    'close_reason': row[4],
                    'close_time': str(row[5]) if row[5] else None,
                    'realized_pnl': float(row[6]) if row[6] else 0
                })
        except Exception:
            pass

        # Check PEGASUS positions
        try:
            c.execute("""
                SELECT position_id, ticker, expiration, 'PEGASUS' as bot_name,
                       close_reason, close_time, realized_pnl
                FROM pegasus_positions
                WHERE status = 'partial_close'
                ORDER BY COALESCE(close_time, open_time) DESC
            """)
            for row in c.fetchall():
                positions.append({
                    'position_id': row[0],
                    'ticker': row[1],
                    'expiration': str(row[2]) if row[2] else None,
                    'bot_name': row[3],
                    'close_reason': row[4],
                    'close_time': str(row[5]) if row[5] else None,
                    'realized_pnl': float(row[6]) if row[6] else 0
                })
        except Exception:
            pass

        conn.close()
        return {
            "success": True,
            "data": positions,
            "count": len(positions),
            "by_bot": {
                "ARES": len([p for p in positions if p['bot_name'] == 'ARES']),
                "ATHENA": len([p for p in positions if p['bot_name'] == 'ATHENA']),
                "PEGASUS": len([p for p in positions if p['bot_name'] == 'PEGASUS'])
            }
        }

    except Exception as e:
        return {"success": False, "error": str(e), "data": [], "count": 0}


@router.post("/orphaned-orders/{order_id}/resolve")
async def resolve_orphaned_order(order_id: int, resolved_by: str = "manual"):
    """Mark an orphaned order as resolved."""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            UPDATE orphaned_orders
            SET resolved = TRUE,
                resolved_at = NOW(),
                resolved_by = %s
            WHERE id = %s
            RETURNING id
        """, (resolved_by, order_id))

        result = c.fetchone()
        conn.commit()
        conn.close()

        if result:
            return {"success": True, "message": f"Order {order_id} marked as resolved"}
        else:
            return {"success": False, "error": f"Order {order_id} not found"}

    except Exception as e:
        return {"success": False, "error": str(e)}
