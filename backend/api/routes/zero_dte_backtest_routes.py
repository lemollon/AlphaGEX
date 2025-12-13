"""
0DTE Iron Condor Backtest API Routes

Handles the hybrid scaling Iron Condor strategy with:
- Configurable parameters (risk %, SD multiplier, spread width)
- Automatic tier scaling based on account size
- Real-time progress tracking
- Async job processing for long backtests
- Multi-leg strategy support (Iron Condor, Bull Put, Bear Call)
- VIX filtering and stop loss
- CSV/Excel export
- Equity curve and risk metrics
"""

import logging
import sys
import os
import csv
import json
import io
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import psycopg2.extras

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from database_adapter import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/zero-dte", tags=["0DTE Backtest"])


class ZeroDTEBacktestConfig(BaseModel):
    """Configuration for 0DTE hybrid backtest - ENHANCED"""
    # Basic settings
    start_date: str = Field(default="2021-01-01", description="Start date YYYY-MM-DD")
    end_date: str = Field(default="2025-12-01", description="End date YYYY-MM-DD")
    initial_capital: float = Field(default=1_000_000, description="Starting capital")
    spread_width: float = Field(default=10.0, description="Spread width in dollars")
    risk_per_trade_pct: float = Field(default=5.0, description="Risk per trade as % of equity")
    ticker: str = Field(default="SPX", description="Ticker symbol")
    strategy: str = Field(default="hybrid_fixed", description="Strategy: hybrid_fixed, aggressive, realistic")

    # Multi-leg strategy type
    strategy_type: str = Field(default="iron_condor", description="iron_condor, bull_put, bear_call, iron_butterfly, diagonal_call, diagonal_put")

    # Strike selection method
    strike_selection: str = Field(default="sd", description="Strike selection method: sd, fixed, delta")
    sd_multiplier: float = Field(default=1.0, description="SD multiplier (for strike_selection=sd)")
    fixed_strike_distance: float = Field(default=50.0, description="Fixed points from price (for strike_selection=fixed)")
    target_delta: float = Field(default=0.16, description="Target delta for short strikes (for strike_selection=delta)")

    # VIX filtering
    min_vix: Optional[float] = Field(default=None, description="Minimum VIX to trade (None = no filter)")
    max_vix: Optional[float] = Field(default=None, description="Maximum VIX to trade (None = no filter)")

    # Risk management
    stop_loss_pct: Optional[float] = Field(default=None, description="Stop loss as % of max loss (None = no stop)")
    profit_target_pct: Optional[float] = Field(default=None, description="Profit target as % of credit (None = let expire)")

    # Trading days
    trade_monday: bool = Field(default=True, description="Trade on Monday")
    trade_tuesday: bool = Field(default=True, description="Trade on Tuesday")
    trade_wednesday: bool = Field(default=True, description="Trade on Wednesday")
    trade_thursday: bool = Field(default=True, description="Trade on Thursday")
    trade_friday: bool = Field(default=True, description="Trade on Friday")

    # Position limits override
    max_contracts_override: Optional[int] = Field(default=None, description="Override max contracts (None = use tier default)")

    # Transaction costs override
    commission_per_leg: Optional[float] = Field(default=None, description="Override commission (None = use tier default)")
    slippage_per_spread: Optional[float] = Field(default=None, description="Override slippage (None = use tier default)")


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


# ============================================================================
# Health Check Endpoint - Use this to debug KRONOS issues
# ============================================================================

