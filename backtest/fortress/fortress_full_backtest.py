#!/usr/bin/env python3
"""
FORTRESS Full Realistic Backtest Engine
========================================
Implements the 8-phase profitability proof framework:
  Phase 0: Data validation
  Phase 1: Single trade validation
  Phase 2: Baseline backtest (no filters, no optimization)
  Phase 3: Filter testing (FOMC, CPI, NFP, VIX spike, DOW)
  Phase 4: Exit optimization (profit target x stop loss grid)
  Phase 5: Strike selection comparison (delta, SD, OTM%, ATR)
  Phase 6: Walk-forward validation
  Phase 7: Monte Carlo stress test
  Phase 8: Final 25-stat scorecard

Defaults match production run_backtest.py:
  - SD-based strike selection (1.2x multiplier)
  - $5 wide wings, 3 trading day DTE
  - 15% risk per trade, $100K capital
  - 50% profit target, VIX > 50 filter
  - Slippage: $0.01/leg (entry via net_credit, exit via exit_debit)
  - Commission: $0.65/contract x 8 transactions (scales by contracts)
  - Stop loss logic with intermediate-day MTM
  - Economic event calendar filtering
  - Multiple exit strategy grid testing

Usage:
    python backtest/fortress/fortress_full_backtest.py --phase 2
    python backtest/fortress/fortress_full_backtest.py --phase 3
    python backtest/fortress/fortress_full_backtest.py --phase all
    python backtest/fortress/fortress_full_backtest.py --phase 4 --start-date 2020-01-01
"""

import os
import sys
import math
import argparse
import logging
import json
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pandas and numpy required. Run: pip install pandas numpy")
    sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 required. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_DB_URL = os.environ.get('ORAT_DATABASE_URL') or os.environ.get(
    'DATABASE_URL',
    'postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest'
)


# ============================================================================
# ECONOMIC EVENT CALENDAR
# ============================================================================

# FOMC announcement dates (2020-2025)
FOMC_DATES = [
    # 2020
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
    "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    # 2021
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
    "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    # 2022
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
    "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    # 2023
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-17",
]

# CPI release dates (2020-2025) - typically 2nd week of month
CPI_DATES = [
    # 2020
    "2020-01-14", "2020-02-13", "2020-03-11", "2020-04-10", "2020-05-12",
    "2020-06-10", "2020-07-14", "2020-08-12", "2020-09-11", "2020-10-13",
    "2020-11-12", "2020-12-10",
    # 2021
    "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13", "2021-05-12",
    "2021-06-10", "2021-07-13", "2021-08-11", "2021-09-14", "2021-10-13",
    "2021-11-10", "2021-12-10",
    # 2022
    "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11",
    "2022-06-10", "2022-07-13", "2022-08-10", "2022-09-13", "2022-10-13",
    "2022-11-10", "2022-12-13",
    # 2023
    "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12", "2023-05-10",
    "2023-06-13", "2023-07-12", "2023-08-10", "2023-09-13", "2023-10-12",
    "2023-11-14", "2023-12-12",
    # 2024
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15",
    "2024-06-12", "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10",
    "2024-11-13", "2024-12-11",
    # 2025
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13",
    "2025-06-11", "2025-07-15", "2025-08-12", "2025-09-10", "2025-10-14",
    "2025-11-12", "2025-12-10",
]

# NFP release dates (2020-2025) - typically 1st Friday of month
NFP_DATES = [
    # 2020
    "2020-01-10", "2020-02-07", "2020-03-06", "2020-04-03", "2020-05-08",
    "2020-06-05", "2020-07-02", "2020-08-07", "2020-09-04", "2020-10-02",
    "2020-11-06", "2020-12-04",
    # 2021
    "2021-01-08", "2021-02-05", "2021-03-05", "2021-04-02", "2021-05-07",
    "2021-06-04", "2021-07-02", "2021-08-06", "2021-09-03", "2021-10-08",
    "2021-11-05", "2021-12-03",
    # 2022
    "2022-01-07", "2022-02-04", "2022-03-04", "2022-04-01", "2022-05-06",
    "2022-06-03", "2022-07-08", "2022-08-05", "2022-09-02", "2022-10-07",
    "2022-11-04", "2022-12-02",
    # 2023
    "2023-01-06", "2023-02-03", "2023-03-10", "2023-04-07", "2023-05-05",
    "2023-06-02", "2023-07-07", "2023-08-04", "2023-09-01", "2023-10-06",
    "2023-11-03", "2023-12-08",
    # 2024
    "2024-01-05", "2024-02-02", "2024-03-08", "2024-04-05", "2024-05-03",
    "2024-06-07", "2024-07-05", "2024-08-02", "2024-09-06", "2024-10-04",
    "2024-11-01", "2024-12-06",
    # 2025
    "2025-01-10", "2025-02-07", "2025-03-07", "2025-04-04", "2025-05-02",
    "2025-06-06", "2025-07-03", "2025-08-01", "2025-09-05", "2025-10-03",
    "2025-11-07", "2025-12-05",
]

# Quad witching dates (3rd Friday of March, June, September, December)
QUAD_WITCH_DATES = [
    "2020-03-20", "2020-06-19", "2020-09-18", "2020-12-18",
    "2021-03-19", "2021-06-18", "2021-09-17", "2021-12-17",
    "2022-03-18", "2022-06-17", "2022-09-16", "2022-12-16",
    "2023-03-17", "2023-06-16", "2023-09-15", "2023-12-15",
    "2024-03-15", "2024-06-21", "2024-09-20", "2024-12-20",
    "2025-03-21", "2025-06-20", "2025-09-19", "2025-12-19",
]


def build_event_calendar() -> Dict[str, set]:
    """Build sets of event dates for quick lookup."""
    def parse_dates(date_strings):
        result = set()
        for ds in date_strings:
            try:
                result.add(date.fromisoformat(ds))
            except ValueError:
                pass
        return result

    fomc_set = parse_dates(FOMC_DATES)
    # Also add day-after FOMC
    fomc_plus1 = set()
    for d in fomc_set:
        fomc_plus1.add(d + timedelta(days=1))

    return {
        'fomc': fomc_set,
        'fomc_plus1': fomc_plus1,
        'cpi': parse_dates(CPI_DATES),
        'nfp': parse_dates(NFP_DATES),
        'quad_witch': parse_dates(QUAD_WITCH_DATES),
    }


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class RealisticConfig:
    """Full realistic backtest configuration."""
    # Core
    ticker: str = 'SPY'
    initial_capital: float = 100_000
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    # Strike selection - default to SD method (matches production run_backtest.py)
    strike_method: str = 'sd'     # 'delta', 'sd', 'otm_pct', 'expected_move', 'atr'
    target_delta: float = 0.16    # For delta method
    sd_multiplier: float = 1.2    # For SD method (production: 1.2 minimum floor)
    otm_pct: float = 1.0          # For OTM% method (% from spot)
    atr_multiplier: float = 1.0   # For ATR method

    # Structure - matches production run_backtest.py
    spread_width: float = 5.0     # $5 wide wings (production)
    min_dte_trading_days: int = 3  # 3 trading days to expiration (production)

    # Position sizing - matches production run_backtest.py
    max_risk_per_trade: float = 200.0  # Fallback if risk_per_trade_pct = 0
    max_contracts: int = 75
    risk_per_trade_pct: float = 15.0   # 15% of capital (production)

    # Costs (CRITICAL for realism)
    slippage_per_leg: float = 0.01     # $0.01 per leg
    num_legs: int = 4                   # IC = 4 legs
    commission_per_contract: float = 0.65  # $0.65 per contract
    num_transactions: int = 8           # 4 open + 4 close

    # Exit rules - matches production run_backtest.py
    profit_target_pct: float = 50.0    # Take profit at 50% of credit (production)
    stop_loss_multiplier: float = 0.0  # 0 = no stop loss (baseline)
    time_exit_before_exp: bool = False  # Close EOD before expiration if profitable

    # Filters - matches production run_backtest.py
    max_vix: float = 50.0              # VIX > 50 blocks trading (production)
    vix_spike_threshold: float = 0.0   # 0 = no spike filter
    skip_fomc: bool = False
    skip_fomc_next_day: bool = False
    skip_cpi: bool = False
    skip_nfp: bool = False
    skip_quad_witch: bool = False
    skip_days_of_week: List[int] = field(default_factory=list)  # 0=Mon, 4=Fri
    min_iv_rank: float = 0.0           # 0 = no IV rank filter

    # Pricing
    use_mid_price: bool = False        # False = bid/ask realistic
    min_credit: float = 0.10           # Minimum credit to take trade (production)
    max_concurrent: int = 1            # 1 position at a time

    @property
    def slippage_per_contract(self) -> float:
        """Total slippage per contract (all legs combined)."""
        return self.slippage_per_leg * self.num_legs

    @property
    def commission_per_trade(self) -> float:
        """Total commission per trade (open + close)."""
        return self.commission_per_contract * self.num_transactions

    def cost_for_trade(self, contracts: int) -> float:
        """Total transaction costs for a trade (commission only).

        Slippage is handled separately via net_credit (entry) and exit_debit (exit),
        so this returns ONLY commission to avoid double-counting slippage.
        Commission scales per contract: $0.65/contract * 8 transactions * N contracts.
        """
        commission = self.commission_per_contract * self.num_transactions * contracts
        return commission


# ============================================================================
# TRADE DATA CLASS
# ============================================================================

@dataclass
class Trade:
    """A single IC trade with full cost tracking."""
    entry_date: date
    expiration_date: date
    entry_dte: int
    spot_at_entry: float
    vix_at_entry: float
    expected_move: float

    # Strikes
    short_put: float
    long_put: float
    short_call: float
    long_call: float
    strike_method: str = ''

    # Entry pricing (per contract, before slippage)
    put_spread_credit: float = 0.0
    call_spread_credit: float = 0.0
    total_credit: float = 0.0         # Raw credit per contract
    net_credit: float = 0.0           # After slippage per contract
    contracts: int = 1
    max_risk_per_contract: float = 0.0

    # Costs
    slippage_total: float = 0.0
    commission_total: float = 0.0

    # Exit
    exit_date: Optional[date] = None
    exit_reason: str = ''
    exit_debit: float = 0.0           # What we paid to close per contract
    spot_at_exit: float = 0.0

    # P&L
    gross_pnl: float = 0.0           # Before costs
    realized_pnl: float = 0.0        # After all costs

    # Context
    gex_regime: str = ''
    call_wall: float = 0.0
    put_wall: float = 0.0
    delta_at_short_put: float = 0.0
    delta_at_short_call: float = 0.0

    @property
    def is_win(self) -> bool:
        return self.realized_pnl > 0


