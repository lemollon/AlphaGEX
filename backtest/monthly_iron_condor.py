#!/usr/bin/env python3
"""
Monthly Iron Condor Backtester for SPX & SPY

Backtests monthly Iron Condor strategies using ORAT EOD options data from the
AlphaGEX PostgreSQL database. Supports both delta-based and percentage-OTM
strike selection with configurable exit rules.

Usage:
    # Phase 1: Data audit
    python backtest/monthly_iron_condor.py --audit

    # Phase 2: Run backtest
    python backtest/monthly_iron_condor.py --ticker SPX --start 2021-01-01 --end 2025-12-31

    # With custom parameters
    python backtest/monthly_iron_condor.py --ticker SPY --delta 0.10 --width 5 --profit-target 50 --stop-loss 200

    # Export results
    python backtest/monthly_iron_condor.py --ticker SPX --export
"""

import os
import sys
import csv
import math
import json
import argparse
import logging
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

import psycopg2
import psycopg2.extras
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MonthlyICConfig:
    """All configurable parameters for the monthly Iron Condor backtest.

    No magic numbers — every tunable lives here.
    """

    # ── Underlying ────────────────────────────────────────────────────────
    ticker: str = "SPX"

    # ── Date range ────────────────────────────────────────────────────────
    start_date: str = "2021-01-01"
    end_date: str = "2025-12-31"

    # ── Entry rules ───────────────────────────────────────────────────────
    target_dte_min: int = 30          # Minimum DTE at entry
    target_dte_max: int = 45          # Maximum DTE at entry
    target_dte_ideal: int = 35        # Preferred DTE (closest wins)

    # ── Strike selection ──────────────────────────────────────────────────
    # Primary: delta-based (if delta data available in orat_options_eod)
    short_delta: float = 0.10         # Target |delta| for short strikes (~10-delta)

    # Fallback: percentage OTM from spot
    pct_otm: float = 5.0             # Percent OTM for short strikes (fallback)

    # Wing width
    wing_width_spx: float = 25.0     # Wing width for SPX ($25)
    wing_width_spy: float = 5.0      # Wing width for SPY ($5)

    # ── Exit rules (first trigger wins) ───────────────────────────────────
    profit_target_pct: float = 50.0   # Close at X% of max credit (50% = half credit)
    stop_loss_pct: float = 200.0      # Close at X% of max credit (200% = 2x credit)
    dte_exit: int = 5                 # Close at X DTE regardless of P&L
    hold_to_expiration: bool = False  # If True, ignore profit/stop and hold to exp

    # ── Position sizing ───────────────────────────────────────────────────
    contracts: int = 1                # Fixed lot size (ignored if dynamic_sizing=True)
    initial_capital: float = 100_000  # Starting capital (for return calculations)

    # ── Collateral / Capital Management ───────────────────────────────────
    max_capital_utilization: float = 80.0   # Max % of equity deployable as margin
    max_concurrent_positions: int = 2       # Max simultaneous open positions (0 = unlimited)
    dynamic_sizing: bool = True             # Size contracts based on available buying power
    max_risk_per_trade_pct: float = 25.0    # Max % of equity at risk in any single trade

    # ── Transaction costs ─────────────────────────────────────────────────
    commission_per_contract: float = 1.30  # Per contract per leg (round-trip)
    slippage_per_contract: float = 0.05    # Per spread in dollars (bid-ask cost)

    # ── Filters ───────────────────────────────────────────────────────────
    min_credit: float = 0.50          # Minimum total IC credit to enter ($)
    max_vix: float = 25.0             # Skip entry if VIX above this
    min_vix: float = 13.0             # Skip entry if VIX below this (premium too thin)
    vix_tighten_sl_above: float = 25.0  # Tighter SL for existing positions when VIX > this
    vix_tighten_sl_pct: float = 150.0   # Tighter SL % when VIX is elevated
    skip_fomc_week: bool = False      # Skip entries during FOMC week (not implemented)

    # ── Stop-loss gap handling ────────────────────────────────────────────
    sl_gap_cap: bool = True           # Cap SL exit debit at intended level + gap slippage
    sl_gap_slippage_pct: float = 10.0 # Extra % beyond SL allowed for gap (10% → 220% on 200% SL)

    # ── DTE mode ──────────────────────────────────────────────────────────
    dte_mode: str = "monthly"         # "monthly" (30-45 DTE), "short" (0-3 DTE), or "weekly" (5-7 DTE)
    short_dte_target: int = 0         # For short mode: 0, 1, 2, or 3 DTE
    weekly_dte_min: int = 5           # For weekly mode: minimum DTE at entry
    weekly_dte_max: int = 7           # For weekly mode: maximum DTE at entry
    day_trade: bool = True            # Day trade: close all positions on entry day using Yahoo OHLC

    @property
    def wing_width(self) -> float:
        """Return wing width based on ticker."""
        if self.ticker.upper() in ("SPX", "SPXW", "^SPX"):
            return self.wing_width_spx
        return self.wing_width_spy

    @property
    def strike_interval(self) -> float:
        """Return strike rounding interval based on ticker."""
        if self.ticker.upper() in ("SPX", "SPXW", "^SPX"):
            return 5.0  # SPX uses $5 intervals
        return 1.0  # SPY uses $1 intervals


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ICTrade:
    """A single monthly Iron Condor trade with full audit trail."""

    trade_id: int = 0

    # ── Entry ─────────────────────────────────────────────────────────────
    entry_date: str = ""
    expiration_date: str = ""
    dte_at_entry: int = 0
    underlying_at_entry: float = 0.0
    vix_at_entry: float = 0.0

    # ── Put spread (bull put) ─────────────────────────────────────────────
    put_short_strike: float = 0.0
    put_long_strike: float = 0.0
    put_credit: float = 0.0           # Per-contract credit received
    put_short_delta: float = 0.0
    put_short_iv: float = 0.0

    # ── Call spread (bear call) ───────────────────────────────────────────
    call_short_strike: float = 0.0
    call_long_strike: float = 0.0
    call_credit: float = 0.0
    call_short_delta: float = 0.0
    call_short_iv: float = 0.0

    # ── Combined ──────────────────────────────────────────────────────────
    total_credit: float = 0.0         # put_credit + call_credit
    max_profit: float = 0.0           # total_credit * 100 * contracts
    max_loss: float = 0.0             # (wing_width - total_credit) * 100 * contracts
    wing_width: float = 0.0
    contracts: int = 1
    margin_required: float = 0.0
    strike_selection_method: str = ""  # "delta" or "pct_otm"

    # ── Exit ──────────────────────────────────────────────────────────────
    exit_date: str = ""
    exit_reason: str = ""             # PROFIT_TARGET, STOP_LOSS, DTE_EXIT, EXPIRATION
    dte_at_exit: int = 0
    underlying_at_exit: float = 0.0
    exit_debit: float = 0.0           # Cost to close (per contract)

    # ── P&L ───────────────────────────────────────────────────────────────
    gross_pnl: float = 0.0           # (credit - debit) * 100 * contracts
    commissions: float = 0.0
    slippage_cost: float = 0.0
    net_pnl: float = 0.0             # gross_pnl - commissions - slippage
    return_on_risk: float = 0.0      # net_pnl / max_loss * 100

    # ── Duration ──────────────────────────────────────────────────────────
    days_held: int = 0


@dataclass
class DailySnapshot:
    """Daily equity snapshot for equity curve."""
    date: str
    equity: float
    daily_pnl: float
    cumulative_pnl: float
    open_positions: int
    high_water_mark: float
    drawdown_pct: float


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE LAYER
# ═══════════════════════════════════════════════════════════════════════════════

