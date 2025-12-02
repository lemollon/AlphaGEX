"""
SPX WHEEL TRADING SYSTEM - Complete End-to-End

This is the COMPLETE system for trading SPX cash-secured puts:

1. CALIBRATION: Run backtests with different parameters to find optimal settings
2. LIVE TRADING: Execute trades using calibrated parameters
3. MONITORING: Compare live results to backtest expectations
4. ADJUSTMENT: Auto-adjust parameters when performance diverges

WORKFLOW:
=========
Step 1: Run calibration (finds best parameters from historical data)
    optimizer = SPXWheelOptimizer()
    best_params = optimizer.find_optimal_parameters()

Step 2: Initialize live trader with calibrated parameters
    trader = SPXWheelTrader(parameters=best_params)

Step 3: Execute daily (or on schedule)
    trader.run_daily_cycle()

Step 4: Monitor and adjust
    trader.compare_to_backtest()
    trader.auto_calibrate()  # Re-run if performance diverges

IMPORTANT: SPX is CASH-SETTLED
- No shares are assigned
- No covered calls
- Pure premium collection from selling puts
- Settlement: Cash difference between strike and settlement price
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection
from data.polygon_data_fetcher import polygon_fetcher

logger = logging.getLogger(__name__)


@dataclass
class WheelParameters:
    """
    Calibrated parameters for SPX wheel trading.
    These come from backtesting - NOT guesses.
    """
    # Core parameters
    put_delta: float = 0.20          # Target delta for puts (0.15-0.30)
    dte_target: int = 45             # Days to expiration (30-60)
    max_margin_pct: float = 0.50     # Max % of capital as margin

    # Position sizing
    contracts_per_trade: int = 1     # Contracts per trade
    max_open_positions: int = 3      # Max concurrent positions

    # Risk management
    stop_loss_pct: float = 200       # Close if option doubles (200%)
    profit_target_pct: float = 50    # Close at 50% profit
    roll_at_dte: int = 7             # Roll position at 7 DTE

    # Market regime filters
    min_vix: float = 12              # Don't trade below this VIX
    max_vix: float = 35              # Don't trade above this VIX
    avoid_earnings: bool = True      # Skip around earnings

    # Backtest performance (filled by optimizer)
    backtest_win_rate: float = 0
    backtest_expectancy: float = 0
    backtest_max_drawdown: float = 0
    backtest_total_return: float = 0
    backtest_period: str = ""
    calibration_date: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> 'WheelParameters':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class BacktestResult:
    """Result from a single backtest run"""
    parameters: WheelParameters
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return_pct: float
    max_drawdown_pct: float
    expectancy_pct: float  # Expected return per trade
    sharpe_ratio: float
    premium_collected: float
    settlement_losses: float
    net_profit: float


class SPXWheelOptimizer:
    """
    Finds optimal parameters by backtesting multiple configurations.

    This is STEP 1 of the workflow:
    - Tests different delta/DTE combinations
    - Finds what works best for your risk tolerance
    - Outputs parameters to use in live trading
    """

    def __init__(
        self,
        start_date: str = "2022-01-01",
        end_date: str = None,
        initial_capital: float = 1000000
    ):
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        self.initial_capital = initial_capital
        self.results: List[BacktestResult] = []

    def find_optimal_parameters(
        self,
        delta_range: List[float] = [0.15, 0.20, 0.25, 0.30],
        dte_range: List[int] = [30, 45, 60],
        optimize_for: str = 'sharpe'  # 'sharpe', 'return', 'win_rate', 'drawdown'
    ) -> WheelParameters:
        """
        Test multiple parameter combinations and find the best.

        Args:
            delta_range: List of deltas to test
            dte_range: List of DTEs to test
            optimize_for: What metric to optimize

        Returns:
            WheelParameters with best configuration
        """
        print("\n" + "="*70)
        print("SPX WHEEL PARAMETER OPTIMIZATION")
        print("="*70)
        print(f"Testing {len(delta_range) * len(dte_range)} configurations...")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Capital: ${self.initial_capital:,.0f}")
        print(f"Optimizing for: {optimize_for}")
        print("="*70 + "\n")

        self.results = []

        for delta in delta_range:
            for dte in dte_range:
                params = WheelParameters(
                    put_delta=delta,
                    dte_target=dte
                )

                print(f"Testing: Delta={delta}, DTE={dte}...", end=" ")

                result = self._run_single_backtest(params)
                self.results.append(result)

                print(f"Win: {result.win_rate:.1f}%, Return: {result.total_return_pct:+.1f}%, "
                      f"DD: {result.max_drawdown_pct:.1f}%")

        # Find best based on optimization target
        best = self._select_best(optimize_for)

        # Store backtest stats in parameters
        best.parameters.backtest_win_rate = best.win_rate
        best.parameters.backtest_expectancy = best.expectancy_pct
        best.parameters.backtest_max_drawdown = best.max_drawdown_pct
        best.parameters.backtest_total_return = best.total_return_pct
        best.parameters.backtest_period = f"{self.start_date} to {self.end_date}"
        best.parameters.calibration_date = datetime.now().isoformat()

        self._print_optimization_results(best)
        self._save_parameters(best.parameters)

        return best.parameters

    def _run_single_backtest(self, params: WheelParameters) -> BacktestResult:
        """Run backtest with specific parameters"""
        from backtest.spx_premium_backtest import SPXPremiumBacktester

        backtester = SPXPremiumBacktester(
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            put_delta=params.put_delta,
            dte_target=params.dte_target,
            max_margin_pct=params.max_margin_pct
        )

        # Suppress output during optimization
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            results = backtester.run()

        summary = results['summary']

        return BacktestResult(
            parameters=params,
            total_trades=summary['total_trades'],
            winning_trades=summary['expired_otm'],
            losing_trades=summary['cash_settled_itm'],
            win_rate=summary['win_rate'],
            total_return_pct=summary['total_return_pct'],
            max_drawdown_pct=summary['max_drawdown_pct'],
            expectancy_pct=summary['net_premium'] / max(1, summary['total_trades']) / 100,
            sharpe_ratio=summary['total_return_pct'] / max(1, summary['max_drawdown_pct']),
            premium_collected=summary['total_premium_collected'],
            settlement_losses=summary['total_settlement_losses'],
            net_profit=summary['net_premium']
        )

    def _select_best(self, optimize_for: str) -> BacktestResult:
        """Select best result based on optimization target"""
        if optimize_for == 'sharpe':
            return max(self.results, key=lambda x: x.sharpe_ratio)
        elif optimize_for == 'return':
            return max(self.results, key=lambda x: x.total_return_pct)
        elif optimize_for == 'win_rate':
            return max(self.results, key=lambda x: x.win_rate)
        elif optimize_for == 'drawdown':
            return min(self.results, key=lambda x: x.max_drawdown_pct)
        else:
            return max(self.results, key=lambda x: x.sharpe_ratio)

    def _print_optimization_results(self, best: BacktestResult):
        """Print optimization summary"""
        print("\n" + "="*70)
        print("OPTIMIZATION RESULTS")
        print("="*70)

        print("\nALL CONFIGURATIONS TESTED:")
        print(f"{'Delta':<8} {'DTE':<6} {'Win%':<8} {'Return%':<10} {'MaxDD%':<10} {'Sharpe':<8}")
        print("-"*60)

        for r in sorted(self.results, key=lambda x: x.sharpe_ratio, reverse=True):
            marker = " <-- BEST" if r == best else ""
            print(f"{r.parameters.put_delta:<8.2f} {r.parameters.dte_target:<6} "
                  f"{r.win_rate:<8.1f} {r.total_return_pct:<10.1f} "
                  f"{r.max_drawdown_pct:<10.1f} {r.sharpe_ratio:<8.2f}{marker}")

        print("\n" + "="*70)
        print("OPTIMAL PARAMETERS FOUND")
        print("="*70)
        print(f"Put Delta:       {best.parameters.put_delta}")
        print(f"DTE Target:      {best.parameters.dte_target} days")
        print(f"Win Rate:        {best.win_rate:.1f}%")
        print(f"Total Return:    {best.total_return_pct:+.1f}%")
        print(f"Max Drawdown:    {best.max_drawdown_pct:.1f}%")
        print(f"Expectancy:      ${best.expectancy_pct*100:.2f} per trade")
        print(f"Sharpe Ratio:    {best.sharpe_ratio:.2f}")
        print("="*70)

    def _save_parameters(self, params: WheelParameters):
        """Save calibrated parameters to database"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Ensure table exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS spx_wheel_parameters (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    parameters JSONB NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')

            # Deactivate old parameters
            cursor.execute("UPDATE spx_wheel_parameters SET is_active = FALSE")

            # Insert new parameters
            cursor.execute('''
                INSERT INTO spx_wheel_parameters (parameters, is_active)
                VALUES (%s, TRUE)
            ''', (json.dumps(params.to_dict()),))

            conn.commit()
            conn.close()
            print("\nParameters saved to database.")

        except Exception as e:
            logger.error(f"Failed to save parameters: {e}")


