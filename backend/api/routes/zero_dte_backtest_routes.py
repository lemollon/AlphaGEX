"""
0DTE Iron Condor Backtest API Routes

Handles the hybrid scaling Iron Condor strategy with:
- Configurable parameters (risk %, SD multiplier, spread width)
- Automatic tier scaling based on account size
- Real-time progress tracking
- Async job processing for long backtests
"""

import logging
import sys
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import psycopg2.extras

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from database_adapter import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/zero-dte", tags=["0DTE Backtest"])


class ZeroDTEBacktestConfig(BaseModel):
    """Configuration for 0DTE hybrid backtest"""
    start_date: str = Field(default="2021-01-01", description="Start date YYYY-MM-DD")
    end_date: str = Field(default="2025-12-01", description="End date YYYY-MM-DD")
    initial_capital: float = Field(default=1_000_000, description="Starting capital")
    spread_width: float = Field(default=10.0, description="Spread width in dollars")
    sd_multiplier: float = Field(default=1.0, description="Standard deviation multiplier for strike selection")
    risk_per_trade_pct: float = Field(default=5.0, description="Risk per trade as % of equity")
    ticker: str = Field(default="SPX", description="Ticker symbol")
    strategy: str = Field(default="hybrid_fixed", description="Strategy: hybrid_fixed, aggressive, realistic")


class BacktestJobStatus(BaseModel):
    """Status of a running backtest job"""
    job_id: str
    status: str  # pending, running, completed, failed
    progress: float
    progress_message: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# In-memory job storage (in production, use Redis or database)
_jobs: Dict[str, Dict] = {}


def run_hybrid_fixed_backtest(config: ZeroDTEBacktestConfig, job_id: str):
    """Run the hybrid fixed backtest in background"""
    try:
        _jobs[job_id]['status'] = 'running'
        _jobs[job_id]['progress_message'] = 'Initializing backtest...'

        # Import the backtest module
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

        # Create backtester
        backtester = HybridFixedBacktester(
            start_date=config.start_date,
            end_date=config.end_date,
            initial_capital=config.initial_capital,
            spread_width=config.spread_width,
            sd_multiplier=config.sd_multiplier,
            risk_per_trade_pct=config.risk_per_trade_pct,
            ticker=config.ticker,
        )

        _jobs[job_id]['progress'] = 10
        _jobs[job_id]['progress_message'] = 'Loading market data...'

        # Run backtest
        results = backtester.run()

        # Store results
        _jobs[job_id]['status'] = 'completed'
        _jobs[job_id]['progress'] = 100
        _jobs[job_id]['progress_message'] = 'Backtest completed!'
        _jobs[job_id]['completed_at'] = datetime.now().isoformat()
        _jobs[job_id]['result'] = results

        # Save to database
        save_backtest_results(results, config, job_id)

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        _jobs[job_id]['status'] = 'failed'
        _jobs[job_id]['error'] = str(e)
        _jobs[job_id]['progress_message'] = f'Error: {str(e)}'


def save_backtest_results(results: Dict, config: ZeroDTEBacktestConfig, job_id: str):
    """Save backtest results to database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if table exists, create if not
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS zero_dte_backtest_results (
                id SERIAL PRIMARY KEY,
                job_id VARCHAR(100) UNIQUE,
                created_at TIMESTAMP DEFAULT NOW(),
                strategy VARCHAR(100),
                ticker VARCHAR(20),
                start_date DATE,
                end_date DATE,
                initial_capital DECIMAL(15,2),
                final_equity DECIMAL(15,2),
                total_pnl DECIMAL(15,2),
                total_return_pct DECIMAL(10,2),
                avg_monthly_return_pct DECIMAL(10,2),
                max_drawdown_pct DECIMAL(10,2),
                total_trades INTEGER,
                win_rate DECIMAL(10,2),
                profit_factor DECIMAL(10,2),
                avg_win DECIMAL(15,2),
                avg_loss DECIMAL(15,2),
                total_costs DECIMAL(15,2),
                config JSONB,
                tier_stats JSONB,
                monthly_returns JSONB
            )
        """)

        s = results.get('summary', {})
        t = results.get('trades', {})
        c = results.get('costs', {})

        cursor.execute("""
            INSERT INTO zero_dte_backtest_results (
                job_id, strategy, ticker, start_date, end_date,
                initial_capital, final_equity, total_pnl, total_return_pct,
                avg_monthly_return_pct, max_drawdown_pct, total_trades,
                win_rate, profit_factor, avg_win, avg_loss, total_costs,
                config, tier_stats, monthly_returns
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s::jsonb
            )
            ON CONFLICT (job_id) DO UPDATE SET
                final_equity = EXCLUDED.final_equity,
                total_pnl = EXCLUDED.total_pnl,
                total_return_pct = EXCLUDED.total_return_pct
        """, (
            job_id,
            config.strategy,
            config.ticker,
            config.start_date,
            config.end_date,
            s.get('initial_capital', config.initial_capital),
            s.get('final_equity', 0),
            s.get('total_pnl', 0),
            s.get('total_return_pct', 0),
            s.get('avg_monthly_return_pct', 0),
            s.get('max_drawdown_pct', 0),
            t.get('total', 0),
            t.get('win_rate', 0),
            t.get('profit_factor', 0) if t.get('profit_factor') != float('inf') else 999,
            t.get('avg_win', 0),
            t.get('avg_loss', 0),
            c.get('total_costs', 0),
            str(config.dict()).replace("'", '"'),
            str(results.get('tier_stats', {})).replace("'", '"'),
            str(results.get('monthly_returns', {})).replace("'", '"'),
        ))

        conn.commit()
        conn.close()
        logger.info(f"Saved backtest results for job {job_id}")

    except Exception as e:
        logger.error(f"Failed to save results: {e}")