class BacktestDB:
    """Database access layer for the monthly IC backtester.

    Uses two databases (matching CHRONICLES pattern):
      - ORAT_DATABASE_URL → orat_options_eod (options chain data)
      - DATABASE_URL      → gex_structure_daily, market_data_daily (GEX/price)

    On Render both env vars are pre-set. Locally, put them in .env.
    """

    # Default database URLs — no env var setup needed
    DEFAULT_ORAT_URL = "postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest"
    DEFAULT_MAIN_URL = "postgresql://alphagex_user:ia5KWqhz4wfwsjiQxlPEGMfgftYT6Du1@dpg-d4132pje5dus738rkoug-a.oregon-postgres.render.com/alphagex"

    def __init__(self):
        self.orat_url = os.getenv("ORAT_DATABASE_URL") or self.DEFAULT_ORAT_URL
        self.main_url = os.getenv("DATABASE_URL") or self.DEFAULT_MAIN_URL
        self._orat_conn = None
        self._main_conn = None
        self._main_conn_rw = None

    def get_orat_conn(self):
        """Return a persistent read-only connection to the ORAT options database."""
        if self._orat_conn is None or self._orat_conn.closed:
            self._orat_conn = psycopg2.connect(self.orat_url, connect_timeout=30)
            self._orat_conn.set_session(readonly=True, autocommit=True)
        return self._orat_conn

    def get_main_conn(self):
        """Return a persistent read-only connection to the main AlphaGEX database."""
        if self._main_conn is None or self._main_conn.closed:
            self._main_conn = psycopg2.connect(self.main_url, connect_timeout=30)
            self._main_conn.set_session(readonly=True, autocommit=True)
        return self._main_conn

    def get_main_conn_rw(self):
        """Return a writable connection to the main AlphaGEX database (for saving results)."""
        if self._main_conn_rw is None or self._main_conn_rw.closed:
            self._main_conn_rw = psycopg2.connect(self.main_url, connect_timeout=30)
            self._main_conn_rw.autocommit = False
        return self._main_conn_rw

    def get_conn(self):
        """Return main DB connection (backward compat for audit)."""
        return self.get_main_conn()

    def close(self):
        """Close persistent connections."""
        for conn in (self._orat_conn, self._main_conn, self._main_conn_rw):
            if conn and not conn.closed:
                conn.close()
        self._orat_conn = None
        self._main_conn = None
        self._main_conn_rw = None

    # ── Results persistence ────────────────────────────────────────────────

    def _ensure_results_tables(self):
        """Create backtest results tables if they don't exist."""
        conn = self.get_main_conn_rw()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ic_backtest_runs (
                    run_id          SERIAL PRIMARY KEY,
                    run_key         TEXT UNIQUE NOT NULL,
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    ticker          TEXT NOT NULL,
                    dte_mode        TEXT NOT NULL,
                    short_dte       INT,
                    start_date      TEXT NOT NULL,
                    end_date        TEXT NOT NULL,
                    initial_capital FLOAT NOT NULL,
                    max_utilization FLOAT NOT NULL,
                    max_risk_per_trade FLOAT NOT NULL,
                    config_json     JSONB NOT NULL,
                    summary_json    JSONB NOT NULL,
                    risk_json       JSONB NOT NULL,
                    collateral_json JSONB NOT NULL,
                    exit_reasons    JSONB,
                    monthly_returns JSONB,
                    annual_returns  JSONB,
                    streaks_json    JSONB
                );

                CREATE TABLE IF NOT EXISTS ic_backtest_trades (
                    id              SERIAL PRIMARY KEY,
                    run_id          INT NOT NULL REFERENCES ic_backtest_runs(run_id) ON DELETE CASCADE,
                    trade_id        INT NOT NULL,
                    entry_date      TEXT,
                    expiration_date TEXT,
                    dte_at_entry    INT,
                    underlying_at_entry  FLOAT,
                    vix_at_entry    FLOAT,
                    put_short_strike     FLOAT,
                    put_long_strike      FLOAT,
                    put_credit           FLOAT,
                    put_short_delta      FLOAT,
                    put_short_iv         FLOAT,
                    call_short_strike    FLOAT,
                    call_long_strike     FLOAT,
                    call_credit          FLOAT,
                    call_short_delta     FLOAT,
                    call_short_iv        FLOAT,
                    total_credit    FLOAT,
                    max_profit      FLOAT,
                    max_loss        FLOAT,
                    wing_width      FLOAT,
                    contracts       INT,
                    margin_required FLOAT,
                    strike_selection_method TEXT,
                    exit_date       TEXT,
                    exit_reason     TEXT,
                    dte_at_exit     INT,
                    underlying_at_exit FLOAT,
                    exit_debit      FLOAT,
                    gross_pnl       FLOAT,
                    commissions     FLOAT,
                    slippage_cost   FLOAT,
                    net_pnl         FLOAT,
                    return_on_risk  FLOAT,
                    days_held       INT
                );

                CREATE TABLE IF NOT EXISTS ic_backtest_equity_curve (
                    id              SERIAL PRIMARY KEY,
                    run_id          INT NOT NULL REFERENCES ic_backtest_runs(run_id) ON DELETE CASCADE,
                    date            TEXT NOT NULL,
                    trade_num       INT,
                    equity          FLOAT,
                    pnl             FLOAT,
                    cumulative_pnl  FLOAT,
                    return_pct      FLOAT,
                    drawdown_pct    FLOAT,
                    exit_reason     TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_ic_bt_trades_run ON ic_backtest_trades(run_id);
                CREATE INDEX IF NOT EXISTS idx_ic_bt_equity_run ON ic_backtest_equity_curve(run_id);
                CREATE INDEX IF NOT EXISTS idx_ic_bt_runs_key ON ic_backtest_runs(run_key);
            """)
        conn.commit()

    def save_results(self, config: 'MonthlyICConfig', results: Dict,
                     trades: List['ICTrade']):
        """Save a complete backtest run (summary + trades + equity curve) to PostgreSQL."""
        self._ensure_results_tables()

        # Build a unique key for this run so re-runs overwrite
        dte_label = config.dte_mode
        if config.dte_mode == "short":
            dte_label = f"{config.short_dte_target}dte"
        elif config.dte_mode == "weekly":
            dte_label = "weekly"

        run_key = (f"{config.ticker}_{dte_label}_"
                   f"{int(config.initial_capital)}_{int(config.max_capital_utilization)}_"
                   f"{int(config.max_risk_per_trade_pct)}_"
                   f"{config.start_date}_{config.end_date}")

        conn = self.get_main_conn_rw()
        with conn.cursor() as cur:
            # Delete any previous run with same key (re-run overwrites)
            cur.execute("DELETE FROM ic_backtest_runs WHERE run_key = %s", (run_key,))

            # Insert run summary
            cur.execute("""
                INSERT INTO ic_backtest_runs (
                    run_key, ticker, dte_mode, short_dte,
                    start_date, end_date, initial_capital,
                    max_utilization, max_risk_per_trade,
                    config_json, summary_json, risk_json, collateral_json,
                    exit_reasons, monthly_returns, annual_returns, streaks_json
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                ) RETURNING run_id
            """, (
                run_key, config.ticker, config.dte_mode,
                config.short_dte_target if config.dte_mode == "short" else None,
                config.start_date, config.end_date, config.initial_capital,
                config.max_capital_utilization, config.max_risk_per_trade_pct,
                json.dumps(results.get('config', {}), default=str),
                json.dumps(results.get('summary', {}), default=str),
                json.dumps(results.get('risk', {}), default=str),
                json.dumps(results.get('collateral', {}), default=str),
                json.dumps(results.get('exit_reasons', {}), default=str),
                json.dumps(results.get('monthly_returns', {}), default=str),
                json.dumps(results.get('annual_returns', {}), default=str),
                json.dumps(results.get('streaks', {}), default=str),
            ))
            run_id = cur.fetchone()[0]

            # Bulk insert trades
            if trades:
                trade_values = []
                for t in trades:
                    d = asdict(t) if hasattr(t, '__dataclass_fields__') else t
                    trade_values.append((
                        run_id, d.get('trade_id', 0),
                        d.get('entry_date', ''), d.get('expiration_date', ''),
                        d.get('dte_at_entry', 0), d.get('underlying_at_entry', 0),
                        d.get('vix_at_entry', 0),
                        d.get('put_short_strike', 0), d.get('put_long_strike', 0),
                        d.get('put_credit', 0), d.get('put_short_delta', 0),
                        d.get('put_short_iv', 0),
                        d.get('call_short_strike', 0), d.get('call_long_strike', 0),
                        d.get('call_credit', 0), d.get('call_short_delta', 0),
                        d.get('call_short_iv', 0),
                        d.get('total_credit', 0), d.get('max_profit', 0),
                        d.get('max_loss', 0), d.get('wing_width', 0),
                        d.get('contracts', 1), d.get('margin_required', 0),
                        d.get('strike_selection_method', ''),
                        d.get('exit_date', ''), d.get('exit_reason', ''),
                        d.get('dte_at_exit', 0), d.get('underlying_at_exit', 0),
                        d.get('exit_debit', 0),
                        d.get('gross_pnl', 0), d.get('commissions', 0),
                        d.get('slippage_cost', 0), d.get('net_pnl', 0),
                        d.get('return_on_risk', 0), d.get('days_held', 0),
                    ))
                psycopg2.extras.execute_batch(cur, """
                    INSERT INTO ic_backtest_trades (
                        run_id, trade_id, entry_date, expiration_date,
                        dte_at_entry, underlying_at_entry, vix_at_entry,
                        put_short_strike, put_long_strike, put_credit,
                        put_short_delta, put_short_iv,
                        call_short_strike, call_long_strike, call_credit,
                        call_short_delta, call_short_iv,
                        total_credit, max_profit, max_loss, wing_width,
                        contracts, margin_required, strike_selection_method,
                        exit_date, exit_reason, dte_at_exit,
                        underlying_at_exit, exit_debit,
                        gross_pnl, commissions, slippage_cost, net_pnl,
                        return_on_risk, days_held
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                """, trade_values, page_size=100)

            # Bulk insert equity curve
            eq_curve = results.get('equity_curve', [])
            if eq_curve:
                eq_values = [(
                    run_id, pt.get('date', ''), pt.get('trade_num', 0),
                    pt.get('equity', 0), pt.get('pnl', 0),
                    pt.get('cumulative_pnl', 0), pt.get('return_pct', 0),
                    pt.get('drawdown_pct', 0), pt.get('exit_reason', ''),
                ) for pt in eq_curve]
                psycopg2.extras.execute_batch(cur, """
                    INSERT INTO ic_backtest_equity_curve (
                        run_id, date, trade_num, equity, pnl,
                        cumulative_pnl, return_pct, drawdown_pct, exit_reason
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, eq_values, page_size=200)

        conn.commit()
        logger.info(f"Saved run {run_key} to database: run_id={run_id}, "
                     f"{len(trades)} trades, {len(eq_curve)} equity points")
        return run_id

    # ── Schema discovery (Phase 1) ────────────────────────────────────────

    def audit_tables(self) -> List[Dict]:
        """List all tables with row counts (main DB)."""
        conn = self.get_main_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT schemaname, relname AS table_name, n_live_tup AS row_count
                FROM pg_stat_user_tables
                ORDER BY n_live_tup DESC;
            """)
            rows = [dict(r) for r in cur.fetchall()]
        return rows

    def audit_columns(self, table_name: str, use_orat: bool = False) -> List[Dict]:
        """Get columns for a table."""
        conn = self.get_orat_conn() if use_orat else self.get_main_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (table_name,))
            rows = [dict(r) for r in cur.fetchall()]
        return rows

    def audit_orat_data(self) -> Dict:
        """Audit the orat_options_eod table specifically (from ORAT database)."""
        conn = self.get_orat_conn()
        result = {}
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Date range
            cur.execute("""
                SELECT MIN(trade_date) AS min_date,
                       MAX(trade_date) AS max_date,
                       COUNT(*) AS total_rows,
                       COUNT(DISTINCT trade_date) AS distinct_days,
                       COUNT(DISTINCT ticker) AS distinct_tickers
                FROM orat_options_eod;
            """)
            result['summary'] = dict(cur.fetchone())

            # Tickers
            cur.execute("""
                SELECT ticker, COUNT(*) AS rows,
                       MIN(trade_date) AS min_date, MAX(trade_date) AS max_date,
                       COUNT(DISTINCT trade_date) AS days
                FROM orat_options_eod
                GROUP BY ticker ORDER BY rows DESC;
            """)
            result['tickers'] = [dict(r) for r in cur.fetchall()]

            # DTE distribution
            cur.execute("""
                SELECT dte, COUNT(*) AS rows
                FROM orat_options_eod
                WHERE ticker IN ('SPX', 'SPXW', 'SPY')
                GROUP BY dte ORDER BY dte;
            """)
            result['dte_distribution'] = [dict(r) for r in cur.fetchall()]

            # Delta availability
            cur.execute("""
                SELECT
                    COUNT(*) AS total_rows,
                    COUNT(delta) AS rows_with_delta,
                    COUNT(put_iv) AS rows_with_put_iv,
                    COUNT(call_iv) AS rows_with_call_iv,
                    COUNT(put_bid) AS rows_with_put_bid,
                    COUNT(call_bid) AS rows_with_call_bid
                FROM orat_options_eod
                WHERE ticker IN ('SPX', 'SPXW', 'SPY');
            """)
            result['data_completeness'] = dict(cur.fetchone())

            # Monthly expiration check: are there options with DTE 30-45?
            cur.execute("""
                SELECT COUNT(DISTINCT trade_date) AS days_with_monthly_dte
                FROM orat_options_eod
                WHERE ticker IN ('SPX', 'SPXW')
                  AND dte BETWEEN 30 AND 45;
            """)
            result['monthly_dte_days'] = dict(cur.fetchone())

            # Sample 10 rows
            cur.execute("""
                SELECT trade_date, ticker, expiration_date, strike, underlying_price,
                       put_bid, put_ask, put_mid, call_bid, call_ask, call_mid,
                       delta, put_iv, call_iv, dte
                FROM orat_options_eod
                WHERE ticker IN ('SPX', 'SPXW') AND dte BETWEEN 30 AND 45
                ORDER BY trade_date DESC, strike
                LIMIT 10;
            """)
            result['sample_monthly'] = [dict(r) for r in cur.fetchall()]

        return result

    def audit_gex_data(self) -> Dict:
        """Audit GEX-related tables (main DB)."""
        conn = self.get_main_conn()
        result = {}
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for table in ('gex_structure_daily', 'gex_history'):
                try:
                    cur.execute(f"""
                        SELECT MIN(trade_date) AS min_date, MAX(trade_date) AS max_date,
                               COUNT(*) AS rows, COUNT(DISTINCT trade_date) AS days
                        FROM {table}
                        WHERE symbol IN ('SPX', 'SPY', 'SPXW');
                    """)
                    result[table] = dict(cur.fetchone())
                except Exception:
                    conn.rollback()
                    result[table] = "TABLE NOT FOUND"
        return result

    def audit_price_data(self) -> Dict:
        """Check for underlying price data in various tables."""
        conn = self.get_main_conn()
        result = {}
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check gex_structure_daily for OHLC
            try:
                cur.execute("""
                    SELECT MIN(trade_date) AS min_date, MAX(trade_date) AS max_date,
                           COUNT(*) AS rows,
                           COUNT(spot_open) AS has_open,
                           COUNT(spot_close) AS has_close
                    FROM gex_structure_daily
                    WHERE symbol IN ('SPX', 'SPY');
                """)
                result['gex_structure_daily'] = dict(cur.fetchone())
            except Exception:
                conn.rollback()
                result['gex_structure_daily'] = "NOT AVAILABLE"

        # Check orat DB for underlying_price
        try:
            orat_conn = self.get_orat_conn()
            with orat_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur2:
                cur2.execute("""
                    SELECT MIN(trade_date) AS min_date, MAX(trade_date) AS max_date,
                           COUNT(DISTINCT trade_date) AS days,
                           COUNT(underlying_price) AS has_price
                    FROM orat_options_eod
                    WHERE ticker IN ('SPX', 'SPXW', 'SPY')
                      AND underlying_price IS NOT NULL;
                """)
                result['orat_underlying'] = dict(cur2.fetchone())
        except Exception as e:
            result['orat_underlying'] = f"NOT AVAILABLE ({e})"

        return result

    # ── Backtest data queries ─────────────────────────────────────────────

    def get_monthly_expirations(self, ticker: str, start_date: str, end_date: str) -> List[Dict]:
        """Find distinct expiration dates with DTE in the monthly range.

        Returns list of {trade_date, expiration_date, dte} grouped by
        expiration, with the earliest trade_date per expiration that falls
        within the target DTE window.
        """
        conn = self.get_orat_conn()
        # We also accept SPXW for SPX weeklies (which include monthly-like expirations)
        tickers = [ticker]
        if ticker.upper() == "SPX":
            tickers = ["SPX", "SPXW"]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT expiration_date
                FROM orat_options_eod
                WHERE ticker = ANY(%s)
                  AND trade_date >= %s
                  AND trade_date <= %s
                  AND dte BETWEEN 25 AND 50
                ORDER BY expiration_date;
            """, (tickers, start_date, end_date))
            expirations = [dict(r) for r in cur.fetchall()]
        return expirations

    def get_short_dte_entries(
        self, ticker: str, start_date: str, end_date: str, target_dte: int
    ) -> List[Dict]:
        """Find all (trade_date, expiration_date) pairs for short-DTE IC trading.

        For 0DTE: trade_date == expiration_date
        For 1DTE: expiration_date = trade_date + 1 trading day
        For 2DTE/3DTE: similar pattern

        Returns list of {trade_date, expiration_date, dte}.
        """
        conn = self.get_orat_conn()
        tickers = [ticker]
        if ticker.upper() == "SPX":
            tickers = ["SPX", "SPXW"]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT trade_date, expiration_date, dte
                FROM orat_options_eod
                WHERE ticker = ANY(%s)
                  AND trade_date >= %s
                  AND trade_date <= %s
                  AND dte = %s
                ORDER BY trade_date;
            """, (tickers, start_date, end_date, target_dte))
            rows = [dict(r) for r in cur.fetchall()]

        # Deduplicate: one entry per trade_date (pick the first expiration if multiple)
        seen_dates = set()
        unique = []
        for r in rows:
            td = r['trade_date'].strftime('%Y-%m-%d') if isinstance(r['trade_date'], date) else str(r['trade_date'])
            if td not in seen_dates:
                seen_dates.add(td)
                unique.append(r)
        return unique

    def get_weekly_dte_entries(
        self, ticker: str, start_date: str, end_date: str,
        dte_min: int, dte_max: int
    ) -> List[Dict]:
        """Find all (trade_date, expiration_date) pairs for weekly IC trading.

        Queries expirations where DTE is between dte_min and dte_max (e.g., 5-7).
        For each trade_date, picks the expiration closest to the midpoint of the range.

        Returns list of {trade_date, expiration_date, dte}.
        """
        conn = self.get_orat_conn()
        tickers = [ticker]
        if ticker.upper() == "SPX":
            tickers = ["SPX", "SPXW"]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT trade_date, expiration_date, dte
                FROM orat_options_eod
                WHERE ticker = ANY(%s)
                  AND trade_date >= %s
                  AND trade_date <= %s
                  AND dte BETWEEN %s AND %s
                ORDER BY trade_date, dte;
            """, (tickers, start_date, end_date, dte_min, dte_max))
            rows = [dict(r) for r in cur.fetchall()]

        # Deduplicate: one entry per trade_date, pick expiration closest to midpoint DTE
        target_dte = (dte_min + dte_max) // 2
        best_by_date = {}
        for r in rows:
            td = r['trade_date'].strftime('%Y-%m-%d') if isinstance(r['trade_date'], date) else str(r['trade_date'])
            distance = abs(r['dte'] - target_dte)
            if td not in best_by_date or distance < best_by_date[td][1]:
                best_by_date[td] = (r, distance)

        return [v[0] for v in sorted(best_by_date.values(), key=lambda x: str(x[0]['trade_date']))]

    def get_options_chain(
        self, ticker: str, trade_date: str, expiration_date: str
    ) -> List[Dict]:
        """Get full options chain for a specific trade_date + expiration.

        Returns all strikes with bid/ask/mid, greeks, IV.
        """
        conn = self.get_orat_conn()
        tickers = [ticker]
        if ticker.upper() == "SPX":
            tickers = ["SPX", "SPXW"]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT trade_date, ticker, expiration_date, strike, underlying_price,
                       put_bid, put_ask, put_mid, call_bid, call_ask, call_mid,
                       delta, put_iv, call_iv, dte,
                       call_volume, put_volume, call_oi, put_oi
                FROM orat_options_eod
                WHERE ticker = ANY(%s)
                  AND trade_date = %s
                  AND expiration_date = %s
                ORDER BY strike;
            """, (tickers, trade_date, expiration_date))
            rows = [dict(r) for r in cur.fetchall()]

        # Convert Decimal to float
        for row in rows:
            for key in row:
                if isinstance(row[key], Decimal):
                    row[key] = float(row[key])
        return rows

    def get_chain_on_date(
        self, ticker: str, trade_date: str, dte_min: int, dte_max: int
    ) -> List[Dict]:
        """Get all options for a trade_date within a DTE range.

        Used to find available expirations on a given entry date.
        """
        conn = self.get_orat_conn()
        tickers = [ticker]
        if ticker.upper() == "SPX":
            tickers = ["SPX", "SPXW"]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT expiration_date, dte
                FROM orat_options_eod
                WHERE ticker = ANY(%s)
                  AND trade_date = %s
                  AND dte BETWEEN %s AND %s
                ORDER BY dte;
            """, (tickers, trade_date, dte_min, dte_max))
            rows = [dict(r) for r in cur.fetchall()]
        return rows

    def get_trading_days(self, ticker: str, start_date: str, end_date: str) -> List[str]:
        """Get all distinct trading days with options data (ORAT DB)."""
        conn = self.get_orat_conn()
        tickers = [ticker]
        if ticker.upper() == "SPX":
            tickers = ["SPX", "SPXW"]

        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT trade_date
                FROM orat_options_eod
                WHERE ticker = ANY(%s)
                  AND trade_date >= %s AND trade_date <= %s
                ORDER BY trade_date;
            """, (tickers, start_date, end_date))
            days = [row[0].strftime('%Y-%m-%d') if isinstance(row[0], date) else str(row[0])
                    for row in cur.fetchall()]
        return days

    def get_underlying_price(self, ticker: str, trade_date: str) -> Optional[float]:
        """Get underlying price for a date from ORAT data."""
        conn = self.get_orat_conn()
        tickers = [ticker]
        if ticker.upper() == "SPX":
            tickers = ["SPX", "SPXW"]

        with conn.cursor() as cur:
            cur.execute("""
                SELECT underlying_price
                FROM orat_options_eod
                WHERE ticker = ANY(%s) AND trade_date = %s
                  AND underlying_price IS NOT NULL
                LIMIT 1;
            """, (tickers, trade_date))
            row = cur.fetchone()
        return float(row[0]) if row else None

    def get_vix_for_date(self, trade_date: str) -> Optional[float]:
        """Get VIX closing value for a given date (single-date fallback).

        Prefer load_vix_cache() for bulk loading. This is only used if cache misses.
        """
        # Source 1: ORAT DB
        try:
            conn = self.get_orat_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT underlying_price
                    FROM orat_options_eod
                    WHERE ticker IN ('^VIX', 'VIX')
                      AND trade_date = %s
                      AND underlying_price IS NOT NULL
                    LIMIT 1;
                """, (trade_date,))
                row = cur.fetchone()
            if row:
                return float(row[0])
        except Exception:
            pass

        # Source 2: Main DB gex_structure_daily
        try:
            conn = self.get_main_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT spot_close
                    FROM gex_structure_daily
                    WHERE symbol = 'VIX' AND trade_date = %s
                    LIMIT 1;
                """, (trade_date,))
                row = cur.fetchone()
            if row and row[0]:
                return float(row[0])
        except Exception:
            pass

        return None

    def load_vix_cache(self, start_date: str, end_date: str) -> Dict[str, float]:
        """Bulk-load all VIX values for the date range into a dict.

        Returns {date_str: vix_value}. Single query instead of per-day lookups.
        """
        cache = {}

        # Source 1: ORAT DB — try to get VIX underlying_price
        try:
            conn = self.get_orat_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT trade_date, underlying_price
                    FROM orat_options_eod
                    WHERE ticker IN ('^VIX', 'VIX')
                      AND trade_date >= %s AND trade_date <= %s
                      AND underlying_price IS NOT NULL
                    ORDER BY trade_date;
                """, (start_date, end_date))
                for row in cur.fetchall():
                    d = row[0].strftime('%Y-%m-%d') if isinstance(row[0], date) else str(row[0])
                    cache[d] = float(row[1])
        except Exception:
            pass

        # Source 2: Fill gaps from gex_structure_daily
        try:
            conn = self.get_main_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT trade_date, spot_close
                    FROM gex_structure_daily
                    WHERE symbol = 'VIX'
                      AND trade_date >= %s AND trade_date <= %s
                      AND spot_close IS NOT NULL
                    ORDER BY trade_date;
                """, (start_date, end_date))
                for row in cur.fetchall():
                    d = row[0].strftime('%Y-%m-%d') if isinstance(row[0], date) else str(row[0])
                    if d not in cache:  # Don't overwrite ORAT data
                        cache[d] = float(row[1])
        except Exception:
            pass

        return cache

    def load_spx_ohlc_cache(self, start_date: str, end_date: str) -> Dict[str, Dict]:
        """Load SPX daily OHLC from Yahoo Finance for day-trade intraday simulation.

        Uses ^GSPC (S&P 500 index) via yfinance. Returns {date_str: {open, high, low, close}}.
        Pattern from backtest/zero_dte_bull_put_spread.py.
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed - day trade OHLC unavailable. pip install yfinance")
            return {}

        try:
            ticker = yf.Ticker("^GSPC")
            start_dt = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=5)
            end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=5)
            df = ticker.history(start=start_dt, end=end_dt)

            if df.empty:
                logger.warning("No SPX OHLC data from Yahoo Finance")
                return {}

            cache = {}
            for idx, row in df.iterrows():
                cache[idx.strftime('%Y-%m-%d')] = {
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                }
            logger.info(f"Loaded {len(cache)} days of SPX OHLC from Yahoo Finance")
            return cache
        except Exception as e:
            logger.warning(f"Failed to load SPX OHLC from Yahoo: {e}")
            return {}


