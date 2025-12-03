"""
Walk-Forward Optimization Framework

Prevents overfitting by using proper train/test splits on time series data.

Key Concepts:
1. In-Sample (IS): Data used to optimize/train parameters
2. Out-of-Sample (OOS): Data used to validate performance
3. Walk-Forward: Rolling window where we train -> test -> walk forward

Example with 60-day IS / 20-day OOS:
    [====== IS Window 1 ======][OOS 1]
              [====== IS Window 2 ======][OOS 2]
                        [====== IS Window 3 ======][OOS 3]

This prevents:
- Curve-fitting to historical data
- Selection bias from cherry-picking parameters
- False confidence from in-sample results

Author: AlphaGEX Quant
Date: 2025-12-03
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import json

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


@dataclass
class WalkForwardWindow:
    """Single train/test window"""
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_days: int
    test_days: int


@dataclass
class WindowResult:
    """Results from a single walk-forward window"""
    window: WalkForwardWindow
    train_metrics: Dict
    test_metrics: Dict
    optimal_params: Dict
    degradation_pct: float  # How much worse OOS vs IS


@dataclass
class WalkForwardResult:
    """Complete walk-forward analysis results"""
    strategy_name: str
    symbol: str
    total_windows: int
    is_avg_win_rate: float      # In-sample average
    oos_avg_win_rate: float     # Out-of-sample average
    degradation_pct: float      # (IS - OOS) / IS * 100
    is_robust: bool             # OOS degradation < 20%?
    window_results: List[WindowResult]
    recommended_params: Dict
    analysis_date: str

    def to_dict(self) -> Dict:
        return {
            'strategy_name': self.strategy_name,
            'symbol': self.symbol,
            'total_windows': self.total_windows,
            'is_avg_win_rate': round(self.is_avg_win_rate, 2),
            'oos_avg_win_rate': round(self.oos_avg_win_rate, 2),
            'degradation_pct': round(self.degradation_pct, 2),
            'is_robust': self.is_robust,
            'recommended_params': self.recommended_params,
            'analysis_date': self.analysis_date,
            'window_count': len(self.window_results)
        }


class WalkForwardOptimizer:
    """
    Walk-Forward Optimization for strategy parameters.

    Prevents overfitting by:
    1. Training on historical window
    2. Testing on forward window (unseen data)
    3. Walking forward and repeating

    Typical setup:
    - Train window: 60 trading days (~3 months)
    - Test window: 20 trading days (~1 month)
    - Walk-forward step: 20 trading days

    Key Metrics:
    - In-Sample (IS) performance: What backtest shows
    - Out-of-Sample (OOS) performance: What actually happens
    - Degradation: (IS - OOS) / IS - should be < 20%
    """

    def __init__(
        self,
        symbol: str = "SPY",
        train_days: int = 60,
        test_days: int = 20,
        step_days: int = 20,
        min_trades_per_window: int = 5
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            symbol: Trading symbol
            train_days: Days in training window (IS)
            test_days: Days in test window (OOS)
            step_days: Days to step forward each iteration
            min_trades_per_window: Minimum trades required per window
        """
        self.symbol = symbol
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.min_trades_per_window = min_trades_per_window

    def create_windows(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[WalkForwardWindow]:
        """
        Create walk-forward windows from date range.

        Returns list of (train_start, train_end, test_start, test_end) tuples.
        """
        windows = []
        window_id = 0

        current_train_start = start_date

        while True:
            train_end = current_train_start + timedelta(days=self.train_days)
            test_start = train_end + timedelta(days=1)
            test_end = test_start + timedelta(days=self.test_days)

            # Stop if test window goes beyond end date
            if test_end > end_date:
                break

            windows.append(WalkForwardWindow(
                window_id=window_id,
                train_start=current_train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_days=self.train_days,
                test_days=self.test_days
            ))

            # Walk forward
            current_train_start += timedelta(days=self.step_days)
            window_id += 1

        return windows

    def optimize_window(
        self,
        window: WalkForwardWindow,
        strategy_func: Callable,
        param_grid: Dict[str, List],
        historical_data: pd.DataFrame
    ) -> WindowResult:
        """
        Optimize parameters on a single walk-forward window.

        Args:
            window: Train/test window definition
            strategy_func: Function that runs strategy given params, returns metrics
            param_grid: Dict of param_name -> values to test
            historical_data: DataFrame with price/indicator data

        Returns:
            WindowResult with optimal params and IS/OOS metrics
        """
        # Filter data to train window
        train_data = historical_data[
            (historical_data.index >= window.train_start) &
            (historical_data.index <= window.train_end)
        ]

        test_data = historical_data[
            (historical_data.index >= window.test_start) &
            (historical_data.index <= window.test_end)
        ]

        if len(train_data) < 10 or len(test_data) < 5:
            return WindowResult(
                window=window,
                train_metrics={'win_rate': 0, 'trades': 0},
                test_metrics={'win_rate': 0, 'trades': 0},
                optimal_params={},
                degradation_pct=100.0
            )

        # Grid search on training data
        best_params = {}
        best_train_metric = -np.inf

        # Generate all parameter combinations
        from itertools import product
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())

        for combo in product(*param_values):
            params = dict(zip(param_names, combo))

            # Run strategy on train data
            try:
                train_metrics = strategy_func(train_data, params)
                train_score = train_metrics.get('win_rate', 0) * train_metrics.get('trades', 0)

                if train_score > best_train_metric:
                    best_train_metric = train_score
                    best_params = params
                    best_train_metrics = train_metrics
            except Exception as e:
                continue

        if not best_params:
            return WindowResult(
                window=window,
                train_metrics={'win_rate': 0, 'trades': 0},
                test_metrics={'win_rate': 0, 'trades': 0},
                optimal_params={},
                degradation_pct=100.0
            )

        # Test optimal params on OOS data
        try:
            test_metrics = strategy_func(test_data, best_params)
        except Exception:
            test_metrics = {'win_rate': 0, 'trades': 0}

        # Calculate degradation
        is_wr = best_train_metrics.get('win_rate', 0)
        oos_wr = test_metrics.get('win_rate', 0)
        degradation = ((is_wr - oos_wr) / is_wr * 100) if is_wr > 0 else 100.0

        return WindowResult(
            window=window,
            train_metrics=best_train_metrics,
            test_metrics=test_metrics,
            optimal_params=best_params,
            degradation_pct=degradation
        )

    def run_walk_forward(
        self,
        strategy_name: str,
        strategy_func: Callable,
        param_grid: Dict[str, List],
        start_date: datetime,
        end_date: datetime,
        historical_data: pd.DataFrame
    ) -> WalkForwardResult:
        """
        Run complete walk-forward analysis.

        Args:
            strategy_name: Name of strategy being tested
            strategy_func: Function(data, params) -> metrics dict
            param_grid: Parameters to optimize
            start_date: Analysis start date
            end_date: Analysis end date
            historical_data: Full historical data

        Returns:
            WalkForwardResult with aggregate metrics
        """
        # Create windows
        windows = self.create_windows(start_date, end_date)

        if not windows:
            return WalkForwardResult(
                strategy_name=strategy_name,
                symbol=self.symbol,
                total_windows=0,
                is_avg_win_rate=0,
                oos_avg_win_rate=0,
                degradation_pct=100,
                is_robust=False,
                window_results=[],
                recommended_params={},
                analysis_date=datetime.now().isoformat()
            )

        # Run optimization on each window
        window_results = []
        for window in windows:
            result = self.optimize_window(
                window, strategy_func, param_grid, historical_data
            )
            window_results.append(result)

        # Aggregate results
        valid_results = [r for r in window_results if r.train_metrics.get('trades', 0) >= self.min_trades_per_window]

        if not valid_results:
            return WalkForwardResult(
                strategy_name=strategy_name,
                symbol=self.symbol,
                total_windows=len(windows),
                is_avg_win_rate=0,
                oos_avg_win_rate=0,
                degradation_pct=100,
                is_robust=False,
                window_results=window_results,
                recommended_params={},
                analysis_date=datetime.now().isoformat()
            )

        # Calculate aggregate metrics
        is_win_rates = [r.train_metrics.get('win_rate', 0) for r in valid_results]
        oos_win_rates = [r.test_metrics.get('win_rate', 0) for r in valid_results]

        is_avg = np.mean(is_win_rates)
        oos_avg = np.mean(oos_win_rates)
        degradation = ((is_avg - oos_avg) / is_avg * 100) if is_avg > 0 else 100.0

        # Strategy is robust if degradation < 20%
        is_robust = degradation < 20 and oos_avg > 50

        # Find most common optimal params (mode)
        param_counts = {}
        for r in valid_results:
            param_key = json.dumps(r.optimal_params, sort_keys=True)
            param_counts[param_key] = param_counts.get(param_key, 0) + 1

        if param_counts:
            best_param_key = max(param_counts.keys(), key=lambda k: param_counts[k])
            recommended_params = json.loads(best_param_key)
        else:
            recommended_params = {}

        return WalkForwardResult(
            strategy_name=strategy_name,
            symbol=self.symbol,
            total_windows=len(windows),
            is_avg_win_rate=is_avg,
            oos_avg_win_rate=oos_avg,
            degradation_pct=degradation,
            is_robust=is_robust,
            window_results=window_results,
            recommended_params=recommended_params,
            analysis_date=datetime.now().isoformat()
        )

    def validate_current_params(
        self,
        strategy_name: str,
        current_params: Dict,
        strategy_func: Callable,
        historical_data: pd.DataFrame,
        lookback_days: int = 365
    ) -> Dict:
        """
        Validate if current strategy parameters are still optimal.

        Compares current params against walk-forward optimal params.

        Returns recommendation to keep, adjust, or retrain.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        # Run walk-forward to find optimal params
        result = self.run_walk_forward(
            strategy_name=strategy_name,
            strategy_func=strategy_func,
            param_grid={k: [v] for k, v in current_params.items()},  # Test current only
            start_date=start_date,
            end_date=end_date,
            historical_data=historical_data
        )

        # Compare current vs optimal
        recommendation = {
            'strategy': strategy_name,
            'current_params': current_params,
            'optimal_params': result.recommended_params,
            'is_current_optimal': current_params == result.recommended_params,
            'is_win_rate': result.is_avg_win_rate,
            'oos_win_rate': result.oos_avg_win_rate,
            'degradation_pct': result.degradation_pct,
            'is_robust': result.is_robust,
            'recommendation': 'KEEP' if result.is_robust else 'RETRAIN'
        }

        return recommendation

    def save_results_to_db(self, result: WalkForwardResult):
        """Save walk-forward results to database"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO walk_forward_results (
                    strategy_name, symbol, total_windows,
                    is_avg_win_rate, oos_avg_win_rate,
                    degradation_pct, is_robust,
                    recommended_params, analysis_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                result.strategy_name,
                result.symbol,
                result.total_windows,
                result.is_avg_win_rate,
                result.oos_avg_win_rate,
                result.degradation_pct,
                result.is_robust,
                json.dumps(result.recommended_params),
                result.analysis_date
            ))

            conn.commit()
            conn.close()
            print(f"Saved walk-forward results for {result.strategy_name}")
        except Exception as e:
            print(f"Could not save walk-forward results: {e}")


