#!/usr/bin/env python3
"""
0DTE Iron Condor Strategy - Optimized for 10% Monthly Returns

QUANT STRATEGY DESIGN:
======================
This strategy aims for aggressive returns through premium collection on BOTH sides.

Key Innovations:
1. IRON CONDOR: Sell Bull Put + Bear Call every day (double premium)
2. TIGHTER STRIKES: 0.5 SD from open (more premium, higher win rate in range)
3. AGGRESSIVE SIZING: 5% risk per leg (10% total daily risk exposure)
4. IV-BASED ADJUSTMENTS: Wider spreads when IV is high
5. NO PROFIT TARGET: Let 0DTE expire for full credit
6. TIGHT STOP: 1.5x credit to cut losses fast

The Math:
---------
Iron Condor profit zone: Open ± 0.5 SD
- In normal markets, ~38% of days stay within 0.5 SD
- But 0DTE settles at close, and most intraday moves mean-revert
- Historical SPX data shows ~60-65% of days close within 0.5 SD of open

Risk/Reward:
- Credit received: ~$3-4 per $10 spread (30-40% of width)
- Max loss per leg: $10 - credit = ~$6-7
- With BOTH legs, total credit: ~$6-8 per iron condor
- Max loss: $10 (only one side can lose)

Expected Value:
- Win rate: ~60% (both legs profit)
- Partial win: ~25% (one leg profits, one loses)
- Full loss: ~15% (one side max loss)
- EV = 0.60 * $6 + 0.25 * $0 - 0.15 * $4 = $3.00 per IC

Usage:
    python backtest/zero_dte_iron_condor.py --start 2021-01-01 --end 2025-12-01 --capital 1000000
"""

import os
import sys
import uuid
import argparse
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
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


@dataclass
class IronCondorTrade:
    """Single 0DTE Iron Condor trade (Bull Put + Bear Call combined)"""
    trade_date: str
    trade_number: int

    # Underlying
    underlying_price: float
    open_price: float

    # Bull Put Spread (lower wing)
    put_short_strike: float
    put_long_strike: float
    put_credit: float
    put_short_delta: float
    put_short_iv: float

    # Bear Call Spread (upper wing)
    call_short_strike: float
    call_long_strike: float
    call_credit: float
    call_short_delta: float
    call_short_iv: float

    # Combined Iron Condor
    total_credit: float  # Per iron condor
    max_loss: float  # Per iron condor (width - total_credit, only one side can lose)
    spread_width: float

    # Position sizing
    contracts: int
    total_premium: float  # Total credit received
    total_risk: float  # Max possible loss
    margin_required: float

    # Settlement
    settlement_price: float = 0.0
    daily_low: float = 0.0
    daily_high: float = 0.0

    # P&L
    put_pnl: float = 0.0
    call_pnl: float = 0.0
    total_pnl: float = 0.0
    pnl_percent: float = 0.0

    # Classification
    outcome: str = ""  # "FULL_WIN", "PUT_LOSS", "CALL_LOSS", "STOPPED_PUT", "STOPPED_CALL"
    put_breached: bool = False
    call_breached: bool = False

    # Metadata
    vix_at_entry: float = 0.0
    iv_rank: float = 0.0  # IV percentile
    expected_move: float = 0.0


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