# ═══════════════════════════════════════════════════════════════════════════════
# STRIKE SELECTION
# ═══════════════════════════════════════════════════════════════════════════════

class StrikeSelector:
    """Selects Iron Condor strikes using delta or percentage-OTM methods."""

    def __init__(self, config: MonthlyICConfig):
        self.config = config

    def select_strikes(
        self, chain: List[Dict], underlying: float
    ) -> Optional[Dict]:
        """Select IC strikes from the options chain.

        Tries delta-based selection first; falls back to pct_otm.

        Returns:
            Dict with put_short, put_long, call_short, call_long options,
            or None if no valid IC can be constructed.
        """
        # Check if delta data is usable
        has_delta = any(
            opt.get('delta') is not None and opt['delta'] != 0
            for opt in chain
        )

        if has_delta:
            result = self._select_by_delta(chain, underlying)
            if result:
                result['method'] = 'delta'
                return result

        # Fallback to percentage OTM
        result = self._select_by_pct_otm(chain, underlying)
        if result:
            result['method'] = 'pct_otm'
        return result

    def _select_by_delta(
        self, chain: List[Dict], underlying: float
    ) -> Optional[Dict]:
        """Select strikes by matching target delta."""
        target_delta = self.config.short_delta
        width = self.config.wing_width
        interval = self.config.strike_interval

        # Separate OTM puts (delta should be negative, |delta| near target)
        # and OTM calls (delta positive, near target)
        otm_puts = [
            opt for opt in chain
            if opt['strike'] < underlying
            and opt.get('delta') is not None
            and opt.get('put_bid') and opt['put_bid'] > 0
        ]

        otm_calls = [
            opt for opt in chain
            if opt['strike'] > underlying
            and opt.get('delta') is not None
            and opt.get('call_bid') and opt['call_bid'] > 0
        ]

        if not otm_puts or not otm_calls:
            return None

        # For puts, delta in ORAT is typically the call delta.
        # Put delta = call delta - 1. A ~10 delta put has call delta ~0.90.
        # We want |put_delta| ≈ target_delta, so call_delta ≈ 1 - target_delta.
        # But ORAT may store actual put delta as negative.
        # We'll handle both conventions.

        # Find short put: closest to target |put_delta|
        def put_delta_distance(opt):
            d = opt['delta']
            if d is None:
                return 999
            # If delta is positive (call convention), put_delta ≈ d - 1
            # If delta is negative, it's already put_delta
            if d > 0:
                put_d = abs(d - 1)  # e.g., 0.90 call → 0.10 put
            else:
                put_d = abs(d)
            return abs(put_d - target_delta)

        short_put = min(otm_puts, key=put_delta_distance)

        # Find short call: closest to target call_delta
        def call_delta_distance(opt):
            d = opt['delta']
            if d is None:
                return 999
            if d < 0:
                call_d = abs(d + 1)  # Negative convention
            else:
                call_d = d
            return abs(call_d - target_delta)

        short_call = min(otm_calls, key=call_delta_distance)

        # Find long strikes at wing_width away
        long_put = self._find_wing(chain, short_put['strike'] - width, 'put', below=True)
        long_call = self._find_wing(chain, short_call['strike'] + width, 'call', below=False)

        if not long_put or not long_call:
            return None

        return {
            'put_short': short_put,
            'put_long': long_put,
            'call_short': short_call,
            'call_long': long_call,
        }

    def _select_by_pct_otm(
        self, chain: List[Dict], underlying: float
    ) -> Optional[Dict]:
        """Select strikes by percentage OTM from underlying."""
        pct = self.config.pct_otm / 100.0
        width = self.config.wing_width
        interval = self.config.strike_interval

        # Target strikes
        put_target = underlying * (1 - pct)
        call_target = underlying * (1 + pct)

        # Round to nearest interval, AWAY from spot for safety
        put_target = math.floor(put_target / interval) * interval
        call_target = math.ceil(call_target / interval) * interval

        # Find short put
        otm_puts = [
            opt for opt in chain
            if opt['strike'] <= put_target
            and opt.get('put_bid') and opt['put_bid'] > 0
        ]
        if not otm_puts:
            return None
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - put_target))

        # Find short call
        otm_calls = [
            opt for opt in chain
            if opt['strike'] >= call_target
            and opt.get('call_bid') and opt['call_bid'] > 0
        ]
        if not otm_calls:
            return None
        short_call = min(otm_calls, key=lambda x: abs(x['strike'] - call_target))

        # Wings
        long_put = self._find_wing(chain, short_put['strike'] - width, 'put', below=True)
        long_call = self._find_wing(chain, short_call['strike'] + width, 'call', below=False)

        if not long_put or not long_call:
            return None

        return {
            'put_short': short_put,
            'put_long': long_put,
            'call_short': short_call,
            'call_long': long_call,
        }

    def _find_wing(
        self, chain: List[Dict], target_strike: float,
        option_type: str, below: bool
    ) -> Optional[Dict]:
        """Find the wing (long) option closest to target_strike."""
        if option_type == 'put':
            candidates = [
                opt for opt in chain
                if opt.get('put_ask') and opt['put_ask'] > 0
            ]
        else:
            candidates = [
                opt for opt in chain
                if opt.get('call_ask') and opt['call_ask'] > 0
            ]

        if not candidates:
            return None

        # Find closest to target
        best = min(candidates, key=lambda x: abs(x['strike'] - target_strike))

        # Verify it's on the correct side
        if below and best['strike'] > target_strike + self.config.strike_interval:
            return None
        if not below and best['strike'] < target_strike - self.config.strike_interval:
            return None

        return best