@router.get("/health")
async def health_check():
    """
    Health check endpoint for KRONOS debugging.

    Returns detailed status about:
    - Backend connectivity
    - Database connectivity
    - Active jobs
    - ORAT data availability

    Use this to verify everything is working before running a backtest.
    """
    # Check ORAT_DATABASE_URL first, then fall back to DATABASE_URL
    orat_db_url = os.getenv('ORAT_DATABASE_URL')
    database_url = os.getenv('DATABASE_URL')
    has_orat_db = bool(orat_db_url or database_url)

    health = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "backend": "running",
        "orat_database_url_configured": bool(orat_db_url),
        "database_url_configured": bool(database_url),
        "using_database": "ORAT_DATABASE_URL" if orat_db_url else ("DATABASE_URL" if database_url else "none"),
        "database": "not_configured" if not has_orat_db else "unknown",
        "orat_data": "unavailable" if not has_orat_db else "unknown",
        "active_jobs": len([j for j in _jobs.values() if j.get('status') == 'running']),
        "total_jobs": len(_jobs),
    }

    if not has_orat_db:
        health["status"] = "degraded"
        health["error"] = (
            "Neither ORAT_DATABASE_URL nor DATABASE_URL is set. "
            "KRONOS requires PostgreSQL with ORAT options data. "
            "Set ORAT_DATABASE_URL to point to your backtester database."
        )
        return health

    # Check database connectivity using ORAT database
    try:
        conn = get_orat_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        health["database"] = "connected"

        # Check ORAT data
        cursor.execute("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT ticker) as tickers,
                MIN(trade_date) as earliest_date,
                MAX(trade_date) as latest_date
            FROM orat_options_eod
        """)
        row = cursor.fetchone()
        if row and row[0] > 0:
            health["orat_data"] = {
                "status": "available",
                "total_rows": row[0],
                "tickers": row[1],
                "date_range": f"{row[2]} to {row[3]}"
            }
        else:
            health["orat_data"] = {"status": "empty", "total_rows": 0}

        conn.close()
    except Exception as e:
        health["database"] = f"error: {str(e)}"
        health["orat_data"] = "unavailable"
        health["status"] = "degraded"

    return health


def get_orat_connection():
    """
    Get database connection for ORAT options data.
    Uses ORAT_DATABASE_URL if set, otherwise falls back to DATABASE_URL.
    """
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("Neither ORAT_DATABASE_URL nor DATABASE_URL is set")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def run_hybrid_fixed_backtest(config: ZeroDTEBacktestConfig, job_id: str):
    """Run the hybrid fixed backtest in background"""
    try:
        print(f"\n{'='*60}", flush=True)
        print(f"🚀 KRONOS BACKTEST STARTING - Job: {job_id}", flush=True)
        print(f"   Ticker: {config.ticker}", flush=True)
        print(f"   Date Range: {config.start_date} to {config.end_date}", flush=True)
        print(f"   Initial Capital: ${config.initial_capital:,.0f}", flush=True)
        print(f"   Strategy: {config.strategy_type}", flush=True)
        print(f"{'='*60}\n", flush=True)

        _jobs[job_id]['status'] = 'running'
        _jobs[job_id]['progress'] = 5
        _jobs[job_id]['progress_message'] = 'Initializing backtest...'

        # Check ORAT_DATABASE_URL or DATABASE_URL before proceeding
        orat_db = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
        if not orat_db:
            error_msg = (
                "Neither ORAT_DATABASE_URL nor DATABASE_URL is set. "
                "KRONOS backtester requires a PostgreSQL connection to access ORAT options data. "
                "Set ORAT_DATABASE_URL to point to your backtester database with ORAT options data."
            )
            logger.error(error_msg)
            _jobs[job_id]['status'] = 'failed'
            _jobs[job_id]['progress'] = 100
            _jobs[job_id]['error'] = error_msg
            _jobs[job_id]['progress_message'] = 'ORAT database not configured'
            _jobs[job_id]['completed_at'] = datetime.now().isoformat()
            return

        # Log which database is being used
        using_db = "ORAT_DATABASE_URL" if os.getenv('ORAT_DATABASE_URL') else "DATABASE_URL"
        print(f"📊 Using {using_db} for ORAT options data", flush=True)

        # Import the backtest module
        print("📦 Importing HybridFixedBacktester...", flush=True)
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester
        print("✅ Import successful", flush=True)

        # Build trade_days list from config
        trade_days = []
        if config.trade_monday: trade_days.append(0)
        if config.trade_tuesday: trade_days.append(1)
        if config.trade_wednesday: trade_days.append(2)
        if config.trade_thursday: trade_days.append(3)
        if config.trade_friday: trade_days.append(4)

        _jobs[job_id]['progress'] = 10
        _jobs[job_id]['progress_message'] = 'Creating backtester...'

        print(f"🔧 Creating backtester instance...", flush=True)
        # Create backtester with all enhanced parameters
        backtester = HybridFixedBacktester(
            start_date=config.start_date,
            end_date=config.end_date,
            initial_capital=config.initial_capital,
            spread_width=config.spread_width,
            sd_multiplier=config.sd_multiplier,
            risk_per_trade_pct=config.risk_per_trade_pct,
            ticker=config.ticker,
            # New enhanced parameters
            strategy_type=config.strategy_type,
            min_vix=config.min_vix,
            max_vix=config.max_vix,
            stop_loss_pct=config.stop_loss_pct,
            profit_target_pct=config.profit_target_pct,
            trade_days=trade_days if trade_days else None,
            max_contracts_override=config.max_contracts_override,
            commission_per_leg_override=config.commission_per_leg,
            slippage_per_spread_override=config.slippage_per_spread,
            # Strike selection method
            strike_selection=config.strike_selection,
            fixed_strike_distance=config.fixed_strike_distance,
            target_delta=config.target_delta,
        )

        _jobs[job_id]['progress'] = 15
        _jobs[job_id]['progress_message'] = 'Loading market data...'

        # Provide progress callback to backtester
        def update_progress(pct: int, message: str):
            # Scale progress from 15-95 (leave 5% at start and end)
            scaled_pct = 15 + int(pct * 0.80)
            _jobs[job_id]['progress'] = scaled_pct
            _jobs[job_id]['progress_message'] = message

        # Attach progress callback to backtester
        backtester.progress_callback = update_progress

        # Run backtest
        logger.info(f"Starting backtest for {config.ticker} from {config.start_date} to {config.end_date}")
        results = backtester.run()
        logger.info(f"Backtest run() returned: {type(results)}, keys: {results.keys() if results else 'empty'}")

        _jobs[job_id]['progress'] = 95
        _jobs[job_id]['progress_message'] = 'Finalizing results...'

        # Check if results are valid (not empty)
        if not results or not results.get('trades') or results.get('trades', {}).get('total', 0) == 0:
            # More detailed error info with debug stats
            error_detail = f'No trades found for {config.ticker} between {config.start_date} and {config.end_date}.'
            if not results:
                error_detail += ' Backtest returned empty results (check if market data or ORAT data loaded).'
            elif not results.get('trades'):
                error_detail += f' Results missing "trades" key. Keys: {list(results.keys())}'
            else:
                error_detail += f' Trade count was 0.'

            # Include debug stats if available
            if hasattr(backtester, 'debug_stats'):
                ds = backtester.debug_stats
                sf = ds.get('strategy_failures', {})
                error_detail += f"\n\nDEBUG STATS:"
                error_detail += f"\n- Skipped (wrong weekday): {ds.get('skipped_by_trade_day', 0)}"
                error_detail += f"\n- Skipped (VIX filter): {ds.get('skipped_by_vix_filter', 0)}"
                error_detail += f"\n- Skipped (tier limit): {ds.get('skipped_by_tier_limit', 0)}"
                error_detail += f"\n- Skipped (no OHLC): {ds.get('skipped_no_ohlc', 0)}"
                error_detail += f"\n- Skipped (no options): {ds.get('skipped_no_options', 0)}"
                error_detail += f"\n- Skipped (strategy failed): {ds.get('skipped_no_strategy', 0)}"
                error_detail += f"\n- Strategy failures: no_otm_puts={sf.get('no_otm_puts', 0)}, no_otm_calls={sf.get('no_otm_calls', 0)}, no_long_put={sf.get('no_long_put', 0)}, no_long_call={sf.get('no_long_call', 0)}"

            logger.warning(error_detail)
            _jobs[job_id]['status'] = 'failed'
            _jobs[job_id]['progress'] = 100
            _jobs[job_id]['error'] = error_detail
            _jobs[job_id]['progress_message'] = 'No trades found'
            _jobs[job_id]['completed_at'] = datetime.now().isoformat()
            return

        # Store results
        _jobs[job_id]['status'] = 'completed'
        _jobs[job_id]['progress'] = 100
        _jobs[job_id]['progress_message'] = f'Completed! {results["trades"]["total"]} trades analyzed.'
        _jobs[job_id]['completed_at'] = datetime.now().isoformat()
        _jobs[job_id]['result'] = results

        # Save to database
        save_backtest_results(results, config, job_id)

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        _jobs[job_id]['status'] = 'failed'
        _jobs[job_id]['progress'] = 100
        _jobs[job_id]['error'] = str(e)
        _jobs[job_id]['progress_message'] = f'Error: {str(e)}'
        _jobs[job_id]['completed_at'] = datetime.now().isoformat()


def _sanitize_numeric(value, default=0.0, max_value=999999999.99):
    """
    Sanitize numeric value for PostgreSQL DECIMAL columns.
    PostgreSQL DECIMAL does NOT accept NaN, Infinity, or -Infinity.
    """
    import math

    if value is None:
        return default

    try:
        num = float(value)
        # Check for NaN and infinity
        if math.isnan(num) or math.isinf(num):
            return default if num != float('inf') else min(999.0, max_value)
        # Clamp to max_value to prevent overflow
        return min(max(num, -max_value), max_value)
    except (TypeError, ValueError):
        return default


def save_backtest_results(results: Dict, config: ZeroDTEBacktestConfig, job_id: str):
    """Save backtest results to database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Table should already exist, but create if not
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

        # Sanitize ALL numeric values - PostgreSQL DECIMAL rejects NaN/Infinity
        initial_capital = _sanitize_numeric(s.get('initial_capital', config.initial_capital))
        final_equity = _sanitize_numeric(s.get('final_equity', 0))
        total_pnl = _sanitize_numeric(s.get('total_pnl', 0))
        total_return_pct = _sanitize_numeric(s.get('total_return_pct', 0), max_value=99999999.99)
        avg_monthly_return_pct = _sanitize_numeric(s.get('avg_monthly_return_pct', 0), max_value=99999999.99)
        max_drawdown_pct = _sanitize_numeric(s.get('max_drawdown_pct', 0), max_value=99999999.99)

        total_trades = int(t.get('total', 0)) if t.get('total') is not None else 0
        win_rate = _sanitize_numeric(t.get('win_rate', 0), max_value=100.0)
        profit_factor = _sanitize_numeric(t.get('profit_factor', 0), default=999.0, max_value=999.0)
        avg_win = _sanitize_numeric(t.get('avg_win', 0))
        avg_loss = _sanitize_numeric(t.get('avg_loss', 0))
        total_costs = _sanitize_numeric(c.get('total_costs', 0))

        # Properly serialize JSON using json.dumps() - NOT string conversion!
        # This handles None -> null, True -> true, special chars, etc.
        config_json = json.dumps(config.dict(), default=str)
        tier_stats_json = json.dumps(results.get('tier_stats', {}), default=str)
        monthly_returns_json = json.dumps(results.get('monthly_returns', {}), default=str)

        # Debug logging
        print(f"📝 KRONOS: Saving backtest - job_id={job_id}, trades={total_trades}, return={total_return_pct:.2f}%", flush=True)

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
            initial_capital,
            final_equity,
            total_pnl,
            total_return_pct,
            avg_monthly_return_pct,
            max_drawdown_pct,
            total_trades,
            win_rate,
            profit_factor,
            avg_win,
            avg_loss,
            total_costs,
            config_json,
            tier_stats_json,
            monthly_returns_json,
        ))

        conn.commit()
        logger.info(f"✅ Saved backtest summary for job {job_id}")

        # =================================================================
        # SAVE INDIVIDUAL TRADES for ML training and analysis
        # =================================================================
        all_trades = results.get('all_trades', [])
        if all_trades:
            # Create trades table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS zero_dte_backtest_trades (
                    id SERIAL PRIMARY KEY,
                    backtest_id VARCHAR(100) NOT NULL,
                    trade_date DATE,
                    trade_number INTEGER,
                    tier_name VARCHAR(50),

                    -- Entry data
                    underlying_price_entry DECIMAL(10,2),
                    vix_entry DECIMAL(8,2),
                    iv_used DECIMAL(10,6),
                    expected_move_1d DECIMAL(10,2),
                    sd_multiplier DECIMAL(6,3),

                    -- Iron Condor strikes
                    put_long_strike DECIMAL(10,2),
                    put_short_strike DECIMAL(10,2),
                    call_short_strike DECIMAL(10,2),
                    call_long_strike DECIMAL(10,2),

                    -- Credits
                    put_credit DECIMAL(10,4),
                    call_credit DECIMAL(10,4),
                    total_credit DECIMAL(10,4),

                    -- Exit/Results
                    close_price DECIMAL(10,2),
                    daily_high DECIMAL(10,2),
                    daily_low DECIMAL(10,2),
                    put_outcome VARCHAR(30),
                    call_outcome VARCHAR(30),
                    outcome VARCHAR(30),
                    net_pnl DECIMAL(12,2),
                    return_pct DECIMAL(10,4),

                    -- GEX data (V2 enrichment for ML training)
                    gex_net DECIMAL(20,2),
                    gex_normalized DECIMAL(15,6),
                    gex_regime VARCHAR(20),
                    gex_flip_point DECIMAL(10,2),
                    gex_call_wall DECIMAL(10,2),
                    gex_put_wall DECIMAL(10,2),
                    gex_distance_to_flip_pct DECIMAL(10,4),
                    gex_between_walls BOOLEAN,

                    created_at TIMESTAMP DEFAULT NOW(),

                    CONSTRAINT fk_backtest FOREIGN KEY (backtest_id)
                        REFERENCES zero_dte_backtest_results(job_id) ON DELETE CASCADE
                )
            """)

            # Create indexes for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_trades_backtest_id
                ON zero_dte_backtest_trades(backtest_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_trades_date
                ON zero_dte_backtest_trades(trade_date)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_trades_outcome
                ON zero_dte_backtest_trades(outcome)
            """)

            # Delete existing trades for this backtest (in case of re-run)
            cursor.execute("""
                DELETE FROM zero_dte_backtest_trades WHERE backtest_id = %s
            """, (job_id,))

            # Insert each trade
            trades_saved = 0
            for trade in all_trades:
                try:
                    cursor.execute("""
                        INSERT INTO zero_dte_backtest_trades (
                            backtest_id, trade_date, trade_number, tier_name,
                            underlying_price_entry, vix_entry, iv_used, expected_move_1d, sd_multiplier,
                            put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                            put_credit, call_credit, total_credit,
                            close_price, daily_high, daily_low,
                            put_outcome, call_outcome, outcome,
                            net_pnl, return_pct,
                            gex_net, gex_normalized, gex_regime, gex_flip_point,
                            gex_call_wall, gex_put_wall, gex_distance_to_flip_pct, gex_between_walls
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s
                        )
                    """, (
                        job_id,
                        trade.get('trade_date'),
                        trade.get('trade_number'),
                        trade.get('tier_name'),
                        _sanitize_numeric(trade.get('open_price')),
                        _sanitize_numeric(trade.get('vix')),
                        _sanitize_numeric(trade.get('iv_used')),
                        _sanitize_numeric(trade.get('expected_move_1d')),
                        _sanitize_numeric(trade.get('sd_multiplier')),
                        _sanitize_numeric(trade.get('put_long_strike')),
                        _sanitize_numeric(trade.get('put_short_strike')),
                        _sanitize_numeric(trade.get('call_short_strike')),
                        _sanitize_numeric(trade.get('call_long_strike')),
                        _sanitize_numeric(trade.get('put_credit_gross')),
                        _sanitize_numeric(trade.get('call_credit_gross')),
                        _sanitize_numeric(trade.get('total_credit')),
                        _sanitize_numeric(trade.get('close_price')),
                        _sanitize_numeric(trade.get('daily_high')),
                        _sanitize_numeric(trade.get('daily_low')),
                        trade.get('put_outcome'),
                        trade.get('call_outcome'),
                        trade.get('outcome'),
                        _sanitize_numeric(trade.get('net_pnl')),
                        _sanitize_numeric(trade.get('return_pct')),
                        # GEX data (may be None if not enriched)
                        _sanitize_numeric(trade.get('gex_net'), default=None) if trade.get('gex_net') is not None else None,
                        _sanitize_numeric(trade.get('gex_normalized'), default=None) if trade.get('gex_normalized') is not None else None,
                        trade.get('gex_regime'),
                        _sanitize_numeric(trade.get('gex_flip_point'), default=None) if trade.get('gex_flip_point') is not None else None,
                        _sanitize_numeric(trade.get('gex_call_wall'), default=None) if trade.get('gex_call_wall') is not None else None,
                        _sanitize_numeric(trade.get('gex_put_wall'), default=None) if trade.get('gex_put_wall') is not None else None,
                        _sanitize_numeric(trade.get('gex_distance_to_flip_pct'), default=None) if trade.get('gex_distance_to_flip_pct') is not None else None,
                        trade.get('gex_between_walls'),
                    ))
                    trades_saved += 1
                except Exception as trade_err:
                    logger.warning(f"Failed to save trade {trade.get('trade_date')}: {trade_err}")

            conn.commit()
            logger.info(f"✅ Saved {trades_saved}/{len(all_trades)} individual trades for job {job_id}")
            print(f"✅ KRONOS: Saved {trades_saved} trades to database (for ML training)", flush=True)

        conn.close()
        print(f"✅ KRONOS: Saved backtest results to database (job_id: {job_id})", flush=True)

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"❌ Failed to save backtest results: {e}\n{error_detail}")
        print(f"❌ KRONOS: Failed to save results to database: {e}", flush=True)
        print(f"   Error details: {error_detail}", flush=True)


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


