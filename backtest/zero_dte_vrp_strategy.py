#!/usr/bin/env python3
"""
0DTE Volatility Risk Premium (VRP) Strategy

THE EDGE: Implied Volatility > Realized Volatility ~85% of the time
This is the scientific basis for premium-selling strategies used by hedge funds.

STRATEGY DESIGN:
================
1. ONLY TRADE WHEN EDGE EXISTS: VIX > 18 (IV overpriced relative to RV)
2. WIDE STRIKES: 1.0-1.5 SD for 80%+ win rate
3. CONSISTENT SIZING: 3% risk per trade (Kelly-fractional)
4. NO STOP LOSS: Spread defines max risk - let theta work
5. COMPOUND DAILY: Reinvest gains immediately
6. SKIP EXTREMES: VIX > 40 = gamma risk too high

THE MATH:
=========
- 1.0 SD puts have ~84% probability of expiring OTM
- Average credit: ~$2.50 on $10 spread (25% of width)
- Win: +$2.50, Loss: -$7.50
- EV per trade = 0.84 × $2.50 - 0.16 × $7.50 = $2.10 - $1.20 = +$0.90
- Edge = $0.90 / $7.50 = 12% per trade
- At 3% risk × 20 trades/month × 12% edge = 7.2% monthly expected

REALISTIC TARGET: 5-8% monthly (after slippage, skipped days)
This compounds to 80-150% annually - still exceptional.

Usage:
    python backtest/zero_dte_vrp_strategy.py --start 2021-01-01 --end 2025-12-01
"""

import os
import sys
import uuid
import argparse
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal

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
class VRPTrade:
    """Single VRP trade"""
    trade_date: str
    trade_number: int
    strategy: str  # "BULL_PUT" or "IRON_CONDOR"

    # Market context
    vix: float
    iv_rv_ratio: float  # IV / RV - edge indicator

    # Position
    underlying_price: float
    open_price: float

    # Put spread (always present)
    put_short_strike: float
    put_long_strike: float
    put_credit: float
    put_delta: float

    # Call spread (for iron condor only)
    call_short_strike: float = 0
    call_long_strike: float = 0
    call_credit: float = 0
    call_delta: float = 0

    # Combined
    total_credit: float = 0
    spread_width: float = 10.0
    max_loss: float = 0

    # Sizing
    contracts: int = 0
    total_premium: float = 0
    total_risk: float = 0
    risk_pct_of_equity: float = 0

    # Settlement
    settlement_price: float = 0
    daily_high: float = 0
    daily_low: float = 0

    # P&L
    put_pnl: float = 0
    call_pnl: float = 0
    total_pnl: float = 0
    return_on_risk: float = 0

    # Outcome
    outcome: str = ""
    put_breached: bool = False
    call_breached: bool = False


