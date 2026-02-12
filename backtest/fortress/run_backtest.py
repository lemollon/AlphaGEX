#!/usr/bin/env python3
"""
FORTRESS Backtest - Production-Matched IC Backtest Engine
=========================================================

Connects directly to the Render PostgreSQL database.
Matches FORTRESS production logic exactly (Feb 2026 version).

Key Production Parameters:
- EM = spot * (VIX/100) / sqrt(252)
- SD Multiplier: 1.2 (minimum floor)
- Spread Width: $5
- Min DTE: 3 trading days
- Risk Per Trade: 15% of capital
- Profit Target: 50% of credit
- GEX Walls: DISABLED (pure SD math)
- VIX Filter: >50 blocks trading

Usage:
    # From Render shell:
    cd /home/user/AlphaGEX  # or wherever the repo is
    python backtest/fortress/run_backtest.py

    # Custom params:
    python backtest/fortress/run_backtest.py --sd-multiplier 1.0 --min-dte 0 --spread-width 5

    # DTE sweep:
    python backtest/fortress/run_backtest.py --dte-sweep
"""

import os
import sys
import math
import argparse
import logging
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import json

# Add project root for imports
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Default DB URL (backtest database)
DEFAULT_DB_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest'
)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class BacktestConfig:
    """Backtest configuration matching FORTRESS production params."""
    ticker: str = 'SPY'
    sd_multiplier: float = 1.2       # Min floor in production
    spread_width: float = 5.0        # $5 wide spreads
    min_dte_trading_days: int = 3     # 3 trading days to expiration
    risk_per_trade_pct: float = 15.0  # 15% of capital
    initial_capital: float = 100_000
    max_contracts: int = 75
    profit_target_pct: float = 50.0   # Take profit at 50% of credit
    max_vix: float = 50.0             # Hard VIX filter
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None
    use_mid_price: bool = False       # False = use bid/ask (realistic)
    min_credit: float = 0.10          # Skip trades with < $0.10 credit

    def __str__(self):
        return (
            f"FORTRESS Backtest Config:\n"
            f"  Ticker:          {self.ticker}\n"
            f"  SD Multiplier:   {self.sd_multiplier}\n"
            f"  Spread Width:    ${self.spread_width}\n"
            f"  Min DTE:         {self.min_dte_trading_days} trading days\n"
            f"  Risk/Trade:      {self.risk_per_trade_pct}%\n"
            f"  Capital:         ${self.initial_capital:,.0f}\n"
            f"  Profit Target:   {self.profit_target_pct}%\n"
            f"  VIX Filter:      >{self.max_vix}\n"
            f"  Pricing:         {'Mid' if self.use_mid_price else 'Bid/Ask (realistic)'}\n"
        )


@dataclass
class Trade:
    """A single IC trade."""
    entry_date: date
    expiration_date: date
    entry_dte: int                     # Calendar DTE at entry
    spot_at_entry: float
    vix_at_entry: float
    expected_move: float

    # Strikes
    short_put: float
    long_put: float
    short_call: float
    long_call: float

    # Entry pricing (per contract)
    put_spread_credit: float           # Short put bid - long put ask
    call_spread_credit: float          # Short call bid - long call ask
    total_credit: float                # Per contract credit
    contracts: int
    max_risk_per_contract: float       # spread_width - total_credit

    # Exit
    exit_date: Optional[date] = None
    exit_reason: str = ''
    exit_credit: float = 0.0           # What we paid to close (0 if expired)
    spot_at_exit: float = 0.0

    # P&L
    realized_pnl: float = 0.0         # Total P&L (contracts * 100 * per_contract_pnl)

    # GEX context (informational)
    gex_regime: str = ''
    call_wall: float = 0.0
    put_wall: float = 0.0

    @property
    def per_contract_pnl(self):
        return self.total_credit - self.exit_credit

    @property
    def is_win(self):
        return self.realized_pnl > 0


# ============================================================================
# DATABASE LOADER
# ============================================================================

