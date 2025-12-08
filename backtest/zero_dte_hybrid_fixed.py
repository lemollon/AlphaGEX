#!/usr/bin/env python3
"""
HYBRID SCALING Strategy - FIXED VERSION

Key fix: All trades are DAY TRADES (enter and exit same day)
- Use longer DTE options for LIQUIDITY, not for holding
- Strike selection uses appropriate SD for the DTE
- Settlement is same-day close (now correct since we exit same day)

STRATEGY LOGIC:
===============
- 0DTE: 1-day expected move = Price × IV × √(1/252)
- Weekly: 7-day expected move = Price × IV × √(7/252) → ~2.6x wider strikes
- Monthly: 30-day expected move = Price × IV × √(30/252) → ~5.5x wider strikes

WHY THIS WORKS:
- Longer DTE = more liquidity = can trade bigger size
- Wider strikes = lower probability of breach on single day
- Day-trade = capture theta decay + avoid overnight risk
- Exit EOD = known settlement, no gap risk

Usage:
    python backtest/zero_dte_hybrid_fixed.py --start 2021-01-01 --end 2025-12-01
"""

import os
import sys
import argparse
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("Warning: yfinance not installed")


@dataclass
class ScalingTier:
    """Configuration for each account size tier"""
    name: str
    min_equity: float
    max_equity: float
    target_dte: int  # Target DTE for liquidity
    sd_days: int  # Days to use for SD calculation
    max_contracts: int
    trades_per_week: int
    commission_per_leg: float
    slippage_per_spread: float


# Define scaling tiers with CORRECT SD calculations
SCALING_TIERS = [
    ScalingTier(
        name="TIER_1_0DTE",
        min_equity=0,
        max_equity=2_000_000,
        target_dte=0,  # 0DTE options
        sd_days=1,     # 1-day SD: √(1/252)
        max_contracts=100,
        trades_per_week=5,
        commission_per_leg=0.65,
        slippage_per_spread=0.15,  # Higher slippage on 0DTE
    ),
    ScalingTier(
        name="TIER_2_WEEKLY",
        min_equity=2_000_000,
        max_equity=5_000_000,
        target_dte=7,  # Weekly options
        sd_days=7,     # 7-day SD: √(7/252)
        max_contracts=300,
        trades_per_week=5,
        commission_per_leg=0.65,
        slippage_per_spread=0.10,  # Better fills on weeklies
    ),
    ScalingTier(
        name="TIER_3_MONTHLY",
        min_equity=5_000_000,
        max_equity=15_000_000,
        target_dte=30,  # Monthly options
        sd_days=30,     # 30-day SD: √(30/252)
        max_contracts=500,
        trades_per_week=3,
        commission_per_leg=0.65,
        slippage_per_spread=0.08,
    ),
    ScalingTier(
        name="TIER_4_LARGE",
        min_equity=15_000_000,
        max_equity=float('inf'),
        target_dte=45,  # 45 DTE for max liquidity
        sd_days=30,     # Still use 30-day SD (don't go too wide)
        max_contracts=1000,
        trades_per_week=2,
        commission_per_leg=0.50,
        slippage_per_spread=0.05,
    ),
]


@dataclass
class DayTrade:
    """Single day trade with proper SD calculation"""
    trade_date: str
    trade_number: int

    # Tier info
    tier_name: str
    account_equity: float
    target_dte: int
    actual_dte: int
    sd_days_used: int

    # Market context
    vix: float
    open_price: float
    close_price: float
    daily_high: float
    daily_low: float
    underlying_price: float

    # Expected move calculation
    iv_used: float
    expected_move_1d: float  # 1-day move for reference
    expected_move_sd: float  # Actual SD used for strikes
    sd_multiplier: float

    # Put spread
    put_short_strike: float
    put_long_strike: float
    put_credit_gross: float
    put_credit_net: float
    put_distance_from_open: float  # How far OTM

    # Call spread
    call_short_strike: float
    call_long_strike: float
    call_credit_gross: float
    call_credit_net: float
    call_distance_from_open: float

    # Combined
    total_credit_gross: float
    total_credit_net: float
    spread_width: float
    max_loss: float

    # Costs
    total_costs: float

    # Sizing
    contracts: int
    contracts_requested: int
    total_premium: float
    total_risk: float
    risk_pct: float

    # P&L
    put_pnl: float = 0
    call_pnl: float = 0
    gross_pnl: float = 0
    net_pnl: float = 0
    return_pct: float = 0

    # Outcome
    outcome: str = ""
    put_breached: bool = False
    call_breached: bool = False
    intraday_put_threat: bool = False  # Did price threaten put strike intraday?
    intraday_call_threat: bool = False