@router.post("/run")
async def run_zero_dte_backtest(
    config: ZeroDTEBacktestConfig,
    background_tasks: BackgroundTasks
):
    """
    Run a 0DTE Iron Condor backtest.

    Returns immediately with job_id for tracking progress.
    """
    import uuid
    job_id = f"zero_dte_{uuid.uuid4().hex[:8]}"

    # Initialize job
    _jobs[job_id] = {
        'job_id': job_id,
        'status': 'pending',
        'progress': 0,
        'progress_message': 'Job queued...',
        'result': None,
        'error': None,
        'created_at': datetime.now().isoformat(),
        'completed_at': None,
        'config': config.dict(),
    }

    # Run in background
    background_tasks.add_task(run_hybrid_fixed_backtest, config, job_id)

    return {
        "success": True,
        "async": True,
        "job_id": job_id,
        "message": "Backtest job started"
    }


@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a backtest job"""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    return {
        "success": True,
        "job": job
    }


@router.get("/results")
async def get_backtest_results(limit: int = 20):
    """Get saved backtest results from database"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM zero_dte_backtest_results
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))

        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row['id'],
                'job_id': row['job_id'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'strategy': row['strategy'],
                'ticker': row['ticker'],
                'start_date': str(row['start_date']),
                'end_date': str(row['end_date']),
                'initial_capital': float(row['initial_capital'] or 0),
                'final_equity': float(row['final_equity'] or 0),
                'total_pnl': float(row['total_pnl'] or 0),
                'total_return_pct': float(row['total_return_pct'] or 0),
                'avg_monthly_return_pct': float(row['avg_monthly_return_pct'] or 0),
                'max_drawdown_pct': float(row['max_drawdown_pct'] or 0),
                'total_trades': row['total_trades'],
                'win_rate': float(row['win_rate'] or 0),
                'profit_factor': float(row['profit_factor'] or 0),
                'total_costs': float(row['total_costs'] or 0),
                'config': row.get('config'),
                'tier_stats': row.get('tier_stats'),
                'monthly_returns': row.get('monthly_returns'),
            })

        conn.close()
        return {"success": True, "results": results}

    except Exception as e:
        logger.error(f"Failed to get results: {e}")
        return {"success": True, "results": []}  # Return empty if table doesn't exist


@router.get("/strategies")
async def get_available_strategies():
    """Get list of available 0DTE strategies"""
    return {
        "success": True,
        "strategies": [
            {
                "id": "hybrid_fixed",
                "name": "Hybrid Fixed (Recommended)",
                "description": "Automatically scales DTE based on account size. Uses correct SD calculations for each tier. All trades are day trades.",
                "features": [
                    "Auto-scaling tiers ($0-$2M → $2M-$5M → $5M-$15M → $15M+)",
                    "Correct SD for each DTE (1-day, 7-day, 30-day)",
                    "Day trades only (enter open, exit close)",
                    "Liquidity-aware position limits",
                    "Realistic transaction costs"
                ],
                "recommended_settings": {
                    "risk_per_trade_pct": 5.0,
                    "sd_multiplier": 1.0,
                    "spread_width": 10.0
                }
            },
            {
                "id": "aggressive",
                "name": "Aggressive (High Risk)",
                "description": "Trades every day with 10% risk per trade. No position limits. For small accounts seeking maximum growth.",
                "features": [
                    "10% risk per trade",
                    "Daily Iron Condors",
                    "No stop loss (let theta work)",
                    "Maximum compounding"
                ],
                "recommended_settings": {
                    "risk_per_trade_pct": 10.0,
                    "sd_multiplier": 1.0,
                    "spread_width": 10.0
                }
            },
            {
                "id": "realistic",
                "name": "Realistic (Conservative)",
                "description": "Includes full transaction costs and 100 contract limit. Shows what's actually achievable.",
                "features": [
                    "$0.65/leg commission",
                    "$0.10 slippage per spread",
                    "100 contract max (liquidity)",
                    "Honest returns"
                ],
                "recommended_settings": {
                    "risk_per_trade_pct": 10.0,
                    "sd_multiplier": 1.0,
                    "spread_width": 10.0
                }
            }
        ]
    }


@router.get("/tiers")
async def get_scaling_tiers():
    """Get tier configuration for hybrid strategy"""
    return {
        "success": True,
        "tiers": [
            {
                "name": "TIER_1_0DTE",
                "equity_range": "$0 - $2M",
                "options_dte": "0-1 DTE (0DTE)",
                "sd_days": 1,
                "max_contracts": 100,
                "trades_per_week": 5,
                "description": "Fast compounding with 0DTE options"
            },
            {
                "name": "TIER_2_WEEKLY",
                "equity_range": "$2M - $5M",
                "options_dte": "5-7 DTE (Weekly)",
                "sd_days": 7,
                "max_contracts": 300,
                "trades_per_week": 5,
                "description": "More liquidity with weekly options"
            },
            {
                "name": "TIER_3_MONTHLY",
                "equity_range": "$5M - $15M",
                "options_dte": "21-35 DTE (Monthly)",
                "sd_days": 30,
                "max_contracts": 500,
                "trades_per_week": 3,
                "description": "Maximum liquidity, reduced frequency"
            },
            {
                "name": "TIER_4_LARGE",
                "equity_range": "$15M+",
                "options_dte": "30-45 DTE",
                "sd_days": 30,
                "max_contracts": 1000,
                "trades_per_week": 2,
                "description": "Institutional-level with volume discounts"
            }
        ]
    }
