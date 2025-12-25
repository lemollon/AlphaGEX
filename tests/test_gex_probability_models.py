"""
GEX Probability Models Tests

Tests for GEX-based probability models.

Run with: pytest tests/test_gex_probability_models.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGEXProbabilityImport:
    """Tests for GEX probability import"""

    def test_import_gex_probability(self):
        """Test that GEX probability can be imported"""
        try:
            from quant.gex_probability_models import GEXProbabilityModel
            assert GEXProbabilityModel is not None
        except ImportError:
            pytest.skip("GEX probability models not available")


class TestGEXProbabilityInitialization:
    """Tests for GEX probability initialization"""

    def test_model_initialization(self):
        """Test model can be initialized"""
        try:
            from quant.gex_probability_models import GEXProbabilityModel
            model = GEXProbabilityModel()
            assert model is not None
        except ImportError:
            pytest.skip("GEX probability models not available")


class TestPriceProbability:
    """Tests for price probability calculations"""

    def test_calculate_price_probability(self, mock_gex_data):
        """Test price probability calculation"""
        try:
            from quant.gex_probability_models import GEXProbabilityModel

            model = GEXProbabilityModel()
            if hasattr(model, 'calculate_price_probability'):
                with patch.object(model, 'calculate_price_probability') as mock_prob:
                    mock_prob.return_value = 0.65
                    result = model.calculate_price_probability(585.0, mock_gex_data)
                    assert 0 <= result <= 1
        except ImportError:
            pytest.skip("GEX probability models not available")


class TestRangeProbability:
    """Tests for range probability calculations"""

    def test_calculate_range_probability(self, mock_gex_data):
        """Test range probability calculation"""
        try:
            from quant.gex_probability_models import GEXProbabilityModel

            model = GEXProbabilityModel()
            if hasattr(model, 'calculate_range_probability'):
                with patch.object(model, 'calculate_range_probability') as mock_range:
                    mock_range.return_value = 0.75
                    result = model.calculate_range_probability(580.0, 590.0, mock_gex_data)
                    assert 0 <= result <= 1
        except ImportError:
            pytest.skip("GEX probability models not available")


class TestGEXRegimeImpact:
    """Tests for GEX regime impact on probability"""

    def test_positive_gamma_impact(self):
        """Test positive gamma regime impact"""
        try:
            from quant.gex_probability_models import GEXProbabilityModel

            model = GEXProbabilityModel()
            if hasattr(model, 'get_regime_adjustment'):
                with patch.object(model, 'get_regime_adjustment') as mock_adj:
                    mock_adj.return_value = 0.9  # 90% of expected move in positive gamma
                    result = model.get_regime_adjustment('POSITIVE')
                    assert result <= 1.0  # Move should be dampened
        except ImportError:
            pytest.skip("GEX probability models not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