class IronCondorBacktester:
    """
    Backtester for 0DTE Iron Condor strategy on SPX.

    Strategy: Sell BOTH Bull Put Spread AND Bear Call Spread each day.
    This creates a profit zone where SPX can move within ±X SD.
    """

    def __init__(
        self,
        start_date: str = "2021-01-01",
        end_date: str = None,
        initial_capital: float = 1_000_000,
        spread_width: float = 10.0,
        put_sd: float = 0.5,  # SDs below open for put spread
        call_sd: float = 0.5,  # SDs above open for call spread
        risk_per_leg_pct: float = 5.0,  # Risk per leg (5% = 10% total)
        ticker: str = "SPX",
        stop_loss_multiplier: float = 1.5,  # Tighter stop for faster cut
        use_profit_target: bool = False,  # Let 0DTE expire
        profit_target_pct: float = 80.0,  # If enabled, take at 80%
        iv_adjust: bool = True,  # Adjust strikes based on IV
        min_credit_pct: float = 25.0,  # Min credit as % of width (skip if too low)
    ):
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        self.initial_capital = initial_capital
        self.spread_width = spread_width
        self.put_sd = put_sd
        self.call_sd = call_sd
        self.risk_per_leg_pct = risk_per_leg_pct
        self.ticker = ticker
        self.stop_loss_multiplier = stop_loss_multiplier
        self.use_profit_target = use_profit_target
        self.profit_target_pct = profit_target_pct
        self.iv_adjust = iv_adjust
        self.min_credit_pct = min_credit_pct

        # State
        self.cash = initial_capital
        self.equity = initial_capital
        self.high_water_mark = initial_capital

        # Tracking
        self.all_trades: List[IronCondorTrade] = []
        self.daily_equity: List[DailyEquity] = []
        self.trade_counter = 0

        # Stats
        self.days_traded = 0
        self.days_with_data = 0
        self.days_skipped = 0

        # Cache
        self.spx_ohlc: Dict[str, Dict] = {}
        self.vix_data: Dict[str, float] = {}
        self.iv_history: List[float] = []  # For IV rank calculation

    def get_connection(self):
        """Get database connection"""
        from database_adapter import get_connection
        return get_connection()

    def load_spx_ohlc_data(self):
        """Load SPX OHLC data from Yahoo Finance"""
        if not YFINANCE_AVAILABLE:
            print("  yfinance not available - will use simulated settlement")
            return

        print("  Loading SPX price data from Yahoo Finance...")
        try:
            start = datetime.strptime(self.start_date, '%Y-%m-%d') - timedelta(days=30)
            end = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=5)

            spx = yf.Ticker("^GSPC")
            hist = spx.history(start=start, end=end)

            for date_idx, row in hist.iterrows():
                date_str = date_idx.strftime('%Y-%m-%d')
                self.spx_ohlc[date_str] = {
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row['Volume'])
                }
            print(f"  Loaded {len(self.spx_ohlc)} days of SPX OHLC data")
        except Exception as e:
            print(f"  Warning: Failed to load SPX data: {e}")

    def load_vix_data(self):
        """Load VIX data for context"""
        if not YFINANCE_AVAILABLE:
            return

        print("  Loading VIX data...")
        try:
            start = datetime.strptime(self.start_date, '%Y-%m-%d') - timedelta(days=365)
            end = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=5)

            vix = yf.Ticker("^VIX")
            hist = vix.history(start=start, end=end)

            for date_idx, row in hist.iterrows():
                date_str = date_idx.strftime('%Y-%m-%d')
                self.vix_data[date_str] = float(row['Close'])
                self.iv_history.append(float(row['Close']))

            print(f"  Loaded {len(self.vix_data)} days of VIX data")
        except Exception as e:
            print(f"  Warning: Failed to load VIX data: {e}")

    def get_iv_rank(self, current_vix: float) -> float:
        """Calculate IV rank (percentile over last 252 days)"""
        if len(self.iv_history) < 20:
            return 50.0  # Default to middle

        # Use last 252 days (1 year)
        lookback = self.iv_history[-252:] if len(self.iv_history) >= 252 else self.iv_history

        below = sum(1 for v in lookback if v < current_vix)
        return (below / len(lookback)) * 100

    def get_spx_prices(self, trade_date: str) -> Tuple[float, float, float, float]:
        """Get OHLC for a date"""
        if trade_date in self.spx_ohlc:
            data = self.spx_ohlc[trade_date]
            return data['open'], data['high'], data['low'], data['close']
        return None, None, None, None

    def calculate_expected_move(self, price: float, iv: float) -> float:
        """Calculate 1 SD expected move for 0DTE"""
        # Daily expected move = Price * IV * sqrt(1/252)
        return price * iv * math.sqrt(1/252)

    def get_trading_days(self) -> List[str]:
        """Get list of trading days with 0DTE options"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Query for days with 0DTE options
        cursor.execute("""
            SELECT DISTINCT trade_date
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date >= %s
              AND trade_date <= %s
              AND dte <= 1
            ORDER BY trade_date
        """, (self.ticker, self.start_date, self.end_date))

        days = [row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()]
        conn.close()

        return days

    def get_options_for_date(self, trade_date: str) -> List[Dict]:
        """Get all 0DTE options for a date"""
        conn = self.get_connection()
        cursor = conn.cursor()

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
                call_bid,
                call_ask,
                call_mid,
                delta,
                put_iv,
                call_iv,
                dte
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date = %s
              AND dte <= 1
            ORDER BY strike DESC
        """, (self.ticker, trade_date))

        columns = ['trade_date', 'ticker', 'expiration_date', 'strike',
                   'underlying_price', 'put_bid', 'put_ask', 'put_mid',
                   'call_bid', 'call_ask', 'call_mid',
                   'delta', 'put_iv', 'call_iv', 'dte']

        options = []
        for row in cursor.fetchall():
            opt = dict(zip(columns, row))
            for key in ['strike', 'underlying_price', 'put_bid', 'put_ask',
                       'put_mid', 'call_bid', 'call_ask', 'call_mid',
                       'delta', 'put_iv', 'call_iv']:
                if opt[key] is not None:
                    opt[key] = float(opt[key])
            options.append(opt)

        conn.close()
        return options

    def find_put_spread(self, options: List[Dict], target_strike: float) -> Optional[Tuple[Dict, Dict]]:
        """Find bull put spread at target strike"""
        if not options:
            return None

        underlying = options[0]['underlying_price']

        # OTM puts (strikes below current price)
        otm_puts = [
            opt for opt in options
            if opt['strike'] < underlying
            and opt.get('put_bid') and opt['put_bid'] > 0
        ]

        if not otm_puts:
            return None

        # Find short put closest to target
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - target_strike))

        # Find long put at width below
        long_strike = short_put['strike'] - self.spread_width

        long_candidates = [
            opt for opt in options
            if abs(opt['strike'] - long_strike) < 1
            and opt.get('put_ask') and opt['put_ask'] > 0
        ]

        if not long_candidates:
            long_candidates = [
                opt for opt in options
                if opt['strike'] < short_put['strike']
                and opt.get('put_ask') and opt['put_ask'] > 0
            ]
            if not long_candidates:
                return None
            long_put = max(long_candidates, key=lambda x: x['strike'])
        else:
            long_put = min(long_candidates, key=lambda x: abs(x['strike'] - long_strike))

        if long_put['strike'] >= short_put['strike']:
            return None

        return (short_put, long_put)

    def find_call_spread(self, options: List[Dict], target_strike: float) -> Optional[Tuple[Dict, Dict]]:
        """Find bear call spread at target strike"""
        if not options:
            return None

        underlying = options[0]['underlying_price']

        # OTM calls (strikes above current price)
        otm_calls = [
            opt for opt in options
            if opt['strike'] > underlying
            and opt.get('call_bid') and opt['call_bid'] > 0
        ]

        if not otm_calls:
            return None

        # Find short call closest to target
        short_call = min(otm_calls, key=lambda x: abs(x['strike'] - target_strike))

        # Find long call at width above
        long_strike = short_call['strike'] + self.spread_width

        long_candidates = [
            opt for opt in options
            if abs(opt['strike'] - long_strike) < 1
            and opt.get('call_ask') and opt['call_ask'] > 0
        ]

        if not long_candidates:
            long_candidates = [
                opt for opt in options
                if opt['strike'] > short_call['strike']
                and opt.get('call_ask') and opt['call_ask'] > 0
            ]
            if not long_candidates:
                return None
            long_call = min(long_candidates, key=lambda x: x['strike'])
        else:
            long_call = min(long_candidates, key=lambda x: abs(x['strike'] - long_strike))

        if long_call['strike'] <= short_call['strike']:
            return None

        return (short_call, long_call)

    def calculate_put_credit(self, short_put: Dict, long_put: Dict) -> float:
        """Calculate credit for bull put spread"""
        short_bid = short_put.get('put_bid', 0) or 0
        long_ask = long_put.get('put_ask', 0) or 0
        return max(0, short_bid - long_ask)

    def calculate_call_credit(self, short_call: Dict, long_call: Dict) -> float:
        """Calculate credit for bear call spread"""
        short_bid = short_call.get('call_bid', 0) or 0
        long_ask = long_call.get('call_ask', 0) or 0
        return max(0, short_bid - long_ask)

    def size_position(self, total_credit: float, max_loss_per_ic: float) -> Tuple[int, float, float]:
        """
        Size iron condor position based on risk parameters.

        For iron condor, only ONE side can lose max (they're opposite directions).
        So max_loss = spread_width - total_credit (not 2x)
        """
        # Risk budget for iron condor (both legs combined)
        total_risk_pct = self.risk_per_leg_pct * 2  # 10% if 5% per leg
        risk_budget = self.equity * (total_risk_pct / 100)

        # Max loss per iron condor
        if max_loss_per_ic <= 0:
            return 0, 0, 0

        # Calculate contracts
        contracts = int(risk_budget / (max_loss_per_ic * 100))
        contracts = max(1, min(contracts, 200))  # 1-200 contracts

        total_premium = total_credit * 100 * contracts
        total_risk = max_loss_per_ic * 100 * contracts

        return contracts, total_premium, total_risk

    def execute_iron_condor(self, trade_date: str, options: List[Dict],
                             open_price: float, avg_iv: float, vix: float) -> Optional[IronCondorTrade]:
        """Execute iron condor trade"""
        if not options or not open_price or not avg_iv:
            return None

        # Calculate expected move
        expected_move = self.calculate_expected_move(open_price, avg_iv)

        # Adjust SD based on IV rank (tighter in low IV, wider in high IV)
        iv_rank = self.get_iv_rank(vix) if vix else 50

        if self.iv_adjust:
            # In high IV (rank > 70), use wider strikes for safety
            # In low IV (rank < 30), can be tighter
            if iv_rank > 70:
                put_sd_adj = self.put_sd * 1.2
                call_sd_adj = self.call_sd * 1.2
            elif iv_rank < 30:
                put_sd_adj = self.put_sd * 0.9
                call_sd_adj = self.call_sd * 0.9
            else:
                put_sd_adj = self.put_sd
                call_sd_adj = self.call_sd
        else:
            put_sd_adj = self.put_sd
            call_sd_adj = self.call_sd

        # Calculate target strikes
        put_target = open_price - (put_sd_adj * expected_move)
        call_target = open_price + (call_sd_adj * expected_move)

        # Round to nearest $5 (SPX strikes)
        put_target = round(put_target / 5) * 5
        call_target = round(call_target / 5) * 5

        # Find spreads
        put_spread = self.find_put_spread(options, put_target)
        call_spread = self.find_call_spread(options, call_target)

        if not put_spread or not call_spread:
            return None

        short_put, long_put = put_spread
        short_call, long_call = call_spread

        # Calculate credits
        put_credit = self.calculate_put_credit(short_put, long_put)
        call_credit = self.calculate_call_credit(short_call, long_call)
        total_credit = put_credit + call_credit

        # Check minimum credit threshold
        min_credit = self.spread_width * (self.min_credit_pct / 100)
        if total_credit < min_credit:
            return None

        # Max loss: only one side can lose (they're opposite directions)
        # If price crashes: put side loses, call side wins full credit
        # If price spikes: call side loses, put side wins full credit
        max_loss = self.spread_width - total_credit

        # Size position
        contracts, total_premium, total_risk = self.size_position(total_credit, max_loss)

        if contracts == 0:
            return None

        self.trade_counter += 1

        trade = IronCondorTrade(
            trade_date=trade_date,
            trade_number=self.trade_counter,
            underlying_price=short_put['underlying_price'],
            open_price=open_price,
            put_short_strike=short_put['strike'],
            put_long_strike=long_put['strike'],
            put_credit=put_credit,
            put_short_delta=short_put['delta'],
            put_short_iv=short_put.get('put_iv', 0) or 0,
            call_short_strike=short_call['strike'],
            call_long_strike=long_call['strike'],
            call_credit=call_credit,
            call_short_delta=short_call['delta'],
            call_short_iv=short_call.get('call_iv', 0) or 0,
            total_credit=total_credit,
            max_loss=max_loss,
            spread_width=self.spread_width,
            contracts=contracts,
            total_premium=total_premium,
            total_risk=total_risk,
            margin_required=total_risk,
            vix_at_entry=vix,
            iv_rank=iv_rank,
            expected_move=expected_move
        )

        return trade

    def settle_trade(self, trade: IronCondorTrade, settlement_price: float,
                     daily_low: float, daily_high: float):
        """
        Settle iron condor with stop loss logic.

        Stop loss checks:
        - Put side: if LOW < (put_short_strike - stop_loss_price)
        - Call side: if HIGH > (call_short_strike + stop_loss_price)
        """
        put_credit = trade.put_credit
        call_credit = trade.call_credit

        # Stop loss prices
        put_stop_price = trade.put_short_strike - (put_credit * self.stop_loss_multiplier)
        call_stop_price = trade.call_short_strike + (call_credit * self.stop_loss_multiplier)

        trade.daily_low = daily_low if daily_low else settlement_price
        trade.daily_high = daily_high if daily_high else settlement_price
        trade.settlement_price = settlement_price

        put_pnl = 0
        call_pnl = 0
        outcome = ""

        # Check put side stop loss
        put_stopped = daily_low is not None and daily_low < put_stop_price

        # Check call side stop loss
        call_stopped = daily_high is not None and daily_high > call_stop_price

        # Calculate put side P&L
        if put_stopped:
            # Stopped out on put side
            put_loss = put_credit * self.stop_loss_multiplier
            put_pnl = put_credit - put_loss  # Net loss
            trade.put_breached = True
            outcome = "STOPPED_PUT"
        elif settlement_price >= trade.put_short_strike:
            # Both puts OTM - keep full credit
            put_pnl = put_credit
        elif settlement_price > trade.put_long_strike:
            # Short put ITM, long put OTM - partial loss
            intrinsic = trade.put_short_strike - settlement_price
            put_pnl = put_credit - intrinsic
            trade.put_breached = True
        else:
            # Both puts ITM - max loss on put side
            put_pnl = put_credit - self.spread_width
            trade.put_breached = True

        # Calculate call side P&L
        if call_stopped:
            # Stopped out on call side
            call_loss = call_credit * self.stop_loss_multiplier
            call_pnl = call_credit - call_loss  # Net loss
            trade.call_breached = True
            if outcome == "":
                outcome = "STOPPED_CALL"
            else:
                outcome = "STOPPED_BOTH"
        elif settlement_price <= trade.call_short_strike:
            # Both calls OTM - keep full credit
            call_pnl = call_credit
        elif settlement_price < trade.call_long_strike:
            # Short call ITM, long call OTM - partial loss
            intrinsic = settlement_price - trade.call_short_strike
            call_pnl = call_credit - intrinsic
            trade.call_breached = True
        else:
            # Both calls ITM - max loss on call side
            call_pnl = call_credit - self.spread_width
            trade.call_breached = True

        # Determine outcome
        if outcome == "":
            if not trade.put_breached and not trade.call_breached:
                outcome = "FULL_WIN"
            elif trade.put_breached and not trade.call_breached:
                outcome = "PUT_LOSS"
            elif trade.call_breached and not trade.put_breached:
                outcome = "CALL_LOSS"
            else:
                outcome = "DOUBLE_LOSS"  # Very rare - massive whipsaw

        # Total P&L
        trade.put_pnl = put_pnl
        trade.call_pnl = call_pnl

        total_pnl_per_ic = put_pnl + call_pnl
        trade.total_pnl = total_pnl_per_ic * 100 * trade.contracts
        trade.pnl_percent = (trade.total_pnl / trade.total_risk * 100) if trade.total_risk > 0 else 0
        trade.outcome = outcome

        # Update account
        self.cash += trade.total_pnl
        self.equity = self.cash

        return trade

    def run(self) -> Dict:
        """Run the backtest"""
        print("\n" + "=" * 80)
        print("0DTE IRON CONDOR BACKTESTER - AGGRESSIVE 10% MONTHLY TARGET")
        print("=" * 80)
        print(f"Period:             {self.start_date} to {self.end_date}")
        print(f"Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"Strategy:           Iron Condor (Bull Put + Bear Call)")
        print(f"Put Strike:         {self.put_sd} SD below open")
        print(f"Call Strike:        {self.call_sd} SD above open")
        print(f"Spread Width:       ${self.spread_width:.0f}")
        print(f"Risk Per Leg:       {self.risk_per_leg_pct}% ({self.risk_per_leg_pct * 2}% total)")
        print(f"Stop Loss:          {self.stop_loss_multiplier}x credit")
        print(f"IV Adjustment:      {'Enabled' if self.iv_adjust else 'Disabled'}")
        print(f"Min Credit:         {self.min_credit_pct}% of width")
        print(f"Ticker:             {self.ticker}")
        print("=" * 80)

        # Get trading days
        print("\nFetching trading days from ORAT database...")
        trading_days = self.get_trading_days()

        if not trading_days:
            print("No trading days found with 0DTE options!")
            print(f"Check that ticker '{self.ticker}' exists in your database.")
            return {}

        print(f"Found {len(trading_days)} trading days with 0DTE data")

        # Load price data
        self.load_spx_ohlc_data()
        use_real_data = len(self.spx_ohlc) > 0

        self.load_vix_data()

        if use_real_data:
            print("  Using REAL SPX prices for settlement")
        else:
            print("  Using SIMULATED settlement (install yfinance for real data)")

        # Process each day
        total_days = len(trading_days)
        for i, trade_date in enumerate(trading_days):
            self.days_with_data += 1

            # Progress
            if i % 10 == 0:
                pct = (i / total_days) * 100
                bar_len = 30
                filled = int(bar_len * i / total_days)
                bar = "=" * filled + "-" * (bar_len - filled)
                print(f"\r[{bar}] {pct:5.1f}% ({i}/{total_days}) | Trades: {len(self.all_trades)} | Equity: ${self.equity:,.0f}", end="", flush=True)

            # Get OHLC data
            open_price, high_price, low_price, close_price = self.get_spx_prices(trade_date)

            if not open_price:
                self.days_skipped += 1
                continue

            # Get VIX
            vix = self.vix_data.get(trade_date, 20.0)

            # Get options
            options = self.get_options_for_date(trade_date)

            if not options:
                self.days_skipped += 1
                continue

            # Get average IV
            ivs = [opt['put_iv'] for opt in options if opt.get('put_iv') and opt['put_iv'] > 0]
            if not ivs:
                ivs = [opt['call_iv'] for opt in options if opt.get('call_iv') and opt['call_iv'] > 0]
            avg_iv = sum(ivs) / len(ivs) if ivs else 0.20

            # Execute iron condor
            trade = self.execute_iron_condor(trade_date, options, open_price, avg_iv, vix)

            if trade:
                # Settle
                settlement_price = close_price if close_price else open_price
                self.settle_trade(trade, settlement_price, low_price, high_price)
                self.all_trades.append(trade)
                self.days_traded += 1
            else:
                self.days_skipped += 1

            # Track equity
            self.high_water_mark = max(self.high_water_mark, self.equity)

        print(f"\r[{'=' * 30}] 100.0% Complete!{' ' * 40}")

        # Calculate results
        results = self.calculate_results()
        self.print_results(results)

        return results

    def calculate_results(self) -> Dict:
        """Calculate comprehensive results"""
        if not self.all_trades:
            return {}

        total_pnl = sum(t.total_pnl for t in self.all_trades)
        total_return_pct = (total_pnl / self.initial_capital) * 100

        wins = [t for t in self.all_trades if t.total_pnl > 0]
        losses = [t for t in self.all_trades if t.total_pnl <= 0]

        win_rate = len(wins) / len(self.all_trades) * 100 if self.all_trades else 0

        gross_profit = sum(t.total_pnl for t in wins)
        gross_loss = sum(t.total_pnl for t in losses)

        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0

        profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')

        # Monthly returns
        monthly_returns = {}
        for t in self.all_trades:
            month = t.trade_date[:7]
            monthly_returns[month] = monthly_returns.get(month, 0) + t.total_pnl

        # Convert to percentages
        monthly_pct = {m: (pnl / self.initial_capital) * 100 for m, pnl in monthly_returns.items()}
        avg_monthly = sum(monthly_pct.values()) / len(monthly_pct) if monthly_pct else 0

        # Outcome breakdown
        outcomes = {}
        for t in self.all_trades:
            outcomes[t.outcome] = outcomes.get(t.outcome, 0) + 1

        # Max drawdown
        peak = self.initial_capital
        max_dd = 0
        running_equity = self.initial_capital
        for t in self.all_trades:
            running_equity += t.total_pnl
            peak = max(peak, running_equity)
            dd = (peak - running_equity) / peak * 100
            max_dd = max(max_dd, dd)

        # Full wins vs partial
        full_wins = len([t for t in self.all_trades if t.outcome == "FULL_WIN"])
        put_losses = len([t for t in self.all_trades if t.outcome == "PUT_LOSS"])
        call_losses = len([t for t in self.all_trades if t.outcome == "CALL_LOSS"])

        return {
            'summary': {
                'strategy': '0DTE Iron Condor',
                'ticker': self.ticker,
                'start_date': self.start_date,
                'end_date': self.end_date,
                'initial_capital': self.initial_capital,
                'final_equity': self.equity,
                'total_pnl': total_pnl,
                'total_return_pct': total_return_pct,
                'avg_monthly_return_pct': avg_monthly,
                'target_monthly': 10.0,
                'target_met': avg_monthly >= 10.0,
            },
            'trades': {
                'total': len(self.all_trades),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'largest_win': max(t.total_pnl for t in self.all_trades) if self.all_trades else 0,
                'largest_loss': min(t.total_pnl for t in self.all_trades) if self.all_trades else 0,
            },
            'risk': {
                'max_drawdown_pct': max_dd,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss,
            },
            'outcomes': outcomes,
            'outcome_analysis': {
                'full_wins': full_wins,
                'full_win_pct': (full_wins / len(self.all_trades) * 100) if self.all_trades else 0,
                'put_losses': put_losses,
                'call_losses': call_losses,
            },
            'monthly_returns': monthly_pct,
            'days': {
                'with_data': self.days_with_data,
                'traded': self.days_traded,
                'skipped': self.days_skipped,
            },
            'parameters': {
                'put_sd': self.put_sd,
                'call_sd': self.call_sd,
                'spread_width': self.spread_width,
                'risk_per_leg_pct': self.risk_per_leg_pct,
                'stop_loss_multiplier': self.stop_loss_multiplier,
            }
        }

    def print_results(self, results: Dict):
        """Print formatted results"""
        if not results:
            print("No results to display")
            return

        s = results['summary']
        t = results['trades']
        r = results['risk']
        o = results['outcomes']
        oa = results['outcome_analysis']

        print("\n" + "=" * 80)
        print("0DTE IRON CONDOR RESULTS - TARGETING 10% MONTHLY")
        print("=" * 80)

        print(f"\nSymbol                 {s['ticker']}")
        print(f"Period                 {s['start_date']} - {s['end_date']}")
        print(f"Strategy               {s['strategy']}")

        print("-" * 80)
        print(f"\nINITIAL CAPITAL        ${s['initial_capital']:>15,.2f}")
        print(f"FINAL EQUITY           ${s['final_equity']:>15,.2f}")
        print(f"TOTAL P&L              ${s['total_pnl']:>15,.2f}")
        print(f"TOTAL RETURN           {s['total_return_pct']:>15.2f}%")

        print("-" * 80)
        print(f"\nMONTHLY PERFORMANCE:")
        print(f"  Average Monthly Return:  {s['avg_monthly_return_pct']:+.2f}%")
        print(f"  Target (10%):            {'✓ MET' if s['target_met'] else '✗ NOT MET'}")

        print("-" * 80)
        print(f"\nTRADE STATISTICS:")
        print(f"  Total Trades:            {t['total']}")
        print(f"  Winning Trades:          {t['wins']} ({t['win_rate']:.1f}%)")
        print(f"  Losing Trades:           {t['losses']}")
        print(f"  Profit Factor:           {t['profit_factor']:.2f}")
        print(f"  Average Win:             ${t['avg_win']:,.2f}")
        print(f"  Average Loss:            ${t['avg_loss']:,.2f}")
        print(f"  Largest Win:             ${t['largest_win']:,.2f}")
        print(f"  Largest Loss:            ${t['largest_loss']:,.2f}")

        print("-" * 80)
        print(f"\nRISK METRICS:")
        print(f"  Max Drawdown:            {r['max_drawdown_pct']:.2f}%")
        print(f"  Gross Profit:            ${r['gross_profit']:,.2f}")
        print(f"  Gross Loss:              ${r['gross_loss']:,.2f}")

        print("-" * 80)
        print(f"\nOUTCOME BREAKDOWN:")
        print(f"  Full Wins (both sides):  {oa['full_wins']} ({oa['full_win_pct']:.1f}%)")
        print(f"  Put Side Losses:         {oa['put_losses']}")
        print(f"  Call Side Losses:        {oa['call_losses']}")

        for outcome, count in o.items():
            pct = count / t['total'] * 100 if t['total'] > 0 else 0
            print(f"  {outcome}: {count} ({pct:.1f}%)")

        print("-" * 80)
        print(f"\nMONTHLY RETURNS:")
        for month, pct in sorted(results['monthly_returns'].items()):
            bar = "+" * int(max(0, pct)) + "-" * int(max(0, -pct))
            print(f"  {month}: {pct:+7.2f}% {bar[:20]}")

        print("=" * 80)

    def export_trades(self, filename: str = None):
        """Export trades to CSV"""
        if not self.all_trades:
            print("No trades to export")
            return

        import csv

        if not filename:
            filename = f"iron_condor_trades_{self.start_date}_{self.end_date}.csv"

        filepath = Path(__file__).parent / filename

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self.all_trades[0]).keys())
            writer.writeheader()
            for trade in self.all_trades:
                writer.writerow(asdict(trade))

        print(f"\nExported {len(self.all_trades)} trades to {filepath}")


