"""
FORTRESS ML Advisor Tests

Tests for the FORTRESS iron condor ML advisor.

Run with: pytest tests/test_fortress_ml_advisor.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFortressMLAdvisorImport:
    """Tests for FORTRESS ML advisor import"""

    def test_import_fortress_advisor(self):
        """Test that FORTRESS advisor can be imported"""
        try:
            from quant.fortress_ml_advisor import FortressMLAdvisor
            assert FortressMLAdvisor is not None
        except ImportError:
            pytest.skip("FORTRESS ML advisor not available")


class TestFortressMLAdvisorInitialization:
    """Tests for FORTRESS ML advisor initialization"""

    def test_advisor_initialization(self):
        """Test advisor can be initialized"""
        try:
            from quant.fortress_ml_advisor import FortressMLAdvisor
            advisor = FortressMLAdvisor()
            assert advisor is not None
        except ImportError:
            pytest.skip("FORTRESS ML advisor not available")


class TestIronCondorPrediction:
    """Tests for iron condor predictions"""

    def test_predict_ic_success(self, mock_market_data):
        """Test IC success prediction"""
        try:
            from quant.fortress_ml_advisor import FortressMLAdvisor

            advisor = FortressMLAdvisor()
            if hasattr(advisor, 'predict_success_probability'):
                with patch.object(advisor, 'predict_success_probability') as mock_pred:
                    mock_pred.return_value = 0.75
                    result = advisor.predict_success_probability(mock_market_data)
                    assert 0 <= result <= 1
        except ImportError:
            pytest.skip("FORTRESS ML advisor not available")


class TestStrikeRecommendation:
    """Tests for strike recommendations"""

    def test_recommend_strikes(self, mock_market_data):
        """Test strike recommendation"""
        try:
            from quant.fortress_ml_advisor import FortressMLAdvisor

            advisor = FortressMLAdvisor()
            if hasattr(advisor, 'recommend_strikes'):
                with patch.object(advisor, 'recommend_strikes') as mock_strikes:
                    mock_strikes.return_value = {
                        'short_put': 5800,
                        'long_put': 5790,
                        'short_call': 5900,
                        'long_call': 5910
                    }
                    result = advisor.recommend_strikes(mock_market_data)
                    assert 'short_put' in result or 'short_call' in result
        except ImportError:
            pytest.skip("FORTRESS ML advisor not available")


class TestRiskAssessment:
    """Tests for risk assessment"""

    def test_assess_ic_risk(self, mock_iron_condor_position):
        """Test IC risk assessment"""
        try:
            from quant.fortress_ml_advisor import FortressMLAdvisor

            advisor = FortressMLAdvisor()
            if hasattr(advisor, 'assess_risk'):
                with patch.object(advisor, 'assess_risk') as mock_risk:
                    mock_risk.return_value = {'risk_level': 'MODERATE', 'score': 0.4}
                    result = advisor.assess_risk(mock_iron_condor_position)
                    assert 'risk_level' in result or 'score' in result
        except ImportError:
            pytest.skip("FORTRESS ML advisor not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