class DataLoader:
    """Loads data from PostgreSQL."""

    def __init__(self, db_url: str = DEFAULT_DB_URL):
        self.db_url = db_url
        self._conn = None

    def connect(self):
        """Establish DB connection."""
        logger.info("Connecting to database...")
        self._conn = psycopg2.connect(self.db_url)
        logger.info("Connected successfully")

    def close(self):
        if self._conn:
            self._conn.close()

    def load_trading_calendar(self, ticker: str = 'SPY') -> List[date]:
        """Get all trading dates from underlying_prices."""
        query = """
            SELECT DISTINCT trade_date
            FROM underlying_prices
            WHERE symbol = %s
            ORDER BY trade_date
        """
        df = pd.read_sql(query, self._conn, params=(ticker,))
        if df.empty:
            # Fallback: derive from ORAT data
            logger.warning("No underlying_prices data, deriving calendar from ORAT")
            query = """
                SELECT DISTINCT trade_date
                FROM orat_options_eod
                WHERE ticker = %s
                ORDER BY trade_date
            """
            df = pd.read_sql(query, self._conn, params=(ticker,))
        return sorted(df['trade_date'].tolist())

    def load_underlying_prices(self, ticker: str = 'SPY') -> pd.DataFrame:
        """Load daily close prices."""
        query = """
            SELECT trade_date, symbol, open, high, low, close
            FROM underlying_prices
            WHERE symbol = %s
            ORDER BY trade_date
        """
        df = pd.read_sql(query, self._conn, params=(ticker,))
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        return df.set_index('trade_date')

    def load_vix_history(self) -> pd.DataFrame:
        """Load VIX daily data."""
        query = """
            SELECT trade_date, open, high, low, close
            FROM vix_history
            ORDER BY trade_date
        """
        df = pd.read_sql(query, self._conn)
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        return df.set_index('trade_date')

    def load_gex_daily(self, ticker: str = 'SPY') -> pd.DataFrame:
        """Load GEX daily data for informational context."""
        # Try gex_structure_daily first (more detailed)
        query = """
            SELECT trade_date, symbol, call_wall, put_wall, flip_point,
                   net_gamma, gamma_imbalance_pct,
                   magnet_1_strike, magnet_2_strike, magnet_3_strike
            FROM gex_structure_daily
            WHERE symbol = %s
            ORDER BY trade_date
        """
        df = pd.read_sql(query, self._conn, params=(ticker.replace('SPY', 'SPY'),))
        if df.empty:
            # Try gex_daily
            query = """
                SELECT trade_date, symbol, call_wall, put_wall, flip_point,
                       net_gex as net_gamma, gex_regime
                FROM gex_daily
                WHERE symbol = %s
                ORDER BY trade_date
            """
            df = pd.read_sql(query, self._conn, params=(ticker,))
        if not df.empty:
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            df = df.set_index('trade_date')
        return df

    def load_option_chain(self, ticker: str, trade_date: date, expiration_date: date) -> pd.DataFrame:
        """Load option chain for a specific date and expiration."""
        query = """
            SELECT strike, option_type,
                   call_bid, call_ask, call_mid,
                   put_bid, put_ask, put_mid,
                   delta, gamma, call_iv, put_iv,
                   underlying_price, dte
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date = %s
              AND expiration_date = %s
            ORDER BY strike
        """
        df = pd.read_sql(query, self._conn, params=(ticker, trade_date, expiration_date))
        return df

    def load_available_expirations(self, ticker: str, trade_date: date) -> pd.DataFrame:
        """Get available expirations and their DTE for a given trade date."""
        query = """
            SELECT DISTINCT expiration_date, dte
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date = %s
              AND dte >= 0
            ORDER BY expiration_date
        """
        return pd.read_sql(query, self._conn, params=(ticker, trade_date))

    def get_settlement_price(self, ticker: str, settlement_date: date) -> Optional[float]:
        """Get the underlying close price on a specific date."""
        query = """
            SELECT close FROM underlying_prices
            WHERE symbol = %s AND trade_date = %s
        """
        df = pd.read_sql(query, self._conn, params=(ticker, settlement_date))
        if not df.empty and df.iloc[0]['close'] is not None:
            return float(df.iloc[0]['close'])

        # Fallback: get from ORAT underlying_price
        query = """
            SELECT DISTINCT underlying_price
            FROM orat_options_eod
            WHERE ticker = %s AND trade_date = %s
            LIMIT 1
        """
        df = pd.read_sql(query, self._conn, params=(ticker, settlement_date))
        if not df.empty:
            return float(df.iloc[0]['underlying_price'])
        return None


# ============================================================================
# EXPECTED MOVE CALCULATION
# ============================================================================

def calculate_expected_move(spot: float, vix: float) -> float:
    """
    Calculate expected daily move (1 SD).
    MATCHES FORTRESS PRODUCTION: spot * (VIX/100) / sqrt(252)
    """
    annual_factor = math.sqrt(252)  # Trading days per year
    daily_vol = (vix / 100) / annual_factor
    return round(spot * daily_vol, 2)


# ============================================================================
# STRIKE SELECTION
# ============================================================================

def select_strikes(spot: float, expected_move: float, sd_multiplier: float,
                   spread_width: float) -> Dict[str, float]:
    """
    Select IC strikes using FORTRESS production logic.
    Pure SD math - NO GEX wall influence.
    """
    # Minimum EM floor (0.5% of spot)
    min_em = spot * 0.005
    effective_em = max(expected_move, min_em)

    # Short strikes = spot +/- (SD * EM), rounded AWAY from spot
    short_put = math.floor(spot - sd_multiplier * effective_em)
    short_call = math.ceil(spot + sd_multiplier * effective_em)

    # Long strikes are spread_width away
    long_put = short_put - spread_width
    long_call = short_call + spread_width

    return {
        'short_put': short_put,
        'long_put': long_put,
        'short_call': short_call,
        'long_call': long_call,
    }