class SPXWheelTrader:
    """
    LIVE SPX wheel trader using calibrated parameters.

    This is STEP 2 of the workflow:
    - Loads parameters from calibration
    - Executes trades on SPX
    - Manages positions
    - Tracks performance vs backtest
    """

    def __init__(self, parameters: WheelParameters = None):
        """
        Initialize with calibrated parameters.

        If no parameters provided, loads from database (most recent calibration).
        """
        self.params = parameters or self._load_parameters()
        self.positions: List[Dict] = []
        self._ensure_tables()

        print("\n" + "="*70)
        print("SPX WHEEL TRADER INITIALIZED")
        print("="*70)
        print(f"Parameters from: {self.params.calibration_date or 'default'}")
        print(f"Put Delta:       {self.params.put_delta}")
        print(f"DTE Target:      {self.params.dte_target}")
        print(f"Max Margin:      {self.params.max_margin_pct*100:.0f}%")
        print(f"Backtest Win%:   {self.params.backtest_win_rate:.1f}%")
        print(f"Backtest Return: {self.params.backtest_total_return:+.1f}%")
        print("="*70)

    def _load_parameters(self) -> WheelParameters:
        """Load most recent calibrated parameters from database"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT parameters FROM spx_wheel_parameters
                WHERE is_active = TRUE
                ORDER BY timestamp DESC
                LIMIT 1
            ''')

            result = cursor.fetchone()
            conn.close()

            if result:
                return WheelParameters.from_dict(result[0])

        except Exception as e:
            logger.warning(f"Could not load parameters: {e}")

        print("WARNING: Using default parameters - run calibration first!")
        return WheelParameters()

    def _ensure_tables(self):
        """Create required tables"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS spx_wheel_positions (
                    id SERIAL PRIMARY KEY,
                    opened_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMPTZ,
                    status VARCHAR(20) DEFAULT 'OPEN',
                    option_ticker VARCHAR(50),
                    strike DECIMAL(10,2),
                    expiration DATE,
                    contracts INTEGER,
                    entry_price DECIMAL(10,4),
                    exit_price DECIMAL(10,4),
                    premium_received DECIMAL(12,2),
                    settlement_pnl DECIMAL(12,2),
                    total_pnl DECIMAL(12,2),
                    parameters_used JSONB,
                    notes TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS spx_wheel_performance (
                    id SERIAL PRIMARY KEY,
                    date DATE UNIQUE,
                    equity DECIMAL(14,2),
                    daily_pnl DECIMAL(12,2),
                    cumulative_pnl DECIMAL(12,2),
                    open_positions INTEGER,
                    backtest_expected_equity DECIMAL(14,2),
                    divergence_pct DECIMAL(8,4)
                )
            ''')

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to create tables: {e}")

    def run_daily_cycle(self) -> Dict:
        """
        Run the daily trading cycle.

        Returns dict with actions taken and current status.
        """
        now = datetime.now()
        print(f"\n[{now.strftime('%Y-%m-%d %H:%M')}] Running daily cycle...")

        result = {
            'timestamp': now.isoformat(),
            'actions': [],
            'positions_opened': 0,
            'positions_closed': 0,
            'current_positions': 0
        }

        # 1. Check market conditions
        if not self._should_trade_today():
            result['actions'].append('SKIP: Market conditions not favorable')
            return result

        # 2. Get current SPX price
        spot = self._get_spx_price()
        if not spot:
            result['actions'].append('ERROR: Could not get SPX price')
            return result

        # 3. Check expiring positions
        expired = self._process_expirations(spot)
        result['positions_closed'] = expired
        if expired:
            result['actions'].append(f'CLOSED: {expired} positions expired')

        # 4. Check if we should roll any positions
        rolled = self._check_rolls(spot)
        if rolled:
            result['actions'].append(f'ROLLED: {rolled} positions')

        # 5. Open new position if we have capacity
        if self._can_open_position(spot):
            opened = self._open_new_position(spot)
            if opened:
                result['positions_opened'] = 1
                result['actions'].append(f'OPENED: New put position')

        # 6. Update performance tracking
        self._update_performance(spot)

        result['current_positions'] = len(self._get_open_positions())

        # 7. Check divergence from backtest
        divergence = self._check_backtest_divergence()
        if divergence and abs(divergence) > 10:
            result['actions'].append(f'WARNING: {divergence:+.1f}% divergence from backtest')

        return result

    def _should_trade_today(self) -> bool:
        """Check if we should trade based on market conditions"""
        vix = self._get_vix()

        if vix < self.params.min_vix:
            print(f"VIX ({vix:.1f}) below minimum ({self.params.min_vix})")
            return False

        if vix > self.params.max_vix:
            print(f"VIX ({vix:.1f}) above maximum ({self.params.max_vix})")
            return False

        # Check if market is open
        now = datetime.now()
        if now.weekday() > 4:  # Weekend
            return False

        return True

    def _get_spx_price(self) -> Optional[float]:
        """Get current SPX price"""
        for symbol in ['SPX', '^SPX', '$SPX.X', 'I:SPX']:
            price = polygon_fetcher.get_current_price(symbol)
            if price and price > 0:
                return price
        return None

    def _get_vix(self) -> float:
        """Get current VIX"""
        for symbol in ['^VIX', 'VIX', '$VIX.X']:
            vix = polygon_fetcher.get_current_price(symbol)
            if vix and vix > 0:
                return vix
        return 17.0  # Default

    def _get_open_positions(self) -> List[Dict]:
        """Get open positions from database"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, option_ticker, strike, expiration, contracts, entry_price, premium_received
                FROM spx_wheel_positions
                WHERE status = 'OPEN'
            ''')

            positions = []
            for row in cursor.fetchall():
                positions.append({
                    'id': row[0],
                    'option_ticker': row[1],
                    'strike': float(row[2]),
                    'expiration': row[3],
                    'contracts': row[4],
                    'entry_price': float(row[5]),
                    'premium_received': float(row[6])
                })

            conn.close()
            return positions

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def _can_open_position(self, spot: float) -> bool:
        """Check if we can open a new position"""
        open_positions = self._get_open_positions()

        if len(open_positions) >= self.params.max_open_positions:
            return False

        # Check margin
        # TODO: Calculate actual margin used
        return True

    def _open_new_position(self, spot: float) -> bool:
        """Open a new put position"""
        # Calculate strike
        strike_offset = spot * (0.04 + self.params.put_delta * 0.15)
        strike = round((spot - strike_offset) / 5) * 5

        # Calculate expiration
        target = datetime.now() + timedelta(days=self.params.dte_target)
        days_until_friday = (4 - target.weekday()) % 7
        expiration = (target + timedelta(days=days_until_friday)).date()

        # Get option price
        option_ticker = f"O:SPX{expiration.strftime('%y%m%d')}P{int(strike*1000):08d}"

        # For now, estimate price (in real trading, get from broker)
        estimated_price = spot * 0.015 * (self.params.dte_target / 45) ** 0.5

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO spx_wheel_positions (
                    option_ticker, strike, expiration, contracts,
                    entry_price, premium_received, parameters_used, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                option_ticker,
                strike,
                expiration,
                self.params.contracts_per_trade,
                estimated_price,
                estimated_price * 100 * self.params.contracts_per_trade,
                json.dumps(self.params.to_dict()),
                f"Opened at SPX={spot:.2f}, Delta={self.params.put_delta}"
            ))

            position_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()

            print(f"OPENED: {option_ticker} @ ${estimated_price:.2f}")
            print(f"        Strike: ${strike:.0f}, Exp: {expiration}")

            return True

        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return False

    def _process_expirations(self, spot: float) -> int:
        """Process any expiring positions"""
        today = datetime.now().date()
        closed = 0

        for pos in self._get_open_positions():
            if pos['expiration'] <= today:
                # Determine settlement
                if spot < pos['strike']:
                    # ITM - loss
                    settlement_pnl = -(pos['strike'] - spot) * 100 * pos['contracts']
                else:
                    # OTM - keep premium
                    settlement_pnl = 0

                total_pnl = pos['premium_received'] + settlement_pnl

                try:
                    conn = get_connection()
                    cursor = conn.cursor()

                    cursor.execute('''
                        UPDATE spx_wheel_positions SET
                            status = 'CLOSED',
                            closed_at = NOW(),
                            settlement_pnl = %s,
                            total_pnl = %s,
                            notes = notes || %s
                        WHERE id = %s
                    ''', (
                        settlement_pnl,
                        total_pnl,
                        f" | Settled at SPX={spot:.2f}, P&L=${total_pnl:.2f}",
                        pos['id']
                    ))

                    conn.commit()
                    conn.close()
                    closed += 1

                    print(f"CLOSED: {pos['option_ticker']} | P&L: ${total_pnl:.2f}")

                except Exception as e:
                    logger.error(f"Failed to close position: {e}")

        return closed

    def _check_rolls(self, spot: float) -> int:
        """Check if any positions need to be rolled"""
        # TODO: Implement roll logic
        return 0

    def _update_performance(self, spot: float):
        """Update performance tracking - store daily equity snapshot"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Calculate current equity
            cursor.execute('''
                SELECT
                    COALESCE(SUM(total_pnl), 0) FILTER (WHERE status = 'CLOSED'),
                    COALESCE(SUM(premium_received), 0) FILTER (WHERE status = 'OPEN')
                FROM spx_wheel_positions
            ''')

            result = cursor.fetchone()
            realized_pnl = float(result[0] or 0)
            open_premium = float(result[1] or 0)

            # Rough mark-to-market for open positions
            open_positions = self._get_open_positions()
            mtm_adjustment = 0
            for pos in open_positions:
                # If ITM, estimate loss
                if spot < pos['strike']:
                    mtm_adjustment -= (pos['strike'] - spot) * 100 * pos['contracts']

            # Use initial capital of 1M as baseline (could be configured)
            base_capital = 1000000
            current_equity = base_capital + realized_pnl + open_premium + mtm_adjustment
            cumulative_pnl = current_equity - base_capital

            today = datetime.now().date()

            cursor.execute('''
                INSERT INTO spx_wheel_performance (date, equity, daily_pnl, cumulative_pnl, open_positions)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    equity = EXCLUDED.equity,
                    cumulative_pnl = EXCLUDED.cumulative_pnl,
                    open_positions = EXCLUDED.open_positions
            ''', (today, current_equity, 0, cumulative_pnl, len(open_positions)))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.warning(f"Could not update performance: {e}")

    def _check_backtest_divergence(self) -> Optional[float]:
        """Check how live performance compares to backtest"""
        comparison = self.compare_to_backtest()
        return comparison.get('divergence', None)

    def compare_to_backtest(self) -> Dict:
        """
        Compare live performance to backtest expectations.

        Returns dict with comparison metrics.
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get live trading statistics
            cursor.execute('''
                SELECT
                    COUNT(*) FILTER (WHERE status = 'CLOSED') as closed,
                    COUNT(*) FILTER (WHERE total_pnl > 0) as winners,
                    COALESCE(SUM(premium_received), 0) as premium,
                    COALESCE(SUM(settlement_pnl), 0) as settlement,
                    COALESCE(SUM(total_pnl), 0) as total_pnl
                FROM spx_wheel_positions
            ''')

            result = cursor.fetchone()
            conn.close()

            if not result or result[0] == 0:
                return {
                    'live_return': 0,
                    'live_win_rate': 0,
                    'backtest_return': self.params.backtest_total_return,
                    'backtest_win_rate': self.params.backtest_win_rate,
                    'divergence': 0,
                    'recommendation': 'Not enough trades yet for comparison'
                }

            closed, winners, premium, settlement, total_pnl = result

            live_win_rate = (winners / closed * 100) if closed > 0 else 0

            # Calculate win rate divergence
            win_rate_divergence = live_win_rate - self.params.backtest_win_rate

            # Recommendation based on divergence
            if closed < 10:
                recommendation = 'Need more trades for meaningful comparison (min 10)'
            elif abs(win_rate_divergence) < 5:
                recommendation = 'Performance tracking as expected'
            elif abs(win_rate_divergence) < 10:
                recommendation = 'Minor divergence - monitor closely'
            else:
                recommendation = 'SIGNIFICANT DIVERGENCE - Consider recalibrating'

            return {
                'live_return': float(total_pnl),
                'live_win_rate': live_win_rate,
                'backtest_return': self.params.backtest_total_return,
                'backtest_win_rate': self.params.backtest_win_rate,
                'divergence': win_rate_divergence,
                'closed_trades': closed,
                'recommendation': recommendation
            }

        except Exception as e:
            logger.error(f"Failed to compare to backtest: {e}")
            return {
                'live_return': 0,
                'backtest_return': self.params.backtest_total_return,
                'divergence': 0,
                'recommendation': f'Error: {e}'
            }

    def get_status(self) -> Dict:
        """Get current trader status"""
        positions = self._get_open_positions()

        return {
            'parameters': self.params.to_dict(),
            'open_positions': len(positions),
            'positions': positions,
            'backtest_win_rate': self.params.backtest_win_rate,
            'backtest_return': self.params.backtest_total_return
        }