@router.get("/trades/{backtest_id}")
async def get_backtest_trades(backtest_id: str):
    """
    Get individual trades from a saved backtest for ML training.

    Returns all trades with their features and outcomes for ARES ML advisor training.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM zero_dte_backtest_trades
            WHERE backtest_id = %s
            ORDER BY trade_date, trade_number
        """, (backtest_id,))

        trades = []
        for row in cursor.fetchall():
            trades.append({
                'trade_date': str(row['trade_date']) if row['trade_date'] else None,
                'trade_number': row['trade_number'],
                'tier_name': row['tier_name'],
                'underlying_price_entry': float(row['underlying_price_entry'] or 0),
                'vix_entry': float(row['vix_entry'] or 0),
                'iv_used': float(row['iv_used'] or 0),
                'sd_multiplier': float(row['sd_multiplier'] or 0),
                'put_long_strike': float(row['put_long_strike'] or 0),
                'put_short_strike': float(row['put_short_strike'] or 0),
                'call_short_strike': float(row['call_short_strike'] or 0),
                'call_long_strike': float(row['call_long_strike'] or 0),
                'total_credit': float(row['total_credit'] or 0),
                'close_price': float(row['close_price'] or 0),
                'outcome': row['outcome'],
                'net_pnl': float(row['net_pnl'] or 0),
                'return_pct': float(row['return_pct'] or 0),
                # GEX features for ML
                'gex_net': float(row['gex_net']) if row.get('gex_net') is not None else None,
                'gex_normalized': float(row['gex_normalized']) if row.get('gex_normalized') is not None else None,
                'gex_regime': row.get('gex_regime'),
                'gex_flip_point': float(row['gex_flip_point']) if row.get('gex_flip_point') is not None else None,
                'gex_between_walls': row.get('gex_between_walls'),
            })

        conn.close()
        return {"success": True, "backtest_id": backtest_id, "trade_count": len(trades), "trades": trades}

    except Exception as e:
        logger.error(f"Failed to get trades: {e}")
        return {"success": False, "error": str(e), "trades": []}


@router.get("/trades-for-ml")
async def get_all_trades_for_ml(limit: int = 10000):
    """
    Get all backtest trades for ML model training.

    Returns trades from all backtests with features suitable for ARES ML advisor.
    This endpoint is used by the ML training pipeline.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT
                t.backtest_id,
                t.trade_date,
                t.trade_number,
                t.tier_name,
                t.underlying_price_entry,
                t.vix_entry,
                t.sd_multiplier,
                t.put_short_strike,
                t.call_short_strike,
                t.total_credit,
                t.close_price,
                t.outcome,
                t.net_pnl,
                t.return_pct,
                t.gex_net,
                t.gex_normalized,
                t.gex_regime,
                t.gex_distance_to_flip_pct,
                t.gex_between_walls,
                r.strategy,
                r.ticker
            FROM zero_dte_backtest_trades t
            JOIN zero_dte_backtest_results r ON t.backtest_id = r.job_id
            ORDER BY t.trade_date DESC
            LIMIT %s
        """, (limit,))

        trades = []
        for row in cursor.fetchall():
            # Convert to ML-friendly format
            is_win = row['outcome'] == 'MAX_PROFIT'
            trades.append({
                'trade_date': str(row['trade_date']) if row['trade_date'] else None,
                'backtest_id': row['backtest_id'],
                'strategy': row['strategy'],
                'ticker': row['ticker'],
                # Features for ML
                'vix': float(row['vix_entry'] or 0),
                'price': float(row['underlying_price_entry'] or 0),
                'sd_multiplier': float(row['sd_multiplier'] or 0),
                'put_short_strike': float(row['put_short_strike'] or 0),
                'call_short_strike': float(row['call_short_strike'] or 0),
                'gex_normalized': float(row['gex_normalized']) if row.get('gex_normalized') is not None else None,
                'gex_regime': row.get('gex_regime'),
                'gex_distance_to_flip_pct': float(row['gex_distance_to_flip_pct']) if row.get('gex_distance_to_flip_pct') is not None else None,
                'gex_between_walls': row.get('gex_between_walls'),
                # Labels/outcomes
                'outcome': row['outcome'],
                'is_win': is_win,
                'net_pnl': float(row['net_pnl'] or 0),
                'return_pct': float(row['return_pct'] or 0),
            })

        conn.close()

        # Summary stats
        win_count = sum(1 for t in trades if t['is_win'])
        total = len(trades)
        win_rate = (win_count / total * 100) if total > 0 else 0

        return {
            "success": True,
            "total_trades": total,
            "win_count": win_count,
            "loss_count": total - win_count,
            "win_rate": round(win_rate, 2),
            "trades": trades
        }

    except Exception as e:
        logger.error(f"Failed to get trades for ML: {e}")
        return {"success": False, "error": str(e), "trades": []}


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