# ============================================================================
# DATABASE LOADER (extended from run_backtest.py)
# ============================================================================

class DataLoader:
    """Loads data from PostgreSQL with caching."""

    def __init__(self, db_url: str = DEFAULT_DB_URL):
        self.db_url = db_url
        self._conn = None
        self._chain_cache: Dict[str, pd.DataFrame] = {}
        self._price_cache: Dict[date, float] = {}

    def connect(self):
        logger.info("Connecting to database...")
        self._conn = psycopg2.connect(self.db_url)
        logger.info("Connected successfully")

    def close(self):
        if self._conn:
            self._conn.close()

    def load_trading_calendar(self, ticker: str = 'SPY') -> List[date]:
        query = """
            SELECT DISTINCT trade_date FROM underlying_prices
            WHERE symbol = %s ORDER BY trade_date
        """
        df = pd.read_sql(query, self._conn, params=(ticker,))
        if df.empty:
            query = """
                SELECT DISTINCT trade_date FROM orat_options_eod
                WHERE ticker = %s ORDER BY trade_date
            """
            df = pd.read_sql(query, self._conn, params=(ticker,))
        return sorted(df['trade_date'].tolist())

    def load_underlying_prices(self, ticker: str = 'SPY') -> pd.DataFrame:
        query = """
            SELECT trade_date, open, high, low, close
            FROM underlying_prices WHERE symbol = %s ORDER BY trade_date
        """
        df = pd.read_sql(query, self._conn, params=(ticker,))
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        return df.set_index('trade_date')

    def load_vix_history(self) -> pd.DataFrame:
        query = "SELECT trade_date, open, high, low, close FROM vix_history ORDER BY trade_date"
        df = pd.read_sql(query, self._conn)
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        return df.set_index('trade_date')

    def load_gex_daily(self, ticker: str = 'SPY') -> pd.DataFrame:
        query = """
            SELECT trade_date, call_wall, put_wall, flip_point, net_gamma,
                   gamma_imbalance_pct
            FROM gex_structure_daily WHERE symbol = %s ORDER BY trade_date
        """
        df = pd.read_sql(query, self._conn, params=(ticker,))
        if df.empty:
            query = """
                SELECT trade_date, call_wall, put_wall, flip_point,
                       net_gex as net_gamma, gex_regime
                FROM gex_daily WHERE symbol = %s ORDER BY trade_date
            """
            df = pd.read_sql(query, self._conn, params=(ticker,))
        if not df.empty:
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            df = df.set_index('trade_date')
        return df

    def load_option_chain(self, ticker: str, trade_date: date,
                          expiration_date: date) -> pd.DataFrame:
        cache_key = f"{ticker}_{trade_date}_{expiration_date}"
        if cache_key in self._chain_cache:
            return self._chain_cache[cache_key]

        query = """
            SELECT strike, option_type,
                   call_bid, call_ask, call_mid,
                   put_bid, put_ask, put_mid,
                   delta, gamma, call_iv, put_iv,
                   underlying_price, dte
            FROM orat_options_eod
            WHERE ticker = %s AND trade_date = %s AND expiration_date = %s
            ORDER BY strike
        """
        df = pd.read_sql(query, self._conn, params=(ticker, trade_date, expiration_date))
        self._chain_cache[cache_key] = df

        # Limit cache size
        if len(self._chain_cache) > 500:
            keys = list(self._chain_cache.keys())
            for k in keys[:200]:
                del self._chain_cache[k]

        return df

    def load_available_expirations(self, ticker: str, trade_date: date) -> pd.DataFrame:
        query = """
            SELECT DISTINCT expiration_date, dte FROM orat_options_eod
            WHERE ticker = %s AND trade_date = %s AND dte >= 0
            ORDER BY expiration_date
        """
        return pd.read_sql(query, self._conn, params=(ticker, trade_date))

    def get_settlement_price(self, ticker: str, settlement_date: date) -> Optional[float]:
        if settlement_date in self._price_cache:
            return self._price_cache[settlement_date]

        query = "SELECT close FROM underlying_prices WHERE symbol = %s AND trade_date = %s"
        df = pd.read_sql(query, self._conn, params=(ticker, settlement_date))
        if not df.empty and df.iloc[0]['close'] is not None:
            val = float(df.iloc[0]['close'])
            self._price_cache[settlement_date] = val
            return val

        query = """
            SELECT DISTINCT underlying_price FROM orat_options_eod
            WHERE ticker = %s AND trade_date = %s LIMIT 1
        """
        df = pd.read_sql(query, self._conn, params=(ticker, settlement_date))
        if not df.empty:
            val = float(df.iloc[0]['underlying_price'])
            self._price_cache[settlement_date] = val
            return val
        return None


# ============================================================================
# STRIKE SELECTION METHODS
# ============================================================================

def calculate_expected_move(spot: float, vix: float) -> float:
    """EM = spot * (VIX/100) / sqrt(252)"""
    return round(spot * (vix / 100) / math.sqrt(252), 2)


def select_strikes_sd(spot: float, vix: float, sd_mult: float,
                      spread_width: float) -> Dict[str, float]:
    """SD-based: spot +/- (sd_mult * EM)."""
    em = calculate_expected_move(spot, vix)
    min_em = spot * 0.005
    effective_em = max(em, min_em)

    short_put = math.floor(spot - sd_mult * effective_em)
    short_call = math.ceil(spot + sd_mult * effective_em)
    return {
        'short_put': short_put, 'long_put': short_put - spread_width,
        'short_call': short_call, 'long_call': short_call + spread_width,
    }


def select_strikes_delta(chain: pd.DataFrame, target_delta: float,
                         spread_width: float, spot: float) -> Optional[Dict[str, float]]:
    """Delta-based: find strikes nearest to target delta."""
    if chain.empty or 'delta' not in chain.columns:
        return None

    # Put side: find strike where put delta is closest to -target_delta
    # In ORAT, delta for puts is negative
    puts = chain[chain['strike'] < spot].copy()
    calls = chain[chain['strike'] > spot].copy()

    if puts.empty or calls.empty:
        return None

    # For puts, delta should be around -0.16 for 16-delta
    puts['put_delta_abs'] = puts['delta'].abs()
    puts_sorted = puts.iloc[(puts['put_delta_abs'] - target_delta).abs().argsort()]
    if puts_sorted.empty:
        return None
    short_put = float(puts_sorted.iloc[0]['strike'])

    # For calls, delta should be around +0.16
    calls_sorted = calls.iloc[(calls['delta'].abs() - target_delta).abs().argsort()]
    if calls_sorted.empty:
        return None
    short_call = float(calls_sorted.iloc[0]['strike'])

    # Ensure strikes are on correct side
    if short_put >= spot or short_call <= spot:
        return None

    return {
        'short_put': short_put, 'long_put': short_put - spread_width,
        'short_call': short_call, 'long_call': short_call + spread_width,
    }


def select_strikes_otm_pct(spot: float, otm_pct: float,
                            spread_width: float) -> Dict[str, float]:
    """OTM percentage: strikes at fixed % from spot."""
    offset = spot * (otm_pct / 100)
    short_put = math.floor(spot - offset)
    short_call = math.ceil(spot + offset)
    return {
        'short_put': short_put, 'long_put': short_put - spread_width,
        'short_call': short_call, 'long_call': short_call + spread_width,
    }


def select_strikes_atr(spot: float, atr14: float, atr_mult: float,
                        spread_width: float) -> Dict[str, float]:
    """ATR-based: strikes at spot +/- (atr_mult * ATR14)."""
    offset = atr_mult * atr14
    short_put = math.floor(spot - offset)
    short_call = math.ceil(spot + offset)
    return {
        'short_put': short_put, 'long_put': short_put - spread_width,
        'short_call': short_call, 'long_call': short_call + spread_width,
    }


def select_strikes_expected_move(spot: float, chain: pd.DataFrame,
                                  spread_width: float) -> Optional[Dict[str, float]]:
    """Expected move from ATM straddle implied vol."""
    if chain.empty:
        return None
    # Find ATM strike
    atm_idx = (chain['strike'] - spot).abs().idxmin()
    atm = chain.loc[atm_idx]
    call_iv = float(atm.get('call_iv', 0) or 0)
    put_iv = float(atm.get('put_iv', 0) or 0)
    avg_iv = (call_iv + put_iv) / 2
    if avg_iv <= 0:
        return None
    dte = float(atm.get('dte', 2) or 2)
    em = spot * avg_iv * math.sqrt(dte / 365)
    short_put = math.floor(spot - em)
    short_call = math.ceil(spot + em)
    return {
        'short_put': short_put, 'long_put': short_put - spread_width,
        'short_call': short_call, 'long_call': short_call + spread_width,
    }


# ============================================================================
# IC PRICING & SETTLEMENT
# ============================================================================