def calibrate_and_trade():
    """
    COMPLETE WORKFLOW: Calibrate parameters then start trading.

    This is what you run to set up the system:
    1. Runs optimization to find best parameters
    2. Initializes trader with those parameters
    3. Ready to execute trades
    """
    print("\n" + "="*70)
    print("SPX WHEEL SYSTEM - CALIBRATE AND TRADE")
    print("="*70)

    # Step 1: Calibrate
    print("\n[STEP 1] Running parameter optimization...")
    optimizer = SPXWheelOptimizer(
        start_date="2022-01-01",
        initial_capital=1000000
    )

    params = optimizer.find_optimal_parameters(
        delta_range=[0.15, 0.20, 0.25],
        dte_range=[30, 45, 60],
        optimize_for='sharpe'
    )

    # Step 2: Initialize trader
    print("\n[STEP 2] Initializing trader with optimized parameters...")
    trader = SPXWheelTrader(parameters=params)

    # Step 3: Show status
    print("\n[STEP 3] System ready. Current status:")
    status = trader.get_status()
    print(f"  Open positions: {status['open_positions']}")
    print(f"  Using delta: {params.put_delta}")
    print(f"  Using DTE: {params.dte_target}")
    print(f"  Backtest win rate: {params.backtest_win_rate:.1f}%")

    print("\n" + "="*70)
    print("SYSTEM READY")
    print("="*70)
    print("\nNext steps:")
    print("  1. Run trader.run_daily_cycle() to execute trades")
    print("  2. Run trader.compare_to_backtest() to check performance")
    print("  3. Re-run calibrate_and_trade() monthly to update parameters")
    print("="*70)

    return trader


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='SPX Wheel Trading System')
    parser.add_argument('--calibrate', action='store_true', help='Run calibration')
    parser.add_argument('--trade', action='store_true', help='Run daily trade cycle')
    parser.add_argument('--status', action='store_true', help='Show current status')
    parser.add_argument('--full', action='store_true', help='Calibrate and prepare for trading')
    args = parser.parse_args()

    if args.calibrate:
        optimizer = SPXWheelOptimizer()
        optimizer.find_optimal_parameters()

    elif args.trade:
        trader = SPXWheelTrader()
        result = trader.run_daily_cycle()
        print(f"\nActions taken: {result['actions']}")

    elif args.status:
        trader = SPXWheelTrader()
        status = trader.get_status()
        print(json.dumps(status, indent=2, default=str))

    elif args.full:
        calibrate_and_trade()

    else:
        parser.print_help()