@router.get("/strategy-types")
async def get_strategy_types():
    """Get available multi-leg strategy types"""
    return {
        "success": True,
        "strategy_types": [
            {
                "id": "iron_condor",
                "name": "Iron Condor",
                "description": "Bull Put Spread + Bear Call Spread. Profit if price stays between strikes.",
                "legs": 4,
                "direction": "neutral",
                "credit": True
            },
            {
                "id": "bull_put",
                "name": "Bull Put Spread",
                "description": "Sell put, buy lower put. Profit if price stays above short strike.",
                "legs": 2,
                "direction": "bullish",
                "credit": True
            },
            {
                "id": "bear_call",
                "name": "Bear Call Spread",
                "description": "Sell call, buy higher call. Profit if price stays below short strike.",
                "legs": 2,
                "direction": "bearish",
                "credit": True
            },
            {
                "id": "iron_butterfly",
                "name": "Iron Butterfly",
                "description": "ATM short straddle + OTM wings. Maximum profit at center strike.",
                "legs": 4,
                "direction": "neutral",
                "credit": True
            },
            {
                "id": "diagonal_call",
                "name": "Diagonal Call (PMCC)",
                "description": "Sell near-term OTM call at SD distance, buy longer-term call. Poor Man's Covered Call.",
                "legs": 2,
                "direction": "bearish/neutral",
                "credit": False,
                "note": "Short strike placed at configured SD multiplier above price"
            },
            {
                "id": "diagonal_put",
                "name": "Diagonal Put (PMCP)",
                "description": "Sell near-term OTM put at SD distance, buy longer-term put. Poor Man's Covered Put.",
                "legs": 2,
                "direction": "bullish/neutral",
                "credit": False,
                "note": "Short strike placed at configured SD multiplier below price"
            },
            {
                "id": "gex_protected_iron_condor",
                "name": "GEX-Protected Iron Condor",
                "description": "Iron Condor with strikes placed outside GEX walls (call wall/put wall) for additional protection. Falls back to SD when GEX data unavailable.",
                "legs": 4,
                "direction": "neutral",
                "credit": True,
                "note": "Uses GEX walls as support/resistance levels for strike selection",
                "features": ["GEX wall protection", "SD fallback", "Positive GEX bias"]
            },
            {
                "id": "bull_call",
                "name": "Bull Call Spread",
                "description": "Buy ATM call, sell OTM call. Profit if price rises. Debit spread with defined risk.",
                "legs": 2,
                "direction": "bullish",
                "credit": False
            },
            {
                "id": "apache_directional",
                "name": "APACHE GEX Directional",
                "description": "Bull Call Spread near put wall (support), Bear Call Spread near call wall (resistance). Uses GEX walls for entry timing.",
                "legs": 2,
                "direction": "adaptive",
                "credit": "mixed",
                "note": "Bullish when near put wall, Bearish when near call wall. 90%+ win rate with 1% wall filter.",
                "features": ["GEX wall timing", "ML direction prediction", "Oracle integration"]
            }
        ]
    }


@router.get("/export/trades/{job_id}")
async def export_trades_csv(job_id: str):
    """Export trades from a backtest to CSV"""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']
    trades = result.get('all_trades', [])

    if not trades:
        raise HTTPException(status_code=404, detail="No trades found")

    # Create CSV in memory
    output = io.StringIO()
    if trades:
        fieldnames = trades[0].keys() if isinstance(trades[0], dict) else []
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade if isinstance(trade, dict) else trade.__dict__)

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=trades_{job_id}.csv"}
    )


@router.get("/export/summary/{job_id}")
async def export_summary_csv(job_id: str):
    """Export backtest summary to CSV"""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']

    # Flatten summary data
    summary_data = []

    # Add main metrics
    s = result.get('summary', {})
    t = result.get('trades', {})
    c = result.get('costs', {})
    r = result.get('risk_metrics', {})

    summary_data.append({'metric': 'Initial Capital', 'value': s.get('initial_capital', 0)})
    summary_data.append({'metric': 'Final Equity', 'value': s.get('final_equity', 0)})
    summary_data.append({'metric': 'Total P&L', 'value': s.get('total_pnl', 0)})
    summary_data.append({'metric': 'Total Return %', 'value': s.get('total_return_pct', 0)})
    summary_data.append({'metric': 'Avg Monthly Return %', 'value': s.get('avg_monthly_return_pct', 0)})
    summary_data.append({'metric': 'Max Drawdown %', 'value': s.get('max_drawdown_pct', 0)})
    summary_data.append({'metric': 'Total Trades', 'value': t.get('total', 0)})
    summary_data.append({'metric': 'Win Rate %', 'value': t.get('win_rate', 0)})
    summary_data.append({'metric': 'Profit Factor', 'value': t.get('profit_factor', 0)})
    summary_data.append({'metric': 'Total Costs', 'value': c.get('total_costs', 0)})
    summary_data.append({'metric': 'Sharpe Ratio', 'value': r.get('sharpe_ratio', 0)})
    summary_data.append({'metric': 'Sortino Ratio', 'value': r.get('sortino_ratio', 0)})
    summary_data.append({'metric': 'Max Consecutive Losses', 'value': r.get('max_consecutive_losses', 0)})

    # Create CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['metric', 'value'])
    writer.writeheader()
    writer.writerows(summary_data)

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=summary_{job_id}.csv"}
    )


@router.get("/export/equity-curve/{job_id}")
async def export_equity_curve_csv(job_id: str):
    """Export equity curve data to CSV"""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']
    equity_curve = result.get('equity_curve', [])

    if not equity_curve:
        raise HTTPException(status_code=404, detail="No equity curve data")

    # Create CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['date', 'equity', 'drawdown_pct', 'daily_pnl'])
    writer.writeheader()
    writer.writerows(equity_curve)

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=equity_curve_{job_id}.csv"}
    )


@router.get("/compare")
async def compare_backtests(job_ids: str):
    """Compare multiple backtests side by side

    Args:
        job_ids: Comma-separated list of job IDs to compare
    """
    ids = [j.strip() for j in job_ids.split(',')]

    comparisons = []
    for job_id in ids:
        if job_id in _jobs and _jobs[job_id]['status'] == 'completed':
            job = _jobs[job_id]
            result = job.get('result', {})
            config = job.get('config', {})

            s = result.get('summary', {})
            t = result.get('trades', {})
            r = result.get('risk_metrics', {})

            comparisons.append({
                'job_id': job_id,
                'config': config,
                'metrics': {
                    'initial_capital': s.get('initial_capital', 0),
                    'final_equity': s.get('final_equity', 0),
                    'total_return_pct': s.get('total_return_pct', 0),
                    'avg_monthly_return_pct': s.get('avg_monthly_return_pct', 0),
                    'max_drawdown_pct': s.get('max_drawdown_pct', 0),
                    'total_trades': t.get('total', 0),
                    'win_rate': t.get('win_rate', 0),
                    'profit_factor': t.get('profit_factor', 0),
                    'sharpe_ratio': r.get('sharpe_ratio', 0),
                    'sortino_ratio': r.get('sortino_ratio', 0),
                }
            })

    return {"success": True, "comparisons": comparisons}