class VRPBacktester:
    """
    Volatility Risk Premium backtester.

    Core principle: Only trade when IV > RV (edge exists).
    """

    def __init__(
        self,
        start_date: str = "2021-01-01",
        end_date: str = None,
        initial_capital: float = 1_000_000,
        spread_width: float = 10.0,
        sd_multiplier: float = 1.0,  # 1 SD = ~84% win rate
        risk_per_trade_pct: float = 3.0,  # Conservative Kelly
        min_vix: float = 18.0,  # Only trade when VIX > this (IV elevated)
        max_vix: float = 40.0,  # Skip extreme fear (gamma too high)
        use_iron_condor: bool = False,  # Single leg or both
        ticker: str = "SPX",
    ):
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        self.initial_capital = initial_capital
        self.spread_width = spread_width
        self.sd_multiplier = sd_multiplier
        self.risk_per_trade_pct = risk_per_trade_pct
        self.min_vix = min_vix
        self.max_vix = max_vix
        self.use_iron_condor = use_iron_condor
        self.ticker = ticker

        # State
        self.equity = initial_capital
        self.high_water_mark = initial_capital

        # Tracking
        self.all_trades: List[VRPTrade] = []
        self.trade_counter = 0

        # Stats
        self.days_traded = 0
        self.days_skipped_low_vix = 0
        self.days_skipped_high_vix = 0
        self.days_skipped_no_data = 0

        # Cache
        self.spx_ohlc: Dict[str, Dict] = {}
        self.vix_data: Dict[str, float] = {}
        self.realized_vol: Dict[str, float] = {}

    def get_connection(self):
        from database_adapter import get_connection
        return get_connection()

    def load_market_data(self):
        """Load SPX and VIX data from Yahoo Finance"""
        if not YFINANCE_AVAILABLE:
            print("  yfinance required for VRP strategy")
            return

        print("  Loading market data...")

        start = datetime.strptime(self.start_date, '%Y-%m-%d') - timedelta(days=60)
        end = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=5)

        # SPX data
        try:
            spx = yf.Ticker("^GSPC")
            hist = spx.history(start=start, end=end)

            prices = []
            for date_idx, row in hist.iterrows():
                date_str = date_idx.strftime('%Y-%m-%d')
                self.spx_ohlc[date_str] = {
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                }
                prices.append((date_str, float(row['Close'])))

            # Calculate 20-day realized volatility
            for i in range(20, len(prices)):
                recent_prices = [p[1] for p in prices[i-20:i]]
                returns = [(recent_prices[j] / recent_prices[j-1]) - 1
                          for j in range(1, len(recent_prices))]
                rv = (sum(r**2 for r in returns) / len(returns)) ** 0.5
                rv_annual = rv * math.sqrt(252) * 100  # Annualized, in %
                self.realized_vol[prices[i][0]] = rv_annual

            print(f"  Loaded {len(self.spx_ohlc)} days of SPX data")
        except Exception as e:
            print(f"  Failed to load SPX: {e}")

        # VIX data
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(start=start, end=end)

            for date_idx, row in hist.iterrows():
                date_str = date_idx.strftime('%Y-%m-%d')
                self.vix_data[date_str] = float(row['Close'])

            print(f"  Loaded {len(self.vix_data)} days of VIX data")
        except Exception as e:
            print(f"  Failed to load VIX: {e}")

    def get_edge_metrics(self, trade_date: str) -> Tuple[float, float, float]:
        """
        Calculate edge metrics for a given date.

        Returns: (vix, realized_vol, iv_rv_ratio)

        When IV/RV > 1.0, implied volatility is "overpriced" relative to
        what the market actually delivered. This is the VRP edge.
        """
        vix = self.vix_data.get(trade_date, 0)
        rv = self.realized_vol.get(trade_date, 0)

        if rv > 0:
            iv_rv_ratio = vix / rv
        else:
            iv_rv_ratio = 1.0

        return vix, rv, iv_rv_ratio

    def should_trade(self, trade_date: str) -> Tuple[bool, str, float, float]:
        """
        Determine if we should trade based on VRP edge.

        Returns: (should_trade, reason, vix, iv_rv_ratio)
        """
        vix, rv, iv_rv_ratio = self.get_edge_metrics(trade_date)

        if vix < self.min_vix:
            return False, "VIX_TOO_LOW", vix, iv_rv_ratio

        if vix > self.max_vix:
            return False, "VIX_TOO_HIGH", vix, iv_rv_ratio

        # Edge check: only trade when IV > RV (premium is "overpriced")
        if iv_rv_ratio < 0.9:  # Some buffer
            return False, "NO_VRP_EDGE", vix, iv_rv_ratio

        return True, "TRADE", vix, iv_rv_ratio

    def get_trading_days(self) -> List[str]:
        """Get trading days with 0DTE options"""
        conn = self.get_connection()
        cursor = conn.cursor()

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
        """Get 0DTE options for a date"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                strike, underlying_price,
                put_bid, put_ask, call_bid, call_ask,
                delta, put_iv, call_iv
            FROM orat_options_eod
            WHERE ticker = %s AND trade_date = %s AND dte <= 1
            ORDER BY strike DESC
        """, (self.ticker, trade_date))

        columns = ['strike', 'underlying_price', 'put_bid', 'put_ask',
                   'call_bid', 'call_ask', 'delta', 'put_iv', 'call_iv']

        options = []
        for row in cursor.fetchall():
            opt = dict(zip(columns, row))
            for key in opt:
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

        # OTM puts
        otm_puts = [o for o in options if o['strike'] < underlying
                   and o.get('put_bid', 0) and o['put_bid'] > 0]

        if not otm_puts:
            return None

        # Short put closest to target
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - target_strike))

        # Long put at width below
        long_strike = short_put['strike'] - self.spread_width
        long_candidates = [o for o in options
                          if abs(o['strike'] - long_strike) < 1
                          and o.get('put_ask', 0) and o['put_ask'] > 0]

        if not long_candidates:
            return None

        long_put = min(long_candidates, key=lambda x: abs(x['strike'] - long_strike))

        if long_put['strike'] >= short_put['strike']:
            return None

        return (short_put, long_put)

    def find_call_spread(self, options: List[Dict], target_strike: float) -> Optional[Tuple[Dict, Dict]]:
        """Find bear call spread at target strike"""
        if not options:
            return None

        underlying = options[0]['underlying_price']

        # OTM calls
        otm_calls = [o for o in options if o['strike'] > underlying
                    and o.get('call_bid', 0) and o['call_bid'] > 0]

        if not otm_calls:
            return None

        # Short call closest to target
        short_call = min(otm_calls, key=lambda x: abs(x['strike'] - target_strike))

        # Long call at width above
        long_strike = short_call['strike'] + self.spread_width
        long_candidates = [o for o in options
                          if abs(o['strike'] - long_strike) < 1
                          and o.get('call_ask', 0) and o['call_ask'] > 0]

        if not long_candidates:
            return None

        long_call = min(long_candidates, key=lambda x: abs(x['strike'] - long_strike))

        if long_call['strike'] <= short_call['strike']:
            return None

        return (short_call, long_call)

    def execute_trade(self, trade_date: str, options: List[Dict],
                      vix: float, iv_rv_ratio: float) -> Optional[VRPTrade]:
        """Execute VRP trade"""
        if not options:
            return None

        # Get prices
        ohlc = self.spx_ohlc.get(trade_date)
        if not ohlc:
            return None

        open_price = ohlc['open']
        underlying = options[0]['underlying_price']

        # Calculate expected move
        avg_iv = sum(o.get('put_iv', 0) or 0 for o in options[:20]) / 20
        if avg_iv <= 0:
            avg_iv = vix / 100

        expected_move = open_price * avg_iv * math.sqrt(1/252)

        # Target strikes at SD from open
        put_target = open_price - (self.sd_multiplier * expected_move)
        put_target = round(put_target / 5) * 5

        # Find put spread
        put_spread = self.find_put_spread(options, put_target)
        if not put_spread:
            return None

        short_put, long_put = put_spread
        put_credit = (short_put.get('put_bid', 0) or 0) - (long_put.get('put_ask', 0) or 0)

        if put_credit <= 0:
            return None

        # Iron condor if enabled
        call_short_strike = 0
        call_long_strike = 0
        call_credit = 0
        call_delta = 0
        strategy = "BULL_PUT"

        if self.use_iron_condor:
            call_target = open_price + (self.sd_multiplier * expected_move)
            call_target = round(call_target / 5) * 5

            call_spread = self.find_call_spread(options, call_target)
            if call_spread:
                short_call, long_call = call_spread
                call_credit = (short_call.get('call_bid', 0) or 0) - (long_call.get('call_ask', 0) or 0)

                if call_credit > 0:
                    call_short_strike = short_call['strike']
                    call_long_strike = long_call['strike']
                    call_delta = short_call.get('delta', 0) or 0
                    strategy = "IRON_CONDOR"

        total_credit = put_credit + call_credit

        # For iron condor, only one side can lose
        if strategy == "IRON_CONDOR":
            max_loss = self.spread_width - total_credit
        else:
            max_loss = self.spread_width - put_credit

        if max_loss <= 0:
            return None

        # Position sizing - risk X% of equity
        risk_budget = self.equity * (self.risk_per_trade_pct / 100)
        contracts = int(risk_budget / (max_loss * 100))
        contracts = max(1, min(contracts, 500))

        total_premium = total_credit * 100 * contracts
        total_risk = max_loss * 100 * contracts
        risk_pct = (total_risk / self.equity) * 100

        self.trade_counter += 1

        trade = VRPTrade(
            trade_date=trade_date,
            trade_number=self.trade_counter,
            strategy=strategy,
            vix=vix,
            iv_rv_ratio=iv_rv_ratio,
            underlying_price=underlying,
            open_price=open_price,
            put_short_strike=short_put['strike'],
            put_long_strike=long_put['strike'],
            put_credit=put_credit,
            put_delta=short_put.get('delta', 0) or 0,
            call_short_strike=call_short_strike,
            call_long_strike=call_long_strike,
            call_credit=call_credit,
            call_delta=call_delta,
            total_credit=total_credit,
            spread_width=self.spread_width,
            max_loss=max_loss,
            contracts=contracts,
            total_premium=total_premium,
            total_risk=total_risk,
            risk_pct_of_equity=risk_pct,
        )

        return trade

    def settle_trade(self, trade: VRPTrade):
        """Settle trade at expiration - no stop loss, let theta work"""
        ohlc = self.spx_ohlc.get(trade.trade_date)
        if not ohlc:
            return

        settlement = ohlc['close']
        trade.settlement_price = settlement
        trade.daily_high = ohlc['high']
        trade.daily_low = ohlc['low']

        # Put spread P&L
        if settlement >= trade.put_short_strike:
            # Both puts OTM - full profit
            trade.put_pnl = trade.put_credit
            trade.put_breached = False
        elif settlement > trade.put_long_strike:
            # Short put ITM, long put OTM - partial loss
            intrinsic = trade.put_short_strike - settlement
            trade.put_pnl = trade.put_credit - intrinsic
            trade.put_breached = True
        else:
            # Both ITM - max loss on put side
            trade.put_pnl = trade.put_credit - self.spread_width
            trade.put_breached = True

        # Call spread P&L (if iron condor)
        if trade.strategy == "IRON_CONDOR" and trade.call_credit > 0:
            if settlement <= trade.call_short_strike:
                # Both calls OTM - full profit
                trade.call_pnl = trade.call_credit
                trade.call_breached = False
            elif settlement < trade.call_long_strike:
                # Short call ITM, long call OTM - partial loss
                intrinsic = settlement - trade.call_short_strike
                trade.call_pnl = trade.call_credit - intrinsic
                trade.call_breached = True
            else:
                # Both ITM - max loss on call side
                trade.call_pnl = trade.call_credit - self.spread_width
                trade.call_breached = True

        # Total P&L
        total_pnl_per_contract = trade.put_pnl + trade.call_pnl
        trade.total_pnl = total_pnl_per_contract * 100 * trade.contracts
        trade.return_on_risk = (trade.total_pnl / trade.total_risk * 100) if trade.total_risk > 0 else 0

        # Outcome
        if not trade.put_breached and not trade.call_breached:
            trade.outcome = "MAX_PROFIT"
        elif trade.put_breached and trade.call_breached:
            trade.outcome = "DOUBLE_BREACH"  # Very rare
        elif trade.put_breached:
            trade.outcome = "PUT_BREACHED"
        else:
            trade.outcome = "CALL_BREACHED"

        # Update equity
        self.equity += trade.total_pnl
        self.high_water_mark = max(self.high_water_mark, self.equity)

    def run(self) -> Dict:
        """Run the backtest"""
        print("\n" + "=" * 80)
        print("VOLATILITY RISK PREMIUM (VRP) STRATEGY")
        print("=" * 80)
        print(f"Period:             {self.start_date} to {self.end_date}")
        print(f"Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"Strategy:           {'Iron Condor' if self.use_iron_condor else 'Bull Put Spread'}")
        print(f"Strike Distance:    {self.sd_multiplier} SD from open")
        print(f"Risk Per Trade:     {self.risk_per_trade_pct}%")
        print(f"VIX Range:          {self.min_vix} - {self.max_vix}")
        print(f"Edge:               Trade only when IV > RV (VRP exists)")
        print("=" * 80)

        # Load data
        print("\nLoading market data...")
        self.load_market_data()

        if not self.spx_ohlc or not self.vix_data:
            print("Failed to load market data")
            return {}

        # Get trading days
        print("Fetching trading days...")
        trading_days = self.get_trading_days()

        if not trading_days:
            print(f"No 0DTE data found for {self.ticker}")
            return {}

        print(f"Found {len(trading_days)} potential trading days")

        # Process each day
        total_days = len(trading_days)
        for i, trade_date in enumerate(trading_days):

            if i % 20 == 0:
                pct = (i / total_days) * 100
                print(f"\r  Processing: {pct:.1f}% | Trades: {len(self.all_trades)} | Equity: ${self.equity:,.0f}", end="", flush=True)

            # Check if we should trade (VRP edge exists)
            should_trade, reason, vix, iv_rv_ratio = self.should_trade(trade_date)

            if not should_trade:
                if reason == "VIX_TOO_LOW":
                    self.days_skipped_low_vix += 1
                elif reason == "VIX_TOO_HIGH":
                    self.days_skipped_high_vix += 1
                continue

            # Get options
            options = self.get_options_for_date(trade_date)
            if not options:
                self.days_skipped_no_data += 1
                continue

            # Execute trade
            trade = self.execute_trade(trade_date, options, vix, iv_rv_ratio)

            if trade:
                self.settle_trade(trade)
                self.all_trades.append(trade)
                self.days_traded += 1

        print(f"\r  Processing: 100% Complete!{' ' * 40}")

        # Calculate results
        results = self.calculate_results()
        self.print_results(results)

        return results

    def calculate_results(self) -> Dict:
        """Calculate comprehensive results"""
        if not self.all_trades:
            return {}

        total_pnl = sum(t.total_pnl for t in self.all_trades)
        total_return = (self.equity - self.initial_capital) / self.initial_capital * 100

        wins = [t for t in self.all_trades if t.total_pnl > 0]
        losses = [t for t in self.all_trades if t.total_pnl <= 0]

        win_rate = len(wins) / len(self.all_trades) * 100

        gross_profit = sum(t.total_pnl for t in wins)
        gross_loss = sum(t.total_pnl for t in losses)
        profit_factor = abs(gross_profit / gross_loss) if gross_loss else float('inf')

        # Monthly returns
        monthly = {}
        for t in self.all_trades:
            month = t.trade_date[:7]
            monthly[month] = monthly.get(month, 0) + t.total_pnl

        monthly_pct = {m: (pnl / self.initial_capital) * 100 for m, pnl in monthly.items()}
        avg_monthly = sum(monthly_pct.values()) / len(monthly_pct) if monthly_pct else 0

        # Drawdown
        peak = self.initial_capital
        max_dd = 0
        equity = self.initial_capital
        for t in self.all_trades:
            equity += t.total_pnl
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        # VIX analysis
        avg_vix = sum(t.vix for t in self.all_trades) / len(self.all_trades)
        avg_iv_rv = sum(t.iv_rv_ratio for t in self.all_trades) / len(self.all_trades)

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
            'vrp_metrics': {
                'avg_vix_traded': avg_vix,
                'avg_iv_rv_ratio': avg_iv_rv,
                'days_skipped_low_vix': self.days_skipped_low_vix,
                'days_skipped_high_vix': self.days_skipped_high_vix,
            },
            'monthly_returns': monthly_pct,
            'days_traded': self.days_traded,
        }

    def print_results(self, results: Dict):
        """Print results"""
        if not results:
            return

        s = results['summary']
        t = results['trades']
        v = results['vrp_metrics']

        print("\n" + "=" * 80)
        print("VRP STRATEGY RESULTS")
        print("=" * 80)

        print(f"\nCAPITAL")
        print(f"  Initial:              ${s['initial_capital']:>15,.2f}")
        print(f"  Final:                ${s['final_equity']:>15,.2f}")
        print(f"  Total P&L:            ${s['total_pnl']:>15,.2f}")
        print(f"  Total Return:         {s['total_return_pct']:>15.2f}%")

        print(f"\nMONTHLY PERFORMANCE")
        print(f"  Avg Monthly Return:   {s['avg_monthly_return_pct']:>15.2f}%")
        print(f"  Max Drawdown:         {s['max_drawdown_pct']:>15.2f}%")

        print(f"\nTRADE STATISTICS")
        print(f"  Total Trades:         {t['total']:>15}")
        print(f"  Win Rate:             {t['win_rate']:>15.1f}%")
        print(f"  Profit Factor:        {t['profit_factor']:>15.2f}")
        print(f"  Avg Win:              ${t['avg_win']:>14,.2f}")
        print(f"  Avg Loss:             ${t['avg_loss']:>14,.2f}")

        print(f"\nVRP EDGE METRICS")
        print(f"  Avg VIX When Traded:  {v['avg_vix_traded']:>15.1f}")
        print(f"  Avg IV/RV Ratio:      {v['avg_iv_rv_ratio']:>15.2f}")
        print(f"  Days Skipped (Low VIX):  {v['days_skipped_low_vix']}")
        print(f"  Days Skipped (High VIX): {v['days_skipped_high_vix']}")

        print(f"\nMONTHLY BREAKDOWN:")
        for month, pct in sorted(results['monthly_returns'].items()):
            bar = "+" * min(20, int(pct)) if pct > 0 else "-" * min(20, int(-pct))
            print(f"  {month}: {pct:+7.2f}% {bar}")

        print("=" * 80)

    def export_trades(self, filename: str = None):
        """Export to CSV"""
        if not self.all_trades:
            return

        import csv

        if not filename:
            filename = f"vrp_trades_{self.start_date}_{self.end_date}.csv"

        filepath = Path(__file__).parent / filename

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self.all_trades[0]).keys())
            writer.writeheader()
            for trade in self.all_trades:
                writer.writerow(asdict(trade))

        print(f"\nExported {len(self.all_trades)} trades to {filepath}")


def main():
    parser = argparse.ArgumentParser(description='VRP 0DTE Strategy')

    parser.add_argument('--start', default='2021-01-01')
    parser.add_argument('--end', default='2025-12-01')
    parser.add_argument('--capital', type=float, default=1_000_000)
    parser.add_argument('--width', type=float, default=10.0)
    parser.add_argument('--sd', type=float, default=1.0)
    parser.add_argument('--risk', type=float, default=3.0)
    parser.add_argument('--minvix', type=float, default=18.0)
    parser.add_argument('--maxvix', type=float, default=40.0)
    parser.add_argument('--ticker', default='SPX')
    parser.add_argument('--ic', action='store_true', help='Use Iron Condor')
    parser.add_argument('--export', action='store_true')

    args = parser.parse_args()

    backtester = VRPBacktester(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        spread_width=args.width,
        sd_multiplier=args.sd,
        risk_per_trade_pct=args.risk,
        min_vix=args.minvix,
        max_vix=args.maxvix,
        ticker=args.ticker,
        use_iron_condor=args.ic,
    )

    results = backtester.run()

    if args.export:
        backtester.export_trades()

    return results


if __name__ == "__main__":
    main()