# ============================================================================
# IC PRICING
# ============================================================================

def price_iron_condor(chain: pd.DataFrame, strikes: Dict[str, float],
                      use_mid: bool = False) -> Optional[Dict]:
    """
    Price an Iron Condor from the ORAT option chain.

    Returns dict with credit details, or None if strikes not found.
    """
    def get_row(strike_val):
        rows = chain[chain['strike'] == strike_val]
        if rows.empty:
            return None
        return rows.iloc[0]

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
        # Realistic: sell at bid, buy at ask
        put_credit = float(sp['put_bid'] or 0) - float(lp['put_ask'] or 0)
        call_credit = float(sc['call_bid'] or 0) - float(lc['call_ask'] or 0)

    # Sanity checks
    if put_credit < 0:
        put_credit = 0  # Can't have negative credit on a credit spread
    if call_credit < 0:
        call_credit = 0

    total_credit = put_credit + call_credit

    return {
        'put_credit': round(put_credit, 4),
        'call_credit': round(call_credit, 4),
        'total_credit': round(total_credit, 4),
        'underlying_price': float(sp['underlying_price']),
    }


def calculate_ic_exit_value(chain: pd.DataFrame, strikes: Dict[str, float],
                            use_mid: bool = False) -> Optional[float]:
    """
    Calculate current value of an IC (what it would cost to close).
    Used for profit target checks on intermediate days.
    """
    def get_row(strike_val):
        rows = chain[chain['strike'] == strike_val]
        if rows.empty:
            return None
        return rows.iloc[0]

    sp = get_row(strikes['short_put'])
    lp = get_row(strikes['long_put'])
    sc = get_row(strikes['short_call'])
    lc = get_row(strikes['long_call'])

    if any(x is None for x in [sp, lp, sc, lc]):
        return None

    if use_mid:
        # Cost to close = buy back shorts at ask, sell longs at bid (reversed)
        # But using mid for simplicity
        put_cost = float(sp['put_mid'] or 0) - float(lp['put_mid'] or 0)
        call_cost = float(sc['call_mid'] or 0) - float(lc['call_mid'] or 0)
    else:
        # Cost to close: buy shorts at ask, sell longs at bid
        put_cost = float(sp['put_ask'] or 0) - float(lp['put_bid'] or 0)
        call_cost = float(sc['call_ask'] or 0) - float(lc['call_bid'] or 0)

    return round(max(0, put_cost + call_cost), 4)


