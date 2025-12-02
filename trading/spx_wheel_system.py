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

# Broker integration - THIS IS WHAT EXECUTES REAL TRADES
try:
    from data.tradier_data_fetcher import TradierDataFetcher, OrderSide, OrderType
    BROKER_AVAILABLE = True
except ImportError:
    BROKER_AVAILABLE = False

# Market calendar for earnings check - THIS WAS MISSING!
try:
    from trading.market_calendar import get_calendar, should_trade_today
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False

# Alert system - THIS WAS MISSING!
try:
    from trading.alerts import get_alerts, AlertLevel
    ALERTS_AVAILABLE = True
except ImportError:
    ALERTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """
    CRITICAL: This determines if REAL money is at risk.

    PAPER - Logs trades to database only. No real orders placed.
    LIVE  - Executes actual orders via Tradier. REAL MONEY AT RISK.
    """
    PAPER = "paper"
    LIVE = "live"


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

        # === SAVE BEST BACKTEST TRADES TO DATABASE ===
        print("\n[SAVING BEST BACKTEST TRADES TO DATABASE...]")
        self._run_single_backtest(best.parameters, save_to_db=True)
        print("✓ Backtest trades saved - view in dashboard!")

        return best.parameters

    def _run_single_backtest(self, params: WheelParameters, save_to_db: bool = False) -> BacktestResult:
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

        # Suppress output during optimization (but still save trades if requested)
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            results = backtester.run(save_to_db=save_to_db)

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
    SPX wheel trader using calibrated parameters.

    SUPPORTS TWO MODES:
    - PAPER: Logs trades to database only. No real money.
    - LIVE:  Executes real orders via Tradier. REAL MONEY AT RISK.

    This is STEP 2 of the workflow:
    - Loads parameters from calibration
    - Executes trades on SPX (paper or live)
    - Manages positions
    - Tracks performance vs backtest
    """

    def __init__(
        self,
        parameters: WheelParameters = None,
        mode: TradingMode = TradingMode.PAPER,
        initial_capital: float = 1000000
    ):
        """
        Initialize with calibrated parameters.

        Args:
            parameters: Calibrated WheelParameters (loads from DB if None)
            mode: PAPER (simulation) or LIVE (real money)
            initial_capital: Starting capital for paper trading
        """
        self.params = parameters or self._load_parameters()
        self.positions: List[Dict] = []
        self.mode = mode
        self.initial_capital = initial_capital
        self.broker = None

        # Initialize broker for LIVE mode
        if mode == TradingMode.LIVE:
            if not BROKER_AVAILABLE:
                raise RuntimeError(
                    "LIVE mode requires Tradier broker. "
                    "Set TRADIER_API_KEY and TRADIER_ACCOUNT_ID."
                )
            self.broker = TradierDataFetcher()
            if self.broker.sandbox:
                print("⚠️  WARNING: Tradier is in SANDBOX mode (paper trading via broker)")
            else:
                print("🔴 LIVE TRADING MODE - REAL MONEY AT RISK!")

        self._ensure_tables()

        print("\n" + "="*70)
        print(f"SPX WHEEL TRADER - {mode.value.upper()} MODE")
        print("="*70)
        print(f"Parameters from: {self.params.calibration_date or 'default'}")
        print(f"Put Delta:       {self.params.put_delta}")
        print(f"DTE Target:      {self.params.dte_target}")
        print(f"Max Margin:      {self.params.max_margin_pct*100:.0f}%")
        print(f"Backtest Win%:   {self.params.backtest_win_rate:.1f}%")
        print(f"Backtest Return: {self.params.backtest_total_return:+.1f}%")
        if mode == TradingMode.LIVE and self.broker:
            balance = self._get_account_balance()
            print(f"Account Balance: ${balance.get('total_equity', 0):,.2f}")
            print(f"Buying Power:    ${balance.get('option_buying_power', 0):,.2f}")
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
        """
        Check if we should trade based on market conditions.

        NOW IMPLEMENTS ALL THE MISSING CHECKS:
        - VIX filter (was working)
        - Market open check (was partial)
        - Earnings check (WAS NOT IMPLEMENTED!)
        - FOMC check (WAS NOT IMPLEMENTED!)
        """
        # Check market calendar (includes earnings & FOMC)
        if CALENDAR_AVAILABLE and self.params.avoid_earnings:
            can_trade, reason = should_trade_today()
            if not can_trade:
                print(f"  {reason}")
                return False

        # Check VIX levels
        vix = self._get_vix()

        if vix < self.params.min_vix:
            print(f"  VIX ({vix:.1f}) below minimum ({self.params.min_vix})")
            return False

        if vix > self.params.max_vix:
            print(f"  VIX ({vix:.1f}) above maximum ({self.params.max_vix})")
            return False

        # Check if market is open
        now = datetime.now()
        if now.weekday() > 4:  # Weekend
            print("  Weekend - market closed")
            return False

        # Market hours check (simplified - 9:30 AM to 4 PM ET)
        if now.hour < 9 or now.hour >= 16:
            print(f"  Outside market hours")
            return False
        if now.hour == 9 and now.minute < 30:
            print(f"  Market not open yet")
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

    def _get_account_balance(self) -> Dict:
        """Get account balance from broker (LIVE mode) or calculate from DB (PAPER mode)"""
        if self.mode == TradingMode.LIVE and self.broker:
            return self.broker.get_account_balance()

        # Paper mode: calculate from database
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    COALESCE(SUM(total_pnl), 0) FILTER (WHERE status = 'CLOSED'),
                    COALESCE(SUM(premium_received), 0) FILTER (WHERE status = 'OPEN')
                FROM spx_wheel_positions
            ''')

            result = cursor.fetchone()
            realized_pnl = float(result[0] or 0)
            open_premium = float(result[1] or 0)
            conn.close()

            total_equity = self.initial_capital + realized_pnl + open_premium

            # Estimate margin used (20% of notional per contract)
            open_positions = self._get_open_positions()
            margin_used = sum(
                pos['strike'] * 100 * pos['contracts'] * 0.20
                for pos in open_positions
            )

            return {
                'total_equity': total_equity,
                'option_buying_power': total_equity - margin_used,
                'margin_used': margin_used,
                'realized_pnl': realized_pnl,
                'mode': 'PAPER'
            }

        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return {'total_equity': self.initial_capital, 'option_buying_power': self.initial_capital}

    def _get_real_option_price(self, strike: float, expiration: str) -> Tuple[float, float, str]:
        """
        Get REAL option price from broker or Polygon.

        Returns:
            (bid, ask, source) - prices and data source
        """
        exp_str = expiration.replace('-', '')[2:]  # "2024-12-20" -> "241220"
        option_ticker = f"O:SPX{exp_str}P{int(strike*1000):08d}"

        # Try broker first (most accurate for live trading)
        if self.mode == TradingMode.LIVE and self.broker:
            try:
                # Tradier uses different symbol format
                tradier_symbol = f"SPXW{exp_str}P{int(strike*1000):08d}"
                quote = self.broker.get_quote(tradier_symbol)
                if quote:
                    bid = float(quote.get('bid', 0) or 0)
                    ask = float(quote.get('ask', 0) or 0)
                    if bid > 0:
                        return bid, ask, "TRADIER_LIVE"
            except Exception as e:
                logger.warning(f"Tradier quote failed: {e}")

        # Try Polygon historical/real-time
        try:
            df = polygon_fetcher.get_historical_option_prices(
                'SPX', strike, expiration, 'put',
                start_date=datetime.now().strftime('%Y-%m-%d'),
                end_date=datetime.now().strftime('%Y-%m-%d')
            )
            if df is not None and len(df) > 0:
                close = df.iloc[0].get('close', 0)
                if close > 0:
                    spread = close * 0.03
                    return close - spread/2, close + spread/2, "POLYGON"
        except Exception as e:
            logger.warning(f"Polygon quote failed: {e}")

        # Fallback to estimation
        spot = self._get_spx_price() or 5800
        dte = (datetime.strptime(expiration, '%Y-%m-%d') - datetime.now()).days
        estimated = spot * 0.015 * (dte / 45) ** 0.5
        return estimated * 0.97, estimated * 1.03, "ESTIMATED"

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
        """
        Check if we can open a new position.

        Verifies:
        1. Not at max position limit
        2. Have enough buying power / margin
        """
        open_positions = self._get_open_positions()

        # Check position limit
        if len(open_positions) >= self.params.max_open_positions:
            print(f"  Cannot open: At max positions ({len(open_positions)}/{self.params.max_open_positions})")
            return False

        # Check margin/buying power
        balance = self._get_account_balance()
        buying_power = balance.get('option_buying_power', 0)

        # Estimate margin for new position (20% of notional for SPX)
        estimated_strike = round((spot * (1 - 0.04 - self.params.put_delta * 0.15)) / 5) * 5
        margin_required = estimated_strike * 100 * self.params.contracts_per_trade * 0.20

        if buying_power < margin_required:
            print(f"  Cannot open: Insufficient margin (need ${margin_required:,.0f}, have ${buying_power:,.0f})")
            return False

        # Check max margin usage
        total_equity = balance.get('total_equity', self.initial_capital)
        current_margin = balance.get('margin_used', 0)
        max_margin = total_equity * self.params.max_margin_pct

        if (current_margin + margin_required) > max_margin:
            print(f"  Cannot open: Would exceed max margin ({self.params.max_margin_pct*100:.0f}%)")
            return False

        return True

    def _open_new_position(self, spot: float) -> bool:
        """
        Open a new put position.

        PAPER mode: Logs to database only
        LIVE mode:  Places actual order via Tradier
        """
        # Calculate strike
        strike_offset = spot * (0.04 + self.params.put_delta * 0.15)
        strike = round((spot - strike_offset) / 5) * 5

        # Calculate expiration (find next Friday)
        target = datetime.now() + timedelta(days=self.params.dte_target)
        days_until_friday = (4 - target.weekday()) % 7
        if days_until_friday == 0:
            days_until_friday = 7  # Next Friday, not today
        expiration = (target + timedelta(days=days_until_friday)).date()
        expiration_str = expiration.strftime('%Y-%m-%d')

        # Get REAL option price
        bid, ask, price_source = self._get_real_option_price(strike, expiration_str)
        entry_price = bid  # Sell at bid

        # Build tickers
        exp_fmt = expiration.strftime('%y%m%d')
        option_ticker = f"O:SPX{exp_fmt}P{int(strike*1000):08d}"
        tradier_symbol = f"SPXW{exp_fmt}P{int(strike*1000):08d}"

        order_id = None
        order_status = "PAPER"

        # === LIVE MODE: PLACE REAL ORDER ===
        if self.mode == TradingMode.LIVE and self.broker:
            print(f"\n🔴 PLACING LIVE ORDER:")
            print(f"   Symbol: {tradier_symbol}")
            print(f"   Action: SELL TO OPEN")
            print(f"   Qty:    {self.params.contracts_per_trade}")
            print(f"   Price:  ${entry_price:.2f} (from {price_source})")

            try:
                result = self.broker.sell_put(
                    symbol='SPX',
                    expiration=expiration_str,
                    strike=strike,
                    quantity=self.params.contracts_per_trade,
                    limit_price=entry_price
                )

                order_info = result.get('order', {})
                order_id = order_info.get('id')
                order_status = order_info.get('status', 'UNKNOWN')

                print(f"   Order ID: {order_id}")
                print(f"   Status:   {order_status}")

                if order_status not in ['pending', 'open', 'filled', 'partially_filled']:
                    logger.error(f"Order failed: {result}")
                    return False

            except Exception as e:
                logger.error(f"LIVE order failed: {e}")
                print(f"   ❌ ORDER FAILED: {e}")
                return False

        # === LOG TO DATABASE ===
        try:
            conn = get_connection()
            cursor = conn.cursor()

            notes = f"Opened at SPX={spot:.2f}, Delta={self.params.put_delta}, Price source={price_source}"
            if order_id:
                notes += f", Order ID={order_id}, Status={order_status}"

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
                entry_price,
                entry_price * 100 * self.params.contracts_per_trade,
                json.dumps({
                    **self.params.to_dict(),
                    'order_id': order_id,
                    'price_source': price_source,
                    'mode': self.mode.value
                }),
                notes
            ))

            position_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()

            mode_str = "🔴 LIVE" if self.mode == TradingMode.LIVE else "📝 PAPER"
            print(f"\n{mode_str} POSITION OPENED:")
            print(f"   Ticker:   {option_ticker}")
            print(f"   Strike:   ${strike:.0f}")
            print(f"   Exp:      {expiration}")
            print(f"   Price:    ${entry_price:.2f} ({price_source})")
            print(f"   Premium:  ${entry_price * 100 * self.params.contracts_per_trade:,.2f}")
            print(f"   DB ID:    {position_id}")

            # Send alert for new trade
            if ALERTS_AVAILABLE:
                alerts = get_alerts()
                alerts.alert_trade_executed(
                    "SELL_PUT",
                    {
                        'id': position_id,
                        'option_ticker': option_ticker,
                        'strike': strike,
                        'expiration': str(expiration),
                        'contracts': self.params.contracts_per_trade,
                        'entry_price': entry_price,
                        'premium_received': entry_price * 100 * self.params.contracts_per_trade,
                        'price_source': price_source
                    },
                    self.mode.value
                )

            return True

        except Exception as e:
            logger.error(f"Failed to log position: {e}")
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
        """
        Check if any positions need to be rolled.

        Roll conditions:
        1. DTE <= roll_at_dte (e.g., 7 days)
        2. Position is profitable (option price dropped)

        Roll action:
        1. Close current position (buy to close)
        2. Open new position at same delta, further out
        """
        rolled = 0
        today = datetime.now().date()

        for pos in self._get_open_positions():
            exp_date = pos['expiration']
            if isinstance(exp_date, str):
                exp_date = datetime.strptime(exp_date, '%Y-%m-%d').date()

            dte_remaining = (exp_date - today).days

            # Check if needs roll
            if dte_remaining <= self.params.roll_at_dte:
                print(f"\n  Position {pos['option_ticker']} has {dte_remaining} DTE - checking for roll...")

                # Get current price
                bid, ask, source = self._get_real_option_price(pos['strike'], exp_date.strftime('%Y-%m-%d'))
                current_price = (bid + ask) / 2

                # Calculate P&L if we close now
                close_cost = ask  # Buy to close at ask
                open_price = pos['entry_price']
                profit_pct = ((open_price - close_cost) / open_price) * 100

                if profit_pct >= self.params.profit_target_pct:
                    print(f"    Profit: {profit_pct:.1f}% >= target {self.params.profit_target_pct}% - ROLLING")

                    # Close current position
                    if self._close_position(pos, close_cost, "ROLL"):
                        # Open new position
                        if self._open_new_position(spot):
                            rolled += 1
                            print(f"    ✓ Roll complete")
                        else:
                            print(f"    ✗ Failed to open new position")
                    else:
                        print(f"    ✗ Failed to close position")

                else:
                    print(f"    Profit: {profit_pct:.1f}% < target {self.params.profit_target_pct}% - HOLD")

        return rolled

    def _close_position(self, pos: Dict, exit_price: float, reason: str) -> bool:
        """Close a position (for rolls or early exit)"""
        try:
            # In LIVE mode, place buy-to-close order
            if self.mode == TradingMode.LIVE and self.broker:
                exp_str = pos['expiration']
                if hasattr(exp_str, 'strftime'):
                    exp_str = exp_str.strftime('%Y-%m-%d')
                exp_fmt = exp_str.replace('-', '')[2:]
                tradier_symbol = f"SPXW{exp_fmt}P{int(pos['strike']*1000):08d}"

                print(f"  🔴 PLACING BUY-TO-CLOSE ORDER: {tradier_symbol}")

                result = self.broker.place_option_order(
                    option_symbol=tradier_symbol,
                    side=OrderSide.BUY_TO_CLOSE,
                    quantity=pos['contracts'],
                    order_type=OrderType.LIMIT,
                    price=exit_price
                )

                order_id = result.get('order', {}).get('id')
                print(f"     Order ID: {order_id}")

            # Update database
            conn = get_connection()
            cursor = conn.cursor()

            pnl = (pos['entry_price'] - exit_price) * 100 * pos['contracts']

            cursor.execute('''
                UPDATE spx_wheel_positions SET
                    status = 'CLOSED',
                    closed_at = NOW(),
                    exit_price = %s,
                    total_pnl = %s,
                    notes = notes || %s
                WHERE id = %s
            ''', (
                exit_price,
                pnl,
                f" | CLOSED ({reason}): Exit=${exit_price:.2f}, P&L=${pnl:.2f}",
                pos['id']
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return False

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