def price_iron_condor(chain: pd.DataFrame, strikes: Dict[str, float],
                      use_mid: bool = False) -> Optional[Dict]:
    """Price an IC from ORAT chain. Returns credit details or None."""
    def get_row(strike_val):
        rows = chain[chain['strike'] == strike_val]
        return rows.iloc[0] if not rows.empty else None

    sp = get_row(strikes['short_put'])
    lp = get_row(strikes['long_put'])
    sc = get_row(strikes['short_call'])
    lc = get_row(strikes['long_call'])

    if any(x is None for x in [sp, lp, sc, lc]):
        return None

    if use_mid:
        put_credit = float(sp['put_mid'] or 0) - float(lp['put_mid'] or 0)
        call_credit = float(sc['call_mid'] or 0) - float(lc['call_mid'] or 0)
    else:
        put_credit = float(sp['put_bid'] or 0) - float(lp['put_ask'] or 0)
        call_credit = float(sc['call_bid'] or 0) - float(lc['call_ask'] or 0)

    put_credit = max(0, put_credit)
    call_credit = max(0, call_credit)
    total_credit = put_credit + call_credit

    # Get deltas for tracking
    sp_delta = float(sp.get('delta', 0) or 0)
    sc_delta = float(sc.get('delta', 0) or 0)

    return {
        'put_credit': round(put_credit, 4),
        'call_credit': round(call_credit, 4),
        'total_credit': round(total_credit, 4),
        'underlying_price': float(sp['underlying_price']),
        'short_put_delta': sp_delta,
        'short_call_delta': sc_delta,
    }


def calculate_ic_exit_value(chain: pd.DataFrame, strikes: Dict[str, float],
                            use_mid: bool = False) -> Optional[float]:
    """Calculate current debit to close the IC."""
    def get_row(strike_val):
        rows = chain[chain['strike'] == strike_val]
        return rows.iloc[0] if not rows.empty else None

    sp = get_row(strikes['short_put'])
    lp = get_row(strikes['long_put'])
    sc = get_row(strikes['short_call'])
    lc = get_row(strikes['long_call'])

    if any(x is None for x in [sp, lp, sc, lc]):
        return None

    if use_mid:
        put_cost = float(sp['put_mid'] or 0) - float(lp['put_mid'] or 0)
        call_cost = float(sc['call_mid'] or 0) - float(lc['call_mid'] or 0)
    else:
        put_cost = float(sp['put_ask'] or 0) - float(lp['put_bid'] or 0)
        call_cost = float(sc['call_ask'] or 0) - float(lc['call_bid'] or 0)

    return round(max(0, put_cost + call_cost), 4)


def calculate_settlement_pnl(spot_close: float, strikes: Dict[str, float],
                             entry_credit: float) -> Tuple[float, str]:
    """Calculate per-contract P&L at expiration settlement."""
    sp, lp = strikes['short_put'], strikes['long_put']
    sc, lc = strikes['short_call'], strikes['long_call']

    put_loss = max(0, sp - spot_close) - max(0, lp - spot_close)
    call_loss = max(0, spot_close - sc) - max(0, spot_close - lc)
    total_loss = put_loss + call_loss
    pnl = entry_credit - total_loss

    if total_loss == 0:
        reason = "MAX_PROFIT"
    elif put_loss > 0 and call_loss > 0:
        reason = "BOTH_BREACHED"
    elif put_loss > 0:
        reason = "PUT_BREACHED"
    elif call_loss > 0:
        reason = "CALL_BREACHED"
    else:
        reason = "EXPIRED_OTM"

    return round(pnl, 4), reason


# ============================================================================
# STATISTICS ENGINE
# ============================================================================