# ═══════════════════════════════════════════════════════════════════════════════
# PRICING
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_ic_credit(strikes: Dict) -> Tuple[float, float, float]:
    """Calculate Iron Condor credit from selected strikes.

    Uses mid-price (average of bid/ask) for entries.

    Returns:
        (put_credit, call_credit, total_credit) — all per-contract.
    """
    ps = strikes['put_short']
    pl = strikes['put_long']
    cs = strikes['call_short']
    cl = strikes['call_long']

    # Put spread credit: sell short put, buy long put
    put_short_price = _mid(ps.get('put_bid'), ps.get('put_ask'))
    put_long_price = _mid(pl.get('put_bid'), pl.get('put_ask'))
    put_credit = max(0, put_short_price - put_long_price)

    # Call spread credit: sell short call, buy long call
    call_short_price = _mid(cs.get('call_bid'), cs.get('call_ask'))
    call_long_price = _mid(cl.get('call_bid'), cl.get('call_ask'))
    call_credit = max(0, call_short_price - call_long_price)

    total_credit = put_credit + call_credit
    return put_credit, call_credit, total_credit


def calculate_ic_debit(
    chain: List[Dict], trade: ICTrade
) -> float:
    """Calculate cost to close the IC at current mid-prices.

    Returns debit per contract (positive = cost to close).
    """
    # Find current prices for each leg
    put_short_opt = _find_strike(chain, trade.put_short_strike)
    put_long_opt = _find_strike(chain, trade.put_long_strike)
    call_short_opt = _find_strike(chain, trade.call_short_strike)
    call_long_opt = _find_strike(chain, trade.call_long_strike)

    if not all([put_short_opt, put_long_opt, call_short_opt, call_long_opt]):
        return None  # Can't price — hold or use intrinsic

    # To close: buy back short, sell long
    put_short_close = _mid(put_short_opt.get('put_bid'), put_short_opt.get('put_ask'))
    put_long_close = _mid(put_long_opt.get('put_bid'), put_long_opt.get('put_ask'))
    call_short_close = _mid(call_short_opt.get('call_bid'), call_short_opt.get('call_ask'))
    call_long_close = _mid(call_long_opt.get('call_bid'), call_long_opt.get('call_ask'))

    # Debit to close put spread: buy short put - sell long put
    put_debit = put_short_close - put_long_close
    # Debit to close call spread: buy short call - sell long call
    call_debit = call_short_close - call_long_close

    total_debit = max(0, put_debit) + max(0, call_debit)
    return total_debit


def calculate_settlement_value(trade: ICTrade, settlement_price: float) -> float:
    """Calculate intrinsic value at expiration (cash settlement for SPX).

    For SPX: cash-settled, no early assignment risk.
    For SPY: exercise-settled but we treat as cash for backtest simplicity.

    Returns debit equivalent per contract.
    """
    # Put spread intrinsic
    if settlement_price < trade.put_short_strike:
        # Short put ITM
        put_intrinsic = min(
            trade.put_short_strike - settlement_price,
            trade.put_short_strike - trade.put_long_strike  # Capped at width
        )
    else:
        put_intrinsic = 0.0

    # Call spread intrinsic
    if settlement_price > trade.call_short_strike:
        # Short call ITM
        call_intrinsic = min(
            settlement_price - trade.call_short_strike,
            trade.call_long_strike - trade.call_short_strike  # Capped at width
        )
    else:
        call_intrinsic = 0.0

    return put_intrinsic + call_intrinsic


def _mid(bid, ask) -> float:
    """Calculate mid-price from bid/ask, handling None."""
    if bid and ask and bid > 0 and ask > 0:
        return (float(bid) + float(ask)) / 2.0
    if bid and bid > 0:
        return float(bid)
    if ask and ask > 0:
        return float(ask)
    return 0.0


