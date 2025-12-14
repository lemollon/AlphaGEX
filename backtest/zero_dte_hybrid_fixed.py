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

# GEX Calculator integration for GEX-Protected strategies
try:
    from quant.kronos_gex_calculator import KronosGEXCalculator, GEXData
    GEX_AVAILABLE = True
except ImportError:
    GEX_AVAILABLE = False
    KronosGEXCalculator = None
    GEXData = None


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

    # GEX-Protected strategy fields
    gex_protected: bool = False
    gex_put_wall: Optional[float] = None
    gex_call_wall: Optional[float] = None
    gex_regime: str = ""


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
        # Swing trading
        hold_days: int = 1,  # 1 = day trade, 2+ = swing trade
        # Apache directional settings
        wall_proximity_pct: float = 1.0,  # How close to wall to trigger (1.0 = 1%, 2.0 = 2%)
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

        # Swing trading
        self.hold_days = hold_days
        self.open_positions = []  # Track positions for swing trades

        # Apache directional settings
        self.wall_proximity_pct = wall_proximity_pct
        self.swing_stats = {
            'positions_opened': 0,
            'positions_closed': 0,
            'avg_hold_days': 0,
        }

        # Debug mode - traces all execution paths
        self.debug_mode = True  # Enable detailed logging
        self.debug_stats = {
            'total_days_processed': 0,
            'skipped_by_trade_day': 0,
            'skipped_by_vix_filter': 0,
            'skipped_by_tier_limit': 0,
            'skipped_no_ohlc': 0,
            'skipped_no_options': 0,
            'skipped_no_strategy': 0,
            'skipped_bad_credit': 0,
            'trades_executed': 0,
            'strategy_failures': {
                'no_options': 0,
                'no_dtes': 0,
                'no_dte_options': 0,
                'no_otm_puts': 0,
                'no_otm_calls': 0,
                'no_long_put': 0,
                'no_long_call': 0,
                'bad_put_credit': 0,
                'bad_call_credit': 0,
            }
        }

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

        # Progress callback (set by caller for UI updates)
        self.progress_callback = None

        # Cache
        self.spx_ohlc: Dict[str, Dict] = {}
        self.vix_data: Dict[str, float] = {}

        # GEX Calculator for GEX-Protected strategies
        self.gex_calculator = None
        self.gex_cache: Dict[str, Optional[GEXData]] = {}
        if GEX_AVAILABLE and self.strategy_type == 'gex_protected_iron_condor':
            self.gex_calculator = KronosGEXCalculator(ticker)

        # GEX strategy stats
        self.gex_stats = {
            'trades_with_gex_walls': 0,
            'trades_with_sd_fallback': 0,
            'gex_unavailable_days': 0,
        }

        # ML Model for directional prediction (Apache strategy)
        self.ml_predictor = None
        self.ml_stats = {
            'ml_predictions': 0,
            'ml_confirmed_trades': 0,
            'ml_rejected_trades': 0,
            'ml_unavailable': 0,
        }
        if self.strategy_type == 'apache_directional':
            self._load_ml_model()

    def _load_ml_model(self):
        """Load ML model for directional prediction if available"""
        try:
            from quant.gex_directional_ml import GEXDirectionalPredictor
            model_path = 'models/gex_directional_model.joblib'
            if os.path.exists(model_path):
                self.ml_predictor = GEXDirectionalPredictor(ticker=self.ticker)
                self.ml_predictor.load_model(model_path)
                print(f"✅ Loaded ML model from {model_path}")
            else:
                print(f"⚠️ ML model not found at {model_path} - using wall proximity only")
        except Exception as e:
            print(f"⚠️ Could not load ML model: {e}")
            self.ml_predictor = None

    def _get_ml_prediction(self, gex_data: Dict, vix: float = None) -> Optional[str]:
        """Get ML prediction for direction: BULLISH, BEARISH, or FLAT"""
        if not self.ml_predictor:
            self.ml_stats['ml_unavailable'] += 1
            return None

        try:
            # Build features for prediction
            features = {
                'net_gex': gex_data.get('net_gex', 0),
                'call_wall': gex_data.get('call_wall', 0),
                'put_wall': gex_data.get('put_wall', 0),
                'total_call_gex': gex_data.get('total_call_gex', 0),
                'total_put_gex': gex_data.get('total_put_gex', 0),
                'vix': vix or 20,
            }

            prediction = self.ml_predictor.predict(features)
            self.ml_stats['ml_predictions'] += 1
            return prediction.direction.value if prediction else None
        except Exception as e:
            self.ml_stats['ml_unavailable'] += 1
            return None

    def get_connection(self):
        """
        Get database connection for ORAT options data.
        Uses ORAT_DATABASE_URL if set, otherwise falls back to DATABASE_URL.
        """
        import psycopg2
        from urllib.parse import urlparse

        # Try ORAT-specific database first, then fall back to main DATABASE_URL
        database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')

        if not database_url:
            raise ValueError(
                "Neither ORAT_DATABASE_URL nor DATABASE_URL is set. "
                "Set ORAT_DATABASE_URL to point to the PostgreSQL database containing ORAT options data."
            )

        result = urlparse(database_url)
        conn = psycopg2.connect(
            host=result.hostname,
            port=result.port or 5432,
            user=result.username,
            password=result.password,
            database=result.path[1:],
            connect_timeout=30,
            options='-c statement_timeout=300000'
        )
        return conn

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
            self.delta_fallback_count = getattr(self, 'delta_fallback_count', 0) + 1
            if self.delta_fallback_count == 1:
                print(f"⚠️ Warning: Delta-based strike selection falling back to SD method (delta data not available)")
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
            self.debug_stats['skipped_by_trade_day'] += 1
            return False

        # VIX filter
        if vix is not None:
            if self.min_vix is not None and vix < self.min_vix:
                self.vix_filter_skips += 1
                self.debug_stats['skipped_by_vix_filter'] += 1
                return False
            if self.max_vix is not None and vix > self.max_vix:
                self.vix_filter_skips += 1
                self.debug_stats['skipped_by_vix_filter'] += 1
                return False

        week_num = dt.isocalendar()[1]
        if self.current_week != week_num:
            self.current_week = week_num
            self.trades_this_week = 0

        if self.trades_this_week >= tier.trades_per_week:
            self.debug_stats['skipped_by_tier_limit'] += 1
            return False

        if tier.trades_per_week == 5:
            return weekday < 5
        elif tier.trades_per_week == 3:
            return weekday in [0, 2, 4]
        elif tier.trades_per_week == 2:
            return weekday in [1, 3]

        # Default case - trades_per_week is not 2, 3, or 5
        self.debug_stats['skipped_by_tier_limit'] += 1
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
        """Get all trading days from ORAT options data"""
        try:
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

            if not days:
                print(f"⚠️ Warning: No trading days found for {self.ticker} between {self.start_date} and {self.end_date}")

            return days

        except Exception as e:
            print(f"❌ Error fetching trading days: {e}")
            print("   Make sure orat_options_eod table exists and has data for the specified ticker/dates")
            return []

    def get_options_for_date(self, trade_date: str, target_dte: int) -> List[Dict]:
        """Get options near target DTE"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get options within range of target DTE
            min_dte = max(0, target_dte - 3)
            max_dte = target_dte + 7

            cursor.execute("""
                SELECT
                    strike, underlying_price, dte,
                    put_bid, put_ask, call_bid, call_ask,
                    delta, put_iv, call_iv,
                    gamma, call_oi, put_oi
                FROM orat_options_eod
                WHERE ticker = %s
                  AND trade_date = %s
                  AND dte >= %s
                  AND dte <= %s
                ORDER BY ABS(dte - %s), strike
            """, (self.ticker, trade_date, min_dte, max_dte, target_dte))

            columns = ['strike', 'underlying_price', 'dte', 'put_bid', 'put_ask',
                       'call_bid', 'call_ask', 'delta', 'put_iv', 'call_iv',
                       'gamma', 'call_oi', 'put_oi']

            options = []
            for row in cursor.fetchall():
                opt = dict(zip(columns, row))
                for key in opt:
                    if opt[key] is not None and key != 'dte':
                        opt[key] = float(opt[key])
                options.append(opt)

            conn.close()

            # Debug logging for first few calls
            if self.debug_mode and not hasattr(self, '_options_debug_count'):
                self._options_debug_count = 0
            if self.debug_mode and self._options_debug_count < 3:
                self._options_debug_count += 1
                if options:
                    dtes = list(set(o['dte'] for o in options))
                    underlying = options[0]['underlying_price'] if options else 'N/A'
                    puts_with_bid = len([o for o in options if o.get('put_bid', 0) and o['put_bid'] > 0.05])
                    calls_with_bid = len([o for o in options if o.get('call_bid', 0) and o['call_bid'] > 0.05])
                    print(f"   DEBUG [{trade_date}]: {len(options)} options, DTEs={sorted(dtes)}, "
                          f"underlying={underlying:.0f}, puts_w_bid={puts_with_bid}, calls_w_bid={calls_with_bid}")
                else:
                    print(f"   DEBUG [{trade_date}]: No options found for ticker={self.ticker}, DTE range [{min_dte}, {max_dte}]")

            return options

        except Exception as e:
            print(f"⚠️ Warning: Error fetching options for {trade_date}: {e}")
            return []

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

    def find_bull_call_spread(self, options: List[Dict], open_price: float,
                              strike_distance: float, target_dte: int,
                              use_raw_distance: bool = False) -> Optional[Dict]:
        """
        Find Bull Call Spread (call debit spread) - bullish strategy.

        Buy ATM/near-money call, sell OTM call.
        Profit when underlying rises above long strike + debit paid.

        Used by APACHE when near put wall (support) for bullish plays.
        """
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

        # Target long call strike at or slightly below current price (ATM or slightly ITM)
        if use_raw_distance:
            long_call_target = open_price - (strike_distance * 0.25)  # Slightly ITM for better delta
        else:
            long_call_target = open_price - (self.sd_multiplier * strike_distance * 0.25)
        long_call_target = round(long_call_target / 5) * 5

        # Find calls near the money
        near_calls = [o for o in dte_options
                     if o.get('call_ask', 0) and o['call_ask'] > 0.05
                     and o.get('call_bid', 0) and o['call_bid'] > 0.05]

        if not near_calls:
            return None

        # Long call at target (buy at ask)
        long_call = min(near_calls, key=lambda x: abs(x['strike'] - long_call_target))

        # Short call above (sell at bid) - spread_width away
        short_call_strike = long_call['strike'] + self.spread_width
        short_call_candidates = [o for o in dte_options
                                if abs(o['strike'] - short_call_strike) < 2
                                and o.get('call_bid', 0) and o['call_bid'] > 0]
        if not short_call_candidates:
            return None
        short_call = min(short_call_candidates, key=lambda x: abs(x['strike'] - short_call_strike))

        # Debit spread: pay ask for long, receive bid for short
        long_cost = long_call.get('call_ask', 0) or 0
        short_credit = short_call.get('call_bid', 0) or 0
        net_debit = long_cost - short_credit  # Positive = cost

        if net_debit <= 0:
            # No cost means something is wrong with pricing
            return None

        # Max profit = spread width - debit paid
        max_profit = self.spread_width - net_debit
        if max_profit <= 0:
            return None

        return {
            'actual_dte': actual_dte,
            'put_short_strike': 0,
            'put_long_strike': 0,
            'put_credit': 0,
            'call_short_strike': short_call['strike'],
            'call_long_strike': long_call['strike'],
            'call_credit': -net_debit,  # Negative credit = debit
            'total_credit': -net_debit,  # Negative = debit spread
            'strategy_type': 'bull_call',
            'is_debit_spread': True,
            'max_profit': max_profit,
            'max_loss': net_debit
        }

    def find_bear_put_spread(self, options: List[Dict], open_price: float,
                              strike_distance: float, target_dte: int,
                              use_raw_distance: bool = False) -> Optional[Dict]:
        """
        Find Bear Put Spread (put debit spread) - bearish strategy.

        Buy ATM/near-money put, sell OTM put below.
        Profit when underlying falls below long strike - debit paid.

        Used for bearish directional plays.
        """
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

        # Target long put strike at or slightly above current price (ATM or slightly ITM)
        if use_raw_distance:
            long_put_target = open_price + (strike_distance * 0.25)  # Slightly ITM for better delta
        else:
            long_put_target = open_price + (self.sd_multiplier * strike_distance * 0.25)
        long_put_target = round(long_put_target / 5) * 5

        # Find puts near the money
        near_puts = [o for o in dte_options
                    if o.get('put_ask', 0) and o['put_ask'] > 0.05
                    and o.get('put_bid', 0) and o['put_bid'] > 0.05]

        if not near_puts:
            return None

        # Long put at target (buy at ask)
        long_put = min(near_puts, key=lambda x: abs(x['strike'] - long_put_target))

        # Short put below (sell at bid) - spread_width away
        short_put_strike = long_put['strike'] - self.spread_width
        short_put_candidates = [o for o in dte_options
                               if abs(o['strike'] - short_put_strike) < 2
                               and o.get('put_bid', 0) and o['put_bid'] > 0]
        if not short_put_candidates:
            return None
        short_put = min(short_put_candidates, key=lambda x: abs(x['strike'] - short_put_strike))

        # Debit spread: pay ask for long, receive bid for short
        long_cost = long_put.get('put_ask', 0) or 0
        short_credit = short_put.get('put_bid', 0) or 0
        net_debit = long_cost - short_credit  # Positive = cost

        if net_debit <= 0:
            return None

        # Max profit = spread width - debit paid
        max_profit = self.spread_width - net_debit
        if max_profit <= 0:
            return None

        return {
            'actual_dte': actual_dte,
            'put_short_strike': short_put['strike'],
            'put_long_strike': long_put['strike'],
            'put_credit': -net_debit,  # Negative credit = debit
            'call_short_strike': 0,
            'call_long_strike': 0,
            'call_credit': 0,
            'total_credit': -net_debit,  # Negative = debit spread
            'strategy_type': 'bear_put',
            'is_debit_spread': True,
            'is_put_debit_spread': True,  # Flag for P&L calculation
            'max_profit': max_profit,
            'max_loss': net_debit
        }

    def calculate_gex_walls_from_options(self, options: List[Dict], spot_price: float) -> Dict:
        """
        Calculate GEX walls from historical options data.

        GEX = gamma × open_interest × 100 × spot_price²

        Returns dict with put_wall (support) and call_wall (resistance).
        """
        if not options:
            return {'put_wall': 0, 'call_wall': 0, 'net_gex': 0}

        # Group by strike and calculate GEX
        strike_gex = {}

        for opt in options:
            strike = opt.get('strike', 0)
            gamma = opt.get('gamma', 0) or 0
            call_oi = opt.get('call_oi', 0) or 0
            put_oi = opt.get('put_oi', 0) or 0

            if strike not in strike_gex:
                strike_gex[strike] = {'call_gex': 0, 'put_gex': 0}

            # GEX formula: gamma × OI × 100 × spot²
            # Calls have positive gamma exposure, puts have negative
            if gamma > 0:
                call_gex = gamma * call_oi * 100 * (spot_price ** 2) / 1e9  # Scale down
                put_gex = gamma * put_oi * 100 * (spot_price ** 2) / 1e9

                strike_gex[strike]['call_gex'] += call_gex
                strike_gex[strike]['put_gex'] += put_gex

        if not strike_gex:
            return {'put_wall': 0, 'call_wall': 0, 'net_gex': 0}

        # Find call wall (highest call GEX above spot - resistance)
        call_wall = 0
        max_call_gex = 0
        for strike, gex in strike_gex.items():
            if strike > spot_price and gex['call_gex'] > max_call_gex:
                max_call_gex = gex['call_gex']
                call_wall = strike

        # Find put wall (highest put GEX below spot - support)
        put_wall = 0
        max_put_gex = 0
        for strike, gex in strike_gex.items():
            if strike < spot_price and gex['put_gex'] > max_put_gex:
                max_put_gex = gex['put_gex']
                put_wall = strike

        # Calculate net GEX
        total_call_gex = sum(g['call_gex'] for g in strike_gex.values())
        total_put_gex = sum(g['put_gex'] for g in strike_gex.values())
        net_gex = total_call_gex - total_put_gex

        return {
            'put_wall': put_wall,
            'call_wall': call_wall,
            'net_gex': net_gex,
            'total_call_gex': total_call_gex,
            'total_put_gex': total_put_gex
        }

    def find_apache_directional(self, options: List[Dict], open_price: float,
                                 strike_distance: float, target_dte: int,
                                 use_raw_distance: bool = False,
                                 gex_data: Dict = None,
                                 vix: float = None) -> Optional[Dict]:
        """
        APACHE Directional Spread - uses GEX walls + ML to determine direction.
        DEBIT SPREADS ONLY for defined risk.

        Strategy:
        1. Check if near a GEX wall (put wall = support, call wall = resistance)
        2. Get ML prediction for direction confirmation
        3. Trade only if wall proximity AND ML agree (or ML unavailable)

        - Near put wall + ML BULLISH: Bull Call Spread
        - Near call wall + ML BEARISH: Bear Put Spread
        """
        # Calculate GEX walls from the options data we have
        if not gex_data:
            gex_data = self.calculate_gex_walls_from_options(options, open_price)

        put_wall = gex_data.get('put_wall', 0)
        call_wall = gex_data.get('call_wall', 0)
        spot = open_price

        if not put_wall or not call_wall:
            # Can't determine walls - skip trade
            return None

        # Calculate distance to walls (as percentage)
        put_wall_distance_pct = abs(spot - put_wall) / spot * 100
        call_wall_distance_pct = abs(spot - call_wall) / spot * 100

        # NEW LOGIC: Trade based on which wall is CLOSER (within max threshold)
        # - If closer to put wall → expect bounce → bullish (bull call spread)
        # - If closer to call wall → expect rejection → bearish (bear put spread)
        max_wall_distance = self.wall_proximity_pct  # Max distance to consider trading

        # Check if we're within trading range of at least one wall
        near_any_wall = (put_wall_distance_pct <= max_wall_distance or
                        call_wall_distance_pct <= max_wall_distance)

        if not near_any_wall:
            # Too far from both walls - no edge
            return None

        # Determine direction based on which wall is closer
        closer_to_put = put_wall_distance_pct < call_wall_distance_pct

        # Get ML prediction (if available)
        ml_prediction = self._get_ml_prediction(gex_data, vix)

        if closer_to_put:
            # Closer to put wall (support) → expect bounce → BULLISH
            if ml_prediction is None or ml_prediction == 'BULLISH':
                if ml_prediction:
                    self.ml_stats['ml_confirmed_trades'] += 1
                return self.find_bull_call_spread(options, open_price, strike_distance, target_dte, use_raw_distance)
            else:
                self.ml_stats['ml_rejected_trades'] += 1
                return None
        else:
            # Closer to call wall (resistance) → expect rejection → BEARISH
            if ml_prediction is None or ml_prediction == 'BEARISH':
                if ml_prediction:
                    self.ml_stats['ml_confirmed_trades'] += 1
                return self.find_bear_put_spread(options, open_price, strike_distance, target_dte, use_raw_distance)
            else:
                self.ml_stats['ml_rejected_trades'] += 1
                return None

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

        # For diagonal, max loss depends on whether it's a debit or credit
        # Debit spread: max loss = net debit paid
        # Credit spread: max loss = spread width - credit received
        if net_debit > 0:
            max_loss = net_debit
        else:
            # Credit scenario: max loss is spread width reduced by credit received
            max_loss = max(self.spread_width + net_debit, 0.01)  # net_debit is negative here

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

        # For diagonal, max loss depends on whether it's a debit or credit
        # Debit spread: max loss = net debit paid
        # Credit spread: max loss = spread width - credit received
        if net_debit > 0:
            max_loss = net_debit
        else:
            # Credit scenario: max loss is spread width reduced by credit received
            max_loss = max(self.spread_width + net_debit, 0.01)  # net_debit is negative here

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

    def get_gex_for_date(self, trade_date: str) -> Optional[GEXData]:
        """
        Get GEX data for a trading date (cached and stored to DB).

        Returns:
            GEXData with call_wall, put_wall, flip_point, etc. or None if unavailable
        """
        if not self.gex_calculator:
            return None

        if trade_date in self.gex_cache:
            return self.gex_cache[trade_date]

        # Calculate, cache, and store to database for ML training
        gex = self.gex_calculator.calculate_gex_for_date(trade_date, dte_max=7)
        self.gex_cache[trade_date] = gex

        if gex:
            # Store GEX data to database for ML training (async, don't block)
            try:
                self.gex_calculator.store_gex_to_database(gex)
            except Exception as e:
                # Don't fail the backtest if storage fails
                pass
        else:
            self.gex_stats['gex_unavailable_days'] += 1

        return gex

    def find_gex_protected_iron_condor(
        self,
        options: List[Dict],
        open_price: float,
        expected_move: float,
        target_dte: int,
        trade_date: str
    ) -> Optional[Dict]:
        """
        Find Iron Condor with strikes outside GEX walls when available.

        GEX-Protected Strategy:
        - Put strike below the put wall (support level)
        - Call strike above the call wall (resistance level)
        - Falls back to SD-based strikes when GEX walls unavailable

        Args:
            options: Options chain for the day
            open_price: Opening price of underlying
            expected_move: Expected move based on IV and SD days
            target_dte: Target days to expiration
            trade_date: Date string for GEX lookup

        Returns:
            Iron Condor dict with strikes, or None if not possible
        """
        if not options:
            self.debug_stats['strategy_failures']['no_options'] += 1
            return None

        # Get GEX data for this date
        gex = self.get_gex_for_date(trade_date)

        # Determine strike distances
        use_gex_walls = False
        put_distance = None
        call_distance = None

        if gex and gex.put_wall > 0 and gex.call_wall > 0:
            # GEX walls are now guaranteed to be meaningful support/resistance levels
            # (GEX calculator ensures walls are at least 0.5% away from spot)

            # Add small buffer outside the walls for extra protection
            put_wall_buffer = open_price * 0.002  # 0.2% buffer
            call_wall_buffer = open_price * 0.002

            # Distance from open price to wall (plus buffer)
            put_distance = open_price - gex.put_wall + put_wall_buffer
            call_distance = gex.call_wall - open_price + call_wall_buffer

            # Use GEX walls - they represent real support/resistance levels
            use_gex_walls = True
            self.gex_stats['trades_with_gex_walls'] += 1

            logger.debug(
                f"GEX walls for {trade_date}: put_wall=${gex.put_wall:.2f} "
                f"call_wall=${gex.call_wall:.2f} spot=${open_price:.2f}"
            )
        else:
            # No GEX data available - fall back to SD
            self.gex_stats['trades_with_sd_fallback'] += 1
            logger.debug(f"No GEX data for {trade_date}, using SD fallback")

        # Fall back to SD-based strikes if GEX walls not used
        if not use_gex_walls:
            put_distance = self.sd_multiplier * expected_move
            call_distance = self.sd_multiplier * expected_move

        # Find the iron condor with calculated distances
        result = self.find_iron_condor(
            options=options,
            open_price=open_price,
            put_distance=put_distance,
            call_distance=call_distance,
            target_dte=target_dte,
            use_raw_distance=True
        )

        if result:
            # Add GEX info to result for tracking
            result['gex_protected'] = use_gex_walls
            result['gex_put_wall'] = gex.put_wall if gex else None
            result['gex_call_wall'] = gex.call_wall if gex else None
            result['gex_regime'] = gex.gex_regime if gex else 'UNKNOWN'
            result['strategy_type'] = 'gex_protected_iron_condor'

        return result

    def find_strategy(self, options: List[Dict], open_price: float,
                      expected_move: float, target_dte: int,
                      iv: float = 0.15, sd_days: int = 1,
                      trade_date: str = None) -> Optional[Dict]:
        """
        Find the appropriate strategy based on strategy_type setting.

        Strike selection is determined by self.strike_selection:
        - 'sd': Use expected_move × sd_multiplier (default behavior)
        - 'fixed': Use fixed_strike_distance points
        - 'delta': Find strikes by target delta
        - 'gex': Use GEX walls (for gex_protected_iron_condor strategy)

        Args:
            options: Options chain
            open_price: Opening price of underlying
            expected_move: Expected move based on IV
            target_dte: Target days to expiration
            iv: Implied volatility (decimal)
            sd_days: Days for SD calculation
            trade_date: Date string (required for GEX-protected strategies)
        """
        # Handle GEX-Protected Iron Condor separately - it has its own strike logic
        if self.strategy_type == 'gex_protected_iron_condor':
            if trade_date is None:
                # Fallback to regular iron condor if no date provided
                return self.find_iron_condor(options, open_price,
                                            self.sd_multiplier * expected_move,
                                            self.sd_multiplier * expected_move,
                                            target_dte, use_raw_distance=True)
            return self.find_gex_protected_iron_condor(
                options, open_price, expected_move, target_dte, trade_date
            )

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
        elif self.strategy_type == 'bull_call':
            return self.find_bull_call_spread(options, open_price, call_distance, target_dte, use_raw_distance=True)
        elif self.strategy_type == 'bear_put':
            return self.find_bear_put_spread(options, open_price, put_distance, target_dte, use_raw_distance=True)
        elif self.strategy_type == 'apache_directional':
            return self.find_apache_directional(options, open_price, call_distance, target_dte, use_raw_distance=True)
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
            self.debug_stats['strategy_failures']['no_options'] += 1
            return None

        if call_distance is None:
            call_distance = put_distance

        # Find options closest to target DTE
        available_dtes = list(set(o['dte'] for o in options))
        if not available_dtes:
            self.debug_stats['strategy_failures']['no_dtes'] += 1
            return None

        actual_dte = min(available_dtes, key=lambda x: abs(x - target_dte))
        dte_options = [o for o in options if o['dte'] == actual_dte]

        if not dte_options:
            self.debug_stats['strategy_failures']['no_dte_options'] += 1
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

        if not otm_puts:
            self.debug_stats['strategy_failures']['no_otm_puts'] += 1
            return None
        if not otm_calls:
            self.debug_stats['strategy_failures']['no_otm_calls'] += 1
            return None

        # Short put at target
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - put_target))

        # Long put below
        long_put_strike = short_put['strike'] - self.spread_width
        long_put_candidates = [o for o in dte_options
                              if abs(o['strike'] - long_put_strike) < 2
                              and o.get('put_ask', 0) and o['put_ask'] > 0]
        if not long_put_candidates:
            self.debug_stats['strategy_failures']['no_long_put'] += 1
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
            self.debug_stats['strategy_failures']['no_long_call'] += 1
            return None
        long_call = min(long_call_candidates, key=lambda x: abs(x['strike'] - long_call_strike))

        # Calculate credits
        put_credit = (short_put.get('put_bid', 0) or 0) - (long_put.get('put_ask', 0) or 0)
        call_credit = (short_call.get('call_bid', 0) or 0) - (long_call.get('call_ask', 0) or 0)

        if put_credit <= 0:
            self.debug_stats['strategy_failures']['bad_put_credit'] += 1
            return None
        if call_credit <= 0:
            self.debug_stats['strategy_failures']['bad_call_credit'] += 1
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
            self.debug_stats['skipped_no_ohlc'] += 1
            if self.debug_mode and self.debug_stats['skipped_no_ohlc'] <= 3:
                print(f"   DEBUG [{trade_date}]: No OHLC data available")
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
            self.debug_stats['skipped_no_options'] += 1
            if self.debug_mode and self.debug_stats['skipped_no_options'] <= 3:
                print(f"   DEBUG [{trade_date}]: No options returned for DTE={tier.target_dte}")
            return None

        underlying = options[0]['underlying_price']

        # Find strategy with appropriate strike selection method
        # Pass iv, sd_days, and trade_date for delta/sd/gex calculation
        ic = self.find_strategy(options, open_price, expected_move_sd, tier.target_dte,
                                iv=iv, sd_days=tier.sd_days, trade_date=trade_date)
        if not ic:
            self.debug_stats['skipped_no_strategy'] += 1
            if self.debug_mode and self.debug_stats['skipped_no_strategy'] <= 3:
                print(f"   DEBUG [{trade_date}]: find_strategy returned None (underlying={underlying:.0f}, options={len(options)})")
            return None

        # Apply slippage (entry)
        put_credit_net = ic['put_credit'] - (tier.slippage_per_spread / 2)
        call_credit_net = ic['call_credit'] - (tier.slippage_per_spread / 2)
        total_credit_net = put_credit_net + call_credit_net
        is_debit_spread = ic.get('is_debit_spread', False)

        # For debit spreads, credit is negative (cost to enter)
        if not is_debit_spread and total_credit_net <= 0:
            self.debug_stats['skipped_bad_credit'] += 1
            if self.debug_mode and self.debug_stats['skipped_bad_credit'] <= 3:
                print(f"   DEBUG [{trade_date}]: Total credit <= 0 after slippage (put={put_credit_net:.2f}, call={call_credit_net:.2f})")
            return None

        # Max loss calculation
        if is_debit_spread:
            # For debit spreads, max loss = debit paid (use value from strategy or calculate)
            if 'max_loss' in ic and ic['max_loss']:
                max_loss = ic['max_loss']
            else:
                max_loss = abs(total_credit_net)  # Debit paid
        elif 'max_loss_override' in ic and ic['max_loss_override']:
            # Use override for diagonal spreads
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
        is_put_debit_spread = ic.get('is_put_debit_spread', False)

        if is_put_debit_spread and ic['put_credit'] < 0:
            # PUT DEBIT SPREAD (Bear Put Spread) - long at higher strike, short at lower strike
            # put_long_strike = higher strike (bought), put_short_strike = lower strike (sold)
            debit_paid = abs(ic['put_credit'])  # Positive value

            if close_price > ic['put_long_strike']:
                # Both OTM at close - max loss (lose the debit)
                put_pnl = -debit_paid
                put_breached = True  # We lost money
            elif close_price > ic['put_short_strike']:
                # Long put ITM, short put OTM - partial profit
                intrinsic = ic['put_long_strike'] - close_price
                put_pnl = intrinsic - debit_paid
                put_breached = put_pnl < 0
            else:
                # Both ITM - max profit (spread width - debit paid)
                put_pnl = self.spread_width - debit_paid
                put_breached = False  # Max profit scenario

        elif ic['put_credit'] > 0:  # CREDIT SPREAD - Only calculate if we have a put credit spread
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
        is_debit_spread = ic.get('is_debit_spread', False)

        if is_debit_spread and ic['call_credit'] < 0:
            # DEBIT SPREAD (Bull Call Spread) - long at lower strike, short at higher strike
            # call_long_strike = lower strike (bought), call_short_strike = higher strike (sold)
            debit_paid = abs(ic['call_credit'])  # Positive value

            if close_price < ic['call_long_strike']:
                # Both OTM at close - max loss (lose the debit)
                call_pnl = -debit_paid
                call_breached = True  # We lost money
            elif close_price < ic['call_short_strike']:
                # Long call ITM, short call OTM - partial profit
                intrinsic = close_price - ic['call_long_strike']
                call_pnl = intrinsic - debit_paid
                call_breached = call_pnl < 0
            else:
                # Both ITM - max profit (spread width - debit paid)
                call_pnl = self.spread_width - debit_paid
                call_breached = False  # Max profit scenario

        elif ic['call_credit'] > 0:  # CREDIT SPREAD - Only calculate if we have a call credit spread
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
        # Only check if the strike is non-zero (diagonal strategies may have one side = 0)
        intraday_put_threat = ic['put_short_strike'] > 0 and daily_low < ic['put_short_strike']
        intraday_call_threat = ic['call_short_strike'] > 0 and daily_high > ic['call_short_strike']

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
            # GEX-Protected fields
            gex_protected=ic.get('gex_protected', False),
            gex_put_wall=ic.get('gex_put_wall'),
            gex_call_wall=ic.get('gex_call_wall'),
            gex_regime=ic.get('gex_regime', ''),
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

    # ==================== SWING TRADING METHODS ====================

    def _open_swing_position(self, trade_date: str, tier, vix: float) -> Optional[Dict]:
        """Open a new swing position"""
        # Get OHLC data
        ohlc = self.spx_ohlc.get(trade_date)
        if not ohlc:
            return None

        open_price = ohlc['open']

        # Get options
        options = self.get_options_for_date(trade_date, tier.target_dte)
        if not options:
            return None

        # Calculate expected move (IV from VIX)
        iv = vix / 100
        expected_move = self.calculate_expected_move(open_price, iv, tier.sd_days)

        # Find strategy
        ic = self.find_strategy(options, open_price, iv, expected_move, tier.sd_days, tier.target_dte, vix)
        if not ic:
            return None

        # Create position record
        return {
            'entry_date': trade_date,
            'entry_price': open_price,
            'strategy': ic,
            'tier': tier,
            'vix': vix,
            'days_held': 0,
        }

    def _close_mature_positions(self, current_date: str, trading_days: List[str], current_idx: int):
        """Close positions that have been held for hold_days"""
        positions_to_close = []

        for pos in self.open_positions:
            # Find how many trading days since entry
            try:
                entry_idx = trading_days.index(pos['entry_date'])
                days_held = current_idx - entry_idx
                pos['days_held'] = days_held

                if days_held >= self.hold_days:
                    positions_to_close.append(pos)
            except ValueError:
                # Entry date not found, close anyway
                positions_to_close.append(pos)

        # Close mature positions
        for pos in positions_to_close:
            trade = self._close_swing_position(pos, current_date)
            if trade:
                self.all_trades.append(trade)
            self.open_positions.remove(pos)
            self.swing_stats['positions_closed'] += 1

    def _close_swing_position(self, position: Dict, exit_date: str) -> Optional:
        """Close a swing position and calculate P&L"""
        ohlc = self.spx_ohlc.get(exit_date)
        if not ohlc:
            return None

        close_price = ohlc['close']
        ic = position['strategy']
        tier = position['tier']

        # Calculate P&L same as day trade but with swing entry/exit
        is_debit_spread = ic.get('is_debit_spread', False)
        is_put_debit_spread = ic.get('is_put_debit_spread', False)

        put_pnl = 0
        call_pnl = 0

        # Put spread P&L
        if is_put_debit_spread and ic['put_credit'] < 0:
            debit_paid = abs(ic['put_credit'])
            if close_price > ic['put_long_strike']:
                put_pnl = -debit_paid
            elif close_price > ic['put_short_strike']:
                intrinsic = ic['put_long_strike'] - close_price
                put_pnl = intrinsic - debit_paid
            else:
                put_pnl = self.spread_width - debit_paid
        elif ic['put_credit'] > 0:
            if close_price >= ic['put_short_strike']:
                put_pnl = ic['put_credit']
            elif close_price > ic['put_long_strike']:
                intrinsic = ic['put_short_strike'] - close_price
                put_pnl = ic['put_credit'] - intrinsic
            else:
                put_pnl = ic['put_credit'] - self.spread_width

        # Call spread P&L
        if is_debit_spread and ic['call_credit'] < 0:
            debit_paid = abs(ic['call_credit'])
            if close_price < ic['call_long_strike']:
                call_pnl = -debit_paid
            elif close_price < ic['call_short_strike']:
                intrinsic = close_price - ic['call_long_strike']
                call_pnl = intrinsic - debit_paid
            else:
                call_pnl = self.spread_width - debit_paid
        elif ic['call_credit'] > 0:
            if close_price <= ic['call_short_strike']:
                call_pnl = ic['call_credit']
            elif close_price < ic['call_long_strike']:
                intrinsic = close_price - ic['call_short_strike']
                call_pnl = ic['call_credit'] - intrinsic
            else:
                call_pnl = ic['call_credit'] - self.spread_width

        # Total P&L
        contracts = 1  # Simplified for swing
        gross_pnl = (put_pnl + call_pnl) * 100 * contracts
        total_costs = 10  # Simple cost estimate for swing
        net_pnl = gross_pnl - total_costs

        # Update equity
        self.equity += net_pnl

        # Track consecutive wins/losses
        if net_pnl > 0:
            self.current_consecutive_losses = 0
        else:
            self.current_consecutive_losses += 1
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.current_consecutive_losses)

        # Create trade record matching DayTrade dataclass
        self.trade_counter += 1
        entry_ohlc = self.spx_ohlc.get(position['entry_date'], {})
        entry_high = entry_ohlc.get('high', position['entry_price'])
        entry_low = entry_ohlc.get('low', position['entry_price'])

        trade = DayTrade(
            trade_date=position['entry_date'],
            trade_number=self.trade_counter,
            tier_name=tier.name,
            account_equity=self.equity,
            target_dte=tier.target_dte,
            actual_dte=ic.get('actual_dte', tier.target_dte),
            sd_days_used=tier.sd_days,
            vix=position['vix'],
            open_price=position['entry_price'],
            close_price=close_price,
            daily_high=entry_high,
            daily_low=entry_low,
            underlying_price=position['entry_price'],
            iv_used=ic.get('iv', position['vix'] / 100),
            expected_move_1d=ic.get('expected_move', 0),
            expected_move_sd=ic.get('expected_move', 0),
            sd_multiplier=self.sd_multiplier,
            put_short_strike=ic.get('put_short_strike', 0),
            put_long_strike=ic.get('put_long_strike', 0),
            put_credit_gross=ic.get('put_credit', 0),
            put_credit_net=ic.get('put_credit', 0),
            put_distance_from_open=position['entry_price'] - ic.get('put_short_strike', 0) if ic.get('put_short_strike') else 0,
            call_short_strike=ic.get('call_short_strike', 0),
            call_long_strike=ic.get('call_long_strike', 0),
            call_credit_gross=ic.get('call_credit', 0),
            call_credit_net=ic.get('call_credit', 0),
            call_distance_from_open=ic.get('call_short_strike', 0) - position['entry_price'] if ic.get('call_short_strike') else 0,
            total_credit_gross=ic.get('total_credit', 0),
            total_credit_net=ic.get('total_credit', 0),
            spread_width=self.spread_width,
            max_loss=abs(ic.get('total_credit', 0)) if is_debit_spread else self.spread_width - ic.get('total_credit', 0),
            total_costs=total_costs,
            contracts=contracts,
            contracts_requested=contracts,
            total_premium=abs(ic.get('total_credit', 0)) * 100 * contracts,
            total_risk=self.spread_width * 100 * contracts,
            risk_pct=(self.spread_width * 100 * contracts) / self.equity * 100,
            put_pnl=put_pnl * 100 * contracts,
            call_pnl=call_pnl * 100 * contracts,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            return_pct=(net_pnl / (self.spread_width * 100 * contracts)) * 100 if self.spread_width else 0,
            outcome='WIN' if net_pnl > 0 else 'LOSS',
            put_breached=put_pnl < 0,
            call_breached=call_pnl < 0,
            intraday_put_threat=False,
            intraday_call_threat=False,
        )

        return trade

    def _close_all_positions(self, exit_date: str):
        """Close all remaining open positions"""
        for pos in self.open_positions[:]:
            trade = self._close_swing_position(pos, exit_date)
            if trade:
                self.all_trades.append(trade)
            self.swing_stats['positions_closed'] += 1
        self.open_positions.clear()

    # ==================== MAIN RUN METHOD ====================

    def run(self) -> Dict:
        """Run the fixed hybrid backtest"""
        trade_type = "SWING TRADES" if self.hold_days > 1 else "DAY TRADES"
        print("\n" + "=" * 80)
        print(f"HYBRID SCALING STRATEGY - FIXED ({trade_type})")
        print("=" * 80)
        print(f"Period:             {self.start_date} to {self.end_date}")
        print(f"Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"Risk Per Trade:     {self.risk_per_trade_pct}%")
        print(f"SD Multiplier:      {self.sd_multiplier}")
        print(f"Spread Width:       ${self.spread_width}")
        print(f"Strategy Type:      {self.strategy_type}")
        if self.strategy_type == 'gex_protected_iron_condor':
            print(f"  -> Uses GEX walls for strikes when available, falls back to SD")
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
        if self.progress_callback:
            self.progress_callback(5, 'Loading market data...')
        self.load_market_data()

        if not self.spx_ohlc:
            print("Failed to load market data")
            if self.progress_callback:
                self.progress_callback(100, 'Failed to load market data')
            return {}

        # Get trading days
        print("Fetching trading days...")
        if self.progress_callback:
            self.progress_callback(10, 'Fetching trading days from database...')
        trading_days = self.get_trading_days()

        if not trading_days:
            print("No options data found")
            if self.progress_callback:
                self.progress_callback(100, 'No options data found in database')
            return {}

        print(f"Found {len(trading_days)} trading days")
        if self.progress_callback:
            self.progress_callback(15, f'Processing {len(trading_days)} trading days...')

        # Track tier transitions
        current_tier_name = None
        tier_transitions = []

        # Process each day
        total_days = len(trading_days)
        last_progress_report = 0
        for i, trade_date in enumerate(trading_days):

            # Progress bar and callback
            if i % 20 == 0 or i == total_days - 1:
                pct = ((i + 1) / total_days) * 100
                tier = self.get_current_tier()
                bar_len = 40
                filled = int(bar_len * (i + 1) / total_days)
                bar = "█" * filled + "░" * (bar_len - filled)
                print(f"\r  [{bar}] {pct:5.1f}% | {tier.name} | Equity: ${self.equity:,.0f}", end="", flush=True)

                # Report progress via callback (scale 15-95%)
                if self.progress_callback and pct - last_progress_report >= 5:
                    scaled_pct = int(15 + (pct * 0.80))
                    self.progress_callback(scaled_pct, f'Processing: {i+1}/{total_days} days ({len(self.all_trades)} trades)')
                    last_progress_report = pct

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

            # Swing trading: Close positions that have reached hold_days
            if self.hold_days > 1:
                self._close_mature_positions(trade_date, trading_days, i)

            # Execute and settle trade
            if self.hold_days == 1:
                # Day trade: enter and exit same day
                trade = self.execute_and_settle_trade(trade_date, tier)
                if trade:
                    self.all_trades.append(trade)
            else:
                # Swing trade: open position if we don't have too many open
                if len(self.open_positions) < 3:  # Max 3 concurrent positions
                    position = self._open_swing_position(trade_date, tier, vix_today)
                    if position:
                        self.open_positions.append(position)
                        self.swing_stats['positions_opened'] += 1

        # Close any remaining open positions at end
        if self.hold_days > 1 and self.open_positions:
            self._close_all_positions(trading_days[-1] if trading_days else None)

        print(f"\r  [{'█' * 40}] 100.0% Complete!{' ' * 40}")

        # Print debug summary
        if self.debug_mode:
            print("\n" + "=" * 60)
            print("🔍 DEBUG EXECUTION SUMMARY")
            print("=" * 60)
            print(f"Total trading days processed: {len(trading_days)}")
            print(f"Trades executed: {len(self.all_trades)}")
            print(f"\nSkip reasons:")
            print(f"  - Trade day filter (wrong weekday): {self.debug_stats['skipped_by_trade_day']}")
            print(f"  - VIX filter: {self.debug_stats['skipped_by_vix_filter']}")
            print(f"  - Tier frequency limit: {self.debug_stats['skipped_by_tier_limit']}")
            print(f"  - No OHLC data (Yahoo): {self.debug_stats['skipped_no_ohlc']}")
            print(f"  - No options data (ORAT): {self.debug_stats['skipped_no_options']}")
            print(f"  - Strategy failed: {self.debug_stats['skipped_no_strategy']}")
            print(f"  - Bad credit after slippage: {self.debug_stats['skipped_bad_credit']}")
            print(f"\nStrategy failure breakdown:")
            sf = self.debug_stats['strategy_failures']
            print(f"  - No options passed: {sf['no_options']}")
            print(f"  - No available DTEs: {sf['no_dtes']}")
            print(f"  - No options at target DTE: {sf['no_dte_options']}")
            print(f"  - No OTM puts with bid: {sf['no_otm_puts']}")
            print(f"  - No OTM calls with bid: {sf['no_otm_calls']}")
            print(f"  - No long put at spread width: {sf['no_long_put']}")
            print(f"  - No long call at spread width: {sf['no_long_call']}")
            print(f"  - Bad put credit (<=0): {sf['bad_put_credit']}")
            print(f"  - Bad call credit (<=0): {sf['bad_call_credit']}")
            print("=" * 60 + "\n")

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
                # GEX-Protected fields
                'gex_protected': t.gex_protected,
                'gex_put_wall': t.gex_put_wall,
                'gex_call_wall': t.gex_call_wall,
                'gex_regime': t.gex_regime,
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
            'gex_stats': self.gex_stats if self.strategy_type == 'gex_protected_iron_condor' else None,
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

        # GEX-Protected strategy stats
        gex_stats = results.get('gex_stats')
        if gex_stats:
            print(f"\nGEX-PROTECTED STRATEGY STATS")
            gex_wall_trades = gex_stats.get('trades_with_gex_walls', 0)
            sd_fallback_trades = gex_stats.get('trades_with_sd_fallback', 0)
            total_gex_trades = gex_wall_trades + sd_fallback_trades
            if total_gex_trades > 0:
                gex_wall_pct = (gex_wall_trades / total_gex_trades) * 100
                print(f"  GEX Wall Trades:      {gex_wall_trades:>10} ({gex_wall_pct:.1f}%)")
                print(f"  SD Fallback Trades:   {sd_fallback_trades:>10} ({100 - gex_wall_pct:.1f}%)")
                print(f"  GEX Unavailable Days: {gex_stats.get('gex_unavailable_days', 0):>10}")

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
    parser.add_argument('--strategy', default='iron_condor',
                       choices=['iron_condor', 'gex_protected_iron_condor', 'bull_put',
                               'bear_call', 'iron_butterfly', 'diagonal_call', 'diagonal_put'],
                       help='Strategy type (default: iron_condor)')

    args = parser.parse_args()

    backtester = HybridFixedBacktester(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        spread_width=args.width,
        sd_multiplier=args.sd,
        risk_per_trade_pct=args.risk,
        ticker=args.ticker,
        strategy_type=args.strategy,
    )

    results = backtester.run()
    return results


if __name__ == "__main__":
    main()
