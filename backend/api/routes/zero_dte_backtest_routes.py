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

    # Swing trading
    hold_days: int = Field(default=1, description="Hold duration: 1=day trade (exit same day), 2+=swing trade")

    # Apache directional settings
    wall_proximity_pct: float = Field(default=1.0, description="Wall proximity threshold for Apache (1.0=1%, 2.0=2%, etc)")


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
            # Swing trading
            hold_days=config.hold_days,
            # Apache directional settings
            wall_proximity_pct=config.wall_proximity_pct,
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


def _format_strategy_name(strategy_type: str) -> str:
    """Convert strategy_type to a human-readable display name"""
    STRATEGY_NAMES = {
        "iron_condor": "Iron Condor",
        "bull_put": "Bull Put Spread",
        "bear_call": "Bear Call Spread",
        "iron_butterfly": "Iron Butterfly",
        "diagonal_call": "Diagonal Call (PMCC)",
        "diagonal_put": "Diagonal Put (PMCP)",
        "gex_protected_iron_condor": "GEX-Protected IC",
        "bull_call": "Bull Call Spread",
        "bear_put": "Bear Put Spread",
        "apache_directional": "Apache Directional",
    }
    return STRATEGY_NAMES.get(strategy_type, strategy_type.replace("_", " ").title())


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

        # Get formatted strategy name from strategy_type
        strategy_display_name = _format_strategy_name(config.strategy_type)

        # Debug logging
        print(f"📝 KRONOS: Saving backtest - job_id={job_id}, strategy={strategy_display_name}, trades={total_trades}, return={total_return_pct:.2f}%", flush=True)

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
            strategy_display_name,
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
                "id": "bear_put",
                "name": "Bear Put Spread",
                "description": "Buy ATM put, sell OTM put below. Profit if price falls. Debit spread with defined risk.",
                "legs": 2,
                "direction": "bearish",
                "credit": False
            },
            {
                "id": "apache_directional",
                "name": "APACHE GEX Directional",
                "description": "DEBIT SPREADS ONLY. Bull Call near put wall (support), Bear Put near call wall (resistance). Only trades at GEX walls.",
                "legs": 2,
                "direction": "adaptive",
                "credit": False,
                "note": "Bullish debit when near put wall, Bearish debit when near call wall. Skips trades when not near walls.",
                "features": ["GEX wall timing", "Debit spreads only", "Defined risk"]
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
    },
    {
        "id": "apache_directional",
        "name": "Apache GEX Directional",
        "description": "Trades debit spreads at GEX walls. Bull Call near put wall (support), Bear Put near call wall (resistance). Only trades when near walls.",
        "is_preset": True,
        "tags": ["apache", "gex", "directional", "debit"],
        "config": {
            "strategy_type": "apache_directional",
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "wall_proximity_pct": 1.0,
            "strike_selection": "sd",
            "sd_multiplier": 1.0
        }
    },
    {
        "id": "bull_put_credit",
        "name": "Bull Put Spread",
        "description": "Bullish credit spread - sell put, buy lower put. Profit if price stays above short strike.",
        "is_preset": True,
        "tags": ["bullish", "credit", "put_spread"],
        "config": {
            "strategy_type": "bull_put",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "sd"
        }
    },
    {
        "id": "bear_call_credit",
        "name": "Bear Call Spread",
        "description": "Bearish credit spread - sell call, buy higher call. Profit if price stays below short strike.",
        "is_preset": True,
        "tags": ["bearish", "credit", "call_spread"],
        "config": {
            "strategy_type": "bear_call",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "sd"
        }
    },
    {
        "id": "iron_butterfly",
        "name": "Iron Butterfly",
        "description": "ATM short straddle with OTM wings. Maximum profit at center strike, ideal for range-bound markets.",
        "is_preset": True,
        "tags": ["neutral", "iron_butterfly", "high_premium"],
        "config": {
            "strategy_type": "iron_butterfly",
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "sd",
            "sd_multiplier": 1.0
        }
    },
    {
        "id": "bull_call_debit",
        "name": "Bull Call Spread",
        "description": "Bullish debit spread - buy ATM call, sell higher OTM call. Profit if price rises above breakeven.",
        "is_preset": True,
        "tags": ["bullish", "debit", "call_spread"],
        "config": {
            "strategy_type": "bull_call",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "sd"
        }
    },
    {
        "id": "bear_put_debit",
        "name": "Bear Put Spread",
        "description": "Bearish debit spread - buy ATM put, sell lower OTM put. Profit if price falls below breakeven.",
        "is_preset": True,
        "tags": ["bearish", "debit", "put_spread"],
        "config": {
            "strategy_type": "bear_put",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "sd"
        }
    },
    {
        "id": "diagonal_call_pmcc",
        "name": "Diagonal Call (PMCC)",
        "description": "Poor Man's Covered Call - sell near-term OTM call, buy longer-term ITM/ATM call. Profit from premium and theta decay.",
        "is_preset": True,
        "tags": ["diagonal", "pmcc", "theta"],
        "config": {
            "strategy_type": "diagonal_call",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "sd"
        }
    },
    {
        "id": "diagonal_put_pmcp",
        "name": "Diagonal Put (PMCP)",
        "description": "Poor Man's Covered Put - sell near-term OTM put, buy longer-term ITM/ATM put. Profit from premium and theta decay.",
        "is_preset": True,
        "tags": ["diagonal", "pmcp", "theta"],
        "config": {
            "strategy_type": "diagonal_put",
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "spread_width": 10.0,
            "strike_selection": "sd"
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


def _get_all_heartbeats() -> dict:
    """Get heartbeat info for all bots from the database"""
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT bot_name, last_heartbeat, status, scan_count, details
            FROM bot_heartbeats
            ORDER BY last_heartbeat DESC
        ''')

        rows = cursor.fetchall()
        conn.close()

        heartbeats = {}
        for row in rows:
            bot_name, last_heartbeat, status, scan_count, details = row

            # Convert timestamp to Central Time
            last_heartbeat_ct = None
            if last_heartbeat:
                # PostgreSQL may return UTC or naive datetime - handle both cases
                if last_heartbeat.tzinfo is None:
                    # Naive datetime from PostgreSQL - assume it's UTC
                    last_heartbeat = last_heartbeat.replace(tzinfo=ZoneInfo("UTC"))
                # Convert to Central Time
                last_heartbeat_ct = last_heartbeat.astimezone(CENTRAL_TZ)

            heartbeats[bot_name] = {
                'last_scan': last_heartbeat_ct.strftime('%Y-%m-%d %H:%M:%S CT') if last_heartbeat_ct else None,
                'last_scan_iso': last_heartbeat_ct.isoformat() if last_heartbeat_ct else None,
                'status': status,
                'scan_count_today': scan_count or 0,
                'details': details or {}
            }
        return heartbeats
    except Exception as e:
        logger.debug(f"Could not get heartbeats: {e}")
        return {}


@router.get("/oracle/status")
async def get_oracle_status():
    """
    Get Oracle system status including Claude AI availability and bot heartbeats.

    Returns information about:
    - ML model status (trained/untrained)
    - Claude AI status (enabled/disabled)
    - Model version
    - All bot heartbeats (ARES, ATHENA, etc.)
    """
    try:
        from quant.oracle_advisor import get_oracle

        oracle = get_oracle()

        # Get heartbeats for all bots
        heartbeats = _get_all_heartbeats()

        return {
            "success": True,
            "oracle": {
                "model_trained": oracle.is_trained,
                "model_version": oracle.model_version,
                "claude_available": oracle.claude_available,
                "claude_model": oracle.claude.CLAUDE_MODEL if oracle.claude else None,
                "high_confidence_threshold": oracle.high_confidence_threshold,
                "low_confidence_threshold": oracle.low_confidence_threshold,
            },
            "bot_heartbeats": heartbeats
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}",
            "bot_heartbeats": _get_all_heartbeats()
        }
    except Exception as e:
        logger.error(f"Failed to get Oracle status: {e}")
        return {
            "success": False,
            "error": str(e),
            "bot_heartbeats": _get_all_heartbeats()
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


@router.get("/oracle/data-flows")
async def get_oracle_data_flows(limit: int = 50, bot_name: str = None):
    """
    Get detailed Oracle data flow records for FULL TRANSPARENCY.

    Returns complete data at each stage of the Oracle pipeline:
    - INPUT: Market context data fed into Oracle
    - ML_OUTPUT: ML model predictions and features
    - DECISION: Final advice with all reasoning

    This gives you complete visibility into what data Oracle is processing.
    """
    try:
        from quant.oracle_advisor import oracle_live_log

        flows = oracle_live_log.get_data_flows(limit=limit, bot_name=bot_name)

        return {
            "success": True,
            "data_flows": flows,
            "count": len(flows)
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}",
            "data_flows": []
        }
    except Exception as e:
        logger.error(f"Failed to get Oracle data flows: {e}")
        return {
            "success": False,
            "error": str(e),
            "data_flows": []
        }


@router.get("/oracle/claude-exchanges")
async def get_oracle_claude_exchanges(limit: int = 20, bot_name: str = None):
    """
    Get COMPLETE Claude AI exchanges with FULL TRANSPARENCY.

    Returns the EXACT prompts sent to Claude and EXACT responses received.
    This is critical for:
    - Seeing what market data Claude is analyzing
    - Understanding Claude's reasoning
    - Verifying Claude is not hallucinating
    - Full audit trail of AI decision-making

    Each exchange includes:
    - prompt_sent: The full prompt text sent to Claude
    - response_received: The complete response from Claude
    - market_context: All market data that was included
    - ml_prediction: The ML model's prediction that was validated
    - tokens_used: Token consumption for cost tracking
    - response_time_ms: Response latency
    """
    try:
        from quant.oracle_advisor import oracle_live_log

        exchanges = oracle_live_log.get_claude_exchanges(limit=limit, bot_name=bot_name)

        return {
            "success": True,
            "claude_exchanges": exchanges,
            "count": len(exchanges)
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}",
            "claude_exchanges": []
        }
    except Exception as e:
        logger.error(f"Failed to get Claude exchanges: {e}")
        return {
            "success": False,
            "error": str(e),
            "claude_exchanges": []
        }


@router.get("/oracle/full-transparency")
async def get_oracle_full_transparency(bot_name: str = None):
    """
    Get COMPLETE Oracle transparency data in one call.

    Returns everything:
    - Recent logs (500 max)
    - Data flows with full input/output at each stage
    - Complete Claude AI exchanges with full prompt/response
    - Latest data flow for each bot

    Use this endpoint for the Oracle transparency dashboard.
    """
    try:
        from quant.oracle_advisor import oracle_live_log

        # Get all transparency data
        logs = oracle_live_log.get_logs(limit=100)
        data_flows = oracle_live_log.get_data_flows(limit=50, bot_name=bot_name)
        claude_exchanges = oracle_live_log.get_claude_exchanges(limit=20, bot_name=bot_name)

        # Get latest flow per bot
        latest_by_bot = {}
        for bot in ['ARES', 'ATHENA', 'ICARUS', 'PEGASUS', 'TITAN', 'PHOENIX']:
            latest = oracle_live_log.get_latest_flow_for_bot(bot)
            if latest:
                latest_by_bot[bot] = latest

        return {
            "success": True,
            "logs": logs,
            "data_flows": data_flows,
            "claude_exchanges": claude_exchanges,
            "latest_by_bot": latest_by_bot,
            "summary": {
                "total_logs": len(logs),
                "total_data_flows": len(data_flows),
                "total_claude_exchanges": len(claude_exchanges)
            }
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}",
            "logs": [],
            "data_flows": [],
            "claude_exchanges": [],
            "latest_by_bot": {}
        }
    except Exception as e:
        logger.error(f"Failed to get Oracle transparency data: {e}")
        return {
            "success": False,
            "error": str(e),
            "logs": [],
            "data_flows": [],
            "claude_exchanges": [],
            "latest_by_bot": {}
        }


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


@router.get("/oracle/training-status")
async def get_oracle_training_status():
    """
    Get comprehensive Oracle training status.

    Returns information about:
    - Model training status and version
    - Pending outcomes count
    - Training metrics if available
    - Whether retraining is needed
    """
    try:
        from quant.oracle_advisor import get_training_status

        status = get_training_status()

        return {
            "success": True,
            **status
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}"
        }
    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/oracle/trigger-training")
async def trigger_oracle_training(force: bool = False):
    """
    Manually trigger Oracle model training.

    Args:
        force: If True, train even if threshold not met

    Returns:
        Training result with metrics
    """
    try:
        from quant.oracle_advisor import auto_train

        result = auto_train(force=force)

        return {
            "success": result.get('success', False),
            **result
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Oracle module not available: {e}"
        }
    except Exception as e:
        logger.error(f"Failed to trigger training: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/oracle/predictions")
async def get_oracle_predictions_full(
    days: int = 30,
    limit: int = 100,
    bot_name: Optional[str] = None,
    include_claude: bool = True
):
    """
    Get full Oracle predictions with Claude analysis data.

    Args:
        days: Number of days to look back (default: 30)
        limit: Maximum number of predictions (default: 100)
        bot_name: Filter by bot (ARES, ATLAS, PHOENIX, ATHENA)
        include_claude: Include Claude analysis data (default: True)

    Returns comprehensive prediction data including:
    - Market context at prediction time
    - ML model prediction details
    - Claude AI analysis and reasoning
    - Actual outcomes if available
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = """
            SELECT
                id, trade_date, bot_name, prediction_time,
                spot_price, vix, gex_net, gex_normalized, gex_regime,
                gex_flip_point, gex_call_wall, gex_put_wall, day_of_week,
                advice, win_probability, confidence,
                suggested_risk_pct, suggested_sd_multiplier,
                use_gex_walls, suggested_put_strike, suggested_call_strike,
                reasoning, top_factors, model_version,
                claude_analysis,
                prediction_used, actual_outcome, actual_pnl, outcome_date
            FROM oracle_predictions
            WHERE trade_date >= CURRENT_DATE - INTERVAL '%s days'
        """
        params = [days]

        if bot_name:
            query += " AND bot_name = %s"
            params.append(bot_name.upper())

        query += " ORDER BY trade_date DESC, prediction_time DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        predictions = []
        for row in rows:
            pred = dict(row)

            # Parse JSONB fields - ensure top_factors is always a dict or None
            top_factors = pred.get('top_factors')
            if top_factors is not None:
                if isinstance(top_factors, str):
                    try:
                        parsed = json.loads(top_factors)
                        pred['top_factors'] = parsed if isinstance(parsed, dict) else {}
                    except (json.JSONDecodeError, TypeError):
                        pred['top_factors'] = {}
                elif not isinstance(top_factors, dict):
                    pred['top_factors'] = {}

            # Include or exclude Claude analysis
            if include_claude:
                claude_analysis = pred.get('claude_analysis')
                if claude_analysis is not None:
                    if isinstance(claude_analysis, str):
                        try:
                            parsed = json.loads(claude_analysis)
                            pred['claude_analysis'] = parsed if isinstance(parsed, dict) else None
                        except (json.JSONDecodeError, TypeError):
                            pred['claude_analysis'] = None
                    elif not isinstance(claude_analysis, dict):
                        pred['claude_analysis'] = None
            else:
                pred.pop('claude_analysis', None)

            predictions.append(pred)

        return {
            "success": True,
            "predictions": predictions,
            "count": len(predictions),
            "days": days
        }

    except Exception as e:
        logger.error(f"Failed to get predictions: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "predictions": []
        }


@router.get("/oracle/bot-interactions")
async def get_oracle_bot_interactions(
    days: int = 7,
    limit: int = 200,
    bot_name: Optional[str] = None
):
    """
    Get all bot interactions with Oracle.

    Shows every time a bot (ARES, ATLAS, PHOENIX, ATHENA) consulted Oracle
    with full context and reasoning.

    Args:
        days: Number of days to look back
        limit: Maximum interactions to return
        bot_name: Filter by specific bot
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get from both oracle_predictions and bot_decision_logs
        query = """
            SELECT
                'prediction' as source,
                op.id,
                op.trade_date,
                op.bot_name,
                op.prediction_time as timestamp,
                op.advice as action,
                op.win_probability,
                op.confidence,
                op.reasoning,
                op.spot_price,
                op.vix,
                op.gex_regime,
                op.gex_net,
                op.gex_call_wall,
                op.gex_put_wall,
                op.gex_flip_point,
                op.day_of_week,
                op.suggested_risk_pct,
                op.suggested_sd_multiplier,
                op.use_gex_walls,
                op.suggested_put_strike,
                op.suggested_call_strike,
                op.model_version,
                op.top_factors,
                op.claude_analysis,
                op.actual_outcome,
                op.actual_pnl,
                op.outcome_date
            FROM oracle_predictions op
            WHERE op.trade_date >= CURRENT_DATE - INTERVAL '%s days'
        """
        params = [days]

        if bot_name:
            query += " AND op.bot_name = %s"
            params.append(bot_name.upper())

        query += " ORDER BY op.prediction_time DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        interactions = [dict(row) for row in cursor.fetchall()]

        # Also get from bot_decision_logs for ORACLE entries
        try:
            cursor.execute("""
                SELECT
                    'decision_log' as source,
                    id,
                    timestamp,
                    bot_name,
                    decision_type,
                    action,
                    symbol,
                    entry_reasoning,
                    market_context,
                    claude_context,
                    passed_all_checks,
                    blocked_reason
                FROM bot_decision_logs
                WHERE bot_name = 'ORACLE'
                AND timestamp >= NOW() - INTERVAL '%s days'
                ORDER BY timestamp DESC
                LIMIT %s
            """, (days, limit))
            decision_logs = [dict(row) for row in cursor.fetchall()]
            interactions.extend(decision_logs)
        except Exception as e:
            logger.warning(f"Could not fetch bot_decision_logs: {e}")

        conn.close()

        # Parse JSON fields (same as /oracle/predictions endpoint)
        for interaction in interactions:
            # Parse top_factors - ensure it's always a dict or None
            top_factors = interaction.get('top_factors')
            if top_factors is not None:
                if isinstance(top_factors, str):
                    try:
                        parsed = json.loads(top_factors)
                        # Ensure parsed result is a dict, not None or other types
                        interaction['top_factors'] = parsed if isinstance(parsed, dict) else {}
                    except (json.JSONDecodeError, TypeError):
                        interaction['top_factors'] = {}
                elif not isinstance(top_factors, dict):
                    # Handle unexpected types
                    interaction['top_factors'] = {}

            # Parse claude_analysis - ensure it's always a dict or None
            claude_analysis = interaction.get('claude_analysis')
            if claude_analysis is not None:
                if isinstance(claude_analysis, str):
                    try:
                        parsed = json.loads(claude_analysis)
                        interaction['claude_analysis'] = parsed if isinstance(parsed, dict) else None
                    except (json.JSONDecodeError, TypeError):
                        interaction['claude_analysis'] = None
                elif not isinstance(claude_analysis, dict):
                    interaction['claude_analysis'] = None

        # Sort by timestamp
        interactions.sort(key=lambda x: x.get('timestamp') or x.get('trade_date') or '', reverse=True)

        return {
            "success": True,
            "interactions": interactions[:limit],
            "count": len(interactions[:limit]),
            "days": days
        }

    except Exception as e:
        logger.error(f"Failed to get bot interactions: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "interactions": []
        }


@router.get("/oracle/performance")
async def get_oracle_performance(days: int = 90):
    """
    Get Oracle prediction performance metrics.

    Returns:
    - Accuracy by bot
    - Win rate predictions vs actuals
    - Calibration metrics
    - Performance over time
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get predictions with outcomes
        cursor.execute("""
            SELECT
                bot_name,
                advice,
                win_probability,
                confidence,
                actual_outcome,
                actual_pnl,
                trade_date
            FROM oracle_predictions
            WHERE trade_date >= CURRENT_DATE - INTERVAL '%s days'
            AND actual_outcome IS NOT NULL
            ORDER BY trade_date
        """, (days,))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "success": True,
                "message": "No predictions with outcomes yet",
                "total_predictions": 0,
                "performance": {}
            }

        # Calculate metrics
        total = len(rows)
        wins = sum(1 for r in rows if r['actual_outcome'] in ['MAX_PROFIT', 'WIN', 'PARTIAL_WIN'])
        losses = total - wins

        # Group by bot
        by_bot = {}
        for row in rows:
            bot = row['bot_name']
            if bot not in by_bot:
                by_bot[bot] = {'total': 0, 'wins': 0, 'pnl': 0, 'predictions': []}
            by_bot[bot]['total'] += 1
            by_bot[bot]['pnl'] += row['actual_pnl'] or 0
            if row['actual_outcome'] in ['MAX_PROFIT', 'WIN', 'PARTIAL_WIN']:
                by_bot[bot]['wins'] += 1
            by_bot[bot]['predictions'].append({
                'predicted_prob': row['win_probability'],
                'actual_win': 1 if row['actual_outcome'] in ['MAX_PROFIT', 'WIN', 'PARTIAL_WIN'] else 0
            })

        # Calculate accuracy per bot
        for bot in by_bot:
            by_bot[bot]['win_rate'] = by_bot[bot]['wins'] / by_bot[bot]['total'] if by_bot[bot]['total'] > 0 else 0
            by_bot[bot]['avg_predicted_prob'] = sum(p['predicted_prob'] for p in by_bot[bot]['predictions']) / len(by_bot[bot]['predictions'])
            del by_bot[bot]['predictions']

        # Calculate calibration (predicted vs actual win rate)
        all_predicted_probs = [r['win_probability'] for r in rows]
        avg_predicted = sum(all_predicted_probs) / len(all_predicted_probs) if all_predicted_probs else 0
        actual_win_rate = wins / total if total > 0 else 0

        total_pnl = sum(r['actual_pnl'] or 0 for r in rows)

        return {
            "success": True,
            "total_predictions": total,
            "days": days,
            "overall": {
                "wins": wins,
                "losses": losses,
                "win_rate": actual_win_rate,
                "avg_predicted_win_prob": avg_predicted,
                "calibration_error": abs(avg_predicted - actual_win_rate),
                "total_pnl": total_pnl
            },
            "by_bot": by_bot
        }

    except Exception as e:
        logger.error(f"Failed to get Oracle performance: {e}")
        import traceback
        traceback.print_exc()
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


# ============================================================================
# PERFORMANCE OPTIMIZATION ENDPOINTS
# ============================================================================

@router.get("/init")
async def get_kronos_init():
    """
    Consolidated init endpoint - returns ALL startup data in a single request.

    This replaces 8+ separate API calls on page load:
    - strategies
    - strategy_types
    - tiers
    - presets
    - saved_strategies
    - oracle_status
    - health
    - results (recent)

    PERFORMANCE BENEFIT: Single request vs 8+ separate requests
    """
    try:
        init_data = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
        }

        # Health status
        orat_db_url = os.getenv('ORAT_DATABASE_URL')
        database_url = os.getenv('DATABASE_URL')
        has_db = bool(orat_db_url or database_url)

        init_data["health"] = {
            "status": "ok" if has_db else "degraded",
            "backend": "running",
            "database": "configured" if has_db else "not_configured",
        }

        # Strategies (static data)
        init_data["strategies"] = [
            {
                "id": "hybrid_fixed",
                "name": "Hybrid Fixed (Recommended)",
                "description": "Automatically scales DTE based on account size. Uses correct SD calculations for each tier.",
                "features": ["Auto-scaling tiers", "Correct SD for each DTE", "Day trades only", "Realistic transaction costs"],
                "recommended_settings": {"risk_per_trade_pct": 5.0, "sd_multiplier": 1.0, "spread_width": 10.0}
            },
            {
                "id": "aggressive",
                "name": "Aggressive (High Risk)",
                "description": "10% risk per trade with daily Iron Condors. For small accounts seeking maximum growth.",
                "features": ["10% risk per trade", "Daily Iron Condors", "Maximum compounding"],
                "recommended_settings": {"risk_per_trade_pct": 10.0, "sd_multiplier": 1.0, "spread_width": 10.0}
            },
            {
                "id": "realistic",
                "name": "Realistic (Conservative)",
                "description": "Includes full transaction costs and position limits.",
                "features": ["$0.65/leg commission", "100 contract max", "Honest returns"],
                "recommended_settings": {"risk_per_trade_pct": 10.0, "sd_multiplier": 1.0, "spread_width": 10.0}
            }
        ]

        # Strategy types (static data)
        init_data["strategy_types"] = [
            {"id": "iron_condor", "name": "Iron Condor", "legs": 4, "direction": "neutral", "credit": True},
            {"id": "bull_put", "name": "Bull Put Spread", "legs": 2, "direction": "bullish", "credit": True},
            {"id": "bear_call", "name": "Bear Call Spread", "legs": 2, "direction": "bearish", "credit": True},
            {"id": "iron_butterfly", "name": "Iron Butterfly", "legs": 4, "direction": "neutral", "credit": True},
            {"id": "gex_protected_iron_condor", "name": "GEX-Protected Iron Condor", "legs": 4, "direction": "neutral", "credit": True,
             "note": "Uses GEX walls for strike protection, falls back to SD when unavailable"},
            {"id": "bull_call", "name": "Bull Call Spread", "legs": 2, "direction": "bullish", "credit": False},
            {"id": "bear_put", "name": "Bear Put Spread", "legs": 2, "direction": "bearish", "credit": False},
            {"id": "apache_directional", "name": "APACHE GEX Directional", "legs": 2, "direction": "adaptive", "credit": False,
             "note": "Bull Call near put wall, Bear Put near call wall. Debit spreads only."},
        ]

        # Tiers (static data)
        init_data["tiers"] = [
            {"name": "TIER_1_0DTE", "equity_range": "$0 - $2M", "options_dte": "0-1 DTE", "sd_days": 1, "max_contracts": 100, "trades_per_week": 5},
            {"name": "TIER_2_WEEKLY", "equity_range": "$2M - $5M", "options_dte": "5-7 DTE", "sd_days": 7, "max_contracts": 300, "trades_per_week": 5},
            {"name": "TIER_3_MONTHLY", "equity_range": "$5M - $15M", "options_dte": "21-35 DTE", "sd_days": 30, "max_contracts": 500, "trades_per_week": 3},
            {"name": "TIER_4_LARGE", "equity_range": "$15M+", "options_dte": "30-45 DTE", "sd_days": 30, "max_contracts": 1000, "trades_per_week": 2},
        ]

        # Presets (static data)
        init_data["presets"] = STRATEGY_PRESETS

        # Saved strategies from database
        saved_strategies = []
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT * FROM zero_dte_saved_strategies
                ORDER BY CASE WHEN is_preset THEN 0 ELSE 1 END, created_at DESC
                LIMIT 50
            """)
            for row in cursor.fetchall():
                saved_strategies.append({
                    'id': row['id'],
                    'name': row['name'],
                    'description': row.get('description', ''),
                    'config': row.get('config', {}),
                    'tags': row.get('tags', []),
                    'is_preset': row.get('is_preset', False)
                })
            conn.close()
        except Exception as e:
            logger.debug(f"No saved strategies table: {e}")
        init_data["saved_strategies"] = saved_strategies

        # Recent results (limit to 5 for init)
        recent_results = []
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT id, job_id, created_at, strategy, ticker, start_date, end_date,
                       initial_capital, final_equity, total_return_pct, win_rate, total_trades
                FROM zero_dte_backtest_results
                ORDER BY created_at DESC LIMIT 5
            """)
            for row in cursor.fetchall():
                recent_results.append({
                    'id': row['id'],
                    'job_id': row['job_id'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'strategy': row['strategy'],
                    'ticker': row['ticker'],
                    'total_return_pct': float(row['total_return_pct'] or 0),
                    'win_rate': float(row['win_rate'] or 0),
                    'total_trades': row['total_trades'],
                })
            conn.close()
        except Exception as e:
            logger.debug(f"No results table: {e}")
        init_data["recent_results"] = recent_results

        # Oracle status
        oracle_status = {"claude_available": False, "model_version": "v3.0"}
        try:
            from ai.oracle_advisor import OracleAdvisor
            advisor = OracleAdvisor()
            oracle_status = {
                "claude_available": advisor.client is not None,
                "claude_model": advisor.model if advisor.client else None,
                "model_version": "v3.0"
            }
        except Exception as e:
            logger.debug(f"Oracle not available: {e}")
        init_data["oracle"] = oracle_status

        # Active jobs
        active_jobs = [
            {"job_id": jid, "status": j["status"], "progress": j["progress"]}
            for jid, j in _jobs.items()
            if j.get("status") in ("pending", "running")
        ]
        init_data["active_jobs"] = active_jobs

        return init_data

    except Exception as e:
        logger.error(f"Init failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/job/{job_id}/stream")
async def stream_job_progress(job_id: str):
    """
    Server-Sent Events (SSE) endpoint for real-time job progress.

    PERFORMANCE BENEFIT: No polling - instant updates pushed to client.

    Usage:
        const eventSource = new EventSource('/api/zero-dte/job/{job_id}/stream');
        eventSource.onmessage = (e) => { const data = JSON.parse(e.data); ... };
    """
    import asyncio

    async def event_generator():
        """Generate SSE events for job progress"""
        last_progress = -1
        retry_count = 0
        max_retries = 600  # 10 minutes max (checking every second)

        while retry_count < max_retries:
            if job_id not in _jobs:
                yield f"data: {json.dumps({'error': 'Job not found', 'status': 'not_found'})}\n\n"
                break

            job = _jobs[job_id]
            current_progress = job.get('progress', 0)

            # Only send update if progress changed or status changed
            if current_progress != last_progress or job['status'] in ('completed', 'failed'):
                event_data = {
                    'job_id': job_id,
                    'status': job['status'],
                    'progress': current_progress,
                    'progress_message': job.get('progress_message', ''),
                }

                if job['status'] == 'completed':
                    # Include summary on completion
                    result = job.get('result', {})
                    event_data['summary'] = result.get('summary', {})
                    event_data['trades'] = result.get('trades', {})
                    yield f"data: {json.dumps(event_data)}\n\n"
                    break

                elif job['status'] == 'failed':
                    event_data['error'] = job.get('error', 'Unknown error')
                    yield f"data: {json.dumps(event_data)}\n\n"
                    break

                else:
                    yield f"data: {json.dumps(event_data)}\n\n"

                last_progress = current_progress

            await asyncio.sleep(0.5)  # Check every 500ms
            retry_count += 1

        # Final message if timeout
        if retry_count >= max_retries:
            yield f"data: {json.dumps({'error': 'Timeout', 'status': 'timeout'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# ============================================================================
# NATURAL LANGUAGE BACKTESTING WITH CLAUDE
# ============================================================================

class NaturalLanguageBacktestRequest(BaseModel):
    """Request for natural language backtesting"""
    query: str = Field(..., description="Natural language description of backtest to run")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context")


@router.post("/natural-language")
async def natural_language_backtest(
    request: NaturalLanguageBacktestRequest,
    background_tasks: BackgroundTasks
):
    """
    Run a backtest using natural language description.

    Uses Claude to parse the request and generate appropriate configuration.

    Examples:
        - "Run an iron condor backtest for 2023 with 1.5 SD multiplier"
        - "Test the GEX-protected strategy from January 2022 to June 2023 with $500k starting capital"
        - "Backtest aggressive iron condors during high VIX periods (VIX > 20) in 2024"
        - "Compare conservative vs aggressive iron condors for last year"

    Returns:
        - parsed_config: The configuration parsed from natural language
        - job_id: Job ID to track progress
    """
    try:
        # Try to use Claude to parse the natural language
        parsed_config = None
        parsing_method = "claude"

        try:
            from ai.oracle_advisor import OracleAdvisor
            advisor = OracleAdvisor()

            if advisor.client:
                # Use Claude to parse natural language
                parse_prompt = f"""Parse this natural language backtest request into a JSON configuration.

User Request: "{request.query}"

Available parameters:
- start_date: YYYY-MM-DD format (default: 2022-01-01)
- end_date: YYYY-MM-DD format (default: today)
- initial_capital: number (default: 1000000)
- strategy_type: iron_condor, bull_put, bear_call, iron_butterfly, gex_protected_iron_condor, bull_call, bear_put, apache_directional
- strike_selection: sd, fixed, delta (default: sd)
- sd_multiplier: number 0.5-3.0 (default: 1.0)
- fixed_strike_distance: number 20-100 (for strike_selection=fixed)
- target_delta: number 0.05-0.50 (for strike_selection=delta)
- risk_per_trade_pct: number 1-15 (default: 5.0)
- spread_width: number 5-20 (default: 10)
- min_vix: number or null (filter: only trade when VIX >= this)
- max_vix: number or null (filter: only trade when VIX <= this)
- stop_loss_pct: number or null (exit if loss exceeds % of max loss)
- profit_target_pct: number or null (exit if profit reaches % of credit)
- trade_monday through trade_friday: boolean (which days to trade)

Return ONLY valid JSON, no markdown or explanation. Example:
{{"start_date": "2023-01-01", "end_date": "2023-12-31", "strategy_type": "iron_condor", "sd_multiplier": 1.5}}
"""
                response = advisor.client.messages.create(
                    model=advisor.model,
                    max_tokens=500,
                    messages=[{"role": "user", "content": parse_prompt}]
                )

                response_text = response.content[0].text.strip()
                # Extract JSON from response
                if response_text.startswith('{'):
                    parsed_config = json.loads(response_text)
                else:
                    # Try to find JSON in response
                    import re
                    json_match = re.search(r'\{[^{}]+\}', response_text)
                    if json_match:
                        parsed_config = json.loads(json_match.group())

        except Exception as claude_error:
            logger.warning(f"Claude parsing failed, using fallback: {claude_error}")
            parsing_method = "fallback"

        # Fallback: Simple keyword parsing
        if not parsed_config:
            parsing_method = "keyword"
            parsed_config = _parse_natural_language_fallback(request.query)

        # Build full config with defaults
        full_config = {
            "start_date": parsed_config.get("start_date", "2022-01-01"),
            "end_date": parsed_config.get("end_date", datetime.now().strftime("%Y-%m-%d")),
            "initial_capital": parsed_config.get("initial_capital", 1000000),
            "spread_width": parsed_config.get("spread_width", 10.0),
            "sd_multiplier": parsed_config.get("sd_multiplier", 1.0),
            "risk_per_trade_pct": parsed_config.get("risk_per_trade_pct", 5.0),
            "ticker": parsed_config.get("ticker", "SPX"),
            "strategy": "hybrid_fixed",
            "strategy_type": parsed_config.get("strategy_type", "iron_condor"),
            "strike_selection": parsed_config.get("strike_selection", "sd"),
            "fixed_strike_distance": parsed_config.get("fixed_strike_distance", 50),
            "target_delta": parsed_config.get("target_delta", 0.16),
            "min_vix": parsed_config.get("min_vix"),
            "max_vix": parsed_config.get("max_vix"),
            "stop_loss_pct": parsed_config.get("stop_loss_pct"),
            "profit_target_pct": parsed_config.get("profit_target_pct"),
            "trade_monday": parsed_config.get("trade_monday", True),
            "trade_tuesday": parsed_config.get("trade_tuesday", True),
            "trade_wednesday": parsed_config.get("trade_wednesday", True),
            "trade_thursday": parsed_config.get("trade_thursday", True),
            "trade_friday": parsed_config.get("trade_friday", True),
            "max_contracts_override": parsed_config.get("max_contracts_override"),
            "commission_per_leg": parsed_config.get("commission_per_leg"),
            "slippage_per_spread": parsed_config.get("slippage_per_spread"),
            "hold_days": parsed_config.get("hold_days", 1),
            "wall_proximity_pct": parsed_config.get("wall_proximity_pct", 1.0),
        }

        # Create job
        import uuid
        job_id = f"nlp_{uuid.uuid4().hex[:8]}"

        _jobs[job_id] = {
            'job_id': job_id,
            'status': 'pending',
            'progress': 0,
            'progress_message': 'Parsed natural language request, starting backtest...',
            'result': None,
            'error': None,
            'created_at': datetime.now().isoformat(),
            'completed_at': None,
            'config': full_config,
            'original_query': request.query,
            'parsing_method': parsing_method,
        }

        # Run backtest in background
        config_obj = ZeroDTEBacktestConfig(**full_config)
        background_tasks.add_task(run_hybrid_fixed_backtest, config_obj, job_id)

        return {
            "success": True,
            "job_id": job_id,
            "parsing_method": parsing_method,
            "original_query": request.query,
            "parsed_config": parsed_config,
            "full_config": full_config,
            "message": f"Backtest started using {parsing_method} parsing"
        }

    except Exception as e:
        logger.error(f"Natural language backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def _parse_natural_language_fallback(query: str) -> Dict[str, Any]:
    """
    Simple keyword-based parsing as fallback when Claude is unavailable.
    """
    import re

    config = {}
    query_lower = query.lower()

    # Parse dates
    date_patterns = [
        r'from\s+(\d{4}-\d{2}-\d{2})',
        r'since\s+(\d{4}-\d{2}-\d{2})',
        r'starting\s+(\d{4}-\d{2}-\d{2})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, query_lower)
        if match:
            config["start_date"] = match.group(1)
            break

    # End date
    end_patterns = [
        r'to\s+(\d{4}-\d{2}-\d{2})',
        r'until\s+(\d{4}-\d{2}-\d{2})',
        r'ending\s+(\d{4}-\d{2}-\d{2})',
    ]
    for pattern in end_patterns:
        match = re.search(pattern, query_lower)
        if match:
            config["end_date"] = match.group(1)
            break

    # Year shortcuts
    year_match = re.search(r'\b(202[0-5])\b', query_lower)
    if year_match and "start_date" not in config:
        year = year_match.group(1)
        config["start_date"] = f"{year}-01-01"
        config["end_date"] = f"{year}-12-31"

    # Parse capital
    capital_match = re.search(r'\$?([\d,]+)\s*(?:k|K|thousand)?', query)
    if capital_match:
        amount = float(capital_match.group(1).replace(',', ''))
        if 'k' in query_lower or 'thousand' in query_lower:
            amount *= 1000
        if amount > 100:  # Likely a capital amount
            config["initial_capital"] = amount

    # Parse SD multiplier
    sd_match = re.search(r'(\d+\.?\d*)\s*(?:sd|SD|standard deviation)', query)
    if sd_match:
        config["sd_multiplier"] = float(sd_match.group(1))

    # Parse strategy type
    if 'gex' in query_lower and 'protected' in query_lower:
        config["strategy_type"] = "gex_protected_iron_condor"
    elif 'iron condor' in query_lower or 'ic' in query_lower:
        config["strategy_type"] = "iron_condor"
    elif 'bull put' in query_lower:
        config["strategy_type"] = "bull_put"
    elif 'bear call' in query_lower:
        config["strategy_type"] = "bear_call"
    elif 'butterfly' in query_lower:
        config["strategy_type"] = "iron_butterfly"
    elif 'apache' in query_lower or 'directional' in query_lower:
        config["strategy_type"] = "apache_directional"

    # Parse VIX filters
    vix_high_match = re.search(r'vix\s*[>≥]\s*(\d+)', query_lower)
    if vix_high_match:
        config["min_vix"] = float(vix_high_match.group(1))

    vix_low_match = re.search(r'vix\s*[<≤]\s*(\d+)', query_lower)
    if vix_low_match:
        config["max_vix"] = float(vix_low_match.group(1))

    # Parse risk keywords
    if 'aggressive' in query_lower:
        config["risk_per_trade_pct"] = 8.0
        config["sd_multiplier"] = config.get("sd_multiplier", 0.8)
    elif 'conservative' in query_lower:
        config["risk_per_trade_pct"] = 3.0
        config["sd_multiplier"] = config.get("sd_multiplier", 1.5)

    return config


# ============================================================================
# ENHANCED ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/analytics/vix-regime/{job_id}")
async def get_vix_regime_analysis(job_id: str):
    """
    Get VIX regime analysis for a completed backtest.
    Breaks down performance by VIX levels.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']
    trades = result.get('all_trades', [])

    if not trades:
        return {"success": False, "error": "No trades found"}

    # Define VIX regimes
    regimes = {
        'extreme_low': {'min': 0, 'max': 12, 'label': 'Extreme Low (<12)', 'trades': [], 'color': '#22c55e'},
        'low': {'min': 12, 'max': 18, 'label': 'Low (12-18)', 'trades': [], 'color': '#84cc16'},
        'normal': {'min': 18, 'max': 25, 'label': 'Normal (18-25)', 'trades': [], 'color': '#eab308'},
        'elevated': {'min': 25, 'max': 35, 'label': 'Elevated (25-35)', 'trades': [], 'color': '#f97316'},
        'high': {'min': 35, 'max': 50, 'label': 'High (35-50)', 'trades': [], 'color': '#ef4444'},
        'extreme': {'min': 50, 'max': 1000, 'label': 'Extreme (>50)', 'trades': [], 'color': '#dc2626'},
    }

    # Categorize trades by VIX regime
    for trade in trades:
        vix = trade.get('vix', 20)
        for regime_name, regime in regimes.items():
            if regime['min'] <= vix < regime['max']:
                regime['trades'].append(trade)
                break

    # Calculate statistics per regime
    regime_stats = []
    for regime_name, regime in regimes.items():
        trades_list = regime['trades']
        if not trades_list:
            continue

        wins = [t for t in trades_list if t.get('net_pnl', 0) > 0]
        total_pnl = sum(t.get('net_pnl', 0) for t in trades_list)
        avg_pnl = total_pnl / len(trades_list) if trades_list else 0
        win_rate = (len(wins) / len(trades_list) * 100) if trades_list else 0
        avg_vix = sum(t.get('vix', 0) for t in trades_list) / len(trades_list)

        regime_stats.append({
            'regime': regime_name,
            'label': regime['label'],
            'color': regime['color'],
            'trade_count': len(trades_list),
            'win_count': len(wins),
            'loss_count': len(trades_list) - len(wins),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(avg_pnl, 2),
            'win_rate': round(win_rate, 1),
            'avg_vix': round(avg_vix, 1),
            'best_trade': round(max(t.get('net_pnl', 0) for t in trades_list), 2) if trades_list else 0,
            'worst_trade': round(min(t.get('net_pnl', 0) for t in trades_list), 2) if trades_list else 0,
        })

    # Find optimal VIX range
    best_regime = max(regime_stats, key=lambda x: x['avg_pnl']) if regime_stats else None

    return {
        "success": True,
        "job_id": job_id,
        "total_trades": len(trades),
        "regimes": regime_stats,
        "optimal_regime": best_regime['regime'] if best_regime else None,
        "recommendation": f"Best performance in {best_regime['label']} with {best_regime['win_rate']:.1f}% win rate" if best_regime else None
    }


@router.get("/analytics/day-of-week/{job_id}")
async def get_day_of_week_analysis(job_id: str):
    """
    Get day-of-week performance analysis for a completed backtest.
    Shows which days perform best.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']
    trades = result.get('all_trades', [])

    if not trades:
        return {"success": False, "error": "No trades found"}

    # Day names
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    day_colors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f97316', '#22c55e']

    # Initialize day stats
    day_stats = {i: {'trades': [], 'name': day_names[i], 'color': day_colors[i]} for i in range(5)}

    # Categorize trades by day of week
    for trade in trades:
        trade_date = trade.get('trade_date', '')
        if trade_date:
            try:
                from datetime import datetime
                dt = datetime.strptime(trade_date, '%Y-%m-%d')
                dow = dt.weekday()  # 0=Monday, 4=Friday
                if dow < 5:  # Only weekdays
                    day_stats[dow]['trades'].append(trade)
            except:
                pass

    # Calculate statistics per day
    results = []
    for dow, data in day_stats.items():
        trades_list = data['trades']
        if not trades_list:
            results.append({
                'day': dow,
                'name': data['name'],
                'color': data['color'],
                'trade_count': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'win_rate': 0,
            })
            continue

        wins = [t for t in trades_list if t.get('net_pnl', 0) > 0]
        total_pnl = sum(t.get('net_pnl', 0) for t in trades_list)
        avg_pnl = total_pnl / len(trades_list)
        win_rate = (len(wins) / len(trades_list) * 100)

        results.append({
            'day': dow,
            'name': data['name'],
            'color': data['color'],
            'trade_count': len(trades_list),
            'win_count': len(wins),
            'loss_count': len(trades_list) - len(wins),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(avg_pnl, 2),
            'win_rate': round(win_rate, 1),
            'best_trade': round(max(t.get('net_pnl', 0) for t in trades_list), 2),
            'worst_trade': round(min(t.get('net_pnl', 0) for t in trades_list), 2),
        })

    # Find best and worst days
    trading_days = [r for r in results if r['trade_count'] > 0]
    best_day = max(trading_days, key=lambda x: x['avg_pnl']) if trading_days else None
    worst_day = min(trading_days, key=lambda x: x['avg_pnl']) if trading_days else None

    return {
        "success": True,
        "job_id": job_id,
        "total_trades": len(trades),
        "days": results,
        "best_day": best_day['name'] if best_day else None,
        "worst_day": worst_day['name'] if worst_day else None,
        "recommendation": f"Best performance on {best_day['name']} ({best_day['win_rate']:.1f}% win rate, ${best_day['avg_pnl']:.2f} avg)" if best_day else None
    }


@router.get("/analytics/trade/{job_id}/{trade_number}")
async def get_trade_inspector(job_id: str, trade_number: int):
    """
    Get detailed inspection of a single trade with GEX context.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']
    trades = result.get('all_trades', [])

    # Find the trade
    trade = None
    for t in trades:
        if t.get('trade_number') == trade_number:
            trade = t
            break

    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_number} not found")

    # Calculate additional context
    entry_price = trade.get('underlying_price', trade.get('open_price', 0))
    put_short = trade.get('put_short_strike', 0)
    call_short = trade.get('call_short_strike', 0)
    gex_put_wall = trade.get('gex_put_wall')
    gex_call_wall = trade.get('gex_call_wall')

    # Calculate distances
    put_distance_pct = ((entry_price - put_short) / entry_price * 100) if entry_price and put_short else 0
    call_distance_pct = ((call_short - entry_price) / entry_price * 100) if entry_price and call_short else 0

    context = {
        'entry_price': entry_price,
        'put_short_strike': put_short,
        'call_short_strike': call_short,
        'put_distance_pct': round(put_distance_pct, 2),
        'call_distance_pct': round(call_distance_pct, 2),
        'put_strike_vs_wall': None,
        'call_strike_vs_wall': None,
    }

    if gex_put_wall:
        context['gex_put_wall'] = gex_put_wall
        context['put_strike_vs_wall'] = 'ABOVE' if put_short > gex_put_wall else 'BELOW'
        context['put_wall_cushion_pct'] = round((put_short - gex_put_wall) / entry_price * 100, 2) if entry_price else 0

    if gex_call_wall:
        context['gex_call_wall'] = gex_call_wall
        context['call_strike_vs_wall'] = 'BELOW' if call_short < gex_call_wall else 'ABOVE'
        context['call_wall_cushion_pct'] = round((gex_call_wall - call_short) / entry_price * 100, 2) if entry_price else 0

    # Outcome analysis
    outcome_analysis = {
        'outcome': trade.get('outcome', 'Unknown'),
        'net_pnl': trade.get('net_pnl', 0),
        'return_pct': trade.get('return_pct', 0),
        'put_breached': trade.get('put_breached', False),
        'call_breached': trade.get('call_breached', False),
        'intraday_put_threat': trade.get('intraday_put_threat', False),
        'intraday_call_threat': trade.get('intraday_call_threat', False),
        'exit_type': trade.get('exit_type', 'EOD'),
    }

    return {
        "success": True,
        "job_id": job_id,
        "trade_number": trade_number,
        "trade": trade,
        "context": context,
        "outcome_analysis": outcome_analysis,
        "market_conditions": {
            'vix': trade.get('vix', 0),
            'daily_range': round(trade.get('daily_high', 0) - trade.get('daily_low', 0), 2),
            'daily_change_pct': round((trade.get('close_price', 0) - trade.get('open_price', 1)) / trade.get('open_price', 1) * 100, 2) if trade.get('open_price') else 0,
            'gex_regime': trade.get('gex_regime', 'Unknown'),
        }
    }


@router.post("/analytics/monte-carlo/{job_id}")
async def run_monte_carlo_simulation(job_id: str, simulations: int = 1000, confidence_level: float = 0.95):
    """
    Run Monte Carlo simulation on backtest results.
    Shuffles trade sequence to estimate confidence intervals.
    """
    import random
    import math

    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']
    trades = result.get('all_trades', [])
    initial_capital = result.get('summary', {}).get('initial_capital', 1000000)

    if len(trades) < 10:
        return {"success": False, "error": "Need at least 10 trades for Monte Carlo simulation"}

    # Extract P&L values
    pnl_values = [t.get('net_pnl', 0) for t in trades]

    # Run simulations
    final_equities = []
    max_drawdowns = []

    for _ in range(simulations):
        # Shuffle trade order
        shuffled_pnl = random.sample(pnl_values, len(pnl_values))

        # Calculate equity curve
        equity = initial_capital
        peak = equity
        max_dd = 0

        for pnl in shuffled_pnl:
            equity += pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        final_equities.append(equity)
        max_drawdowns.append(max_dd)

    # Calculate statistics
    final_equities.sort()
    max_drawdowns.sort()

    # Percentile indices
    p5_idx = int(simulations * 0.05)
    p25_idx = int(simulations * 0.25)
    p50_idx = int(simulations * 0.50)
    p75_idx = int(simulations * 0.75)
    p95_idx = int(simulations * 0.95)

    # Calculate probability of hitting thresholds
    prob_profit = sum(1 for e in final_equities if e > initial_capital) / simulations * 100
    prob_double = sum(1 for e in final_equities if e > initial_capital * 2) / simulations * 100
    prob_loss_50 = sum(1 for e in final_equities if e < initial_capital * 0.5) / simulations * 100
    prob_dd_30 = sum(1 for dd in max_drawdowns if dd > 30) / simulations * 100
    prob_dd_50 = sum(1 for dd in max_drawdowns if dd > 50) / simulations * 100

    # Original performance
    original_final = result.get('summary', {}).get('final_equity', initial_capital)
    original_return = result.get('summary', {}).get('total_return_pct', 0)
    original_dd = result.get('summary', {}).get('max_drawdown_pct', 0)

    return {
        "success": True,
        "job_id": job_id,
        "simulations": simulations,
        "trade_count": len(trades),
        "original": {
            "final_equity": original_final,
            "return_pct": original_return,
            "max_drawdown_pct": original_dd,
        },
        "monte_carlo": {
            "final_equity": {
                "p5": round(final_equities[p5_idx], 2),
                "p25": round(final_equities[p25_idx], 2),
                "median": round(final_equities[p50_idx], 2),
                "p75": round(final_equities[p75_idx], 2),
                "p95": round(final_equities[p95_idx], 2),
                "mean": round(sum(final_equities) / simulations, 2),
            },
            "return_pct": {
                "p5": round((final_equities[p5_idx] - initial_capital) / initial_capital * 100, 2),
                "median": round((final_equities[p50_idx] - initial_capital) / initial_capital * 100, 2),
                "p95": round((final_equities[p95_idx] - initial_capital) / initial_capital * 100, 2),
            },
            "max_drawdown_pct": {
                "p5": round(max_drawdowns[p5_idx], 2),
                "median": round(max_drawdowns[p50_idx], 2),
                "p95": round(max_drawdowns[p95_idx], 2),
                "max": round(max(max_drawdowns), 2),
            },
        },
        "probabilities": {
            "profit": round(prob_profit, 1),
            "double_money": round(prob_double, 1),
            "lose_50_pct": round(prob_loss_50, 1),
            "drawdown_over_30": round(prob_dd_30, 1),
            "drawdown_over_50": round(prob_dd_50, 1),
        },
        "confidence_interval": {
            "level": confidence_level,
            "return_range": [
                round((final_equities[p5_idx] - initial_capital) / initial_capital * 100, 2),
                round((final_equities[p95_idx] - initial_capital) / initial_capital * 100, 2)
            ],
        },
        "verdict": "ROBUST" if prob_profit > 80 and prob_dd_50 < 10 else "MODERATE" if prob_profit > 60 else "RISKY"
    }


@router.get("/analytics/monthly/{job_id}")
async def get_monthly_analysis(job_id: str):
    """
    Get month-by-month performance breakdown.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']
    trades = result.get('all_trades', [])

    if not trades:
        return {"success": False, "error": "No trades found"}

    # Group trades by month
    from collections import defaultdict
    monthly_data = defaultdict(list)

    for trade in trades:
        trade_date = trade.get('trade_date', '')
        if trade_date:
            month_key = trade_date[:7]  # YYYY-MM
            monthly_data[month_key].append(trade)

    # Calculate monthly stats
    monthly_stats = []
    for month, month_trades in sorted(monthly_data.items()):
        wins = [t for t in month_trades if t.get('net_pnl', 0) > 0]
        total_pnl = sum(t.get('net_pnl', 0) for t in month_trades)
        win_rate = (len(wins) / len(month_trades) * 100) if month_trades else 0

        monthly_stats.append({
            'month': month,
            'trade_count': len(month_trades),
            'win_count': len(wins),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(total_pnl / len(month_trades), 2) if month_trades else 0,
            'win_rate': round(win_rate, 1),
            'is_profitable': total_pnl > 0,
        })

    # Summary stats
    profitable_months = sum(1 for m in monthly_stats if m['is_profitable'])
    best_month = max(monthly_stats, key=lambda x: x['total_pnl']) if monthly_stats else None
    worst_month = min(monthly_stats, key=lambda x: x['total_pnl']) if monthly_stats else None

    return {
        "success": True,
        "job_id": job_id,
        "total_months": len(monthly_stats),
        "profitable_months": profitable_months,
        "monthly_win_rate": round(profitable_months / len(monthly_stats) * 100, 1) if monthly_stats else 0,
        "months": monthly_stats,
        "best_month": best_month,
        "worst_month": worst_month,
    }


@router.get("/analytics/streaks/{job_id}")
async def get_streak_analysis(job_id: str):
    """
    Analyze winning and losing streaks.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    result = job['result']
    trades = result.get('all_trades', [])

    if not trades:
        return {"success": False, "error": "No trades found"}

    # Sort trades by date
    sorted_trades = sorted(trades, key=lambda x: x.get('trade_date', ''))

    # Analyze streaks
    current_win_streak = 0
    current_loss_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    win_streaks = []
    loss_streaks = []

    for trade in sorted_trades:
        pnl = trade.get('net_pnl', 0)
        if pnl > 0:
            current_win_streak += 1
            if current_loss_streak > 0:
                loss_streaks.append(current_loss_streak)
                current_loss_streak = 0
            max_win_streak = max(max_win_streak, current_win_streak)
        else:
            current_loss_streak += 1
            if current_win_streak > 0:
                win_streaks.append(current_win_streak)
                current_win_streak = 0
            max_loss_streak = max(max_loss_streak, current_loss_streak)

    # Don't forget the last streak
    if current_win_streak > 0:
        win_streaks.append(current_win_streak)
    if current_loss_streak > 0:
        loss_streaks.append(current_loss_streak)

    # Calculate streak distributions
    win_streak_dist = {}
    for s in win_streaks:
        win_streak_dist[s] = win_streak_dist.get(s, 0) + 1

    loss_streak_dist = {}
    for s in loss_streaks:
        loss_streak_dist[s] = loss_streak_dist.get(s, 0) + 1

    return {
        "success": True,
        "job_id": job_id,
        "total_trades": len(trades),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "avg_win_streak": round(sum(win_streaks) / len(win_streaks), 1) if win_streaks else 0,
        "avg_loss_streak": round(sum(loss_streaks) / len(loss_streaks), 1) if loss_streaks else 0,
        "win_streak_distribution": dict(sorted(win_streak_dist.items())),
        "loss_streak_distribution": dict(sorted(loss_streak_dist.items())),
        "current_streak": {
            "type": "WIN" if current_win_streak > current_loss_streak else "LOSS",
            "count": max(current_win_streak, current_loss_streak)
        }
    }


@router.get("/analytics/comprehensive/{job_id}")
async def get_comprehensive_analytics(job_id: str):
    """
    Get all analytics for a backtest in one call.
    Combines VIX regime, day-of-week, monthly, and streak analysis.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job['status'] != 'completed' or not job.get('result'):
        raise HTTPException(status_code=400, detail="Backtest not completed")

    # Get all analytics
    vix_analysis = await get_vix_regime_analysis(job_id)
    dow_analysis = await get_day_of_week_analysis(job_id)
    monthly_analysis = await get_monthly_analysis(job_id)
    streak_analysis = await get_streak_analysis(job_id)

    # Monte Carlo (quick version with fewer simulations)
    mc_analysis = await run_monte_carlo_simulation(job_id, simulations=500)

    result = job['result']

    return {
        "success": True,
        "job_id": job_id,
        "summary": result.get('summary', {}),
        "trades_summary": result.get('trades', {}),
        "risk_metrics": result.get('risk_metrics', {}),
        "analytics": {
            "vix_regime": vix_analysis if vix_analysis.get('success') else None,
            "day_of_week": dow_analysis if dow_analysis.get('success') else None,
            "monthly": monthly_analysis if monthly_analysis.get('success') else None,
            "streaks": streak_analysis if streak_analysis.get('success') else None,
            "monte_carlo": mc_analysis if mc_analysis.get('success') else None,
        },
        "recommendations": _generate_recommendations(vix_analysis, dow_analysis, monthly_analysis, mc_analysis)
    }


def _generate_recommendations(vix_analysis, dow_analysis, monthly_analysis, mc_analysis):
    """Generate actionable recommendations based on analytics."""
    recommendations = []

    if vix_analysis and vix_analysis.get('success'):
        optimal = vix_analysis.get('optimal_regime')
        if optimal:
            recommendations.append({
                "type": "VIX_FILTER",
                "priority": "HIGH",
                "message": vix_analysis.get('recommendation', ''),
                "action": f"Consider adding VIX filter for {optimal} regime"
            })

    if dow_analysis and dow_analysis.get('success'):
        best = dow_analysis.get('best_day')
        worst = dow_analysis.get('worst_day')
        if best and worst and best != worst:
            recommendations.append({
                "type": "DAY_FILTER",
                "priority": "MEDIUM",
                "message": f"Best on {best}, worst on {worst}",
                "action": f"Consider trading only on {best} or avoiding {worst}"
            })

    if mc_analysis and mc_analysis.get('success'):
        verdict = mc_analysis.get('verdict', 'UNKNOWN')
        prob_profit = mc_analysis.get('probabilities', {}).get('profit', 0)
        if verdict == 'RISKY':
            recommendations.append({
                "type": "RISK_WARNING",
                "priority": "HIGH",
                "message": f"Monte Carlo shows only {prob_profit}% probability of profit",
                "action": "Consider reducing position size or adjusting strategy parameters"
            })
        elif verdict == 'ROBUST':
            recommendations.append({
                "type": "CONFIDENCE",
                "priority": "LOW",
                "message": f"Strategy shows {prob_profit}% probability of profit across simulations",
                "action": "Strategy appears robust to trade sequence randomization"
            })

    if monthly_analysis and monthly_analysis.get('success'):
        monthly_wr = monthly_analysis.get('monthly_win_rate', 0)
        if monthly_wr < 50:
            recommendations.append({
                "type": "CONSISTENCY",
                "priority": "MEDIUM",
                "message": f"Only {monthly_wr}% of months are profitable",
                "action": "Strategy may have inconsistent monthly returns"
            })

    return recommendations
