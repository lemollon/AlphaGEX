#!/usr/bin/env python3
"""
HYBRID SCALING Iron Condor Strategy

Automatically scales DTE and position size based on account size to handle liquidity.

SCALING TIERS:
==============
| Account Size    | Strategy      | DTE    | Max Contracts | Trade Freq |
|-----------------|---------------|--------|---------------|------------|
| $100K - $2M     | 0DTE Condor   | 0-1    | 100           | Daily      |
| $2M - $5M       | Weekly Condor | 5-7    | 300           | Daily      |
| $5M - $15M      | Monthly Condor| 21-35  | 500           | 3x/week    |
| $15M+           | Monthly Condor| 30-45  | 1000          | 2x/week    |

KEY FEATURES:
- Automatic DTE selection based on account size
- Liquidity-aware position sizing
- Realistic transaction costs
- Reduced trade frequency at larger sizes
- Smooth transitions between tiers

Usage:
    python backtest/zero_dte_hybrid_scaling.py --start 2021-01-01 --end 2025-12-01
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
    min_dte: int
    max_dte: int
    max_contracts: int
    trades_per_week: int  # Max trades per week
    commission_per_leg: float
    slippage_per_spread: float


# Define scaling tiers
SCALING_TIERS = [
    ScalingTier(
        name="TIER_1_0DTE",
        min_equity=0,
        max_equity=2_000_000,
        min_dte=0,
        max_dte=1,
        max_contracts=100,
        trades_per_week=5,  # Daily
        commission_per_leg=0.65,
        slippage_per_spread=0.10,
    ),
    ScalingTier(
        name="TIER_2_WEEKLY",
        min_equity=2_000_000,
        max_equity=5_000_000,
        min_dte=5,
        max_dte=7,
        max_contracts=300,
        trades_per_week=5,  # Daily
        commission_per_leg=0.65,
        slippage_per_spread=0.08,  # Better fills on weeklies
    ),
    ScalingTier(
        name="TIER_3_MONTHLY",
        min_equity=5_000_000,
        max_equity=15_000_000,
        min_dte=21,
        max_dte=35,
        max_contracts=500,
        trades_per_week=3,  # Mon/Wed/Fri
        commission_per_leg=0.65,
        slippage_per_spread=0.05,  # Better fills on monthlies
    ),
    ScalingTier(
        name="TIER_4_LARGE",
        min_equity=15_000_000,
        max_equity=float('inf'),
        min_dte=30,
        max_dte=45,
        max_contracts=1000,
        trades_per_week=2,  # Tue/Thu
        commission_per_leg=0.50,  # Volume discount
        slippage_per_spread=0.03,  # Institutional execution
    ),
]


@dataclass
class HybridTrade:
    """Trade with tier information"""
    trade_date: str
    trade_number: int

    # Tier info
    tier_name: str
    account_equity_at_entry: float
    dte_used: int

    # Market context
    vix: float
    open_price: float
    underlying_price: float
    expected_move: float

    # Put spread
    put_short_strike: float
    put_long_strike: float
    put_credit: float

    # Call spread
    call_short_strike: float
    call_long_strike: float
    call_credit: float

    # Combined
    total_credit: float
    spread_width: float
    max_loss: float

    # Costs
    commission_total: float
    slippage_total: float
    total_costs: float

    # Sizing
    contracts: int
    contracts_requested: int
    total_premium: float
    total_risk: float
    risk_pct: float

    # Settlement
    settlement_price: float = 0

    # P&L
    gross_pnl: float = 0
    net_pnl: float = 0
    return_pct: float = 0

    # Outcome
    outcome: str = ""
    put_breached: bool = False
    call_breached: bool = False


class HybridScalingBacktester:
    """
    Hybrid strategy that automatically scales based on account size.

    As the account grows:
    1. Switches to longer DTE for more liquidity
    2. Increases max contract size
    3. Reduces trade frequency to avoid market impact
    """

    def __init__(
        self,
        start_date: str = "2021-01-01",
        end_date: str = None,
        initial_capital: float = 1_000_000,
        spread_width: float = 10.0,
        sd_multiplier: float = 1.0,
        risk_per_trade_pct: float = 5.0,  # More conservative for scaling
        ticker: str = "SPX",
    ):
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        self.initial_capital = initial_capital
        self.spread_width = spread_width
        self.sd_multiplier = sd_multiplier
        self.risk_per_trade_pct = risk_per_trade_pct
        self.ticker = ticker

        # State
        self.equity = initial_capital
        self.high_water_mark = initial_capital

        # Tracking
        self.all_trades: List[HybridTrade] = []
        self.trade_counter = 0

        # Stats by tier
        self.tier_stats = {tier.name: {'trades': 0, 'pnl': 0, 'days': 0} for tier in SCALING_TIERS}

        # Weekly trade counter (reset each week)
        self.current_week = None
        self.trades_this_week = 0

        # Costs tracking
        self.total_commissions = 0
        self.total_slippage = 0

        # Cache
        self.spx_ohlc: Dict[str, Dict] = {}
        self.vix_data: Dict[str, float] = {}

    def get_connection(self):
        from database_adapter import get_connection
        return get_connection()

    def get_current_tier(self) -> ScalingTier:
        """Get the appropriate tier based on current equity"""
        for tier in SCALING_TIERS:
            if tier.min_equity <= self.equity < tier.max_equity:
                return tier
        return SCALING_TIERS[-1]  # Largest tier as fallback

    def should_trade_today(self, trade_date: str, tier: ScalingTier) -> bool:
        """
        Determine if we should trade today based on tier's trade frequency.

        - 5x/week: Trade Mon-Fri
        - 3x/week: Trade Mon/Wed/Fri
        - 2x/week: Trade Tue/Thu
        """
        dt = datetime.strptime(trade_date, '%Y-%m-%d')
        weekday = dt.weekday()  # 0=Mon, 4=Fri

        # Check if new week
        week_num = dt.isocalendar()[1]
        if self.current_week != week_num:
            self.current_week = week_num
            self.trades_this_week = 0

        # Check if we've hit weekly limit
        if self.trades_this_week >= tier.trades_per_week:
            return False

        # Check day of week based on frequency
        if tier.trades_per_week == 5:
            # Daily (Mon-Fri)
            return weekday < 5
        elif tier.trades_per_week == 3:
            # Mon/Wed/Fri
            return weekday in [0, 2, 4]
        elif tier.trades_per_week == 2:
            # Tue/Thu
            return weekday in [1, 3]
        else:
            return weekday < tier.trades_per_week

    def load_market_data(self):
        """Load SPX and VIX data"""
        if not YFINANCE_AVAILABLE:
            print("  yfinance required")
            return

        print("  Loading market data from Yahoo Finance...")

        start = datetime.strptime(self.start_date, '%Y-%m-%d') - timedelta(days=60)
        end = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=5)

        try:
            spx = yf.Ticker("^GSPC")
            hist = spx.history(start=start, end=end)

            for date_idx, row in hist.iterrows():
                date_str = date_idx.strftime('%Y-%m-%d')
                self.spx_ohlc[date_str] = {
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                }

            print(f"  Loaded {len(self.spx_ohlc)} days of SPX data")
        except Exception as e:
            print(f"  Failed to load SPX: {e}")

        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(start=start, end=end)

            for date_idx, row in hist.iterrows():
                date_str = date_idx.strftime('%Y-%m-%d')
                self.vix_data[date_str] = float(row['Close'])

            print(f"  Loaded {len(self.vix_data)} days of VIX data")
        except Exception as e:
            print(f"  Failed to load VIX: {e}")

    def get_trading_days(self) -> List[str]:
        """Get all trading days with options data"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get all days with any options data
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

    def get_options_for_date(self, trade_date: str, min_dte: int, max_dte: int) -> List[Dict]:
        """Get options within DTE range"""
        conn = self.get_connection()
        cursor = conn.cursor()

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
            ORDER BY dte, strike
        """, (self.ticker, trade_date, min_dte, max_dte))

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

    def find_iron_condor(self, options: List[Dict], open_price: float,
                         expected_move: float, dte: int) -> Optional[Dict]:
        """Find Iron Condor at specified DTE"""
        if not options:
            return None

        # Filter to specific DTE (or closest)
        dte_options = [o for o in options if o['dte'] == dte]
        if not dte_options:
            # Find closest DTE
            available_dtes = set(o['dte'] for o in options)
            if not available_dtes:
                return None
            closest_dte = min(available_dtes, key=lambda x: abs(x - dte))
            dte_options = [o for o in options if o['dte'] == closest_dte]
            dte = closest_dte

        underlying = dte_options[0]['underlying_price']

        # Adjust expected move for DTE (scale by sqrt of time)
        days_factor = math.sqrt(dte / 252) if dte > 0 else math.sqrt(1/252)
        vix = self.vix_data.get(options[0].get('trade_date', ''), 15)
        adjusted_move = open_price * (vix / 100) * days_factor

        # Target strikes
        put_target = open_price - (self.sd_multiplier * adjusted_move)
        put_target = round(put_target / 5) * 5

        call_target = open_price + (self.sd_multiplier * adjusted_move)
        call_target = round(call_target / 5) * 5

        # Find OTM options
        otm_puts = [o for o in dte_options if o['strike'] < underlying
                   and o.get('put_bid', 0) and o['put_bid'] > 0]
        otm_calls = [o for o in dte_options if o['strike'] > underlying
                    and o.get('call_bid', 0) and o['call_bid'] > 0]

        if not otm_puts or not otm_calls:
            return None

        # Short put
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - put_target))

        # Long put
        long_put_strike = short_put['strike'] - self.spread_width
        long_put_candidates = [o for o in dte_options
                              if abs(o['strike'] - long_put_strike) < 1
                              and o.get('put_ask', 0) and o['put_ask'] > 0]
        if not long_put_candidates:
            return None
        long_put = min(long_put_candidates, key=lambda x: abs(x['strike'] - long_put_strike))

        # Short call
        short_call = min(otm_calls, key=lambda x: abs(x['strike'] - call_target))

        # Long call
        long_call_strike = short_call['strike'] + self.spread_width
        long_call_candidates = [o for o in dte_options
                               if abs(o['strike'] - long_call_strike) < 1
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
            'dte': dte,
            'put_short_strike': short_put['strike'],
            'put_long_strike': long_put['strike'],
            'put_credit': put_credit,
            'call_short_strike': short_call['strike'],
            'call_long_strike': long_call['strike'],
            'call_credit': call_credit,
            'total_credit': put_credit + call_credit,
        }

    def execute_trade(self, trade_date: str, tier: ScalingTier) -> Optional[HybridTrade]:
        """Execute trade based on current tier"""
        ohlc = self.spx_ohlc.get(trade_date)
        if not ohlc:
            return None

        open_price = ohlc['open']
        vix = self.vix_data.get(trade_date, 15.0)

        # Get options for tier's DTE range
        options = self.get_options_for_date(trade_date, tier.min_dte, tier.max_dte)
        if not options:
            return None

        underlying = options[0]['underlying_price']

        # Expected move
        iv = vix / 100
        expected_move = open_price * iv * math.sqrt(1/252)

        # Target DTE (middle of range)
        target_dte = (tier.min_dte + tier.max_dte) // 2
        if tier.min_dte == 0:
            target_dte = 0  # Prefer 0DTE for first tier

        # Find iron condor
        ic = self.find_iron_condor(options, open_price, expected_move, target_dte)
        if not ic:
            return None

        # Apply slippage to credit
        total_credit = ic['total_credit'] - tier.slippage_per_spread
        if total_credit <= 0:
            return None

        # Max loss
        max_loss = self.spread_width - total_credit
        if max_loss <= 0:
            return None

        # Position sizing
        risk_budget = self.equity * (self.risk_per_trade_pct / 100)
        contracts_requested = int(risk_budget / (max_loss * 100))
        contracts_requested = max(1, contracts_requested)

        # Apply tier's contract limit
        contracts = min(contracts_requested, tier.max_contracts)

        # Calculate costs
        commission_total = tier.commission_per_leg * 4 * contracts  # 4 legs
        slippage_total = tier.slippage_per_spread * contracts * 100
        total_costs = commission_total + slippage_total

        self.total_commissions += commission_total
        self.total_slippage += slippage_total

        # Premium and risk
        total_premium = total_credit * 100 * contracts - commission_total
        total_risk = max_loss * 100 * contracts
        risk_pct = (total_risk / self.equity) * 100

        self.trade_counter += 1
        self.trades_this_week += 1

        trade = HybridTrade(
            trade_date=trade_date,
            trade_number=self.trade_counter,
            tier_name=tier.name,
            account_equity_at_entry=self.equity,
            dte_used=ic['dte'],
            vix=vix,
            open_price=open_price,
            underlying_price=underlying,
            expected_move=expected_move,
            put_short_strike=ic['put_short_strike'],
            put_long_strike=ic['put_long_strike'],
            put_credit=ic['put_credit'],
            call_short_strike=ic['call_short_strike'],
            call_long_strike=ic['call_long_strike'],
            call_credit=ic['call_credit'],
            total_credit=total_credit,
            spread_width=self.spread_width,
            max_loss=max_loss,
            commission_total=commission_total,
            slippage_total=slippage_total,
            total_costs=total_costs,
            contracts=contracts,
            contracts_requested=contracts_requested,
            total_premium=total_premium,
            total_risk=total_risk,
            risk_pct=risk_pct,
        )

        return trade

    def settle_trade(self, trade: HybridTrade):
        """Settle trade at expiration"""
        # For simplicity, we settle based on entry day's close
        # In reality, longer DTE would settle on expiration day
        ohlc = self.spx_ohlc.get(trade.trade_date)
        if not ohlc:
            return

        # For longer DTE, simulate settlement based on expected probability
        # This is a simplification - real backtest would track to expiration
        if trade.dte_used > 1:
            # Simulate: use close price adjusted for time decay
            # Longer DTE = more time for price to move, but also more theta collected
            settlement = ohlc['close']
        else:
            settlement = ohlc['close']

        trade.settlement_price = settlement

        # Put spread P&L
        if settlement >= trade.put_short_strike:
            put_pnl = trade.put_credit
            trade.put_breached = False
        elif settlement > trade.put_long_strike:
            intrinsic = trade.put_short_strike - settlement
            put_pnl = trade.put_credit - intrinsic
            trade.put_breached = True
        else:
            put_pnl = trade.put_credit - self.spread_width
            trade.put_breached = True

        # Call spread P&L
        if settlement <= trade.call_short_strike:
            call_pnl = trade.call_credit
            trade.call_breached = False
        elif settlement < trade.call_long_strike:
            intrinsic = settlement - trade.call_short_strike
            call_pnl = trade.call_credit - intrinsic
            trade.call_breached = True
        else:
            call_pnl = trade.call_credit - self.spread_width
            trade.call_breached = True

        # Gross and net P&L
        gross_pnl = (put_pnl + call_pnl) * 100 * trade.contracts
        trade.gross_pnl = gross_pnl
        trade.net_pnl = gross_pnl - trade.total_costs
        trade.return_pct = (trade.net_pnl / trade.total_risk * 100) if trade.total_risk > 0 else 0

        # Outcome
        if not trade.put_breached and not trade.call_breached:
            trade.outcome = "MAX_PROFIT"
        elif trade.put_breached and trade.call_breached:
            trade.outcome = "DOUBLE_BREACH"
        elif trade.put_breached:
            trade.outcome = "PUT_BREACHED"
        else:
            trade.outcome = "CALL_BREACHED"

        # Update equity and tier stats
        self.equity += trade.net_pnl
        self.high_water_mark = max(self.high_water_mark, self.equity)

        self.tier_stats[trade.tier_name]['trades'] += 1
        self.tier_stats[trade.tier_name]['pnl'] += trade.net_pnl

    def run(self) -> Dict:
        """Run the hybrid scaling backtest"""
        print("\n" + "=" * 80)
        print("HYBRID SCALING IRON CONDOR STRATEGY")
        print("=" * 80)
        print(f"Period:             {self.start_date} to {self.end_date}")
        print(f"Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"Risk Per Trade:     {self.risk_per_trade_pct}%")
        print(f"Spread Width:       ${self.spread_width}")
        print("-" * 80)
        print("SCALING TIERS:")
        for tier in SCALING_TIERS:
            max_eq = f"${tier.max_equity:,.0f}" if tier.max_equity < float('inf') else "Unlimited"
            print(f"  {tier.name:20} ${tier.min_equity:>12,.0f} - {max_eq:>12}")
            print(f"    DTE: {tier.min_dte}-{tier.max_dte}, Max Contracts: {tier.max_contracts}, Trades/Week: {tier.trades_per_week}")
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

            # Check if we should trade today
            if not self.should_trade_today(trade_date, tier):
                continue

            # Execute trade
            trade = self.execute_trade(trade_date, tier)

            if trade:
                self.settle_trade(trade)
                self.all_trades.append(trade)
                self.tier_stats[tier.name]['days'] += 1

        print(f"\r  [{'█' * 40}] 100.0% Complete!{' ' * 40}")

        # Calculate results
        results = self.calculate_results(tier_transitions)
        self.print_results(results)
        self.export_trades()

        return results

    def calculate_results(self, tier_transitions: List[Dict]) -> Dict:
        """Calculate comprehensive results"""
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
        equity = self.initial_capital
        for t in self.all_trades:
            equity += t.net_pnl
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        # Outcomes
        outcomes = {}
        for t in self.all_trades:
            outcomes[t.outcome] = outcomes.get(t.outcome, 0) + 1

        return {
            'summary': {
                'initial_capital': self.initial_capital,
                'final_equity': self.equity,
                'total_pnl': total_pnl,
                'total_return_pct': total_return,
                'avg_monthly_return_pct': avg_monthly,
                'max_drawdown_pct': max_dd,
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
            'tier_stats': self.tier_stats,
            'tier_transitions': tier_transitions,
            'outcomes': outcomes,
            'monthly_returns': monthly_pct,
        }

    def print_results(self, results: Dict):
        """Print results"""
        if not results:
            return

        s = results['summary']
        t = results['trades']
        c = results['costs']
        ts = results['tier_stats']
        tt = results['tier_transitions']
        o = results['outcomes']

        print("\n" + "=" * 80)
        print("HYBRID SCALING RESULTS")
        print("=" * 80)

        print(f"\nCAPITAL")
        print(f"  Initial:              ${s['initial_capital']:>15,.2f}")
        print(f"  Final:                ${s['final_equity']:>15,.2f}")
        print(f"  Total P&L:            ${s['total_pnl']:>15,.2f}")
        print(f"  Total Return:         {s['total_return_pct']:>15.2f}%")

        print(f"\nPERFORMANCE")
        print(f"  Avg Monthly Return:   {s['avg_monthly_return_pct']:>15.2f}%")
        print(f"  Max Drawdown:         {s['max_drawdown_pct']:>15.2f}%")

        print(f"\nTRADE STATISTICS")
        print(f"  Total Trades:         {t['total']:>15}")
        print(f"  Win Rate:             {t['win_rate']:>15.1f}%")
        pf = f"{t['profit_factor']:.2f}" if t['profit_factor'] != float('inf') else "∞"
        print(f"  Profit Factor:        {pf:>15}")

        print(f"\nTRANSACTION COSTS")
        print(f"  Total Commissions:    ${c['total_commissions']:>15,.2f}")
        print(f"  Total Slippage:       ${c['total_slippage']:>15,.2f}")
        print(f"  Total Costs:          ${c['total_costs']:>15,.2f}")

        print(f"\nTIER BREAKDOWN")
        for tier_name, stats in ts.items():
            if stats['trades'] > 0:
                avg_pnl = stats['pnl'] / stats['trades']
                print(f"  {tier_name}:")
                print(f"    Trades: {stats['trades']:>6} | P&L: ${stats['pnl']:>14,.2f} | Avg: ${avg_pnl:>10,.2f}")

        if tt:
            print(f"\nTIER TRANSITIONS")
            for trans in tt[:10]:  # Show first 10
                print(f"  {trans['date']}: {trans['from_tier']} → {trans['to_tier']} (Equity: ${trans['equity']:,.0f})")
            if len(tt) > 10:
                print(f"  ... and {len(tt) - 10} more transitions")

        print(f"\nOUTCOME BREAKDOWN")
        for outcome, count in sorted(o.items(), key=lambda x: -x[1]):
            pct = count / t['total'] * 100
            print(f"  {outcome:20} {count:>5} ({pct:5.1f}%)")

        print(f"\nMONTHLY RETURNS")
        monthly = results['monthly_returns']
        for month, pct in sorted(monthly.items()):
            bar_len = min(30, int(abs(pct) * 2))
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
            filename = f"hybrid_scaling_trades_{self.start_date}_{self.end_date}.csv"

        filepath = Path(__file__).parent / filename

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self.all_trades[0]).keys())
            writer.writeheader()
            for trade in self.all_trades:
                writer.writerow(asdict(trade))

        print(f"\nExported {len(self.all_trades)} trades to {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Hybrid Scaling Iron Condor Strategy')

    parser.add_argument('--start', default='2021-01-01')
    parser.add_argument('--end', default='2025-12-01')
    parser.add_argument('--capital', type=float, default=1_000_000)
    parser.add_argument('--width', type=float, default=10.0)
    parser.add_argument('--sd', type=float, default=1.0)
    parser.add_argument('--risk', type=float, default=5.0, help='Risk per trade percent (default: 5)')
    parser.add_argument('--ticker', default='SPX')

    args = parser.parse_args()

    backtester = HybridScalingBacktester(
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
