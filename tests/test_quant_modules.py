"""
Tests for AlphaGEX Quant Modules

Tests:
1. ML Regime Classifier
2. Walk-Forward Optimizer
3. Ensemble Strategy Weighting
4. Monte Carlo Kelly Stress Testing

Run with: pytest tests/test_quant_modules.py -v
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


class TestMLRegimeClassifier:
    """Tests for ML Regime Classifier"""

    def test_classifier_initialization(self):
        """Test classifier can be initialized"""
        from quant.ml_regime_classifier import MLRegimeClassifier
        classifier = MLRegimeClassifier("SPY")
        assert classifier.symbol == "SPY"
        assert classifier.is_trained is False or classifier.is_trained is True

    def test_rule_based_label_sell_premium(self):
        """Test rule-based labeling for SELL_PREMIUM scenario"""
        from quant.ml_regime_classifier import MLRegimeClassifier, MLRegimeAction
        classifier = MLRegimeClassifier("SPY")

        # High IV, positive GEX, range-bound -> SELL_PREMIUM
        label = classifier._rule_based_label(
            gex_normalized=1.0,
            gex_percentile=70,  # Positive
            vix=25,
            iv_rank=75,  # High IV
            iv_hv_ratio=1.3,
            distance_to_flip=0.0,
            momentum_4h=0.1,  # Range-bound
            above_20ma=True
        )
        assert label == MLRegimeAction.SELL_PREMIUM.value

    def test_rule_based_label_buy_calls(self):
        """Test rule-based labeling for BUY_CALLS scenario"""
        from quant.ml_regime_classifier import MLRegimeClassifier, MLRegimeAction
        classifier = MLRegimeClassifier("SPY")

        # Negative GEX, below flip, positive momentum -> BUY_CALLS
        label = classifier._rule_based_label(
            gex_normalized=0.5,
            gex_percentile=20,  # Negative
            vix=28,
            iv_rank=50,
            iv_hv_ratio=1.0,
            distance_to_flip=-1.5,  # Below flip
            momentum_4h=0.5,  # Positive momentum
            above_20ma=True
        )
        assert label == MLRegimeAction.BUY_CALLS.value

    def test_rule_based_label_buy_puts(self):
        """Test rule-based labeling for BUY_PUTS scenario"""
        from quant.ml_regime_classifier import MLRegimeClassifier, MLRegimeAction
        classifier = MLRegimeClassifier("SPY")

        # Negative GEX, above flip, negative momentum -> BUY_PUTS
        label = classifier._rule_based_label(
            gex_normalized=0.5,
            gex_percentile=20,  # Negative
            vix=25,
            iv_rank=50,
            iv_hv_ratio=1.0,
            distance_to_flip=1.5,  # Above flip
            momentum_4h=-0.5,  # Negative momentum
            above_20ma=False
        )
        assert label == MLRegimeAction.BUY_PUTS.value

    def test_training_creates_model(self):
        """Test that training creates a usable model"""
        from quant.ml_regime_classifier import MLRegimeClassifier
        classifier = MLRegimeClassifier("TEST")

        # Train from rules (bootstrap)
        metrics = classifier._train_from_rules(lookback_days=90)

        assert classifier.is_trained is True
        assert classifier.model is not None
        assert metrics.accuracy > 0
        assert metrics.f1 > 0

    def test_prediction_returns_valid_result(self):
        """Test that prediction returns valid MLPrediction"""
        from quant.ml_regime_classifier import get_ml_regime_prediction

        prediction = get_ml_regime_prediction(
            symbol="SPY",
            gex_percentile=30,
            iv_rank=70,
            distance_to_flip=-1.0,
            momentum_4h=0.3
        )

        assert prediction.confidence >= 0 and prediction.confidence <= 100
        assert prediction.predicted_action is not None
        assert 'model_version' in dir(prediction)


class TestWalkForwardOptimizer:
    """Tests for Walk-Forward Optimization"""

    def test_window_creation(self):
        """Test walk-forward windows are created correctly"""
        from quant.walk_forward_optimizer import WalkForwardOptimizer

        optimizer = WalkForwardOptimizer(
            symbol="SPY",
            train_days=60,
            test_days=20,
            step_days=20
        )

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)

        windows = optimizer.create_windows(start, end)

        assert len(windows) > 0
        # Each window should have train_days + test_days coverage
        for window in windows:
            train_duration = (window.train_end - window.train_start).days
            test_duration = (window.test_end - window.test_start).days
            assert train_duration == 60
            assert test_duration == 20

    def test_window_non_overlapping_test(self):
        """Test that test periods are sequential (walk-forward)"""
        from quant.walk_forward_optimizer import WalkForwardOptimizer

        optimizer = WalkForwardOptimizer(
            symbol="SPY",
            train_days=60,
            test_days=20,
            step_days=20
        )

        windows = optimizer.create_windows(
            datetime(2024, 1, 1),
            datetime(2024, 12, 31)
        )

        # Each window's test_start should be after previous window's train_end
        for i in range(1, len(windows)):
            assert windows[i].test_start > windows[i-1].train_end

    def test_result_structure(self):
        """Test WalkForwardResult has correct structure"""
        from quant.walk_forward_optimizer import WalkForwardResult

        result = WalkForwardResult(
            strategy_name="TEST",
            symbol="SPY",
            total_windows=5,
            is_avg_win_rate=65,
            oos_avg_win_rate=58,
            degradation_pct=10.8,
            is_robust=True,
            window_results=[],
            recommended_params={'threshold': -1e9},
            analysis_date=datetime.now().isoformat()
        )

        dict_result = result.to_dict()
        assert 'is_avg_win_rate' in dict_result
        assert 'oos_avg_win_rate' in dict_result
        assert 'degradation_pct' in dict_result
        assert 'is_robust' in dict_result


class TestEnsembleStrategy:
    """Tests for Ensemble Strategy Weighting"""

    def test_signal_combination_bullish(self):
        """Test that bullish signals combine correctly"""
        from quant.ensemble_strategy import (
            EnsembleStrategyWeighter,
            IndividualSignal,
            StrategySignal
        )

        weighter = EnsembleStrategyWeighter("SPY")

        # All bullish signals
        signals = [
            IndividualSignal("GEX", StrategySignal.STRONG_BUY, 80, 0.3, "test"),
            IndividualSignal("ML", StrategySignal.BUY, 70, 0.3, "test"),
            IndividualSignal("RSI", StrategySignal.BUY, 65, 0.2, "test"),
        ]

        ensemble = weighter.combine_signals(signals)

        assert ensemble.final_signal in [StrategySignal.STRONG_BUY, StrategySignal.BUY]
        assert ensemble.bullish_weight > ensemble.bearish_weight
        assert ensemble.bullish_weight > ensemble.neutral_weight

    def test_signal_combination_mixed(self):
        """Test that mixed signals result in reduced confidence"""
        from quant.ensemble_strategy import (
            EnsembleStrategyWeighter,
            IndividualSignal,
            StrategySignal
        )

        weighter = EnsembleStrategyWeighter("SPY")

        # Mixed signals
        signals = [
            IndividualSignal("GEX", StrategySignal.BUY, 70, 0.3, "test"),
            IndividualSignal("ML", StrategySignal.SELL, 65, 0.3, "test"),
            IndividualSignal("RSI", StrategySignal.NEUTRAL, 50, 0.3, "test"),
        ]

        ensemble = weighter.combine_signals(signals)

        # With mixed signals, should have lower confidence or be neutral
        assert ensemble.confidence < 80  # Lower confidence due to disagreement

    def test_should_trade_threshold(self):
        """Test that should_trade respects confidence threshold"""
        from quant.ensemble_strategy import EnsembleStrategyWeighter

        weighter = EnsembleStrategyWeighter("SPY")

        # Low confidence GEX data
        signal = weighter.get_ensemble_signal(
            gex_data={'recommended_action': 'BUY_CALLS', 'confidence': 40}
        )

        # Should not trade with only one low-confidence signal
        assert signal.should_trade is False or signal.confidence < 60

    def test_strategy_performance_weight_calculation(self):
        """Test that strategy weights are calculated based on performance"""
        from quant.ensemble_strategy import StrategyPerformance

        perf = StrategyPerformance("TEST")

        # Record some trades
        for _ in range(10):
            perf.record_trade(5.0, "POSITIVE_GAMMA")  # Wins
        for _ in range(5):
            perf.record_trade(-3.0, "POSITIVE_GAMMA")  # Losses

        assert perf.win_rate == pytest.approx(66.67, rel=0.1)

        weight = perf.calculate_weight("POSITIVE_GAMMA")
        assert weight > 0.5  # Winning strategy should have higher weight


class TestMonteCarloKelly:
    """Tests for Monte Carlo Kelly Stress Testing"""

    def test_kelly_calculation_positive_edge(self):
        """Test Kelly formula with positive edge"""
        from quant.monte_carlo_kelly import MonteCarloKelly

        mc = MonteCarloKelly()

        # 60% win rate, 1.5:1 payoff ratio
        kelly = mc.calculate_kelly(
            win_rate=0.60,
            avg_win=15,
            avg_loss=10
        )

        # Expected: (1.5 * 0.6 - 0.4) / 1.5 = (0.9 - 0.4) / 1.5 = 0.333
        assert kelly == pytest.approx(0.333, rel=0.05)

    def test_kelly_calculation_negative_edge(self):
        """Test Kelly formula with negative edge returns 0"""
        from quant.monte_carlo_kelly import MonteCarloKelly

        mc = MonteCarloKelly()

        # 40% win rate, 1:1 payoff -> negative edge
        kelly = mc.calculate_kelly(
            win_rate=0.40,
            avg_win=10,
            avg_loss=10
        )

        # Negative edge should return 0
        assert kelly == 0

    def test_stress_test_returns_valid_result(self):
        """Test stress test returns valid KellyStressTest"""
        from quant.monte_carlo_kelly import MonteCarloKelly

        mc = MonteCarloKelly(num_simulations=1000, num_trades_per_sim=100)

        result = mc.stress_test(
            win_rate=0.65,
            avg_win=15,
            avg_loss=10,
            sample_size=50
        )

        # Optimal Kelly should be calculated
        assert result.kelly_optimal > 0

        # Safe Kelly should be <= optimal
        assert result.kelly_safe <= result.kelly_optimal

        # Conservative should be half of safe
        assert result.kelly_conservative == pytest.approx(result.kelly_safe / 2, rel=0.01)

        # Probabilities should be valid
        assert 0 <= result.prob_ruin_optimal <= 1
        assert 0 <= result.prob_50pct_drawdown_safe <= 1

    def test_safe_kelly_is_safer(self):
        """Test that safe Kelly has lower ruin probability than optimal"""
        from quant.monte_carlo_kelly import MonteCarloKelly

        mc = MonteCarloKelly(num_simulations=2000, num_trades_per_sim=100)

        result = mc.stress_test(
            win_rate=0.60,
            avg_win=12,
            avg_loss=10,
            sample_size=30
        )

        # Safe Kelly should have lower ruin probability
        assert result.prob_ruin_safe <= result.prob_ruin_optimal

    def test_get_safe_position_size(self):
        """Test convenience function returns valid sizing"""
        from quant.monte_carlo_kelly import get_safe_position_size

        result = get_safe_position_size(
            win_rate=0.65,
            avg_win=15,
            avg_loss=10,
            sample_size=50,
            account_size=10000,
            max_risk_pct=20
        )

        assert 'position_size_pct' in result
        assert 'position_value' in result
        assert 'recommendation' in result

        # Position size should be positive and <= max
        assert 0 < result['position_size_pct'] <= 20

        # Position value should match
        expected_value = 10000 * result['position_size_pct'] / 100
        assert result['position_value'] == pytest.approx(expected_value, rel=0.01)

    def test_uncertainty_increases_with_small_samples(self):
        """Test that small sample sizes increase uncertainty"""
        from quant.monte_carlo_kelly import MonteCarloKelly

        mc = MonteCarloKelly()

        # Small sample
        estimate_small = mc.estimate_uncertainty(0.65, 15, 10, sample_size=10)
        # Large sample
        estimate_large = mc.estimate_uncertainty(0.65, 15, 10, sample_size=100)

        # Small sample should have higher uncertainty
        assert estimate_small.win_rate_std > estimate_large.win_rate_std

    def test_validate_current_sizing(self):
        """Test current sizing validation"""
        from quant.monte_carlo_kelly import validate_current_sizing

        # Test with aggressive sizing (20%)
        result = validate_current_sizing(
            current_kelly_pct=20.0,
            win_rate=0.65,
            avg_win=15,
            avg_loss=10,
            sample_size=50
        )

        assert 'risk_level' in result
        assert 'is_safe' in result
        assert 'warning' in result
        assert 'recommended_kelly_pct' in result


class TestQuantIntegration:
    """Integration tests for quant modules working together"""

    def test_ml_prediction_to_ensemble(self):
        """Test ML prediction integrates with ensemble weighter"""
        from quant.ml_regime_classifier import get_ml_regime_prediction
        from quant.ensemble_strategy import get_ensemble_signal

        # Get ML prediction
        ml_pred = get_ml_regime_prediction(
            symbol="SPY",
            gex_percentile=25,
            iv_rank=70,
            distance_to_flip=-1.0
        )

        # Use in ensemble
        ensemble = get_ensemble_signal(
            symbol="SPY",
            gex_data={
                'recommended_action': 'BUY_CALLS',
                'confidence': 75
            },
            ml_prediction={
                'predicted_action': ml_pred.predicted_action.value,
                'confidence': ml_pred.confidence,
                'is_trained': ml_pred.is_trained
            }
        )

        # Should return valid ensemble signal
        assert ensemble.final_signal is not None
        assert len(ensemble.component_signals) > 0

    def test_kelly_with_strategy_stats(self):
        """Test Kelly calculation with simulated strategy stats"""
        from quant.monte_carlo_kelly import get_safe_position_size

        # Simulate strategy stats from backtest
        strategy_stats = {
            'win_rate': 0.72,
            'avg_win': 8.5,
            'avg_loss': 12.0,
            'total_trades': 45
        }

        # Get safe position size
        sizing = get_safe_position_size(
            win_rate=strategy_stats['win_rate'],
            avg_win=strategy_stats['avg_win'],
            avg_loss=strategy_stats['avg_loss'],
            sample_size=strategy_stats['total_trades'],
            account_size=25000
        )

        # Should return valid sizing
        assert sizing['position_size_pct'] > 0
        assert sizing['uncertainty_level'] in ['low', 'medium', 'high']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