@router.get("/data-sources")
async def get_data_sources():
    """Get information about available data sources and their limitations"""
    return {
        "success": True,
        "data_sources": {
            "orat": {
                "name": "ORAT Historical Options Data",
                "description": "End-of-day options data including Greeks, IV, bid/ask",
                "data_available": {
                    "tickers": ["SPX", "SPXW", "SPY"],
                    "date_range": "2021-01-01 to present",
                    "fields": ["strike", "expiration", "bid", "ask", "delta", "gamma", "theta", "vega", "IV", "underlying_price"]
                },
                "limitations": [
                    "EOD data only - no intraday prices",
                    "No tick-by-tick data for backtesting intraday stops",
                    "Settlement uses daily OHLC from Yahoo Finance",
                    "Greeks are EOD snapshot, not intraday"
                ],
                "stored_in_db": True
            },
            "yahoo_finance": {
                "name": "Yahoo Finance",
                "description": "Free OHLC data for underlying and VIX",
                "data_available": {
                    "tickers": ["^GSPC (S&P 500)", "^VIX"],
                    "date_range": "Historical to present",
                    "fields": ["open", "high", "low", "close", "volume"]
                },
                "limitations": [
                    "Data fetched on-demand (not stored)",
                    "Rate limits may apply",
                    "No options data"
                ],
                "stored_in_db": False,
                "recommendation": "Should store for faster backtests"
            },
            "polygon_io": {
                "name": "Polygon.io",
                "description": "Real-time and historical market data API",
                "data_available": {
                    "tickers": "All US equities and options",
                    "date_range": "Depends on subscription",
                    "fields": ["trades", "quotes", "aggregates", "options flow"]
                },
                "limitations": [
                    "Requires paid subscription for historical",
                    "Free tier has delays and limits",
                    "Not currently integrated"
                ],
                "stored_in_db": False,
                "recommendation": "Integrate for real-time data and better options data"
            }
        },
        "recommendations": [
            "Store Yahoo Finance daily OHLC for SPX and VIX to speed up backtests",
            "Store Polygon.io options data if you have a subscription",
            "Consider adding intraday data for stop-loss simulation",
            "Add IV surface data for better premium estimation"
        ]
    }


def fetch_yahoo_finance_direct(symbol: str, start_date: str, end_date: str) -> List[Dict]:
    """
    Fetch historical data directly from Yahoo Finance API (no yfinance library).

    Args:
        symbol: Yahoo Finance symbol (e.g., ^GSPC for S&P 500, ^VIX for VIX)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of daily OHLC records
    """
    import requests

    # Convert dates to Unix timestamps
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

    # Yahoo Finance API URL
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    params = {
        "period1": start_ts,
        "period2": end_ts,
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    logger.info(f"Fetching {symbol} from {start_date} to {end_date}...")

    response = requests.get(url, params=params, headers=headers)

    if response.status_code != 200:
        logger.error(f"Error fetching {symbol}: HTTP {response.status_code}")
        return []

    data = response.json()

    # Parse the response
    result = data.get("chart", {}).get("result", [])
    if not result:
        logger.error(f"No data returned for {symbol}")
        return []

    chart_data = result[0]
    timestamps = chart_data.get("timestamp", [])
    quote = chart_data.get("indicators", {}).get("quote", [{}])[0]
    adjclose = chart_data.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])

    records = []
    for i, ts in enumerate(timestamps):
        try:
            date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

            open_price = quote.get("open", [])[i]
            high_price = quote.get("high", [])[i]
            low_price = quote.get("low", [])[i]
            close_price = quote.get("close", [])[i]
            volume = quote.get("volume", [])[i]
            adj_close = adjclose[i] if i < len(adjclose) else close_price

            # Skip if any price is None
            if any(p is None for p in [open_price, high_price, low_price, close_price]):
                continue

            records.append({
                "date": date,
                "open": round(float(open_price), 2),
                "high": round(float(high_price), 2),
                "low": round(float(low_price), 2),
                "close": round(float(close_price), 2),
                "adj_close": round(float(adj_close), 2) if adj_close else round(float(close_price), 2),
                "volume": int(volume) if volume else 0
            })
        except (IndexError, TypeError):
            continue

    logger.info(f"Retrieved {len(records)} records for {symbol}")
    return records