def main():
    parser = argparse.ArgumentParser(description='0DTE Iron Condor Backtester - 10% Monthly Target')

    parser.add_argument('--start', default='2021-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-12-01', help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=1_000_000, help='Initial capital')
    parser.add_argument('--width', type=float, default=10.0, help='Spread width ($)')
    parser.add_argument('--putsd', type=float, default=0.5, help='Put strike SDs below open')
    parser.add_argument('--callsd', type=float, default=0.5, help='Call strike SDs above open')
    parser.add_argument('--risk', type=float, default=5.0, help='Risk per leg (%)')
    parser.add_argument('--ticker', default='SPX', help='Ticker symbol')
    parser.add_argument('--stoploss', type=float, default=1.5, help='Stop loss multiplier')
    parser.add_argument('--mincredit', type=float, default=25.0, help='Min credit as % of width')
    parser.add_argument('--noivadj', action='store_true', help='Disable IV-based adjustments')
    parser.add_argument('--export', action='store_true', help='Export trades to CSV')

    args = parser.parse_args()

    backtester = IronCondorBacktester(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        spread_width=args.width,
        put_sd=args.putsd,
        call_sd=args.callsd,
        risk_per_leg_pct=args.risk,
        ticker=args.ticker,
        stop_loss_multiplier=args.stoploss,
        min_credit_pct=args.mincredit,
        iv_adjust=not args.noivadj,
    )

    results = backtester.run()

    if args.export and backtester.all_trades:
        backtester.export_trades()

    return results


if __name__ == "__main__":
    main()
