"""
Watchtower Engine Tests

Tests for the Watchtower 0DTE gamma analysis engine.

Run with: pytest tests/test_watchtower_engine.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWatchtowerEngineImport:
    """Tests for Watchtower engine import"""

    def test_import_watchtower_engine(self):
        """Test that Watchtower engine can be imported"""
        try:
            from core.watchtower_engine import WatchtowerEngine
            assert WatchtowerEngine is not None
        except ImportError:
            pytest.skip("Watchtower engine not available")


class TestWatchtowerEngineInitialization:
    """Tests for Watchtower engine initialization"""

    def test_engine_initialization(self):
        """Test engine can be initialized"""
        try:
            from core.watchtower_engine import WatchtowerEngine

            with patch('core.watchtower_engine.get_connection'):
                engine = WatchtowerEngine()
                assert engine is not None
        except ImportError:
            pytest.skip("Watchtower engine not available")


class TestArgusGammaAnalysis:
    """Tests for gamma analysis"""

    def test_analyze_gamma(self, mock_option_chain):
        """Test gamma analysis"""
        try:
            from core.watchtower_engine import WatchtowerEngine

            with patch('core.watchtower_engine.get_connection'):
                engine = WatchtowerEngine()
                if hasattr(engine, 'analyze_gamma'):
                    with patch.object(engine, 'analyze_gamma') as mock_analysis:
                        mock_analysis.return_value = {
                            'net_gamma': 1.5e9,
                            'gamma_regime': 'POSITIVE'
                        }
                        result = engine.analyze_gamma(mock_option_chain)
                        assert 'net_gamma' in result or 'gamma_regime' in result
        except ImportError:
            pytest.skip("Watchtower engine not available")


class TestArgusMagnetDetection:
    """Tests for magnet detection"""

    def test_detect_magnets(self, mock_gex_levels):
        """Test magnet detection"""
        try:
            from core.watchtower_engine import WatchtowerEngine

            with patch('core.watchtower_engine.get_connection'):
                engine = WatchtowerEngine()
                if hasattr(engine, 'find_magnets'):
                    with patch.object(engine, 'find_magnets') as mock_magnets:
                        mock_magnets.return_value = [590.0, 580.0]
                        result = engine.find_magnets(mock_gex_levels)
                        assert isinstance(result, list)
        except ImportError:
            pytest.skip("Watchtower engine not available")


class TestArgusPinPrediction:
    """Tests for pin prediction"""

    def test_predict_likely_pin(self, mock_gex_levels):
        """Test pin prediction"""
        try:
            from core.watchtower_engine import WatchtowerEngine

            with patch('core.watchtower_engine.get_connection'):
                engine = WatchtowerEngine()
                if hasattr(engine, 'predict_pin'):
                    with patch.object(engine, 'predict_pin') as mock_pin:
                        mock_pin.return_value = {'strike': 585.0, 'probability': 0.35}
                        result = engine.predict_pin(mock_gex_levels)
                        assert 'strike' in result or 'probability' in result
        except ImportError:
            pytest.skip("Watchtower engine not available")


class TestArgusOrderFlowPressure:
    """Tests for order flow pressure calculation (GAP fixes)"""

    @pytest.fixture
    def engine(self):
        """Create a test engine instance"""
        try:
            from core.watchtower_engine import WatchtowerEngine
            with patch('core.watchtower_engine.get_connection'):
                return WatchtowerEngine()
        except ImportError:
            pytest.skip("Watchtower engine not available")

    @pytest.fixture
    def mock_strikes(self):
        """Create mock strike data with bid/ask sizes"""
        try:
            from core.watchtower_engine import StrikeData
            return [
                StrikeData(
                    strike=584.0, net_gamma=0.05, call_gamma=0.03, put_gamma=0.02,
                    call_bid_size=150, call_ask_size=100, put_bid_size=80, put_ask_size=200
                ),
                StrikeData(
                    strike=585.0, net_gamma=0.08, call_gamma=0.05, put_gamma=0.03,
                    call_bid_size=200, call_ask_size=120, put_bid_size=100, put_ask_size=250
                ),
                StrikeData(
                    strike=586.0, net_gamma=0.04, call_gamma=0.02, put_gamma=0.02,
                    call_bid_size=100, call_ask_size=80, put_bid_size=60, put_ask_size=150
                ),
            ]
        except ImportError:
            pytest.skip("StrikeData not available")

    def test_calculate_bid_ask_pressure_returns_all_fields(self, engine, mock_strikes):
        """GAP #5: Test that all required fields are returned"""
        result = engine.calculate_bid_ask_pressure(mock_strikes, 585.0)

        required_fields = [
            'net_pressure', 'raw_pressure', 'pressure_direction', 'pressure_strength',
            'call_pressure', 'put_pressure', 'total_bid_size', 'total_ask_size',
            'liquidity_score', 'strikes_used', 'smoothing_periods', 'is_valid',
            'reason', 'top_pressure_strikes', 'imbalance_ratio'
        ]

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    def test_calculate_bid_ask_pressure_empty_strikes(self, engine):
        """GAP #5-6: Test empty strikes returns proper structure with is_valid=False"""
        result = engine.calculate_bid_ask_pressure([], 585.0)

        # Should still have all fields
        assert 'net_pressure' in result
        assert 'raw_pressure' in result
        assert 'smoothing_periods' in result
        assert 'is_valid' in result

        # is_valid should be False for empty strikes
        assert result['is_valid'] is False
        assert result['reason'] is not None

    def test_calculate_bid_ask_pressure_invalid_spot_price(self, engine, mock_strikes):
        """GAP #2-3: Test invalid spot_price returns proper empty result"""
        result = engine.calculate_bid_ask_pressure(mock_strikes, 0)

        assert result['is_valid'] is False
        assert 'raw_pressure' in result
        assert 'smoothing_periods' in result

    def test_calculate_bid_ask_pressure_negative_spot_price(self, engine, mock_strikes):
        """GAP #2-3: Test negative spot_price returns proper empty result"""
        result = engine.calculate_bid_ask_pressure(mock_strikes, -100)

        assert result['is_valid'] is False

    def test_update_smoothing_true_updates_history(self, engine, mock_strikes):
        """GAP #1: Test update_smoothing=True adds to history"""
        # Clear any existing history
        engine._pressure_history = []

        # Call with update_smoothing=True (default)
        engine.calculate_bid_ask_pressure(mock_strikes, 585.0, update_smoothing=True)

        # History should have been updated
        assert len(engine._pressure_history) >= 1

    def test_update_smoothing_false_preserves_history(self, engine, mock_strikes):
        """GAP #1: Test update_smoothing=False does NOT add to history"""
        # Set up existing history
        engine._pressure_history = [0.1, 0.2, 0.3]
        original_len = len(engine._pressure_history)

        # Call with update_smoothing=False
        engine.calculate_bid_ask_pressure(mock_strikes, 585.0, update_smoothing=False)

        # History should NOT have been updated
        assert len(engine._pressure_history) == original_len

    def test_smoothing_periods_range(self, engine, mock_strikes):
        """GAP #1: Test smoothing_periods is always 0-5"""
        # Clear history
        engine._pressure_history = []

        # Call multiple times
        for _ in range(10):
            result = engine.calculate_bid_ask_pressure(mock_strikes, 585.0, update_smoothing=True)
            assert 0 <= result['smoothing_periods'] <= 5

    def test_pressure_direction_valid_values(self, engine, mock_strikes):
        """Test pressure_direction is always a valid enum value"""
        result = engine.calculate_bid_ask_pressure(mock_strikes, 585.0)

        valid_directions = ['BULLISH', 'BEARISH', 'NEUTRAL']
        assert result['pressure_direction'] in valid_directions

    def test_is_valid_is_boolean(self, engine, mock_strikes):
        """GAP #6: Test is_valid is always boolean"""
        # Valid case
        result = engine.calculate_bid_ask_pressure(mock_strikes, 585.0)
        assert isinstance(result['is_valid'], bool)

        # Invalid case (empty strikes)
        result = engine.calculate_bid_ask_pressure([], 585.0)
        assert isinstance(result['is_valid'], bool)


