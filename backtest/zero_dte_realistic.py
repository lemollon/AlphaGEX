#!/usr/bin/env python3
"""
0DTE Iron Condor Strategy - REALISTIC VERSION

Adds real-world constraints:
1. Transaction costs (commissions + slippage)
2. Position limits (max contracts based on liquidity)
3. Realistic fills (not at best bid/ask)
4. Account size caps for liquidity

REALISTIC PARAMETERS:
====================
- Commission: $0.65 per contract per leg (industry standard)
- Slippage: $0.05-0.15 per spread (bid-ask crossing)
- Max contracts: 100 (liquidity limit for 0DTE)
- Max account utilization: Cap growth at realistic levels

Usage:
    python backtest/zero_dte_realistic.py --start 2021-01-01 --end 2025-12-01
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
    """Single Iron Condor trade with realistic costs"""
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
    put_credit_gross: float  # Before costs
    put_credit_net: float    # After costs

    # Call spread (bear call)
    call_short_strike: float
    call_long_strike: float
    call_credit_gross: float
    call_credit_net: float

    # Combined
    total_credit_gross: float
    total_credit_net: float
    spread_width: float
    max_loss: float

    # Costs
    commission_per_contract: float
    slippage_per_spread: float
    total_costs: float

    # Sizing
    contracts: int
    contracts_requested: int  # Before liquidity cap
    total_premium_gross: float
    total_premium_net: float
    total_risk: float
    risk_pct: float

    # Settlement
    settlement_price: float = 0
    daily_high: float = 0
    daily_low: float = 0

    # P&L
    put_pnl: float = 0
    call_pnl: float = 0
    gross_pnl: float = 0
    total_pnl: float = 0  # After costs
    return_pct: float = 0

    # Outcome
    outcome: str = ""
    put_breached: bool = False
    call_breached: bool = False


class RealisticBacktester:
    """
    Iron Condor backtester with REALISTIC constraints.

    Key differences from aggressive version:
    1. Commission: $0.65/contract/leg × 4 legs = $2.60/contract round-trip
    2. Slippage: $0.10 per spread (conservative estimate)
    3. Max contracts: 100 per trade (0DTE liquidity limit)
    4. Position sizing respects liquidity
    """

    def __init__(
        self,
        start_date: str = "2021-01-01",
        end_date: str = None,
        initial_capital: float = 1_000_000,
        spread_width: float = 10.0,
        sd_multiplier: float = 1.0,
        risk_per_trade_pct: float = 10.0,
        ticker: str = "SPX",
        # REALISTIC COSTS
        commission_per_leg: float = 0.65,  # Per contract per leg
        slippage_per_spread: float = 0.10,  # Per Iron Condor spread
        max_contracts: int = 100,  # Liquidity limit
    ):
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        self.initial_capital = initial_capital
        self.spread_width = spread_width
        self.sd_multiplier = sd_multiplier
        self.risk_per_trade_pct = risk_per_trade_pct
        self.ticker = ticker

        # Realistic costs
        self.commission_per_leg = commission_per_leg
        self.slippage_per_spread = slippage_per_spread
        self.max_contracts = max_contracts

        # Iron Condor has 4 legs (2 for put spread, 2 for call spread)
        # Entry: 4 legs, Exit: 4 legs (if exercised) = up to 8 transactions
        # But for 0DTE, most expire worthless so just entry costs
        self.commission_per_contract = commission_per_leg * 4  # 4 legs to open

        # State
        self.equity = initial_capital
        self.high_water_mark = initial_capital

        # Tracking
        self.all_trades: List[IronCondorTrade] = []
        self.trade_counter = 0

        # Stats
        self.days_traded = 0
        self.days_skipped_no_data = 0
        self.total_commissions = 0
        self.total_slippage = 0
        self.contracts_capped_count = 0

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
        """Get ALL trading days with 0DTE options"""
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
        """Find Iron Condor with REALISTIC fills (not best bid)"""
        if not options:
            return None

        underlying = options[0]['underlying_price']

        # Target strikes at 1 SD
        put_target = open_price - (self.sd_multiplier * expected_move)
        put_target = round(put_target / 5) * 5

        call_target = open_price + (self.sd_multiplier * expected_move)
        call_target = round(call_target / 5) * 5

        # Find OTM options
        otm_puts = [o for o in options if o['strike'] < underlying
                   and o.get('put_bid', 0) and o['put_bid'] > 0]
        otm_calls = [o for o in options if o['strike'] > underlying
                    and o.get('call_bid', 0) and o['call_bid'] > 0]

        if not otm_puts or not otm_calls:
            return None

        # Short put
        short_put = min(otm_puts, key=lambda x: abs(x['strike'] - put_target))

        # Long put
        long_put_strike = short_put['strike'] - self.spread_width
        long_put_candidates = [o for o in options
                              if abs(o['strike'] - long_put_strike) < 1
                              and o.get('put_ask', 0) and o['put_ask'] > 0]
        if not long_put_candidates:
            return None
        long_put = min(long_put_candidates, key=lambda x: abs(x['strike'] - long_put_strike))

        # Short call
        short_call = min(otm_calls, key=lambda x: abs(x['strike'] - call_target))

        # Long call
        long_call_strike = short_call['strike'] + self.spread_width
        long_call_candidates = [o for o in options
                               if abs(o['strike'] - long_call_strike) < 1
                               and o.get('call_ask', 0) and o['call_ask'] > 0]
        if not long_call_candidates:
            return None
        long_call = min(long_call_candidates, key=lambda x: abs(x['strike'] - long_call_strike))

        # REALISTIC FILLS: Use bid for sells, ask for buys
        # Then subtract slippage (we won't get best price)
        put_credit_gross = (short_put.get('put_bid', 0) or 0) - (long_put.get('put_ask', 0) or 0)
        call_credit_gross = (short_call.get('call_bid', 0) or 0) - (long_call.get('call_ask', 0) or 0)

        if put_credit_gross <= 0 or call_credit_gross <= 0:
            return None

        # Apply slippage (realistic fill is worse than quoted)
        put_credit_net = put_credit_gross - (self.slippage_per_spread / 2)
        call_credit_net = call_credit_gross - (self.slippage_per_spread / 2)

        return {
            'put_short_strike': short_put['strike'],
            'put_long_strike': long_put['strike'],
            'put_credit_gross': put_credit_gross,
            'put_credit_net': put_credit_net,
            'call_short_strike': short_call['strike'],
            'call_long_strike': long_call['strike'],
            'call_credit_gross': call_credit_gross,
            'call_credit_net': call_credit_net,
            'total_credit_gross': put_credit_gross + call_credit_gross,
            'total_credit_net': put_credit_net + call_credit_net,
        }

    def execute_trade(self, trade_date: str, options: List[Dict]) -> Optional[IronCondorTrade]:
        """Execute Iron Condor with realistic costs and position limits"""
        if not options:
            return None

        ohlc = self.spx_ohlc.get(trade_date)
        if not ohlc:
            return None

        open_price = ohlc['open']
        underlying = options[0]['underlying_price']
        vix = self.vix_data.get(trade_date, 15.0)

        # Expected move
        iv = vix / 100
        expected_move = open_price * iv * math.sqrt(1/252)

        # Find iron condor
        ic = self.find_iron_condor(options, open_price, expected_move)
        if not ic:
            return None

        # Max loss (one side can lose max)
        max_loss_per_spread = self.spread_width - ic['total_credit_net']
        if max_loss_per_spread <= 0:
            return None

        # Position sizing based on risk budget
        risk_budget = self.equity * (self.risk_per_trade_pct / 100)
        contracts_requested = int(risk_budget / (max_loss_per_spread * 100))
        contracts_requested = max(1, contracts_requested)

        # APPLY LIQUIDITY CAP
        contracts = min(contracts_requested, self.max_contracts)
        if contracts < contracts_requested:
            self.contracts_capped_count += 1

        # Calculate costs
        commission_total = self.commission_per_contract * contracts
        slippage_total = self.slippage_per_spread * contracts * 100  # Per spread in dollars
        total_costs = commission_total + slippage_total

        # Track costs
        self.total_commissions += commission_total
        self.total_slippage += slippage_total

        # Premium and risk
        total_premium_gross = ic['total_credit_gross'] * 100 * contracts
        total_premium_net = ic['total_credit_net'] * 100 * contracts - commission_total
        total_risk = max_loss_per_spread * 100 * contracts
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
            put_credit_gross=ic['put_credit_gross'],
            put_credit_net=ic['put_credit_net'],
            call_short_strike=ic['call_short_strike'],
            call_long_strike=ic['call_long_strike'],
            call_credit_gross=ic['call_credit_gross'],
            call_credit_net=ic['call_credit_net'],
            total_credit_gross=ic['total_credit_gross'],
            total_credit_net=ic['total_credit_net'],
            spread_width=self.spread_width,
            max_loss=max_loss_per_spread,
            commission_per_contract=self.commission_per_contract,
            slippage_per_spread=self.slippage_per_spread,
            total_costs=total_costs,
            contracts=contracts,
            contracts_requested=contracts_requested,
            total_premium_gross=total_premium_gross,
            total_premium_net=total_premium_net,
            total_risk=total_risk,
            risk_pct=risk_pct,
        )

        return trade

    def settle_trade(self, trade: IronCondorTrade):
        """Settle with costs already deducted"""
        ohlc = self.spx_ohlc.get(trade.trade_date)
        if not ohlc:
            return

        settlement = ohlc['close']
        trade.settlement_price = settlement
        trade.daily_high = ohlc['high']
        trade.daily_low = ohlc['low']

        # Put spread P&L (before costs)
        if settlement >= trade.put_short_strike:
            trade.put_pnl = trade.put_credit_gross
            trade.put_breached = False
        elif settlement > trade.put_long_strike:
            intrinsic = trade.put_short_strike - settlement
            trade.put_pnl = trade.put_credit_gross - intrinsic
            trade.put_breached = True
        else:
            trade.put_pnl = trade.put_credit_gross - self.spread_width
            trade.put_breached = True

        # Call spread P&L
        if settlement <= trade.call_short_strike:
            trade.call_pnl = trade.call_credit_gross
            trade.call_breached = False
        elif settlement < trade.call_long_strike:
            intrinsic = settlement - trade.call_short_strike
            trade.call_pnl = trade.call_credit_gross - intrinsic
            trade.call_breached = True
        else:
            trade.call_pnl = trade.call_credit_gross - self.spread_width
            trade.call_breached = True

        # Gross P&L
        gross_pnl_per_contract = trade.put_pnl + trade.call_pnl
        trade.gross_pnl = gross_pnl_per_contract * 100 * trade.contracts

        # Net P&L (subtract costs)
        trade.total_pnl = trade.gross_pnl - trade.total_costs
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

        # Update equity
        self.equity += trade.total_pnl
        self.high_water_mark = max(self.high_water_mark, self.equity)

    def run(self) -> Dict:
        """Run realistic backtest"""
        print("\n" + "=" * 80)
        print("REALISTIC IRON CONDOR STRATEGY")
        print("=" * 80)
        print(f"Period:             {self.start_date} to {self.end_date}")
        print(f"Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"Strategy:           Iron Condor (Bull Put + Bear Call)")
        print(f"Strike Distance:    {self.sd_multiplier} SD from OPEN")
        print(f"Risk Per Trade:     {self.risk_per_trade_pct}%")
        print(f"Spread Width:       ${self.spread_width}")
        print("-" * 80)
        print("REALISTIC CONSTRAINTS:")
        print(f"  Commission:       ${self.commission_per_leg}/leg × 4 = ${self.commission_per_contract}/contract")
        print(f"  Slippage:         ${self.slippage_per_spread}/spread")
        print(f"  Max Contracts:    {self.max_contracts} (liquidity limit)")
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
            print(f"No 0DTE data found")
            return {}

        print(f"Found {len(trading_days)} trading days")

        # Process each day
        total_days = len(trading_days)
        for i, trade_date in enumerate(trading_days):

            if i % 10 == 0 or i == total_days - 1:
                pct = ((i + 1) / total_days) * 100
                bar_len = 40
                filled = int(bar_len * (i + 1) / total_days)
                bar = "█" * filled + "░" * (bar_len - filled)
                print(f"\r  [{bar}] {pct:5.1f}% | Trades: {len(self.all_trades)} | Equity: ${self.equity:,.0f}", end="", flush=True)

            options = self.get_options_for_date(trade_date)
            if not options:
                self.days_skipped_no_data += 1
                continue

            trade = self.execute_trade(trade_date, options)

            if trade:
                self.settle_trade(trade)
                self.all_trades.append(trade)
                self.days_traded += 1
            else:
                self.days_skipped_no_data += 1

        print(f"\r  [{'█' * 40}] 100.0% Complete!{' ' * 30}")

        results = self.calculate_results()
        self.print_results(results)
        self.export_trades()

        return results

    def calculate_results(self) -> Dict:
        """Calculate results"""
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
            equity += t.total_pnl
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        # Outcomes
        outcomes = {}
        for t in self.all_trades:
            outcomes[t.outcome] = outcomes.get(t.outcome, 0) + 1

        # Cost analysis
        total_gross_pnl = sum(t.gross_pnl for t in self.all_trades)
        cost_drag = (self.total_commissions + self.total_slippage) / total_gross_pnl * 100 if total_gross_pnl > 0 else 0

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
                'cost_drag_pct': cost_drag,
                'trades_capped': self.contracts_capped_count,
            },
            'outcomes': outcomes,
            'monthly_returns': monthly_pct,
            'days_traded': self.days_traded,
        }

    def print_results(self, results: Dict):
        """Print results"""
        if not results:
            return

        s = results['summary']
        t = results['trades']
        c = results['costs']
        o = results['outcomes']

        print("\n" + "=" * 80)
        print("REALISTIC IRON CONDOR RESULTS")
        print("=" * 80)

        print(f"\nCAPITAL")
        print(f"  Initial:              ${s['initial_capital']:>15,.2f}")
        print(f"  Final:                ${s['final_equity']:>15,.2f}")
        print(f"  Total P&L:            ${s['total_pnl']:>15,.2f}")
        print(f"  Total Return:         {s['total_return_pct']:>15.2f}%")

        print(f"\nPERFORMANCE")
        print(f"  Avg Monthly Return:   {s['avg_monthly_return_pct']:>15.2f}%")
        print(f"  Max Drawdown:         {s['max_drawdown_pct']:>15.2f}%")
        target_met = "✓ YES" if s['avg_monthly_return_pct'] >= 10.0 else "✗ NO"
        print(f"  10% Target Met:       {target_met:>15}")

        print(f"\nTRANSACTION COSTS (REALISTIC)")
        print(f"  Total Commissions:    ${c['total_commissions']:>15,.2f}")
        print(f"  Total Slippage:       ${c['total_slippage']:>15,.2f}")
        print(f"  Total Costs:          ${c['total_costs']:>15,.2f}")
        print(f"  Cost Drag on Profits: {c['cost_drag_pct']:>15.2f}%")
        print(f"  Trades Size-Capped:   {c['trades_capped']:>15} (hit {self.max_contracts} contract limit)")

        print(f"\nTRADE STATISTICS")
        print(f"  Total Trades:         {t['total']:>15}")
        print(f"  Win Rate:             {t['win_rate']:>15.1f}%")
        pf = f"{t['profit_factor']:.2f}" if t['profit_factor'] != float('inf') else "∞"
        print(f"  Profit Factor:        {pf:>15}")
        print(f"  Avg Win:              ${t['avg_win']:>14,.2f}")
        print(f"  Avg Loss:             ${t['avg_loss']:>14,.2f}")

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
            filename = f"realistic_ic_trades_{self.start_date}_{self.end_date}.csv"

        filepath = Path(__file__).parent / filename

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self.all_trades[0]).keys())
            writer.writeheader()
            for trade in self.all_trades:
                writer.writerow(asdict(trade))

        print(f"\nExported {len(self.all_trades)} trades to {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Realistic Iron Condor Strategy')

    parser.add_argument('--start', default='2021-01-01')
    parser.add_argument('--end', default='2025-12-01')
    parser.add_argument('--capital', type=float, default=1_000_000)
    parser.add_argument('--width', type=float, default=10.0)
    parser.add_argument('--sd', type=float, default=1.0)
    parser.add_argument('--risk', type=float, default=10.0)
    parser.add_argument('--ticker', default='SPX')
    # Realistic constraints
    parser.add_argument('--commission', type=float, default=0.65, help='Commission per leg (default: $0.65)')
    parser.add_argument('--slippage', type=float, default=0.10, help='Slippage per spread (default: $0.10)')
    parser.add_argument('--maxcontracts', type=int, default=100, help='Max contracts per trade (default: 100)')

    args = parser.parse_args()

    backtester = RealisticBacktester(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        spread_width=args.width,
        sd_multiplier=args.sd,
        risk_per_trade_pct=args.risk,
        ticker=args.ticker,
        commission_per_leg=args.commission,
        slippage_per_spread=args.slippage,
        max_contracts=args.maxcontracts,
    )

    results = backtester.run()
    return results


if __name__ == "__main__":
    main()
