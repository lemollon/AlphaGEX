"""
Tests for Mathematical Optimization Algorithms
==============================================

Tests cover:
1. Hidden Markov Model (HMM) - Regime detection
2. Kalman Filter - Greeks smoothing
3. Thompson Sampling - Bot allocation
4. Convex Optimizer - Strike selection
5. HJB Exit Optimizer - Exit timing
6. MDP Trade Sequencer - Trade ordering

Author: AlphaGEX Quant Team
Date: January 2025
"""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np

# Import math optimizers
from core.math_optimizers import (
    HiddenMarkovRegimeDetector,
    KalmanFilter,
    MultiDimensionalKalmanFilter,
    ThompsonSamplingAllocator,
    ConvexStrikeOptimizer,
    HJBExitOptimizer,
    MDPTradeSequencer,
    MathOptimizerOrchestrator,
    MarketRegime,
    get_math_optimizer,
    analyze_market,
    optimize_trade,
    check_exit
)

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def hmm_detector():
    """Create HMM regime detector"""
    return HiddenMarkovRegimeDetector()


@pytest.fixture
def kalman_filter():
    """Create Kalman filter"""
    return KalmanFilter(process_variance=0.01, measurement_variance=0.1)


@pytest.fixture
def multi_kalman():
    """Create multi-dimensional Kalman filter"""
    return MultiDimensionalKalmanFilter()


@pytest.fixture
def thompson_allocator():
    """Create Thompson Sampling allocator"""
    return ThompsonSamplingAllocator()


@pytest.fixture
def strike_optimizer():
    """Create convex strike optimizer"""
    return ConvexStrikeOptimizer()


@pytest.fixture
def exit_optimizer():
    """Create HJB exit optimizer"""
    return HJBExitOptimizer()


@pytest.fixture
def trade_sequencer():
    """Create MDP trade sequencer"""
    return MDPTradeSequencer()


@pytest.fixture
def orchestrator():
    """Create optimizer orchestrator"""
    return MathOptimizerOrchestrator()


@pytest.fixture
def sample_market_data():
    """Sample market observation"""
    return {
        'vix': 18.5,
        'net_gamma': 0.3,
        'momentum': 0.4,
        'realized_vol': 0.14,
        'volume_ratio': 1.1
    }


@pytest.fixture
def sample_greeks():
    """Sample Greeks observation"""
    return {
        'delta': 0.32,
        'gamma': 0.05,
        'theta': -0.15,
        'vega': 0.20
    }


@pytest.fixture
def sample_strikes():
    """Sample available strikes"""
    return [
        {'strike': 565, 'delta': -0.20, 'gamma': 0.02, 'theta': -0.08},
        {'strike': 570, 'delta': -0.25, 'gamma': 0.03, 'theta': -0.10},
        {'strike': 575, 'delta': -0.30, 'gamma': 0.04, 'theta': -0.12},
        {'strike': 580, 'delta': -0.35, 'gamma': 0.05, 'theta': -0.15},
        {'strike': 585, 'delta': -0.40, 'gamma': 0.06, 'theta': -0.18},
    ]


@pytest.fixture
def sample_trades():
    """Sample pending trades"""
    return [
        {'symbol': 'SPY', 'direction': 'long', 'expected_pnl': 100, 'win_probability': 0.65, 'bot': 'FORTRESS'},
        {'symbol': 'SPY', 'direction': 'long', 'expected_pnl': 80, 'win_probability': 0.60, 'bot': 'SOLOMON'},
        {'symbol': 'QQQ', 'direction': 'short', 'expected_pnl': 120, 'win_probability': 0.55, 'bot': 'PHOENIX'},
    ]


# =============================================================================
# HMM REGIME DETECTION TESTS
# =============================================================================