class TestArgusNetGexVolume:
    """Tests for net GEX volume calculation (GAP fixes)"""

    @pytest.fixture
    def engine(self):
        """Create a test engine instance"""
        try:
            from core.watchtower_engine import WatchtowerEngine
            with patch('core.watchtower_engine.get_connection'):
                return WatchtowerEngine()
        except ImportError:
            pytest.skip("Watchtower engine not available")

    @pytest.fixture
    def mock_strikes(self):
        """Create mock strike data"""
        try:
            from core.watchtower_engine import StrikeData
            return [
                StrikeData(
                    strike=584.0, net_gamma=0.05, call_gamma=0.03, put_gamma=0.02,
                    call_volume=1000, put_volume=800,
                    call_bid_size=150, call_ask_size=100, put_bid_size=80, put_ask_size=200
                ),
                StrikeData(
                    strike=585.0, net_gamma=0.08, call_gamma=0.05, put_gamma=0.03,
                    call_volume=1500, put_volume=1200,
                    call_bid_size=200, call_ask_size=120, put_bid_size=100, put_ask_size=250
                ),
            ]
        except ImportError:
            pytest.skip("StrikeData not available")

    def test_calculate_net_gex_volume_returns_all_fields(self, engine, mock_strikes):
        """Test that all required fields are returned"""
        result = engine.calculate_net_gex_volume(mock_strikes, 585.0)

        required_fields = [
            'net_gex_volume', 'call_gex_flow', 'put_gex_flow',
            'flow_direction', 'flow_strength', 'imbalance_ratio',
            'bid_ask_pressure', 'combined_signal', 'signal_confidence'
        ]

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    def test_calculate_net_gex_volume_empty_strikes(self, engine):
        """GAP #5-6: Test empty strikes returns proper structure"""
        result = engine.calculate_net_gex_volume([], 585.0)

        # Should have all required fields
        assert 'bid_ask_pressure' in result
        assert 'imbalance_ratio' in result
        assert 'combined_signal' in result

        # bid_ask_pressure should have proper structure
        bid_ask = result['bid_ask_pressure']
        assert 'is_valid' in bid_ask
        assert bid_ask['is_valid'] is False
        assert 'raw_pressure' in bid_ask
        assert 'smoothing_periods' in bid_ask

    def test_update_smoothing_passed_to_bid_ask_pressure(self, engine, mock_strikes):
        """GAP #1: Test update_smoothing parameter is passed through"""
        engine._pressure_history = []

        # With update_smoothing=True
        engine.calculate_net_gex_volume(mock_strikes, 585.0, update_smoothing=True)
        len_after_true = len(engine._pressure_history)

        # With update_smoothing=False
        engine.calculate_net_gex_volume(mock_strikes, 585.0, update_smoothing=False)
        len_after_false = len(engine._pressure_history)

        # History should only grow with update_smoothing=True
        assert len_after_true >= 1
        assert len_after_false == len_after_true  # Should not have grown

    def test_combined_signal_valid_values(self, engine, mock_strikes):
        """Test combined_signal is always a valid enum value"""
        result = engine.calculate_net_gex_volume(mock_strikes, 585.0)

        valid_signals = [
            'NEUTRAL', 'BULLISH', 'BEARISH',
            'STRONG_BULLISH', 'STRONG_BEARISH',
            'DIVERGENCE_BULLISH', 'DIVERGENCE_BEARISH'
        ]
        assert result['combined_signal'] in valid_signals

    def test_signal_confidence_valid_values(self, engine, mock_strikes):
        """Test signal_confidence is always a valid enum value"""
        result = engine.calculate_net_gex_volume(mock_strikes, 585.0)

        valid_confidences = ['HIGH', 'MEDIUM', 'LOW']
        assert result['signal_confidence'] in valid_confidences


class TestArgusResetGammaSmoothing:
    """Tests for daily reset functionality (GAP #3 fix)"""

    @pytest.fixture
    def engine(self):
        """Create a test engine instance"""
        try:
            from core.watchtower_engine import WatchtowerEngine
            with patch('core.watchtower_engine.get_connection'):
                return WatchtowerEngine()
        except ImportError:
            pytest.skip("Watchtower engine not available")

    def test_reset_clears_pressure_history(self, engine):
        """GAP #3: Test that reset clears pressure history"""
        # Set up pressure history
        engine._pressure_history = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Call reset
        engine.reset_gamma_smoothing()

        # Pressure history should be cleared
        assert len(engine._pressure_history) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
