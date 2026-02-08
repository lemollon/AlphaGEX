#!/usr/bin/env python3
"""
VALOR Overnight Hybrid Strategy and Gamma Regime Filter Tests
=================================================================

Tests for the new features:
1. Overnight Hybrid Strategy - Different parameters for overnight vs RTH
2. Gamma Regime Filter - Option to restrict trading to specific gamma regime

Run: pytest tests/test_heracles_overnight_hybrid.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.valor.models import (
    ValorConfig, GammaRegime, TradeDirection, FuturesSignal, SignalSource,
    BayesianWinTracker, MES_POINT_VALUE
)
from trading.valor.signals import HERACLESSignalGenerator


class TestOvernightHybridConfig:
    """Test overnight hybrid strategy configuration parameters."""

    def test_config_has_overnight_hybrid_params(self):
        """Config should have all overnight hybrid parameters with correct defaults."""
        config = ValorConfig()

        # Check all overnight hybrid params exist
        assert hasattr(config, 'use_overnight_hybrid')
        assert hasattr(config, 'overnight_stop_points')
        assert hasattr(config, 'overnight_target_points')
        assert hasattr(config, 'overnight_emergency_stop')

        # Check default values
        assert config.use_overnight_hybrid == True
        assert config.overnight_stop_points == 1.5
        assert config.overnight_target_points == 3.0
        assert config.overnight_emergency_stop == 10.0

    def test_config_rth_params_unchanged(self):
        """RTH parameters should remain at their original values."""
        config = ValorConfig()

        assert config.initial_stop_points == 2.5
        assert config.profit_target_points == 6.0
        assert config.no_loss_emergency_stop == 15.0

    def test_overnight_params_are_tighter(self):
        """Overnight parameters should be tighter than RTH."""
        config = ValorConfig()

        # Overnight stop is tighter (smaller)
        assert config.overnight_stop_points < config.initial_stop_points
        # Overnight target is smaller
        assert config.overnight_target_points < config.profit_target_points
        # Overnight emergency stop is tighter
        assert config.overnight_emergency_stop < config.no_loss_emergency_stop


class TestGammaRegimeFilterConfig:
    """Test gamma regime filter configuration."""

    def test_config_has_gamma_regime_filter(self):
        """Config should have gamma regime filter parameter."""
        config = ValorConfig()

        assert hasattr(config, 'allowed_gamma_regime')
        # Default should be empty (all regimes allowed)
        assert config.allowed_gamma_regime == ""

    def test_config_accepts_positive_filter(self):
        """Config should accept POSITIVE as filter value."""
        config = ValorConfig()
        config.allowed_gamma_regime = "POSITIVE"
        assert config.allowed_gamma_regime == "POSITIVE"

    def test_config_accepts_negative_filter(self):
        """Config should accept NEGATIVE as filter value."""
        config = ValorConfig()
        config.allowed_gamma_regime = "NEGATIVE"
        assert config.allowed_gamma_regime == "NEGATIVE"


class TestSignalGeneratorOvernightHybrid:
    """Test signal generator overnight hybrid functionality."""

    @pytest.fixture
    def config(self):
        """Create a test config."""
        config = ValorConfig()
        config.use_no_loss_trailing = False  # Disable to test original stop logic
        config.use_overnight_hybrid = True
        return config

    @pytest.fixture
    def config_no_loss_trailing(self):
        """Create a config with no-loss trailing enabled."""
        config = ValorConfig()
        config.use_no_loss_trailing = True
        config.use_overnight_hybrid = True
        return config

    @pytest.fixture
    def win_tracker(self):
        """Create a test win tracker."""
        return BayesianWinTracker()

    @pytest.fixture
    def base_signal(self):
        """Create a base signal for testing."""
        return FuturesSignal(
            direction=TradeDirection.LONG,
            confidence=0.7,
            source=SignalSource.GEX_MEAN_REVERSION,
            current_price=5900.0,
            gamma_regime=GammaRegime.POSITIVE,
            gex_value=1e6,
            flip_point=5895.0,
            call_wall=5950.0,
            put_wall=5850.0,
            vix=18.0,
            atr=5.0,
            entry_price=5900.0,
        )

    def test_set_stop_levels_rth_no_loss_trailing(self, config_no_loss_trailing, win_tracker, base_signal):
        """RTH session with no-loss trailing should use 15pt emergency stop."""
        generator = HERACLESSignalGenerator(config_no_loss_trailing, win_tracker)

        signal, stop_type, stop_points = generator._set_stop_levels(
            base_signal, atr=5.0, is_overnight=False
        )

        assert stop_type == 'NO_LOSS_TRAIL'
        assert stop_points == 15.0  # RTH emergency stop
        assert signal.stop_price == 5900.0 - 15.0  # LONG, stop below entry

    def test_set_stop_levels_overnight_no_loss_trailing(self, config_no_loss_trailing, win_tracker, base_signal):
        """Overnight session with no-loss trailing should use 10pt emergency stop."""
        generator = HERACLESSignalGenerator(config_no_loss_trailing, win_tracker)

        signal, stop_type, stop_points = generator._set_stop_levels(
            base_signal, atr=5.0, is_overnight=True
        )

        assert stop_type == 'NO_LOSS_TRAIL_OVERNIGHT'
        assert stop_points == 10.0  # Overnight emergency stop (tighter)
        assert signal.stop_price == 5900.0 - 10.0  # LONG, stop below entry

    def test_set_stop_levels_rth_fixed(self, config, win_tracker, base_signal):
        """RTH session with fixed stops should use 2.5pt stop and 6pt target."""
        generator = HERACLESSignalGenerator(config, win_tracker)

        signal, stop_type, stop_points = generator._set_stop_levels(
            base_signal, atr=5.0, is_overnight=False
        )

        assert stop_type == 'FIXED'
        assert stop_points == 2.5  # RTH stop
        assert signal.stop_price == 5900.0 - 2.5
        assert signal.target_price == 5900.0 + 6.0  # RTH target

    def test_set_stop_levels_overnight_fixed(self, config, win_tracker, base_signal):
        """Overnight session with fixed stops should use 1.5pt stop and 3pt target."""
        generator = HERACLESSignalGenerator(config, win_tracker)

        signal, stop_type, stop_points = generator._set_stop_levels(
            base_signal, atr=5.0, is_overnight=True
        )

        assert stop_type == 'FIXED_OVERNIGHT'
        assert stop_points == 1.5  # Overnight stop (tighter)
        assert signal.stop_price == 5900.0 - 1.5
        assert signal.target_price == 5900.0 + 3.0  # Overnight target (smaller)

    def test_short_signal_overnight_stops(self, config, win_tracker):
        """SHORT signal overnight should have stop above and target below."""
        short_signal = FuturesSignal(
            direction=TradeDirection.SHORT,
            confidence=0.7,
            source=SignalSource.GEX_MOMENTUM,
            current_price=5900.0,
            gamma_regime=GammaRegime.NEGATIVE,
            gex_value=-1e6,
            flip_point=5905.0,
            call_wall=5950.0,
            put_wall=5850.0,
            vix=18.0,
            atr=5.0,
            entry_price=5900.0,
        )

        generator = HERACLESSignalGenerator(config, win_tracker)

        signal, stop_type, stop_points = generator._set_stop_levels(
            short_signal, atr=5.0, is_overnight=True
        )

        assert stop_type == 'FIXED_OVERNIGHT'
        assert signal.stop_price == 5900.0 + 1.5  # SHORT, stop above entry
        assert signal.target_price == 5900.0 - 3.0  # SHORT, target below entry

    def test_overnight_hybrid_disabled(self, win_tracker, base_signal):
        """When overnight hybrid is disabled, overnight should use RTH params."""
        config = ValorConfig()
        config.use_no_loss_trailing = False
        config.use_overnight_hybrid = False

        generator = HERACLESSignalGenerator(config, win_tracker)

        signal, stop_type, stop_points = generator._set_stop_levels(
            base_signal, atr=5.0, is_overnight=True
        )

        # Should use RTH params even though is_overnight=True
        assert stop_type == 'FIXED'  # Not FIXED_OVERNIGHT
        assert stop_points == 2.5  # RTH stop, not 1.5
        assert signal.target_price == 5900.0 + 6.0  # RTH target, not 3.0


class TestSignalGeneratorGammaRegimeFilter:
    """Test signal generator gamma regime filter functionality."""

    @pytest.fixture
    def config(self):
        """Create a test config."""
        return ValorConfig()

    @pytest.fixture
    def win_tracker(self):
        """Create a test win tracker."""
        return BayesianWinTracker()

    def test_no_filter_allows_positive_gamma(self, config, win_tracker):
        """Empty filter should allow positive gamma signals."""
        config.allowed_gamma_regime = ""
        generator = HERACLESSignalGenerator(config, win_tracker)

        # Positive gamma setup (price above flip = SHORT signal expected)
        # Need price to be > 0.5% (flip_point_proximity_pct) from flip point
        # 5895 * 1.005 = 5924.5, so price of 5930 is ~0.6% above flip
        gex_data = {
            'flip_point': 5895.0,
            'call_wall': 5980.0,
            'put_wall': 5810.0,
            'net_gex': 1e9,  # Positive = POSITIVE gamma
        }

        signal = generator.generate_signal(
            current_price=5930.0,  # 0.59% above flip point for mean reversion SHORT
            gex_data=gex_data,
            vix=18.0,
            atr=5.0,
            account_balance=100000.0,
            is_overnight=False
        )

        # Signal should be generated (not filtered)
        assert signal is not None
        assert signal.gamma_regime == GammaRegime.POSITIVE

    def test_no_filter_allows_negative_gamma(self, config, win_tracker):
        """Empty filter should allow negative gamma signals."""
        config.allowed_gamma_regime = ""
        generator = HERACLESSignalGenerator(config, win_tracker)

        # Negative gamma setup with momentum breakout
        gex_data = {
            'flip_point': 5895.0,
            'call_wall': 5950.0,
            'put_wall': 5850.0,
            'net_gex': -1e9,  # Negative = NEGATIVE gamma
        }

        signal = generator.generate_signal(
            current_price=5905.0,  # Above flip for momentum LONG
            gex_data=gex_data,
            vix=18.0,
            atr=5.0,
            account_balance=100000.0,
            is_overnight=False
        )

        # Signal should be generated
        assert signal is not None
        assert signal.gamma_regime == GammaRegime.NEGATIVE

    def test_positive_filter_blocks_negative_gamma(self, config, win_tracker):
        """POSITIVE filter should block negative gamma signals."""
        config.allowed_gamma_regime = "POSITIVE"
        generator = HERACLESSignalGenerator(config, win_tracker)

        # Negative gamma setup
        gex_data = {
            'flip_point': 5895.0,
            'call_wall': 5950.0,
            'put_wall': 5850.0,
            'net_gex': -1e9,  # Negative = NEGATIVE gamma
        }

        signal = generator.generate_signal(
            current_price=5905.0,
            gex_data=gex_data,
            vix=18.0,
            atr=5.0,
            account_balance=100000.0,
            is_overnight=False
        )

        # Signal should be blocked by filter
        assert signal is None

    def test_positive_filter_allows_positive_gamma(self, config, win_tracker):
        """POSITIVE filter should allow positive gamma signals."""
        config.allowed_gamma_regime = "POSITIVE"
        generator = HERACLESSignalGenerator(config, win_tracker)

        # Positive gamma setup
        # Need price to be > 0.5% from flip point to generate signal
        gex_data = {
            'flip_point': 5895.0,
            'call_wall': 5980.0,
            'put_wall': 5810.0,
            'net_gex': 1e9,  # Positive = POSITIVE gamma
        }

        signal = generator.generate_signal(
            current_price=5930.0,  # 0.59% above flip for mean reversion SHORT
            gex_data=gex_data,
            vix=18.0,
            atr=5.0,
            account_balance=100000.0,
            is_overnight=False
        )

        # Signal should be allowed
        assert signal is not None
        assert signal.gamma_regime == GammaRegime.POSITIVE

    def test_negative_filter_blocks_positive_gamma(self, config, win_tracker):
        """NEGATIVE filter should block positive gamma signals."""
        config.allowed_gamma_regime = "NEGATIVE"
        generator = HERACLESSignalGenerator(config, win_tracker)

        # Positive gamma setup
        gex_data = {
            'flip_point': 5895.0,
            'call_wall': 5950.0,
            'put_wall': 5850.0,
            'net_gex': 1e9,  # Positive = POSITIVE gamma
        }

        signal = generator.generate_signal(
            current_price=5910.0,
            gex_data=gex_data,
            vix=18.0,
            atr=5.0,
            account_balance=100000.0,
            is_overnight=False
        )

        # Signal should be blocked by filter
        assert signal is None

    def test_filter_case_insensitive(self, config, win_tracker):
        """Filter should be case-insensitive."""
        config.allowed_gamma_regime = "positive"  # lowercase
        generator = HERACLESSignalGenerator(config, win_tracker)

        # Negative gamma setup
        gex_data = {
            'flip_point': 5895.0,
            'call_wall': 5950.0,
            'put_wall': 5850.0,
            'net_gex': -1e9,  # Negative
        }

        signal = generator.generate_signal(
            current_price=5905.0,
            gex_data=gex_data,
            vix=18.0,
            atr=5.0,
            account_balance=100000.0,
            is_overnight=False
        )

        # Signal should still be blocked (lowercase "positive" should work)
        assert signal is None


class TestOvernightHybridWithNoLossTrailing:
    """Test overnight hybrid integration with no-loss trailing mode."""

    @pytest.fixture
    def config(self):
        """Create config with both features enabled."""
        config = ValorConfig()
        config.use_no_loss_trailing = True
        config.use_overnight_hybrid = True
        return config

    @pytest.fixture
    def win_tracker(self):
        return BayesianWinTracker()

    def test_rth_uses_15pt_emergency_stop(self, config, win_tracker):
        """RTH with no-loss trailing uses 15pt emergency stop."""
        signal = FuturesSignal(
            direction=TradeDirection.LONG,
            confidence=0.7,
            source=SignalSource.GEX_MEAN_REVERSION,
            current_price=5900.0,
            gamma_regime=GammaRegime.POSITIVE,
            gex_value=1e6,
            flip_point=5895.0,
            call_wall=5950.0,
            put_wall=5850.0,
            vix=18.0,
            atr=5.0,
            entry_price=5900.0,
        )

        generator = HERACLESSignalGenerator(config, win_tracker)
        signal, stop_type, stop_pts = generator._set_stop_levels(signal, atr=5.0, is_overnight=False)

        assert stop_type == 'NO_LOSS_TRAIL'
        assert stop_pts == 15.0
        # Emergency stop should be 15 pts below for LONG
        assert signal.stop_price == pytest.approx(5885.0, abs=0.01)

    def test_overnight_uses_10pt_emergency_stop(self, config, win_tracker):
        """Overnight with no-loss trailing uses 10pt emergency stop."""
        signal = FuturesSignal(
            direction=TradeDirection.LONG,
            confidence=0.7,
            source=SignalSource.GEX_MEAN_REVERSION,
            current_price=5900.0,
            gamma_regime=GammaRegime.POSITIVE,
            gex_value=1e6,
            flip_point=5895.0,
            call_wall=5950.0,
            put_wall=5850.0,
            vix=18.0,
            atr=5.0,
            entry_price=5900.0,
        )

        generator = HERACLESSignalGenerator(config, win_tracker)
        signal, stop_type, stop_pts = generator._set_stop_levels(signal, atr=5.0, is_overnight=True)

        assert stop_type == 'NO_LOSS_TRAIL_OVERNIGHT'
        assert stop_pts == 10.0
        # Emergency stop should be 10 pts below for LONG (tighter)
        assert signal.stop_price == pytest.approx(5890.0, abs=0.01)

    def test_short_overnight_emergency_stop(self, config, win_tracker):
        """SHORT overnight uses 10pt emergency stop above entry."""
        signal = FuturesSignal(
            direction=TradeDirection.SHORT,
            confidence=0.7,
            source=SignalSource.GEX_MOMENTUM,
            current_price=5900.0,
            gamma_regime=GammaRegime.NEGATIVE,
            gex_value=-1e6,
            flip_point=5905.0,
            call_wall=5950.0,
            put_wall=5850.0,
            vix=18.0,
            atr=5.0,
            entry_price=5900.0,
        )

        generator = HERACLESSignalGenerator(config, win_tracker)
        signal, stop_type, stop_pts = generator._set_stop_levels(signal, atr=5.0, is_overnight=True)

        assert stop_type == 'NO_LOSS_TRAIL_OVERNIGHT'
        assert stop_pts == 10.0
        # Emergency stop should be 10 pts ABOVE for SHORT
        assert signal.stop_price == pytest.approx(5910.0, abs=0.01)


class TestEmergencyStopCalculation:
    """Test that trader uses stored initial_stop for overnight hybrid."""

    def test_emergency_stop_distance_from_initial_stop(self):
        """Emergency stop distance should be derived from stored initial_stop."""
        from trading.valor.models import FuturesPosition, PositionStatus

        # Simulate a position opened during overnight (10pt emergency stop)
        overnight_position = FuturesPosition(
            position_id="TEST-001",
            symbol="/MESH6",
            direction=TradeDirection.LONG,
            contracts=1,
            entry_price=5900.0,
            entry_value=5900.0 * 1 * MES_POINT_VALUE,
            initial_stop=5890.0,  # 10 pts below = overnight emergency stop
            current_stop=5890.0,
            breakeven_price=5900.0,
        )

        # Calculate emergency stop distance as trader would
        emergency_stop_pts = abs(overnight_position.entry_price - overnight_position.initial_stop)
        assert emergency_stop_pts == 10.0  # Overnight emergency stop

        # Simulate RTH position (15pt emergency stop)
        rth_position = FuturesPosition(
            position_id="TEST-002",
            symbol="/MESH6",
            direction=TradeDirection.LONG,
            contracts=1,
            entry_price=5900.0,
            entry_value=5900.0 * 1 * MES_POINT_VALUE,
            initial_stop=5885.0,  # 15 pts below = RTH emergency stop
            current_stop=5885.0,
            breakeven_price=5900.0,
        )

        emergency_stop_pts_rth = abs(rth_position.entry_price - rth_position.initial_stop)
        assert emergency_stop_pts_rth == 15.0  # RTH emergency stop


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