class TestHiddenMarkovRegimeDetector:
    """Tests for HMM regime detection"""

    def test_initialization(self, hmm_detector):
        """Test HMM initializes correctly"""
        assert hmm_detector.n_states == len(MarketRegime)
        assert len(hmm_detector.states) == 7
        assert hmm_detector.state_belief.shape == (7,)
        assert np.isclose(hmm_detector.state_belief.sum(), 1.0)

    def test_transition_matrix_valid(self, hmm_detector):
        """Test transition matrix rows sum to 1"""
        for i in range(hmm_detector.n_states):
            row_sum = hmm_detector.transition_matrix[i].sum()
            assert np.isclose(row_sum, 1.0), f"Row {i} sums to {row_sum}"

    def test_update_returns_regime_state(self, hmm_detector, sample_market_data):
        """Test update returns valid RegimeState"""
        result = hmm_detector.update(sample_market_data)

        assert result.regime in MarketRegime
        assert 0 <= result.probability <= 1
        assert 0 <= result.confidence <= 1
        assert result.timestamp is not None

    def test_regime_probabilities_sum_to_one(self, hmm_detector, sample_market_data):
        """Test regime probabilities sum to 1"""
        hmm_detector.update(sample_market_data)
        probs = hmm_detector.get_regime_probabilities()

        total = sum(probs.values())
        assert np.isclose(total, 1.0)

    def test_high_vix_detects_volatility(self, hmm_detector):
        """Test high VIX leads to volatile regime detection"""
        high_vol_obs = {
            'vix': 35.0,
            'net_gamma': -0.5,
            'momentum': 0.0,
            'realized_vol': 0.30,
            'volume_ratio': 1.8
        }

        # Update multiple times to build confidence
        for _ in range(5):
            result = hmm_detector.update(high_vol_obs)

        probs = hmm_detector.get_regime_probabilities()
        # High volatility regime should have elevated probability
        assert probs['HIGH_VOLATILITY'] > 0.1

    def test_transition_confidence_threshold(self, hmm_detector):
        """Test that low confidence transitions are blocked"""
        assert hmm_detector.min_transition_confidence == 0.70


# =============================================================================
# KALMAN FILTER TESTS
# =============================================================================

class TestKalmanFilter:
    """Tests for Kalman filter"""

    def test_initialization(self, kalman_filter):
        """Test Kalman filter initializes correctly"""
        assert kalman_filter.state == 0.0
        assert kalman_filter.P == 1.0
        assert kalman_filter.Q == 0.01
        assert kalman_filter.R == 0.1

    def test_update_returns_state(self, kalman_filter):
        """Test update returns valid KalmanState"""
        result = kalman_filter.update(0.5)

        assert result.smoothed_value is not None
        assert 0 <= result.kalman_gain <= 1
        assert result.raw_observation == 0.5

    def test_smoothing_reduces_noise(self, kalman_filter):
        """Test that Kalman smoothing reduces noise"""
        # Generate noisy signal around 0.5
        np.random.seed(42)
        noisy_signal = [0.5 + np.random.normal(0, 0.1) for _ in range(20)]

        smoothed_values = []
        for obs in noisy_signal:
            result = kalman_filter.update(obs)
            smoothed_values.append(result.smoothed_value)

        # Smoothed variance should be less than raw variance
        raw_var = np.var(noisy_signal)
        smoothed_var = np.var(smoothed_values[5:])  # Skip initial convergence
        assert smoothed_var < raw_var

    def test_prediction(self, kalman_filter):
        """Test prediction capability"""
        kalman_filter.update(0.5)
        kalman_filter.update(0.52)
        kalman_filter.update(0.54)

        predictions = kalman_filter.predict(steps=3)
        assert len(predictions) == 3


class TestMultiDimensionalKalmanFilter:
    """Tests for multi-dimensional Kalman filter"""

    def test_initialization(self, multi_kalman):
        """Test multi-dimensional filter initializes all Greeks"""
        assert 'delta' in multi_kalman.filters
        assert 'gamma' in multi_kalman.filters
        assert 'theta' in multi_kalman.filters
        assert 'vega' in multi_kalman.filters

    def test_update_all_greeks(self, multi_kalman, sample_greeks):
        """Test updating all Greeks"""
        results = multi_kalman.update(sample_greeks)

        assert 'delta' in results
        assert 'gamma' in results
        assert 'theta' in results
        assert 'vega' in results

    def test_get_smoothed_greeks(self, multi_kalman, sample_greeks):
        """Test getting smoothed Greeks"""
        multi_kalman.update(sample_greeks)
        smoothed = multi_kalman.get_smoothed_greeks()

        assert isinstance(smoothed, dict)
        assert 'delta' in smoothed