class HybridFixedBacktester:
    """
    FIXED hybrid strategy - all trades are day trades.

    Uses longer DTE for liquidity but exits same day.
    Strike selection uses appropriate SD for the DTE timeframe.

    ENHANCED with:
    - Multi-leg strategy types (Iron Condor, Bull Put, Bear Call, Iron Butterfly)
    - VIX filtering (min/max)
    - Stop loss and profit targets
    - Trading day selection
    - Risk metrics (Sharpe, Sortino)
    - Equity curve tracking
    """

    def __init__(
        self,
        start_date: str = "2021-01-01",
        end_date: str = None,
        initial_capital: float = 1_000_000,
        spread_width: float = 10.0,
        sd_multiplier: float = 1.0,
        risk_per_trade_pct: float = 5.0,
        ticker: str = "SPX",
        # New parameters
        strategy_type: str = "iron_condor",  # iron_condor, bull_put, bear_call, iron_butterfly, diagonal_call, diagonal_put
        min_vix: float = None,
        max_vix: float = None,
        stop_loss_pct: float = None,  # % of max loss to trigger stop
        profit_target_pct: float = None,  # % of credit to take profit
        trade_days: List[int] = None,  # 0=Mon, 4=Fri, None=all weekdays
        max_contracts_override: int = None,
        commission_per_leg_override: float = None,
        slippage_per_spread_override: float = None,
        # Strike selection method
        strike_selection: str = "sd",  # sd, fixed, delta
        fixed_strike_distance: float = 50.0,  # For fixed method: points from price
        target_delta: float = 0.16,  # For delta method: target delta for short strikes
    ):
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        self.initial_capital = initial_capital
        self.spread_width = spread_width
        self.sd_multiplier = sd_multiplier
        self.risk_per_trade_pct = risk_per_trade_pct
        self.ticker = ticker

        # New parameters
        self.strategy_type = strategy_type
        self.min_vix = min_vix
        self.max_vix = max_vix
        self.stop_loss_pct = stop_loss_pct
        self.profit_target_pct = profit_target_pct
        self.trade_days = trade_days if trade_days is not None else [0, 1, 2, 3, 4]
        self.max_contracts_override = max_contracts_override
        self.commission_per_leg_override = commission_per_leg_override
        self.slippage_per_spread_override = slippage_per_spread_override

        # Strike selection
        self.strike_selection = strike_selection
        self.fixed_strike_distance = fixed_strike_distance
        self.target_delta = target_delta

        # State
        self.equity = initial_capital
        self.high_water_mark = initial_capital

        # Tracking
        self.all_trades: List[DayTrade] = []
        self.trade_counter = 0

        # Equity curve tracking
        self.equity_curve: List[Dict] = []
        self.daily_returns: List[float] = []

        # Stats by tier
        self.tier_stats = {tier.name: {'trades': 0, 'pnl': 0, 'wins': 0, 'losses': 0}
                          for tier in SCALING_TIERS}

        # Stats by day of week
        self.day_of_week_stats = {i: {'trades': 0, 'pnl': 0, 'wins': 0} for i in range(5)}

        # Stats by VIX level
        self.vix_level_stats = {
            'low': {'trades': 0, 'pnl': 0, 'wins': 0},      # VIX < 15
            'medium': {'trades': 0, 'pnl': 0, 'wins': 0},   # 15 <= VIX < 25
            'high': {'trades': 0, 'pnl': 0, 'wins': 0},     # VIX >= 25
        }

        # Weekly trade counter
        self.current_week = None
        self.trades_this_week = 0

        # Costs tracking
        self.total_commissions = 0
        self.total_slippage = 0

        # Consecutive loss tracking
        self.current_consecutive_losses = 0
        self.max_consecutive_losses = 0

        # VIX filter skip count
        self.vix_filter_skips = 0

        # Cache
        self.spx_ohlc: Dict[str, Dict] = {}
        self.vix_data: Dict[str, float] = {}

    def get_connection(self):
        from database_adapter import get_connection
        return get_connection()

    def get_current_tier(self) -> ScalingTier:
        """Get appropriate tier based on current equity"""
        for tier in SCALING_TIERS:
            if tier.min_equity <= self.equity < tier.max_equity:
                return tier
        return SCALING_TIERS[-1]

    def calculate_expected_move(self, price: float, iv: float, days: int) -> float:
        """
        Calculate expected move for given number of days.

        Formula: Expected Move = Price × IV × √(days/252)

        Examples at IV=20%, Price=$5000:
        - 1 day:  $5000 × 0.20 × √(1/252)  = $63 (1.3%)
        - 7 days: $5000 × 0.20 × √(7/252)  = $167 (3.3%)
        - 30 days: $5000 × 0.20 × √(30/252) = $345 (6.9%)
        """
        return price * iv * math.sqrt(days / 252)

    def calculate_strike_distance(self, price: float, iv: float, days: int,
                                  options: List[Dict] = None, direction: str = "put") -> float:
        """
        Calculate strike distance based on selected method.

        Methods:
        - sd: Use SD multiplier × expected move
        - fixed: Use fixed point distance
        - delta: Find strike at target delta

        Args:
            price: Current underlying price
            iv: Implied volatility (decimal)
            days: Days for SD calculation
            options: Options chain (needed for delta method)
            direction: "put" or "call" (for delta method)

        Returns:
            Strike distance in points
        """
        if self.strike_selection == "fixed":
            return self.fixed_strike_distance

        elif self.strike_selection == "delta" and options:
            # Find the strike with delta closest to target
            target = self.target_delta
            if direction == "put":
                # For puts, look for negative delta close to -target
                candidates = [o for o in options if o.get('delta') is not None
                             and o['strike'] < price]
                if candidates:
                    # Find put with delta closest to -target_delta
                    best = min(candidates, key=lambda x: abs(abs(x.get('delta', 0)) - target))
                    return price - best['strike']
            else:
                # For calls, look for positive delta close to target
                candidates = [o for o in options if o.get('delta') is not None
                             and o['strike'] > price]
                if candidates:
                    best = min(candidates, key=lambda x: abs(x.get('delta', 0) - target))
                    return best['strike'] - price

            # Fall back to SD if delta not found
            expected_move = self.calculate_expected_move(price, iv, days)
            return self.sd_multiplier * expected_move

        else:  # Default: SD method
            expected_move = self.calculate_expected_move(price, iv, days)
            return self.sd_multiplier * expected_move

    def should_trade_today(self, trade_date: str, tier: ScalingTier, vix: float = None) -> bool:
        """Determine if we should trade today based on tier frequency, VIX filter, and trade days"""
        dt = datetime.strptime(trade_date, '%Y-%m-%d')
        weekday = dt.weekday()

        # Check if this day of week is enabled for trading
        if weekday not in self.trade_days:
            return False

        # VIX filter
        if vix is not None:
            if self.min_vix is not None and vix < self.min_vix:
                self.vix_filter_skips += 1
                return False
            if self.max_vix is not None and vix > self.max_vix:
                self.vix_filter_skips += 1
                return False

        week_num = dt.isocalendar()[1]
        if self.current_week != week_num:
            self.current_week = week_num
            self.trades_this_week = 0

        if self.trades_this_week >= tier.trades_per_week:
            return False

        if tier.trades_per_week == 5:
            return weekday < 5
        elif tier.trades_per_week == 3:
            return weekday in [0, 2, 4]
        elif tier.trades_per_week == 2:
            return weekday in [1, 3]
        return False

    def load_market_data(self):
        """Load SPX and VIX data - first from DB, then from Yahoo API"""
        start = datetime.strptime(self.start_date, '%Y-%m-%d') - timedelta(days=10)
        end = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=5)
        start_str = start.strftime('%Y-%m-%d')
        end_str = end.strftime('%Y-%m-%d')

        # Try loading from database first
        db_loaded = self._load_market_data_from_db(start_str, end_str)

        if db_loaded:
            return

        # Fall back to direct Yahoo Finance API (no yfinance library needed)
        print("  Loading market data from Yahoo Finance API...")
        self._load_market_data_from_yahoo(start_str, end_str)

    def _load_market_data_from_db(self, start_str: str, end_str: str) -> bool:
        """Load market data from stored database. Returns True if successful."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Check if table exists and has data
            cursor.execute("""
                SELECT COUNT(*) FROM market_data_daily
                WHERE symbol = 'SPX' AND date >= %s AND date <= %s
            """, (start_str, end_str))
            spx_count = cursor.fetchone()[0]

            if spx_count == 0:
                conn.close()
                return False

            # Load SPX data
            cursor.execute("""
                SELECT date, open, high, low, close
                FROM market_data_daily
                WHERE symbol = 'SPX' AND date >= %s AND date <= %s
                ORDER BY date
            """, (start_str, end_str))

            for row in cursor.fetchall():
                date_str = row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0])
                self.spx_ohlc[date_str] = {
                    'open': float(row[1]) if row[1] else 0,
                    'high': float(row[2]) if row[2] else 0,
                    'low': float(row[3]) if row[3] else 0,
                    'close': float(row[4]) if row[4] else 0,
                }

            print(f"  Loaded {len(self.spx_ohlc)} days of SPX data from database")

            # Load VIX data
            cursor.execute("""
                SELECT date, close
                FROM market_data_daily
                WHERE symbol = 'VIX' AND date >= %s AND date <= %s
                ORDER BY date
            """, (start_str, end_str))

            for row in cursor.fetchall():
                date_str = row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0])
                self.vix_data[date_str] = float(row[1]) if row[1] else 0

            print(f"  Loaded {len(self.vix_data)} days of VIX data from database")

            conn.close()
            return len(self.spx_ohlc) > 0

        except Exception as e:
            print(f"  Database load failed: {e}, falling back to Yahoo...")
            return False

    def _load_market_data_from_yahoo(self, start_str: str, end_str: str):
        """Load market data directly from Yahoo Finance API (no yfinance needed)"""
        import requests

        def fetch_yahoo_data(symbol: str, start: str, end: str) -> List[Dict]:
            """Fetch data from Yahoo Finance API"""
            start_ts = int(datetime.strptime(start, "%Y-%m-%d").timestamp())
            end_ts = int(datetime.strptime(end, "%Y-%m-%d").timestamp())

            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "period1": start_ts,
                "period2": end_ts,
                "interval": "1d",
                "events": "history"
            }
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

            try:
                response = requests.get(url, params=params, headers=headers, timeout=30)
                if response.status_code != 200:
                    return []

                data = response.json()
                result = data.get("chart", {}).get("result", [])
                if not result:
                    return []

                chart_data = result[0]
                timestamps = chart_data.get("timestamp", [])
                quote = chart_data.get("indicators", {}).get("quote", [{}])[0]

                records = []
                for i, ts in enumerate(timestamps):
                    try:
                        date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                        open_p = quote.get("open", [])[i]
                        high_p = quote.get("high", [])[i]
                        low_p = quote.get("low", [])[i]
                        close_p = quote.get("close", [])[i]

                        if any(p is None for p in [open_p, high_p, low_p, close_p]):
                            continue

                        records.append({
                            "date": date,
                            "open": float(open_p),
                            "high": float(high_p),
                            "low": float(low_p),
                            "close": float(close_p)
                        })
                    except (IndexError, TypeError):
                        continue

                return records
            except Exception as e:
                print(f"  Yahoo API error for {symbol}: {e}")
                return []

        # Fetch SPX
        spx_data = fetch_yahoo_data("^GSPC", start_str, end_str)
        for rec in spx_data:
            self.spx_ohlc[rec["date"]] = {
                'open': rec["open"],
                'high': rec["high"],
                'low': rec["low"],
                'close': rec["close"],
            }
        print(f"  Loaded {len(self.spx_ohlc)} days of SPX data from Yahoo API")

        # Fetch VIX
        vix_data = fetch_yahoo_data("^VIX", start_str, end_str)
        for rec in vix_data:
            self.vix_data[rec["date"]] = rec["close"]
        print(f"  Loaded {len(self.vix_data)} days of VIX data from Yahoo API")

    def get_trading_days(self) -> List[str]:
        """Get all trading days"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT trade_date
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date >= %s
              AND trade_date <= %s
            ORDER BY trade_date
        """, (self.ticker, self.start_date, self.end_date))

        days = [row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()]
        conn.close()
        return days

    def get_options_for_date(self, trade_date: str, target_dte: int) -> List[Dict]:
        """Get options near target DTE"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get options within range of target DTE
        min_dte = max(0, target_dte - 3)
        max_dte = target_dte + 7

        cursor.execute("""
            SELECT
                strike, underlying_price, dte,
                put_bid, put_ask, call_bid, call_ask,
                delta, put_iv, call_iv
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date = %s
              AND dte >= %s
              AND dte <= %s
            ORDER BY ABS(dte - %s), strike
        """, (self.ticker, trade_date, min_dte, max_dte, target_dte))

        columns = ['strike', 'underlying_price', 'dte', 'put_bid', 'put_ask',
                   'call_bid', 'call_ask', 'delta', 'put_iv', 'call_iv']

        options = []
        for row in cursor.fetchall():
            opt = dict(zip(columns, row))
            for key in opt:
                if opt[key] is not None and key != 'dte':
                    opt[key] = float(opt[key])
            options.append(opt)

        conn.close()
        return options

    def find_bull_put_spread(self, options: List[Dict], open_price: float,
                             strike_distance: float, target_dte: int,
                             use_raw_distance: bool = False) -> Optional[Dict]:
        """Find Bull Put Spread only (put credit spread)"""
        if not options:
            return None

        available_dtes = list(set(o['dte'] for o in options))
        if not available_dtes:
            return None

        actual_dte = min(available_dtes, key=lambda x: abs(x - target_dte))
        dte_options = [o for o in options if o['dte'] == actual_dte]

        if not dte_options:
            return None

        underlying = dte_options[0]['underlying_price']

        # Target put strike at specified distance below open
        if use_raw_distance:
            put_target = open_price - strike_distance
        else:
            put_target = open_price - (self.sd_multiplier * strike_distance)
        put_target = round(put_target / 5) * 5

        # Find OTM puts
        otm_puts = [o for o in dte_options if o['strike'] < underlying
                   and o.get('put_bid', 0) and o['put_bid'] > 0.05]

        if not otm_puts:
            return None

        # Short put at target
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - put_target))

        # Long put below
        long_put_strike = short_put['strike'] - self.spread_width
        long_put_candidates = [o for o in dte_options
                              if abs(o['strike'] - long_put_strike) < 2
                              and o.get('put_ask', 0) and o['put_ask'] > 0]
        if not long_put_candidates:
            return None
        long_put = min(long_put_candidates, key=lambda x: abs(x['strike'] - long_put_strike))

        put_credit = (short_put.get('put_bid', 0) or 0) - (long_put.get('put_ask', 0) or 0)
        if put_credit <= 0:
            return None

        return {
            'actual_dte': actual_dte,
            'put_short_strike': short_put['strike'],
            'put_long_strike': long_put['strike'],
            'put_credit': put_credit,
            'call_short_strike': 0,
            'call_long_strike': 0,
            'call_credit': 0,
            'total_credit': put_credit,
            'strategy_type': 'bull_put'
        }

    def find_bear_call_spread(self, options: List[Dict], open_price: float,
                              strike_distance: float, target_dte: int,
                              use_raw_distance: bool = False) -> Optional[Dict]:
        """Find Bear Call Spread only (call credit spread)"""
        if not options:
            return None

        available_dtes = list(set(o['dte'] for o in options))
        if not available_dtes:
            return None

        actual_dte = min(available_dtes, key=lambda x: abs(x - target_dte))
        dte_options = [o for o in options if o['dte'] == actual_dte]

        if not dte_options:
            return None

        underlying = dte_options[0]['underlying_price']

        # Target call strike at specified distance above open
        if use_raw_distance:
            call_target = open_price + strike_distance
        else:
            call_target = open_price + (self.sd_multiplier * strike_distance)
        call_target = round(call_target / 5) * 5

        # Find OTM calls
        otm_calls = [o for o in dte_options if o['strike'] > underlying
                    and o.get('call_bid', 0) and o['call_bid'] > 0.05]

        if not otm_calls:
            return None

        # Short call at target
        short_call = min(otm_calls, key=lambda x: abs(x['strike'] - call_target))

        # Long call above
        long_call_strike = short_call['strike'] + self.spread_width
        long_call_candidates = [o for o in dte_options
                               if abs(o['strike'] - long_call_strike) < 2
                               and o.get('call_ask', 0) and o['call_ask'] > 0]
        if not long_call_candidates:
            return None
        long_call = min(long_call_candidates, key=lambda x: abs(x['strike'] - long_call_strike))

        call_credit = (short_call.get('call_bid', 0) or 0) - (long_call.get('call_ask', 0) or 0)
        if call_credit <= 0:
            return None

        return {
            'actual_dte': actual_dte,
            'put_short_strike': 0,
            'put_long_strike': 0,
            'put_credit': 0,
            'call_short_strike': short_call['strike'],
            'call_long_strike': long_call['strike'],
            'call_credit': call_credit,
            'total_credit': call_credit,
            'strategy_type': 'bear_call'
        }

    def find_iron_butterfly(self, options: List[Dict], open_price: float,
                            expected_move: float, target_dte: int) -> Optional[Dict]:
        """Find Iron Butterfly (ATM short straddle + OTM wings)"""
        if not options:
            return None

        available_dtes = list(set(o['dte'] for o in options))
        if not available_dtes:
            return None

        actual_dte = min(available_dtes, key=lambda x: abs(x - target_dte))
        dte_options = [o for o in options if o['dte'] == actual_dte]

        if not dte_options:
            return None

        underlying = dte_options[0]['underlying_price']

        # ATM strike (center strike)
        atm_strike = round(open_price / 5) * 5

        # Find ATM options for short straddle
        atm_options = [o for o in dte_options if abs(o['strike'] - atm_strike) < 2]
        if not atm_options:
            return None

        atm = atm_options[0]

        # Short put and call at ATM
        short_put_credit = atm.get('put_bid', 0) or 0
        short_call_credit = atm.get('call_bid', 0) or 0

        # Long put below (wing)
        long_put_strike = atm_strike - self.spread_width
        long_put_candidates = [o for o in dte_options
                              if abs(o['strike'] - long_put_strike) < 2
                              and o.get('put_ask', 0) and o['put_ask'] > 0]
        if not long_put_candidates:
            return None
        long_put = min(long_put_candidates, key=lambda x: abs(x['strike'] - long_put_strike))

        # Long call above (wing)
        long_call_strike = atm_strike + self.spread_width
        long_call_candidates = [o for o in dte_options
                               if abs(o['strike'] - long_call_strike) < 2
                               and o.get('call_ask', 0) and o['call_ask'] > 0]
        if not long_call_candidates:
            return None
        long_call = min(long_call_candidates, key=lambda x: abs(x['strike'] - long_call_strike))

        # Calculate credits
        put_credit = short_put_credit - (long_put.get('put_ask', 0) or 0)
        call_credit = short_call_credit - (long_call.get('call_ask', 0) or 0)
        total_credit = put_credit + call_credit

        if total_credit <= 0:
            return None

        return {
            'actual_dte': actual_dte,
            'put_short_strike': atm_strike,
            'put_long_strike': long_put['strike'],
            'put_credit': put_credit,
            'call_short_strike': atm_strike,
            'call_long_strike': long_call['strike'],
            'call_credit': call_credit,
            'total_credit': total_credit,
            'strategy_type': 'iron_butterfly'
        }

    def find_diagonal_call(self, options: List[Dict], open_price: float,
                           strike_distance: float, target_dte: int,
                           use_raw_distance: bool = False) -> Optional[Dict]:
        """
        Find Diagonal Call Spread (Poor Man's Covered Call)

        - Sell near-term OTM call at specified distance above price
        - Buy longer-term call for protection (same or lower strike)

        This is a DEBIT spread with defined risk.
        Profits from: time decay on short leg, price staying below short strike
        """
        if not options:
            return None

        available_dtes = sorted(set(o['dte'] for o in options))
        if len(available_dtes) < 2:
            return None  # Need at least 2 different DTEs for diagonal

        # Short leg: near-term (closest to target_dte, usually 0-7 DTE)
        short_dte = min(available_dtes, key=lambda x: abs(x - target_dte))

        # Long leg: longer-term (at least 14 days out, preferably 30+)
        long_dte_candidates = [d for d in available_dtes if d >= short_dte + 14]
        if not long_dte_candidates:
            # Fall back to just finding something longer
            long_dte_candidates = [d for d in available_dtes if d > short_dte]
        if not long_dte_candidates:
            return None

        long_dte = min(long_dte_candidates)  # Take the nearest long-term option

        short_dte_options = [o for o in options if o['dte'] == short_dte]
        long_dte_options = [o for o in options if o['dte'] == long_dte]

        if not short_dte_options or not long_dte_options:
            return None

        underlying = short_dte_options[0]['underlying_price']

        # Short call strike at specified distance above open (OTM)
        if use_raw_distance:
            call_target = open_price + strike_distance
        else:
            call_target = open_price + (self.sd_multiplier * strike_distance)
        call_target = round(call_target / 5) * 5

        # Find OTM calls for short leg
        otm_calls_short = [o for o in short_dte_options if o['strike'] > underlying
                          and o.get('call_bid', 0) and o['call_bid'] > 0.05]

        if not otm_calls_short:
            return None

        # Short call at target SD
        short_call = min(otm_calls_short, key=lambda x: abs(x['strike'] - call_target))

        # Long call: ATM or slightly ITM for protection (same strike or lower)
        long_call_target = short_call['strike']  # Same strike = calendar, lower = true diagonal
        long_call_candidates = [o for o in long_dte_options
                               if o['strike'] <= long_call_target
                               and o.get('call_ask', 0) and o['call_ask'] > 0]

        if not long_call_candidates:
            return None

        # Pick the highest strike that's at or below short strike
        long_call = max(long_call_candidates, key=lambda x: x['strike'])

        # Calculate debit (we pay for long, receive for short)
        short_premium = short_call.get('call_bid', 0) or 0
        long_premium = long_call.get('call_ask', 0) or 0

        net_debit = long_premium - short_premium  # Positive = we pay, Negative = credit

        # For diagonal, max loss is the net debit (if long has higher strike) or more complex
        # Simplified: max loss = net debit if debit, or spread width if credit
        if net_debit > 0:
            max_loss = net_debit
        else:
            max_loss = self.spread_width  # Approximate

        return {
            'actual_dte': short_dte,
            'long_dte': long_dte,
            'put_short_strike': 0,
            'put_long_strike': 0,
            'put_credit': 0,
            'call_short_strike': short_call['strike'],
            'call_long_strike': long_call['strike'],
            'call_credit': -net_debit,  # Negative debit = positive credit equivalent
            'total_credit': -net_debit,
            'max_loss_override': max_loss,
            'strategy_type': 'diagonal_call'
        }

    def find_diagonal_put(self, options: List[Dict], open_price: float,
                          strike_distance: float, target_dte: int,
                          use_raw_distance: bool = False) -> Optional[Dict]:
        """
        Find Diagonal Put Spread (Poor Man's Covered Put)

        - Sell near-term OTM put at specified distance below price
        - Buy longer-term put for protection (same or higher strike)

        This is typically a DEBIT spread with defined risk.
        Profits from: time decay on short leg, price staying above short strike
        """
        if not options:
            return None

        available_dtes = sorted(set(o['dte'] for o in options))
        if len(available_dtes) < 2:
            return None

        # Short leg: near-term
        short_dte = min(available_dtes, key=lambda x: abs(x - target_dte))

        # Long leg: longer-term (at least 14 days out)
        long_dte_candidates = [d for d in available_dtes if d >= short_dte + 14]
        if not long_dte_candidates:
            long_dte_candidates = [d for d in available_dtes if d > short_dte]
        if not long_dte_candidates:
            return None

        long_dte = min(long_dte_candidates)

        short_dte_options = [o for o in options if o['dte'] == short_dte]
        long_dte_options = [o for o in options if o['dte'] == long_dte]

        if not short_dte_options or not long_dte_options:
            return None

        underlying = short_dte_options[0]['underlying_price']

        # Short put strike at specified distance below open (OTM)
        if use_raw_distance:
            put_target = open_price - strike_distance
        else:
            put_target = open_price - (self.sd_multiplier * strike_distance)
        put_target = round(put_target / 5) * 5

        # Find OTM puts for short leg
        otm_puts_short = [o for o in short_dte_options if o['strike'] < underlying
                         and o.get('put_bid', 0) and o['put_bid'] > 0.05]

        if not otm_puts_short:
            return None

        # Short put at target SD
        short_put = min(otm_puts_short, key=lambda x: abs(x['strike'] - put_target))

        # Long put: ATM or slightly ITM for protection (same strike or higher)
        long_put_target = short_put['strike']
        long_put_candidates = [o for o in long_dte_options
                              if o['strike'] >= long_put_target
                              and o.get('put_ask', 0) and o['put_ask'] > 0]

        if not long_put_candidates:
            return None

        # Pick the lowest strike that's at or above short strike
        long_put = min(long_put_candidates, key=lambda x: x['strike'])

        # Calculate debit
        short_premium = short_put.get('put_bid', 0) or 0
        long_premium = long_put.get('put_ask', 0) or 0

        net_debit = long_premium - short_premium

        if net_debit > 0:
            max_loss = net_debit
        else:
            max_loss = self.spread_width

        return {
            'actual_dte': short_dte,
            'long_dte': long_dte,
            'put_short_strike': short_put['strike'],
            'put_long_strike': long_put['strike'],
            'put_credit': -net_debit,
            'call_short_strike': 0,
            'call_long_strike': 0,
            'call_credit': 0,
            'total_credit': -net_debit,
            'max_loss_override': max_loss,
            'strategy_type': 'diagonal_put'
        }

    def find_strategy(self, options: List[Dict], open_price: float,
                      expected_move: float, target_dte: int,
                      iv: float = 0.15, sd_days: int = 1) -> Optional[Dict]:
        """
        Find the appropriate strategy based on strategy_type setting.

        Strike selection is determined by self.strike_selection:
        - 'sd': Use expected_move × sd_multiplier (default behavior)
        - 'fixed': Use fixed_strike_distance points
        - 'delta': Find strikes by target delta
        """
        # Calculate actual strike distances based on strike selection method
        if self.strike_selection == 'fixed':
            # For fixed, we use the fixed distance directly
            put_distance = self.fixed_strike_distance
            call_distance = self.fixed_strike_distance
        elif self.strike_selection == 'delta':
            # For delta, calculate from options (if available)
            put_distance = self.calculate_strike_distance(open_price, iv, sd_days, options, "put")
            call_distance = self.calculate_strike_distance(open_price, iv, sd_days, options, "call")
        else:  # 'sd' - default
            # Use SD multiplier × expected move
            put_distance = self.sd_multiplier * expected_move
            call_distance = self.sd_multiplier * expected_move

        # Pass calculated distances to strategy finders
        if self.strategy_type == 'bull_put':
            return self.find_bull_put_spread(options, open_price, put_distance, target_dte, use_raw_distance=True)
        elif self.strategy_type == 'bear_call':
            return self.find_bear_call_spread(options, open_price, call_distance, target_dte, use_raw_distance=True)
        elif self.strategy_type == 'iron_butterfly':
            return self.find_iron_butterfly(options, open_price, expected_move, target_dte)
        elif self.strategy_type == 'diagonal_call':
            return self.find_diagonal_call(options, open_price, call_distance, target_dte, use_raw_distance=True)
        elif self.strategy_type == 'diagonal_put':
            return self.find_diagonal_put(options, open_price, put_distance, target_dte, use_raw_distance=True)
        else:  # iron_condor (default)
            return self.find_iron_condor(options, open_price, put_distance, call_distance, target_dte, use_raw_distance=True)

    def find_iron_condor(self, options: List[Dict], open_price: float,
                         put_distance: float, call_distance: float = None,
                         target_dte: int = 0, use_raw_distance: bool = False) -> Optional[Dict]:
        """
        Find Iron Condor with strikes at specified distance.

        Args:
            options: Options chain
            open_price: Opening price of underlying
            put_distance: Distance for put strike (if use_raw_distance=True, used directly)
            call_distance: Distance for call strike (defaults to put_distance)
            target_dte: Target days to expiration
            use_raw_distance: If True, use distances directly. If False, multiply by sd_multiplier.
        """
        if not options:
            return None

        if call_distance is None:
            call_distance = put_distance

        # Find options closest to target DTE
        available_dtes = list(set(o['dte'] for o in options))
        if not available_dtes:
            return None

        actual_dte = min(available_dtes, key=lambda x: abs(x - target_dte))
        dte_options = [o for o in options if o['dte'] == actual_dte]

        if not dte_options:
            return None

        underlying = dte_options[0]['underlying_price']

        # Target strikes at specified distance from OPEN price
        if use_raw_distance:
            put_target = open_price - put_distance
            call_target = open_price + call_distance
        else:
            put_target = open_price - (self.sd_multiplier * put_distance)
            call_target = open_price + (self.sd_multiplier * call_distance)

        put_target = round(put_target / 5) * 5
        call_target = round(call_target / 5) * 5

        # Find OTM options
        otm_puts = [o for o in dte_options if o['strike'] < underlying
                   and o.get('put_bid', 0) and o['put_bid'] > 0.05]
        otm_calls = [o for o in dte_options if o['strike'] > underlying
                    and o.get('call_bid', 0) and o['call_bid'] > 0.05]

        if not otm_puts or not otm_calls:
            return None

        # Short put at target
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - put_target))

        # Long put below
        long_put_strike = short_put['strike'] - self.spread_width
        long_put_candidates = [o for o in dte_options
                              if abs(o['strike'] - long_put_strike) < 2
                              and o.get('put_ask', 0) and o['put_ask'] > 0]
        if not long_put_candidates:
            return None
        long_put = min(long_put_candidates, key=lambda x: abs(x['strike'] - long_put_strike))

        # Short call at target
        short_call = min(otm_calls, key=lambda x: abs(x['strike'] - call_target))

        # Long call above
        long_call_strike = short_call['strike'] + self.spread_width
        long_call_candidates = [o for o in dte_options
                               if abs(o['strike'] - long_call_strike) < 2
                               and o.get('call_ask', 0) and o['call_ask'] > 0]
        if not long_call_candidates:
            return None
        long_call = min(long_call_candidates, key=lambda x: abs(x['strike'] - long_call_strike))

        # Calculate credits
        put_credit = (short_put.get('put_bid', 0) or 0) - (long_put.get('put_ask', 0) or 0)
        call_credit = (short_call.get('call_bid', 0) or 0) - (long_call.get('call_ask', 0) or 0)

        if put_credit <= 0 or call_credit <= 0:
            return None

        return {
            'actual_dte': actual_dte,
            'put_short_strike': short_put['strike'],
            'put_long_strike': long_put['strike'],
            'put_credit': put_credit,
            'call_short_strike': short_call['strike'],
            'call_long_strike': long_call['strike'],
            'call_credit': call_credit,
            'total_credit': put_credit + call_credit,
        }

    def execute_and_settle_trade(self, trade_date: str, tier: ScalingTier) -> Optional[DayTrade]:
        """Execute and settle trade in same day (day trade)"""
        ohlc = self.spx_ohlc.get(trade_date)
        if not ohlc:
            return None

        open_price = ohlc['open']
        close_price = ohlc['close']
        daily_high = ohlc['high']
        daily_low = ohlc['low']
        vix = self.vix_data.get(trade_date, 15.0)
        iv = vix / 100

        # Calculate expected moves
        expected_move_1d = self.calculate_expected_move(open_price, iv, 1)
        expected_move_sd = self.calculate_expected_move(open_price, iv, tier.sd_days)

        # Get options for tier's target DTE
        options = self.get_options_for_date(trade_date, tier.target_dte)
        if not options:
            return None

        underlying = options[0]['underlying_price']

        # Find strategy with appropriate strike selection method
        # Pass iv and sd_days for delta/sd calculation if needed
        ic = self.find_strategy(options, open_price, expected_move_sd, tier.target_dte, iv=iv, sd_days=tier.sd_days)
        if not ic:
            return None

        # Apply slippage (entry)
        put_credit_net = ic['put_credit'] - (tier.slippage_per_spread / 2)
        call_credit_net = ic['call_credit'] - (tier.slippage_per_spread / 2)
        total_credit_net = put_credit_net + call_credit_net

        if total_credit_net <= 0:
            return None

        # Max loss - use override for diagonal spreads
        if 'max_loss_override' in ic and ic['max_loss_override']:
            max_loss = ic['max_loss_override']
        else:
            max_loss = self.spread_width - total_credit_net

        if max_loss <= 0:
            max_loss = self.spread_width  # Fallback to spread width

        # Position sizing
        risk_budget = self.equity * (self.risk_per_trade_pct / 100)
        contracts_requested = int(risk_budget / (max_loss * 100))
        contracts_requested = max(1, contracts_requested)

        # Apply max contracts (override or tier default)
        max_contracts = self.max_contracts_override if self.max_contracts_override else tier.max_contracts
        contracts = min(contracts_requested, max_contracts)

        # Determine number of legs based on strategy type
        strategy_type = ic.get('strategy_type', 'iron_condor')
        num_legs = 4 if strategy_type in ['iron_condor', 'iron_butterfly'] else 2

        # Costs (entry + exit) - use overrides if provided
        commission_per_leg = self.commission_per_leg_override if self.commission_per_leg_override else tier.commission_per_leg
        slippage_per_spread = self.slippage_per_spread_override if self.slippage_per_spread_override else tier.slippage_per_spread

        commission = commission_per_leg * num_legs * contracts * 2  # legs × 2 (open + close)
        slippage = slippage_per_spread * contracts * 100
        total_costs = commission + slippage

        self.total_commissions += commission
        self.total_slippage += slippage

        # Calculate P&L based on CLOSE price (day trade exit)
        # This is where we PROPERLY simulate exiting at EOD
        strategy_type = ic.get('strategy_type', 'iron_condor')

        # Put spread P&L at close (if applicable)
        put_pnl = 0
        put_breached = False
        if ic['put_credit'] > 0:  # Only calculate if we have a put spread
            if close_price >= ic['put_short_strike']:
                # Both OTM at close - collect full premium
                put_pnl = ic['put_credit']
                put_breached = False
            elif close_price > ic['put_long_strike']:
                # Short put ITM, long put OTM
                intrinsic = ic['put_short_strike'] - close_price
                put_pnl = ic['put_credit'] - intrinsic
                put_breached = True
            else:
                # Both ITM - max loss on put side
                put_pnl = ic['put_credit'] - self.spread_width
                put_breached = True

        # Call spread P&L at close (if applicable)
        call_pnl = 0
        call_breached = False
        if ic['call_credit'] > 0:  # Only calculate if we have a call spread
            if close_price <= ic['call_short_strike']:
                # Both OTM at close
                call_pnl = ic['call_credit']
                call_breached = False
            elif close_price < ic['call_long_strike']:
                # Short call ITM, long call OTM
                intrinsic = close_price - ic['call_short_strike']
                call_pnl = ic['call_credit'] - intrinsic
                call_breached = True
            else:
                # Both ITM - max loss on call side
                call_pnl = ic['call_credit'] - self.spread_width
                call_breached = True

        # Check intraday threats (for analysis)
        intraday_put_threat = daily_low < ic['put_short_strike']
        intraday_call_threat = daily_high > ic['call_short_strike']

        # Total P&L
        gross_pnl = (put_pnl + call_pnl) * 100 * contracts
        net_pnl = gross_pnl - total_costs
        return_pct = (net_pnl / (max_loss * 100 * contracts) * 100) if max_loss > 0 else 0

        # Outcome
        if not put_breached and not call_breached:
            outcome = "MAX_PROFIT"
        elif put_breached and call_breached:
            outcome = "DOUBLE_BREACH"
        elif put_breached:
            outcome = "PUT_BREACHED"
        else:
            outcome = "CALL_BREACHED"

        self.trade_counter += 1
        self.trades_this_week += 1

        trade = DayTrade(
            trade_date=trade_date,
            trade_number=self.trade_counter,
            tier_name=tier.name,
            account_equity=self.equity,
            target_dte=tier.target_dte,
            actual_dte=ic['actual_dte'],
            sd_days_used=tier.sd_days,
            vix=vix,
            open_price=open_price,
            close_price=close_price,
            daily_high=daily_high,
            daily_low=daily_low,
            underlying_price=underlying,
            iv_used=iv,
            expected_move_1d=expected_move_1d,
            expected_move_sd=expected_move_sd,
            sd_multiplier=self.sd_multiplier,
            put_short_strike=ic['put_short_strike'],
            put_long_strike=ic['put_long_strike'],
            put_credit_gross=ic['put_credit'],
            put_credit_net=put_credit_net,
            put_distance_from_open=open_price - ic['put_short_strike'],
            call_short_strike=ic['call_short_strike'],
            call_long_strike=ic['call_long_strike'],
            call_credit_gross=ic['call_credit'],
            call_credit_net=call_credit_net,
            call_distance_from_open=ic['call_short_strike'] - open_price,
            total_credit_gross=ic['total_credit'],
            total_credit_net=total_credit_net,
            spread_width=self.spread_width,
            max_loss=max_loss,
            total_costs=total_costs,
            contracts=contracts,
            contracts_requested=contracts_requested,
            total_premium=total_credit_net * 100 * contracts,
            total_risk=max_loss * 100 * contracts,
            risk_pct=(max_loss * 100 * contracts / self.equity) * 100,
            put_pnl=put_pnl,
            call_pnl=call_pnl,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            return_pct=return_pct,
            outcome=outcome,
            put_breached=put_breached,
            call_breached=call_breached,
            intraday_put_threat=intraday_put_threat,
            intraday_call_threat=intraday_call_threat,
        )

        # Update equity and stats
        self.equity += net_pnl
        self.high_water_mark = max(self.high_water_mark, self.equity)

        # Track daily return for risk metrics
        if self.equity > 0:
            daily_return = net_pnl / (self.equity - net_pnl) if (self.equity - net_pnl) > 0 else 0
            self.daily_returns.append(daily_return)

        # Track equity curve
        drawdown_pct = (self.high_water_mark - self.equity) / self.high_water_mark * 100 if self.high_water_mark > 0 else 0
        self.equity_curve.append({
            'date': trade_date,
            'equity': self.equity,
            'drawdown_pct': drawdown_pct,
            'daily_pnl': net_pnl
        })

        # Tier stats
        self.tier_stats[tier.name]['trades'] += 1
        self.tier_stats[tier.name]['pnl'] += net_pnl
        if net_pnl > 0:
            self.tier_stats[tier.name]['wins'] += 1
            self.current_consecutive_losses = 0
        else:
            self.tier_stats[tier.name]['losses'] += 1
            self.current_consecutive_losses += 1
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.current_consecutive_losses)

        # Day of week stats
        dt = datetime.strptime(trade_date, '%Y-%m-%d')
        weekday = dt.weekday()
        if weekday in self.day_of_week_stats:
            self.day_of_week_stats[weekday]['trades'] += 1
            self.day_of_week_stats[weekday]['pnl'] += net_pnl
            if net_pnl > 0:
                self.day_of_week_stats[weekday]['wins'] += 1

        # VIX level stats
        vix_level = 'low' if vix < 15 else ('medium' if vix < 25 else 'high')
        self.vix_level_stats[vix_level]['trades'] += 1
        self.vix_level_stats[vix_level]['pnl'] += net_pnl
        if net_pnl > 0:
            self.vix_level_stats[vix_level]['wins'] += 1

        return trade

    def run(self) -> Dict:
        """Run the fixed hybrid backtest"""
        print("\n" + "=" * 80)
        print("HYBRID SCALING STRATEGY - FIXED (DAY TRADES)")
        print("=" * 80)
        print(f"Period:             {self.start_date} to {self.end_date}")
        print(f"Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"Risk Per Trade:     {self.risk_per_trade_pct}%")
        print(f"SD Multiplier:      {self.sd_multiplier}")
        print(f"Spread Width:       ${self.spread_width}")
        print("-" * 80)
        print("SCALING TIERS (with correct SD calculations):")
        for tier in SCALING_TIERS:
            max_eq = f"${tier.max_equity:,.0f}" if tier.max_equity < float('inf') else "Unlimited"
            sd_mult = math.sqrt(tier.sd_days / 252)
            print(f"  {tier.name}:")
            print(f"    Equity: ${tier.min_equity:,.0f} - {max_eq}")
            print(f"    Options DTE: {tier.target_dte}, SD Days: {tier.sd_days} (√{tier.sd_days}/252 = {sd_mult:.4f})")
            print(f"    Max Contracts: {tier.max_contracts}, Trades/Week: {tier.trades_per_week}")
        print("-" * 80)
        print("KEY: All trades are DAY TRADES - enter at open, exit at close")
        print("     Longer DTE options used for LIQUIDITY, not for holding")
        print("=" * 80)

        # Load data
        print("\nLoading market data...")
        self.load_market_data()

        if not self.spx_ohlc:
            print("Failed to load market data")
            return {}

        # Get trading days
        print("Fetching trading days...")
        trading_days = self.get_trading_days()

        if not trading_days:
            print("No options data found")
            return {}

        print(f"Found {len(trading_days)} trading days")

        # Track tier transitions
        current_tier_name = None
        tier_transitions = []

        # Process each day
        total_days = len(trading_days)
        for i, trade_date in enumerate(trading_days):

            # Progress bar
            if i % 20 == 0 or i == total_days - 1:
                pct = ((i + 1) / total_days) * 100
                tier = self.get_current_tier()
                bar_len = 40
                filled = int(bar_len * (i + 1) / total_days)
                bar = "█" * filled + "░" * (bar_len - filled)
                print(f"\r  [{bar}] {pct:5.1f}% | {tier.name} | Equity: ${self.equity:,.0f}", end="", flush=True)

            # Get current tier
            tier = self.get_current_tier()

            # Track tier transitions
            if tier.name != current_tier_name:
                if current_tier_name is not None:
                    tier_transitions.append({
                        'date': trade_date,
                        'from_tier': current_tier_name,
                        'to_tier': tier.name,
                        'equity': self.equity
                    })
                current_tier_name = tier.name

            # Get VIX for today (for filtering)
            vix_today = self.vix_data.get(trade_date, 15.0)

            # Check if we should trade today (includes VIX filter)
            if not self.should_trade_today(trade_date, tier, vix_today):
                continue

            # Execute and settle trade (day trade)
            trade = self.execute_and_settle_trade(trade_date, tier)

            if trade:
                self.all_trades.append(trade)

        print(f"\r  [{'█' * 40}] 100.0% Complete!{' ' * 40}")

        # Calculate results
        results = self.calculate_results(tier_transitions)
        self.print_results(results)
        self.export_trades()

        return results

    def calculate_results(self, tier_transitions: List[Dict]) -> Dict:
        """Calculate comprehensive results including risk metrics"""
        if not self.all_trades:
            return {}

        total_pnl = sum(t.net_pnl for t in self.all_trades)
        total_return = (self.equity - self.initial_capital) / self.initial_capital * 100

        wins = [t for t in self.all_trades if t.net_pnl > 0]
        losses = [t for t in self.all_trades if t.net_pnl <= 0]

        win_rate = len(wins) / len(self.all_trades) * 100

        gross_profit = sum(t.net_pnl for t in wins)
        gross_loss = sum(t.net_pnl for t in losses)
        profit_factor = abs(gross_profit / gross_loss) if gross_loss else float('inf')

        # Monthly returns
        monthly = {}
        for t in self.all_trades:
            month = t.trade_date[:7]
            monthly[month] = monthly.get(month, 0) + t.net_pnl

        monthly_pct = {}
        month_start_equity = self.initial_capital
        for month in sorted(monthly.keys()):
            pnl = monthly[month]
            pct = (pnl / month_start_equity) * 100
            monthly_pct[month] = pct
            month_start_equity += pnl

        avg_monthly = sum(monthly_pct.values()) / len(monthly_pct) if monthly_pct else 0

        # Drawdown
        peak = self.initial_capital
        max_dd = 0
        max_dd_date = None
        equity = self.initial_capital
        for t in self.all_trades:
            equity += t.net_pnl
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd
                max_dd_date = t.trade_date

        # Outcomes
        outcomes = {}
        for t in self.all_trades:
            outcomes[t.outcome] = outcomes.get(t.outcome, 0) + 1

        # Intraday threat analysis
        put_threats = sum(1 for t in self.all_trades if t.intraday_put_threat)
        call_threats = sum(1 for t in self.all_trades if t.intraday_call_threat)

        # Risk Metrics - Sharpe and Sortino Ratios
        sharpe_ratio = 0
        sortino_ratio = 0
        if self.daily_returns and len(self.daily_returns) > 1:
            import statistics
            avg_return = statistics.mean(self.daily_returns)
            std_return = statistics.stdev(self.daily_returns) if len(self.daily_returns) > 1 else 0

            # Annualized Sharpe (assuming 252 trading days)
            if std_return > 0:
                sharpe_ratio = (avg_return * 252) / (std_return * math.sqrt(252))

            # Sortino - only downside deviation
            downside_returns = [r for r in self.daily_returns if r < 0]
            if downside_returns and len(downside_returns) > 1:
                downside_std = statistics.stdev(downside_returns)
                if downside_std > 0:
                    sortino_ratio = (avg_return * 252) / (downside_std * math.sqrt(252))

        # Day of week performance
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        day_of_week_performance = {}
        for day_idx, stats in self.day_of_week_stats.items():
            if stats['trades'] > 0:
                day_of_week_performance[day_names[day_idx]] = {
                    'trades': stats['trades'],
                    'pnl': stats['pnl'],
                    'win_rate': (stats['wins'] / stats['trades']) * 100,
                    'avg_pnl': stats['pnl'] / stats['trades']
                }

        # VIX level performance
        vix_performance = {}
        for level, stats in self.vix_level_stats.items():
            if stats['trades'] > 0:
                vix_performance[level] = {
                    'trades': stats['trades'],
                    'pnl': stats['pnl'],
                    'win_rate': (stats['wins'] / stats['trades']) * 100,
                    'avg_pnl': stats['pnl'] / stats['trades']
                }

        # Export all trades as dicts for API
        all_trades_dicts = []
        for t in self.all_trades:
            all_trades_dicts.append({
                'trade_date': t.trade_date,
                'trade_number': t.trade_number,
                'tier_name': t.tier_name,
                'account_equity': t.account_equity,
                'vix': t.vix,
                'open_price': t.open_price,
                'close_price': t.close_price,
                'put_short_strike': t.put_short_strike,
                'put_long_strike': t.put_long_strike,
                'call_short_strike': t.call_short_strike,
                'call_long_strike': t.call_long_strike,
                'total_credit_net': t.total_credit_net,
                'contracts': t.contracts,
                'net_pnl': t.net_pnl,
                'return_pct': t.return_pct,
                'outcome': t.outcome,
                'put_breached': t.put_breached,
                'call_breached': t.call_breached,
            })

        return {
            'summary': {
                'initial_capital': self.initial_capital,
                'final_equity': self.equity,
                'total_pnl': total_pnl,
                'total_return_pct': total_return,
                'avg_monthly_return_pct': avg_monthly,
                'max_drawdown_pct': max_dd,
                'max_drawdown_date': max_dd_date,
            },
            'trades': {
                'total': len(self.all_trades),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'avg_win': gross_profit / len(wins) if wins else 0,
                'avg_loss': gross_loss / len(losses) if losses else 0,
            },
            'costs': {
                'total_commissions': self.total_commissions,
                'total_slippage': self.total_slippage,
                'total_costs': self.total_commissions + self.total_slippage,
            },
            'risk_metrics': {
                'sharpe_ratio': sharpe_ratio,
                'sortino_ratio': sortino_ratio,
                'max_consecutive_losses': self.max_consecutive_losses,
                'vix_filter_skips': self.vix_filter_skips,
            },
            'risk_analysis': {
                'intraday_put_threats': put_threats,
                'intraday_call_threats': call_threats,
                'threat_rate': (put_threats + call_threats) / len(self.all_trades) * 100 if self.all_trades else 0,
            },
            'tier_stats': self.tier_stats,
            'tier_transitions': tier_transitions,
            'outcomes': outcomes,
            'monthly_returns': monthly_pct,
            'day_of_week_performance': day_of_week_performance,
            'vix_performance': vix_performance,
            'equity_curve': self.equity_curve,
            'all_trades': all_trades_dicts,
        }

    def print_results(self, results: Dict):
        """Print detailed results"""
        if not results:
            return

        s = results['summary']
        t = results['trades']
        c = results['costs']
        r = results['risk_analysis']
        ts = results['tier_stats']
        tt = results['tier_transitions']
        o = results['outcomes']

        print("\n" + "=" * 80)
        print("HYBRID SCALING RESULTS - FIXED")
        print("=" * 80)

        print(f"\nCAPITAL")
        print(f"  Initial:              ${s['initial_capital']:>15,.2f}")
        print(f"  Final:                ${s['final_equity']:>15,.2f}")
        print(f"  Total P&L:            ${s['total_pnl']:>15,.2f}")
        print(f"  Total Return:         {s['total_return_pct']:>15.2f}%")

        print(f"\nPERFORMANCE")
        print(f"  Avg Monthly Return:   {s['avg_monthly_return_pct']:>15.2f}%")
        print(f"  Max Drawdown:         {s['max_drawdown_pct']:>15.2f}%")
        if s['max_drawdown_date']:
            print(f"  Max DD Date:          {s['max_drawdown_date']:>15}")

        print(f"\nTRADE STATISTICS")
        print(f"  Total Trades:         {t['total']:>15}")
        print(f"  Win Rate:             {t['win_rate']:>15.1f}%")
        pf = f"{t['profit_factor']:.2f}" if t['profit_factor'] != float('inf') else "∞"
        print(f"  Profit Factor:        {pf:>15}")
        print(f"  Avg Win:              ${t['avg_win']:>14,.2f}")
        print(f"  Avg Loss:             ${t['avg_loss']:>14,.2f}")

        print(f"\nRISK ANALYSIS (Intraday)")
        print(f"  Put Threats:          {r['intraday_put_threats']:>15} (price hit put strike intraday)")
        print(f"  Call Threats:         {r['intraday_call_threats']:>15} (price hit call strike intraday)")
        print(f"  Threat Rate:          {r['threat_rate']:>15.1f}%")

        print(f"\nTRANSACTION COSTS")
        print(f"  Total Commissions:    ${c['total_commissions']:>15,.2f}")
        print(f"  Total Slippage:       ${c['total_slippage']:>15,.2f}")
        print(f"  Total Costs:          ${c['total_costs']:>15,.2f}")

        print(f"\nTIER BREAKDOWN")
        for tier_name, stats in ts.items():
            if stats['trades'] > 0:
                win_rate = stats['wins'] / stats['trades'] * 100
                avg_pnl = stats['pnl'] / stats['trades']
                print(f"  {tier_name}:")
                print(f"    Trades: {stats['trades']:>5} | Wins: {stats['wins']:>4} | WR: {win_rate:>5.1f}% | P&L: ${stats['pnl']:>12,.2f} | Avg: ${avg_pnl:>8,.2f}")

        if tt:
            print(f"\nTIER TRANSITIONS")
            for trans in tt:
                print(f"  {trans['date']}: {trans['from_tier']} → {trans['to_tier']} (Equity: ${trans['equity']:,.0f})")

        print(f"\nOUTCOME BREAKDOWN")
        for outcome, count in sorted(o.items(), key=lambda x: -x[1]):
            pct = count / t['total'] * 100
            print(f"  {outcome:20} {count:>5} ({pct:5.1f}%)")

        print(f"\nMONTHLY RETURNS")
        monthly = results['monthly_returns']
        for month, pct in sorted(monthly.items()):
            bar_len = min(30, int(abs(pct) * 3))
            if pct >= 0:
                bar = "+" * bar_len
                print(f"  {month}: {pct:+7.2f}% {bar}")
            else:
                bar = "-" * bar_len
                print(f"  {month}: {pct:+7.2f}% {bar}")

        print("=" * 80)

    def export_trades(self, filename: str = None):
        """Export to CSV"""
        if not self.all_trades:
            return

        import csv

        if not filename:
            filename = f"hybrid_fixed_trades_{self.start_date}_{self.end_date}.csv"

        filepath = Path(__file__).parent / filename

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self.all_trades[0]).keys())
            writer.writeheader()
            for trade in self.all_trades:
                writer.writerow(asdict(trade))

        print(f"\nExported {len(self.all_trades)} trades to {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Hybrid Scaling Strategy - Fixed')

    parser.add_argument('--start', default='2021-01-01')
    parser.add_argument('--end', default='2025-12-01')
    parser.add_argument('--capital', type=float, default=1_000_000)
    parser.add_argument('--width', type=float, default=10.0)
    parser.add_argument('--sd', type=float, default=1.0)
    parser.add_argument('--risk', type=float, default=5.0)
    parser.add_argument('--ticker', default='SPX')

    args = parser.parse_args()

    backtester = HybridFixedBacktester(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        spread_width=args.width,
        sd_multiplier=args.sd,
        risk_per_trade_pct=args.risk,
        ticker=args.ticker,
    )

    results = backtester.run()
    return results


if __name__ == "__main__":
    main()