def calculate_settlement_pnl(spot_close: float, strikes: Dict[str, float],
                             entry_credit: float, spread_width: float) -> Tuple[float, str]:
    """
    Calculate P&L at settlement (expiration).

    Returns (per_contract_pnl, exit_reason).
    """
    sp, lp = strikes['short_put'], strikes['long_put']
    sc, lc = strikes['short_call'], strikes['long_call']

    # Put side intrinsic value (what we owe)
    put_loss = max(0, sp - spot_close) - max(0, lp - spot_close)

    # Call side intrinsic value
    call_loss = max(0, spot_close - sc) - max(0, spot_close - lc)

    total_loss = put_loss + call_loss
    pnl = entry_credit - total_loss

    if total_loss == 0:
        reason = "MAX_PROFIT"
    elif put_loss > 0 and call_loss > 0:
        reason = "BOTH_BREACHED"  # Shouldn't happen with wide enough strikes
    elif put_loss > 0:
        reason = "PUT_BREACHED"
    elif call_loss > 0:
        reason = "CALL_BREACHED"
    else:
        reason = "EXPIRED_OTM"

    return round(pnl, 4), reason


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class FortressBacktest:
    """Main backtest engine."""

    def __init__(self, config: BacktestConfig, db_url: str = DEFAULT_DB_URL):
        self.config = config
        self.loader = DataLoader(db_url)
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []
        self.daily_log: List[Dict] = []
        self.skipped_days: List[Dict] = []
        self.capital = config.initial_capital

    def run(self):
        """Execute the full backtest."""
        print(f"\n{'='*70}")
        print(f"  FORTRESS BACKTEST ENGINE")
        print(f"  Production-Matched (Feb 2026)")
        print(f"{'='*70}")
        print(str(self.config))

        self.loader.connect()

        try:
            self._run_backtest()
        finally:
            self.loader.close()

        self._print_results()

    def _run_backtest(self):
        """Core backtest loop."""
        # Load reference data
        logger.info("Loading trading calendar...")
        trading_dates = self.loader.load_trading_calendar(self.config.ticker)
        logger.info(f"  {len(trading_dates)} trading dates available")

        logger.info("Loading VIX history...")
        vix_df = self.loader.load_vix_history()
        logger.info(f"  {len(vix_df)} VIX records")

        logger.info("Loading underlying prices...")
        prices_df = self.loader.load_underlying_prices(self.config.ticker)
        logger.info(f"  {len(prices_df)} price records")

        logger.info("Loading GEX data (informational)...")
        gex_df = self.loader.load_gex_daily(self.config.ticker)
        logger.info(f"  {len(gex_df)} GEX records")

        # Build trading date index for DTE calculation
        trading_date_set = set(trading_dates)
        trading_date_idx = {d: i for i, d in enumerate(trading_dates)}

        # Filter date range
        start = date.fromisoformat(self.config.start_date) if self.config.start_date else trading_dates[0]
        end = date.fromisoformat(self.config.end_date) if self.config.end_date else trading_dates[-1]

        eligible_dates = [d for d in trading_dates if start <= d <= end]
        logger.info(f"\nBacktesting {len(eligible_dates)} trading days: {start} → {end}")

        # Track open positions
        open_positions: List[Trade] = []
        capital = self.config.initial_capital
        cumulative_pnl = 0.0

        for day_idx, trade_date in enumerate(eligible_dates):
            if day_idx % 100 == 0 and day_idx > 0:
                logger.info(f"  Day {day_idx}/{len(eligible_dates)} ({trade_date}) | P&L: ${cumulative_pnl:,.2f}")

            # ---------------------------------------------------------------
            # STEP 1: Check and close any positions that expire today or hit targets
            # ---------------------------------------------------------------
            still_open = []
            for pos in open_positions:
                closed = False

                # Check if expired
                if trade_date >= pos.expiration_date:
                    # Settlement
                    settle_price = self.loader.get_settlement_price(
                        self.config.ticker, pos.expiration_date
                    )
                    if settle_price is None:
                        # Use last known price
                        settle_price = pos.spot_at_entry
                        logger.warning(f"  No settlement price for {pos.expiration_date}, using entry spot")

                    strikes = {
                        'short_put': pos.short_put, 'long_put': pos.long_put,
                        'short_call': pos.short_call, 'long_call': pos.long_call,
                    }
                    per_contract_pnl, reason = calculate_settlement_pnl(
                        settle_price, strikes, pos.total_credit, self.config.spread_width
                    )
                    pos.exit_date = pos.expiration_date
                    pos.exit_reason = reason
                    pos.spot_at_exit = settle_price
                    pos.exit_credit = pos.total_credit - per_contract_pnl  # What we "paid" to close
                    pos.realized_pnl = round(per_contract_pnl * pos.contracts * 100, 2)

                    self.trades.append(pos)
                    cumulative_pnl += pos.realized_pnl
                    capital += pos.realized_pnl
                    closed = True

                elif trade_date > pos.entry_date:
                    # Check profit target on intermediate days
                    chain = self.loader.load_option_chain(
                        self.config.ticker, trade_date, pos.expiration_date
                    )
                    if not chain.empty:
                        strikes = {
                            'short_put': pos.short_put, 'long_put': pos.long_put,
                            'short_call': pos.short_call, 'long_call': pos.long_call,
                        }
                        current_value = calculate_ic_exit_value(
                            chain, strikes, self.config.use_mid_price
                        )
                        if current_value is not None:
                            target = pos.total_credit * (1 - self.config.profit_target_pct / 100)
                            if current_value <= target:
                                per_contract_pnl = pos.total_credit - current_value
                                pos.exit_date = trade_date
                                pos.exit_reason = "PROFIT_TARGET"
                                pos.exit_credit = current_value
                                settle = self.loader.get_settlement_price(
                                    self.config.ticker, trade_date
                                )
                                pos.spot_at_exit = settle or pos.spot_at_entry
                                pos.realized_pnl = round(per_contract_pnl * pos.contracts * 100, 2)

                                self.trades.append(pos)
                                cumulative_pnl += pos.realized_pnl
                                capital += pos.realized_pnl
                                closed = True

                if not closed:
                    still_open.append(pos)

            open_positions = still_open

            # ---------------------------------------------------------------
            # STEP 2: Check if we should open a new position today
            # ---------------------------------------------------------------

            # Skip if we already have an open position (1 position at a time)
            if open_positions:
                continue

            # Get VIX
            vix_close = None
            if trade_date in vix_df.index:
                vix_close = float(vix_df.loc[trade_date, 'close'])
            if vix_close is None or pd.isna(vix_close):
                self.skipped_days.append({
                    'date': trade_date, 'reason': 'NO_VIX_DATA'
                })
                continue

            # VIX filter
            if vix_close > self.config.max_vix:
                self.skipped_days.append({
                    'date': trade_date, 'reason': f'VIX_TOO_HIGH ({vix_close:.1f})'
                })
                continue

            # Get spot price
            spot = None
            if trade_date in prices_df.index:
                spot = prices_df.loc[trade_date, 'close']
                if isinstance(spot, pd.Series):
                    spot = spot.iloc[0]
                spot = float(spot) if spot and not pd.isna(spot) else None

            if spot is None:
                # Fallback: get from ORAT
                spot = self.loader.get_settlement_price(self.config.ticker, trade_date)
            if spot is None:
                self.skipped_days.append({
                    'date': trade_date, 'reason': 'NO_SPOT_PRICE'
                })
                continue

            # Find target expiration (min_dte TRADING days ahead)
            idx = trading_date_idx.get(trade_date)
            if idx is None:
                continue
            target_exp_idx = idx + self.config.min_dte_trading_days
            if target_exp_idx >= len(trading_dates):
                self.skipped_days.append({
                    'date': trade_date, 'reason': 'NOT_ENOUGH_DATES_FOR_DTE'
                })
                continue
            target_expiration = trading_dates[target_exp_idx]

            # Check if ORAT has this expiration
            chain = self.loader.load_option_chain(
                self.config.ticker, trade_date, target_expiration
            )
            if chain.empty:
                # Try nearby expirations
                avail = self.loader.load_available_expirations(self.config.ticker, trade_date)
                if avail.empty:
                    self.skipped_days.append({
                        'date': trade_date, 'reason': 'NO_OPTION_DATA'
                    })
                    continue
                # Find closest expiration >= target
                avail['expiration_date'] = pd.to_datetime(avail['expiration_date']).dt.date
                future_exp = avail[avail['expiration_date'] >= target_expiration]
                if future_exp.empty:
                    # Try any expiration >= min_dte calendar days
                    min_cal_dte = self.config.min_dte_trading_days  # Fallback
                    future_exp = avail[avail['dte'] >= min_cal_dte]
                if future_exp.empty:
                    self.skipped_days.append({
                        'date': trade_date, 'reason': f'NO_EXPIRATION_>={self.config.min_dte_trading_days}DTE'
                    })
                    continue
                target_expiration = future_exp.iloc[0]['expiration_date']
                chain = self.loader.load_option_chain(
                    self.config.ticker, trade_date, target_expiration
                )
                if chain.empty:
                    continue

            # Calculate expected move
            em = calculate_expected_move(spot, vix_close)

            # Select strikes
            strikes = select_strikes(
                spot, em, self.config.sd_multiplier, self.config.spread_width
            )

            # Price the IC
            pricing = price_iron_condor(chain, strikes, self.config.use_mid_price)
            if pricing is None:
                self.skipped_days.append({
                    'date': trade_date,
                    'reason': f'STRIKES_NOT_IN_CHAIN (SP={strikes["short_put"]}, SC={strikes["short_call"]})',
                    'spot': spot, 'em': em, 'vix': vix_close,
                })
                continue

            total_credit = pricing['total_credit']
            if total_credit < self.config.min_credit:
                self.skipped_days.append({
                    'date': trade_date,
                    'reason': f'CREDIT_TOO_LOW (${total_credit:.4f})',
                    'spot': spot, 'em': em, 'vix': vix_close,
                })
                continue

            # Position sizing
            max_risk_per_contract = (self.config.spread_width - total_credit) * 100
            if max_risk_per_contract <= 0:
                max_risk_per_contract = self.config.spread_width * 100

            max_risk_budget = capital * (self.config.risk_per_trade_pct / 100)
            contracts = int(max_risk_budget / max_risk_per_contract)
            contracts = max(1, min(contracts, self.config.max_contracts))

            # Calendar DTE
            cal_dte = (target_expiration - trade_date).days

            # GEX context (informational)
            gex_regime = ''
            call_wall = 0.0
            put_wall = 0.0
            if not gex_df.empty and trade_date in gex_df.index:
                row = gex_df.loc[trade_date]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                call_wall = float(row.get('call_wall', 0) or 0)
                put_wall = float(row.get('put_wall', 0) or 0)
                gex_regime = str(row.get('gex_regime', row.get('net_gamma', '')))

            # Create trade
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
                put_spread_credit=pricing['put_credit'],
                call_spread_credit=pricing['call_credit'],
                total_credit=total_credit,
                contracts=contracts,
                max_risk_per_contract=max_risk_per_contract,
                gex_regime=gex_regime,
                call_wall=call_wall,
                put_wall=put_wall,
            )

            open_positions.append(trade)

            # Record equity
            self.equity_curve.append({
                'date': trade_date,
                'capital': capital,
                'cumulative_pnl': cumulative_pnl,
                'open_positions': len(open_positions),
            })

        # Close any remaining open positions at last available price
        for pos in open_positions:
            settle = self.loader.get_settlement_price(self.config.ticker, eligible_dates[-1])
            if settle:
                strikes = {
                    'short_put': pos.short_put, 'long_put': pos.long_put,
                    'short_call': pos.short_call, 'long_call': pos.long_call,
                }
                per_contract_pnl, reason = calculate_settlement_pnl(
                    settle, strikes, pos.total_credit, self.config.spread_width
                )
                pos.exit_date = eligible_dates[-1]
                pos.exit_reason = f"BACKTEST_END ({reason})"
                pos.spot_at_exit = settle
                pos.realized_pnl = round(per_contract_pnl * pos.contracts * 100, 2)
                self.trades.append(pos)
                cumulative_pnl += pos.realized_pnl

        logger.info(f"\nBacktest complete: {len(self.trades)} trades executed")

    def _print_results(self):
        """Print comprehensive results."""
        if not self.trades:
            print("\nNO TRADES EXECUTED")
            print(f"Skipped days: {len(self.skipped_days)}")
            if self.skipped_days:
                reasons = {}
                for s in self.skipped_days:
                    r = s['reason'].split(' ')[0]
                    reasons[r] = reasons.get(r, 0) + 1
                for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
                    print(f"  {r}: {c}")
            return

        # Build results
        wins = [t for t in self.trades if t.is_win]
        losses = [t for t in self.trades if not t.is_win]
        total_pnl = sum(t.realized_pnl for t in self.trades)
        win_pnls = [t.realized_pnl for t in wins]
        loss_pnls = [t.realized_pnl for t in losses]

        # Max drawdown
        running_pnl = 0
        peak = 0
        max_dd = 0
        for t in self.trades:
            running_pnl += t.realized_pnl
            peak = max(peak, running_pnl)
            dd = peak - running_pnl
            max_dd = max(max_dd, dd)

        # Exit reason breakdown
        reasons = {}
        for t in self.trades:
            r = t.exit_reason
            reasons[r] = reasons.get(r, 0) + 1

        # Monthly breakdown
        monthly = {}
        for t in self.trades:
            key = t.entry_date.strftime('%Y-%m')
            if key not in monthly:
                monthly[key] = {'trades': 0, 'wins': 0, 'pnl': 0}
            monthly[key]['trades'] += 1
            monthly[key]['wins'] += 1 if t.is_win else 0
            monthly[key]['pnl'] += t.realized_pnl

        # Day-of-week breakdown
        dow = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri'}
        dow_stats = {}
        for t in self.trades:
            d = dow.get(t.entry_date.weekday(), '?')
            if d not in dow_stats:
                dow_stats[d] = {'trades': 0, 'wins': 0, 'pnl': 0}
            dow_stats[d]['trades'] += 1
            dow_stats[d]['wins'] += 1 if t.is_win else 0
            dow_stats[d]['pnl'] += t.realized_pnl

        # VIX regime breakdown
        vix_buckets = {'<15': [], '15-20': [], '20-25': [], '25-30': [], '30+': []}
        for t in self.trades:
            v = t.vix_at_entry
            if v < 15:
                vix_buckets['<15'].append(t)
            elif v < 20:
                vix_buckets['15-20'].append(t)
            elif v < 25:
                vix_buckets['20-25'].append(t)
            elif v < 30:
                vix_buckets['25-30'].append(t)
            else:
                vix_buckets['30+'].append(t)

        # Print
        print(f"\n{'='*70}")
        print(f"  FORTRESS BACKTEST RESULTS")
        print(f"{'='*70}")

        print(f"\n--- PARAMETERS ---")
        print(f"  Ticker:        {self.config.ticker}")
        print(f"  SD Multiplier: {self.config.sd_multiplier}")
        print(f"  Spread Width:  ${self.config.spread_width}")
        print(f"  Min DTE:       {self.config.min_dte_trading_days} trading days")
        print(f"  Pricing:       {'Mid' if self.config.use_mid_price else 'Bid/Ask (realistic)'}")
        first = self.trades[0].entry_date
        last = self.trades[-1].entry_date
        print(f"  Period:        {first} → {last}")

        print(f"\n--- OVERALL PERFORMANCE ---")
        print(f"  Total Trades:     {len(self.trades)}")
        print(f"  Win Rate:         {len(wins)/len(self.trades)*100:.1f}%")
        print(f"  Total P&L:        ${total_pnl:>12,.2f}")
        print(f"  Return on Cap:    {total_pnl/self.config.initial_capital*100:>8.1f}%")
        print(f"  Max Drawdown:     ${max_dd:>12,.2f}")
        if win_pnls:
            print(f"  Avg Win:          ${np.mean(win_pnls):>12,.2f}")
        if loss_pnls:
            print(f"  Avg Loss:         ${np.mean(loss_pnls):>12,.2f}")
        if win_pnls and loss_pnls:
            profit_factor = sum(win_pnls) / abs(sum(loss_pnls)) if sum(loss_pnls) != 0 else float('inf')
            print(f"  Profit Factor:    {profit_factor:>12.2f}")
            expectancy = np.mean([t.realized_pnl for t in self.trades])
            print(f"  Expectancy:       ${expectancy:>12,.2f}")

        print(f"\n--- EXIT REASONS ---")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            pct = count / len(self.trades) * 100
            pnl_for_reason = sum(t.realized_pnl for t in self.trades if t.exit_reason == reason)
            print(f"  {reason:25s} {count:>5} ({pct:5.1f}%)  P&L: ${pnl_for_reason:>10,.2f}")

        print(f"\n--- DAY OF WEEK ---")
        for d in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']:
            if d in dow_stats:
                s = dow_stats[d]
                wr = s['wins'] / s['trades'] * 100 if s['trades'] else 0
                print(f"  {d}: {s['trades']:>4} trades, {wr:5.1f}% WR, ${s['pnl']:>10,.2f} P&L")

        print(f"\n--- VIX REGIME ---")
        for bucket in ['<15', '15-20', '20-25', '25-30', '30+']:
            trades_in = vix_buckets[bucket]
            if trades_in:
                wr = sum(1 for t in trades_in if t.is_win) / len(trades_in) * 100
                pnl = sum(t.realized_pnl for t in trades_in)
                print(f"  VIX {bucket:>5}: {len(trades_in):>4} trades, {wr:5.1f}% WR, ${pnl:>10,.2f} P&L")

        print(f"\n--- MONTHLY BREAKDOWN (Last 12) ---")
        sorted_months = sorted(monthly.keys())[-12:]
        for m in sorted_months:
            s = monthly[m]
            wr = s['wins'] / s['trades'] * 100 if s['trades'] else 0
            print(f"  {m}: {s['trades']:>3} trades, {wr:5.1f}% WR, ${s['pnl']:>10,.2f}")

        print(f"\n--- PREMIUM ANALYSIS ---")
        credits = [t.total_credit for t in self.trades]
        print(f"  Avg Credit:       ${np.mean(credits):.4f}")
        print(f"  Min Credit:       ${np.min(credits):.4f}")
        print(f"  Max Credit:       ${np.max(credits):.4f}")
        print(f"  Avg Contracts:    {np.mean([t.contracts for t in self.trades]):.1f}")
        print(f"  Avg EM:           ${np.mean([t.expected_move for t in self.trades]):.2f}")

        print(f"\n--- SKIP ANALYSIS ---")
        print(f"  Total Skipped Days: {len(self.skipped_days)}")
        skip_reasons = {}
        for s in self.skipped_days:
            r = s['reason'].split(' ')[0]
            skip_reasons[r] = skip_reasons.get(r, 0) + 1
        for r, c in sorted(skip_reasons.items(), key=lambda x: -x[1])[:10]:
            print(f"    {r}: {c}")

        # Sample trades
        print(f"\n--- SAMPLE TRADES (First 5) ---")
        for t in self.trades[:5]:
            flag = 'W' if t.is_win else 'L'
            print(f"  [{flag}] {t.entry_date} → {t.exit_date} | "
                  f"Spot=${t.spot_at_entry:.2f} VIX={t.vix_at_entry:.1f} EM=${t.expected_move:.2f} | "
                  f"P{t.short_put}/{t.long_put} C{t.short_call}/{t.long_call} | "
                  f"Credit=${t.total_credit:.4f} x{t.contracts} | "
                  f"{t.exit_reason} → ${t.realized_pnl:+,.2f}")

        if losses:
            print(f"\n--- WORST 5 LOSSES ---")
            worst = sorted(self.trades, key=lambda t: t.realized_pnl)[:5]
            for t in worst:
                print(f"  {t.entry_date} → {t.exit_date} | "
                      f"Spot=${t.spot_at_entry:.2f} VIX={t.vix_at_entry:.1f} | "
                      f"P{t.short_put} C{t.short_call} | "
                      f"{t.exit_reason} → ${t.realized_pnl:+,.2f}")

        print(f"\n{'='*70}")


