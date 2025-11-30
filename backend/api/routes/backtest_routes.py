"""
Backtesting API routes.

Handles backtest results, strategy analysis, and smart recommendations.
"""

import math
from datetime import datetime

from fastapi import APIRouter, HTTPException
import psycopg2.extras

from database_adapter import get_connection

router = APIRouter(prefix="/api/backtests", tags=["Backtesting"])


def safe_round(value, decimals=2, default=0):
    """Round a value, returning default if inf/nan"""
    if value is None:
        return default
    try:
        float_val = float(value)
        if math.isnan(float_val) or math.isinf(float_val):
            return default
        return round(float_val, decimals)
    except (ValueError, TypeError, OverflowError):
        return default


@router.get("/results")
async def get_backtest_results(strategy_name: str = None, limit: int = 50):
    """Get backtest results for all strategies or specific strategy"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if strategy_name:
            c.execute('''
                SELECT *
                FROM backtest_results
                WHERE strategy_name = %s
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (strategy_name, int(limit)))
        else:
            c.execute('''
                SELECT *
                FROM backtest_results
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (int(limit),))

        results = []
        for row in c.fetchall():
            results.append({
                'id': row['id'],
                'timestamp': row['timestamp'].isoformat() if row['timestamp'] else None,
                'strategy_name': row['strategy_name'],
                'symbol': row.get('symbol', 'SPY'),
                'start_date': str(row.get('start_date', '')),
                'end_date': str(row.get('end_date', '')),
                'total_trades': row.get('total_trades', 0),
                'winning_trades': row.get('winning_trades', 0),
                'losing_trades': row.get('losing_trades', 0),
                'win_rate': safe_round(row.get('win_rate', 0)),
                'avg_win_pct': safe_round(row.get('avg_win_pct', 0)),
                'avg_loss_pct': safe_round(row.get('avg_loss_pct', 0)),
                'largest_win_pct': safe_round(row.get('largest_win_pct', 0)),
                'largest_loss_pct': safe_round(row.get('largest_loss_pct', 0)),
                'expectancy_pct': safe_round(row.get('expectancy_pct', 0)),
                'total_return_pct': safe_round(row.get('total_return_pct', 0)),
                'max_drawdown_pct': safe_round(row.get('max_drawdown_pct', 0)),
                'sharpe_ratio': safe_round(row.get('sharpe_ratio', 0)),
                'avg_trade_duration_days': safe_round(row.get('avg_trade_duration_days', 0))
            })

        conn.close()

        return {
            "success": True,
            "data": {"results": results}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_backtest_summary():
    """Get summary statistics across all backtests"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT
                COUNT(DISTINCT strategy_name) as total_strategies,
                AVG(win_rate) as avg_win_rate,
                AVG(expectancy_pct) as avg_expectancy,
                MAX(expectancy_pct) as best_expectancy,
                MIN(expectancy_pct) as worst_expectancy,
                SUM(total_trades) as total_trades_tested
            FROM backtest_results
            WHERE timestamp = (
                SELECT MAX(timestamp) FROM backtest_results
            )
        ''')
        summary = c.fetchone()
        conn.close()

        return {
            "success": True,
            "data": {
                "total_strategies": summary['total_strategies'] or 0,
                "avg_win_rate": safe_round(summary['avg_win_rate'] or 0),
                "avg_expectancy": safe_round(summary['avg_expectancy'] or 0),
                "best_expectancy": safe_round(summary['best_expectancy'] or 0),
                "worst_expectancy": safe_round(summary['worst_expectancy'] or 0),
                "total_trades_tested": summary['total_trades_tested'] or 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-strategies")
async def get_best_strategies(min_expectancy: float = 0.5, limit: int = 10):
    """Get top performing strategies from backtests"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT
                strategy_name,
                win_rate,
                expectancy_pct,
                total_trades,
                avg_win_pct,
                avg_loss_pct,
                sharpe_ratio,
                max_drawdown_pct
            FROM backtest_results
            WHERE timestamp = (SELECT MAX(timestamp) FROM backtest_results)
              AND expectancy_pct >= %s
            ORDER BY expectancy_pct DESC
            LIMIT %s
        ''', (min_expectancy, int(limit)))

        strategies = []
        for row in c.fetchall():
            strategies.append({
                'strategy_name': row['strategy_name'],
                'win_rate': safe_round(row['win_rate']),
                'expectancy_pct': safe_round(row['expectancy_pct']),
                'total_trades': row['total_trades'],
                'avg_win_pct': safe_round(row['avg_win_pct']),
                'avg_loss_pct': safe_round(row['avg_loss_pct']),
                'sharpe_ratio': safe_round(row['sharpe_ratio']),
                'max_drawdown_pct': safe_round(row['max_drawdown_pct'])
            })

        conn.close()

        return {
            "success": True,
            "data": strategies
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_backtests(lookback_days: int = 90):
    """
    Run backtests for all pattern strategies.

    This triggers the autonomous_backtest_engine which:
    1. Queries historical regime_signals from database
    2. Calculates win rates, expectancy, etc.
    3. Saves results to backtest_results table
    4. Updates strategy_stats.json for Kelly sizing
    """
    try:
        from backtest.autonomous_backtest_engine import get_backtester

        backtester = get_backtester()
        results = backtester.backtest_all_patterns_and_save(
            lookback_days=lookback_days,
            save_to_db=True
        )

        # Count patterns with actual data
        patterns_with_data = sum(1 for r in results if r.get('total_signals', 0) > 0)

        return {
            "success": True,
            "message": f"Backtest complete - {patterns_with_data} patterns with signals",
            "data": {
                "total_patterns": len(results),
                "patterns_with_signals": patterns_with_data,
                "lookback_days": lookback_days,
                "timestamp": datetime.now().isoformat(),
                "results_summary": [
                    {
                        "pattern": r['pattern'],
                        "signals": r['total_signals'],
                        "win_rate": safe_round(r['win_rate']),
                        "expectancy": safe_round(r['expectancy'])
                    }
                    for r in results[:10]  # Top 10
                ]
            }
        }
    except ImportError as e:
        # Fallback to multi-strategy backtester
        try:
            from multi_strategy_backtester import MultiStrategyBacktester
            backtester = MultiStrategyBacktester()
            results = backtester.run_all_backtests(lookback_days=lookback_days, save_to_db=True)
            return {
                "success": True,
                "message": f"Ran {len(results)} strategy backtests (fallback mode)",
                "data": {
                    "strategies_tested": len(results),
                    "timestamp": datetime.now().isoformat()
                }
            }
        except ImportError:
            raise HTTPException(status_code=500, detail=f"No backtester available: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/smart-recommendations")
async def get_smart_recommendations():
    """Get AI-powered strategy recommendations based on backtest results"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get latest backtest results
        c.execute('''
            SELECT
                strategy_name,
                win_rate,
                expectancy_pct,
                total_trades,
                sharpe_ratio,
                max_drawdown_pct
            FROM backtest_results
            WHERE timestamp = (SELECT MAX(timestamp) FROM backtest_results)
            ORDER BY expectancy_pct DESC
        ''')
        strategies = c.fetchall()
        conn.close()

        if not strategies:
            return {
                "success": True,
                "data": {
                    "recommendations": [],
                    "message": "No backtest data available. Run backtests first."
                }
            }

        recommendations = []
        for s in strategies[:5]:  # Top 5
            if s['expectancy_pct'] > 1.0 and s['win_rate'] > 50:
                rec_type = "STRONG_BUY"
                reasoning = f"High expectancy ({s['expectancy_pct']:.1f}%) with solid win rate ({s['win_rate']:.0f}%)"
            elif s['expectancy_pct'] > 0.5:
                rec_type = "CONSIDER"
                reasoning = f"Positive expectancy ({s['expectancy_pct']:.1f}%) but verify with current conditions"
            else:
                rec_type = "CAUTION"
                reasoning = f"Low expectancy ({s['expectancy_pct']:.1f}%). May need optimization."

            recommendations.append({
                "strategy_name": s['strategy_name'],
                "recommendation": rec_type,
                "reasoning": reasoning,
                "win_rate": safe_round(s['win_rate']),
                "expectancy_pct": safe_round(s['expectancy_pct']),
                "sharpe_ratio": safe_round(s['sharpe_ratio']),
                "max_drawdown_pct": safe_round(s['max_drawdown_pct'])
            })

        return {
            "success": True,
            "data": {
                "recommendations": recommendations,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy-stats")
async def get_strategy_stats_endpoint():
    """
    Get current strategy statistics from strategy_stats.json.
    These are updated by backtests and used for Kelly position sizing.
    """
    try:
        from core.strategy_stats import get_strategy_stats

        stats = get_strategy_stats()

        # Count sources
        backtest_count = sum(1 for s in stats.values() if s.get('source') == 'backtest')
        initial_count = sum(1 for s in stats.values() if s.get('source') == 'initial_estimate')

        return {
            "success": True,
            "data": stats,
            "summary": {
                "total_strategies": len(stats),
                "from_backtest": backtest_count,
                "initial_estimates": initial_count,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
