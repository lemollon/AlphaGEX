"""
Pin Risk Analyzer Tests

Tests for the Pin Risk Analyzer, specifically the to_dict() serialization
that must be compatible with the frontend PinRisk interface.

Run with: pytest tests/test_pin_risk_analyzer.py -v
"""

import pytest
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPinRiskAnalyzerImport:
    """Tests for Pin Risk Analyzer import"""

    def test_import_pin_risk_analyzer(self):
        """Test that pin risk analyzer can be imported"""
        from core.pin_risk_analyzer import (
            PinRiskAnalyzer,
            PinRiskAnalysis,
            PinRiskLevel,
            GammaRegime,
            GammaLevels
        )
        assert PinRiskAnalyzer is not None
        assert PinRiskAnalysis is not None


class TestPinRiskAnalysisToDict:
    """Tests for PinRiskAnalysis.to_dict() frontend compatibility"""

    def test_to_dict_has_frontend_score_field(self):
        """Test that to_dict returns 'score' field for frontend"""
        from core.pin_risk_analyzer import (
            PinRiskAnalysis, PinRiskLevel, GammaRegime, GammaLevels
        )

        analysis = PinRiskAnalysis(
            symbol='SPY',
            timestamp=datetime.now(),
            pin_risk_score=65
        )
        result = analysis.to_dict()

        assert 'score' in result, "Missing 'score' field (frontend expects this)"
        assert result['score'] == 65

    def test_to_dict_has_frontend_level_field(self):
        """Test that to_dict returns 'level' field for frontend"""
        from core.pin_risk_analyzer import (
            PinRiskAnalysis, PinRiskLevel, GammaRegime
        )

        analysis = PinRiskAnalysis(
            symbol='SPY',
            timestamp=datetime.now(),
            pin_risk_level=PinRiskLevel.HIGH
        )
        result = analysis.to_dict()

        assert 'level' in result, "Missing 'level' field (frontend expects this)"
        assert result['level'] == 'high'

    def test_to_dict_has_frontend_days_to_expiry_field(self):
        """Test that to_dict returns 'days_to_expiry' field for frontend"""
        from core.pin_risk_analyzer import PinRiskAnalysis, PinRiskLevel, GammaRegime

        analysis = PinRiskAnalysis(
            symbol='SPY',
            timestamp=datetime.now(),
            days_to_weekly_expiry=2
        )
        result = analysis.to_dict()

        assert 'days_to_expiry' in result, "Missing 'days_to_expiry' field (frontend expects this)"
        assert result['days_to_expiry'] == 2

    def test_to_dict_has_nested_expected_range(self):
        """Test that to_dict returns nested 'expected_range' object for frontend"""
        from core.pin_risk_analyzer import PinRiskAnalysis, PinRiskLevel, GammaRegime

        analysis = PinRiskAnalysis(
            symbol='SPY',
            timestamp=datetime.now(),
            expected_range_low=585.0,
            expected_range_high=595.0,
            expected_range_pct=1.7
        )
        result = analysis.to_dict()

        assert 'expected_range' in result, "Missing 'expected_range' field (frontend expects nested object)"
        assert isinstance(result['expected_range'], dict), "expected_range should be a dict"
        assert 'low' in result['expected_range'], "Missing expected_range.low"
        assert 'high' in result['expected_range'], "Missing expected_range.high"
        assert 'pct' in result['expected_range'], "Missing expected_range.pct"
        assert result['expected_range']['low'] == 585.0
        assert result['expected_range']['high'] == 595.0
        assert result['expected_range']['pct'] == 1.7

    def test_to_dict_has_flat_gamma_levels(self):
        """Test that to_dict returns flat max_pain, call_wall, put_wall, flip_point for frontend"""
        from core.pin_risk_analyzer import PinRiskAnalysis, GammaLevels, PinRiskLevel, GammaRegime

        analysis = PinRiskAnalysis(
            symbol='SPY',
            timestamp=datetime.now()
        )
        analysis.gamma_levels = GammaLevels(
            max_pain=590.0,
            call_wall=595.0,
            put_wall=585.0,
            flip_point=588.0,
            net_gex=0.5
        )
        result = analysis.to_dict()

        # Frontend expects these as flat fields, not nested in gamma_levels
        assert 'max_pain' in result, "Missing 'max_pain' field (frontend expects flat)"
        assert 'call_wall' in result, "Missing 'call_wall' field (frontend expects flat)"
        assert 'put_wall' in result, "Missing 'put_wall' field (frontend expects flat)"
        assert 'flip_point' in result, "Missing 'flip_point' field (frontend expects flat)"
        assert result['max_pain'] == 590.0
        assert result['call_wall'] == 595.0
        assert result['put_wall'] == 585.0
        assert result['flip_point'] == 588.0

    def test_to_dict_maintains_backward_compatibility(self):
        """Test that to_dict still includes original field names for backward compatibility"""
        from core.pin_risk_analyzer import (
            PinRiskAnalysis, PinRiskLevel, GammaRegime, GammaLevels
        )

        analysis = PinRiskAnalysis(
            symbol='SPY',
            timestamp=datetime.now(),
            pin_risk_score=65,
            pin_risk_level=PinRiskLevel.HIGH,
            days_to_weekly_expiry=2,
            expected_range_low=585.0,
            expected_range_high=595.0,
            expected_range_pct=1.7
        )
        analysis.gamma_levels = GammaLevels(
            max_pain=590.0,
            call_wall=595.0,
            put_wall=585.0,
            flip_point=588.0,
            net_gex=0.5
        )
        result = analysis.to_dict()

        # Original field names should still exist
        assert 'pin_risk_score' in result, "Missing backward compat 'pin_risk_score'"
        assert 'pin_risk_level' in result, "Missing backward compat 'pin_risk_level'"
        assert 'days_to_weekly_expiry' in result, "Missing backward compat 'days_to_weekly_expiry'"
        assert 'expected_range_low' in result, "Missing backward compat 'expected_range_low'"
        assert 'expected_range_high' in result, "Missing backward compat 'expected_range_high'"
        assert 'expected_range_pct' in result, "Missing backward compat 'expected_range_pct'"
        assert 'gamma_levels' in result, "Missing backward compat 'gamma_levels'"

    def test_to_dict_complete_frontend_interface(self):
        """Test that to_dict provides all fields needed by frontend PinRisk interface"""
        from core.pin_risk_analyzer import (
            PinRiskAnalysis, PinRiskLevel, GammaRegime, GammaLevels,
            PinFactor, TradingImplication
        )

        analysis = PinRiskAnalysis(
            symbol='SPY',
            timestamp=datetime.now(),
            spot_price=590.50,
            pin_risk_score=65,
            pin_risk_level=PinRiskLevel.HIGH,
            gamma_regime=GammaRegime.POSITIVE,
            gamma_regime_description='Positive gamma environment',
            long_call_outlook='challenging',
            days_to_weekly_expiry=2,
            is_expiration_day=False,
            expected_range_low=585.0,
            expected_range_high=595.0,
            expected_range_pct=1.7,
            summary='Test summary'
        )
        analysis.gamma_levels = GammaLevels(
            max_pain=590.0,
            call_wall=595.0,
            put_wall=585.0,
            flip_point=588.0,
            net_gex=0.5
        )
        analysis.pin_factors = [
            PinFactor(name='test', score=10, description='Test factor')
        ]
        analysis.trading_implications = [
            TradingImplication(
                position_type='long_calls',
                outlook='unfavorable',
                reasoning='Test',
                recommendation='Test'
            )
        ]
        analysis.pin_breakers = ['Test breaker']

        result = analysis.to_dict()

        # All fields expected by frontend PinRisk interface
        frontend_required = [
            'score', 'level', 'gamma_regime', 'gamma_regime_description',
            'long_call_outlook', 'max_pain', 'call_wall', 'put_wall',
            'flip_point', 'expected_range', 'days_to_expiry',
            'is_expiration_day', 'pin_factors', 'trading_implications',
            'pin_breakers', 'summary'
        ]

        for field in frontend_required:
            assert field in result, f"Missing frontend required field: {field}"

        # Verify expected_range structure
        assert result['expected_range']['low'] == 585.0
        assert result['expected_range']['high'] == 595.0
        assert result['expected_range']['pct'] == 1.7


class TestGammaLevelsToDict:
    """Tests for GammaLevels.to_dict()"""

    def test_gamma_levels_to_dict(self):
        """Test GammaLevels serialization"""
        from core.pin_risk_analyzer import GammaLevels

        levels = GammaLevels(
            flip_point=588.0,
            call_wall=595.0,
            put_wall=585.0,
            max_pain=590.0,
            net_gex=0.5,
            call_gex=1.2,
            put_gex=-0.7
        )
        result = levels.to_dict()

        assert result['flip_point'] == 588.0
        assert result['call_wall'] == 595.0
        assert result['put_wall'] == 585.0
        assert result['max_pain'] == 590.0
        assert result['net_gex'] == 0.5