def run_walk_forward_validation(
    strategy_name: str,
    strategy_func: Callable,
    param_grid: Dict[str, List],
    symbol: str = "SPY",
    train_days: int = 60,
    test_days: int = 20,
    lookback_days: int = 365
) -> WalkForwardResult:
    """
    Convenience function to run walk-forward validation.

    Example usage:
        def my_strategy(data, params):
            # Run strategy logic
            return {'win_rate': 65, 'trades': 20, 'return_pct': 15}

        result = run_walk_forward_validation(
            strategy_name="GEX_SQUEEZE",
            strategy_func=my_strategy,
            param_grid={
                'gex_threshold': [-2e9, -1e9, -0.5e9],
                'profit_target': [0.3, 0.5, 0.75]
            }
        )

        if result.is_robust:
            print(f"Strategy is robust! OOS win rate: {result.oos_avg_win_rate}%")
    """
    # Try to fetch historical data
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days + 30)  # Extra buffer
        historical_data = ticker.history(start=start_date, end=end_date)
    except Exception as e:
        print(f"Could not fetch historical data: {e}")
        historical_data = pd.DataFrame()

    optimizer = WalkForwardOptimizer(
        symbol=symbol,
        train_days=train_days,
        test_days=test_days
    )

    result = optimizer.run_walk_forward(
        strategy_name=strategy_name,
        strategy_func=strategy_func,
        param_grid=param_grid,
        start_date=datetime.now() - timedelta(days=lookback_days),
        end_date=datetime.now(),
        historical_data=historical_data
    )

    # Save to DB
    optimizer.save_results_to_db(result)

    return result


