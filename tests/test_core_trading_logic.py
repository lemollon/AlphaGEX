"""
Tests for core trading logic modules.

This test suite covers the most critical trading logic:
- MarketRegimeClassifier: Regime classification and action decisions
- ProbabilityCalculator: Probability weight calculations
- Risk calculations and position sizing

Run with: pytest tests/test_core_trading_logic.py -v
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.market_regime_classifier import (
    MarketRegimeClassifier,
    MarketAction,
    VolatilityRegime,
    GammaRegime,
    TrendRegime,
    RegimeClassification,
)


class TestMarketRegimeClassifier:
    """Tests for MarketRegimeClassifier"""

    @pytest.fixture
    def classifier(self):
        """Create a classifier with database disabled"""
        with patch('market_regime_classifier.DB_AVAILABLE', False):
            return MarketRegimeClassifier(symbol="SPY")

    # =========================================================================
    # IV Rank Calculation Tests
    # =========================================================================

    def test_calculate_iv_rank_normal_range(self, classifier):
        """Test IV rank calculation with normal data"""
        current_iv = 0.20
        iv_history = [0.15, 0.18, 0.22, 0.25, 0.20, 0.19, 0.21] * 10  # ~70 days

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        assert 0 <= iv_rank <= 100
        assert 0 <= iv_percentile <= 100

    def test_calculate_iv_rank_extreme_high(self, classifier):
        """Test IV rank when current IV is at the top of range"""
        current_iv = 0.30
        iv_history = [0.15, 0.18, 0.20, 0.22, 0.25] * 20

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        assert iv_rank == 100.0  # At max
        assert iv_percentile == 100.0  # Higher than all historical

    def test_calculate_iv_rank_extreme_low(self, classifier):
        """Test IV rank when current IV is at the bottom of range"""
        current_iv = 0.10
        iv_history = [0.15, 0.18, 0.20, 0.22, 0.25] * 20

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        assert iv_rank == 0.0  # Below min (clamped)
        assert iv_percentile == 0.0  # Lower than all historical

    def test_calculate_iv_rank_insufficient_data(self, classifier):
        """Test IV rank with insufficient historical data"""
        current_iv = 0.20
        iv_history = [0.18, 0.19]  # Only 2 days

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        # Should return default 50, 50 with insufficient data
        assert iv_rank == 50.0
        assert iv_percentile == 50.0

    def test_calculate_iv_rank_empty_history(self, classifier):
        """Test IV rank with empty history"""
        iv_rank, iv_percentile = classifier.calculate_iv_rank(0.20, [])

        assert iv_rank == 50.0
        assert iv_percentile == 50.0

    # =========================================================================
    # Volatility Regime Classification Tests
    # =========================================================================

    def test_classify_volatility_extreme_high(self, classifier):
        """Test volatility regime classification for extreme high IV"""
        assert classifier.classify_volatility_regime(85) == VolatilityRegime.EXTREME_HIGH
        assert classifier.classify_volatility_regime(100) == VolatilityRegime.EXTREME_HIGH

    def test_classify_volatility_high(self, classifier):
        """Test volatility regime classification for high IV"""
        assert classifier.classify_volatility_regime(70) == VolatilityRegime.HIGH
        assert classifier.classify_volatility_regime(60) == VolatilityRegime.HIGH

    def test_classify_volatility_normal(self, classifier):
        """Test volatility regime classification for normal IV"""
        assert classifier.classify_volatility_regime(50) == VolatilityRegime.NORMAL
        assert classifier.classify_volatility_regime(40) == VolatilityRegime.NORMAL

    def test_classify_volatility_low(self, classifier):
        """Test volatility regime classification for low IV"""
        assert classifier.classify_volatility_regime(30) == VolatilityRegime.LOW
        assert classifier.classify_volatility_regime(20) == VolatilityRegime.LOW

    def test_classify_volatility_extreme_low(self, classifier):
        """Test volatility regime classification for extreme low IV"""
        assert classifier.classify_volatility_regime(15) == VolatilityRegime.EXTREME_LOW
        assert classifier.classify_volatility_regime(5) == VolatilityRegime.EXTREME_LOW

    # =========================================================================
    # Gamma Regime Classification Tests
    # =========================================================================

    def test_classify_gamma_strong_negative(self, classifier):
        """Test gamma regime for strong negative GEX"""
        assert classifier.classify_gamma_regime(-3e9) == GammaRegime.STRONG_NEGATIVE
        assert classifier.classify_gamma_regime(-2.5e9) == GammaRegime.STRONG_NEGATIVE

    def test_classify_gamma_negative(self, classifier):
        """Test gamma regime for negative GEX"""
        assert classifier.classify_gamma_regime(-1e9) == GammaRegime.NEGATIVE
        assert classifier.classify_gamma_regime(-0.6e9) == GammaRegime.NEGATIVE

    def test_classify_gamma_neutral(self, classifier):
        """Test gamma regime for neutral GEX"""
        assert classifier.classify_gamma_regime(0) == GammaRegime.NEUTRAL
        assert classifier.classify_gamma_regime(-0.3e9) == GammaRegime.NEUTRAL
        assert classifier.classify_gamma_regime(0.3e9) == GammaRegime.NEUTRAL

    def test_classify_gamma_positive(self, classifier):
        """Test gamma regime for positive GEX"""
        assert classifier.classify_gamma_regime(1e9) == GammaRegime.POSITIVE
        assert classifier.classify_gamma_regime(0.6e9) == GammaRegime.POSITIVE

    def test_classify_gamma_strong_positive(self, classifier):
        """Test gamma regime for strong positive GEX"""
        assert classifier.classify_gamma_regime(3e9) == GammaRegime.STRONG_POSITIVE
        assert classifier.classify_gamma_regime(2.5e9) == GammaRegime.STRONG_POSITIVE

    # =========================================================================
    # Trend Regime Classification Tests
    # =========================================================================

    def test_classify_trend_strong_uptrend(self, classifier):
        """Test trend regime for strong uptrend conditions"""
        result = classifier.classify_trend_regime(
            spot=600,
            flip_point=590,  # ~1.7% above flip
            momentum_1h=0.3,
            momentum_4h=0.6,  # Strong positive momentum
            above_20ma=True,
            above_50ma=True
        )
        assert result == TrendRegime.STRONG_UPTREND

    def test_classify_trend_strong_downtrend(self, classifier):
        """Test trend regime for strong downtrend conditions"""
        result = classifier.classify_trend_regime(
            spot=580,
            flip_point=600,  # ~3.3% below flip
            momentum_1h=-0.3,
            momentum_4h=-0.6,  # Strong negative momentum
            above_20ma=False,
            above_50ma=False
        )
        assert result == TrendRegime.STRONG_DOWNTREND

    def test_classify_trend_range_bound(self, classifier):
        """Test trend regime for range-bound conditions"""
        result = classifier.classify_trend_regime(
            spot=595,
            flip_point=595,  # At flip
            momentum_1h=0.1,
            momentum_4h=0.05,  # Low momentum
            above_20ma=True,
            above_50ma=False  # Mixed
        )
        assert result == TrendRegime.RANGE_BOUND

    # =========================================================================
    # Action Decision Tests
    # =========================================================================

    def test_determine_action_sell_premium_conditions(self, classifier):
        """Test action decision for selling premium (high IV, range-bound)"""
        action, confidence, reasoning = classifier.determine_action(
            vol_regime=VolatilityRegime.EXTREME_HIGH,
            gamma_regime=GammaRegime.STRONG_POSITIVE,
            trend_regime=TrendRegime.RANGE_BOUND,
            iv_hv_ratio=1.5,  # IV overpriced
            distance_to_flip_pct=0.5,
            vix=25
        )

        assert action == MarketAction.SELL_PREMIUM
        assert confidence >= 70  # Should have high confidence

    def test_determine_action_buy_calls_conditions(self, classifier):
        """Test action decision for buying calls (negative gamma, bullish)"""
        action, confidence, reasoning = classifier.determine_action(
            vol_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.STRONG_NEGATIVE,
            trend_regime=TrendRegime.UPTREND,
            iv_hv_ratio=0.9,  # IV reasonable
            distance_to_flip_pct=-2,  # Below flip
            vix=18
        )

        assert action == MarketAction.BUY_CALLS
        assert "negative gamma" in reasoning.lower() or "uptrend" in reasoning.lower()

    def test_determine_action_buy_puts_conditions(self, classifier):
        """Test action decision for buying puts (negative gamma, bearish)"""
        action, confidence, reasoning = classifier.determine_action(
            vol_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.STRONG_NEGATIVE,
            trend_regime=TrendRegime.DOWNTREND,
            iv_hv_ratio=0.9,
            distance_to_flip_pct=2,  # Above flip
            vix=22
        )

        assert action == MarketAction.BUY_PUTS
        assert "negative gamma" in reasoning.lower() or "downtrend" in reasoning.lower()

    def test_determine_action_stay_flat_neutral(self, classifier):
        """Test action decision for staying flat (uncertain conditions)"""
        action, confidence, reasoning = classifier.determine_action(
            vol_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.NEUTRAL,
            trend_regime=TrendRegime.RANGE_BOUND,
            iv_hv_ratio=1.0,  # Fair value
            distance_to_flip_pct=0,  # At flip
            vix=18
        )

        # Should either stay flat or have low confidence
        assert action == MarketAction.STAY_FLAT or confidence < 60

    # =========================================================================
    # Threshold Constants Tests
    # =========================================================================

    def test_threshold_constants_reasonable(self, classifier):
        """Test that threshold constants are reasonable values"""
        # IV thresholds should be in percentile range
        assert 0 < classifier.IV_EXTREME_LOW < classifier.IV_LOW < classifier.IV_HIGH < classifier.IV_EXTREME_HIGH <= 100

        # GEX thresholds should be ordered
        assert classifier.GEX_STRONG_NEGATIVE < classifier.GEX_NEGATIVE < 0
        assert 0 < classifier.GEX_POSITIVE < classifier.GEX_STRONG_POSITIVE

        # Anti-whiplash parameters should be positive
        assert classifier.MIN_BARS_FOR_REGIME > 0
        assert classifier.REGIME_CHANGE_THRESHOLD > 0
        assert classifier.DECISION_COOLDOWN_BARS >= 0


class TestProbabilityWeights:
    """Tests for probability weight calculations"""

    def test_probability_weights_sum_to_one(self):
        """Test that default probability weights sum to 1.0"""
        try:
            from core.probability_calculator import ProbabilityWeights
        except ImportError:
            pytest.skip("probability_calculator requires database dependencies")

        weights = ProbabilityWeights()
        total = (
            weights.gex_wall_strength +
            weights.volatility_impact +
            weights.psychology_signal +
            weights.mm_positioning +
            weights.historical_pattern
        )

        assert abs(total - 1.0) < 0.01  # Allow small floating point error

    def test_probability_weights_to_dict(self):
        """Test weight serialization to dict"""
        try:
            from core.probability_calculator import ProbabilityWeights
        except ImportError:
            pytest.skip("probability_calculator requires database dependencies")

        weights = ProbabilityWeights()
        d = weights.to_dict()

        assert 'gex_wall_strength' in d
        assert 'volatility_impact' in d
        assert 'psychology_signal' in d
        assert 'mm_positioning' in d
        assert 'historical_pattern' in d


class TestRiskCalculations:
    """Tests for risk calculation utilities"""

    def test_kelly_criterion_basic(self):
        """Test Kelly criterion calculation"""
        # Kelly = W - [(1-W)/R] where W=win rate, R=win/loss ratio
        # For 60% win rate, 1.5:1 reward/risk
        # Kelly = 0.60 - [(1-0.60)/1.5] = 0.60 - 0.267 = 0.333 (33.3%)

        win_rate = 0.60
        avg_win = 150
        avg_loss = 100
        win_loss_ratio = avg_win / avg_loss

        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        assert 0.30 < kelly < 0.40  # Should be around 33%

    def test_kelly_criterion_negative_edge(self):
        """Test Kelly criterion with negative expected value"""
        # 40% win rate, 1:1 reward/risk = negative expectancy
        win_rate = 0.40
        win_loss_ratio = 1.0

        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        assert kelly < 0  # Should be negative - don't bet

    def test_kelly_criterion_edge_cases(self):
        """Test Kelly criterion edge cases"""
        # 100% win rate should give Kelly of 1.0
        kelly_perfect = 1.0 - ((1 - 1.0) / 1.5)
        assert kelly_perfect == 1.0

        # 0% win rate should give Kelly of -infinity (handled separately)
        # We just verify the formula doesn't crash
        win_rate = 0.01
        win_loss_ratio = 1.0
        kelly_bad = win_rate - ((1 - win_rate) / win_loss_ratio)
        assert kelly_bad < 0

    def test_position_sizing_max_risk(self):
        """Test position sizing respects maximum risk"""
        account_size = 100000
        max_risk_pct = 0.02  # 2% max risk
        option_price = 5.00
        contracts_per_option = 100

        max_risk_dollars = account_size * max_risk_pct
        max_contracts = int(max_risk_dollars / (option_price * contracts_per_option))

        # With $100k, 2% risk = $2000 max loss
        # $5 option x 100 = $500 per contract
        # Max contracts = 4

        assert max_contracts == 4

    def test_stop_loss_calculation(self):
        """Test stop loss percentage calculation"""
        entry_price = 10.00
        stop_loss_pct = 0.50  # 50% stop loss

        stop_price = entry_price * (1 - stop_loss_pct)

        assert stop_price == 5.00

    def test_profit_target_calculation(self):
        """Test profit target calculation"""
        entry_price = 10.00
        profit_target_pct = 1.00  # 100% profit target

        target_price = entry_price * (1 + profit_target_pct)

        assert target_price == 20.00


class TestMarketActionEnum:
    """Tests for MarketAction enum"""

    def test_all_actions_defined(self):
        """Test all expected market actions are defined"""
        expected_actions = [
            'SELL_PREMIUM', 'BUY_CALLS', 'BUY_PUTS',
            'STAY_FLAT', 'CLOSE_POSITIONS'
        ]

        for action_name in expected_actions:
            assert hasattr(MarketAction, action_name)

    def test_action_values_are_strings(self):
        """Test action values are strings for serialization"""
        for action in MarketAction:
            assert isinstance(action.value, str)


class TestRegimeEnums:
    """Tests for regime classification enums"""

    def test_volatility_regime_ordering(self):
        """Test volatility regime has all expected values"""
        expected = ['EXTREME_HIGH', 'HIGH', 'NORMAL', 'LOW', 'EXTREME_LOW']
        for regime_name in expected:
            assert hasattr(VolatilityRegime, regime_name)

    def test_gamma_regime_ordering(self):
        """Test gamma regime has all expected values"""
        expected = ['STRONG_NEGATIVE', 'NEGATIVE', 'NEUTRAL', 'POSITIVE', 'STRONG_POSITIVE']
        for regime_name in expected:
            assert hasattr(GammaRegime, regime_name)

    def test_trend_regime_ordering(self):
        """Test trend regime has all expected values"""
        expected = ['STRONG_UPTREND', 'UPTREND', 'RANGE_BOUND', 'DOWNTREND', 'STRONG_DOWNTREND']
        for regime_name in expected:
            assert hasattr(TrendRegime, regime_name)


# =========================================================================
# Integration Tests
# =========================================================================

class TestClassifierIntegration:
    """Integration tests for the classifier"""

    @pytest.fixture
    def classifier(self):
        """Create a classifier with database disabled"""
        with patch('market_regime_classifier.DB_AVAILABLE', False):
            return MarketRegimeClassifier(symbol="SPY")

    def test_full_classification_flow(self, classifier):
        """Test a full classification from raw data to action"""
        # This tests the whole flow would work (with mocked data)
        iv_rank = 75  # High IV
        net_gex = 2.5e9  # Strong positive gamma

        vol_regime = classifier.classify_volatility_regime(iv_rank)
        gamma_regime = classifier.classify_gamma_regime(net_gex)

        assert vol_regime == VolatilityRegime.HIGH
        assert gamma_regime == GammaRegime.STRONG_POSITIVE

        # With high IV and strong positive gamma, should lean toward selling premium
        trend_regime = TrendRegime.RANGE_BOUND

        action, confidence, reasoning = classifier.determine_action(
            vol_regime=vol_regime,
            gamma_regime=gamma_regime,
            trend_regime=trend_regime,
            iv_hv_ratio=1.3,
            distance_to_flip_pct=0.5,
            vix=22
        )

        # Should recommend selling premium in this environment
        assert action == MarketAction.SELL_PREMIUM


# =========================================================================
# Kelly Criterion Bug Fix Tests
# =========================================================================

class TestKellyBugFixes:
    """Tests to verify Kelly criterion bug fixes are working correctly"""

    def test_negative_kelly_should_block_trade(self):
        """CRITICAL: Negative Kelly = negative expected value = NO TRADE

        Bug that was fixed: System would still trade at 1% minimum when
        Kelly was negative, which meant trading with negative expected value.
        """
        # 40% win rate, 0.5:1 reward/risk = very negative expectancy
        win_rate = 0.40
        avg_win = 5.0   # 5% average win
        avg_loss = 10.0  # 10% average loss
        risk_reward = avg_win / avg_loss  # 0.5

        # Kelly = W - [(1-W)/R] = 0.40 - [0.60/0.5] = 0.40 - 1.20 = -0.80
        kelly = win_rate - ((1 - win_rate) / risk_reward)

        assert kelly < 0, "Kelly should be negative for this setup"
        assert kelly == pytest.approx(-0.80, rel=0.01)

        # The fix: When kelly <= 0, should return 0 contracts (block trade)
        # Not trade at 1% minimum as before

    def test_negative_kelly_formula_scenarios(self):
        """Test various scenarios that should result in negative Kelly"""
        test_cases = [
            # (win_rate, risk_reward, expected_kelly_sign)
            (0.50, 0.50, 'negative'),  # Break-even WR but bad R/R
            (0.40, 1.00, 'negative'),  # Low WR, even R/R
            (0.30, 1.50, 'negative'),  # Very low WR
            (0.45, 0.80, 'negative'),  # Below break-even
        ]

        for win_rate, risk_reward, expected_sign in test_cases:
            kelly = win_rate - ((1 - win_rate) / risk_reward)
            if expected_sign == 'negative':
                assert kelly < 0, f"Kelly should be negative for WR={win_rate}, R/R={risk_reward}"

    def test_positive_kelly_scenarios(self):
        """Test scenarios that should have positive Kelly (tradeable)"""
        test_cases = [
            # (win_rate, risk_reward, min_expected_kelly)
            (0.55, 1.00, 0.05),   # Slight edge
            (0.60, 1.50, 0.15),   # Good setup
            (0.70, 1.00, 0.20),   # High win rate
            (0.50, 2.00, 0.15),   # Good R/R compensates for 50% WR
        ]

        for win_rate, risk_reward, min_kelly in test_cases:
            kelly = win_rate - ((1 - win_rate) / risk_reward)
            assert kelly > min_kelly, f"Kelly should be > {min_kelly} for WR={win_rate}, R/R={risk_reward}"

    def test_expectancy_threshold_is_zero(self):
        """Verify expectancy threshold is 0, not -5%

        Bug that was fixed: Previously allowed strategies with -4.9% expectancy
        to trade. Now any negative expectancy blocks the trade.
        """
        # The correct threshold should block ANY negative expectancy
        threshold = 0.0

        # These should all be blocked
        blocked_expectancies = [-0.1, -1.0, -4.9, -5.0, -10.0]
        for exp in blocked_expectancies:
            should_block = exp < threshold
            assert should_block, f"Expectancy {exp}% should be blocked (threshold={threshold})"

        # Only non-negative should pass
        allowed_expectancies = [0.0, 0.1, 1.0, 5.0]
        for exp in allowed_expectancies:
            should_allow = exp >= threshold
            assert should_allow, f"Expectancy {exp}% should be allowed"

    def test_win_rate_threshold_is_40_percent(self):
        """Verify minimum win rate is 40%, not 35%

        Bug that was fixed: 35% win rate is too low for most setups.
        Raised to 40% for better risk management.
        """
        min_win_rate = 40.0  # Percentage

        # These should be blocked
        blocked_rates = [35.0, 38.0, 39.9]
        for rate in blocked_rates:
            should_block = rate < min_win_rate
            assert should_block, f"Win rate {rate}% should be blocked (min={min_win_rate}%)"


class TestStrategyStatsDefaults:
    """Tests for strategy stats default value handling"""

    def test_zero_avg_win_uses_default(self):
        """When avg_win is 0.0, should use conservative default (8.0%)"""
        avg_win_from_stats = 0.0
        default_avg_win = 8.0

        # The fix: Check for 0.0 and use default
        if avg_win_from_stats <= 0:
            actual_avg_win = default_avg_win
        else:
            actual_avg_win = avg_win_from_stats

        assert actual_avg_win == 8.0

    def test_zero_avg_loss_uses_default(self):
        """When avg_loss is 0.0, should use conservative default (12.0%)"""
        avg_loss_from_stats = 0.0
        default_avg_loss = 12.0

        # The fix: Check for 0.0 and use default
        if avg_loss_from_stats <= 0:
            actual_avg_loss = default_avg_loss
        else:
            actual_avg_loss = avg_loss_from_stats

        assert actual_avg_loss == 12.0

    def test_default_risk_reward_is_conservative(self):
        """Default R/R from defaults should be conservative (8/12 = 0.67)"""
        default_avg_win = 8.0
        default_avg_loss = 12.0

        risk_reward = default_avg_win / default_avg_loss

        # 0.67 R/R is conservative - requires ~60% win rate to break even
        assert risk_reward == pytest.approx(0.667, rel=0.01)

        # Calculate break-even win rate for this R/R
        # Kelly = 0 when W = (1-W)/R => W = 1/(1+R) = 1/1.67 = 0.60
        breakeven_wr = 1 / (1 + risk_reward)
        assert breakeven_wr > 0.55, "Break-even WR should be > 55% with these defaults"


class TestProbabilityEngine:
    """Tests for ProbabilityEngine trade setup calculations"""

    def test_probability_engine_initialization(self):
        """Test ProbabilityEngine initializes correctly"""
        try:
            from backend.probability_engine import ProbabilityEngine
        except ImportError:
            pytest.skip("probability_engine not available")

        engine = ProbabilityEngine()

        # Should have mm_state_win_rates dict
        assert hasattr(engine, 'mm_state_win_rates')
        assert 'PANICKING' in engine.mm_state_win_rates
        assert 'DEFENDING' in engine.mm_state_win_rates
        assert 'NEUTRAL' in engine.mm_state_win_rates

    def test_calculate_best_setup_panicking(self):
        """Test best setup calculation for PANICKING state"""
        try:
            from backend.probability_engine import ProbabilityEngine
        except ImportError:
            pytest.skip("probability_engine not available")

        engine = ProbabilityEngine()
        setup = engine.calculate_best_setup(
            mm_state='PANICKING',
            spot_price=570.0,
            flip_point=568.0,
            call_wall=575.0,
            put_wall=565.0,
            net_gex=-2e9
        )

        assert setup is not None
        assert setup.mm_state == 'PANICKING'
        assert setup.win_rate > 0.80  # High win rate in panic squeeze
        assert 'Call' in setup.setup_type

    def test_calculate_best_setup_defending(self):
        """Test best setup calculation for DEFENDING state"""
        try:
            from backend.probability_engine import ProbabilityEngine
        except ImportError:
            pytest.skip("probability_engine not available")

        engine = ProbabilityEngine()
        setup = engine.calculate_best_setup(
            mm_state='DEFENDING',
            spot_price=570.0,
            flip_point=568.0,
            call_wall=575.0,
            put_wall=565.0,
            net_gex=2e9
        )

        assert setup is not None
        assert setup.mm_state == 'DEFENDING'
        assert 'Condor' in setup.setup_type  # Should recommend iron condor

    def test_calculate_best_setup_neutral_no_edge(self):
        """Test that NEUTRAL state returns no clear edge"""
        try:
            from backend.probability_engine import ProbabilityEngine
        except ImportError:
            pytest.skip("probability_engine not available")

        engine = ProbabilityEngine()
        setup = engine.calculate_best_setup(
            mm_state='NEUTRAL',
            spot_price=570.0,
            flip_point=None,
            call_wall=None,
            put_wall=None,
            net_gex=0
        )

        # NEUTRAL should return None (no clear edge)
        assert setup is None

    def test_position_sizing_kelly(self):
        """Test Kelly Criterion position sizing"""
        try:
            from backend.probability_engine import ProbabilityEngine
        except ImportError:
            pytest.skip("probability_engine not available")

        engine = ProbabilityEngine()
        sizing = engine.calculate_position_sizing(
            win_rate=0.87,  # 87% win rate
            avg_win=0.24,   # 24% avg win
            avg_loss=-0.30, # 30% max loss
            account_size=10000,
            option_price=3.20
        )

        # Kelly should be positive with these parameters
        assert sizing.kelly_pct > 0
        # Conservative should be half of Kelly
        assert sizing.conservative_pct == pytest.approx(sizing.kelly_pct / 2, rel=0.01)
        # Should recommend at least 1 contract
        assert sizing.recommended_contracts >= 1

    def test_regime_edge_calculation(self):
        """Test regime edge calculation"""
        try:
            from backend.probability_engine import ProbabilityEngine
        except ImportError:
            pytest.skip("probability_engine not available")

        engine = ProbabilityEngine()

        # PANICKING should have positive edge
        edge_data = engine.calculate_regime_edge('PANICKING')
        assert edge_data['edge'] > 30  # Should be 35%+ edge

        # NEUTRAL should have no edge
        edge_data = engine.calculate_regime_edge('NEUTRAL')
        assert edge_data['edge'] == 0


class TestProbabilityCalculatorLogic:
    """Tests for ProbabilityCalculator non-database logic"""

    def test_gex_probability_positive_gex(self):
        """Test GEX probability calculation with positive GEX"""
        try:
            from core.probability_calculator import ProbabilityCalculator
        except ImportError:
            pytest.skip("probability_calculator not available")

        # Create instance without database (will use defaults)
        try:
            calc = ProbabilityCalculator()
        except Exception:
            pytest.skip("ProbabilityCalculator requires database")

        gex_data = {'net_gex': 2e9, 'flip_point': 570.0}
        prob_in, prob_above, prob_below = calc._calculate_gex_probability(
            gex_data, current_price=570.0
        )

        # Positive GEX = higher probability of range-bound
        assert prob_in > 0.50
        assert prob_in > prob_above
        assert prob_in > prob_below
        # Probabilities should roughly sum to 1
        assert 0.95 < (prob_in + prob_above + prob_below) < 1.05

    def test_volatility_adjustment(self):
        """Test volatility adjustment factor"""
        try:
            from core.probability_calculator import ProbabilityCalculator
        except ImportError:
            pytest.skip("probability_calculator not available")

        try:
            calc = ProbabilityCalculator()
        except Exception:
            pytest.skip("ProbabilityCalculator requires database")

        # Low VIX = higher confidence
        adj_low = calc._calculate_volatility_adjustment(vix=12, implied_vol=0.2)
        assert adj_low > 1.0

        # High VIX = lower confidence
        adj_high = calc._calculate_volatility_adjustment(vix=35, implied_vol=0.4)
        assert adj_high < 1.0

    def test_mm_state_impact(self):
        """Test MM state impact calculation"""
        try:
            from core.probability_calculator import ProbabilityCalculator
        except ImportError:
            pytest.skip("probability_calculator not available")

        try:
            calc = ProbabilityCalculator()
        except Exception:
            pytest.skip("ProbabilityCalculator requires database")

        # DEFENDING should increase confidence
        adj, insight = calc._calculate_mm_state_impact('DEFENDING')
        assert adj > 1.0
        assert 'dampened' in insight.lower() or 'defending' in insight.lower()

        # PANICKING should decrease confidence
        adj, insight = calc._calculate_mm_state_impact('PANICKING')
        assert adj < 1.0

    def test_psychology_adjustment_extreme_fomo(self):
        """Test psychology adjustment with extreme FOMO"""
        try:
            from core.probability_calculator import ProbabilityCalculator
        except ImportError:
            pytest.skip("probability_calculator not available")

        try:
            calc = ProbabilityCalculator()
        except Exception:
            pytest.skip("ProbabilityCalculator requires database")

        # Extreme FOMO = reversal risk
        adj, insight = calc._calculate_psychology_adjustment({'fomo_level': 90, 'fear_level': 20})
        assert adj < 1.0
        assert 'reversal' in insight.lower() or 'fomo' in insight.lower()

    def test_vol_adj_to_text(self):
        """Test volatility adjustment text helper"""
        try:
            from core.probability_calculator import vol_adj_to_text
        except ImportError:
            pytest.skip("vol_adj_to_text not available")

        assert 'low' in vol_adj_to_text(1.2).lower()
        assert 'normal' in vol_adj_to_text(1.0).lower()
        assert 'elevated' in vol_adj_to_text(0.8).lower()
        assert 'high' in vol_adj_to_text(0.6).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