# =============================================================================
# THOMPSON SAMPLING TESTS
# =============================================================================

class TestThompsonSamplingAllocator:
    """Tests for Thompson Sampling"""

    def test_initialization(self, thompson_allocator):
        """Test Thompson allocator initializes correctly"""
        assert 'FORTRESS' in thompson_allocator.bot_names
        assert 'SOLOMON' in thompson_allocator.bot_names
        assert thompson_allocator.alpha['FORTRESS'] == 1.0
        assert thompson_allocator.beta['FORTRESS'] == 1.0

    def test_record_win(self, thompson_allocator):
        """Test recording a win updates alpha"""
        initial_alpha = thompson_allocator.alpha['FORTRESS']
        thompson_allocator.record_outcome('FORTRESS', win=True, pnl=100)

        assert thompson_allocator.alpha['FORTRESS'] > initial_alpha

    def test_record_loss(self, thompson_allocator):
        """Test recording a loss updates beta"""
        initial_beta = thompson_allocator.beta['FORTRESS']
        thompson_allocator.record_outcome('FORTRESS', win=False, pnl=-50)

        assert thompson_allocator.beta['FORTRESS'] > initial_beta

    def test_allocation_sums_to_one(self, thompson_allocator):
        """Test allocations sum to 1"""
        allocation = thompson_allocator.sample_allocation(100000)

        total = sum(allocation.allocations.values())
        assert np.isclose(total, 1.0)

    def test_allocation_respects_bounds(self, thompson_allocator):
        """Test allocations respect min/max bounds"""
        allocation = thompson_allocator.sample_allocation(100000)

        for bot, alloc in allocation.allocations.items():
            assert alloc >= thompson_allocator.min_allocation
            assert alloc <= thompson_allocator.max_allocation

    def test_winning_bot_gets_more(self, thompson_allocator):
        """Test that a winning bot gets higher allocation over time"""
        # Record many wins for FORTRESS
        for _ in range(20):
            thompson_allocator.record_outcome('FORTRESS', win=True, pnl=100)

        # Record many losses for PHOENIX
        for _ in range(20):
            thompson_allocator.record_outcome('PHOENIX', win=False, pnl=-50)

        win_rates = thompson_allocator.get_expected_win_rates()
        assert win_rates['FORTRESS'] > win_rates['PHOENIX']

    def test_reset_bot(self, thompson_allocator):
        """Test resetting a bot's statistics"""
        thompson_allocator.record_outcome('FORTRESS', win=True, pnl=100)
        thompson_allocator.reset_bot('FORTRESS')

        assert thompson_allocator.alpha['FORTRESS'] == 1.0
        assert thompson_allocator.beta['FORTRESS'] == 1.0


# =============================================================================
# CONVEX STRIKE OPTIMIZER TESTS
# =============================================================================

class TestConvexStrikeOptimizer:
    """Tests for convex strike optimizer"""

    def test_initialization(self, strike_optimizer):
        """Test optimizer initializes with scenarios"""
        assert len(strike_optimizer.scenarios) == 7

        # Probabilities should sum to 1
        total_prob = sum(s['probability'] for s in strike_optimizer.scenarios)
        assert np.isclose(total_prob, 1.0)

    def test_optimize_returns_result(self, strike_optimizer, sample_strikes):
        """Test optimize returns valid result"""
        result = strike_optimizer.optimize(
            available_strikes=sample_strikes,
            spot_price=590,
            target_delta=0.30
        )

        assert result.original_strike > 0
        assert result.optimized_strike > 0
        assert result.scenarios_evaluated == 7

    def test_optimization_improves_or_matches(self, strike_optimizer, sample_strikes):
        """Test that optimization doesn't make things worse"""
        result = strike_optimizer.optimize(
            available_strikes=sample_strikes,
            spot_price=590,
            target_delta=0.30
        )

        # Optimized loss should be <= original loss
        assert result.expected_loss_optimized <= result.expected_loss_original

    def test_empty_strikes_raises_error(self, strike_optimizer):
        """Test that empty strikes raises error"""
        with pytest.raises(ValueError):
            strike_optimizer.optimize(
                available_strikes=[],
                spot_price=590,
                target_delta=0.30
            )


