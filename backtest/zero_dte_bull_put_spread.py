#!/usr/bin/env python3
"""
0DTE Bull Put Spread Backtester using ORAT Historical Data

Strategy:
- Sell OTM put at target delta (e.g., 10-20 delta)
- Buy further OTM put for protection (e.g., $5-10 wide spread)
- Both expire same day (0DTE / DTE=0)
- SPX is cash-settled (European style)

Uses REAL bid/ask prices from ORAT database (no estimation).

Usage:
    python backtest/zero_dte_bull_put_spread.py --start 2020-01-01 --end 2025-12-01 --capital 1000000
"""

import os
import sys
import uuid
import argparse
import random
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# Try to import yfinance for real OHLC data
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("Warning: yfinance not installed. Run: pip install yfinance")
    print("Using simulated settlement prices instead of real OHLC data.")


@dataclass
class BullPutSpreadTrade:
    """Single 0DTE Bull Put Spread trade"""
    trade_date: str
    trade_number: int

    # Underlying
    underlying_price: float

    # Short put (sold)
    short_strike: float
    short_bid: float
    short_ask: float
    short_delta: float
    short_iv: float

    # Long put (bought)
    long_strike: float
    long_bid: float
    long_ask: float
    long_delta: float
    long_iv: float

    # Spread details
    spread_width: float
    credit_received: float  # Per spread
    max_loss: float  # Per spread (width - credit)
    max_profit: float  # Credit received

    # Entry
    contracts: int
    total_credit: float
    total_risk: float
    margin_required: float

    # Exit (filled at expiration)
    settlement_price: float = 0.0
    exit_debit: float = 0.0
    pnl_per_spread: float = 0.0
    total_pnl: float = 0.0
    pnl_percent: float = 0.0

    # Classification
    outcome: str = ""  # "MAX_PROFIT", "PARTIAL_WIN", "PARTIAL_LOSS", "MAX_LOSS"
    short_breached: bool = False
    long_breached: bool = False

    # Timing
    expiration_date: str = ""
    dte: int = 0


@dataclass
class DailyEquity:
    """Daily account snapshot"""
    date: str
    equity: float
    daily_pnl: float
    cumulative_pnl: float
    drawdown_pct: float
    high_water_mark: float
    trades_today: int
    win_rate_cumulative: float