@router.post("/store-market-data")
async def store_market_data(ticker: str = "^GSPC", days: int = 365 * 5):
    """Store Yahoo Finance data in database for faster backtests (no yfinance dependency)"""
    try:
        from datetime import timedelta

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        # Fetch data directly from Yahoo
        records = fetch_yahoo_finance_direct(ticker, start_str, end_str)

        if not records:
            return {"success": False, "error": "No data returned from Yahoo Finance"}

        # Normalize symbol for storage
        symbol_map = {
            "^GSPC": "SPX",
            "^VIX": "VIX"
        }
        normalized_symbol = symbol_map.get(ticker, ticker)

        # Store in database
        conn = get_connection()
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_data_daily (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                open DECIMAL(12,4),
                high DECIMAL(12,4),
                low DECIMAL(12,4),
                close DECIMAL(12,4),
                adj_close DECIMAL(12,4),
                volume BIGINT,
                source VARCHAR(50) DEFAULT 'yahoo',
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, date)
            )
        """)

        # Create index
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_data_daily_symbol_date
            ON market_data_daily(symbol, date)
        """)

        # Insert data
        rows_inserted = 0
        for record in records:
            try:
                cursor.execute("""
                    INSERT INTO market_data_daily (symbol, date, open, high, low, close, adj_close, volume, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        adj_close = EXCLUDED.adj_close,
                        volume = EXCLUDED.volume,
                        source = EXCLUDED.source
                """, (
                    normalized_symbol,
                    record["date"],
                    record["open"],
                    record["high"],
                    record["low"],
                    record["close"],
                    record.get("adj_close", record["close"]),
                    record.get("volume", 0),
                    "yahoo"
                ))
                rows_inserted += 1
            except Exception as e:
                logger.warning(f"Failed to insert row for {record['date']}: {e}")

        conn.commit()
        conn.close()

        return {
            "success": True,
            "ticker": ticker,
            "symbol": normalized_symbol,
            "rows_inserted": rows_inserted,
            "date_range": {
                "start": records[0]["date"] if records else start_str,
                "end": records[-1]["date"] if records else end_str
            }
        }

    except Exception as e:
        logger.error(f"Failed to store market data: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@router.post("/backfill-all")
async def backfill_all_market_data(start_date: str = "2020-01-01"):
    """Backfill all required market data (SPX and VIX) from Yahoo Finance"""
    results = []

    # Symbols to backfill: (yahoo_symbol, normalized_symbol)
    symbols = [
        ("^GSPC", "SPX"),
        ("^VIX", "VIX"),
    ]

    end_date = datetime.now().strftime('%Y-%m-%d')

    for yahoo_symbol, normalized_symbol in symbols:
        try:
            # Fetch data
            records = fetch_yahoo_finance_direct(yahoo_symbol, start_date, end_date)

            if not records:
                results.append({
                    "symbol": normalized_symbol,
                    "success": False,
                    "error": "No data returned"
                })
                continue

            # Store in database
            conn = get_connection()
            cursor = conn.cursor()

            # Ensure table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_data_daily (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    date DATE NOT NULL,
                    open DECIMAL(12,4),
                    high DECIMAL(12,4),
                    low DECIMAL(12,4),
                    close DECIMAL(12,4),
                    adj_close DECIMAL(12,4),
                    volume BIGINT,
                    source VARCHAR(50) DEFAULT 'yahoo',
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(symbol, date)
                )
            """)

            rows_inserted = 0
            for record in records:
                try:
                    cursor.execute("""
                        INSERT INTO market_data_daily (symbol, date, open, high, low, close, adj_close, volume, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            adj_close = EXCLUDED.adj_close,
                            volume = EXCLUDED.volume
                    """, (
                        normalized_symbol,
                        record["date"],
                        record["open"],
                        record["high"],
                        record["low"],
                        record["close"],
                        record.get("adj_close", record["close"]),
                        record.get("volume", 0),
                        "yahoo"
                    ))
                    rows_inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to insert {normalized_symbol} row for {record['date']}: {e}")

            conn.commit()
            conn.close()

            results.append({
                "symbol": normalized_symbol,
                "success": True,
                "rows_inserted": rows_inserted,
                "date_range": {
                    "start": records[0]["date"],
                    "end": records[-1]["date"]
                }
            })

        except Exception as e:
            results.append({
                "symbol": normalized_symbol,
                "success": False,
                "error": str(e)
            })

    return {
        "success": all(r["success"] for r in results),
        "results": results
    }


@router.get("/stored-data-status")
async def get_stored_data_status():
    """Get status of stored market data"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        market_data = []
        orat_data = []

        # Check market_data_daily table (new schema with symbol/date columns)
        try:
            cursor.execute("""
                SELECT
                    symbol,
                    COUNT(*) as row_count,
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date,
                    source
                FROM market_data_daily
                GROUP BY symbol, source
                ORDER BY symbol
            """)

            for row in cursor.fetchall():
                market_data.append({
                    'symbol': row['symbol'],
                    'row_count': row['row_count'],
                    'earliest_date': str(row['earliest_date']),
                    'latest_date': str(row['latest_date']),
                    'source': row.get('source', 'unknown')
                })
        except Exception as e:
            logger.warning(f"market_data_daily table not found or error: {e}")

        # Check ORAT options data
        try:
            cursor.execute("""
                SELECT
                    ticker,
                    COUNT(*) as row_count,
                    MIN(trade_date) as earliest_date,
                    MAX(trade_date) as latest_date
                FROM orat_options_eod
                GROUP BY ticker
                ORDER BY ticker
            """)

            for row in cursor.fetchall():
                orat_data.append({
                    'ticker': row['ticker'],
                    'row_count': row['row_count'],
                    'earliest_date': str(row['earliest_date']),
                    'latest_date': str(row['latest_date'])
                })
        except Exception as e:
            logger.warning(f"orat_options_eod table not found or error: {e}")

        conn.close()

        return {
            "success": True,
            "market_data_daily": market_data,
            "orat_options_eod": orat_data
        }

    except Exception as e:
        logger.error(f"Failed to get data status: {e}")
        return {"success": False, "error": str(e), "market_data_daily": [], "orat_options_eod": []}


@router.get("/data-quality-check")
async def check_data_quality():
    """
    Check data quality for backtesting - especially delta field availability.
    Access via: GET /api/zero-dte/data-quality-check
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        results = {}

        # Check total ORAT records
        cursor.execute("SELECT COUNT(*) FROM orat_options_eod")
        results['total_orat_records'] = cursor.fetchone()[0]

        # Check records with delta
        cursor.execute("SELECT COUNT(*) FROM orat_options_eod WHERE delta IS NOT NULL")
        results['records_with_delta'] = cursor.fetchone()[0]

        # Delta coverage percentage
        if results['total_orat_records'] > 0:
            results['delta_coverage_pct'] = round(
                results['records_with_delta'] / results['total_orat_records'] * 100, 2
            )
        else:
            results['delta_coverage_pct'] = 0

        # Check date range
        cursor.execute("""
            SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date)
            FROM orat_options_eod
        """)
        row = cursor.fetchone()
        results['date_range'] = {
            'earliest': str(row[0]) if row[0] else None,
            'latest': str(row[1]) if row[1] else None,
            'trading_days': row[2] or 0
        }

        # Check SPX vs SPXW breakdown
        cursor.execute("""
            SELECT ticker, COUNT(*) as cnt
            FROM orat_options_eod
            GROUP BY ticker
        """)
        results['by_ticker'] = {row[0]: row[1] for row in cursor.fetchall()}

        # Sample of delta values (to verify they're reasonable)
        cursor.execute("""
            SELECT delta FROM orat_options_eod
            WHERE delta IS NOT NULL
            LIMIT 10
        """)
        sample_deltas = [float(row[0]) for row in cursor.fetchall()]
        results['sample_deltas'] = sample_deltas

        conn.close()

        # Provide recommendation
        if results['delta_coverage_pct'] >= 90:
            results['delta_status'] = "GOOD - Delta data available"
            results['recommendation'] = "Delta-based strike selection will work"
        elif results['delta_coverage_pct'] >= 50:
            results['delta_status'] = "PARTIAL - Some delta data available"
            results['recommendation'] = "Delta selection may work but will often fall back to SD"
        else:
            results['delta_status'] = "MISSING - Delta data not available"
            results['recommendation'] = "Use SD or Fixed strike selection instead"

        return {"success": True, **results}

    except Exception as e:
        logger.error(f"Data quality check failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# STRATEGY PRESETS AND SAVED STRATEGIES
# ============================================================================

class SavedStrategy(BaseModel):
    """Model for saved strategy configurations"""
    name: str = Field(..., description="Strategy name")
    description: str = Field(default="", description="Strategy description")
    config: Dict[str, Any] = Field(..., description="Strategy configuration")
    tags: List[str] = Field(default=[], description="Tags for filtering")


# Built-in strategy presets
STRATEGY_PRESETS = [
    {
        "id": "conservative_ic",
        "name": "Conservative IC",
        "description": "Standard Iron Condor with 1.5 SD multiplier for wider strikes and lower risk",
        "is_preset": True,
        "tags": ["conservative", "iron_condor", "low_risk"],
        "config": {
            "strategy_type": "iron_condor",
            "sd_multiplier": 1.5,
            "risk_per_trade_pct": 3.0,
            "spread_width": 10.0,
            "max_vix": 30,
            "strike_selection": "sd"
        }
    },
    {
        "id": "aggressive_ic",
        "name": "Aggressive IC",
        "description": "Aggressive Iron Condor with 0.8 SD multiplier for tighter strikes and higher premium",
        "is_preset": True,
        "tags": ["aggressive", "iron_condor", "high_premium"],
        "config": {
            "strategy_type": "iron_condor",
            "sd_multiplier": 0.8,
            "risk_per_trade_pct": 8.0,
            "spread_width": 10.0,
            "min_vix": 15,
            "strike_selection": "sd"
        }
    },
    {
        "id": "gex_protected_ic",
        "name": "GEX-Protected IC",
        "description": "Iron Condor using GEX walls for strike selection with SD fallback. Trades with additional protection from gamma exposure levels.",
        "is_preset": True,
        "tags": ["gex", "iron_condor", "protected"],
        "config": {
            "strategy_type": "gex_protected_iron_condor",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "sd"
        }
    },
    {
        "id": "vix_filter_ic",
        "name": "VIX Filter IC",
        "description": "Iron Condor only trading in elevated volatility (VIX 18-35) for better premium",
        "is_preset": True,
        "tags": ["vix_filter", "iron_condor", "volatility"],
        "config": {
            "strategy_type": "iron_condor",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "min_vix": 18,
            "max_vix": 35,
            "strike_selection": "sd"
        }
    },
    {
        "id": "mon_wed_ic",
        "name": "Monday-Wednesday IC",
        "description": "Iron Condor trading only on Mon/Wed for lower theta decay competition",
        "is_preset": True,
        "tags": ["day_filter", "iron_condor"],
        "config": {
            "strategy_type": "iron_condor",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "trade_monday": True,
            "trade_tuesday": False,
            "trade_wednesday": True,
            "trade_thursday": False,
            "trade_friday": False,
            "strike_selection": "sd"
        }
    },
    {
        "id": "delta_based_ic",
        "name": "Delta-Based IC",
        "description": "Iron Condor using 16-delta strikes for consistent probability-based positioning",
        "is_preset": True,
        "tags": ["delta", "iron_condor", "probability"],
        "config": {
            "strategy_type": "iron_condor",
            "target_delta": 0.16,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "delta"
        }
    }
]

# In-memory storage for user-saved strategies (in production, use database)
_saved_strategies: Dict[str, Dict] = {}


@router.get("/presets")
async def get_strategy_presets():
    """
    Get built-in strategy presets.

    These are pre-configured strategy configurations that users can select
    and optionally modify before running a backtest.
    """
    return {
        "success": True,
        "presets": STRATEGY_PRESETS
    }


def _ensure_saved_strategies_table(cursor):
    """Ensure the saved_strategies table exists"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_strategies (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            user_id VARCHAR(100) DEFAULT NULL,
            strategy_type VARCHAR(50) NOT NULL,
            parameters JSONB NOT NULL,
            last_backtest_date TIMESTAMP WITH TIME ZONE,
            backtest_results JSONB,
            is_preset BOOLEAN DEFAULT FALSE,
            is_public BOOLEAN DEFAULT FALSE,
            tags VARCHAR(255)[],
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create unique constraint if not exists (ignore error if already exists)
    try:
        cursor.execute("""
            ALTER TABLE saved_strategies
            ADD CONSTRAINT unique_strategy_name_user UNIQUE (name, user_id)
        """)
    except:
        pass  # Constraint already exists