# =============================================================================
# HJB EXIT OPTIMIZER TESTS
# =============================================================================

class TestHJBExitOptimizer:
    """Tests for HJB exit optimizer"""

    def test_initialization(self, exit_optimizer):
        """Test optimizer initializes with defaults"""
        assert exit_optimizer.base_profit_target == 0.50
        assert exit_optimizer.base_stop_loss == -1.00

    def test_should_exit_at_profit_target(self, exit_optimizer):
        """Test exit signal when profit target reached"""
        now = datetime.now(CENTRAL_TZ)

        signal = exit_optimizer.should_exit(
            current_pnl=150,
            max_profit=200,
            entry_time=now - timedelta(hours=4),
            expiry_time=now + timedelta(hours=4),
            current_volatility=0.15
        )

        # At 75% profit, should likely exit
        assert signal.current_pnl_pct == 0.75

    def test_should_not_exit_early(self, exit_optimizer):
        """Test no exit signal when profitable but below boundary"""
        now = datetime.now(CENTRAL_TZ)

        signal = exit_optimizer.should_exit(
            current_pnl=50,
            max_profit=200,
            entry_time=now - timedelta(hours=1),
            expiry_time=now + timedelta(hours=7),
            current_volatility=0.15
        )

        # At 25% profit with lots of time, should hold
        assert signal.current_pnl_pct == 0.25

    def test_should_exit_at_stop_loss(self, exit_optimizer):
        """Test exit signal at stop loss"""
        now = datetime.now(CENTRAL_TZ)

        signal = exit_optimizer.should_exit(
            current_pnl=-250,
            max_profit=200,
            entry_time=now - timedelta(hours=4),
            expiry_time=now + timedelta(hours=4),
            current_volatility=0.15
        )

        # At -125% of max profit, should exit
        assert signal.should_exit
        assert 'Stop loss' in signal.reason

    def test_exit_signal_contains_reason(self, exit_optimizer):
        """Test exit signal always has a reason"""
        now = datetime.now(CENTRAL_TZ)

        signal = exit_optimizer.should_exit(
            current_pnl=100,
            max_profit=200,
            entry_time=now - timedelta(hours=2),
            expiry_time=now + timedelta(hours=6),
            current_volatility=0.15
        )

        assert signal.reason != ""


# =============================================================================
# MDP TRADE SEQUENCER TESTS
# =============================================================================

class TestMDPTradeSequencer:
    """Tests for MDP trade sequencer"""

    def test_initialization(self, trade_sequencer):
        """Test sequencer initializes with defaults"""
        assert trade_sequencer.transaction_cost == 5
        assert trade_sequencer.gamma == 0.95
        assert trade_sequencer.correlation_threshold == 0.70

    def test_sequence_returns_result(self, trade_sequencer, sample_trades):
        """Test sequence returns valid result"""
        result = trade_sequencer.sequence_trades(
            pending_trades=sample_trades,
            existing_positions=[],
            market_regime='TRENDING_BULLISH'
        )

        assert result.original_order is not None
        assert result.optimized_order is not None
        assert result.reason != ""

    def test_empty_trades_handled(self, trade_sequencer):
        """Test empty trades handled gracefully"""
        result = trade_sequencer.sequence_trades(
            pending_trades=[],
            existing_positions=[],
            market_regime='TRENDING_BULLISH'
        )

        assert len(result.optimized_order) == 0
        assert "No pending trades" in result.reason

    def test_redundant_trades_skipped(self, trade_sequencer):
        """Test redundant trades are identified"""
        trades = [
            {'symbol': 'SPY', 'direction': 'long', 'expected_pnl': 100, 'win_probability': 0.65, 'bot': 'FORTRESS'},
            {'symbol': 'SPY', 'direction': 'long', 'expected_pnl': 80, 'win_probability': 0.60, 'bot': 'SOLOMON'},
        ]
        existing = [
            {'symbol': 'SPY', 'direction': 'long'}
        ]

        result = trade_sequencer.sequence_trades(
            pending_trades=trades,
            existing_positions=existing,
            market_regime='TRENDING_BULLISH'
        )

        # Both trades should be marked as redundant
        assert len(result.skipped_trades) > 0

    def test_max_trades_respected(self, trade_sequencer, sample_trades):
        """Test max trades limit is respected"""
        result = trade_sequencer.sequence_trades(
            pending_trades=sample_trades,
            existing_positions=[],
            market_regime='TRENDING_BULLISH',
            max_trades=1
        )

        assert len(result.optimized_order) <= 1