class ZeroDTEBullPutSpreadBacktester:
    """
    Backtester for 0DTE Bull Put Spread strategy on SPX using ORAT data.

    Strategy Rules:
    1. Enter at market open (use EOD data as proxy)
    2. Sell put at target delta (e.g., 10-20 delta)
    3. Buy put $5 or $10 below for protection
    4. Hold to expiration (cash settlement)
    5. Collect credit if OTM, pay difference if ITM
    """

    def __init__(
        self,
        start_date: str = "2020-01-01",
        end_date: str = None,
        initial_capital: float = 1_000_000,
        target_delta: float = 0.15,  # 15 delta puts
        spread_width: float = 10.0,  # $10 wide spread
        max_risk_per_trade_pct: float = 2.0,  # Max 2% of capital at risk per trade
        max_daily_trades: int = 1,  # 1 trade per day
        ticker: str = "SPXW",  # SPXW for weeklies (0DTE)
        monthly_return_target: float = 10.0,  # 10% monthly target
        trading_days_of_week: List[int] = None,  # Days to trade: 0=Mon, 1=Tue, etc.
        max_vix: float = 30.0,  # Don't trade when VIX > this (crash protection)
    ):
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        self.initial_capital = initial_capital
        self.target_delta = target_delta
        self.spread_width = spread_width
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_daily_trades = max_daily_trades
        self.ticker = ticker
        self.monthly_return_target = monthly_return_target
        # Default to Monday and Tuesday only
        self.trading_days_of_week = trading_days_of_week if trading_days_of_week is not None else [0, 1]
        self.max_vix = max_vix  # VIX threshold - don't trade above this

        # State
        self.cash = initial_capital
        self.equity = initial_capital
        self.high_water_mark = initial_capital

        # Tracking
        self.all_trades: List[BullPutSpreadTrade] = []
        self.daily_equity: List[DailyEquity] = []
        self.trade_counter = 0

        # Stats
        self.days_traded = 0
        self.days_with_data = 0
        self.days_skipped = 0
        self.days_skipped_vix = 0  # Days skipped due to high VIX

        # Cache for SPX OHLC data (loaded once at start)
        self.spx_ohlc: Dict[str, Dict] = {}

        # Cache for VIX data (for crash protection)
        self.vix_data: Dict[str, float] = {}

    def load_spx_ohlc_data(self):
        """
        Load SPX OHLC data from Yahoo Finance.
        This gives us real open/close prices for accurate backtesting.

        Entry: Use OPEN price (assumes entry at market open)
        Settlement: Use CLOSE price (0DTE settles at close)
        """
        if not YFINANCE_AVAILABLE:
            print("  yfinance not available - will use simulated settlement")
            return

        print("  Loading SPX OHLC data from Yahoo Finance...")

        try:
            # Yahoo Finance uses ^GSPC for SPX
            ticker = yf.Ticker("^GSPC")

            # Add buffer days to handle weekends
            start = datetime.strptime(self.start_date, '%Y-%m-%d') - timedelta(days=5)
            end = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=5)

            df = ticker.history(start=start, end=end)

            if df.empty:
                print("  Warning: No SPX data from Yahoo Finance")
                return

            # Convert to dictionary for fast lookup
            for idx, row in df.iterrows():
                date_str = idx.strftime('%Y-%m-%d')
                self.spx_ohlc[date_str] = {
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row['Volume'])
                }

            print(f"  Loaded {len(self.spx_ohlc)} days of SPX OHLC data")

        except Exception as e:
            print(f"  Warning: Failed to load SPX data from Yahoo: {e}")
            print("  Will use simulated settlement prices")

    def get_spx_prices(self, trade_date: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Get SPX open and close prices for a given date.
        Returns (open_price, close_price) or (None, None) if not available.
        """
        if trade_date in self.spx_ohlc:
            data = self.spx_ohlc[trade_date]
            return data['open'], data['close']
        return None, None

    def load_vix_data(self):
        """
        Load VIX data from Yahoo Finance for crash protection.
        When VIX is above threshold, we skip trading that day.
        """
        if not YFINANCE_AVAILABLE:
            print("  VIX filter disabled - yfinance not available")
            return

        print("  Loading VIX data from Yahoo Finance...")

        try:
            ticker = yf.Ticker("^VIX")

            start = datetime.strptime(self.start_date, '%Y-%m-%d') - timedelta(days=5)
            end = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=5)

            df = ticker.history(start=start, end=end)

            if df.empty:
                print("  Warning: No VIX data from Yahoo Finance")
                return

            for idx, row in df.iterrows():
                date_str = idx.strftime('%Y-%m-%d')
                # Use the close price as the VIX level
                self.vix_data[date_str] = float(row['Close'])

            print(f"  Loaded {len(self.vix_data)} days of VIX data")

        except Exception as e:
            print(f"  Warning: Failed to load VIX data: {e}")
            print("  VIX filter will be disabled")

    def get_vix(self, trade_date: str) -> Optional[float]:
        """Get VIX level for a given date."""
        return self.vix_data.get(trade_date)

    def should_trade(self, trade_date: str) -> Tuple[bool, str]:
        """
        Check if we should trade on this date based on VIX filter.
        Returns (should_trade, reason)
        """
        vix = self.get_vix(trade_date)

        if vix is None:
            # No VIX data - trade anyway
            return True, ""

        if vix > self.max_vix:
            return False, f"VIX={vix:.1f} > {self.max_vix}"

        return True, ""

    def get_connection(self):
        """Get database connection"""
        from database_adapter import get_connection
        return get_connection()

    def get_trading_days(self) -> List[str]:
        """Get list of trading days with 0DTE options data"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Find days where we have 0DTE options (dte = 0 or dte = 1 for same-day expiry)
        cursor.execute("""
            SELECT DISTINCT trade_date
            FROM orat_options_eod
            WHERE ticker = %s
              AND dte <= 1
              AND trade_date >= %s
              AND trade_date <= %s
            ORDER BY trade_date
        """, (self.ticker, self.start_date, self.end_date))

        days = [row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()]
        conn.close()

        return days

    def get_options_for_date(self, trade_date: str) -> List[Dict]:
        """Get all 0DTE options for a given date"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get 0DTE puts with bid/ask/delta
        cursor.execute("""
            SELECT
                trade_date,
                ticker,
                expiration_date,
                strike,
                underlying_price,
                put_bid,
                put_ask,
                put_mid,
                delta,
                put_iv,
                dte
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date = %s
              AND dte <= 1
              AND put_bid > 0
              AND put_ask > 0
            ORDER BY strike DESC
        """, (self.ticker, trade_date))

        columns = ['trade_date', 'ticker', 'expiration_date', 'strike',
                   'underlying_price', 'put_bid', 'put_ask', 'put_mid',
                   'delta', 'put_iv', 'dte']

        options = []
        for row in cursor.fetchall():
            opt = dict(zip(columns, row))
            # Convert to float for calculations
            for key in ['strike', 'underlying_price', 'put_bid', 'put_ask',
                       'put_mid', 'delta', 'put_iv']:
                if opt[key] is not None:
                    opt[key] = float(opt[key])
            options.append(opt)

        conn.close()
        return options

    def find_spread(self, options: List[Dict], target_delta: float, spread_width: float) -> Optional[Tuple[Dict, Dict]]:
        """
        Find optimal bull put spread:
        - Short put near target delta
        - Long put at (short_strike - spread_width)

        Returns (short_put, long_put) or None if no valid spread found

        NOTE: ORAT stores CALL delta (0 to 1), not put delta.
        Put delta = call delta - 1
        So for a 15 delta PUT, we need call delta = 0.85
        """
        if not options:
            return None

        # ORAT stores CALL delta (0 to 1)
        # For OTM puts: call delta 0.70-0.95 = put delta -0.30 to -0.05
        # For 15 delta put: call delta = 1 - 0.15 = 0.85
        target_call_delta = 1.0 - target_delta  # Convert put delta target to call delta

        short_candidates = [
            opt for opt in options
            if opt['delta'] is not None
            and 0.70 < opt['delta'] < 0.95  # Call delta for 5-30 delta puts
        ]

        if not short_candidates:
            return None

        # Find put closest to target (using call delta)
        short_put = min(short_candidates, key=lambda x: abs(x['delta'] - target_call_delta))

        # Find long put at spread_width below
        long_strike = short_put['strike'] - spread_width

        # Find exact or closest strike
        long_candidates = [opt for opt in options if abs(opt['strike'] - long_strike) < 1]

        if not long_candidates:
            # Try to find any strike below
            long_candidates = [opt for opt in options if opt['strike'] < short_put['strike']]
            if not long_candidates:
                return None
            long_put = max(long_candidates, key=lambda x: x['strike'])
        else:
            long_put = min(long_candidates, key=lambda x: abs(x['strike'] - long_strike))

        # Validate spread
        if long_put['strike'] >= short_put['strike']:
            return None

        return (short_put, long_put)

    def calculate_credit(self, short_put: Dict, long_put: Dict) -> float:
        """
        Calculate credit received for bull put spread.
        Sell short put at bid, buy long put at ask (realistic fills)
        """
        credit = short_put['put_bid'] - long_put['put_ask']
        return max(0, credit)  # Should always be positive for valid spread

    def calculate_settlement(self, short_strike: float, long_strike: float,
                            settlement_price: float) -> Tuple[float, str]:
        """
        Calculate P&L at expiration based on settlement price.

        Returns: (pnl_per_spread, outcome)

        SPX is cash-settled:
        - If settlement > short_strike: Both OTM, keep full credit
        - If long_strike < settlement < short_strike: Partial loss
        - If settlement < long_strike: Max loss = width - credit
        """
        if settlement_price >= short_strike:
            # Both OTM - keep full credit
            return 0, "MAX_PROFIT"
        elif settlement_price > long_strike:
            # Short put ITM, long put OTM
            # Loss = short_strike - settlement
            loss = short_strike - settlement_price
            return -loss, "PARTIAL_LOSS"
        else:
            # Both ITM - max loss
            # Loss = short_strike - long_strike = spread_width
            loss = short_strike - long_strike
            return -loss, "MAX_LOSS"

    def simulate_settlement(self, entry_price: float, iv: float, trade_date: str) -> float:
        """
        Simulate realistic settlement price based on IV.

        ORAT provides EOD data, so we need to simulate intraday movement.
        Expected Daily Move = Underlying * IV * sqrt(1/252)

        Uses trade_date as random seed for reproducibility.
        """
        # Seed random with date for reproducibility
        date_seed = int(trade_date.replace('-', ''))
        random.seed(date_seed)

        # Calculate expected daily move (1 standard deviation)
        # Annualized IV to daily: IV * sqrt(1/252)
        daily_vol = iv * math.sqrt(1/252)
        expected_move = entry_price * daily_vol

        # Simulate using normal distribution
        # Most days within 1 SD, occasionally 2-3 SD moves
        z_score = random.gauss(0, 1)

        # Cap extreme moves to 3 standard deviations
        z_score = max(-3, min(3, z_score))

        # Calculate settlement
        settlement = entry_price + (expected_move * z_score)

        return settlement

    def size_position(self, credit: float, spread_width: float,
                      underlying_price: float) -> Tuple[int, float, float]:
        """
        Calculate position size based on risk management rules.

        Returns: (contracts, total_credit, total_risk)
        """
        # Max loss per spread
        max_loss_per_spread = (spread_width - credit) * 100  # Per contract

        # Max capital at risk
        max_risk = self.equity * (self.max_risk_per_trade_pct / 100)

        # Calculate contracts
        if max_loss_per_spread <= 0:
            contracts = 0
        else:
            contracts = int(max_risk / max_loss_per_spread)

        # Minimum 1 contract if we can afford it
        contracts = max(1, min(contracts, 100))  # Cap at 100 contracts

        total_credit = credit * 100 * contracts
        total_risk = max_loss_per_spread * contracts

        return contracts, total_credit, total_risk

    def execute_trade(self, trade_date: str, options: List[Dict]) -> Optional[BullPutSpreadTrade]:
        """Execute a single bull put spread trade"""

        # Find spread
        spread = self.find_spread(options, self.target_delta, self.spread_width)
        if not spread:
            return None

        short_put, long_put = spread

        # Calculate credit
        credit = self.calculate_credit(short_put, long_put)
        if credit <= 0:
            return None

        # Calculate actual spread width
        actual_width = short_put['strike'] - long_put['strike']

        # Size position
        contracts, total_credit, total_risk = self.size_position(
            credit, actual_width, short_put['underlying_price']
        )

        if contracts == 0:
            return None

        self.trade_counter += 1

        # Create trade
        trade = BullPutSpreadTrade(
            trade_date=trade_date,
            trade_number=self.trade_counter,
            underlying_price=short_put['underlying_price'],
            short_strike=short_put['strike'],
            short_bid=short_put['put_bid'],
            short_ask=short_put['put_ask'],
            short_delta=short_put['delta'],
            short_iv=short_put['put_iv'] or 0,
            long_strike=long_put['strike'],
            long_bid=long_put['put_bid'],
            long_ask=long_put['put_ask'],
            long_delta=long_put['delta'],
            long_iv=long_put['put_iv'] or 0,
            spread_width=actual_width,
            credit_received=credit,
            max_loss=actual_width - credit,
            max_profit=credit,
            contracts=contracts,
            total_credit=total_credit,
            total_risk=total_risk,
            margin_required=total_risk,  # Simplified
            expiration_date=str(short_put['expiration_date']),
            dte=short_put['dte']
        )

        return trade

    def settle_trade(self, trade: BullPutSpreadTrade, settlement_price: float):
        """Settle trade at expiration"""

        # Calculate settlement P&L
        pnl_per_spread, outcome = self.calculate_settlement(
            trade.short_strike,
            trade.long_strike,
            settlement_price
        )

        # Add credit to P&L
        net_pnl_per_spread = trade.credit_received + pnl_per_spread

        # Total P&L
        total_pnl = net_pnl_per_spread * 100 * trade.contracts
        pnl_percent = (total_pnl / trade.total_risk * 100) if trade.total_risk > 0 else 0

        # Update trade
        trade.settlement_price = settlement_price
        trade.pnl_per_spread = net_pnl_per_spread
        trade.total_pnl = total_pnl
        trade.pnl_percent = pnl_percent
        trade.outcome = outcome
        trade.short_breached = settlement_price < trade.short_strike
        trade.long_breached = settlement_price < trade.long_strike

        # Update account
        self.cash += total_pnl
        self.equity = self.cash

        return trade

    def run(self) -> Dict:
        """Run the backtest"""
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        trading_days_str = ', '.join([day_names[d] for d in self.trading_days_of_week])

        print("\n" + "=" * 80)
        print("0DTE BULL PUT SPREAD BACKTESTER - USING ORAT DATA")
        print("=" * 80)
        print(f"Period:           {self.start_date} to {self.end_date}")
        print(f"Initial Capital:  ${self.initial_capital:,.2f}")
        print(f"Target Delta:     {self.target_delta} ({self.target_delta*100:.0f} delta puts)")
        print(f"Spread Width:     ${self.spread_width:.0f}")
        print(f"Max Risk/Trade:   {self.max_risk_per_trade_pct}%")
        print(f"Monthly Target:   {self.monthly_return_target}%")
        print(f"Ticker:           {self.ticker}")
        print(f"Trading Days:     {trading_days_str}")
        print(f"VIX Filter:       Skip when VIX > {self.max_vix}")
        print("=" * 80)

        # Get trading days
        print("\nFetching trading days from ORAT database...")
        trading_days = self.get_trading_days()

        if not trading_days:
            print("No trading days found with 0DTE options!")
            return {}

        print(f"Found {len(trading_days)} trading days with 0DTE data")

        # Filter by day of week (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri)
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        selected_days = [day_names[d] for d in self.trading_days_of_week]
        print(f"Filtering to trade only on: {', '.join(selected_days)}")

        original_count = len(trading_days)
        trading_days = [
            d for d in trading_days
            if datetime.strptime(d, '%Y-%m-%d').weekday() in self.trading_days_of_week
        ]
        print(f"Filtered to {len(trading_days)} days (from {original_count})")

        # Load real SPX OHLC data from Yahoo Finance
        self.load_spx_ohlc_data()
        use_real_data = len(self.spx_ohlc) > 0
        if use_real_data:
            print("  Using REAL SPX close prices for settlement")
        else:
            print("  Using SIMULATED settlement prices (install yfinance for real data)")

        # Load VIX data for crash protection
        self.load_vix_data()
        use_vix_filter = len(self.vix_data) > 0
        if use_vix_filter:
            print(f"  VIX filter ENABLED - will skip trading when VIX > {self.max_vix}")
        else:
            print("  VIX filter disabled - no VIX data available")

        # Process each day
        total_days = len(trading_days)
        for i, trade_date in enumerate(trading_days):
            self.days_with_data += 1

            # Progress bar every 10 days
            if i % 10 == 0:
                pct = (i / total_days) * 100
                bar_len = 30
                filled = int(bar_len * i / total_days)
                bar = "=" * filled + "-" * (bar_len - filled)
                print(f"\r[{bar}] {pct:5.1f}% ({i}/{total_days}) | Trades: {len(self.all_trades)} | Equity: ${self.equity:,.0f}", end="", flush=True)

            # Check VIX filter - skip high volatility days (crash protection)
            if use_vix_filter:
                should_trade, skip_reason = self.should_trade(trade_date)
                if not should_trade:
                    self.days_skipped_vix += 1
                    self.days_skipped += 1
                    continue

            # Get options for this day
            options = self.get_options_for_date(trade_date)

            if not options:
                self.days_skipped += 1
                continue

            # Execute trade
            trade = self.execute_trade(trade_date, options)

            if trade:
                # Get settlement price using REAL intraday movement
                if use_real_data:
                    open_price, close_price = self.get_spx_prices(trade_date)
                    if open_price and close_price:
                        # Calculate REAL intraday move from Yahoo
                        # This is the actual Open -> Close movement for the day
                        intraday_move = close_price - open_price

                        # Apply intraday move to ORAT's underlying
                        # ORAT underlying_price represents entry level
                        # Settlement = entry + actual daily movement
                        settlement_price = trade.underlying_price + intraday_move
                    else:
                        # Fallback to ORAT's underlying_price
                        settlement_price = trade.underlying_price
                else:
                    # Simulate settlement based on IV (fallback)
                    iv = trade.short_iv if trade.short_iv > 0 else 0.20
                    settlement_price = self.simulate_settlement(
                        trade.underlying_price, iv, trade_date
                    )

                self.settle_trade(trade, settlement_price)
                self.all_trades.append(trade)
                self.days_traded += 1
            else:
                self.days_skipped += 1

            # Track daily equity
            self.high_water_mark = max(self.high_water_mark, self.equity)
            drawdown = (self.high_water_mark - self.equity) / self.high_water_mark * 100

            wins = sum(1 for t in self.all_trades if t.total_pnl > 0)
            total = len(self.all_trades)
            win_rate = (wins / total * 100) if total > 0 else 0

            daily = DailyEquity(
                date=trade_date,
                equity=self.equity,
                daily_pnl=trade.total_pnl if trade else 0,
                cumulative_pnl=self.equity - self.initial_capital,
                drawdown_pct=drawdown,
                high_water_mark=self.high_water_mark,
                trades_today=1 if trade else 0,
                win_rate_cumulative=win_rate
            )
            self.daily_equity.append(daily)

        # Final progress
        print(f"\r[{'=' * 30}] 100.0% ({total_days}/{total_days}) | Trades: {len(self.all_trades)} | Equity: ${self.equity:,.0f}")
        print()

        return self._generate_results()

    def _generate_results(self) -> Dict:
        """Generate comprehensive results"""

        if not self.all_trades:
            return {"error": "No trades executed"}

        # Basic stats
        wins = [t for t in self.all_trades if t.total_pnl > 0]
        losses = [t for t in self.all_trades if t.total_pnl <= 0]

        total_pnl = sum(t.total_pnl for t in self.all_trades)
        total_return_pct = (self.equity - self.initial_capital) / self.initial_capital * 100

        win_rate = len(wins) / len(self.all_trades) * 100 if self.all_trades else 0

        # Gross profit/loss
        gross_profit = sum(t.total_pnl for t in wins) if wins else 0
        gross_loss = sum(t.total_pnl for t in losses) if losses else 0

        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0

        profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')

        # Expected payoff (average trade)
        expected_payoff = total_pnl / len(self.all_trades) if self.all_trades else 0

        # Drawdowns
        max_dd_pct = max(d.drawdown_pct for d in self.daily_equity) if self.daily_equity else 0
        # Calculate absolute and maximal drawdown in dollars
        peak_equity = self.initial_capital
        max_dd_dollars = 0
        for daily in self.daily_equity:
            peak_equity = max(peak_equity, daily.equity)
            dd = peak_equity - daily.equity
            max_dd_dollars = max(max_dd_dollars, dd)

        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses = 0
        max_consec_win_profit = 0
        max_consec_loss_amount = 0

        current_wins = 0
        current_losses = 0
        current_win_profit = 0
        current_loss_amount = 0

        for trade in self.all_trades:
            if trade.total_pnl > 0:
                current_wins += 1
                current_win_profit += trade.total_pnl
                if current_wins > max_consec_wins:
                    max_consec_wins = current_wins
                    max_consec_win_profit = current_win_profit
                current_losses = 0
                current_loss_amount = 0
            else:
                current_losses += 1
                current_loss_amount += trade.total_pnl
                if current_losses > max_consec_losses:
                    max_consec_losses = current_losses
                    max_consec_loss_amount = current_loss_amount
                current_wins = 0
                current_win_profit = 0

        # Monthly returns
        monthly_returns = self._calculate_monthly_returns()
        avg_monthly = sum(monthly_returns.values()) / len(monthly_returns) if monthly_returns else 0

        # Outcome breakdown
        outcomes = {}
        for t in self.all_trades:
            outcomes[t.outcome] = outcomes.get(t.outcome, 0) + 1

        # Generate backtest ID
        backtest_id = f"0DTE_BPS_{self.start_date}_{self.end_date}_{uuid.uuid4().hex[:8]}"

        results = {
            'summary': {
                'backtest_id': backtest_id,
                'strategy': '0DTE Bull Put Spread',
                'ticker': self.ticker,
                'start_date': self.start_date,
                'end_date': self.end_date,
                'initial_capital': self.initial_capital,
                'final_equity': self.equity,
                'total_pnl': total_pnl,
                'total_return_pct': total_return_pct,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss,
                'max_drawdown_pct': max_dd_pct,
                'max_drawdown_dollars': max_dd_dollars,
            },
            'trades': {
                'total_trades': len(self.all_trades),
                'winning_trades': len(wins),
                'losing_trades': len(losses),
                'win_rate_pct': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'expected_payoff': expected_payoff,
                'largest_win': max(t.total_pnl for t in self.all_trades) if self.all_trades else 0,
                'largest_loss': min(t.total_pnl for t in self.all_trades) if self.all_trades else 0,
                'max_consec_wins': max_consec_wins,
                'max_consec_win_profit': max_consec_win_profit,
                'max_consec_losses': max_consec_losses,
                'max_consec_loss_amount': max_consec_loss_amount,
            },
            'outcomes': outcomes,
            'monthly_returns': monthly_returns,
            'avg_monthly_return_pct': avg_monthly,
            'monthly_target_met': avg_monthly >= self.monthly_return_target,
            'data_quality': {
                'days_with_data': self.days_with_data,
                'days_traded': self.days_traded,
                'days_skipped': self.days_skipped,
                'days_skipped_vix': self.days_skipped_vix,
            },
            'parameters': {
                'target_delta': self.target_delta,
                'spread_width': self.spread_width,
                'max_risk_per_trade_pct': self.max_risk_per_trade_pct,
            }
        }

        self._print_results(results)
        self._save_to_database(results, backtest_id)

        return results

    def _calculate_monthly_returns(self) -> Dict[str, float]:
        """Calculate monthly returns"""
        if not self.daily_equity:
            return {}

        monthly = {}
        current_month = None
        month_start_equity = self.initial_capital

        for daily in self.daily_equity:
            month = daily.date[:7]  # YYYY-MM

            if month != current_month:
                if current_month:
                    month_return = (prev_equity - month_start_equity) / month_start_equity * 100
                    monthly[current_month] = month_return
                current_month = month
                month_start_equity = prev_equity if 'prev_equity' in dir() else self.initial_capital

            prev_equity = daily.equity

        # Final month
        if current_month and prev_equity:
            month_return = (prev_equity - month_start_equity) / month_start_equity * 100
            monthly[current_month] = month_return

        return monthly

    def _print_results(self, results: Dict):
        """Print formatted results in MetaTrader style"""
        s = results['summary']
        t = results['trades']
        o = results['outcomes']

        print("\n" + "=" * 80)
        print("0DTE BULL PUT SPREAD BACKTEST RESULTS")
        print("=" * 80)

        # Period info
        print(f"\nSymbol                 {s['ticker']} (S&P 500 Index)")
        print(f"Period                 {s['start_date']} - {s['end_date']}")
        print(f"Strategy               {s['strategy']}")

        print("-" * 80)

        # Main performance metrics (MetaTrader style)
        print(f"\nInitial deposit        {s['initial_capital']:,.2f}")
        print(f"Total net profit       {s['total_pnl']:,.2f}              Gross profit           {s['gross_profit']:,.2f}")
        print(f"                                               Gross loss             {s['gross_loss']:,.2f}")
        pf_str = f"{t['profit_factor']:.2f}" if t['profit_factor'] != float('inf') else "inf"
        print(f"Profit factor          {pf_str}                Expected payoff        {t['expected_payoff']:,.2f}")
        print(f"Maximal drawdown       {s['max_drawdown_dollars']:,.2f} ({s['max_drawdown_pct']:.2f}%)")

        print("-" * 80)

        # Trade statistics
        print(f"\nTotal trades           {t['total_trades']}")
        win_pct = t['winning_trades'] / t['total_trades'] * 100 if t['total_trades'] > 0 else 0
        loss_pct = t['losing_trades'] / t['total_trades'] * 100 if t['total_trades'] > 0 else 0
        print(f"                       Profit trades (pct of total)   {t['winning_trades']} ({win_pct:.2f}%)")
        print(f"                       Loss trades (pct of total)     {t['losing_trades']} ({loss_pct:.2f}%)")

        print(f"\n                       Largest profit trade          {t['largest_win']:,.2f}")
        print(f"                       Largest loss trade            {t['largest_loss']:,.2f}")

        print(f"\n                       Average profit trade          {t['avg_win']:,.2f}")
        print(f"                       Average loss trade            {t['avg_loss']:,.2f}")

        print(f"\n                       Maximum consecutive wins      {t['max_consec_wins']} ({t['max_consec_win_profit']:,.2f})")
        print(f"                       Maximum consecutive losses    {t['max_consec_losses']} ({t['max_consec_loss_amount']:,.2f})")

        print("-" * 80)

        # Outcome breakdown
        print(f"\nOUTCOME BREAKDOWN:")
        for outcome, count in o.items():
            pct = count / t['total_trades'] * 100 if t['total_trades'] > 0 else 0
            print(f"  {outcome}: {count} ({pct:.1f}%)")

        print("-" * 80)

        # Risk management stats
        dq = results['data_quality']
        print(f"\nRISK MANAGEMENT:")
        print(f"  Days with data:         {dq['days_with_data']}")
        print(f"  Days traded:            {dq['days_traded']}")
        print(f"  Days skipped (VIX):     {dq['days_skipped_vix']} (VIX > {self.max_vix})")
        print(f"  Days skipped (other):   {dq['days_skipped'] - dq['days_skipped_vix']}")

        print("-" * 80)

        # Monthly returns
        print(f"\nMONTHLY RETURNS:")
        print(f"  Average Monthly Return:  {results['avg_monthly_return_pct']:+.2f}%")
        print(f"  Target ({self.monthly_return_target}%):           {'MET' if results['monthly_target_met'] else 'NOT MET'}")

        monthly = results['monthly_returns']
        if monthly:
            print(f"\n  Recent months:")
            for month in list(monthly.keys())[-6:]:
                print(f"    {month}: {monthly[month]:+.2f}%")

        print("\n" + "=" * 80)

    def _save_to_database(self, results: Dict, backtest_id: str):
        """Save backtest results to database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            s = results['summary']
            t = results['trades']

            # Save to zero_dte_backtest_results
            cursor.execute("""
                INSERT INTO zero_dte_backtest_results (
                    backtest_id, strategy_name, symbol, start_date, end_date,
                    config, total_trades, winning_trades, losing_trades, win_rate,
                    total_pnl, total_pnl_pct, avg_trade_pnl, avg_win, avg_loss,
                    largest_win, largest_loss, max_drawdown_pct, profit_factor,
                    days_with_data, days_skipped
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (backtest_id) DO NOTHING
            """, (
                backtest_id,
                '0DTE Bull Put Spread',
                self.ticker,
                self.start_date,
                self.end_date,
                str(results['parameters']),
                t['total_trades'],
                t['winning_trades'],
                t['losing_trades'],
                t['win_rate_pct'],
                s['total_pnl'],
                s['total_return_pct'],
                s['total_pnl'] / t['total_trades'] if t['total_trades'] > 0 else 0,
                t['avg_win'],
                t['avg_loss'],
                t['largest_win'],
                t['largest_loss'],
                s['max_drawdown_pct'],
                t['profit_factor'],
                results['data_quality']['days_with_data'],
                results['data_quality']['days_skipped']
            ))

            # Save individual trades
            for trade in self.all_trades:
                cursor.execute("""
                    INSERT INTO zero_dte_backtest_trades (
                        backtest_id, trade_date, trade_number,
                        underlying_price_entry, short_strike, long_strike,
                        spread_width, entry_credit, short_delta_entry, short_iv_entry,
                        contracts, settlement_price, pnl_per_spread, pnl_percent,
                        total_pnl, outcome, short_strike_breached, long_strike_breached
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    backtest_id,
                    trade.trade_date,
                    trade.trade_number,
                    trade.underlying_price,
                    trade.short_strike,
                    trade.long_strike,
                    trade.spread_width,
                    trade.credit_received,
                    trade.short_delta,
                    trade.short_iv,
                    trade.contracts,
                    trade.settlement_price,
                    trade.pnl_per_spread,
                    trade.pnl_percent,
                    trade.total_pnl,
                    trade.outcome,
                    trade.short_breached,
                    trade.long_breached
                ))

            # Save equity curve
            for daily in self.daily_equity:
                cursor.execute("""
                    INSERT INTO zero_dte_equity_curve (
                        backtest_id, trade_date, equity, daily_pnl,
                        cumulative_pnl, drawdown_pct, high_water_mark
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    backtest_id,
                    daily.date,
                    daily.equity,
                    daily.daily_pnl,
                    daily.cumulative_pnl,
                    daily.drawdown_pct,
                    daily.high_water_mark
                ))

            conn.commit()
            conn.close()

            print(f"\nResults saved to database (backtest_id: {backtest_id})")

        except Exception as e:
            print(f"\nWarning: Could not save to database: {e}")

    def export_trades_to_csv(self, filepath: str = None) -> str:
        """Export all trades to CSV for analysis"""
        import csv

        if filepath is None:
            filepath = f"0dte_bps_trades_{self.start_date}_{self.end_date}.csv"

        with open(filepath, 'w', newline='') as f:
            if self.all_trades:
                writer = csv.DictWriter(f, fieldnames=asdict(self.all_trades[0]).keys())
                writer.writeheader()
                for trade in self.all_trades:
                    writer.writerow(asdict(trade))

        print(f"Exported {len(self.all_trades)} trades to {filepath}")
        return filepath


def main():
    parser = argparse.ArgumentParser(description='0DTE Bull Put Spread Backtester')
    parser.add_argument('--start', default='2020-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2025-12-01', help='End date YYYY-MM-DD')
    parser.add_argument('--capital', type=float, default=1_000_000, help='Initial capital')
    parser.add_argument('--delta', type=float, default=0.15, help='Target delta (e.g., 0.15 for 15 delta)')
    parser.add_argument('--width', type=float, default=10.0, help='Spread width in dollars')
    parser.add_argument('--risk', type=float, default=2.0, help='Max risk per trade (percent)')
    parser.add_argument('--ticker', default='SPXW', help='Ticker (SPXW for weeklies)')
    parser.add_argument('--days', default='0,1', help='Days to trade: 0=Mon,1=Tue,2=Wed,3=Thu,4=Fri (default: 0,1 for Mon-Tue)')
    parser.add_argument('--maxvix', type=float, default=30.0, help='Max VIX to trade (skip days above this, default: 30)')
    parser.add_argument('--export', action='store_true', help='Export trades to CSV')

    args = parser.parse_args()

    # Parse trading days
    trading_days = [int(d.strip()) for d in args.days.split(',')]

    backtester = ZeroDTEBullPutSpreadBacktester(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        target_delta=args.delta,
        spread_width=args.width,
        max_risk_per_trade_pct=args.risk,
        ticker=args.ticker,
        trading_days_of_week=trading_days,
        max_vix=args.maxvix
    )

    results = backtester.run()

    if args.export and backtester.all_trades:
        backtester.export_trades_to_csv()

    return results


if __name__ == "__main__":
    main()