@router.get("/saved-strategies")
async def get_saved_strategies():
    """
    Get user-saved strategy configurations.

    Returns both built-in presets and user-saved strategies.
    """
    # Try to load from database
    strategies = []

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Ensure table exists
        _ensure_saved_strategies_table(cursor)
        conn.commit()

        cursor.execute("""
            SELECT id, name, description, strategy_type, parameters,
                   is_preset, tags, created_at, updated_at, backtest_results
            FROM saved_strategies
            ORDER BY is_preset DESC, name
        """)

        for row in cursor.fetchall():
            strategies.append({
                "id": str(row['id']),
                "name": row['name'],
                "description": row['description'] or "",
                "strategy_type": row['strategy_type'],
                "config": row['parameters'] if isinstance(row['parameters'], dict) else json.loads(row['parameters'] or '{}'),
                "is_preset": row['is_preset'],
                "tags": row['tags'] or [],
                "created_at": str(row['created_at']) if row['created_at'] else None,
                "backtest_results": row['backtest_results']
            })

        conn.close()

    except Exception as e:
        logger.warning(f"Could not load saved strategies from database: {e}")
        # Fall back to in-memory storage
        strategies = list(_saved_strategies.values())

    # Add presets if not in database
    preset_names = {s['name'] for s in strategies if s.get('is_preset')}
    for preset in STRATEGY_PRESETS:
        if preset['name'] not in preset_names:
            strategies.append(preset)

    return {
        "success": True,
        "strategies": strategies
    }


@router.post("/saved-strategies")
async def save_strategy(strategy: SavedStrategy):
    """
    Save a custom strategy configuration.

    Users can save their backtest configurations for later use.
    """
    strategy_id = f"user_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    strategy_data = {
        "id": strategy_id,
        "name": strategy.name,
        "description": strategy.description,
        "config": strategy.config,
        "tags": strategy.tags,
        "is_preset": False,
        "created_at": datetime.now().isoformat()
    }

    # Try to save to database
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Ensure table exists
        _ensure_saved_strategies_table(cursor)
        conn.commit()

        cursor.execute("""
            INSERT INTO saved_strategies (name, description, strategy_type, parameters, is_preset, tags)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (name, user_id) DO UPDATE SET
                description = EXCLUDED.description,
                parameters = EXCLUDED.parameters,
                tags = EXCLUDED.tags,
                updated_at = NOW()
            RETURNING id
        """, (
            strategy.name,
            strategy.description,
            strategy.config.get('strategy_type', 'iron_condor'),
            json.dumps(strategy.config),
            False,
            strategy.tags
        ))

        row = cursor.fetchone()
        if row:
            strategy_id = str(row[0])

        conn.commit()
        conn.close()

        logger.info(f"Saved strategy '{strategy.name}' to database")

    except Exception as e:
        logger.warning(f"Could not save to database, using in-memory: {e}")
        # Fall back to in-memory storage
        _saved_strategies[strategy_id] = strategy_data

    return {
        "success": True,
        "strategy_id": strategy_id,
        "message": f"Strategy '{strategy.name}' saved successfully"
    }