# ============================================================================
# DTE SWEEP
# ============================================================================

def run_dte_sweep(db_url: str = DEFAULT_DB_URL):
    """Run backtest across multiple DTE values for comparison."""
    print(f"\n{'='*70}")
    print(f"  FORTRESS DTE SWEEP")
    print(f"{'='*70}\n")

    results = []
    for dte in [0, 1, 2, 3, 4, 5]:
        config = BacktestConfig(min_dte_trading_days=dte)
        bt = FortressBacktest(config, db_url)
        bt.loader.connect()
        try:
            bt._run_backtest()
        finally:
            bt.loader.close()

        total_pnl = sum(t.realized_pnl for t in bt.trades)
        wins = sum(1 for t in bt.trades if t.is_win)
        n = len(bt.trades)
        wr = wins / n * 100 if n else 0

        # Max drawdown
        running = 0
        peak = 0
        max_dd = 0
        for t in bt.trades:
            running += t.realized_pnl
            peak = max(peak, running)
            max_dd = max(max_dd, peak - running)

        results.append({
            'dte': dte,
            'trades': n,
            'win_rate': wr,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / n if n else 0,
            'max_dd': max_dd,
            'return_pct': total_pnl / config.initial_capital * 100,
            'avg_credit': np.mean([t.total_credit for t in bt.trades]) if bt.trades else 0,
        })

    print(f"\n{'DTE':>4} | {'Trades':>7} | {'Win%':>6} | {'Total P&L':>12} | {'Return%':>8} | {'MaxDD':>10} | {'AvgCredit':>10}")
    print(f"{'-'*4}-+-{'-'*7}-+-{'-'*6}-+-{'-'*12}-+-{'-'*8}-+-{'-'*10}-+-{'-'*10}")
    for r in results:
        print(f"{r['dte']:>4} | {r['trades']:>7} | {r['win_rate']:>5.1f}% | ${r['total_pnl']:>10,.2f} | {r['return_pct']:>7.1f}% | ${r['max_dd']:>8,.2f} | ${r['avg_credit']:>9.4f}")


