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
        """
        if not options:
            return None

        # Filter for OTM puts (delta < 0, closer to 0 = more OTM)
        # ORAT delta is negative for puts, so we look for delta close to -target_delta
        short_candidates = [
            opt for opt in options
            if opt['delta'] is not None
            and -0.30 < opt['delta'] < -0.05  # Between 5 and 30 delta puts
        ]

        if not short_candidates:
            return None

        # Find put closest to target delta
        target = -target_delta
        short_put = min(short_candidates, key=lambda x: abs(x['delta'] - target))

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
        print("=" * 80)

        # Get trading days
        print("\nFetching trading days from ORAT database...")
        trading_days = self.get_trading_days()

        if not trading_days:
            print("No trading days found with 0DTE options!")
            return {}

        print(f"Found {len(trading_days)} trading days with 0DTE data")

        # Process each day
        for i, trade_date in enumerate(trading_days):
            self.days_with_data += 1

            # Get options for this day
            options = self.get_options_for_date(trade_date)

            if not options:
                self.days_skipped += 1
                continue

            # Get underlying price for settlement
            underlying_price = options[0]['underlying_price'] if options else 0

            # Execute trade
            trade = self.execute_trade(trade_date, options)

            if trade:
                # For 0DTE, we settle same day using underlying close as proxy
                # In reality, SPX settles to AM settlement price
                self.settle_trade(trade, underlying_price)
                self.all_trades.append(trade)
                self.days_traded += 1

                # Progress output
                if i % 50 == 0 or trade.outcome in ["MAX_LOSS", "PARTIAL_LOSS"]:
                    status = "+" if trade.total_pnl > 0 else "-"
                    print(f"[{trade_date}] {status} {trade.outcome}: "
                          f"${trade.total_pnl:+,.2f} | "
                          f"Equity: ${self.equity:,.2f} | "
                          f"Short: {trade.short_strike} | "
                          f"Settlement: {underlying_price:.2f}")
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

        avg_win = sum(t.total_pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.total_pnl for t in losses) / len(losses) if losses else 0

        profit_factor = abs(sum(t.total_pnl for t in wins) / sum(t.total_pnl for t in losses)) if losses and sum(t.total_pnl for t in losses) != 0 else float('inf')

        # Max drawdown
        max_dd = max(d.drawdown_pct for d in self.daily_equity) if self.daily_equity else 0

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
                'max_drawdown_pct': max_dd,
            },
            'trades': {
                'total_trades': len(self.all_trades),
                'winning_trades': len(wins),
                'losing_trades': len(losses),
                'win_rate_pct': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'largest_win': max(t.total_pnl for t in self.all_trades) if self.all_trades else 0,
                'largest_loss': min(t.total_pnl for t in self.all_trades) if self.all_trades else 0,
            },
            'outcomes': outcomes,
            'monthly_returns': monthly_returns,
            'avg_monthly_return_pct': avg_monthly,
            'monthly_target_met': avg_monthly >= self.monthly_return_target,
            'data_quality': {
                'days_with_data': self.days_with_data,
                'days_traded': self.days_traded,
                'days_skipped': self.days_skipped,
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
        """Print formatted results"""
        s = results['summary']
        t = results['trades']
        o = results['outcomes']

        print("\n" + "=" * 80)
        print("0DTE BULL PUT SPREAD BACKTEST RESULTS")
        print("=" * 80)

        print(f"\nPERFORMANCE:")
        print(f"  Initial Capital:     ${s['initial_capital']:,.2f}")
        print(f"  Final Equity:        ${s['final_equity']:,.2f}")
        print(f"  Total P&L:           ${s['total_pnl']:+,.2f}")
        print(f"  Total Return:        {s['total_return_pct']:+.2f}%")
        print(f"  Max Drawdown:        {s['max_drawdown_pct']:.2f}%")

        print(f"\nTRADE STATISTICS:")
        print(f"  Total Trades:        {t['total_trades']}")
        print(f"  Winning Trades:      {t['winning_trades']}")
        print(f"  Losing Trades:       {t['losing_trades']}")
        print(f"  Win Rate:            {t['win_rate_pct']:.1f}%")
        print(f"  Avg Win:             ${t['avg_win']:+,.2f}")
        print(f"  Avg Loss:            ${t['avg_loss']:+,.2f}")
        print(f"  Profit Factor:       {t['profit_factor']:.2f}")
        print(f"  Largest Win:         ${t['largest_win']:+,.2f}")
        print(f"  Largest Loss:        ${t['largest_loss']:+,.2f}")

        print(f"\nOUTCOME BREAKDOWN:")
        for outcome, count in o.items():
            pct = count / t['total_trades'] * 100 if t['total_trades'] > 0 else 0
            print(f"  {outcome}: {count} ({pct:.1f}%)")

        print(f"\nMONTHLY RETURNS:")
        print(f"  Average Monthly:     {results['avg_monthly_return_pct']:+.2f}%")
        print(f"  Target ({self.monthly_return_target}%):        {'MET' if results['monthly_target_met'] else 'NOT MET'}")

        # Show some months
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
    parser.add_argument('--export', action='store_true', help='Export trades to CSV')

    args = parser.parse_args()

    backtester = ZeroDTEBullPutSpreadBacktester(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        target_delta=args.delta,
        spread_width=args.width,
        max_risk_per_trade_pct=args.risk,
        ticker=args.ticker
    )

    results = backtester.run()

    if args.export and backtester.all_trades:
        backtester.export_trades_to_csv()

    return results


if __name__ == "__main__":
    main()