def _find_strike(chain: List[Dict], strike: float) -> Optional[Dict]:
    """Find option in chain closest to a given strike."""
    if not chain:
        return None
    best = min(chain, key=lambda x: abs(float(x['strike']) - strike))
    if abs(float(best['strike']) - strike) < 1.0:
        return best
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class MonthlyICBacktester:
    """Monthly Iron Condor backtester.

    For each monthly expiration cycle:
    1. Find entry date (first trading day where DTE is in target range)
    2. Select strikes (delta or pct_otm)
    3. Calculate credit received
    4. Monitor daily: check profit target, stop loss, DTE exit
    5. Settle at expiration if no early exit
    6. Log result
    """

    def __init__(self, config: MonthlyICConfig):
        self.config = config
        self.db = BacktestDB()
        self.selector = StrikeSelector(config)

        # State
        self.trades: List[ICTrade] = []
        self.daily_snapshots: List[DailySnapshot] = []
        self.trade_counter = 0

        # Equity tracking
        self.equity = config.initial_capital
        self.high_water_mark = config.initial_capital
        self.cumulative_pnl = 0.0

        # Collateral tracking
        self.open_positions: List[ICTrade] = []  # Positions not yet closed
        self.margin_deployed: float = 0.0
        self.trades_skipped_no_capital: int = 0
        self.trades_skipped_vix: int = 0
        self.peak_concurrent_positions: int = 0
        self.peak_margin_deployed: float = 0.0

    def _available_buying_power(self) -> float:
        """Return capital available for new positions."""
        max_deployable = self.equity * (self.config.max_capital_utilization / 100.0)
        return max(0, max_deployable - self.margin_deployed)

    def _close_expired_before(self, current_date: str, all_trading_days: List[str]):
        """Close any open positions whose exit would have occurred before current_date.

        For monthly ICs, positions opened in earlier cycles may have closed by now
        (profit target, stop loss, DTE exit, or expiration). We must process them
        to free up margin before evaluating new entries.
        """
        still_open = []
        for pos in self.open_positions:
            if pos.exit_date and pos.exit_date <= current_date:
                # Already closed — margin is freed
                self.margin_deployed -= pos.margin_required
            else:
                still_open.append(pos)
        self.open_positions = still_open

    def _calculate_contracts_for_trade(self, wing_width: float, total_credit: float) -> int:
        """Determine how many contracts we can afford given available capital.

        Returns 0 if we can't afford even 1 contract.
        """
        margin_per_contract = wing_width * 100  # Reg-T for IC
        max_loss_per_contract = (wing_width - total_credit) * 100

        available = self._available_buying_power()

        # Check position count cap
        if self.config.max_concurrent_positions > 0:
            if len(self.open_positions) >= self.config.max_concurrent_positions:
                return 0

        if self.config.dynamic_sizing:
            # How many contracts can we afford from buying power?
            max_by_margin = int(available / margin_per_contract) if margin_per_contract > 0 else 0

            # How many contracts stay within per-trade risk limit?
            max_risk_dollars = self.equity * (self.config.max_risk_per_trade_pct / 100.0)
            max_by_risk = int(max_risk_dollars / max_loss_per_contract) if max_loss_per_contract > 0 else 0

            contracts = min(max_by_margin, max_by_risk)

            # Minimum 1-contract floor: if total equity can cover at least 1 IC,
            # always allow it. This ensures small accounts ($5k) can trade even
            # at low utilization — the utilization cap is aspirational, not blocking.
            if contracts == 0 and self.equity >= margin_per_contract and len(self.open_positions) == 0:
                contracts = 1

            return max(0, contracts)
        else:
            # Fixed sizing — check if we can afford the configured number
            needed_margin = margin_per_contract * self.config.contracts
            needed_risk = max_loss_per_contract * self.config.contracts
            max_risk_dollars = self.equity * (self.config.max_risk_per_trade_pct / 100.0)

            if needed_margin > available:
                return 0
            if needed_risk > max_risk_dollars:
                return 0
            return self.config.contracts

    def _register_open_position(self, trade: ICTrade):
        """Track a newly opened position for collateral purposes."""
        self.open_positions.append(trade)
        self.margin_deployed += trade.margin_required
        self.peak_concurrent_positions = max(self.peak_concurrent_positions, len(self.open_positions))
        self.peak_margin_deployed = max(self.peak_margin_deployed, self.margin_deployed)

    def _release_position_margin(self, trade: ICTrade):
        """Release margin when a position closes."""
        self.margin_deployed = max(0, self.margin_deployed - trade.margin_required)
        self.open_positions = [p for p in self.open_positions if p.trade_id != trade.trade_id]

    def run(self) -> Dict:
        """Execute the full backtest."""
        if self.config.dte_mode == "short":
            dte_label = f"{self.config.short_dte_target}DTE"
        elif self.config.dte_mode == "weekly":
            dte_label = f"Weekly ({self.config.weekly_dte_min}-{self.config.weekly_dte_max} DTE)"
        else:
            dte_label = "Monthly (30-45 DTE)"
        sizing_label = "DYNAMIC" if self.config.dynamic_sizing else f"FIXED ({self.config.contracts} contracts)"

        logger.info("=" * 80)
        logger.info("IRON CONDOR BACKTESTER")
        logger.info("=" * 80)
        logger.info(f"Ticker:          {self.config.ticker}")
        logger.info(f"Period:          {self.config.start_date} → {self.config.end_date}")
        logger.info(f"DTE mode:        {dte_label}")
        logger.info(f"Capital:         ${self.config.initial_capital:,.0f}")
        logger.info(f"Collateral:      ENFORCED ({self.config.max_capital_utilization}% max utilization)")
        logger.info(f"Sizing:          {sizing_label}")
        logger.info(f"Max risk/trade:  {self.config.max_risk_per_trade_pct}% of equity")
        logger.info(f"Short delta:     {self.config.short_delta}")
        logger.info(f"Wing width:      ${self.config.wing_width}")
        logger.info(f"Profit target:   {self.config.profit_target_pct}% of credit")
        logger.info(f"Stop loss:       {self.config.stop_loss_pct}% of credit (gap-capped: {self.config.sl_gap_cap})")
        logger.info(f"VIX filter:      {self.config.min_vix}–{self.config.max_vix} (tighter SL >{self.config.vix_tighten_sl_above}: {self.config.vix_tighten_sl_pct}%)")
        logger.info(f"Max positions:   {self.config.max_concurrent_positions if self.config.max_concurrent_positions > 0 else 'unlimited'}")
        logger.info(f"DTE exit:        {self.config.dte_exit} DTE")
        logger.info("=" * 80)

        # Step 0: Bulk-load VIX data (one query instead of per-day lookups)
        self.vix_cache = self.db.load_vix_cache(
            self.config.start_date, self.config.end_date
        )
        logger.info(f"Loaded {len(self.vix_cache)} VIX values into cache")

        # Step 0b: Bulk-load SPX daily OHLC from Yahoo Finance (for day trade mode)
        if self.config.day_trade:
            self.ohlc_cache = self.db.load_spx_ohlc_cache(
                self.config.start_date, self.config.end_date
            )
            logger.info(f"Loaded {len(self.ohlc_cache)} days of SPX OHLC for day trade mode")
        else:
            self.ohlc_cache = {}

        # Step 1: Get all trading days
        all_trading_days = self.db.get_trading_days(
            self.config.ticker, self.config.start_date, self.config.end_date
        )
        logger.info(f"Found {len(all_trading_days)} trading days with data")

        if not all_trading_days:
            logger.error("No trading days found. Check ticker and date range.")
            return {}

        # Step 2: Build entry list based on DTE mode
        if self.config.dte_mode == "short":
            entries = self._build_short_dte_entries(all_trading_days)
        elif self.config.dte_mode == "weekly":
            entries = self._build_weekly_dte_entries(all_trading_days)
        else:
            entries = self._build_monthly_entries(all_trading_days)

        logger.info(f"Found {len(entries)} potential entry opportunities")
        if not entries:
            logger.error("No entry opportunities found.")
            return {}

        # Step 3: Process each entry with collateral enforcement
        for entry_date, exp_str in entries:
            # Release margin from positions that closed before this entry
            self._close_expired_before(entry_date, all_trading_days)

            # Execute the trade cycle (collateral check happens inside)
            trade = self._execute_cycle_with_collateral(entry_date, exp_str, all_trading_days)
            if trade:
                self.trades.append(trade)
                self._register_open_position(trade)
                logger.info(
                    f"  Trade #{trade.trade_id}: {trade.entry_date} → {trade.exit_date} | "
                    f"{trade.contracts}x | Credit: ${trade.total_credit:.2f} | "
                    f"P&L: ${trade.net_pnl:+,.2f} | Exit: {trade.exit_reason} | "
                    f"Margin: ${self.margin_deployed:,.0f}/{self.equity * self.config.max_capital_utilization / 100:,.0f}"
                )

        # Step 4: Calculate and return results
        results = self._calculate_results()
        self._print_results(results)

        return results

    def _build_monthly_entries(self, all_trading_days: List[str]) -> List[Tuple[str, str]]:
        """Build (entry_date, expiration_date) pairs for monthly IC strategy."""
        expirations = self.db.get_monthly_expirations(
            self.config.ticker, self.config.start_date, self.config.end_date
        )
        trading_days_set = set(all_trading_days)
        entries = []
        processed = set()

        for exp_info in expirations:
            exp_date = exp_info['expiration_date']
            if exp_date is None:
                continue
            exp_str = exp_date.strftime('%Y-%m-%d') if isinstance(exp_date, date) else str(exp_date)
            if exp_str in processed:
                continue
            processed.add(exp_str)

            exp_dt = datetime.strptime(exp_str, '%Y-%m-%d')
            ideal_entry_dt = exp_dt - timedelta(days=self.config.target_dte_ideal)

            best_entry = None
            best_distance = 999

            for day_offset in range(-10, 11):
                candidate_dt = ideal_entry_dt + timedelta(days=day_offset)
                candidate_str = candidate_dt.strftime('%Y-%m-%d')
                if candidate_str not in trading_days_set or candidate_str < self.config.start_date:
                    continue
                dte = (exp_dt - candidate_dt).days
                if self.config.target_dte_min <= dte <= self.config.target_dte_max:
                    distance = abs(dte - self.config.target_dte_ideal)
                    if distance < best_distance:
                        best_distance = distance
                        best_entry = candidate_str

            if best_entry:
                entries.append((best_entry, exp_str))

        return entries

    def _build_short_dte_entries(self, all_trading_days: List[str]) -> List[Tuple[str, str]]:
        """Build (entry_date, expiration_date) pairs for short-DTE IC strategy (0-3 DTE)."""
        rows = self.db.get_short_dte_entries(
            self.config.ticker, self.config.start_date, self.config.end_date,
            self.config.short_dte_target
        )
        entries = []
        for r in rows:
            td = r['trade_date'].strftime('%Y-%m-%d') if isinstance(r['trade_date'], date) else str(r['trade_date'])
            ed = r['expiration_date'].strftime('%Y-%m-%d') if isinstance(r['expiration_date'], date) else str(r['expiration_date'])
            entries.append((td, ed))
        return entries

    def _build_weekly_dte_entries(self, all_trading_days: List[str]) -> List[Tuple[str, str]]:
        """Build (entry_date, expiration_date) pairs for weekly IC strategy (5-7 DTE)."""
        rows = self.db.get_weekly_dte_entries(
            self.config.ticker, self.config.start_date, self.config.end_date,
            self.config.weekly_dte_min, self.config.weekly_dte_max
        )
        entries = []
        for r in rows:
            td = r['trade_date'].strftime('%Y-%m-%d') if isinstance(r['trade_date'], date) else str(r['trade_date'])
            ed = r['expiration_date'].strftime('%Y-%m-%d') if isinstance(r['expiration_date'], date) else str(r['expiration_date'])
            entries.append((td, ed))
        return entries

    def _execute_cycle_with_collateral(
        self, entry_date: str, expiration_date: str,
        all_trading_days: List[str]
    ) -> Optional[ICTrade]:
        """Execute a single IC cycle with collateral enforcement and VIX filter."""

        # ── VIX filter ───────────────────────────────────────────────────
        vix = self.vix_cache.get(entry_date)
        if vix is not None:
            if vix > self.config.max_vix:
                self.trades_skipped_vix += 1
                logger.debug(f"  SKIPPED {entry_date}: VIX {vix:.1f} > {self.config.max_vix} (too high)")
                return None
            if vix < self.config.min_vix:
                self.trades_skipped_vix += 1
                logger.debug(f"  SKIPPED {entry_date}: VIX {vix:.1f} < {self.config.min_vix} (premium too thin)")
                return None

        # ── Entry ─────────────────────────────────────────────────────────
        chain = self.db.get_options_chain(
            self.config.ticker, entry_date, expiration_date
        )
        if not chain:
            return None

        underlying = None
        for opt in chain:
            if opt.get('underlying_price'):
                underlying = float(opt['underlying_price'])
                break
        if not underlying:
            return None

        # Select strikes
        strikes = self.selector.select_strikes(chain, underlying)
        if not strikes:
            return None

        # Calculate credit
        put_credit, call_credit, total_credit = calculate_ic_credit(strikes)
        if total_credit < self.config.min_credit:
            return None

        wing_width = abs(strikes['put_short']['strike'] - strikes['put_long']['strike'])

        # ── Collateral check ─────────────────────────────────────────────
        contracts = self._calculate_contracts_for_trade(wing_width, total_credit)
        if contracts <= 0:
            self.trades_skipped_no_capital += 1
            logger.warning(
                f"  SKIPPED {entry_date}: Insufficient capital "
                f"(available: ${self._available_buying_power():,.0f}, "
                f"needed: ${wing_width * 100:,.0f}/contract, "
                f"open positions: {len(self.open_positions)})"
            )
            return None

        # Build trade object with collateral-enforced contract count
        self.trade_counter += 1
        entry_dt = datetime.strptime(entry_date, '%Y-%m-%d')
        exp_dt = datetime.strptime(expiration_date, '%Y-%m-%d')
        dte = (exp_dt - entry_dt).days

        max_loss_per_contract = (wing_width - total_credit) * 100
        margin = wing_width * 100

        trade = ICTrade(
            trade_id=self.trade_counter,
            entry_date=entry_date,
            expiration_date=expiration_date,
            dte_at_entry=dte,
            underlying_at_entry=underlying,
            vix_at_entry=vix or 0.0,
            put_short_strike=strikes['put_short']['strike'],
            put_long_strike=strikes['put_long']['strike'],
            put_credit=put_credit,
            put_short_delta=strikes['put_short'].get('delta', 0) or 0,
            put_short_iv=strikes['put_short'].get('put_iv', 0) or 0,
            call_short_strike=strikes['call_short']['strike'],
            call_long_strike=strikes['call_long']['strike'],
            call_credit=call_credit,
            call_short_delta=strikes['call_short'].get('delta', 0) or 0,
            call_short_iv=strikes['call_short'].get('call_iv', 0) or 0,
            total_credit=total_credit,
            max_profit=total_credit * 100 * contracts,
            max_loss=max_loss_per_contract * contracts,
            wing_width=wing_width,
            contracts=contracts,
            margin_required=margin * contracts,
            strike_selection_method=strikes['method'],
        )

        # ── Day trade mode: close on entry day ──────────────────────────
        # All modes are day trades: enter and exit on the same day.
        # Yahoo Finance daily OHLC gives us High/Low for intraday SL check,
        # and Close for EOD settlement.  This works for ALL DTE modes because
        # we always exit on entry day — the expiration only determines which
        # contract we sold (affecting premium/credit).
        if self.config.day_trade:
            ohlc = getattr(self, 'ohlc_cache', {}).get(entry_date)
            if not ohlc:
                # Fallback: no Yahoo data for this day — use ORAT underlying price
                price = self.db.get_underlying_price(self.config.ticker, entry_date)
                if price:
                    debit = calculate_settlement_value(trade, price)
                    return self._close_trade(trade, entry_date, debit, "DAY_TRADE_CLOSE", dte)
                return None  # Can't price exit

            daily_high = ohlc['high']
            daily_low = ohlc['low']
            close_price = ohlc['close']

            effective_sl_pct = self.config.stop_loss_pct
            sl_debit_threshold = trade.total_credit * (1 + effective_sl_pct / 100)

            # Check INTRADAY stop loss using High/Low
            # Worst case: put spread breached at daily low, call spread breached at daily high
            put_intrinsic_at_low = max(0, trade.put_short_strike - daily_low)
            call_intrinsic_at_high = max(0, daily_high - trade.call_short_strike)
            put_intrinsic_at_low = min(put_intrinsic_at_low, trade.wing_width)
            call_intrinsic_at_high = min(call_intrinsic_at_high, trade.wing_width)

            intraday_worst_debit = put_intrinsic_at_low + call_intrinsic_at_high
            if intraday_worst_debit >= sl_debit_threshold:
                capped_debit = sl_debit_threshold
                if self.config.sl_gap_cap:
                    gap_slippage = 1 + self.config.sl_gap_slippage_pct / 100
                    capped_debit = min(intraday_worst_debit, sl_debit_threshold * gap_slippage)
                return self._close_trade(trade, entry_date, capped_debit, "STOP_LOSS", dte)

            # EOD settlement using Close price
            close_debit = calculate_settlement_value(trade, close_price)

            # Check profit target at close
            profit_threshold = trade.total_credit * (1 - self.config.profit_target_pct / 100)
            if close_debit <= profit_threshold:
                return self._close_trade(trade, entry_date, close_debit, "PROFIT_TARGET", dte)

            # Otherwise close at EOD market value
            return self._close_trade(trade, entry_date, close_debit, "DAY_TRADE_CLOSE", dte)

        # ── Multi-day monitoring (only when day_trade=False) ─────────────
        # Find trading days between entry and expiration
        monitoring_days = [
            d for d in all_trading_days
            if d > entry_date and d <= expiration_date
        ]

        for monitor_date in monitoring_days:
            monitor_dt = datetime.strptime(monitor_date, '%Y-%m-%d')
            current_dte = (exp_dt - monitor_dt).days

            # DTE exit check (before we fetch chain to save queries)
            if not self.config.hold_to_expiration and current_dte <= self.config.dte_exit:
                # Try to get current prices for a clean exit
                monitor_chain = self.db.get_options_chain(
                    self.config.ticker, monitor_date, expiration_date
                )
                if monitor_chain:
                    debit = calculate_ic_debit(monitor_chain, trade)
                    if debit is not None:
                        return self._close_trade(trade, monitor_date, debit, "DTE_EXIT", current_dte)

                # Fallback: estimate debit from intrinsic
                price = self.db.get_underlying_price(self.config.ticker, monitor_date)
                if price:
                    debit = calculate_settlement_value(trade, price)
                    return self._close_trade(trade, monitor_date, debit, "DTE_EXIT", current_dte)

            # ── Determine effective stop-loss % (VIX-adaptive) ────────
            effective_sl_pct = self.config.stop_loss_pct
            vix_today = self.vix_cache.get(monitor_date)
            if vix_today and vix_today > self.config.vix_tighten_sl_above:
                effective_sl_pct = self.config.vix_tighten_sl_pct  # Tighter SL in high-VIX

            # ── First check: intrinsic-value SL (catches overnight gaps) ──
            # Before fetching the full chain (expensive), check if the
            # underlying price alone already breaches the stop. This is
            # equivalent to "check at market open" — if SPX gapped through
            # the short strike overnight, intrinsic value reveals it.
            price = self.db.get_underlying_price(self.config.ticker, monitor_date)
            if price:
                intrinsic_debit = calculate_settlement_value(trade, price)
                sl_debit_threshold = trade.total_credit * (1 + effective_sl_pct / 100)
                if intrinsic_debit >= sl_debit_threshold:
                    # Gap detected — cap exit at intended SL level + slippage
                    if self.config.sl_gap_cap:
                        gap_slippage = 1 + self.config.sl_gap_slippage_pct / 100
                        capped_debit = min(intrinsic_debit, sl_debit_threshold * gap_slippage)
                    else:
                        capped_debit = intrinsic_debit
                    return self._close_trade(trade, monitor_date, capped_debit, "STOP_LOSS", current_dte)

            # ── Second check: mid-price based PT/SL (normal intraday) ──
            monitor_chain = self.db.get_options_chain(
                self.config.ticker, monitor_date, expiration_date
            )
            if not monitor_chain:
                continue

            debit = calculate_ic_debit(monitor_chain, trade)
            if debit is None:
                continue

            # Profit target: close when we've captured X% of max credit
            profit_threshold = trade.total_credit * (1 - self.config.profit_target_pct / 100)
            if debit <= profit_threshold:
                return self._close_trade(trade, monitor_date, debit, "PROFIT_TARGET", current_dte)

            # Stop loss: close when loss exceeds X% of credit
            sl_debit_threshold = trade.total_credit * (1 + effective_sl_pct / 100)
            if debit >= sl_debit_threshold:
                # Cap the exit debit if gap blew past the SL level
                if self.config.sl_gap_cap:
                    gap_slippage = 1 + self.config.sl_gap_slippage_pct / 100
                    capped_debit = min(debit, sl_debit_threshold * gap_slippage)
                else:
                    capped_debit = debit
                return self._close_trade(trade, monitor_date, capped_debit, "STOP_LOSS", current_dte)

        # ── Expiration settlement ─────────────────────────────────────────
        return self._settle_at_expiration(trade, all_trading_days)

    def _close_trade(
        self, trade: ICTrade, exit_date: str, exit_debit: float,
        reason: str, dte_at_exit: int
    ) -> ICTrade:
        """Close a trade before expiration."""
        entry_dt = datetime.strptime(trade.entry_date, '%Y-%m-%d')
        exit_dt = datetime.strptime(exit_date, '%Y-%m-%d')

        price = self.db.get_underlying_price(self.config.ticker, exit_date)

        trade.exit_date = exit_date
        trade.exit_reason = reason
        trade.dte_at_exit = dte_at_exit
        trade.underlying_at_exit = price or trade.underlying_at_entry
        trade.exit_debit = exit_debit
        trade.days_held = (exit_dt - entry_dt).days

        # P&L
        gross = (trade.total_credit - exit_debit) * 100 * trade.contracts
        commissions = self.config.commission_per_contract * 4 * trade.contracts * 2  # 4 legs, open+close
        slippage = self.config.slippage_per_contract * 2 * trade.contracts * 2  # 2 spreads, open+close

        trade.gross_pnl = gross
        trade.commissions = commissions
        trade.slippage_cost = slippage
        trade.net_pnl = gross - commissions - slippage
        trade.return_on_risk = (trade.net_pnl / trade.max_loss * 100) if trade.max_loss > 0 else 0

        # Update equity and release margin
        self.cumulative_pnl += trade.net_pnl
        self.equity = self.config.initial_capital + self.cumulative_pnl
        self.high_water_mark = max(self.high_water_mark, self.equity)
        self._release_position_margin(trade)

        return trade

    def _settle_at_expiration(
        self, trade: ICTrade, all_trading_days: List[str]
    ) -> ICTrade:
        """Settle a trade at expiration."""
        # Get settlement price on or near expiration
        exp_date = trade.expiration_date
        settlement_price = self.db.get_underlying_price(self.config.ticker, exp_date)

        # If expiration day has no data, try the day before
        if not settlement_price:
            exp_dt = datetime.strptime(exp_date, '%Y-%m-%d')
            for offset in range(1, 4):
                prev = (exp_dt - timedelta(days=offset)).strftime('%Y-%m-%d')
                settlement_price = self.db.get_underlying_price(self.config.ticker, prev)
                if settlement_price:
                    break

        if not settlement_price:
            logger.warning(f"  No settlement price for {exp_date}, skipping")
            return None

        # Calculate intrinsic value at expiration
        debit = calculate_settlement_value(trade, settlement_price)

        entry_dt = datetime.strptime(trade.entry_date, '%Y-%m-%d')
        exp_dt = datetime.strptime(exp_date, '%Y-%m-%d')

        trade.exit_date = exp_date
        trade.exit_reason = "EXPIRATION"
        trade.dte_at_exit = 0
        trade.underlying_at_exit = settlement_price
        trade.exit_debit = debit
        trade.days_held = (exp_dt - entry_dt).days

        # P&L — at expiration, only pay entry commissions + settlement
        gross = (trade.total_credit - debit) * 100 * trade.contracts
        # At expiration: only entry commissions (no close order needed for cash-settled SPX)
        if self.config.ticker.upper() in ("SPX", "SPXW"):
            commissions = self.config.commission_per_contract * 4 * trade.contracts  # Open only
        else:
            commissions = self.config.commission_per_contract * 4 * trade.contracts * 2
        slippage = self.config.slippage_per_contract * 2 * trade.contracts  # Entry only

        trade.gross_pnl = gross
        trade.commissions = commissions
        trade.slippage_cost = slippage
        trade.net_pnl = gross - commissions - slippage
        trade.return_on_risk = (trade.net_pnl / trade.max_loss * 100) if trade.max_loss > 0 else 0

        # Update equity and release margin
        self.cumulative_pnl += trade.net_pnl
        self.equity = self.config.initial_capital + self.cumulative_pnl
        self.high_water_mark = max(self.high_water_mark, self.equity)
        self._release_position_margin(trade)

        return trade

    # ── Results ───────────────────────────────────────────────────────────

    def _calculate_results(self) -> Dict:
        """Calculate comprehensive backtest metrics."""
        if not self.trades:
            return {
                'summary': {
                    'total_trades': 0, 'win_rate': 0, 'total_pnl': 0,
                    'total_return_pct': 0, 'profit_factor': 0,
                    'avg_pnl': 0, 'avg_win': 0, 'avg_loss': 0,
                    'best_trade_pnl': 0, 'worst_trade_pnl': 0,
                    'final_equity': self.equity,
                    'initial_capital': self.config.initial_capital,
                },
                'risk': {
                    'max_drawdown_pct': 0, 'max_drawdown_dollar': 0,
                    'sharpe_ratio': 0, 'sortino_ratio': 0,
                    'calmar_ratio': 0,
                },
                'collateral': {
                    'trades_skipped_no_capital': self.trades_skipped_no_capital,
                    'trades_skipped_vix': getattr(self, 'trades_skipped_vix', 0),
                    'peak_concurrent_positions': 0,
                    'avg_contracts_per_trade': 0,
                    'peak_margin_deployed': 0,
                },
                'note': f'No trades executed — capital ${self.config.initial_capital:,.0f} '
                        f'at {self.config.max_capital_utilization}% utilization '
                        f'= ${self.config.initial_capital * self.config.max_capital_utilization / 100:,.0f} '
                        f'available (SPX IC margin ~$2,500/contract)',
            }

        trades = self.trades
        n = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]

        # Basic stats
        total_pnl = sum(t.net_pnl for t in trades)
        total_return = (total_pnl / self.config.initial_capital) * 100
        win_rate = len(wins) / n * 100

        gross_profit = sum(t.net_pnl for t in wins)
        gross_loss = sum(t.net_pnl for t in losses)
        profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')

        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0
        avg_pnl = total_pnl / n

        best_trade = max(trades, key=lambda t: t.net_pnl)
        worst_trade = min(trades, key=lambda t: t.net_pnl)
        median_pnl = sorted(t.net_pnl for t in trades)[n // 2]

        avg_days_held = sum(t.days_held for t in trades) / n

        # Max drawdown
        peak = self.config.initial_capital
        max_dd = 0
        max_dd_dollars = 0
        running = self.config.initial_capital
        for t in trades:
            running += t.net_pnl
            peak = max(peak, running)
            dd_pct = (peak - running) / peak * 100
            dd_dollars = peak - running
            max_dd = max(max_dd, dd_pct)
            max_dd_dollars = max(max_dd_dollars, dd_dollars)

        # Sharpe ratio (annualized)
        returns = [t.net_pnl / self.config.initial_capital for t in trades]
        avg_ret = sum(returns) / len(returns)
        std_ret = (sum((r - avg_ret) ** 2 for r in returns) / len(returns)) ** 0.5
        # Annualize based on DTE mode
        if self.config.dte_mode == "short":
            trades_per_year = 252  # ~252 trading days/year for daily trades
        else:
            trades_per_year = 12
        sharpe = (avg_ret / std_ret * math.sqrt(trades_per_year)) if std_ret > 0 else 0

        # Sortino ratio (only downside deviation)
        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_dev = (sum(r ** 2 for r in downside_returns) / len(downside_returns)) ** 0.5
            sortino = (avg_ret / downside_dev * math.sqrt(trades_per_year)) if downside_dev > 0 else 0
        else:
            sortino = float('inf')

        # Monthly returns
        monthly_returns = {}
        for t in trades:
            month = t.entry_date[:7]
            monthly_returns[month] = monthly_returns.get(month, 0) + t.net_pnl

        # Annual returns
        annual_returns = {}
        for t in trades:
            year = t.entry_date[:4]
            annual_returns[year] = annual_returns.get(year, 0) + t.net_pnl

        # Win/loss streaks
        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 0
        for t in trades:
            if t.net_pnl > 0:
                if current_streak > 0:
                    current_streak += 1
                else:
                    current_streak = 1
                max_win_streak = max(max_win_streak, current_streak)
            else:
                if current_streak < 0:
                    current_streak -= 1
                else:
                    current_streak = -1
                max_loss_streak = max(max_loss_streak, abs(current_streak))

        # Exit reason breakdown
        exit_reasons = {}
        for t in trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

        # Equity curve
        equity_curve = []
        running = self.config.initial_capital
        cumulative = 0.0
        for i, t in enumerate(trades):
            running += t.net_pnl
            cumulative += t.net_pnl
            peak_so_far = max(self.config.initial_capital, max((e['equity'] for e in equity_curve), default=self.config.initial_capital))
            dd_pct = ((running - peak_so_far) / peak_so_far * 100) if peak_so_far > 0 else 0
            equity_curve.append({
                'date': t.exit_date,
                'trade_num': i + 1,
                'equity': round(running, 2),
                'pnl': round(t.net_pnl, 2),
                'cumulative_pnl': round(cumulative, 2),
                'return_pct': round(cumulative / self.config.initial_capital * 100, 2),
                'drawdown_pct': round(dd_pct, 2),
                'exit_reason': t.exit_reason,
            })

        return {
            'config': {
                'ticker': self.config.ticker,
                'start_date': self.config.start_date,
                'end_date': self.config.end_date,
                'initial_capital': self.config.initial_capital,
                'short_delta': self.config.short_delta,
                'pct_otm': self.config.pct_otm,
                'wing_width': self.config.wing_width,
                'profit_target_pct': self.config.profit_target_pct,
                'stop_loss_pct': self.config.stop_loss_pct,
                'dte_exit': self.config.dte_exit,
                'contracts': self.config.contracts,
                'hold_to_expiration': self.config.hold_to_expiration,
                'max_capital_utilization': self.config.max_capital_utilization,
                'max_vix': self.config.max_vix,
                'min_vix': self.config.min_vix,
                'sl_gap_cap': self.config.sl_gap_cap,
                'max_concurrent_positions': self.config.max_concurrent_positions,
                'dte_mode': self.config.dte_mode,
                'short_dte_target': self.config.short_dte_target,
            },
            'summary': {
                'total_trades': n,
                'winning_trades': len(wins),
                'losing_trades': len(losses),
                'win_rate': round(win_rate, 2),
                'total_pnl': round(total_pnl, 2),
                'total_return_pct': round(total_return, 2),
                'avg_pnl_per_trade': round(avg_pnl, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'best_trade': round(best_trade.net_pnl, 2),
                'worst_trade': round(worst_trade.net_pnl, 2),
                'median_trade': round(median_pnl, 2),
                'profit_factor': round(profit_factor, 2),
                'avg_days_held': round(avg_days_held, 1),
                'final_equity': round(self.equity, 2),
            },
            'risk': {
                'max_drawdown_pct': round(max_dd, 2),
                'max_drawdown_dollars': round(max_dd_dollars, 2),
                'sharpe_ratio': round(sharpe, 2),
                'sortino_ratio': round(sortino, 2),
                'gross_profit': round(gross_profit, 2),
                'gross_loss': round(gross_loss, 2),
            },
            'streaks': {
                'max_win_streak': max_win_streak,
                'max_loss_streak': max_loss_streak,
            },
            'collateral': {
                'max_capital_utilization_pct': self.config.max_capital_utilization,
                'trades_skipped_no_capital': self.trades_skipped_no_capital,
                'trades_skipped_vix': self.trades_skipped_vix,
                'peak_concurrent_positions': self.peak_concurrent_positions,
                'peak_margin_deployed': round(self.peak_margin_deployed, 2),
                'peak_margin_pct_of_capital': round(
                    self.peak_margin_deployed / self.config.initial_capital * 100, 2
                ) if self.config.initial_capital > 0 else 0,
                'avg_contracts_per_trade': round(
                    sum(t.contracts for t in trades) / n, 2
                ) if n > 0 else 0,
                'dynamic_sizing': self.config.dynamic_sizing,
                'max_concurrent_positions': self.config.max_concurrent_positions,
            },
            'exit_reasons': exit_reasons,
            'monthly_returns': {k: round(v, 2) for k, v in sorted(monthly_returns.items())},
            'annual_returns': {k: round(v, 2) for k, v in sorted(annual_returns.items())},
            'equity_curve': equity_curve,
        }

    def _print_results(self, results: Dict):
        """Print formatted results to console."""
        if 'error' in results:
            logger.error(results['error'])
            return

        s = results['summary']
        r = results['risk']
        c = results['config']
        st = results['streaks']
        ex = results['exit_reasons']

        col = results.get('collateral', {})
        dte_label = c.get('dte_mode', 'monthly').upper()
        if c.get('dte_mode') == 'short':
            dte_label = f"{c.get('short_dte_target', 0)}DTE"

        print("\n" + "=" * 80)
        print(f"  IRON CONDOR BACKTEST RESULTS ({dte_label})")
        print("=" * 80)

        print(f"\n  Ticker:              {c['ticker']}")
        print(f"  Period:              {c['start_date']} → {c['end_date']}")
        print(f"  DTE Mode:            {dte_label}")
        print(f"  Strategy:            {c['short_delta']:.0%} delta IC, ${c['wing_width']:.0f} wings")
        print(f"  Exit rules:          {c['profit_target_pct']}% profit / {c['stop_loss_pct']}% stop / {c['dte_exit']} DTE")
        print(f"  VIX filter:          {c.get('min_vix', 0)}–{c.get('max_vix', 999)}")
        print(f"  SL gap cap:          {'ON' if c.get('sl_gap_cap', True) else 'OFF'}")
        print(f"  Max positions:       {c.get('max_concurrent_positions', 0) or 'unlimited'}")
        print(f"  Collateral:          {c.get('max_capital_utilization', 80)}% max utilization")

        print(f"\n  {'─' * 60}")
        print(f"  PERFORMANCE")
        print(f"  {'─' * 60}")
        print(f"  Initial Capital:     ${c['initial_capital']:>12,.2f}")
        print(f"  Final Equity:        ${s['final_equity']:>12,.2f}")
        print(f"  Total P&L:           ${s['total_pnl']:>+12,.2f}")
        print(f"  Total Return:        {s['total_return_pct']:>+12.2f}%")

        print(f"\n  {'─' * 60}")
        print(f"  TRADE STATISTICS")
        print(f"  {'─' * 60}")
        print(f"  Total Trades:        {s['total_trades']:>8}")
        print(f"  Win Rate:            {s['win_rate']:>7.1f}%")
        print(f"  Avg P&L/Trade:       ${s['avg_pnl_per_trade']:>+10,.2f}")
        print(f"  Avg Win:             ${s['avg_win']:>+10,.2f}")
        print(f"  Avg Loss:            ${s['avg_loss']:>+10,.2f}")
        print(f"  Best Trade:          ${s['best_trade']:>+10,.2f}")
        print(f"  Worst Trade:         ${s['worst_trade']:>+10,.2f}")
        print(f"  Median Trade:        ${s['median_trade']:>+10,.2f}")
        print(f"  Profit Factor:       {s['profit_factor']:>10.2f}")
        print(f"  Avg Days Held:       {s['avg_days_held']:>10.1f}")

        print(f"\n  {'─' * 60}")
        print(f"  RISK METRICS")
        print(f"  {'─' * 60}")
        print(f"  Max Drawdown:        {r['max_drawdown_pct']:>10.2f}%")
        print(f"  Max Drawdown ($):    ${r['max_drawdown_dollars']:>10,.2f}")
        print(f"  Sharpe Ratio:        {r['sharpe_ratio']:>10.2f}")
        print(f"  Sortino Ratio:       {r['sortino_ratio']:>10.2f}")
        print(f"  Max Win Streak:      {st['max_win_streak']:>8}")
        print(f"  Max Loss Streak:     {st['max_loss_streak']:>8}")

        if col:
            print(f"\n  {'─' * 60}")
            print(f"  COLLATERAL MANAGEMENT")
            print(f"  {'─' * 60}")
            print(f"  Max Utilization:     {col.get('max_capital_utilization_pct', 0):>8.0f}%")
            print(f"  Skipped (capital):   {col.get('trades_skipped_no_capital', 0):>8}")
            print(f"  Skipped (VIX):       {col.get('trades_skipped_vix', 0):>8}")
            print(f"  Max Positions Cap:   {col.get('max_concurrent_positions', 0):>8}")
            print(f"  Peak Concurrent:     {col.get('peak_concurrent_positions', 0):>8} positions")
            print(f"  Peak Margin:         ${col.get('peak_margin_deployed', 0):>10,.2f}")
            print(f"  Peak Margin %:       {col.get('peak_margin_pct_of_capital', 0):>8.1f}% of capital")
            print(f"  Avg Contracts/Trade: {col.get('avg_contracts_per_trade', 0):>8.1f}")
            print(f"  Dynamic Sizing:      {'ON' if col.get('dynamic_sizing') else 'OFF':>8}")

        print(f"\n  {'─' * 60}")
        print(f"  EXIT REASONS")
        print(f"  {'─' * 60}")
        for reason, count in sorted(ex.items(), key=lambda x: -x[1]):
            pct = count / s['total_trades'] * 100
            print(f"  {reason:<20s}  {count:>4} ({pct:>5.1f}%)")

        print(f"\n  {'─' * 60}")
        print(f"  ANNUAL RETURNS")
        print(f"  {'─' * 60}")
        for year, pnl in sorted(results['annual_returns'].items()):
            pct = pnl / c['initial_capital'] * 100
            bar = "+" * int(max(0, pct / 2)) + "-" * int(max(0, -pct / 2))
            print(f"  {year}:  ${pnl:>+10,.2f}  ({pct:>+6.1f}%)  {bar[:30]}")

        print(f"\n  {'─' * 60}")
        print(f"  MONTHLY RETURNS")
        print(f"  {'─' * 60}")
        for month, pnl in sorted(results['monthly_returns'].items()):
            pct = pnl / c['initial_capital'] * 100
            bar = "+" * int(max(0, pct * 5)) + "-" * int(max(0, -pct * 5))
            print(f"  {month}:  ${pnl:>+8,.2f}  ({pct:>+5.2f}%)  {bar[:20]}")

        # Print equity curve as copy-pasteable CSV
        ec = results.get('equity_curve', [])
        if ec:
            print(f"\n  {'─' * 60}")
            print(f"  EQUITY CURVE (copy/paste as CSV)")
            print(f"  {'─' * 60}")
            print("date,trade_num,equity,pnl,cumulative_pnl,return_pct,drawdown_pct,exit_reason")
            for row in ec:
                print(f"{row['date']},{row['trade_num']},{row['equity']},{row['pnl']},{row['cumulative_pnl']},{row['return_pct']},{row['drawdown_pct']},{row['exit_reason']}")

        print("\n" + "=" * 80)

    # ── Export ────────────────────────────────────────────────────────────

    def export_trades_csv(self, filepath: str = None):
        """Export all trades to CSV."""
        if not self.trades:
            logger.warning("No trades to export")
            return

        if not filepath:
            filepath = (
                f"backtest/results/{self.config.ticker}_monthly_ic_trades_"
                f"{self.config.start_date}_{self.config.end_date}.csv"
            )

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self.trades[0]).keys())
            writer.writeheader()
            for trade in self.trades:
                writer.writerow(asdict(trade))

        logger.info(f"Exported {len(self.trades)} trades to {filepath}")

    def export_results_json(self, results: Dict, filepath: str = None):
        """Export results to JSON."""
        if not filepath:
            filepath = (
                f"backtest/results/{self.config.ticker}_monthly_ic_results_"
                f"{self.config.start_date}_{self.config.end_date}.json"
            )

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Exported results to {filepath}")

    def export_equity_curve_csv(self, results: Dict, filepath: str = None):
        """Export equity curve to CSV."""
        if not results.get('equity_curve'):
            return

        if not filepath:
            filepath = (
                f"backtest/results/{self.config.ticker}_monthly_ic_equity_"
                f"{self.config.start_date}_{self.config.end_date}.csv"
            )

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        fieldnames = ['date', 'trade_num', 'equity', 'pnl', 'cumulative_pnl',
                      'return_pct', 'drawdown_pct', 'exit_reason']
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results['equity_curve'])

        logger.info(f"Exported equity curve to {filepath}")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA AUDIT (Phase 1)