# ============================================================================
# SD SWEEP
# ============================================================================

def run_sd_sweep(db_url: str = DEFAULT_DB_URL):
    """Run backtest across multiple SD multiplier values."""
    print(f"\n{'='*70}")
    print(f"  FORTRESS SD MULTIPLIER SWEEP")
    print(f"{'='*70}\n")

    results = []
    for sd in [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0]:
        config = BacktestConfig(sd_multiplier=sd)
        bt = FortressBacktest(config, db_url)
        bt.loader.connect()
        try:
            bt._run_backtest()
        finally:
            bt.loader.close()

        total_pnl = sum(t.realized_pnl for t in bt.trades)
        wins = sum(1 for t in bt.trades if t.is_win)
        n = len(bt.trades)
        wr = wins / n * 100 if n else 0

        running = 0
        peak = 0
        max_dd = 0
        for t in bt.trades:
            running += t.realized_pnl
            peak = max(peak, running)
            max_dd = max(max_dd, peak - running)

        results.append({
            'sd': sd,
            'trades': n,
            'win_rate': wr,
            'total_pnl': total_pnl,
            'max_dd': max_dd,
            'return_pct': total_pnl / config.initial_capital * 100,
            'avg_credit': np.mean([t.total_credit for t in bt.trades]) if bt.trades else 0,
        })

    print(f"\n{'SD':>5} | {'Trades':>7} | {'Win%':>6} | {'Total P&L':>12} | {'Return%':>8} | {'MaxDD':>10} | {'AvgCredit':>10}")
    print(f"{'-'*5}-+-{'-'*7}-+-{'-'*6}-+-{'-'*12}-+-{'-'*8}-+-{'-'*10}-+-{'-'*10}")
    for r in results:
        print(f"{r['sd']:>5.1f} | {r['trades']:>7} | {r['win_rate']:>5.1f}% | ${r['total_pnl']:>10,.2f} | {r['return_pct']:>7.1f}% | ${r['max_dd']:>8,.2f} | ${r['avg_credit']:>9.4f}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='FORTRESS Backtest Engine')
    parser.add_argument('--ticker', default='SPY', help='Ticker (SPY or SPX)')
    parser.add_argument('--sd-multiplier', type=float, default=1.2, help='SD multiplier (default: 1.2)')
    parser.add_argument('--spread-width', type=float, default=5.0, help='Spread width (default: $5)')
    parser.add_argument('--min-dte', type=int, default=3, help='Min DTE in trading days (default: 3)')
    parser.add_argument('--risk-pct', type=float, default=15.0, help='Risk per trade %% (default: 15)')
    parser.add_argument('--capital', type=float, default=100_000, help='Initial capital (default: $100K)')
    parser.add_argument('--max-vix', type=float, default=50.0, help='Max VIX filter (default: 50)')
    parser.add_argument('--profit-target', type=float, default=50.0, help='Profit target %% (default: 50)')
    parser.add_argument('--start-date', type=str, default=None, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, default=None, help='End date YYYY-MM-DD')
    parser.add_argument('--use-mid', action='store_true', help='Use mid prices (default: bid/ask)')
    parser.add_argument('--db-url', type=str, default=DEFAULT_DB_URL, help='Database URL')

    # Sweep modes
    parser.add_argument('--dte-sweep', action='store_true', help='Run DTE sweep (0-5)')
    parser.add_argument('--sd-sweep', action='store_true', help='Run SD multiplier sweep')

    args = parser.parse_args()

    if args.dte_sweep:
        run_dte_sweep(args.db_url)
        return

    if args.sd_sweep:
        run_sd_sweep(args.db_url)
        return

    config = BacktestConfig(
        ticker=args.ticker,
        sd_multiplier=args.sd_multiplier,
        spread_width=args.spread_width,
        min_dte_trading_days=args.min_dte,
        risk_per_trade_pct=args.risk_pct,
        initial_capital=args.capital,
        max_vix=args.max_vix,
        profit_target_pct=args.profit_target,
        start_date=args.start_date,
        end_date=args.end_date,
        use_mid_price=args.use_mid,
    )

    bt = FortressBacktest(config, args.db_url)
    bt.run()


if __name__ == '__main__':
    main()
