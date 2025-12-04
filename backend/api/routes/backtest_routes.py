"""
Backtesting API routes.

Handles backtest results, strategy analysis, and smart recommendations.

ASYNC PROCESSING:
Long-running backtests are now queued and processed by a background worker.
This prevents browser timeouts and crashes.

Usage:
    POST /api/backtests/run      -> Enqueues job, returns job_id immediately
    GET /api/backtests/job/{id}  -> Check job status and progress
    GET /api/backtests/jobs      -> List recent jobs
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import psycopg2.extras

from database_adapter import get_connection


class BacktestRunConfig(BaseModel):
    """Configuration for running backtests"""
    lookback_days: int = 90
    strategies: Optional[List[str]] = None
    async_mode: bool = True  # NEW: Default to async processing


class SPXBacktestConfig(BaseModel):
    """Configuration for SPX wheel backtests"""
    start_date: str = "2024-01-01"
    end_date: Optional[str] = None
    initial_capital: float = 100000
    put_delta: float = 0.20
    dte_target: int = 45
    max_margin_pct: float = 0.50
    use_ml_scoring: bool = True
    ml_min_score: float = 0.40
    async_mode: bool = True  # NEW: Default to async processing


# Import centralized utilities
from backend.api.utils import safe_round, clean_dict_for_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtests", tags=["Backtesting"])


# Note: safe_round is imported from backend.api.utils


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
async def run_backtests(config: BacktestRunConfig = BacktestRunConfig()):
    """
    Run backtests for all pattern strategies.

    ASYNC MODE (default):
    - Enqueues job to background worker
    - Returns job_id immediately
    - Use GET /api/backtests/job/{job_id} to check progress

    SYNC MODE (async_mode=false):
    - Runs backtest synchronously (may timeout on large datasets)
    - Returns results directly

    Accepts JSON body with:
    - lookback_days: int (default 90)
    - strategies: list of strategy names (optional, runs all if not specified)
    - async_mode: bool (default true) - use background processing
    """
    # ASYNC MODE: Enqueue job and return immediately
    if config.async_mode:
        try:
            from backend.services.job_queue import enqueue_backtest_job

            job_config = {
                "lookback_days": config.lookback_days,
                "strategies": config.strategies
            }

            job_id = enqueue_backtest_job(job_config)

            return {
                "success": True,
                "async": True,
                "job_id": job_id,
                "message": "Backtest job queued. Check progress with GET /api/backtests/job/{job_id}",
                "status_url": f"/api/backtests/job/{job_id}"
            }

        except Exception as e:
            logger.error(f"Failed to enqueue job: {e}")
            # Fall through to sync mode
            logger.info("Falling back to sync mode")

    # SYNC MODE: Run directly (legacy behavior)
    try:
        from backtest.autonomous_backtest_engine import get_backtester

        lookback_days = config.lookback_days
        backtester = get_backtester()
        results = backtester.backtest_all_patterns_and_save(
            lookback_days=lookback_days,
            save_to_db=True
        )

        # Count patterns with actual data
        patterns_with_data = sum(1 for r in results if r.get('total_signals', 0) > 0)

        return {
            "success": True,
            "async": False,
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
            results = backtester.run_all_backtests(lookback_days=config.lookback_days, save_to_db=True)
            return {
                "success": True,
                "async": False,
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


@router.post("/run-spx")
async def run_spx_backtest(config: SPXBacktestConfig = SPXBacktestConfig()):
    """
    Run SPX wheel backtest with ML scoring.

    ASYNC MODE (default):
    - Enqueues job to background worker (no timeout!)
    - Returns job_id immediately
    - Use GET /api/backtests/job/{job_id} to check progress

    This is the heavy operation that was crashing browsers.
    """
    if config.async_mode:
        try:
            from backend.services.job_queue import enqueue_spx_backtest_job

            job_config = {
                "start_date": config.start_date,
                "end_date": config.end_date,
                "initial_capital": config.initial_capital,
                "put_delta": config.put_delta,
                "dte_target": config.dte_target,
                "max_margin_pct": config.max_margin_pct,
                "use_ml_scoring": config.use_ml_scoring,
                "ml_min_score": config.ml_min_score
            }

            job_id = enqueue_spx_backtest_job(job_config)

            return {
                "success": True,
                "async": True,
                "job_id": job_id,
                "message": "SPX backtest job queued. This may take several minutes.",
                "status_url": f"/api/backtests/job/{job_id}"
            }

        except Exception as e:
            logger.error(f"Failed to enqueue SPX job: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to queue job: {e}")

    # Sync mode not recommended for SPX backtests
    raise HTTPException(
        status_code=400,
        detail="SPX backtests require async_mode=true to prevent timeouts. "
               "Use GET /api/backtests/job/{job_id} to check progress."
    )


@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Get status and progress of a background backtest job.

    Returns:
    - status: pending | running | completed | failed
    - progress: 0-100
    - progress_message: Human-readable status
    - result: Full results when completed
    - error: Error message if failed
    """
    try:
        from backend.services.job_queue import get_job_status as get_status

        status = get_status(job_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        return {
            "success": True,
            "job": status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs")
async def list_recent_jobs(limit: int = Query(default=20, le=100)):
    """
    List recent backtest jobs.

    Shows job status, progress, and timing information.
    """
    try:
        from backend.services.job_queue import get_recent_jobs

        jobs = get_recent_jobs(limit=limit)

        return {
            "success": True,
            "jobs": jobs,
            "count": len(jobs)
        }

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
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


class CombinedStrategyConfig(BaseModel):
    """Configuration for Combined Diagonal + CSP Wheel backtest"""
    start_date: str = "2020-01-01"
    end_date: Optional[str] = None
    initial_capital: float = 500000
    csp_allocation_pct: float = 0.60
    diagonal_allocation_pct: float = 0.25
    csp_delta_target: float = 0.20
    csp_dte_target: int = 45
    generate_report: bool = True


@router.post("/run-combined")
async def run_combined_strategy_backtest(config: CombinedStrategyConfig = CombinedStrategyConfig()):
    """
    Run Combined Strategy Backtest: Diagonal Put Spread + Cash-Secured Put Wheel

    This is the investor-grade backtest that combines:
    1. Cash-Secured Put Wheel (60% allocation) - Primary income
    2. Diagonal Put Spread (25% allocation) - Hedge in high IV

    Returns comprehensive investor report with:
    - Executive summary
    - Performance metrics (Sharpe, Sortino, Calmar)
    - Income analysis (monthly income, yield)
    - Risk analysis (drawdown, stress scenarios)
    - Yearly/monthly breakdowns
    """
    try:
        from backtest.combined_strategy_backtester import CombinedStrategyBacktester
        from reports.investor_report_generator import InvestorReportGenerator

        logger.info(f"Running combined strategy backtest: {config.start_date} to {config.end_date}")

        # Create backtester with config
        backtester = CombinedStrategyBacktester(
            initial_capital=config.initial_capital,
            csp_allocation_pct=config.csp_allocation_pct,
            diagonal_allocation_pct=config.diagonal_allocation_pct,
            csp_delta_target=config.csp_delta_target,
            csp_dte_target=config.csp_dte_target
        )

        # Run backtest
        result = backtester.run_backtest(
            start_date=config.start_date,
            end_date=config.end_date
        )

        # Generate investor report
        report = None
        if config.generate_report:
            generator = InvestorReportGenerator()
            report = generator.generate_from_backtest(result)

        return {
            "success": True,
            "message": f"Combined strategy backtest complete: {result.total_trades} trades over {config.start_date} to {result.end_date}",
            "summary": {
                "initial_capital": result.initial_capital,
                "final_equity": result.final_equity,
                "total_return_pct": result.total_return_pct,
                "cagr_pct": result.cagr_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown_pct": result.max_drawdown_pct,
                "win_rate_pct": result.win_rate_pct,
                "total_trades": result.total_trades,
                "avg_monthly_income": result.avg_monthly_income,
                "income_consistency_pct": result.income_consistency_pct
            },
            "investor_report": report,
            "yearly_returns": result.yearly_returns
        }

    except ImportError as e:
        logger.error(f"Import error: {e}")
        raise HTTPException(status_code=500, detail=f"Module not found: {e}")
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/investor-report-sample")
async def get_sample_investor_report():
    """
    Get a sample investor report structure for UI development.

    Returns the full report schema without running a backtest.
    """
    sample_report = {
        "meta": {
            "report_version": "2.0",
            "generated_at": datetime.now().isoformat(),
            "report_type": "sample_investor_report"
        },
        "header": {
            "title": "Combined Options Income Strategy",
            "subtitle": "Diagonal Put Spread + Cash-Secured Put Wheel",
            "period": "2020-01-01 to 2024-12-01",
            "initial_investment": 500000,
            "final_value": 687500
        },
        "executive_summary": {
            "headline": "$500,000 grew to $687,500 (+37.5%)",
            "key_metrics": {
                "total_return": {"value": 37.5, "format": "percent", "label": "Total Return"},
                "cagr": {"value": 8.2, "format": "percent", "label": "CAGR"},
                "sharpe_ratio": {"value": 1.45, "format": "decimal", "label": "Sharpe Ratio"},
                "max_drawdown": {"value": 12.3, "format": "percent", "label": "Max Drawdown"},
                "win_rate": {"value": 82, "format": "percent", "label": "Win Rate"},
                "monthly_income": {"value": 4250, "format": "currency", "label": "Avg Monthly Income"}
            },
            "period_years": 4.9,
            "strategy_type": "Income Generation + Downside Protection"
        },
        "strategy_overview": {
            "strategy_name": "Combined Diagonal Put + CSP Wheel",
            "objective": "Generate consistent monthly income with limited downside risk",
            "components": [
                {
                    "name": "Cash-Secured Put Wheel",
                    "allocation_pct": 60,
                    "description": "Sells OTM puts on SPY/SPX to collect premium.",
                    "mechanics": [
                        "Sell puts at 20 delta (80% win probability)",
                        "Target 45 days to expiration",
                        "If assigned, sell covered calls"
                    ],
                    "risk_profile": "Moderate"
                },
                {
                    "name": "Diagonal Put Spread",
                    "allocation_pct": 25,
                    "description": "Calendar spread hedge in high IV.",
                    "mechanics": [
                        "Buy 75 DTE OTM put",
                        "Sell 10 DTE OTM put",
                        "Net credit entry"
                    ],
                    "risk_profile": "Conservative"
                },
                {
                    "name": "Cash Reserve",
                    "allocation_pct": 15,
                    "description": "Liquidity buffer for margin.",
                    "mechanics": ["Buffer for assignments"],
                    "risk_profile": "Low"
                }
            ],
            "market_conditions": {
                "best_environment": "Sideways to slightly bullish with elevated IV",
                "challenging_environment": "Sharp sudden declines",
                "adaptation": "Diagonal spreads provide hedge"
            }
        },
        "performance_analysis": {
            "returns": {
                "total_return_pct": 37.5,
                "cagr_pct": 8.2,
                "total_dollar_gain": 187500
            },
            "risk_adjusted": {
                "sharpe_ratio": 1.45,
                "sharpe_interpretation": "Excellent - significantly outperforms on risk-adjusted basis",
                "sortino_ratio": 2.1,
                "calmar_ratio": 0.67
            },
            "drawdown_analysis": {
                "max_drawdown_pct": 12.3,
                "max_drawdown_duration_days": 45,
                "context": "Income generation aids faster recovery"
            }
        },
        "income_analysis": {
            "income_summary": {
                "total_premium_collected": 245000,
                "avg_monthly_income": 4250,
                "annual_yield_pct": 10.2
            },
            "income_consistency": {
                "profitable_months_pct": 85,
                "interpretation": "Good consistency - occasional losing months"
            }
        },
        "trade_statistics": {
            "overall": {
                "total_trades": 156,
                "winning_trades": 128,
                "losing_trades": 28,
                "win_rate_pct": 82
            },
            "trade_quality": {
                "profit_factor": 2.3,
                "expectancy_pct": 1.8,
                "avg_trade_duration_days": 32
            }
        },
        "yearly_breakdown": {
            "yearly_returns": {
                "2020": {"return_pct": 15.2, "status": "positive"},
                "2021": {"return_pct": 12.1, "status": "positive"},
                "2022": {"return_pct": -3.5, "status": "negative"},
                "2023": {"return_pct": 8.7, "status": "positive"},
                "2024": {"return_pct": 6.2, "status": "positive"}
            },
            "best_year": ["2020", 15.2],
            "worst_year": ["2022", -3.5],
            "positive_years": 4,
            "total_years": 5
        },
        "key_observations": [
            "Strong CAGR of 8.2% with lower volatility than equities",
            "Exceptional 82% win rate demonstrates strategy edge",
            "85% of months profitable - highly consistent income",
            "Maximum drawdown of 12.3% shows excellent risk management",
            "Sharpe ratio of 1.45 beats most active strategies"
        ],
        "disclosures": {
            "backtest_limitations": [
                "Past performance does not guarantee future results",
                "Backtest uses historical data which may not reflect future conditions",
                "Actual trading involves slippage and execution costs",
                "Bid-ask spreads may differ from backtest assumptions"
            ],
            "strategy_risks": [
                "Selling options involves risk of assignment",
                "Strategy may underperform in strong bull markets",
                "Margin requirements may increase during stress",
                "Early assignment risk on American-style options"
            ],
            "legal": "This report is for informational purposes only and does not constitute investment advice."
        }
    }

    return {
        "success": True,
        "sample_report": sample_report
    }