def compute_full_stats(trades: List[Trade], initial_capital: float,
                       label: str = "") -> Dict[str, Any]:
    """Compute the full 25-stat scorecard plus extras."""
    if not trades:
        return {'label': label, 'total_trades': 0, 'error': 'No trades'}

    pnls = np.array([t.realized_pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    total_trades = len(trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total_trades if total_trades else 0
    total_pnl = float(pnls.sum())
    avg_pnl = float(pnls.mean())
    median_pnl = float(np.median(pnls))
    avg_win = float(wins.mean()) if len(wins) else 0
    avg_loss = float(np.abs(losses).mean()) if len(losses) else 0
    gross_profit = float(wins.sum()) if len(wins) else 0
    gross_loss = float(np.abs(losses.sum())) if len(losses) else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # Equity curve
    equity = np.zeros(total_trades + 1)
    equity[0] = initial_capital
    for i, t in enumerate(trades):
        equity[i + 1] = equity[i] + t.realized_pnl

    # Drawdown
    rolling_max = np.maximum.accumulate(equity)
    drawdown = equity - rolling_max
    max_dd_dollar = float(np.abs(drawdown).max())
    dd_pct = drawdown / np.where(rolling_max > 0, rolling_max, 1)
    max_dd_pct = float(np.abs(dd_pct).max())

    # Max drawdown duration (in trades)
    in_dd = drawdown < 0
    max_dd_duration = 0
    current_dd_len = 0
    for v in in_dd:
        if v:
            current_dd_len += 1
            max_dd_duration = max(max_dd_duration, current_dd_len)
        else:
            current_dd_len = 0

    # Consecutive losses
    max_consec_losses = 0
    current_streak = 0
    for p in pnls:
        if p <= 0:
            current_streak += 1
            max_consec_losses = max(max_consec_losses, current_streak)
        else:
            current_streak = 0

    # Largest single loss
    largest_loss = float(pnls.min()) if len(pnls) else 0

    # Annualized returns (approximate using trade frequency)
    if total_trades >= 2:
        first_date = trades[0].entry_date
        last_date = trades[-1].entry_date
        days_span = (last_date - first_date).days
        years = days_span / 365.25 if days_span > 0 else 1
        ending_equity = equity[-1]
        annualized_return = (ending_equity / initial_capital) ** (1 / years) - 1 if years > 0 else 0
    else:
        annualized_return = 0
        years = 1

    # Daily-ish returns (per-trade returns as proxy)
    trade_returns = pnls / initial_capital
    ann_vol = float(trade_returns.std() * np.sqrt(252 / max(1, total_trades / max(1, years))))
    risk_free = 0.05

    sharpe = (annualized_return - risk_free) / ann_vol if ann_vol > 0 else 0

    # Sortino
    downside = trade_returns[trade_returns < 0]
    downside_vol = float(downside.std() * np.sqrt(252 / max(1, total_trades / max(1, years)))) if len(downside) > 0 else 0.001
    sortino = (annualized_return - risk_free) / downside_vol if downside_vol > 0 else 0

    # Calmar
    calmar = annualized_return / max_dd_pct if max_dd_pct > 0 else 0

    # Statistical significance
    t_stat = 0
    p_value = 1.0
    if HAS_SCIPY and total_trades >= 5:
        t_stat, p_value = scipy_stats.ttest_1samp(pnls, 0)
        t_stat = float(t_stat)
        p_value = float(p_value)

    # Skewness & kurtosis
    skewness = float(scipy_stats.skew(pnls)) if HAS_SCIPY else 0
    kurt = float(scipy_stats.kurtosis(pnls)) if HAS_SCIPY else 0

    # VaR
    var_95 = float(np.percentile(pnls, 5))
    cvar_95 = float(pnls[pnls <= var_95].mean()) if len(pnls[pnls <= var_95]) > 0 else var_95

    # Return on capital
    return_on_capital = total_pnl / initial_capital

    result = {
        'label': label,
        # Category 1: Does it make money?
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
        'median_pnl': median_pnl,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'expected_value': expected_value,
        'annualized_return': annualized_return,
        'return_on_capital': return_on_capital,
        # Category 2: Is the edge real?
        'total_trades': total_trades,
        't_stat': t_stat,
        'p_value': p_value,
        'sharpe': sharpe,
        'sortino': sortino,
        'skewness': skewness,
        'kurtosis': kurt,
        # Category 3: Can you survive bad times?
        'max_dd_dollar': max_dd_dollar,
        'max_dd_pct': max_dd_pct,
        'max_dd_duration': max_dd_duration,
        'max_consec_losses': max_consec_losses,
        'largest_loss': largest_loss,
        'calmar': calmar,
        'var_95': var_95,
        'cvar_95': cvar_95,
        # Extras
        'win_count': win_count,
        'loss_count': loss_count,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'ending_equity': float(equity[-1]),
        'equity_curve': equity.tolist(),
    }

    return result


def print_scorecard(stats: Dict[str, Any]):
    """Print the 25-stat profitability scorecard."""
    if stats.get('total_trades', 0) == 0:
        print(f"  No trades for: {stats.get('label', '?')}")
        return

    label = stats.get('label', 'FORTRESS')
    cap = stats.get('ending_equity', 0) - stats.get('total_pnl', 0)  # starting capital
    if cap <= 0:
        cap = 50000

    print(f"\n{'='*72}")
    print(f"  25-STAT PROFITABILITY SCORECARD: {label}")
    print(f"{'='*72}")

    def check(val, threshold, op='>'):
        if op == '>': return 'PASS' if val > threshold else 'FAIL'
        if op == '>=': return 'PASS' if val >= threshold else 'FAIL'
        if op == '<': return 'PASS' if val < threshold else 'FAIL'
        return '?'

    print(f"\n  CATEGORY 1: DOES IT MAKE MONEY?")
    print(f"  {'#':>3} {'Stat':<30} {'Target':>12} {'Result':>12} {'Pass?':>6}")
    print(f"  {'-'*3} {'-'*30} {'-'*12} {'-'*12} {'-'*6}")
    rows_1 = [
        (1, "Total Net P&L", "> $0", f"${stats['total_pnl']:,.0f}", check(stats['total_pnl'], 0)),
        (2, "Avg Trade P&L", "> $5", f"${stats['avg_pnl']:,.2f}", check(stats['avg_pnl'], 5)),
        (3, "Median Trade P&L", "> $0", f"${stats['median_pnl']:,.2f}", check(stats['median_pnl'], 0)),
        (4, "Win Rate", "> 55%", f"{stats['win_rate']*100:.1f}%", check(stats['win_rate'], 0.55)),
        (5, "Profit Factor", "> 1.3", f"{stats['profit_factor']:.2f}", check(stats['profit_factor'], 1.3)),
        (6, "Expected Value/Trade", "> $3", f"${stats['expected_value']:,.2f}", check(stats['expected_value'], 3)),
        (7, "Annualized Return", "> 15%", f"{stats['annualized_return']*100:.1f}%", check(stats['annualized_return'], 0.15)),
    ]
    passes = 0
    for num, name, target, result, pf in rows_1:
        print(f"  {num:>3} {name:<30} {target:>12} {result:>12} {pf:>6}")
        if pf == 'PASS': passes += 1

    print(f"\n  CATEGORY 2: IS THE EDGE REAL?")
    print(f"  {'#':>3} {'Stat':<30} {'Target':>12} {'Result':>12} {'Pass?':>6}")
    print(f"  {'-'*3} {'-'*30} {'-'*12} {'-'*12} {'-'*6}")
    rows_2 = [
        (8, "Sample Size", "> 200", f"{stats['total_trades']}", check(stats['total_trades'], 200)),
        (9, "t-Statistic", "> 2.0", f"{stats['t_stat']:.2f}", check(stats['t_stat'], 2.0)),
        (10, "Sharpe Ratio", "> 1.0", f"{stats['sharpe']:.2f}", check(stats['sharpe'], 1.0)),
        (11, "Sortino Ratio", "> 1.5", f"{stats['sortino']:.2f}", check(stats['sortino'], 1.5)),
        (14, "P&L Skewness", "> -0.5", f"{stats['skewness']:.2f}", check(stats['skewness'], -0.5)),
    ]
    for num, name, target, result, pf in rows_2:
        print(f"  {num:>3} {name:<30} {target:>12} {result:>12} {pf:>6}")
        if pf == 'PASS': passes += 1

    print(f"\n  CATEGORY 3: SURVIVE THE BAD TIMES?")
    print(f"  {'#':>3} {'Stat':<30} {'Target':>12} {'Result':>12} {'Pass?':>6}")
    print(f"  {'-'*3} {'-'*30} {'-'*12} {'-'*12} {'-'*6}")
    rows_3 = [
        (15, "Max Drawdown ($)", f"< {20}% cap", f"${stats['max_dd_dollar']:,.0f}", check(stats['max_dd_pct'], 0.20, '<')),
        (16, "Max DD Duration (trades)", "< 60", f"{stats['max_dd_duration']}", check(stats['max_dd_duration'], 60, '<')),
        (17, "Max Consecutive Losses", "< 8", f"{stats['max_consec_losses']}", check(stats['max_consec_losses'], 8, '<')),
        (18, "Largest Single Loss", f"< 3% cap", f"${stats['largest_loss']:,.0f}", check(abs(stats['largest_loss']), cap * 0.03, '<')),
        (19, "Calmar Ratio", "> 1.0", f"{stats['calmar']:.2f}", check(stats['calmar'], 1.0)),
        (20, "95% VaR (per trade)", f"< 2% cap", f"${stats['var_95']:,.0f}", check(abs(stats['var_95']), cap * 0.02, '<')),
    ]
    for num, name, target, result, pf in rows_3:
        print(f"  {num:>3} {name:<30} {target:>12} {result:>12} {pf:>6}")
        if pf == 'PASS': passes += 1

    total_checks = len(rows_1) + len(rows_2) + len(rows_3)
    print(f"\n  SCORE: {passes}/{total_checks} checks passed")
    if passes >= 16:
        print(f"  VERDICT: GO LIVE")
    elif passes >= 13:
        print(f"  VERDICT: CONDITIONAL GO (deploy at 50% size)")
    elif passes >= 10:
        print(f"  VERDICT: PAPER TRADE (60 days)")
    else:
        print(f"  VERDICT: NO GO (needs redesign)")


def print_compact_stats(stats: Dict[str, Any]):
    """Print a one-line summary for grid comparisons."""
    if stats.get('total_trades', 0) == 0:
        print(f"  {stats.get('label', '?'):>30}: NO TRADES")
        return
    print(f"  {stats.get('label', ''):>30}: "
          f"N={stats['total_trades']:>4} "
          f"WR={stats['win_rate']*100:>5.1f}% "
          f"PF={stats['profit_factor']:>5.2f} "
          f"Sharpe={stats['sharpe']:>6.2f} "
          f"MaxDD={stats['max_dd_pct']*100:>5.1f}% "
          f"P&L=${stats['total_pnl']:>10,.0f}")


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class FortressRealisticBacktest:
    """Full realistic backtest engine with all phases."""

    def __init__(self, config: RealisticConfig, db_url: str = DEFAULT_DB_URL):
        self.config = config
        self.loader = DataLoader(db_url)
        self.trades: List[Trade] = []
        self.skipped_days: List[Dict] = []

        # Pre-loaded data
        self._trading_dates: List[date] = []
        self._trading_date_set: set = set()
        self._trading_date_idx: Dict[date, int] = {}
        self._vix_df: pd.DataFrame = pd.DataFrame()
        self._prices_df: pd.DataFrame = pd.DataFrame()
        self._gex_df: pd.DataFrame = pd.DataFrame()
        self._event_calendar: Dict[str, set] = {}
        self._atr_cache: Dict[date, float] = {}

    def load_data(self):
        """Load all reference data once."""
        self.loader.connect()

        logger.info("Loading trading calendar...")
        self._trading_dates = self.loader.load_trading_calendar(self.config.ticker)
        self._trading_date_set = set(self._trading_dates)
        self._trading_date_idx = {d: i for i, d in enumerate(self._trading_dates)}
        logger.info(f"  {len(self._trading_dates)} trading dates")

        logger.info("Loading VIX history...")
        self._vix_df = self.loader.load_vix_history()
        logger.info(f"  {len(self._vix_df)} VIX records")

        logger.info("Loading underlying prices...")
        self._prices_df = self.loader.load_underlying_prices(self.config.ticker)
        logger.info(f"  {len(self._prices_df)} price records")

        logger.info("Loading GEX data...")
        self._gex_df = self.loader.load_gex_daily(self.config.ticker)
        logger.info(f"  {len(self._gex_df)} GEX records")

        logger.info("Building event calendar...")
        self._event_calendar = build_event_calendar()

        # Precompute ATR14
        if not self._prices_df.empty and 'high' in self._prices_df.columns:
            self._precompute_atr()

    def _precompute_atr(self):
        """Precompute 14-day ATR for ATR-based strike selection."""
        df = self._prices_df.copy()
        if 'high' not in df.columns or 'low' not in df.columns:
            return
        df['prev_close'] = df['close'].shift(1)
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                (df['high'] - df['prev_close']).abs(),
                (df['low'] - df['prev_close']).abs()
            )
        )
        df['atr14'] = df['tr'].rolling(14).mean()
        for dt, row in df.iterrows():
            if not pd.isna(row.get('atr14', float('nan'))):
                self._atr_cache[dt] = float(row['atr14'])

    def close(self):
        self.loader.close()

    def _should_skip_event(self, trade_date: date) -> Optional[str]:
        """Check if trade_date should be skipped due to economic events."""
        ec = self._event_calendar

        if self.config.skip_fomc and trade_date in ec.get('fomc', set()):
            return 'FOMC_DAY'
        if self.config.skip_fomc_next_day and trade_date in ec.get('fomc_plus1', set()):
            return 'FOMC_NEXT_DAY'
        if self.config.skip_cpi and trade_date in ec.get('cpi', set()):
            return 'CPI_DAY'
        if self.config.skip_nfp and trade_date in ec.get('nfp', set()):
            return 'NFP_DAY'
        if self.config.skip_quad_witch and trade_date in ec.get('quad_witch', set()):
            return 'QUAD_WITCH'
        if trade_date.weekday() in self.config.skip_days_of_week:
            dow_names = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI'}
            return f'SKIP_{dow_names.get(trade_date.weekday(), "?")}'
        return None

    def _check_vix_spike(self, trade_date: date) -> bool:
        """Check if VIX spiked above threshold."""
        if self.config.vix_spike_threshold <= 0:
            return False
        idx = self._trading_date_idx.get(trade_date)
        if idx is None or idx == 0:
            return False
        prev_date = self._trading_dates[idx - 1]
        if trade_date in self._vix_df.index and prev_date in self._vix_df.index:
            today_vix = float(self._vix_df.loc[trade_date, 'close'])
            prev_vix = float(self._vix_df.loc[prev_date, 'close'])
            if prev_vix > 0:
                change_pct = (today_vix - prev_vix) / prev_vix * 100
                return change_pct > self.config.vix_spike_threshold
        return False

    def _select_strikes(self, spot: float, vix: float, chain: pd.DataFrame,
                        trade_date: date) -> Optional[Dict[str, float]]:
        """Select strikes using configured method."""
        method = self.config.strike_method
        sw = self.config.spread_width

        if method == 'delta':
            result = select_strikes_delta(chain, self.config.target_delta, sw, spot)
            if result:
                return result
            # Fallback to SD if delta data missing
            return select_strikes_sd(spot, vix, self.config.sd_multiplier, sw)

        elif method == 'sd':
            return select_strikes_sd(spot, vix, self.config.sd_multiplier, sw)

        elif method == 'otm_pct':
            return select_strikes_otm_pct(spot, self.config.otm_pct, sw)

        elif method == 'atr':
            atr = self._atr_cache.get(trade_date)
            if atr and atr > 0:
                return select_strikes_atr(spot, atr, self.config.atr_multiplier, sw)
            return select_strikes_sd(spot, vix, self.config.sd_multiplier, sw)

        elif method == 'expected_move':
            result = select_strikes_expected_move(spot, chain, sw)
            if result:
                return result
            return select_strikes_sd(spot, vix, self.config.sd_multiplier, sw)

        return select_strikes_sd(spot, vix, self.config.sd_multiplier, sw)

    def run_backtest(self) -> List[Trade]:
        """Execute the core backtest loop. Returns list of trades."""
        self.trades = []
        self.skipped_days = []
        config = self.config

        start = date.fromisoformat(config.start_date) if config.start_date else self._trading_dates[0]
        end = date.fromisoformat(config.end_date) if config.end_date else self._trading_dates[-1]
        eligible_dates = [d for d in self._trading_dates if start <= d <= end]
        logger.info(f"Backtesting {len(eligible_dates)} days: {start} -> {end}")

        open_positions: List[Trade] = []
        capital = config.initial_capital

        for day_idx, trade_date in enumerate(eligible_dates):
            if day_idx % 200 == 0 and day_idx > 0:
                cum_pnl = sum(t.realized_pnl for t in self.trades)
                logger.info(f"  Day {day_idx}/{len(eligible_dates)} ({trade_date}) "
                           f"| Trades: {len(self.trades)} | P&L: ${cum_pnl:,.0f}")

            # ---- STEP 1: Manage open positions ----
            still_open = []
            for pos in open_positions:
                closed = False
                strikes = {
                    'short_put': pos.short_put, 'long_put': pos.long_put,
                    'short_call': pos.short_call, 'long_call': pos.long_call,
                }

                # Check expiration
                if trade_date >= pos.expiration_date:
                    settle_price = self.loader.get_settlement_price(
                        config.ticker, pos.expiration_date
                    )
                    if settle_price is None:
                        settle_price = pos.spot_at_entry

                    per_contract_pnl, reason = calculate_settlement_pnl(
                        settle_price, strikes, pos.net_credit
                    )
                    pos.exit_date = pos.expiration_date
                    pos.exit_reason = reason
                    pos.spot_at_exit = settle_price
                    pos.exit_debit = pos.net_credit - per_contract_pnl
                    pos.gross_pnl = round(per_contract_pnl * pos.contracts * 100, 2)
                    pos.realized_pnl = round(pos.gross_pnl - pos.commission_total, 2)
                    self.trades.append(pos)
                    capital += pos.realized_pnl
                    closed = True

                elif trade_date > pos.entry_date:
                    # Check intermediate day exits (profit target / stop loss)
                    chain = self.loader.load_option_chain(
                        config.ticker, trade_date, pos.expiration_date
                    )
                    if not chain.empty:
                        current_value = calculate_ic_exit_value(
                            chain, strikes, config.use_mid_price
                        )
                        if current_value is not None:
                            # Add slippage to exit
                            exit_debit = current_value + config.slippage_per_contract

                            # Profit target check
                            if config.profit_target_pct > 0:
                                target_debit = pos.net_credit * (1 - config.profit_target_pct / 100)
                                if exit_debit <= target_debit:
                                    per_contract_pnl = pos.net_credit - exit_debit
                                    pos.exit_date = trade_date
                                    pos.exit_reason = "PROFIT_TARGET"
                                    pos.exit_debit = exit_debit
                                    settle = self.loader.get_settlement_price(config.ticker, trade_date)
                                    pos.spot_at_exit = settle or pos.spot_at_entry
                                    pos.gross_pnl = round(per_contract_pnl * pos.contracts * 100, 2)
                                    pos.realized_pnl = round(pos.gross_pnl - pos.commission_total, 2)
                                    self.trades.append(pos)
                                    capital += pos.realized_pnl
                                    closed = True

                            # Stop loss check
                            if not closed and config.stop_loss_multiplier > 0:
                                max_loss_debit = pos.net_credit + (pos.net_credit * config.stop_loss_multiplier)
                                if exit_debit >= max_loss_debit:
                                    per_contract_pnl = pos.net_credit - exit_debit
                                    pos.exit_date = trade_date
                                    pos.exit_reason = "STOP_LOSS"
                                    pos.exit_debit = exit_debit
                                    settle = self.loader.get_settlement_price(config.ticker, trade_date)
                                    pos.spot_at_exit = settle or pos.spot_at_entry
                                    pos.gross_pnl = round(per_contract_pnl * pos.contracts * 100, 2)
                                    pos.realized_pnl = round(pos.gross_pnl - pos.commission_total, 2)
                                    self.trades.append(pos)
                                    capital += pos.realized_pnl
                                    closed = True

                            # Time exit: close EOD before expiration if profitable
                            if not closed and config.time_exit_before_exp:
                                exp_idx = self._trading_date_idx.get(pos.expiration_date)
                                cur_idx = self._trading_date_idx.get(trade_date)
                                if exp_idx and cur_idx and exp_idx - cur_idx == 1:
                                    per_contract_pnl = pos.net_credit - exit_debit
                                    if per_contract_pnl > 0:
                                        pos.exit_date = trade_date
                                        pos.exit_reason = "TIME_EXIT_PROFITABLE"
                                        pos.exit_debit = exit_debit
                                        settle = self.loader.get_settlement_price(config.ticker, trade_date)
                                        pos.spot_at_exit = settle or pos.spot_at_entry
                                        pos.gross_pnl = round(per_contract_pnl * pos.contracts * 100, 2)
                                        pos.realized_pnl = round(pos.gross_pnl - pos.commission_total, 2)
                                        self.trades.append(pos)
                                        capital += pos.realized_pnl
                                        closed = True

                if not closed:
                    still_open.append(pos)

            open_positions = still_open

            # ---- STEP 2: Open new position? ----
            if len(open_positions) >= config.max_concurrent:
                continue

            # Event filter
            skip_reason = self._should_skip_event(trade_date)
            if skip_reason:
                self.skipped_days.append({'date': trade_date, 'reason': skip_reason})
                continue

            # VIX data
            vix_close = None
            if trade_date in self._vix_df.index:
                vix_close = float(self._vix_df.loc[trade_date, 'close'])
            if vix_close is None or pd.isna(vix_close):
                self.skipped_days.append({'date': trade_date, 'reason': 'NO_VIX'})
                continue

            # VIX max filter
            if vix_close > config.max_vix:
                self.skipped_days.append({'date': trade_date, 'reason': f'VIX>{config.max_vix}'})
                continue

            # VIX spike filter
            if self._check_vix_spike(trade_date):
                self.skipped_days.append({'date': trade_date, 'reason': 'VIX_SPIKE'})
                continue

            # Spot price
            spot = None
            if trade_date in self._prices_df.index:
                spot_val = self._prices_df.loc[trade_date, 'close']
                if isinstance(spot_val, pd.Series):
                    spot_val = spot_val.iloc[0]
                spot = float(spot_val) if spot_val is not None and not pd.isna(spot_val) else None
            if spot is None:
                spot = self.loader.get_settlement_price(config.ticker, trade_date)
            if spot is None:
                self.skipped_days.append({'date': trade_date, 'reason': 'NO_SPOT'})
                continue

            # Find target expiration
            idx = self._trading_date_idx.get(trade_date)
            if idx is None:
                continue
            target_exp_idx = idx + config.min_dte_trading_days
            if target_exp_idx >= len(self._trading_dates):
                continue
            target_expiration = self._trading_dates[target_exp_idx]

            # Load option chain
            chain = self.loader.load_option_chain(config.ticker, trade_date, target_expiration)
            if chain.empty:
                avail = self.loader.load_available_expirations(config.ticker, trade_date)
                if avail.empty:
                    self.skipped_days.append({'date': trade_date, 'reason': 'NO_OPTIONS'})
                    continue
                avail['expiration_date'] = pd.to_datetime(avail['expiration_date']).dt.date
                future = avail[avail['expiration_date'] >= target_expiration]
                if future.empty:
                    future = avail[avail['dte'] >= config.min_dte_trading_days]
                if future.empty:
                    self.skipped_days.append({'date': trade_date, 'reason': 'NO_EXPIRATION'})
                    continue
                target_expiration = future.iloc[0]['expiration_date']
                chain = self.loader.load_option_chain(config.ticker, trade_date, target_expiration)
                if chain.empty:
                    continue

            # Select strikes
            strikes = self._select_strikes(spot, vix_close, chain, trade_date)
            if strikes is None:
                self.skipped_days.append({'date': trade_date, 'reason': 'STRIKE_SELECT_FAIL'})
                continue

            # Price IC
            pricing = price_iron_condor(chain, strikes, config.use_mid_price)
            if pricing is None:
                self.skipped_days.append({
                    'date': trade_date,
                    'reason': f'STRIKES_NOT_IN_CHAIN SP={strikes["short_put"]} SC={strikes["short_call"]}'
                })
                continue

            total_credit = pricing['total_credit']
            if total_credit < config.min_credit:
                self.skipped_days.append({'date': trade_date, 'reason': f'LOW_CREDIT ${total_credit:.4f}'})
                continue

            # Apply entry slippage
            net_credit = total_credit - config.slippage_per_contract
            if net_credit <= 0:
                self.skipped_days.append({'date': trade_date, 'reason': 'NEGATIVE_NET_CREDIT'})
                continue

            # Position sizing
            max_risk_per_contract = (config.spread_width - net_credit) * 100
            if max_risk_per_contract <= 0:
                max_risk_per_contract = config.spread_width * 100

            if config.risk_per_trade_pct > 0:
                budget = capital * (config.risk_per_trade_pct / 100)
            else:
                budget = config.max_risk_per_trade

            contracts = int(budget / max_risk_per_contract)
            contracts = max(1, min(contracts, config.max_contracts))

            # Commission
            commission = config.cost_for_trade(contracts)
            slippage_dollar = config.slippage_per_contract * contracts * 100

            cal_dte = (target_expiration - trade_date).days
            em = calculate_expected_move(spot, vix_close)

            # GEX context
            gex_regime = ''
            call_wall = 0.0
            put_wall = 0.0
            if not self._gex_df.empty and trade_date in self._gex_df.index:
                row = self._gex_df.loc[trade_date]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                call_wall = float(row.get('call_wall', 0) or 0)
                put_wall = float(row.get('put_wall', 0) or 0)

            trade = Trade(
                entry_date=trade_date,
                expiration_date=target_expiration,
                entry_dte=cal_dte,
                spot_at_entry=spot,
                vix_at_entry=vix_close,
                expected_move=em,
                short_put=strikes['short_put'],
                long_put=strikes['long_put'],
                short_call=strikes['short_call'],
                long_call=strikes['long_call'],
                strike_method=config.strike_method,
                put_spread_credit=pricing['put_credit'],
                call_spread_credit=pricing['call_credit'],
                total_credit=total_credit,
                net_credit=net_credit,
                contracts=contracts,
                max_risk_per_contract=max_risk_per_contract,
                slippage_total=slippage_dollar,
                commission_total=commission,
                gex_regime=gex_regime,
                call_wall=call_wall,
                put_wall=put_wall,
                delta_at_short_put=pricing.get('short_put_delta', 0),
                delta_at_short_call=pricing.get('short_call_delta', 0),
            )
            open_positions.append(trade)

        # Close remaining at end
        for pos in open_positions:
            settle = self.loader.get_settlement_price(config.ticker, eligible_dates[-1])
            if settle:
                strikes = {
                    'short_put': pos.short_put, 'long_put': pos.long_put,
                    'short_call': pos.short_call, 'long_call': pos.long_call,
                }
                per_contract_pnl, reason = calculate_settlement_pnl(
                    settle, strikes, pos.net_credit
                )
                pos.exit_date = eligible_dates[-1]
                pos.exit_reason = f"BACKTEST_END ({reason})"
                pos.spot_at_exit = settle
                pos.gross_pnl = round(per_contract_pnl * pos.contracts * 100, 2)
                pos.realized_pnl = round(pos.gross_pnl - pos.commission_total, 2)
                self.trades.append(pos)

        logger.info(f"Backtest complete: {len(self.trades)} trades")
        return self.trades


# ============================================================================
# PHASE RUNNERS
# ============================================================================

def run_phase_0(bt: FortressRealisticBacktest):
    """Phase 0: Data validation."""
    print(f"\n{'='*72}")
    print(f"  PHASE 0: DATA ACQUISITION & VALIDATION")
    print(f"{'='*72}")

    # Trading calendar
    dates = bt._trading_dates
    print(f"\n  Trading Calendar: {len(dates)} days ({dates[0]} -> {dates[-1]})")

    # Check gaps
    gaps = 0
    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i-1]).days
        if delta > 5:  # More than a long weekend
            gaps += 1
    gap_pct = gaps / len(dates) * 100
    pf = "PASS" if gap_pct < 2 else "FAIL"
    print(f"  Calendar gaps (>5 days): {gaps} ({gap_pct:.1f}%) [{pf}]")

    # VIX coverage
    vix_dates = set(bt._vix_df.index)
    trading_set = set(dates)
    vix_coverage = len(vix_dates & trading_set) / len(trading_set) * 100
    pf = "PASS" if vix_coverage > 95 else "FAIL"
    print(f"  VIX coverage: {vix_coverage:.1f}% [{pf}]")

    # Price coverage
    price_dates = set(bt._prices_df.index)
    price_coverage = len(price_dates & trading_set) / len(trading_set) * 100
    pf = "PASS" if price_coverage > 95 else "FAIL"
    print(f"  Price coverage: {price_coverage:.1f}% [{pf}]")

    # Check 2DTE availability
    dte2_available = 0
    dte2_total = 0
    sample_dates = [d for d in dates if d >= date(2020, 1, 1)][:500]
    for d in sample_dates:
        idx = bt._trading_date_idx.get(d)
        if idx and idx + 2 < len(dates):
            dte2_total += 1
            target_exp = dates[idx + 2]
            avail = bt.loader.load_available_expirations(bt.config.ticker, d)
            if not avail.empty:
                avail['expiration_date'] = pd.to_datetime(avail['expiration_date']).dt.date
                if target_exp in avail['expiration_date'].values:
                    dte2_available += 1
    if dte2_total > 0:
        dte2_pct = dte2_available / dte2_total * 100
        pf = "PASS" if dte2_pct > 50 else "WARN"
        print(f"  2DTE expiration availability (sample): {dte2_pct:.1f}% ({dte2_available}/{dte2_total}) [{pf}]")

    # Check option chain quality (sample)
    sample_date = dates[len(dates)//2]  # middle of dataset
    avail = bt.loader.load_available_expirations(bt.config.ticker, sample_date)
    if not avail.empty:
        exp = avail.iloc[0]['expiration_date']
        chain = bt.loader.load_option_chain(bt.config.ticker, sample_date, exp)
        if not chain.empty:
            has_delta = chain['delta'].notna().sum() > 0
            has_bid = (chain['put_bid'] > 0).sum() > 0
            has_ask = (chain['put_ask'] > 0).sum() > 0
            bad_spread = ((chain['put_ask'] > 0) & (chain['put_bid'] > chain['put_ask'])).sum()
            print(f"\n  Option Chain Quality (sample {sample_date}, {len(chain)} strikes):")
            print(f"    Has delta data: {'YES' if has_delta else 'NO'} [{'PASS' if has_delta else 'WARN'}]")
            print(f"    Has put bids > 0: {has_bid} [{'PASS' if has_bid else 'FAIL'}]")
            print(f"    Has put asks > 0: {has_ask} [{'PASS' if has_ask else 'FAIL'}]")
            print(f"    Bid > Ask errors: {bad_spread} [{'PASS' if bad_spread == 0 else 'FAIL'}]")

    # GEX coverage
    gex_len = len(bt._gex_df)
    print(f"\n  GEX data: {gex_len} records [{'PASS' if gex_len > 100 else 'WARN'}]")

    # Event calendar
    ec = bt._event_calendar
    print(f"\n  Event Calendar:")
    for key, dates_set in ec.items():
        print(f"    {key}: {len(dates_set)} dates")

    # Years of data
    if dates:
        year_span = (dates[-1] - dates[0]).days / 365.25
        pf = "PASS" if year_span >= 4 else "FAIL"
        print(f"\n  Data span: {year_span:.1f} years [{pf}] (need >= 4)")

    print(f"\n  Phase 0 complete. Review results above before proceeding.")


def run_phase_2(bt: FortressRealisticBacktest) -> Dict[str, Any]:
    """Phase 2: Baseline backtest (no filters, no optimization)."""
    print(f"\n{'='*72}")
    print(f"  PHASE 2: BASELINE BACKTEST (NO FILTERS)")
    print(f"{'='*72}")

    # Reset to baseline config
    bt.config.profit_target_pct = 0.0      # Hold to expiration
    bt.config.stop_loss_multiplier = 0.0   # No stop loss
    bt.config.max_vix = 999.0              # No VIX filter
    bt.config.skip_fomc = False
    bt.config.skip_cpi = False
    bt.config.skip_nfp = False
    bt.config.skip_days_of_week = []
    bt.config.vix_spike_threshold = 0.0

    print(f"\n  Config: {bt.config.strike_method} strikes, "
          f"${bt.config.spread_width} wings, "
          f"{bt.config.min_dte_trading_days}DTE, "
          f"slippage=${bt.config.slippage_per_leg}/leg, "
          f"commission=${bt.config.commission_per_contract}/contract")

    trades = bt.run_backtest()
    stats = compute_full_stats(trades, bt.config.initial_capital, "BASELINE")
    print_scorecard(stats)

    # Print skip analysis
    if bt.skipped_days:
        print(f"\n  Skipped Days: {len(bt.skipped_days)}")
        reasons = defaultdict(int)
        for s in bt.skipped_days:
            r = s['reason'].split(' ')[0]
            reasons[r] += 1
        for r, c in sorted(reasons.items(), key=lambda x: -x[1])[:8]:
            print(f"    {r}: {c}")

    # Gate check
    print(f"\n  --- GATE 2: GO/NO-GO ---")
    gate_passes = 0
    checks = [
        ("Win Rate > 60%", stats.get('win_rate', 0) > 0.60),
        ("Profit Factor > 1.2", stats.get('profit_factor', 0) > 1.2),
        ("Avg Trade P&L > $0", stats.get('avg_pnl', 0) > 0),
        ("Max DD < 30%", stats.get('max_dd_pct', 1) < 0.30),
        ("Sharpe > 0.5", stats.get('sharpe', 0) > 0.5),
        ("Sample Size > 200", stats.get('total_trades', 0) > 200),
    ]
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        if passed:
            gate_passes += 1
        print(f"    [{status}] {name}")
    print(f"  Gate 2: {gate_passes}/6 passed (need 4+ to proceed)")

    return stats


def run_phase_3(bt: FortressRealisticBacktest, baseline_stats: Dict) -> List[Dict]:
    """Phase 3: Filter testing - test each filter independently."""
    print(f"\n{'='*72}")
    print(f"  PHASE 3: FILTER TESTING")
    print(f"{'='*72}")

    results = []

    # Test configurations: (label, config_overrides)
    filter_tests = [
        # VIX max filters
        ("VIX < 25", {'max_vix': 25.0}),
        ("VIX < 30", {'max_vix': 30.0}),
        ("VIX < 35", {'max_vix': 35.0}),
        # VIX spike filters
        ("VIX Spike > 10%", {'vix_spike_threshold': 10.0}),
        ("VIX Spike > 15%", {'vix_spike_threshold': 15.0}),
        ("VIX Spike > 20%", {'vix_spike_threshold': 20.0}),
        # Event filters
        ("Skip FOMC", {'skip_fomc': True}),
        ("Skip FOMC+1", {'skip_fomc': True, 'skip_fomc_next_day': True}),
        ("Skip CPI", {'skip_cpi': True}),
        ("Skip NFP", {'skip_nfp': True}),
        ("Skip All Events", {'skip_fomc': True, 'skip_fomc_next_day': True,
                             'skip_cpi': True, 'skip_nfp': True}),
        # Day of week
        ("Skip Monday", {'skip_days_of_week': [0]}),
        ("Skip Friday", {'skip_days_of_week': [4]}),
        ("Skip Mon+Fri", {'skip_days_of_week': [0, 4]}),
    ]

    print(f"\n  {'Filter':<25} {'Trades':>7} {'WR%':>6} {'PF':>6} "
          f"{'Sharpe':>7} {'MaxDD%':>7} {'P&L':>12} {'vs Base':>8}")
    print(f"  {'-'*25} {'-'*7} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*12} {'-'*8}")

    base_sharpe = baseline_stats.get('sharpe', 0)

    for label, overrides in filter_tests:
        # Reset to baseline
        bt.config.max_vix = 999.0
        bt.config.vix_spike_threshold = 0.0
        bt.config.skip_fomc = False
        bt.config.skip_fomc_next_day = False
        bt.config.skip_cpi = False
        bt.config.skip_nfp = False
        bt.config.skip_quad_witch = False
        bt.config.skip_days_of_week = []
        bt.config.profit_target_pct = 0.0
        bt.config.stop_loss_multiplier = 0.0

        # Apply overrides
        for k, v in overrides.items():
            setattr(bt.config, k, v)

        trades = bt.run_backtest()
        stats = compute_full_stats(trades, bt.config.initial_capital, label)

        sharpe_delta = stats.get('sharpe', 0) - base_sharpe
        sign = '+' if sharpe_delta >= 0 else ''

        print(f"  {label:<25} {stats.get('total_trades', 0):>7} "
              f"{stats.get('win_rate', 0)*100:>5.1f}% "
              f"{stats.get('profit_factor', 0):>5.2f} "
              f"{stats.get('sharpe', 0):>6.2f} "
              f"{stats.get('max_dd_pct', 0)*100:>6.1f}% "
              f"${stats.get('total_pnl', 0):>10,.0f} "
              f"{sign}{sharpe_delta:>6.2f}")

        stats['overrides'] = overrides
        results.append(stats)

    return results


def run_phase_4(bt: FortressRealisticBacktest) -> List[Dict]:
    """Phase 4: Exit optimization - profit target x stop loss grid."""
    print(f"\n{'='*72}")
    print(f"  PHASE 4: EXIT OPTIMIZATION GRID")
    print(f"{'='*72}")

    # Reset filters to baseline
    bt.config.max_vix = 999.0
    bt.config.skip_fomc = False
    bt.config.skip_cpi = False
    bt.config.skip_nfp = False
    bt.config.skip_days_of_week = []
    bt.config.vix_spike_threshold = 0.0

    profit_targets = [0, 25, 50, 75]    # 0 = hold to expiration
    stop_losses = [0, 1.0, 1.5, 2.0]    # 0 = no stop, multiplier of credit

    results = []

    print(f"\n  Grid: Sharpe | PF | Win% | MaxDD%")
    print(f"  {'':>15}", end='')
    for sl in stop_losses:
        sl_label = 'No Stop' if sl == 0 else f'{sl}x Stop'
        print(f"  {sl_label:>20}", end='')
    print()

    for pt in profit_targets:
        pt_label = 'Hold to Exp' if pt == 0 else f'{pt}% PT'
        print(f"  {pt_label:>15}", end='')

        for sl in stop_losses:
            bt.config.profit_target_pct = float(pt)
            bt.config.stop_loss_multiplier = float(sl)

            trades = bt.run_backtest()
            stats = compute_full_stats(
                trades, bt.config.initial_capital,
                f"PT={pt}% SL={sl}x"
            )

            sharpe = stats.get('sharpe', 0)
            pf_val = stats.get('profit_factor', 0)
            wr = stats.get('win_rate', 0) * 100
            dd = stats.get('max_dd_pct', 0) * 100

            print(f"  {sharpe:>4.1f}|{pf_val:>4.1f}|{wr:>4.0f}%|{dd:>4.0f}%", end='')
            results.append(stats)

        print()

    # Find best combo
    best = max(results, key=lambda s: s.get('sharpe', -999))
    print(f"\n  Best combo: {best.get('label', '?')} "
          f"(Sharpe={best.get('sharpe', 0):.2f}, PF={best.get('profit_factor', 0):.2f})")

    return results


def run_phase_5(bt: FortressRealisticBacktest) -> List[Dict]:
    """Phase 5: Strike selection comparison."""
    print(f"\n{'='*72}")
    print(f"  PHASE 5: STRIKE SELECTION COMPARISON")
    print(f"{'='*72}")

    # Reset to baseline exits
    bt.config.profit_target_pct = 0.0
    bt.config.stop_loss_multiplier = 0.0
    bt.config.max_vix = 999.0
    bt.config.skip_fomc = False
    bt.config.skip_cpi = False
    bt.config.skip_nfp = False
    bt.config.skip_days_of_week = []

    results = []

    # Strike method tests
    strike_tests = [
        # Delta-based
        ("Delta 10", 'delta', {'target_delta': 0.10}),
        ("Delta 16", 'delta', {'target_delta': 0.16}),
        ("Delta 20", 'delta', {'target_delta': 0.20}),
        ("Delta 25", 'delta', {'target_delta': 0.25}),
        # SD-based
        ("SD 0.8", 'sd', {'sd_multiplier': 0.8}),
        ("SD 1.0", 'sd', {'sd_multiplier': 1.0}),
        ("SD 1.2", 'sd', {'sd_multiplier': 1.2}),
        ("SD 1.5", 'sd', {'sd_multiplier': 1.5}),
        # OTM percentage
        ("OTM 0.5%", 'otm_pct', {'otm_pct': 0.5}),
        ("OTM 1.0%", 'otm_pct', {'otm_pct': 1.0}),
        ("OTM 1.5%", 'otm_pct', {'otm_pct': 1.5}),
        ("OTM 2.0%", 'otm_pct', {'otm_pct': 2.0}),
        # ATR-based
        ("ATR 0.5x", 'atr', {'atr_multiplier': 0.5}),
        ("ATR 1.0x", 'atr', {'atr_multiplier': 1.0}),
        ("ATR 1.5x", 'atr', {'atr_multiplier': 1.5}),
        # Expected move
        ("Exp Move 1x", 'expected_move', {}),
    ]

    print(f"\n  {'Method':<20} {'Trades':>7} {'WR%':>6} {'PF':>6} "
          f"{'Sharpe':>7} {'MaxDD%':>7} {'P&L':>12} {'AvgCred':>8}")
    print(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*12} {'-'*8}")

    for label, method, overrides in strike_tests:
        bt.config.strike_method = method
        for k, v in overrides.items():
            setattr(bt.config, k, v)

        trades = bt.run_backtest()
        stats = compute_full_stats(trades, bt.config.initial_capital, label)

        avg_credit = np.mean([t.total_credit for t in trades]) if trades else 0

        print(f"  {label:<20} {stats.get('total_trades', 0):>7} "
              f"{stats.get('win_rate', 0)*100:>5.1f}% "
              f"{stats.get('profit_factor', 0):>5.2f} "
              f"{stats.get('sharpe', 0):>6.2f} "
              f"{stats.get('max_dd_pct', 0)*100:>6.1f}% "
              f"${stats.get('total_pnl', 0):>10,.0f} "
              f"${avg_credit:>7.4f}")

        results.append(stats)

    # Wing width comparison with best method
    best_method = max(results, key=lambda s: s.get('sharpe', -999))
    print(f"\n  Best strike method: {best_method.get('label', '?')}")

    original_width = bt.config.spread_width
    print(f"\n  --- Wing Width Comparison (using best method) ---")
    for width in [1, 2, 3, 5, 10]:
        bt.config.spread_width = float(width)
        trades = bt.run_backtest()
        stats = compute_full_stats(trades, bt.config.initial_capital, f"${width} wings")
        print_compact_stats(stats)
        results.append(stats)

    # Reset to original config value
    bt.config.spread_width = original_width

    return results


def run_phase_7(trades: List[Trade], initial_capital: float,
                n_simulations: int = 10000) -> Dict:
    """Phase 7: Monte Carlo stress test."""
    print(f"\n{'='*72}")
    print(f"  PHASE 7: MONTE CARLO STRESS TEST ({n_simulations:,} simulations)")
    print(f"{'='*72}")

    if not trades:
        print("  No trades to simulate!")
        return {}

    pnls = [t.realized_pnl for t in trades]
    n_trades = len(pnls)

    max_dds = []
    max_consec = []
    ending_equities = []

    rng = np.random.default_rng(42)

    for _ in range(n_simulations):
        shuffled = rng.permutation(pnls)
        equity = initial_capital
        peak = equity
        max_dd = 0
        streak = 0
        max_streak = 0

        for pnl in shuffled:
            equity += pnl
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

            if pnl <= 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        max_dds.append(max_dd)
        max_consec.append(max_streak)
        ending_equities.append(equity)

    max_dds = np.array(max_dds)
    max_consec = np.array(max_consec)
    ending_equities = np.array(ending_equities)

    percentiles = [5, 25, 50, 75, 95]

    print(f"\n  {'Metric':<30}", end='')
    for p in percentiles:
        label = "WORST" if p == 5 else ("BEST" if p == 95 else f"{p}th")
        print(f"  {label:>10}", end='')
    print()
    print(f"  {'-'*30}", end='')
    for _ in percentiles:
        print(f"  {'-'*10}", end='')
    print()

    dd_pcts = np.percentile(max_dds, percentiles)
    print(f"  {'Max Drawdown (%)':<30}", end='')
    for v in dd_pcts:
        print(f"  {v*100:>9.1f}%", end='')
    print()

    dd_dollars = dd_pcts * initial_capital
    print(f"  {'Max Drawdown ($)':<30}", end='')
    for v in dd_dollars:
        print(f"  ${v:>8,.0f}", end='')
    print()

    consec_pcts = np.percentile(max_consec, percentiles)
    print(f"  {'Max Consecutive Losses':<30}", end='')
    for v in consec_pcts:
        print(f"  {v:>10.0f}", end='')
    print()

    eq_pcts = np.percentile(ending_equities, percentiles)
    print(f"  {'Ending Equity ($)':<30}", end='')
    for v in eq_pcts:
        print(f"  ${v:>8,.0f}", end='')
    print()

    # Gate 7
    print(f"\n  --- GATE 7: GO/NO-GO ---")
    worst_dd = np.percentile(max_dds, 95)
    worst_consec = np.percentile(max_consec, 95)
    median_eq = np.percentile(ending_equities, 50)
    worst_eq = np.percentile(ending_equities, 5)

    checks = [
        (f"95th %ile Max DD < 40%", worst_dd < 0.40),
        (f"95th %ile Consec Losses < 10", worst_consec < 10),
        (f"Median Ending Equity > Capital", median_eq > initial_capital),
        (f"5th %ile Equity > 70% Capital", worst_eq > initial_capital * 0.70),
    ]
    for name, passed in checks:
        print(f"    [{'PASS' if passed else 'FAIL'}] {name}")

    return {
        'max_dd_percentiles': dd_pcts.tolist(),
        'consec_loss_percentiles': consec_pcts.tolist(),
        'ending_equity_percentiles': eq_pcts.tolist(),
    }


def run_phase_6(bt: FortressRealisticBacktest) -> Dict:
    """Phase 6: Walk-forward validation."""
    print(f"\n{'='*72}")
    print(f"  PHASE 6: WALK-FORWARD VALIDATION")
    print(f"{'='*72}")

    dates = bt._trading_dates
    if not dates:
        print("  No dates available!")
        return {}

    # Use 12-month in-sample, 3-month out-of-sample, roll by 3 months
    start_year = max(2020, dates[0].year)
    all_oos_trades = []
    all_is_trades = []
    windows = []

    current_start = date(start_year, 1, 1)
    end_of_data = dates[-1]

    print(f"\n  Rolling windows (12mo IS + 3mo OOS):")
    print(f"  {'Window':<8} {'IS Period':<25} {'OOS Period':<25} {'IS Trades':>10} {'OOS Trades':>10} {'OOS P&L':>12}")

    window_num = 0
    while True:
        is_end = current_start + timedelta(days=365)
        oos_start = is_end + timedelta(days=1)
        oos_end = oos_start + timedelta(days=90)

        if oos_end > end_of_data:
            break

        # In-sample
        bt.config.start_date = current_start.isoformat()
        bt.config.end_date = is_end.isoformat()
        is_trades = bt.run_backtest()
        all_is_trades.extend(is_trades)

        # Out-of-sample
        bt.config.start_date = oos_start.isoformat()
        bt.config.end_date = oos_end.isoformat()
        oos_trades = bt.run_backtest()
        all_oos_trades.extend(oos_trades)

        is_pnl = sum(t.realized_pnl for t in is_trades)
        oos_pnl = sum(t.realized_pnl for t in oos_trades)

        window_num += 1
        print(f"  {window_num:<8} {str(current_start):>10}-{str(is_end):<14} "
              f"{str(oos_start):>10}-{str(oos_end):<14} "
              f"{len(is_trades):>10} {len(oos_trades):>10} ${oos_pnl:>10,.0f}")

        windows.append({
            'is_start': current_start, 'is_end': is_end,
            'oos_start': oos_start, 'oos_end': oos_end,
            'is_trades': len(is_trades), 'oos_trades': len(oos_trades),
            'is_pnl': is_pnl, 'oos_pnl': oos_pnl,
        })

        # Roll forward 3 months
        month = current_start.month + 3
        year = current_start.year
        if month > 12:
            month -= 12
            year += 1
        current_start = date(year, month, 1)

    # Compute OOS stats
    if all_oos_trades:
        oos_stats = compute_full_stats(all_oos_trades, bt.config.initial_capital, "OOS Combined")
        is_stats = compute_full_stats(all_is_trades, bt.config.initial_capital, "IS Combined")

        print(f"\n  --- Walk-Forward Summary ---")
        print(f"  IS:  Sharpe={is_stats.get('sharpe', 0):.2f}, "
              f"WR={is_stats.get('win_rate', 0)*100:.1f}%, "
              f"PF={is_stats.get('profit_factor', 0):.2f}")
        print(f"  OOS: Sharpe={oos_stats.get('sharpe', 0):.2f}, "
              f"WR={oos_stats.get('win_rate', 0)*100:.1f}%, "
              f"PF={oos_stats.get('profit_factor', 0):.2f}")

        # Gate 6
        is_sharpe = is_stats.get('sharpe', 0)
        oos_sharpe = oos_stats.get('sharpe', 0)
        ratio = oos_sharpe / is_sharpe if is_sharpe != 0 else 0
        wr_diff = abs(oos_stats.get('win_rate', 0) - is_stats.get('win_rate', 0))
        profitable_windows = sum(1 for w in windows if w['oos_pnl'] > 0)
        wf_efficiency = profitable_windows / len(windows) if windows else 0

        print(f"\n  --- GATE 6: GO/NO-GO ---")
        checks = [
            (f"OOS/IS Sharpe ratio > 0.4 (got {ratio:.2f})", ratio > 0.4),
            (f"WR diff < 10pp (got {wr_diff*100:.1f}pp)", wr_diff < 0.10),
            (f"WF Efficiency > 70% (got {wf_efficiency*100:.0f}%)", wf_efficiency > 0.70),
        ]
        for name, passed in checks:
            print(f"    [{'PASS' if passed else 'FAIL'}] {name}")

        return {'oos_stats': oos_stats, 'is_stats': is_stats, 'windows': windows}

    return {}


# ============================================================================
# VIX REGIME BREAKDOWN
# ============================================================================

def print_vix_regime_breakdown(trades: List[Trade], initial_capital: float):
    """Phase 8 Category 4: Performance by VIX regime."""
    print(f"\n  CATEGORY 4: ROBUSTNESS ACROSS CONDITIONS")
    buckets = {
        'VIX < 20': [t for t in trades if t.vix_at_entry < 20],
        'VIX 20-30': [t for t in trades if 20 <= t.vix_at_entry < 30],
        'VIX > 30': [t for t in trades if t.vix_at_entry >= 30],
    }

    for label, bucket_trades in buckets.items():
        if bucket_trades:
            stats = compute_full_stats(bucket_trades, initial_capital, label)
            wr = stats.get('win_rate', 0) * 100
            pf = stats.get('profit_factor', 0)
            pnl = stats.get('total_pnl', 0)
            dd = stats.get('max_dd_pct', 0) * 100
            print(f"  {label:<12}: N={len(bucket_trades):>4}, "
                  f"WR={wr:>5.1f}%, PF={pf:>5.2f}, "
                  f"P&L=${pnl:>10,.0f}, MaxDD={dd:>5.1f}%")

    # Worst month
    monthly = defaultdict(float)
    for t in trades:
        key = t.entry_date.strftime('%Y-%m')
        monthly[key] += t.realized_pnl

    if monthly:
        worst_month = min(monthly.items(), key=lambda x: x[1])
        worst_pct = worst_month[1] / initial_capital * 100
        pf = "PASS" if worst_pct > -8 else "FAIL"
        print(f"\n  Worst month: {worst_month[0]} = ${worst_month[1]:,.0f} ({worst_pct:.1f}%) [{pf}]")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='FORTRESS Full Realistic Backtest')
    parser.add_argument('--phase', type=str, default='2',
                        help='Phase to run: 0,2,3,4,5,6,7,8,all')
    parser.add_argument('--ticker', default='SPY')
    parser.add_argument('--capital', type=float, default=100_000)
    parser.add_argument('--spread-width', type=float, default=5.0)
    parser.add_argument('--min-dte', type=int, default=3)
    parser.add_argument('--strike-method', default='sd',
                        choices=['delta', 'sd', 'otm_pct', 'atr', 'expected_move'])
    parser.add_argument('--target-delta', type=float, default=0.16)
    parser.add_argument('--sd-multiplier', type=float, default=1.2)
    parser.add_argument('--slippage', type=float, default=0.01, help='Per-leg slippage')
    parser.add_argument('--commission', type=float, default=0.65, help='Per-contract commission')
    parser.add_argument('--start-date', type=str, default=None)
    parser.add_argument('--end-date', type=str, default=None)
    parser.add_argument('--db-url', type=str, default=DEFAULT_DB_URL)
    parser.add_argument('--monte-carlo-sims', type=int, default=10000)

    args = parser.parse_args()

    config = RealisticConfig(
        ticker=args.ticker,
        initial_capital=args.capital,
        spread_width=args.spread_width,
        min_dte_trading_days=args.min_dte,
        strike_method=args.strike_method,
        target_delta=args.target_delta,
        sd_multiplier=args.sd_multiplier,
        slippage_per_leg=args.slippage,
        commission_per_contract=args.commission,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    print(f"\n{'='*72}")
    print(f"  FORTRESS FULL REALISTIC BACKTEST ENGINE")
    print(f"  Phases: {args.phase}")
    print(f"{'='*72}")
    print(f"  Ticker:      {config.ticker}")
    print(f"  Capital:     ${config.initial_capital:,.0f}")
    print(f"  Strikes:     {config.strike_method} (delta={config.target_delta}, sd={config.sd_multiplier})")
    print(f"  Wings:       ${config.spread_width}")
    print(f"  DTE:         {config.min_dte_trading_days} trading days")
    print(f"  Slippage:    ${config.slippage_per_leg}/leg (${config.slippage_per_leg * 4:.2f}/contract)")
    print(f"  Commission:  ${config.commission_per_contract}/contract (${config.commission_per_contract * 8:.2f}/trade)")

    bt = FortressRealisticBacktest(config, args.db_url)
    bt.load_data()

    phases = args.phase.lower()

    try:
        if phases in ('0', 'all'):
            run_phase_0(bt)

        baseline_stats = None
        if phases in ('2', 'all', '2-8'):
            baseline_stats = run_phase_2(bt)

        if phases in ('3', 'all', '2-8'):
            if baseline_stats is None:
                baseline_stats = run_phase_2(bt)
            run_phase_3(bt, baseline_stats)

        if phases in ('4', 'all', '2-8'):
            run_phase_4(bt)

        if phases in ('5', 'all', '2-8'):
            run_phase_5(bt)

        if phases in ('6', 'all', '2-8'):
            wf_result = run_phase_6(bt)

        if phases in ('7', 'all', '2-8'):
            # Run baseline first to get trades
            bt.config.start_date = args.start_date
            bt.config.end_date = args.end_date
            bt.config.profit_target_pct = 0.0
            bt.config.stop_loss_multiplier = 0.0
            bt.config.max_vix = 999.0
            trades = bt.run_backtest()
            run_phase_7(trades, config.initial_capital, args.monte_carlo_sims)

        if phases in ('8', 'all', '2-8'):
            # Final scorecard on baseline
            bt.config.start_date = args.start_date
            bt.config.end_date = args.end_date
            bt.config.profit_target_pct = 0.0
            bt.config.stop_loss_multiplier = 0.0
            bt.config.max_vix = 999.0
            trades = bt.run_backtest()
            stats = compute_full_stats(trades, config.initial_capital, "FINAL SCORECARD")
            print_scorecard(stats)
            print_vix_regime_breakdown(trades, config.initial_capital)

    finally:
        bt.close()

    print(f"\n{'='*72}")
    print(f"  BACKTEST COMPLETE")
    print(f"{'='*72}\n")


if __name__ == '__main__':
    main()