# ═══════════════════════════════════════════════════════════════════════════════

def run_data_audit():
    """Run comprehensive Phase 1 data audit and report findings."""
    print("\n" + "=" * 80)
    print("  PHASE 1: DATA AUDIT")
    print("=" * 80)

    db = BacktestDB()

    # 1A: Tables (main DB)
    print("\n  1A. MAIN DB TABLES (top 50 by row count)")
    print("  " + "-" * 60)
    print(f"    DATABASE_URL: {'SET' if db.main_url else 'NOT SET'}")
    tables = db.audit_tables()
    for t in tables[:50]:
        print(f"    {t['table_name']:50s} {t['row_count']:>12,} rows")
    if len(tables) > 50:
        print(f"    ... and {len(tables) - 50} more tables")
    print(f"  Total: {len(tables)} tables")

    # 1A2: ORAT DB tables (may be separate)
    print("\n  1A2. ORAT DB TABLES (options chain database)")
    print("  " + "-" * 60)
    print(f"    ORAT_DATABASE_URL: {'SET' if os.getenv('ORAT_DATABASE_URL') else 'NOT SET (using DATABASE_URL)'}")
    same_db = (db.orat_url == db.main_url)
    print(f"    Same as main DB: {same_db}")
    if not same_db:
        try:
            orat_conn = db.get_orat_conn()
            with orat_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT schemaname, relname AS table_name, n_live_tup AS row_count
                    FROM pg_stat_user_tables
                    ORDER BY n_live_tup DESC LIMIT 30;
                """)
                orat_tables = [dict(r) for r in cur.fetchall()]
            for t in orat_tables:
                print(f"    {t['table_name']:50s} {t['row_count']:>12,} rows")
            print(f"  Total shown: {len(orat_tables)} tables")
        except Exception as e:
            print(f"    ERROR connecting to ORAT DB: {e}")

    # 1B: ORAT options data
    print("\n  1B. ORAT OPTIONS DATA AUDIT")
    print("  " + "-" * 60)
    try:
        orat = db.audit_orat_data()

        s = orat['summary']
        print(f"    Date range: {s['min_date']} → {s['max_date']}")
        print(f"    Total rows: {s['total_rows']:,}")
        print(f"    Distinct days: {s['distinct_days']}")
        print(f"    Distinct tickers: {s['distinct_tickers']}")

        print("\n    Tickers:")
        for t in orat['tickers']:
            print(f"      {t['ticker']:>8s}: {t['rows']:>10,} rows, {t['days']:>5} days  ({t['min_date']} → {t['max_date']})")

        print("\n    DTE Distribution (relevant for monthly IC: DTE 25-50):")
        monthly_rows = 0
        for d in orat['dte_distribution']:
            if 25 <= (d.get('dte') or 0) <= 50:
                print(f"      DTE {d['dte']:>3}: {d['rows']:>10,} rows")
                monthly_rows += d['rows']
        print(f"      Total rows with DTE 25-50: {monthly_rows:,}")

        dc = orat['data_completeness']
        print(f"\n    Data Completeness:")
        print(f"      Total rows:       {dc['total_rows']:>10,}")
        print(f"      With delta:       {dc['rows_with_delta']:>10,}  ({dc['rows_with_delta']/max(dc['total_rows'],1)*100:.1f}%)")
        print(f"      With put IV:      {dc['rows_with_put_iv']:>10,}  ({dc['rows_with_put_iv']/max(dc['total_rows'],1)*100:.1f}%)")
        print(f"      With call IV:     {dc['rows_with_call_iv']:>10,}  ({dc['rows_with_call_iv']/max(dc['total_rows'],1)*100:.1f}%)")
        print(f"      With put bid:     {dc['rows_with_put_bid']:>10,}  ({dc['rows_with_put_bid']/max(dc['total_rows'],1)*100:.1f}%)")
        print(f"      With call bid:    {dc['rows_with_call_bid']:>10,}  ({dc['rows_with_call_bid']/max(dc['total_rows'],1)*100:.1f}%)")

        m = orat['monthly_dte_days']
        print(f"\n    Days with monthly-range DTE (30-45): {m['days_with_monthly_dte']}")

        print("\n    Sample monthly-range rows:")
        for row in orat['sample_monthly']:
            print(f"      {row}")

    except Exception as e:
        print(f"    ERROR: {e}")

    # 1C: GEX data
    print("\n  1C. GEX DATA")
    print("  " + "-" * 60)
    try:
        gex = db.audit_gex_data()
        for table, info in gex.items():
            if isinstance(info, dict):
                print(f"    {table}: {info['min_date']} → {info['max_date']}, {info['rows']:,} rows, {info['days']} days")
            else:
                print(f"    {table}: {info}")
    except Exception as e:
        print(f"    ERROR: {e}")

    # 1D: Price data
    print("\n  1D. UNDERLYING PRICE DATA")
    print("  " + "-" * 60)
    try:
        prices = db.audit_price_data()
        for source, info in prices.items():
            if isinstance(info, dict):
                print(f"    {source}: {info}")
            else:
                print(f"    {source}: {info}")
    except Exception as e:
        print(f"    ERROR: {e}")

    # Summary assessment
    print("\n  " + "=" * 60)
    print("  ASSESSMENT")
    print("  " + "=" * 60)
    print("  Run this script with database access to see full findings.")
    print("  Key questions to answer:")
    print("    - Is there options data with DTE 30-45 for SPX/SPY?")
    print("    - Do we have delta data for strike selection?")
    print("    - Are bid/ask spreads populated for credit calculation?")
    print("    - What date range is covered?")
    print("    - Are there data gaps?")
    print("=" * 80)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Monthly Iron Condor Backtester for SPX & SPY",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run data audit first
  python backtest/monthly_iron_condor.py --audit

  # Backtest SPX with defaults (10-delta, $25 wings, 50% profit target)
  python backtest/monthly_iron_condor.py --ticker SPX

  # Backtest SPY with custom parameters
  python backtest/monthly_iron_condor.py --ticker SPY --delta 0.15 --width 5 --profit-target 75

  # Hold to expiration (no early exits)
  python backtest/monthly_iron_condor.py --ticker SPX --hold-to-exp

  # Export results
  python backtest/monthly_iron_condor.py --ticker SPX --export
        """
    )

    parser.add_argument('--audit', action='store_true', help='Run Phase 1 data audit')
    parser.add_argument('--ticker', default='SPX', help='Underlying: SPX or SPY (default: SPX)')
    parser.add_argument('--start', default='2021-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2025-12-31', help='End date YYYY-MM-DD')
    parser.add_argument('--capital', type=float, default=100_000, help='Initial capital (default: $100,000)')
    parser.add_argument('--delta', type=float, default=0.10, help='Short strike delta (default: 0.10)')
    parser.add_argument('--pct-otm', type=float, default=5.0, help='Pct OTM fallback (default: 5.0)')
    parser.add_argument('--width', type=float, help='Wing width (default: $25 SPX, $5 SPY)')
    parser.add_argument('--profit-target', type=float, default=50.0, help='Profit target %% of credit (default: 50)')
    parser.add_argument('--stop-loss', type=float, default=200.0, help='Stop loss %% of credit (default: 200)')
    parser.add_argument('--dte-exit', type=int, default=5, help='Close at this DTE (default: 5)')
    parser.add_argument('--hold-to-exp', action='store_true', help='Hold to expiration (no early exit)')
    parser.add_argument('--contracts', type=int, default=1, help='Contracts per trade (default: 1)')
    parser.add_argument('--dte-min', type=int, default=30, help='Min DTE at entry (default: 30)')
    parser.add_argument('--dte-max', type=int, default=45, help='Max DTE at entry (default: 45)')
    parser.add_argument('--min-credit', type=float, default=0.50, help='Min IC credit to enter (default: $0.50)')
    parser.add_argument('--export', action='store_true', default=True, help='Export trades CSV, results JSON, equity curve')
    parser.add_argument('--no-export', action='store_true', help='Skip CSV/JSON export')

    # Collateral management
    parser.add_argument('--max-utilization', type=float, default=80.0,
                        help='Max %% of equity deployable as margin (default: 80)')
    parser.add_argument('--max-risk-per-trade', type=float, default=25.0,
                        help='Max %% of equity at risk per trade (default: 25)')
    parser.add_argument('--dynamic-sizing', action='store_true', default=True,
                        help='Dynamically size contracts based on available capital (default: on)')
    parser.add_argument('--no-dynamic-sizing', action='store_true',
                        help='Use fixed contract count (--contracts)')
    parser.add_argument('--max-positions', type=int, default=2,
                        help='Max concurrent positions, 0=unlimited (default: 2)')

    # VIX filters
    parser.add_argument('--max-vix', type=float, default=25.0,
                        help='Skip entry when VIX above this (default: 25)')
    parser.add_argument('--min-vix', type=float, default=13.0,
                        help='Skip entry when VIX below this (default: 13)')
    parser.add_argument('--no-vix-filter', action='store_true',
                        help='Disable VIX entry filter')

    # Stop-loss gap handling
    parser.add_argument('--no-sl-gap-cap', action='store_true',
                        help='Disable SL gap capping (use raw gapped price)')
    parser.add_argument('--sl-gap-slippage', type=float, default=10.0,
                        help='Extra %% slippage on gap SL exits (default: 10)')

    # DTE mode
    parser.add_argument('--dte-mode', default='monthly', choices=['monthly', 'short', 'weekly'],
                        help='DTE strategy: monthly (30-45 DTE), short (0-3 DTE), or weekly (5-7 DTE)')
    parser.add_argument('--short-dte', type=int, default=0, choices=[0, 1, 2, 3],
                        help='Target DTE for short mode (default: 0)')
    parser.add_argument('--weekly-dte-min', type=int, default=5,
                        help='Min DTE for weekly mode (default: 5)')
    parser.add_argument('--weekly-dte-max', type=int, default=7,
                        help='Max DTE for weekly mode (default: 7)')
    parser.add_argument('--day-trade', dest='day_trade', action='store_true', default=True,
                        help='Day trade mode: enter and exit same day (default: True)')
    parser.add_argument('--no-day-trade', dest='day_trade', action='store_false',
                        help='Hold positions until expiration/SL/PT (multi-day monitoring)')

    args = parser.parse_args()

    if args.audit:
        run_data_audit()
        return

    # Build config
    is_dynamic = args.dynamic_sizing and not args.no_dynamic_sizing

    # For short DTE modes, adjust defaults
    dte_mode = args.dte_mode
    short_dte = args.short_dte
    dte_exit = args.dte_exit
    hold_to_exp = args.hold_to_exp
    min_credit = args.min_credit

    if dte_mode == "short":
        # For 0DTE, always hold to expiration (no DTE exit makes sense)
        if short_dte == 0:
            hold_to_exp = True
            dte_exit = 0
        # For 1-3 DTE, reduce min credit (shorter duration = less premium)
        if min_credit == 0.50:
            min_credit = 0.20
    elif dte_mode == "weekly":
        # Weekly ICs (5-7 DTE): reduce min credit, lower DTE exit
        if min_credit == 0.50:
            min_credit = 0.30
        if dte_exit == 5:
            dte_exit = 1  # Exit at 1 DTE for weeklies

    config = MonthlyICConfig(
        ticker=args.ticker.upper(),
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        short_delta=args.delta,
        pct_otm=args.pct_otm,
        profit_target_pct=args.profit_target,
        stop_loss_pct=args.stop_loss,
        dte_exit=dte_exit,
        hold_to_expiration=hold_to_exp,
        contracts=args.contracts,
        target_dte_min=args.dte_min,
        target_dte_max=args.dte_max,
        min_credit=min_credit,
        max_capital_utilization=args.max_utilization,
        max_risk_per_trade_pct=args.max_risk_per_trade,
        dynamic_sizing=is_dynamic,
        max_concurrent_positions=args.max_positions,
        max_vix=args.max_vix if not args.no_vix_filter else 999.0,
        min_vix=args.min_vix if not args.no_vix_filter else 0.0,
        sl_gap_cap=not args.no_sl_gap_cap,
        sl_gap_slippage_pct=args.sl_gap_slippage,
        dte_mode=dte_mode,
        short_dte_target=short_dte,
        weekly_dte_min=args.weekly_dte_min,
        weekly_dte_max=args.weekly_dte_max,
        day_trade=args.day_trade,
    )

    # Override wing width if specified
    if args.width is not None:
        if config.ticker in ("SPX", "SPXW"):
            config.wing_width_spx = args.width
        else:
            config.wing_width_spy = args.width

    # Run backtest
    backtester = MonthlyICBacktester(config)
    results = backtester.run()

    # Export (default on, use --no-export to skip)
    if args.export and not args.no_export:
        capital_label = f"{int(args.capital/1000)}k"
        if dte_mode == "short":
            dte_label = f"{short_dte}dte"
        elif dte_mode == "weekly":
            dte_label = "weekly"
        else:
            dte_label = "monthly"
        util_label = f"util{int(args.max_utilization)}"
        risk_label = f"risk{int(args.max_risk_per_trade)}"
        base = f"backtest/results/{args.ticker.upper()}_{dte_label}_ic"
        suffix = f"{capital_label}_{util_label}_{risk_label}_{args.start}_{args.end}"
        backtester.export_trades_csv(f"{base}_trades_{suffix}.csv")
        backtester.export_results_json(results, f"{base}_results_{suffix}.json")
        backtester.export_equity_curve_csv(results, f"{base}_equity_{suffix}.csv")

    # Always save to database (persists across deploys)
    if backtester.trades:
        try:
            backtester.db.save_results(backtester.config, results, backtester.trades)
        except Exception as e:
            logger.error(f"Failed to save results to database: {e}")

    # Cleanup DB connections after all exports and saves are done
    backtester.db.close()


if __name__ == "__main__":
    main()