# Example strategy function for testing
def example_gex_strategy(data: pd.DataFrame, params: Dict) -> Dict:
    """
    Example strategy function for walk-forward testing.

    This is a placeholder - replace with actual strategy logic.
    """
    gex_threshold = params.get('gex_threshold', -1e9)
    profit_target = params.get('profit_target', 0.5)

    # Simulate trades based on data
    if data.empty:
        return {'win_rate': 0, 'trades': 0, 'return_pct': 0}

    # Simple simulation: days below threshold -> trade
    trades = 0
    wins = 0

    for i in range(len(data)):
        # Simulate 10% chance of trade per day
        if np.random.random() < 0.1:
            trades += 1
            # Simulate win based on some relationship with params
            win_prob = 0.55 + (abs(gex_threshold) / 1e10) * 0.1
            if np.random.random() < win_prob:
                wins += 1

    win_rate = (wins / trades * 100) if trades > 0 else 0
    return {
        'win_rate': win_rate,
        'trades': trades,
        'return_pct': win_rate * 0.2 - 10  # Simplified
    }


if __name__ == "__main__":
    print("Running Walk-Forward Validation Example...")

    # Run walk-forward on example strategy
    result = run_walk_forward_validation(
        strategy_name="EXAMPLE_GEX",
        strategy_func=example_gex_strategy,
        param_grid={
            'gex_threshold': [-2e9, -1e9, -0.5e9],
            'profit_target': [0.3, 0.5, 0.75]
        },
        train_days=60,
        test_days=20,
        lookback_days=365
    )

    print(f"\nWalk-Forward Results:")
    print(f"  Strategy: {result.strategy_name}")
    print(f"  Windows: {result.total_windows}")
    print(f"  In-Sample Win Rate: {result.is_avg_win_rate:.1f}%")
    print(f"  Out-of-Sample Win Rate: {result.oos_avg_win_rate:.1f}%")
    print(f"  Degradation: {result.degradation_pct:.1f}%")
    print(f"  Is Robust: {result.is_robust}")
    print(f"  Recommended Params: {result.recommended_params}")
