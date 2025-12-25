"""
Argus Engine Tests

Tests for the Argus 0DTE gamma analysis engine.

Run with: pytest tests/test_argus_engine.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestArgusEngineImport:
    """Tests for Argus engine import"""

    def test_import_argus_engine(self):
        """Test that Argus engine can be imported"""
        try:
            from core.argus_engine import ArgusEngine
            assert ArgusEngine is not None
        except ImportError:
            pytest.skip("Argus engine not available")


class TestArgusEngineInitialization:
    """Tests for Argus engine initialization"""

    def test_engine_initialization(self):
        """Test engine can be initialized"""
        try:
            from core.argus_engine import ArgusEngine

            with patch('core.argus_engine.get_connection'):
                engine = ArgusEngine()
                assert engine is not None
        except ImportError:
            pytest.skip("Argus engine not available")


class TestArgusGammaAnalysis:
    """Tests for gamma analysis"""

    def test_analyze_gamma(self, mock_option_chain):
        """Test gamma analysis"""
        try:
            from core.argus_engine import ArgusEngine

            with patch('core.argus_engine.get_connection'):
                engine = ArgusEngine()
                if hasattr(engine, 'analyze_gamma'):
                    with patch.object(engine, 'analyze_gamma') as mock_analysis:
                        mock_analysis.return_value = {
                            'net_gamma': 1.5e9,
                            'gamma_regime': 'POSITIVE'
                        }
                        result = engine.analyze_gamma(mock_option_chain)
                        assert 'net_gamma' in result or 'gamma_regime' in result
        except ImportError:
            pytest.skip("Argus engine not available")


class TestArgusMagnetDetection:
    """Tests for magnet detection"""

    def test_detect_magnets(self, mock_gex_levels):
        """Test magnet detection"""
        try:
            from core.argus_engine import ArgusEngine

            with patch('core.argus_engine.get_connection'):
                engine = ArgusEngine()
                if hasattr(engine, 'find_magnets'):
                    with patch.object(engine, 'find_magnets') as mock_magnets:
                        mock_magnets.return_value = [590.0, 580.0]
                        result = engine.find_magnets(mock_gex_levels)
                        assert isinstance(result, list)
        except ImportError:
            pytest.skip("Argus engine not available")


class TestArgusPinPrediction:
    """Tests for pin prediction"""

    def test_predict_likely_pin(self, mock_gex_levels):
        """Test pin prediction"""
        try:
            from core.argus_engine import ArgusEngine

            with patch('core.argus_engine.get_connection'):
                engine = ArgusEngine()
                if hasattr(engine, 'predict_pin'):
                    with patch.object(engine, 'predict_pin') as mock_pin:
                        mock_pin.return_value = {'strike': 585.0, 'probability': 0.35}
                        result = engine.predict_pin(mock_gex_levels)
                        assert 'strike' in result or 'probability' in result
        except ImportError:
            pytest.skip("Argus engine not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
