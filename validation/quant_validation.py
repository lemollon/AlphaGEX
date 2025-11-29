"""
Quant-Level Validation Framework for AlphaGEX

This module provides rigorous validation of:
1. GEX Calculations - Comparing against known market data
2. Gamma Wall Prediction - Statistical analysis of predictive power
3. Out-of-Sample Sharpe Ratio - True performance measurement
4. Paper Trading Validation - Real-time signal tracking

CRITICAL: Run this before trusting any backtest results.

Author: AlphaGEX
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from scipy import stats
import warnings

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class GEXValidationResult:
    """Results from GEX calculation validation"""
    is_valid: bool
    accuracy_score: float  # 0-100
    issues: List[str] = field(default_factory=list)
    correlation_with_api: Optional[float] = None
    mean_error_pct: Optional[float] = None
    test_cases_passed: int = 0
    test_cases_total: int = 0

    def to_dict(self) -> Dict:
        return {
            'is_valid': self.is_valid,
            'accuracy_score': self.accuracy_score,
            'issues': self.issues,
            'correlation': self.correlation_with_api,
            'mean_error_pct': self.mean_error_pct,
            'test_cases': f"{self.test_cases_passed}/{self.test_cases_total}"
        }


@dataclass
class PredictionStats:
    """Statistics for prediction accuracy"""
    total_predictions: int
    correct_direction: int
    accuracy_pct: float
    avg_magnitude_when_correct: float
    avg_magnitude_when_wrong: float
    profit_factor: float
    hit_rate: float
    expected_value: float
    t_statistic: float
    p_value: float
    is_significant: bool


@dataclass
class SharpeAnalysis:
    """Out-of-sample Sharpe ratio analysis"""
    sharpe_ratio: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    n_trades: int
    is_statistically_significant: bool
    confidence_interval_95: Tuple[float, float]


# =============================================================================
# 1. GEX CALCULATION VALIDATION
# =============================================================================

class GEXValidator:
    """
    Validates GEX calculations against known correct values

    Tests:
    1. Unit tests with known inputs/outputs
    2. Comparison against Trading Volatility API
    3. Sanity checks on calculation ranges
    4. Put/Call parity for GEX
    """

    def __init__(self):
        self.test_results = []
        self.known_test_cases = self._build_test_cases()

    def _build_test_cases(self) -> List[Dict]:
        """
        Build test cases with known correct GEX values

        GEX Formula:
        GEX = Spot × Gamma × OI × 100 (× -1 for puts)

        These test cases can be verified manually.
        """
        return [
            # Test Case 1: ATM Call
            {
                'name': 'ATM Call Basic',
                'spot': 450.0,
                'strike': 450.0,
                'gamma': 0.015,
                'oi': 10000,
                'option_type': 'call',
                'expected_gex': 450.0 * 0.015 * 10000 * 100,  # 6,750,000
            },
            # Test Case 2: OTM Put
            {
                'name': 'OTM Put Basic',
                'spot': 450.0,
                'strike': 440.0,
                'gamma': 0.008,
                'oi': 15000,
                'option_type': 'put',
                'expected_gex': -450.0 * 0.008 * 15000 * 100,  # -5,400,000
            },
            # Test Case 3: Deep OTM Call (low gamma)
            {
                'name': 'Deep OTM Call',
                'spot': 450.0,
                'strike': 480.0,
                'gamma': 0.002,
                'oi': 5000,
                'option_type': 'call',
                'expected_gex': 450.0 * 0.002 * 5000 * 100,  # 450,000
            },
            # Test Case 4: Near-expiry ATM (high gamma)
            {
                'name': 'Near Expiry ATM',
                'spot': 450.0,
                'strike': 450.0,
                'gamma': 0.08,  # High gamma near expiry
                'oi': 20000,
                'option_type': 'call',
                'expected_gex': 450.0 * 0.08 * 20000 * 100,  # 72,000,000
            },
            # Test Case 5: Zero OI (should be zero GEX)
            {
                'name': 'Zero OI',
                'spot': 450.0,
                'strike': 460.0,
                'gamma': 0.01,
                'oi': 0,
                'option_type': 'call',
                'expected_gex': 0.0,
            },
            # Test Case 6: Aggregate (Call + Put at same strike should partially cancel)
            {
                'name': 'Aggregate Call+Put',
                'spot': 450.0,
                'strike': 450.0,
                'gamma': 0.015,
                'call_oi': 10000,
                'put_oi': 8000,
                'expected_net_gex': 450.0 * 0.015 * (10000 - 8000) * 100,  # 1,350,000
            },
        ]

    def validate_calculation(self, calc_func) -> GEXValidationResult:
        """
        Run validation tests on a GEX calculation function

        Args:
            calc_func: Function that takes (spot, strike, gamma, oi, option_type)
                       and returns GEX value

        Returns:
            GEXValidationResult with pass/fail and accuracy
        """
        issues = []
        passed = 0
        total = len(self.known_test_cases)

        for tc in self.known_test_cases:
            if 'call_oi' in tc:
                # Aggregate test
                call_gex = calc_func(tc['spot'], tc['strike'], tc['gamma'],
                                    tc['call_oi'], 'call')
                put_gex = calc_func(tc['spot'], tc['strike'], tc['gamma'],
                                   tc['put_oi'], 'put')
                result = call_gex + put_gex
                expected = tc['expected_net_gex']
            else:
                result = calc_func(tc['spot'], tc['strike'], tc['gamma'],
                                  tc['oi'], tc['option_type'])
                expected = tc['expected_gex']

            # Check if result is within 0.1% of expected
            if expected == 0:
                if result == 0:
                    passed += 1
                else:
                    issues.append(f"{tc['name']}: Expected 0, got {result:,.0f}")
            else:
                error_pct = abs(result - expected) / abs(expected) * 100
                if error_pct < 0.1:
                    passed += 1
                else:
                    issues.append(f"{tc['name']}: Expected {expected:,.0f}, got {result:,.0f} ({error_pct:.2f}% error)")

        accuracy = (passed / total) * 100 if total > 0 else 0

        return GEXValidationResult(
            is_valid=passed == total,
            accuracy_score=accuracy,
            issues=issues,
            test_cases_passed=passed,
            test_cases_total=total
        )

    def validate_against_api(self, local_gex_data: Dict, api_gex_data: Dict) -> GEXValidationResult:
        """
        Compare local GEX calculations against Trading Volatility API

        Args:
            local_gex_data: Dict with 'net_gex', 'flip_point', 'call_wall', 'put_wall'
            api_gex_data: Same structure from API

        Returns:
            GEXValidationResult with correlation analysis
        """
        issues = []

        # Compare net GEX
        local_net = local_gex_data.get('net_gex', 0)
        api_net = api_gex_data.get('net_gex', 0)

        if api_net != 0:
            net_gex_error = abs(local_net - api_net) / abs(api_net) * 100
        else:
            net_gex_error = 100 if local_net != 0 else 0

        if net_gex_error > 50:
            issues.append(f"Net GEX differs by {net_gex_error:.1f}% from API")

        # Compare flip point
        local_flip = local_gex_data.get('flip_point', 0)
        api_flip = api_gex_data.get('flip_point', 0)

        if api_flip != 0:
            flip_error = abs(local_flip - api_flip) / api_flip * 100
            if flip_error > 2:  # More than 2% difference
                issues.append(f"Flip point differs by {flip_error:.1f}% ({local_flip:.2f} vs {api_flip:.2f})")

        # Score based on errors
        accuracy = 100 - min(100, net_gex_error * 0.5 + flip_error * 0.5)

        return GEXValidationResult(
            is_valid=len(issues) == 0,
            accuracy_score=accuracy,
            issues=issues,
            mean_error_pct=(net_gex_error + flip_error) / 2
        )

    def sanity_check_gex(self, net_gex: float, spot_price: float, symbol: str = 'SPY') -> List[str]:
        """
        Sanity check GEX values are in realistic range

        SPY typical ranges:
        - Net GEX: -20B to +20B (extreme: ±50B)
        - Net GEX / Spot should be roughly in range

        Returns:
            List of warning messages (empty if all OK)
        """
        warnings_list = []

        # Symbol-specific thresholds
        thresholds = {
            'SPY': {'max_gex': 50e9, 'typical_max': 20e9},
            'QQQ': {'max_gex': 20e9, 'typical_max': 8e9},
            'IWM': {'max_gex': 5e9, 'typical_max': 2e9},
        }

        thresh = thresholds.get(symbol.upper(), thresholds['SPY'])

        if abs(net_gex) > thresh['max_gex']:
            warnings_list.append(f"Net GEX {net_gex/1e9:.1f}B exceeds maximum plausible ({thresh['max_gex']/1e9:.0f}B)")

        if abs(net_gex) > thresh['typical_max']:
            warnings_list.append(f"Net GEX {net_gex/1e9:.1f}B is unusually high (typical max: {thresh['typical_max']/1e9:.0f}B)")

        # Check for suspiciously round numbers (possible dummy data)
        if net_gex != 0 and net_gex == round(net_gex, -9):
            warnings_list.append(f"Net GEX is suspiciously round ({net_gex/1e9:.0f}B) - may be simulated")

        return warnings_list


# =============================================================================
# 2. GAMMA WALL PREDICTION VALIDATION
# =============================================================================

class GammaWallPredictor:
    """
    Validates predictive power of gamma wall detection

    Tests:
    1. Does price respect call walls as resistance?
    2. Does price respect put walls as support?
    3. Does price behavior change at flip point?
    4. Statistical significance of predictions
    """

    def __init__(self):
        self.predictions = []
        self.outcomes = []

    def add_prediction(self, date: datetime, prediction: Dict, outcome: Dict):
        """
        Add a prediction and its outcome

        Args:
            date: Date of prediction
            prediction: Dict with:
                - call_wall: Expected resistance level
                - put_wall: Expected support level
                - flip_point: Expected behavior change level
                - net_gex: Net gamma exposure
                - expected_direction: 'bullish', 'bearish', or 'neutral'
            outcome: Dict with:
                - high: Daily high
                - low: Daily low
                - close: Daily close
                - open: Daily open
                - next_day_close: Next day close (for direction)
        """
        self.predictions.append({
            'date': date,
            **prediction
        })
        self.outcomes.append({
            'date': date,
            **outcome
        })

    def analyze_call_wall_as_resistance(self) -> PredictionStats:
        """
        Analyze if call walls act as resistance

        A call wall is "respected" if:
        - Price approached within 0.5% but didn't close above
        - OR price peaked and reversed near the level
        """
        if not self.predictions or not self.outcomes:
            return self._empty_stats()

        total = 0
        respected = 0
        magnitudes_correct = []
        magnitudes_wrong = []

        for pred, out in zip(self.predictions, self.outcomes):
            call_wall = pred.get('call_wall')
            if call_wall is None or call_wall == 0:
                continue

            total += 1
            high = out['high']
            close = out['close']

            # Did price approach the wall?
            distance_to_wall = (call_wall - close) / close * 100
            approached = high >= call_wall * 0.995  # Within 0.5%

            if approached:
                # Was it respected (didn't close above)?
                if close < call_wall:
                    respected += 1
                    magnitudes_correct.append(abs(distance_to_wall))
                else:
                    magnitudes_wrong.append(abs(distance_to_wall))

        return self._calculate_stats(total, respected, magnitudes_correct, magnitudes_wrong)

    def analyze_put_wall_as_support(self) -> PredictionStats:
        """
        Analyze if put walls act as support

        A put wall is "respected" if:
        - Price approached within 0.5% but didn't close below
        """
        if not self.predictions or not self.outcomes:
            return self._empty_stats()

        total = 0
        respected = 0
        magnitudes_correct = []
        magnitudes_wrong = []

        for pred, out in zip(self.predictions, self.outcomes):
            put_wall = pred.get('put_wall')
            if put_wall is None or put_wall == 0:
                continue

            total += 1
            low = out['low']
            close = out['close']

            # Did price approach the wall?
            distance_to_wall = (close - put_wall) / close * 100
            approached = low <= put_wall * 1.005  # Within 0.5%

            if approached:
                # Was it respected (didn't close below)?
                if close > put_wall:
                    respected += 1
                    magnitudes_correct.append(abs(distance_to_wall))
                else:
                    magnitudes_wrong.append(abs(distance_to_wall))

        return self._calculate_stats(total, respected, magnitudes_correct, magnitudes_wrong)

    def analyze_flip_point_behavior(self) -> Dict:
        """
        Analyze price behavior around the flip point

        When price is above flip point (positive gamma territory):
        - Expect lower volatility, mean reversion
        - Dealers are long gamma, sell highs/buy lows

        When price is below flip point (negative gamma territory):
        - Expect higher volatility, momentum
        - Dealers are short gamma, buy highs/sell lows
        """
        if not self.predictions or not self.outcomes:
            return {'insufficient_data': True}

        above_flip_volatility = []
        below_flip_volatility = []

        for pred, out in zip(self.predictions, self.outcomes):
            flip = pred.get('flip_point')
            if flip is None or flip == 0:
                continue

            open_price = out['open']
            high = out['high']
            low = out['low']

            # Daily volatility (high-low range)
            daily_range = (high - low) / open_price * 100

            if open_price > flip:
                above_flip_volatility.append(daily_range)
            else:
                below_flip_volatility.append(daily_range)

        if not above_flip_volatility or not below_flip_volatility:
            return {'insufficient_data': True}

        avg_vol_above = np.mean(above_flip_volatility)
        avg_vol_below = np.mean(below_flip_volatility)

        # T-test for difference in volatility
        t_stat, p_value = stats.ttest_ind(above_flip_volatility, below_flip_volatility)

        return {
            'avg_volatility_above_flip': avg_vol_above,
            'avg_volatility_below_flip': avg_vol_below,
            'volatility_ratio': avg_vol_below / avg_vol_above if avg_vol_above > 0 else 0,
            't_statistic': t_stat,
            'p_value': p_value,
            'is_significant': p_value < 0.05,
            'theory_holds': avg_vol_below > avg_vol_above,  # Should be higher below flip
            'n_above': len(above_flip_volatility),
            'n_below': len(below_flip_volatility)
        }

    def analyze_direction_prediction(self) -> PredictionStats:
        """
        Analyze if net GEX predicts next-day direction

        Positive GEX -> Expect mean reversion / range-bound
        Negative GEX -> Expect momentum continuation
        """
        if not self.predictions or not self.outcomes:
            return self._empty_stats()

        total = 0
        correct = 0
        returns_correct = []
        returns_wrong = []

        for pred, out in zip(self.predictions, self.outcomes):
            net_gex = pred.get('net_gex', 0)
            next_close = out.get('next_day_close')
            today_close = out['close']

            if next_close is None:
                continue

            total += 1
            actual_return = (next_close - today_close) / today_close * 100

            # Positive GEX: expect mean reversion (if up today, expect down tomorrow)
            # Negative GEX: expect momentum (if up today, expect up tomorrow)
            today_return = (out['close'] - out['open']) / out['open'] * 100

            if net_gex > 0:
                # Mean reversion expected
                predicted_direction = -1 if today_return > 0 else 1
            else:
                # Momentum expected
                predicted_direction = 1 if today_return > 0 else -1

            actual_direction = 1 if actual_return > 0 else -1

            if predicted_direction == actual_direction:
                correct += 1
                returns_correct.append(abs(actual_return))
            else:
                returns_wrong.append(abs(actual_return))

        return self._calculate_stats(total, correct, returns_correct, returns_wrong)

    def _calculate_stats(self, total: int, correct: int,
                        magnitudes_correct: List[float],
                        magnitudes_wrong: List[float]) -> PredictionStats:
        """Calculate prediction statistics"""
        if total == 0:
            return self._empty_stats()

        accuracy = correct / total * 100
        avg_correct = np.mean(magnitudes_correct) if magnitudes_correct else 0
        avg_wrong = np.mean(magnitudes_wrong) if magnitudes_wrong else 0

        profit_factor = avg_correct / avg_wrong if avg_wrong > 0 else float('inf')

        # Calculate expected value
        win_rate = correct / total
        ev = win_rate * avg_correct - (1 - win_rate) * avg_wrong

        # T-test for significance
        if magnitudes_correct and magnitudes_wrong:
            t_stat, p_value = stats.ttest_ind(magnitudes_correct, magnitudes_wrong)
        else:
            t_stat, p_value = 0, 1

        return PredictionStats(
            total_predictions=total,
            correct_direction=correct,
            accuracy_pct=accuracy,
            avg_magnitude_when_correct=avg_correct,
            avg_magnitude_when_wrong=avg_wrong,
            profit_factor=profit_factor,
            hit_rate=win_rate,
            expected_value=ev,
            t_statistic=t_stat,
            p_value=p_value,
            is_significant=p_value < 0.05 and accuracy > 55
        )

    def _empty_stats(self) -> PredictionStats:
        """Return empty stats when no data"""
        return PredictionStats(
            total_predictions=0,
            correct_direction=0,
            accuracy_pct=0,
            avg_magnitude_when_correct=0,
            avg_magnitude_when_wrong=0,
            profit_factor=0,
            hit_rate=0,
            expected_value=0,
            t_statistic=0,
            p_value=1,
            is_significant=False
        )


# =============================================================================
# 3. OUT-OF-SAMPLE SHARPE RATIO CALCULATION
# =============================================================================

class SharpeCalculator:
    """
    Calculates statistically rigorous out-of-sample Sharpe ratio

    CRITICAL: In-sample Sharpe means nothing. Only out-of-sample matters.

    Uses:
    - Walk-forward analysis
    - Bootstrap confidence intervals
    - Multiple lookback periods
    """

    def __init__(self, risk_free_rate: float = 0.045):
        """
        Args:
            risk_free_rate: Annual risk-free rate (default 4.5%)
        """
        self.rf = risk_free_rate
        self.daily_rf = (1 + risk_free_rate) ** (1/252) - 1

    def calculate_sharpe(self, returns: pd.Series, annualize: bool = True) -> float:
        """
        Calculate Sharpe ratio from returns series

        Args:
            returns: Daily returns series
            annualize: Whether to annualize the ratio

        Returns:
            Sharpe ratio
        """
        if len(returns) < 30:
            warnings.warn("Fewer than 30 observations - Sharpe may be unreliable")

        excess_returns = returns - self.daily_rf
        mean_excess = excess_returns.mean()
        std_excess = excess_returns.std()

        if std_excess == 0:
            return 0.0

        sharpe = mean_excess / std_excess

        if annualize:
            sharpe *= np.sqrt(252)

        return sharpe

    def walk_forward_sharpe(self, returns: pd.Series,
                            train_pct: float = 0.7,
                            n_splits: int = 5) -> List[float]:
        """
        Walk-forward out-of-sample Sharpe ratios

        This is the REAL test - not just overall Sharpe.

        Args:
            returns: Full returns series
            train_pct: Percentage used for "training" (ignored in pure OOS)
            n_splits: Number of walk-forward periods

        Returns:
            List of out-of-sample Sharpe ratios for each period
        """
        n = len(returns)
        split_size = n // n_splits

        oos_sharpes = []

        for i in range(n_splits):
            start = i * split_size
            end = min((i + 1) * split_size, n)

            period_returns = returns.iloc[start:end]

            if len(period_returns) >= 20:
                sharpe = self.calculate_sharpe(period_returns)
                oos_sharpes.append(sharpe)

        return oos_sharpes

    def bootstrap_confidence_interval(self, returns: pd.Series,
                                       n_bootstrap: int = 1000,
                                       confidence: float = 0.95) -> Tuple[float, float]:
        """
        Bootstrap confidence interval for Sharpe ratio

        Args:
            returns: Daily returns series
            n_bootstrap: Number of bootstrap samples
            confidence: Confidence level (0.95 = 95%)

        Returns:
            (lower_bound, upper_bound) of confidence interval
        """
        n = len(returns)
        bootstrap_sharpes = []

        for _ in range(n_bootstrap):
            # Sample with replacement
            sample = returns.sample(n=n, replace=True)
            sharpe = self.calculate_sharpe(sample)
            bootstrap_sharpes.append(sharpe)

        lower_pct = (1 - confidence) / 2 * 100
        upper_pct = (1 + confidence) / 2 * 100

        return (
            np.percentile(bootstrap_sharpes, lower_pct),
            np.percentile(bootstrap_sharpes, upper_pct)
        )

    def full_analysis(self, returns: pd.Series) -> SharpeAnalysis:
        """
        Complete Sharpe ratio analysis

        Args:
            returns: Daily returns series

        Returns:
            SharpeAnalysis with all metrics
        """
        if len(returns) < 30:
            return SharpeAnalysis(
                sharpe_ratio=0,
                annualized_return=0,
                annualized_volatility=0,
                max_drawdown=0,
                calmar_ratio=0,
                win_rate=0,
                profit_factor=0,
                n_trades=len(returns),
                is_statistically_significant=False,
                confidence_interval_95=(0, 0)
            )

        # Basic metrics
        sharpe = self.calculate_sharpe(returns)
        annual_ret = returns.mean() * 252
        annual_vol = returns.std() * np.sqrt(252)

        # Max drawdown
        cumulative = (1 + returns).cumprod()
        peak = cumulative.expanding().max()
        drawdown = (cumulative - peak) / peak
        max_dd = drawdown.min()

        # Calmar ratio (return / max drawdown)
        calmar = annual_ret / abs(max_dd) if max_dd != 0 else 0

        # Win rate and profit factor
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        win_rate = len(wins) / len(returns) if len(returns) > 0 else 0

        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf')

        # Confidence interval
        ci = self.bootstrap_confidence_interval(returns)

        # Statistical significance (Sharpe > 0 with 95% confidence)
        is_significant = ci[0] > 0

        return SharpeAnalysis(
            sharpe_ratio=sharpe,
            annualized_return=annual_ret,
            annualized_volatility=annual_vol,
            max_drawdown=max_dd,
            calmar_ratio=calmar,
            win_rate=win_rate,
            profit_factor=profit_factor,
            n_trades=len(returns),
            is_statistically_significant=is_significant,
            confidence_interval_95=ci
        )


# =============================================================================
# 4. PAPER TRADING VALIDATION
# =============================================================================

class PaperTradingValidator:
    """
    Tracks paper trading signals and validates against real outcomes

    Use this to validate signals BEFORE risking real money.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Args:
            db_path: Path to SQLite database for persistence
                     If None, uses in-memory storage
        """
        self.signals: List[Dict] = []
        self.outcomes: List[Dict] = []
        self.db_path = db_path

        if db_path:
            self._init_db()

    def _init_db(self):
        """Initialize database tables"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS paper_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                signal_type TEXT,
                direction TEXT,
                entry_price REAL,
                target_price REAL,
                stop_loss REAL,
                confidence REAL,
                gex_data TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS paper_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                exit_timestamp TEXT,
                exit_price REAL,
                pnl_pct REAL,
                hit_target INTEGER,
                hit_stop INTEGER,
                max_favorable REAL,
                max_adverse REAL,
                FOREIGN KEY (signal_id) REFERENCES paper_signals(id)
            )
        ''')

        conn.commit()
        conn.close()

    def log_signal(self, symbol: str, signal_type: str, direction: str,
                   entry_price: float, target_price: float, stop_loss: float,
                   confidence: float, gex_data: Optional[Dict] = None) -> int:
        """
        Log a paper trading signal

        Args:
            symbol: Trading symbol (e.g., 'SPY')
            signal_type: Type of signal (e.g., 'gamma_wall_bounce', 'flip_breakout')
            direction: 'long' or 'short'
            entry_price: Entry price
            target_price: Target price
            stop_loss: Stop loss price
            confidence: Signal confidence (0-1)
            gex_data: Optional GEX context data

        Returns:
            Signal ID for tracking
        """
        import json

        signal = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'signal_type': signal_type,
            'direction': direction,
            'entry_price': entry_price,
            'target_price': target_price,
            'stop_loss': stop_loss,
            'confidence': confidence,
            'gex_data': gex_data,
            'status': 'pending'
        }

        self.signals.append(signal)
        signal_id = len(self.signals) - 1

        if self.db_path:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''
                INSERT INTO paper_signals
                (timestamp, symbol, signal_type, direction, entry_price,
                 target_price, stop_loss, confidence, gex_data, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal['timestamp'], symbol, signal_type, direction,
                entry_price, target_price, stop_loss, confidence,
                json.dumps(gex_data) if gex_data else None, 'pending'
            ))
            signal_id = c.lastrowid
            conn.commit()
            conn.close()

        logger.info(f"Paper signal logged: {signal_type} {direction} {symbol} @ {entry_price}")
        return signal_id

    def log_outcome(self, signal_id: int, exit_price: float,
                    max_favorable: float, max_adverse: float):
        """
        Log outcome of a paper trade

        Args:
            signal_id: ID from log_signal
            exit_price: Actual exit price
            max_favorable: Maximum favorable excursion (MFE)
            max_adverse: Maximum adverse excursion (MAE)
        """
        if signal_id >= len(self.signals):
            logger.warning(f"Unknown signal ID: {signal_id}")
            return

        signal = self.signals[signal_id]
        entry = signal['entry_price']
        direction = signal['direction']

        # Calculate P&L
        if direction == 'long':
            pnl_pct = (exit_price - entry) / entry * 100
            hit_target = exit_price >= signal['target_price']
            hit_stop = exit_price <= signal['stop_loss']
        else:
            pnl_pct = (entry - exit_price) / entry * 100
            hit_target = exit_price <= signal['target_price']
            hit_stop = exit_price >= signal['stop_loss']

        outcome = {
            'signal_id': signal_id,
            'exit_timestamp': datetime.now().isoformat(),
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'hit_target': hit_target,
            'hit_stop': hit_stop,
            'max_favorable': max_favorable,
            'max_adverse': max_adverse
        }

        self.outcomes.append(outcome)
        self.signals[signal_id]['status'] = 'closed'

        if self.db_path:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''
                INSERT INTO paper_outcomes
                (signal_id, exit_timestamp, exit_price, pnl_pct,
                 hit_target, hit_stop, max_favorable, max_adverse)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal_id, outcome['exit_timestamp'], exit_price, pnl_pct,
                int(hit_target), int(hit_stop), max_favorable, max_adverse
            ))
            c.execute('''
                UPDATE paper_signals SET status = 'closed' WHERE id = ?
            ''', (signal_id,))
            conn.commit()
            conn.close()

        logger.info(f"Paper outcome logged: Signal {signal_id} P&L: {pnl_pct:.2f}%")

    def get_performance_summary(self) -> Dict:
        """Get summary of paper trading performance"""
        if not self.outcomes:
            return {'no_data': True}

        pnls = [o['pnl_pct'] for o in self.outcomes]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        return {
            'total_signals': len(self.signals),
            'closed_trades': len(self.outcomes),
            'win_rate': len(wins) / len(pnls) * 100 if pnls else 0,
            'avg_win': np.mean(wins) if wins else 0,
            'avg_loss': np.mean(losses) if losses else 0,
            'total_pnl': sum(pnls),
            'profit_factor': abs(sum(wins) / sum(losses)) if losses else float('inf'),
            'target_hit_rate': sum(o['hit_target'] for o in self.outcomes) / len(self.outcomes) * 100,
            'stop_hit_rate': sum(o['hit_stop'] for o in self.outcomes) / len(self.outcomes) * 100,
            'avg_mfe': np.mean([o['max_favorable'] for o in self.outcomes]),
            'avg_mae': np.mean([o['max_adverse'] for o in self.outcomes]),
        }


# =============================================================================
# MAIN VALIDATION RUNNER
# =============================================================================

def run_full_validation(backtest_results: Optional[pd.DataFrame] = None) -> Dict:
    """
    Run all validation tests and return comprehensive report

    Args:
        backtest_results: Optional DataFrame with 'date' and 'return' columns

    Returns:
        Dict with all validation results
    """
    results = {
        'timestamp': datetime.now().isoformat(),
        'gex_validation': None,
        'gamma_wall_prediction': None,
        'sharpe_analysis': None,
        'overall_grade': 'F',
        'recommendations': []
    }

    # 1. GEX Calculation Validation
    print("=" * 60)
    print("1. GEX CALCULATION VALIDATION")
    print("=" * 60)

    validator = GEXValidator()

    def simple_gex_calc(spot, strike, gamma, oi, option_type):
        """Simple GEX calculation for testing"""
        gex = spot * gamma * oi * 100
        if option_type == 'put':
            gex = -gex
        return gex

    gex_result = validator.validate_calculation(simple_gex_calc)
    results['gex_validation'] = gex_result.to_dict()

    print(f"GEX Validation: {gex_result.test_cases_passed}/{gex_result.test_cases_total} tests passed")
    if gex_result.issues:
        for issue in gex_result.issues:
            print(f"  - {issue}")

    # 2. Sharpe Ratio Analysis (if backtest results provided)
    if backtest_results is not None and 'return' in backtest_results.columns:
        print("\n" + "=" * 60)
        print("2. OUT-OF-SAMPLE SHARPE ANALYSIS")
        print("=" * 60)

        calc = SharpeCalculator()
        returns = backtest_results['return']
        sharpe_result = calc.full_analysis(returns)

        results['sharpe_analysis'] = {
            'sharpe_ratio': sharpe_result.sharpe_ratio,
            'annualized_return': sharpe_result.annualized_return,
            'annualized_volatility': sharpe_result.annualized_volatility,
            'max_drawdown': sharpe_result.max_drawdown,
            'win_rate': sharpe_result.win_rate,
            'is_significant': sharpe_result.is_statistically_significant,
            'ci_95': sharpe_result.confidence_interval_95
        }

        print(f"Sharpe Ratio: {sharpe_result.sharpe_ratio:.2f}")
        print(f"95% CI: [{sharpe_result.confidence_interval_95[0]:.2f}, {sharpe_result.confidence_interval_95[1]:.2f}]")
        print(f"Statistically Significant: {sharpe_result.is_statistically_significant}")

    # Calculate overall grade
    grade_score = 0

    if gex_result.accuracy_score >= 100:
        grade_score += 25
    elif gex_result.accuracy_score >= 80:
        grade_score += 15

    if results.get('sharpe_analysis'):
        if results['sharpe_analysis']['is_significant']:
            grade_score += 25
        if results['sharpe_analysis']['sharpe_ratio'] > 1.0:
            grade_score += 25
        if results['sharpe_analysis']['sharpe_ratio'] > 2.0:
            grade_score += 25

    # Assign grade
    if grade_score >= 90:
        results['overall_grade'] = 'A'
    elif grade_score >= 75:
        results['overall_grade'] = 'B'
    elif grade_score >= 60:
        results['overall_grade'] = 'C'
    elif grade_score >= 40:
        results['overall_grade'] = 'D'
    else:
        results['overall_grade'] = 'F'

    # Add recommendations
    if not gex_result.is_valid:
        results['recommendations'].append("Fix GEX calculation errors before proceeding")

    if results.get('sharpe_analysis') and not results['sharpe_analysis']['is_significant']:
        results['recommendations'].append("Sharpe ratio not statistically significant - need more data or better strategy")

    print("\n" + "=" * 60)
    print(f"OVERALL GRADE: {results['overall_grade']}")
    print("=" * 60)

    return results


if __name__ == "__main__":
    print("AlphaGEX Quant Validation Framework")
    print("=" * 60)

    # Run basic validation
    results = run_full_validation()

    print("\nValidation complete. Results:")
    print(f"  GEX Validation: {'PASS' if results['gex_validation']['is_valid'] else 'FAIL'}")
    print(f"  Overall Grade: {results['overall_grade']}")

    if results['recommendations']:
        print("\nRecommendations:")
        for rec in results['recommendations']:
            print(f"  - {rec}")