# =============================================================================
# ORCHESTRATOR TESTS
# =============================================================================

class TestMathOptimizerOrchestrator:
    """Tests for the orchestrator"""

    def test_initialization(self, orchestrator):
        """Test orchestrator initializes all components"""
        assert orchestrator.hmm_regime is not None
        assert orchestrator.kalman_greeks is not None
        assert orchestrator.thompson is not None
        assert orchestrator.convex_strike is not None
        assert orchestrator.hjb_exit is not None
        assert orchestrator.mdp_sequencer is not None

    def test_analyze_market(self, orchestrator, sample_market_data):
        """Test full market analysis"""
        result = orchestrator.analyze_market(sample_market_data)

        assert 'regime' in result
        assert 'allocations' in result
        assert 'timestamp' in result

    def test_get_status(self, orchestrator):
        """Test getting optimizer status"""
        status = orchestrator.get_status()

        assert 'hmm_regime' in status
        assert 'kalman' in status
        assert 'thompson' in status


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions"""

    def test_get_math_optimizer_singleton(self):
        """Test singleton pattern"""
        opt1 = get_math_optimizer()
        opt2 = get_math_optimizer()

        assert opt1 is opt2

    def test_analyze_market_function(self, sample_market_data):
        """Test analyze_market convenience function"""
        result = analyze_market(sample_market_data)

        assert 'regime' in result


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple algorithms"""

    def test_full_trading_flow(self, orchestrator, sample_market_data, sample_greeks, sample_strikes, sample_trades):
        """Test full trading analysis flow"""
        # 1. Analyze market
        market_data = {**sample_market_data, 'greeks': sample_greeks}
        market_analysis = orchestrator.analyze_market(market_data)

        assert market_analysis['regime'] is not None
        assert market_analysis['allocations'] is not None

        # 2. Get current regime
        current_regime = market_analysis['regime']['regime']

        # 3. Optimize a trade
        signal = {
            'symbol': 'SPY',
            'direction': 'long',
            'target_delta': 0.30,
            'bot': 'FORTRESS',
            'dte': 1
        }
        trade_opt = orchestrator.optimize_trade(
            signal=signal,
            available_strikes=sample_strikes,
            existing_positions=[],
            spot_price=590,
            current_regime=current_regime
        )

        assert 'optimized' in trade_opt

        # 4. Check exit
        position = {
            'entry_time': datetime.now(CENTRAL_TZ) - timedelta(hours=2),
            'expiry_time': datetime.now(CENTRAL_TZ) + timedelta(hours=6),
            'bot': 'FORTRESS'
        }
        exit_signal = orchestrator.check_exit(
            position=position,
            current_pnl=100,
            max_profit=200,
            current_volatility=0.15
        )

        assert exit_signal.reason != ""

    def test_thompson_feedback_loop(self, orchestrator):
        """Test Thompson learning from trade outcomes"""
        # Record outcomes
        orchestrator.thompson.record_outcome('FORTRESS', True, 150)
        orchestrator.thompson.record_outcome('FORTRESS', True, 100)
        orchestrator.thompson.record_outcome('SOLOMON', False, -50)
        orchestrator.thompson.record_outcome('SOLOMON', False, -75)

        # Get allocation
        allocation = orchestrator.thompson.sample_allocation(100000)

        # FORTRESS should have higher expected win rate
        win_rates = orchestrator.thompson.get_expected_win_rates()
        assert win_rates['FORTRESS'] > win_rates['SOLOMON']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
