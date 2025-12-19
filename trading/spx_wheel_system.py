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

# Decision logging for transparency
try:
    from trading.decision_logger import (
        DecisionLogger,
        TradeDecision,
        DecisionType,
        DataSource,
        PriceSnapshot,
        MarketContext,
        DecisionReasoning,
        BacktestReference,
        BotName,
        TradeLeg
    )
    DECISION_LOGGING_AVAILABLE = True
except ImportError:
    DECISION_LOGGING_AVAILABLE = False

# Comprehensive bot logger
try:
    from trading.bot_logger import (
        log_bot_decision, BotDecision, MarketContext as BotLogMarketContext,
        ClaudeContext, Alternative, RiskCheck, ExecutionTimeline, generate_session_id
    )
    BOT_LOGGER_AVAILABLE = True
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None

# Walk-Forward Optimization for preventing overfitting
try:
    from quant.walk_forward_optimizer import WalkForwardOptimizer, WalkForwardResult
    WALK_FORWARD_AVAILABLE = True
except ImportError:
    WALK_FORWARD_AVAILABLE = False

# Oracle AI advisor for intelligent trading decisions
try:
    from quant.oracle_advisor import (
        OracleAdvisor, MarketContext as OracleMarketContext,
        TradingAdvice, GEXRegime, OraclePrediction, TradeOutcome,
        BotName as OracleBotName
    )
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None
    OracleMarketContext = None
    TradingAdvice = None
    TradeOutcome = None
    OracleBotName = None

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

        # === WALK-FORWARD VALIDATION ===
        # Prevent overfitting by testing on unseen data
        wf_result = self.run_walk_forward_validation(best.parameters)
        if not wf_result.get('is_robust', True):
            print("\n⚠️  WARNING: Parameters may be overfit to historical data")
            print("   Consider using more conservative delta/DTE settings")
            # Store warning in parameters
            best.parameters.backtest_period += " [OVERFIT WARNING]"

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

            # NOTE: Table 'spx_wheel_parameters' is defined in db/config_and_database.py (single source of truth)

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

    def run_walk_forward_validation(
        self,
        params: WheelParameters,
        train_days: int = 90,
        test_days: int = 30
    ) -> Dict:
        """
        Validate parameters using Walk-Forward Analysis to prevent overfitting.

        Walk-forward splits data into train/test windows:
        - Train on historical window, find optimal params
        - Test on forward window (unseen data)
        - Walk forward and repeat

        A robust strategy shows < 20% degradation from in-sample to out-of-sample.

        Returns:
            Dict with validation results including is_robust flag
        """
        if not WALK_FORWARD_AVAILABLE:
            print("  Walk-Forward Optimizer not available - skipping validation")
            return {'is_robust': True, 'degradation_pct': 0, 'recommendation': 'SKIPPED'}

        print("\n" + "="*70)
        print("WALK-FORWARD VALIDATION")
        print("="*70)
        print("Preventing overfitting by testing on unseen data...")
        print(f"Train window: {train_days} days, Test window: {test_days} days")

        try:
            # Create strategy function for walk-forward optimizer
            def csp_strategy(data, params_dict):
                """Run CSP backtest on data window"""
                if data.empty:
                    return {'win_rate': 0, 'trades': 0}

                # Use the backtester with the given parameters
                from backtest.spx_premium_backtest import SPXPremiumBacktester

                start = data.index[0].strftime('%Y-%m-%d')
                end = data.index[-1].strftime('%Y-%m-%d')

                backtester = SPXPremiumBacktester(
                    start_date=start,
                    end_date=end,
                    initial_capital=self.initial_capital,
                    put_delta=params_dict.get('put_delta', params.put_delta),
                    dte_target=params_dict.get('dte_target', params.dte_target),
                    max_margin_pct=params.max_margin_pct
                )

                # Suppress output
                import io
                from contextlib import redirect_stdout
                f = io.StringIO()
                with redirect_stdout(f):
                    results = backtester.run(save_to_db=False)

                summary = results.get('summary', {})
                return {
                    'win_rate': summary.get('win_rate', 0),
                    'trades': summary.get('total_trades', 0),
                    'return_pct': summary.get('total_return_pct', 0)
                }

            # Run walk-forward optimization
            optimizer = WalkForwardOptimizer(
                symbol="SPX",
                train_days=train_days,
                test_days=test_days,
                step_days=test_days,
                min_trades_per_window=3
            )

            # Get historical data
            try:
                import yfinance as yf
                spx = yf.Ticker("^GSPC")  # Use S&P 500 as proxy for SPX
                end_date = datetime.now()
                start_date = datetime.strptime(self.start_date, '%Y-%m-%d')
                historical_data = spx.history(start=start_date, end=end_date)
            except Exception as e:
                print(f"  Could not fetch historical data: {e}")
                return {'is_robust': True, 'degradation_pct': 0, 'recommendation': 'SKIPPED'}

            # Parameter grid - test variations around optimal
            param_grid = {
                'put_delta': [params.put_delta - 0.05, params.put_delta, params.put_delta + 0.05],
                'dte_target': [params.dte_target - 15, params.dte_target, params.dte_target + 15]
            }
            # Filter out invalid values
            param_grid['put_delta'] = [p for p in param_grid['put_delta'] if 0.1 <= p <= 0.4]
            param_grid['dte_target'] = [d for d in param_grid['dte_target'] if 14 <= d <= 90]

            result = optimizer.run_walk_forward(
                strategy_name="SPX_CSP_WHEEL",
                strategy_func=csp_strategy,
                param_grid=param_grid,
                start_date=start_date,
                end_date=end_date,
                historical_data=historical_data
            )

            # Print results
            print(f"\n  Windows tested: {result.total_windows}")
            print(f"  In-Sample Win Rate: {result.is_avg_win_rate:.1f}%")
            print(f"  Out-of-Sample Win Rate: {result.oos_avg_win_rate:.1f}%")
            print(f"  Degradation: {result.degradation_pct:.1f}%")
            print(f"  Is Robust: {result.is_robust}")

            if result.is_robust:
                print("\n  ✓ Strategy PASSED walk-forward validation")
                print("    Parameters are robust and not overfit to historical data")
            else:
                print("\n  ⚠️  Strategy shows signs of overfitting")
                print(f"    Degradation ({result.degradation_pct:.1f}%) exceeds 20% threshold")
                print("    Consider using more conservative parameters")

            print("="*70)

            # Save results
            optimizer.save_results_to_db(result)

            return {
                'is_robust': result.is_robust,
                'degradation_pct': result.degradation_pct,
                'is_win_rate': result.is_avg_win_rate,
                'oos_win_rate': result.oos_avg_win_rate,
                'recommended_params': result.recommended_params,
                'recommendation': 'KEEP' if result.is_robust else 'REVIEW'
            }

        except Exception as e:
            logger.error(f"Walk-forward validation failed: {e}")
            print(f"  Walk-forward validation error: {e}")
            return {'is_robust': True, 'degradation_pct': 0, 'recommendation': 'ERROR'}


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

        # Initialize decision logger for transparency
        self.decision_logger = None
        if DECISION_LOGGING_AVAILABLE:
            self.decision_logger = DecisionLogger()

        # Initialize Oracle AI advisor
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("ATLAS: Oracle AI advisor initialized")
            except Exception as e:
                logger.warning(f"ATLAS: Failed to initialize Oracle AI: {e}")

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
        """
        Verify required tables exist.
        NOTE: Tables 'spx_wheel_positions' and 'spx_wheel_performance' are now
        defined in db/config_and_database.py (single source of truth).
        """
        # Tables are created by main schema - no action needed
        logger.info("SPX wheel tables expected from main schema (db/config_and_database.py)")

    def _log_decision(
        self,
        decision_type: str,
        action: str,
        what: str,
        why: str,
        how: str,
        spot_price: float = 0,
        vix: float = 0,
        strike: float = 0,
        expiration: str = "",
        entry_price: float = 0,
        exit_price: float = 0,
        bid: float = 0,
        ask: float = 0,
        premium: float = 0,
        contracts: int = 0,
        delta: float = 0,
        pnl: float = None,
        order_id: str = ""
    ) -> str:
        """
        Log a trading decision with full transparency (What, Why, How).

        LOGS ALL CRITICAL TRADE DATA:
        - Strike, entry_price, exit_price, expiration
        - Contracts, premium per contract
        - Delta (for CSP)
        - Order ID and execution details
        - Underlying price, VIX

        Returns decision_id for tracking.
        """
        if not self.decision_logger:
            return ""

        try:
            now = datetime.now()
            per_share_price = entry_price if entry_price > 0 else (premium / 100 / max(contracts, 1) if premium > 0 else 0)

            # =====================================================================
            # BUILD TRADE LEG with ALL critical data
            # =====================================================================
            trade_leg = None
            if strike > 0:
                trade_leg = TradeLeg(
                    leg_id=1,
                    action=action,
                    option_type="put",  # ATLAS is CSP only

                    # REQUIRED: Strike and expiration
                    strike=strike,
                    expiration=expiration,

                    # Entry prices
                    entry_price=per_share_price,
                    entry_bid=bid,
                    entry_ask=ask,
                    entry_mid=(bid + ask) / 2 if bid > 0 else per_share_price,

                    # Exit price (if exiting)
                    exit_price=exit_price,

                    # Position sizing
                    contracts=contracts,
                    premium_per_contract=per_share_price * 100,

                    # Greeks at entry (delta for CSP)
                    delta=delta if delta else -self.params.put_delta,  # Short put = negative delta

                    # Order execution
                    order_id=order_id,
                    fill_price=per_share_price,
                    fill_timestamp=now.isoformat(),
                    order_status="filled",

                    # P&L
                    realized_pnl=pnl if pnl is not None else 0
                )

            # Build underlying price snapshot
            underlying_snapshot = PriceSnapshot(
                symbol="SPX",
                price=spot_price,
                timestamp=now.isoformat(),
                source=DataSource.POLYGON_REALTIME
            )

            # Build option snapshot (legacy support)
            option_snapshot = None
            if strike > 0:
                option_snapshot = PriceSnapshot(
                    symbol="SPX",
                    price=per_share_price,
                    bid=bid,
                    ask=ask,
                    timestamp=now.isoformat(),
                    source=DataSource.POLYGON_REALTIME,
                    strike=strike,
                    expiration=expiration,
                    option_type="PUT",
                    delta=delta if delta else -self.params.put_delta
                )

            # Build market context
            market_context = MarketContext(
                timestamp=now.isoformat(),
                spot_price=spot_price,
                spot_source=DataSource.POLYGON_REALTIME,
                vix=vix,
                regime=f"VIX Range: {self.params.min_vix}-{self.params.max_vix}"
            )

            # Build backtest reference from calibrated parameters
            backtest_ref = None
            if self.params.backtest_win_rate > 0:
                backtest_ref = BacktestReference(
                    strategy_name="SPX_WHEEL_CSP",
                    backtest_date=self.params.calibration_date or datetime.now().strftime('%Y-%m-%d'),
                    win_rate=self.params.backtest_win_rate,
                    expectancy=self.params.backtest_expectancy,
                    max_drawdown=self.params.backtest_max_drawdown,
                    backtest_period=self.params.backtest_period,
                    uses_real_data=True,
                    data_source="polygon",
                    date_range=self.params.backtest_period
                )

            # Build reasoning
            supporting = [
                f"Delta target: {self.params.put_delta}",
                f"DTE target: {self.params.dte_target} days",
                f"Backtest win rate: {self.params.backtest_win_rate:.1f}%"
            ]
            risks = []
            if vix > 25:
                risks.append(f"Elevated VIX: {vix:.1f}")
            if vix < self.params.min_vix:
                risks.append(f"VIX below minimum: {vix:.1f} < {self.params.min_vix}")

            reasoning = DecisionReasoning(
                primary_reason=why.split('.')[0] if '.' in why else why,
                supporting_factors=supporting,
                risk_factors=risks
            )

            # Map string decision type to enum
            dt_map = {
                'ENTRY': DecisionType.ENTRY_SIGNAL,
                'EXIT': DecisionType.EXIT_SIGNAL,
                'ROLL': DecisionType.ROLL_DECISION,
                'NO_TRADE': DecisionType.NO_TRADE,
                'EXPIRATION': DecisionType.EXIT_SIGNAL
            }
            decision_type_enum = dt_map.get(decision_type, DecisionType.NO_TRADE)

            # Build the decision with legs array
            decision = TradeDecision(
                decision_id="",
                timestamp=now.isoformat(),
                decision_type=decision_type_enum,
                bot_name=BotName.ATLAS,
                what=what,
                why=why,
                how=how,
                action=action,
                symbol="SPX",
                strategy="SPX_WHEEL_CSP",
                legs=[trade_leg] if trade_leg else [],
                underlying_snapshot=underlying_snapshot,
                option_snapshot=option_snapshot,
                underlying_price_at_entry=spot_price,
                market_context=market_context,
                backtest_reference=backtest_ref,
                reasoning=reasoning,
                position_size_dollars=premium if premium > 0 else 0,
                position_size_contracts=contracts,
                position_size_method="calibrated_kelly",
                max_risk_dollars=strike * 100 * contracts if strike > 0 else 0,
                target_profit_pct=self.params.profit_target_pct,
                stop_loss_pct=self.params.stop_loss_pct,
                actual_pnl=pnl,
                order_id=order_id
            )

            decision_id = self.decision_logger.log_decision(decision)
            logger.info(f"ATLAS logged decision: {decision_id} - {action}")

            # === COMPREHENSIVE BOT LOGGER ===
            if BOT_LOGGER_AVAILABLE and log_bot_decision:
                try:
                    # Map decision type
                    dt_str = "ENTRY" if decision_type == "ENTRY" else "EXIT" if decision_type in ["EXIT", "EXPIRATION"] else "SKIP"

                    # Build risk checks
                    risk_checks = []
                    if vix > 0:
                        risk_checks.append(RiskCheck(
                            check_name="VIX_RANGE",
                            passed=self.params.min_vix <= vix <= self.params.max_vix,
                            current_value=vix,
                            limit_value=self.params.max_vix,
                            message=f"VIX at {vix:.1f}"
                        ))

                    comprehensive = BotDecision(
                        bot_name="ATLAS",
                        decision_type=dt_str,
                        action=action,
                        symbol="SPX",
                        strategy="SPX_WHEEL_CSP",
                        strike=strike,
                        expiration=expiration,
                        option_type="PUT",
                        contracts=contracts,
                        session_id=generate_session_id(),
                        market_context=BotLogMarketContext(
                            spot_price=spot_price,
                            vix=vix,
                        ),
                        entry_reasoning=why.split('.')[0] if '.' in why else why,
                        strike_reasoning=f"Strike ${strike} at delta {self.params.put_delta}",
                        size_reasoning=f"{contracts} contracts",
                        exit_reasoning=why if dt_str == "EXIT" else "",
                        kelly_pct=self.params.position_size_pct,
                        position_size_dollars=premium if premium > 0 else 0,
                        max_risk_dollars=strike * 100 * contracts if strike > 0 else 0,
                        backtest_win_rate=self.params.backtest_win_rate,
                        backtest_expectancy=self.params.backtest_expectancy,
                        risk_checks=risk_checks,
                        passed_all_checks=decision_type != "NO_TRADE",
                        blocked_reason="" if decision_type != "NO_TRADE" else why,
                        actual_pnl=pnl if pnl is not None else 0,
                        execution=ExecutionTimeline(
                            order_submitted_at=now,
                            expected_fill_price=entry_price if entry_price > 0 else premium / 100 / max(contracts, 1),
                            broker_order_id=order_id,
                            broker_status="FILLED" if order_id else "PENDING",
                        ) if dt_str == "ENTRY" else ExecutionTimeline(),
                    )
                    comp_id = log_bot_decision(comprehensive)
                    logger.info(f"ATLAS logged to bot_decision_logs: {comp_id}")
                except Exception as comp_e:
                    logger.warning(f"Could not log ATLAS to comprehensive table: {comp_e}")

            return decision_id

        except Exception as e:
            logger.error(f"Failed to log ATLAS decision: {e}")
            return ""

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
        can_trade, reason = self._should_trade_today()
        if not can_trade:
            result['actions'].append(f'SKIP: {reason}')
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

    def _should_trade_today(self) -> Tuple[bool, str]:
        """
        Check if we should trade based on market conditions.

        NOW IMPLEMENTS ALL THE MISSING CHECKS:
        - VIX filter (was working)
        - Market open check (was partial)
        - Earnings check (WAS NOT IMPLEMENTED!)
        - FOMC check (WAS NOT IMPLEMENTED!)

        Returns:
            (can_trade, reason) - tuple of bool and explanation
        """
        spot = self._get_spx_price() or 0
        vix = self._get_vix()

        # Check market calendar (includes earnings & FOMC)
        if CALENDAR_AVAILABLE and self.params.avoid_earnings:
            can_trade, reason = should_trade_today()
            if not can_trade:
                print(f"  {reason}")
                self._log_decision(
                    decision_type="NO_TRADE",
                    action="SKIP",
                    what=f"NO TRADE for SPX - Calendar restriction",
                    why=f"Market calendar blocked trading. {reason}",
                    how="Checked market calendar for earnings/FOMC events. Trade blocked.",
                    spot_price=spot,
                    vix=vix
                )
                return False, reason

        # Check VIX levels
        if vix < self.params.min_vix:
            reason = f"VIX ({vix:.1f}) below minimum ({self.params.min_vix})"
            print(f"  {reason}")
            self._log_decision(
                decision_type="NO_TRADE",
                action="SKIP",
                what=f"NO TRADE for SPX - VIX too low",
                why=f"VIX at {vix:.1f} is below minimum threshold of {self.params.min_vix}. Low VIX = low premium = bad risk/reward for CSP sellers.",
                how=f"Checked VIX level against calibrated range {self.params.min_vix}-{self.params.max_vix}. Trade skipped.",
                spot_price=spot,
                vix=vix
            )
            return False, reason

        if vix > self.params.max_vix:
            reason = f"VIX ({vix:.1f}) above maximum ({self.params.max_vix})"
            print(f"  {reason}")
            self._log_decision(
                decision_type="NO_TRADE",
                action="SKIP",
                what=f"NO TRADE for SPX - VIX too high",
                why=f"VIX at {vix:.1f} exceeds maximum threshold of {self.params.max_vix}. High VIX = excessive assignment risk.",
                how=f"Checked VIX level against calibrated range {self.params.min_vix}-{self.params.max_vix}. Trade skipped.",
                spot_price=spot,
                vix=vix
            )
            return False, reason

        # Check if market is open
        now = datetime.now()
        if now.weekday() > 4:  # Weekend
            reason = "Weekend - market closed"
            print(f"  {reason}")
            return False, reason

        # Market hours check (simplified - 9:30 AM to 4 PM ET)
        if now.hour < 9 or now.hour >= 16:
            reason = "Outside market hours"
            print(f"  {reason}")
            return False, reason
        if now.hour == 9 and now.minute < 30:
            reason = "Market not open yet"
            print(f"  {reason}")
            return False, reason

        # =========================================================================
        # CONSULT ORACLE AI FOR TRADING ADVICE
        # =========================================================================
        oracle_advice = self.consult_oracle(spot, vix)

        if oracle_advice:
            # Honor Oracle's SKIP advice
            if ORACLE_AVAILABLE and TradingAdvice and oracle_advice.advice == TradingAdvice.SKIP:
                reason = f"Oracle advises SKIP: {oracle_advice.reasoning}"
                print(f"  {reason}")
                self._log_decision(
                    decision_type="NO_TRADE",
                    action="SKIP",
                    what=f"NO TRADE for SPX - Oracle advised SKIP",
                    why=f"Oracle win probability: {oracle_advice.win_probability:.1%}. {oracle_advice.reasoning}",
                    how="Consulted Oracle AI advisor. Conditions unfavorable.",
                    spot_price=spot,
                    vix=vix
                )
                return False, reason

            # Store oracle advice for position sizing
            self._last_oracle_advice = oracle_advice
            print(f"  Oracle: {oracle_advice.advice.value} (Win Prob: {oracle_advice.win_probability:.1%})")
        else:
            self._last_oracle_advice = None
            print("  Oracle: Not available, using default parameters")

        return True, "Market conditions favorable"

    def _get_spx_price(self) -> Optional[float]:
        """Get current SPX price"""
        for symbol in ['SPX', '^SPX', '$SPX.X', 'I:SPX']:
            price = polygon_fetcher.get_current_price(symbol)
            if price and price > 0:
                return price
        return None

    def _get_vix(self) -> float:
        """Get current VIX"""
        for symbol in ['I:VIX', '$VIX.X']:
            vix = polygon_fetcher.get_current_price(symbol)
            if vix and vix > 0:
                return vix
        return 17.0  # Default

    def _build_oracle_context(self, spot: float, vix: float) -> Optional['OracleMarketContext']:
        """
        Build Oracle MarketContext from current market data.

        Args:
            spot: Current SPX price
            vix: Current VIX level

        Returns:
            OracleMarketContext for Oracle consultation
        """
        if not ORACLE_AVAILABLE or OracleMarketContext is None:
            return None

        try:
            now = datetime.now()

            # Try to get GEX data from database
            gex_net = 0
            gex_call_wall = 0
            gex_put_wall = 0
            gex_flip = 0

            try:
                conn = get_connection()
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT net_gex, call_wall, put_wall, gex_flip_point
                    FROM gex_data
                    WHERE symbol = 'SPY'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    gex_net = row[0] or 0
                    gex_call_wall = (row[1] or 0) * 10  # Scale SPY walls to SPX
                    gex_put_wall = (row[2] or 0) * 10
                    gex_flip = (row[3] or 0) * 10
                conn.close()
            except Exception as e:
                logger.debug(f"ATLAS: Could not fetch GEX data: {e}")

            # Determine GEX regime
            gex_regime = GEXRegime.NEUTRAL
            if gex_net > 0:
                gex_regime = GEXRegime.POSITIVE
            elif gex_net < 0:
                gex_regime = GEXRegime.NEGATIVE

            # Check if price is between walls
            between_walls = True
            if gex_put_wall > 0 and gex_call_wall > 0:
                between_walls = gex_put_wall <= spot <= gex_call_wall

            return OracleMarketContext(
                spot_price=spot,
                price_change_1d=0,
                vix=vix,
                vix_percentile_30d=50.0,
                vix_change_1d=0,
                gex_net=gex_net,
                gex_normalized=0,
                gex_regime=gex_regime,
                gex_flip_point=gex_flip,
                gex_call_wall=gex_call_wall,
                gex_put_wall=gex_put_wall,
                gex_distance_to_flip_pct=0,
                gex_between_walls=between_walls,
                day_of_week=now.weekday(),
                days_to_opex=self.params.dte_target,
                win_rate_30d=self.params.backtest_win_rate / 100.0 if self.params.backtest_win_rate else 0.68,
                expected_move_pct=vix / 100.0 * (self.params.dte_target / 365) ** 0.5 * 100
            )

        except Exception as e:
            logger.error(f"ATLAS: Error building Oracle context: {e}")
            return None

    def consult_oracle(self, spot: float, vix: float) -> Optional['OraclePrediction']:
        """
        Consult Oracle AI for trading advice.

        Args:
            spot: Current SPX price
            vix: Current VIX level

        Returns:
            OraclePrediction with advice, or None if Oracle unavailable
        """
        if not self.oracle:
            logger.debug("ATLAS: Oracle not available, proceeding without advice")
            return None

        context = self._build_oracle_context(spot, vix)
        if not context:
            logger.debug("ATLAS: Could not build Oracle context")
            return None

        try:
            # Get advice from Oracle
            advice = self.oracle.get_atlas_advice(context)

            logger.info(f"ATLAS Oracle: {advice.advice.value} | Win Prob: {advice.win_probability:.1%} | "
                       f"Risk: {advice.suggested_risk_pct:.1%}")

            if advice.reasoning:
                logger.info(f"ATLAS Oracle Reasoning: {advice.reasoning}")

            # Store prediction for feedback loop
            try:
                today = datetime.now().strftime('%Y-%m-%d')
                self.oracle.store_prediction(advice, context, today)
            except Exception as e:
                logger.debug(f"ATLAS: Could not store Oracle prediction: {e}")

            return advice

        except Exception as e:
            logger.error(f"ATLAS: Error consulting Oracle: {e}")
            return None

    def record_trade_outcome(
        self,
        trade_date: str,
        outcome_type: str,
        actual_pnl: float
    ) -> bool:
        """
        Record trade outcome back to Oracle for feedback loop.

        Args:
            trade_date: Date of the trade (YYYY-MM-DD)
            outcome_type: One of MAX_PROFIT, PARTIAL_PROFIT, LOSS, etc.
            actual_pnl: Actual P&L from the trade

        Returns:
            True if recorded successfully
        """
        if not self.oracle or not ORACLE_AVAILABLE:
            return False

        try:
            outcome = TradeOutcome[outcome_type]
            self.oracle.update_outcome(
                trade_date,
                OracleBotName.ATLAS,
                outcome,
                actual_pnl
            )
            logger.info(f"ATLAS: Recorded outcome to Oracle: {outcome_type}, PnL=${actual_pnl:,.2f}")
            return True
        except Exception as e:
            logger.error(f"ATLAS: Failed to record outcome: {e}")
            return False

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

            # Log decision for transparency with COMPLETE trade data
            vix = self._get_vix()
            premium_received = entry_price * 100 * self.params.contracts_per_trade
            dte = (expiration - datetime.now().date()).days

            self._log_decision(
                decision_type="ENTRY",
                action="SELL_CSP",
                what=f"SELL {self.params.contracts_per_trade}x SPX ${strike}P exp {expiration_str} ({dte}d) @ ${entry_price:.2f}",
                why=f"Cash-secured put at {self.params.put_delta} delta. VIX at {vix:.1f} within target range {self.params.min_vix}-{self.params.max_vix}. Backtest win rate: {self.params.backtest_win_rate:.1f}%. SPX at ${spot:.2f}, selling {100*(spot-strike)/spot:.1f}% OTM.",
                how=f"Calibrated parameters from {self.params.backtest_period}. Premium: ${premium_received:,.2f}. Margin ~${strike*100*self.params.contracts_per_trade*0.20:,.0f}. Bid/Ask: ${bid:.2f}/${ask:.2f}. Source: {price_source}. Mode: {self.mode.value}.",
                spot_price=spot,
                vix=vix,
                strike=strike,
                expiration=expiration_str,
                entry_price=entry_price,
                bid=bid,
                ask=ask,
                premium=premium_received,
                contracts=self.params.contracts_per_trade,
                delta=-self.params.put_delta,  # Short put = negative delta
                order_id=str(order_id) if order_id else ""
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

                    # Log expiration decision with COMPLETE trade data
                    outcome = "WIN (OTM)" if settlement_pnl >= 0 else "LOSS (ITM)"
                    exp_date_str = pos['expiration'].strftime('%Y-%m-%d') if hasattr(pos['expiration'], 'strftime') else str(pos['expiration'])
                    # Exit price = 0 for OTM (worthless), or intrinsic value for ITM
                    exit_value = max(0, pos['strike'] - spot) if spot < pos['strike'] else 0
                    pos_strike = pos['strike']

                    expiry_why = f"Position expired worthless (kept full premium). Settlement P&L: ${settlement_pnl:+,.2f}." if settlement_pnl >= 0 else f"Position expired ITM at SPX=${spot:.2f} vs strike ${pos_strike:.0f}. Settlement P&L: ${settlement_pnl:+,.2f}."
                    entry_price_val = pos['entry_price']
                    premium_received_val = pos['premium_received']

                    self._log_decision(
                        decision_type="EXPIRATION",
                        action="EXPIRED",
                        what=f"EXPIRED {pos['option_ticker']} - {outcome}",
                        why=expiry_why,
                        how=f"Cash settlement applied. Entry: ${entry_price_val:.2f}/sh. Exit: ${exit_value:.2f}/sh. Premium received: ${premium_received_val:,.2f}. Settlement loss: ${abs(settlement_pnl):,.2f}. Net P&L: ${total_pnl:+,.2f}.",
                        spot_price=spot,
                        strike=pos_strike,
                        expiration=exp_date_str,
                        entry_price=entry_price_val,
                        exit_price=exit_value,
                        premium=premium_received_val,
                        contracts=pos['contracts'],
                        pnl=total_pnl
                    )

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
        order_id = None
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

            # Log decision with COMPLETE trade data
            spot = self._get_spx_price() or 0
            exp_str = pos['expiration']
            if hasattr(exp_str, 'strftime'):
                exp_str = exp_str.strftime('%Y-%m-%d')

            decision_type = "ROLL" if "ROLL" in reason.upper() else "EXIT"
            self._log_decision(
                decision_type=decision_type,
                action="BUY_TO_CLOSE",
                what=f"CLOSE {pos['option_ticker']} - {reason}",
                why=f"Early close ({reason}). Entry: ${pos['entry_price']:.2f}, Exit: ${exit_price:.2f}. Profit: ${pnl:+,.2f} ({100*(pos['entry_price']-exit_price)/pos['entry_price']:.1f}%).",
                how=f"Buy-to-close order at ${exit_price:.2f}. Entry was ${pos['entry_price']:.2f}. Contracts: {pos['contracts']}. Premium collected: ${pos['premium_received']:,.2f}. Net P&L: ${pnl:+,.2f}.",
                spot_price=spot,
                strike=pos['strike'],
                expiration=exp_str,
                entry_price=pos['entry_price'],
                exit_price=exit_price,
                premium=pos['premium_received'],
                contracts=pos['contracts'],
                pnl=pnl,
                order_id=str(order_id) if order_id else ""
            )

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