@router.delete("/saved-strategies/{strategy_id}")
async def delete_saved_strategy(strategy_id: str):
    """Delete a user-saved strategy (cannot delete presets)"""

    # Check if it's a preset
    for preset in STRATEGY_PRESETS:
        if preset['id'] == strategy_id:
            raise HTTPException(status_code=400, detail="Cannot delete built-in presets")

    # Try to delete from database
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM saved_strategies
            WHERE id = %s AND is_preset = FALSE
            RETURNING id
        """, (strategy_id,))

        row = cursor.fetchone()
        conn.commit()
        conn.close()

        if row:
            return {"success": True, "message": "Strategy deleted"}

    except Exception as e:
        logger.warning(f"Could not delete from database: {e}")

    # Try in-memory
    if strategy_id in _saved_strategies:
        del _saved_strategies[strategy_id]
        return {"success": True, "message": "Strategy deleted"}

    raise HTTPException(status_code=404, detail="Strategy not found")


# ============================================================================
# ORACLE CLAUDE AI ENDPOINTS
# ============================================================================

class OracleAnalysisRequest(BaseModel):
    """Request model for Oracle Claude analysis"""
    spot_price: float = Field(default=5000.0, description="Current spot price")
    vix: float = Field(default=20.0, description="Current VIX")
    gex_regime: str = Field(default="NEUTRAL", description="GEX regime: POSITIVE, NEGATIVE, NEUTRAL")
    gex_normalized: float = Field(default=0.0, description="Normalized GEX value")
    gex_call_wall: float = Field(default=0.0, description="GEX call wall strike")
    gex_put_wall: float = Field(default=0.0, description="GEX put wall strike")
    day_of_week: int = Field(default=2, description="Day of week (0=Mon, 4=Fri)")
    bot_name: str = Field(default="ARES", description="Bot name: ARES, ATLAS, PHOENIX")


class OracleExplainRequest(BaseModel):
    """Request model for explaining Oracle prediction"""
    prediction: Dict[str, Any] = Field(..., description="Oracle prediction to explain")
    context: Dict[str, Any] = Field(..., description="Market context used")


@router.get("/oracle/status")
async def get_oracle_status():
    """
    Get Oracle system status including Claude AI availability.

    Returns information about:
    - ML model status (trained/untrained)
    - Claude AI status (enabled/disabled)
    - Model version
    """
    try:
        from quant.oracle_advisor import get_oracle

        oracle = get_oracle()

        return {
            "success": True,
            "oracle": {
                "model_trained": oracle.is_trained,
                "model_version": oracle.model_version,
                "claude_available": oracle.claude_available,
                "claude_model": oracle.claude.CLAUDE_MODEL if oracle.claude else None,
                "high_confidence_threshold": oracle.high_confidence_threshold,
                "low_confidence_threshold": oracle.low_confidence_threshold,
            }
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}"
        }
    except Exception as e:
        logger.error(f"Failed to get Oracle status: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/oracle/analyze")
async def oracle_analyze(request: OracleAnalysisRequest):
    """
    Get Oracle advice with Claude AI validation.

    This endpoint:
    1. Creates market context from request
    2. Gets ML-based prediction from Oracle
    3. Validates with Claude AI (if available)
    4. Returns combined analysis

    Use this for live trading decisions.
    """
    try:
        from quant.oracle_advisor import (
            get_oracle, MarketContext, GEXRegime, BotName
        )

        oracle = get_oracle()

        # Parse GEX regime
        gex_regime = GEXRegime[request.gex_regime.upper()]

        # Parse bot name
        bot_name = BotName[request.bot_name.upper()]

        # Build market context
        context = MarketContext(
            spot_price=request.spot_price,
            vix=request.vix,
            gex_regime=gex_regime,
            gex_normalized=request.gex_normalized,
            gex_call_wall=request.gex_call_wall,
            gex_put_wall=request.gex_put_wall,
            day_of_week=request.day_of_week,
            gex_between_walls=(
                request.gex_put_wall < request.spot_price < request.gex_call_wall
            ) if request.gex_call_wall > 0 and request.gex_put_wall > 0 else True
        )

        # Get advice based on bot type
        if bot_name == BotName.ARES:
            prediction = oracle.get_ares_advice(
                context,
                use_gex_walls=(request.gex_call_wall > 0 and request.gex_put_wall > 0),
                use_claude_validation=True
            )
        elif bot_name == BotName.ATLAS:
            prediction = oracle.get_atlas_advice(context)
        elif bot_name == BotName.PHOENIX:
            prediction = oracle.get_phoenix_advice(context)
        else:
            prediction = oracle.get_ares_advice(context)

        # Get Claude explanation if available
        explanation = None
        if oracle.claude_available:
            explanation = oracle.explain_prediction(prediction, context)

        return {
            "success": True,
            "prediction": {
                "bot_name": prediction.bot_name.value,
                "advice": prediction.advice.value,
                "win_probability": prediction.win_probability,
                "confidence": prediction.confidence,
                "suggested_risk_pct": prediction.suggested_risk_pct,
                "suggested_sd_multiplier": prediction.suggested_sd_multiplier,
                "use_gex_walls": prediction.use_gex_walls,
                "suggested_put_strike": prediction.suggested_put_strike,
                "suggested_call_strike": prediction.suggested_call_strike,
                "reasoning": prediction.reasoning,
                "model_version": prediction.model_version,
                "top_factors": prediction.top_factors
            },
            "claude_explanation": explanation,
            "claude_available": oracle.claude_available,
            "context": {
                "spot_price": context.spot_price,
                "vix": context.vix,
                "gex_regime": context.gex_regime.value,
                "day_of_week": context.day_of_week
            }
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}"
        }
    except Exception as e:
        logger.error(f"Oracle analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/oracle/explain")
async def oracle_explain(request: OracleExplainRequest):
    """
    Get Claude AI explanation of an Oracle prediction.

    Takes a prediction object and market context, returns
    a natural language explanation suitable for traders.
    """
    try:
        from quant.oracle_advisor import (
            get_oracle, MarketContext, GEXRegime, BotName,
            TradingAdvice, OraclePrediction
        )

        oracle = get_oracle()

        if not oracle.claude_available:
            return {
                "success": False,
                "error": "Claude AI not available. Set ANTHROPIC_API_KEY environment variable."
            }

        # Reconstruct prediction object
        pred_data = request.prediction
        prediction = OraclePrediction(
            bot_name=BotName[pred_data.get('bot_name', 'ARES')],
            advice=TradingAdvice[pred_data.get('advice', 'TRADE_FULL')],
            win_probability=pred_data.get('win_probability', 0.68),
            confidence=pred_data.get('confidence', 70),
            suggested_risk_pct=pred_data.get('suggested_risk_pct', 5.0),
            suggested_sd_multiplier=pred_data.get('suggested_sd_multiplier', 1.0),
            use_gex_walls=pred_data.get('use_gex_walls', False),
            suggested_put_strike=pred_data.get('suggested_put_strike'),
            suggested_call_strike=pred_data.get('suggested_call_strike'),
            reasoning=pred_data.get('reasoning', ''),
            model_version=pred_data.get('model_version', '1.0.0')
        )

        # Reconstruct market context
        ctx_data = request.context
        context = MarketContext(
            spot_price=ctx_data.get('spot_price', 5000),
            vix=ctx_data.get('vix', 20),
            gex_regime=GEXRegime[ctx_data.get('gex_regime', 'NEUTRAL')],
            gex_normalized=ctx_data.get('gex_normalized', 0),
            gex_call_wall=ctx_data.get('gex_call_wall', 0),
            gex_put_wall=ctx_data.get('gex_put_wall', 0),
            day_of_week=ctx_data.get('day_of_week', 2),
            gex_between_walls=ctx_data.get('gex_between_walls', True)
        )

        explanation = oracle.explain_prediction(prediction, context)

        return {
            "success": True,
            "explanation": explanation
        }

    except Exception as e:
        logger.error(f"Oracle explain failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/oracle/logs")
async def get_oracle_logs(limit: int = 50):
    """
    Get Oracle live logs for frontend transparency.

    Returns recent Claude AI interactions, validations, and analyses.
    Use this for real-time monitoring of Oracle's reasoning.
    """
    try:
        from quant.oracle_advisor import oracle_live_log

        logs = oracle_live_log.get_logs(limit=limit)

        return {
            "success": True,
            "logs": logs,
            "count": len(logs)
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}",
            "logs": []
        }
    except Exception as e:
        logger.error(f"Failed to get Oracle logs: {e}")
        return {
            "success": False,
            "error": str(e),
            "logs": []
        }


@router.delete("/oracle/logs")
async def clear_oracle_logs():
    """Clear Oracle live logs"""
    try:
        from quant.oracle_advisor import oracle_live_log

        oracle_live_log.clear()

        return {"success": True, "message": "Logs cleared"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/oracle/analyze-patterns")
async def oracle_analyze_patterns(job_id: Optional[str] = None):
    """
    Use Claude AI to analyze patterns in backtest results.

    If job_id is provided, analyzes that specific backtest.
    Otherwise, analyzes any available training data.

    Returns identified patterns, loss conditions, and recommendations.
    """
    try:
        from quant.oracle_advisor import get_oracle

        oracle = get_oracle()

        if not oracle.claude_available:
            return {
                "success": False,
                "error": "Claude AI not available. Set ANTHROPIC_API_KEY environment variable."
            }

        # Get backtest results if job_id provided
        backtest_results = None
        if job_id and job_id in _jobs:
            job = _jobs[job_id]
            if job['status'] == 'completed' and job.get('result'):
                backtest_results = job['result']

        # Run pattern analysis
        analysis = oracle.analyze_patterns(backtest_results)

        return {
            "success": analysis.get('success', False),
            "patterns": analysis.get('patterns', []),
            "loss_conditions": analysis.get('loss_conditions', []),
            "optimal_conditions": analysis.get('optimal_conditions', []),
            "recommendations": analysis.get('recommendations', []),
            "raw_analysis": analysis.get('raw_analysis', ''),
            "error": analysis.get('error')
        }

    except Exception as e:
        logger.error(f"Pattern analysis failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/export/result/{result_id}")
async def export_result_by_id(result_id: int):
    """Export a specific backtest result by database ID"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM zero_dte_backtest_results WHERE id = %s
        """, (result_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Result not found")

        # Create CSV output
        output = io.StringIO()

        # Summary section
        output.write("BACKTEST RESULT EXPORT\n")
        output.write("=" * 50 + "\n\n")

        output.write(f"Backtest ID,{row['id']}\n")
        output.write(f"Job ID,{row['job_id']}\n")
        output.write(f"Created At,{row['created_at']}\n")
        output.write(f"Strategy,{row['strategy']}\n")
        output.write(f"Ticker,{row['ticker']}\n")
        output.write(f"Period,{row['start_date']} to {row['end_date']}\n\n")

        output.write("PERFORMANCE SUMMARY\n")
        output.write("-" * 30 + "\n")
        output.write(f"Initial Capital,${row['initial_capital']:,.2f}\n")
        output.write(f"Final Equity,${row['final_equity']:,.2f}\n")
        output.write(f"Total P&L,${row['total_pnl']:,.2f}\n")
        output.write(f"Total Return,{row['total_return_pct']:.2f}%\n")
        output.write(f"Avg Monthly Return,{row['avg_monthly_return_pct']:.2f}%\n")
        output.write(f"Max Drawdown,{row['max_drawdown_pct']:.2f}%\n")
        output.write(f"Total Trades,{row['total_trades']}\n")
        output.write(f"Win Rate,{row['win_rate']:.2f}%\n")
        output.write(f"Profit Factor,{row['profit_factor']:.2f}\n")
        output.write(f"Total Costs,${row['total_costs']:,.2f}\n\n")

        # Tier stats if available
        if row.get('tier_stats'):
            output.write("TIER STATISTICS\n")
            output.write("-" * 30 + "\n")
            tier_stats = row['tier_stats']
            if isinstance(tier_stats, dict):
                for tier_name, stats in tier_stats.items():
                    if isinstance(stats, dict):
                        output.write(f"\n{tier_name}:\n")
                        for key, value in stats.items():
                            output.write(f"  {key},{value}\n")
            output.write("\n")

        # Monthly returns if available
        if row.get('monthly_returns'):
            output.write("MONTHLY RETURNS\n")
            output.write("-" * 30 + "\n")
            output.write("Month,Return %\n")
            monthly = row['monthly_returns']
            if isinstance(monthly, dict):
                for month, ret in monthly.items():
                    output.write(f"{month},{ret:.2f}\n")
            elif isinstance(monthly, list):
                for item in monthly:
                    if isinstance(item, dict):
                        output.write(f"{item.get('month', 'N/A')},{item.get('return_pct', 0):.2f}\n")

        csv_content = output.getvalue()
        output.close()

        filename = f"backtest_result_{result_id}_{row['strategy']}_{row['start_date']}_to_{row['end_date']}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export result {result_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/all-results")
async def export_all_results():
    """Export all backtest results as CSV"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM zero_dte_backtest_results
            ORDER BY created_at DESC
        """)

        results = cursor.fetchall()
        conn.close()

        if not results:
            raise HTTPException(status_code=404, detail="No results found")

        # Create CSV output
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            'ID', 'Job ID', 'Created At', 'Strategy', 'Ticker',
            'Start Date', 'End Date', 'Initial Capital', 'Final Equity',
            'Total P&L', 'Total Return %', 'Avg Monthly Return %',
            'Max Drawdown %', 'Total Trades', 'Win Rate %',
            'Profit Factor', 'Total Costs'
        ])

        # Data rows
        for row in results:
            writer.writerow([
                row['id'],
                row['job_id'],
                row['created_at'].isoformat() if row['created_at'] else '',
                row['strategy'],
                row['ticker'],
                str(row['start_date']),
                str(row['end_date']),
                f"{row['initial_capital']:.2f}",
                f"{row['final_equity']:.2f}",
                f"{row['total_pnl']:.2f}",
                f"{row['total_return_pct']:.2f}",
                f"{row['avg_monthly_return_pct']:.2f}",
                f"{row['max_drawdown_pct']:.2f}",
                row['total_trades'],
                f"{row['win_rate']:.2f}",
                f"{row['profit_factor']:.2f}",
                f"{row['total_costs']:.2f}"
            ])

        csv_content = output.getvalue()
        output.close()

        filename = f"all_backtest_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export all results: {e}")
        raise HTTPException(status_code=500, detail=str(e))
