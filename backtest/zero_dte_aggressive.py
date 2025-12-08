#!/usr/bin/env python3
"""
0DTE AGGRESSIVE Iron Condor Strategy - TARGET: 10% MONTHLY RETURNS

THE MATH FOR 10% MONTHLY:
=========================
- 20 trading days/month
- Need ~0.5% per day to compound to 10% monthly
- Iron Condor at 1 SD collects ~$3-5 on $10 wide spread
- Win rate at 1 SD: ~68% for BOTH sides to be profitable
- With 10% risk per trade and compounding, this achieves the target

AGGRESSIVE PARAMETERS:
=====================
- Trade EVERY weekday (Mon-Fri)
- Iron Condor: Bull Put + Bear Call simultaneously
- 10% risk per trade (aggressive Kelly)
- 1 SD strikes (balanced risk/reward)
- NO stop loss - let options expire (defined risk)
- Compound daily - reinvest gains immediately

Usage:
    python backtest/zero_dte_aggressive.py --start 2021-01-01 --end 2025-12-01
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
class IronCondorTrade:
    """Single Iron Condor trade"""
    trade_date: str
    trade_number: int

    # Market context
    vix: float
    open_price: float
    underlying_price: float
    expected_move: float

    # Put spread (bull put)
    put_short_strike: float
    put_long_strike: float
    put_credit: float

    # Call spread (bear call)
    call_short_strike: float
    call_long_strike: float
    call_credit: float

    # Combined
    total_credit: float
    spread_width: float
    max_loss: float  # Only one side can lose

    # Sizing
    contracts: int
    total_premium: float
    total_risk: float
    risk_pct: float

    # Settlement
    settlement_price: float = 0
    daily_high: float = 0
    daily_low: float = 0

    # P&L
    put_pnl: float = 0
    call_pnl: float = 0
    total_pnl: float = 0
    return_pct: float = 0

    # Outcome
    outcome: str = ""
    put_breached: bool = False
    call_breached: bool = False


class AggressiveBacktester:
    """
    Aggressive Iron Condor backtester targeting 10% monthly returns.

    Key differences from conservative strategy:
    1. Trade every day (Mon-Fri)
    2. Higher risk per trade (10%)
    3. Iron Condor for double premium
    4. No stop loss - let theta work
    5. Compound daily
    """

    def __init__(
        self,
        start_date: str = "2021-01-01",
        end_date: str = None,
        initial_capital: float = 1_000_000,
        spread_width: float = 10.0,
        sd_multiplier: float = 1.0,  # 1 SD = good balance
        risk_per_trade_pct: float = 10.0,  # AGGRESSIVE: 10% per trade
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
        self.all_trades: List[IronCondorTrade] = []
        self.trade_counter = 0

        # Stats
        self.days_traded = 0
        self.days_skipped_no_data = 0

        # Cache
        self.spx_ohlc: Dict[str, Dict] = {}
        self.vix_data: Dict[str, float] = {}

    def get_connection(self):
        from database_adapter import get_connection
        return get_connection()

    def load_market_data(self):
        """Load SPX and VIX data from Yahoo Finance"""
        if not YFINANCE_AVAILABLE:
            print("  yfinance required")
            return

        print("  Loading market data from Yahoo Finance...")

        start = datetime.strptime(self.start_date, '%Y-%m-%d') - timedelta(days=10)
        end = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=5)

        # SPX data
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

    def get_trading_days(self) -> List[str]:
        """Get ALL trading days (Mon-Fri) with 0DTE options"""
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
            ORDER BY strike
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

    def find_iron_condor(self, options: List[Dict], open_price: float,
                         expected_move: float) -> Optional[Dict]:
        """
        Find Iron Condor strikes at 1 SD from open.

        Iron Condor = Bull Put Spread + Bear Call Spread
        - Put: 1 SD BELOW open
        - Call: 1 SD ABOVE open
        """
        if not options:
            return None

        underlying = options[0]['underlying_price']

        # Target strikes
        put_target = open_price - (self.sd_multiplier * expected_move)
        put_target = round(put_target / 5) * 5

        call_target = open_price + (self.sd_multiplier * expected_move)
        call_target = round(call_target / 5) * 5

        # Find OTM puts (below underlying)
        otm_puts = [o for o in options if o['strike'] < underlying
                   and o.get('put_bid', 0) and o['put_bid'] > 0]

        # Find OTM calls (above underlying)
        otm_calls = [o for o in options if o['strike'] > underlying
                    and o.get('call_bid', 0) and o['call_bid'] > 0]

        if not otm_puts or not otm_calls:
            return None

        # Short put at target
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - put_target))

        # Long put below
        long_put_strike = short_put['strike'] - self.spread_width
        long_put_candidates = [o for o in options
                              if abs(o['strike'] - long_put_strike) < 1
                              and o.get('put_ask', 0) and o['put_ask'] > 0]
        if not long_put_candidates:
            return None
        long_put = min(long_put_candidates, key=lambda x: abs(x['strike'] - long_put_strike))

        # Short call at target
        short_call = min(otm_calls, key=lambda x: abs(x['strike'] - call_target))

        # Long call above
        long_call_strike = short_call['strike'] + self.spread_width
        long_call_candidates = [o for o in options
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
            'put_short_strike': short_put['strike'],
            'put_long_strike': long_put['strike'],
            'put_credit': put_credit,
            'call_short_strike': short_call['strike'],
            'call_long_strike': long_call['strike'],
            'call_credit': call_credit,
            'total_credit': put_credit + call_credit,
        }

    def execute_trade(self, trade_date: str, options: List[Dict]) -> Optional[IronCondorTrade]:
        """Execute Iron Condor trade"""
        if not options:
            return None

        # Get prices
        ohlc = self.spx_ohlc.get(trade_date)
        if not ohlc:
            return None

        open_price = ohlc['open']
        underlying = options[0]['underlying_price']
        vix = self.vix_data.get(trade_date, 15.0)

        # Calculate expected move using VIX
        iv = vix / 100
        expected_move = open_price * iv * math.sqrt(1/252)

        # Find iron condor
        ic = self.find_iron_condor(options, open_price, expected_move)
        if not ic:
            return None

        total_credit = ic['total_credit']

        # For Iron Condor, max loss is width - credit (only one side loses)
        max_loss = self.spread_width - total_credit

        if max_loss <= 0:
            return None

        # AGGRESSIVE position sizing - 10% of equity at risk
        risk_budget = self.equity * (self.risk_per_trade_pct / 100)
        contracts = int(risk_budget / (max_loss * 100))
        contracts = max(1, min(contracts, 1000))  # Cap at 1000 contracts

        total_premium = total_credit * 100 * contracts
        total_risk = max_loss * 100 * contracts
        risk_pct = (total_risk / self.equity) * 100

        self.trade_counter += 1

        trade = IronCondorTrade(
            trade_date=trade_date,
            trade_number=self.trade_counter,
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
            contracts=contracts,
            total_premium=total_premium,
            total_risk=total_risk,
            risk_pct=risk_pct,
        )

        return trade

    def settle_trade(self, trade: IronCondorTrade):
        """Settle Iron Condor at expiration - NO stop loss"""
        ohlc = self.spx_ohlc.get(trade.trade_date)
        if not ohlc:
            return

        settlement = ohlc['close']
        trade.settlement_price = settlement
        trade.daily_high = ohlc['high']
        trade.daily_low = ohlc['low']

        # Put spread P&L
        if settlement >= trade.put_short_strike:
            trade.put_pnl = trade.put_credit
            trade.put_breached = False
        elif settlement > trade.put_long_strike:
            intrinsic = trade.put_short_strike - settlement
            trade.put_pnl = trade.put_credit - intrinsic
            trade.put_breached = True
        else:
            trade.put_pnl = trade.put_credit - self.spread_width
            trade.put_breached = True

        # Call spread P&L
        if settlement <= trade.call_short_strike:
            trade.call_pnl = trade.call_credit
            trade.call_breached = False
        elif settlement < trade.call_long_strike:
            intrinsic = settlement - trade.call_short_strike
            trade.call_pnl = trade.call_credit - intrinsic
            trade.call_breached = True
        else:
            trade.call_pnl = trade.call_credit - self.spread_width
            trade.call_breached = True

        # Total P&L
        total_pnl_per_contract = trade.put_pnl + trade.call_pnl
        trade.total_pnl = total_pnl_per_contract * 100 * trade.contracts
        trade.return_pct = (trade.total_pnl / trade.total_risk * 100) if trade.total_risk > 0 else 0

        # Outcome
        if not trade.put_breached and not trade.call_breached:
            trade.outcome = "MAX_PROFIT"
        elif trade.put_breached and trade.call_breached:
            trade.outcome = "DOUBLE_BREACH"
        elif trade.put_breached:
            trade.outcome = "PUT_BREACHED"
        else:
            trade.outcome = "CALL_BREACHED"

        # Update equity (compound daily)
        self.equity += trade.total_pnl
        self.high_water_mark = max(self.high_water_mark, self.equity)

    def run(self) -> Dict:
        """Run the aggressive backtest"""
        print("\n" + "=" * 80)
        print("AGGRESSIVE IRON CONDOR STRATEGY - TARGET: 10% MONTHLY")
        print("=" * 80)
        print(f"Period:             {self.start_date} to {self.end_date}")
        print(f"Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"Strategy:           Iron Condor (Bull Put + Bear Call)")
        print(f"Strike Distance:    {self.sd_multiplier} SD from OPEN")
        print(f"Risk Per Trade:     {self.risk_per_trade_pct}% (AGGRESSIVE)")
        print(f"Trading Days:       ALL (Mon-Fri)")
        print(f"Stop Loss:          NONE (let theta work)")
        print(f"Spread Width:       ${self.spread_width}")
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
            print(f"No 0DTE data found for {self.ticker}")
            return {}

        print(f"Found {len(trading_days)} trading days")

        # Process each day with progress bar
        total_days = len(trading_days)
        for i, trade_date in enumerate(trading_days):

            # Progress bar
            if i % 10 == 0 or i == total_days - 1:
                pct = ((i + 1) / total_days) * 100
                bar_len = 40
                filled = int(bar_len * (i + 1) / total_days)
                bar = "█" * filled + "░" * (bar_len - filled)
                print(f"\r  [{bar}] {pct:5.1f}% | Trades: {len(self.all_trades)} | Equity: ${self.equity:,.0f}", end="", flush=True)

            # Get options
            options = self.get_options_for_date(trade_date)
            if not options:
                self.days_skipped_no_data += 1
                continue

            # Execute trade
            trade = self.execute_trade(trade_date, options)

            if trade:
                self.settle_trade(trade)
                self.all_trades.append(trade)
                self.days_traded += 1
            else:
                self.days_skipped_no_data += 1

        print(f"\r  [{'█' * 40}] 100.0% Complete!{' ' * 30}")

        # Calculate results
        results = self.calculate_results()
        self.print_results(results)
        self.export_trades()

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

        # Calculate monthly % returns based on starting equity each month
        monthly_pct = {}
        month_start_equity = self.initial_capital
        sorted_months = sorted(monthly.keys())
        for month in sorted_months:
            pnl = monthly[month]
            pct = (pnl / month_start_equity) * 100
            monthly_pct[month] = pct
            month_start_equity += pnl  # Compound

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

        # Outcome breakdown
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
            'outcomes': outcomes,
            'monthly_returns': monthly_pct,
            'days_traded': self.days_traded,
            'days_skipped': self.days_skipped_no_data,
        }

    def print_results(self, results: Dict):
        """Print results"""
        if not results:
            return

        s = results['summary']
        t = results['trades']
        o = results['outcomes']

        print("\n" + "=" * 80)
        print("AGGRESSIVE IRON CONDOR RESULTS")
        print("=" * 80)

        print(f"\n{'CAPITAL':}")
        print(f"  Initial:              ${s['initial_capital']:>15,.2f}")
        print(f"  Final:                ${s['final_equity']:>15,.2f}")
        print(f"  Total P&L:            ${s['total_pnl']:>15,.2f}")
        print(f"  Total Return:         {s['total_return_pct']:>15.2f}%")

        print(f"\n{'PERFORMANCE':}")
        print(f"  Avg Monthly Return:   {s['avg_monthly_return_pct']:>15.2f}%")
        print(f"  Max Drawdown:         {s['max_drawdown_pct']:>15.2f}%")
        target_met = "✓ YES" if s['avg_monthly_return_pct'] >= 10.0 else "✗ NO"
        print(f"  10% Target Met:       {target_met:>15}")

        print(f"\n{'TRADE STATISTICS':}")
        print(f"  Total Trades:         {t['total']:>15}")
        print(f"  Win Rate:             {t['win_rate']:>15.1f}%")
        pf = f"{t['profit_factor']:.2f}" if t['profit_factor'] != float('inf') else "∞"
        print(f"  Profit Factor:        {pf:>15}")
        print(f"  Avg Win:              ${t['avg_win']:>14,.2f}")
        print(f"  Avg Loss:             ${t['avg_loss']:>14,.2f}")

        print(f"\n{'OUTCOME BREAKDOWN':}")
        for outcome, count in sorted(o.items(), key=lambda x: -x[1]):
            pct = count / t['total'] * 100
            print(f"  {outcome:20} {count:>5} ({pct:5.1f}%)")

        print(f"\n{'MONTHLY RETURNS':}")
        monthly = results['monthly_returns']
        for month, pct in sorted(monthly.items()):
            bar_len = min(30, int(abs(pct)))
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
            filename = f"aggressive_ic_trades_{self.start_date}_{self.end_date}.csv"

        filepath = Path(__file__).parent / filename

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self.all_trades[0]).keys())
            writer.writeheader()
            for trade in self.all_trades:
                writer.writerow(asdict(trade))

        print(f"\nExported {len(self.all_trades)} trades to {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Aggressive Iron Condor Strategy')

    parser.add_argument('--start', default='2021-01-01')
    parser.add_argument('--end', default='2025-12-01')
    parser.add_argument('--capital', type=float, default=1_000_000)
    parser.add_argument('--width', type=float, default=10.0)
    parser.add_argument('--sd', type=float, default=1.0)
    parser.add_argument('--risk', type=float, default=10.0, help='Risk per trade percent (default: 10)')
    parser.add_argument('--ticker', default='SPX')

    args = parser.parse_args()

    backtester = AggressiveBacktester(
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
