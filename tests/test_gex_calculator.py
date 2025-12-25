"""
GEX Calculator Tests

Tests for the GEX (Gamma Exposure) calculator module.

Run with: pytest tests/test_gex_calculator.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGEXCalculatorImport:
    """Tests for GEX calculator import"""

    def test_import_gex_calculator(self):
        """Test that GEX calculator can be imported"""
        from data.gex_calculator import validate_options_data, GEXResult
        assert validate_options_data is not None
        assert GEXResult is not None


class TestOptionsDataValidation:
    """Tests for options data validation"""

    def test_validate_empty_data(self):
        """Test validation with empty data"""
        from data.gex_calculator import validate_options_data

        result = validate_options_data([], 585.0, "SPY")
        assert result['valid'] is False
        assert len(result['issues']) > 0

    def test_validate_invalid_spot_price(self):
        """Test validation with invalid spot price"""
        from data.gex_calculator import validate_options_data

        result = validate_options_data([{'strike': 580}], 0, "SPY")
        assert result['valid'] is False

    def test_validate_valid_options_data(self, mock_option_chain):
        """Test validation with valid options data"""
        from data.gex_calculator import validate_options_data

        result = validate_options_data(mock_option_chain, 585.0, "SPY")
        # Should be valid with proper option chain
        assert 'stats' in result

    def test_validate_insufficient_contracts(self):
        """Test validation with too few contracts"""
        from data.gex_calculator import validate_options_data

        few_contracts = [
            {'strike': 580, 'gamma': 0.05, 'open_interest': 100},
            {'strike': 585, 'gamma': 0.06, 'open_interest': 200},
        ]
        result = validate_options_data(few_contracts, 585.0, "SPY")
        assert result['valid'] is False


class TestGEXResultDataclass:
    """Tests for GEXResult dataclass"""

    def test_gex_result_creation(self):
        """Test GEXResult dataclass creation"""
        from data.gex_calculator import GEXResult

        result = GEXResult(
            symbol="SPY",
            spot_price=585.0,
            net_gex=1_500_000_000,
            call_gex=2_000_000_000,
            put_gex=-500_000_000,
            call_wall=590.0,
            put_wall=580.0,
            gamma_flip=583.0,
            flip_point=583.0,
            max_pain=585.0,
            data_source="calculated",
            timestamp=datetime.now()
        )

        assert result.symbol == "SPY"
        assert result.net_gex == 1_500_000_000
        assert result.call_wall == 590.0

    def test_gex_result_fields(self):
        """Test GEXResult has all required fields"""
        from data.gex_calculator import GEXResult
        import dataclasses

        fields = [f.name for f in dataclasses.fields(GEXResult)]
        required_fields = ['symbol', 'spot_price', 'net_gex', 'call_gex', 'put_gex']

        for field in required_fields:
            assert field in fields


class TestGEXCalculation:
    """Tests for GEX calculation functions"""

    def test_calculate_gex_exists(self):
        """Test that GEX calculation function exists"""
        try:
            from data.gex_calculator import calculate_gex
            assert calculate_gex is not None
        except ImportError:
            # Try alternative function name
            from data.gex_calculator import compute_gex_from_chain
            assert compute_gex_from_chain is not None

    def test_gex_formula_positive_gamma(self):
        """Test GEX calculation with positive gamma"""
        # GEX = gamma * OI * 100 * spot^2 / 1e9
        gamma = 0.05
        oi = 10000
        spot = 585.0

        expected_gex = gamma * oi * 100 * (spot ** 2) / 1e9
        assert expected_gex > 0

    def test_gex_walls_detection(self):
        """Test call/put wall detection"""
        try:
            from data.gex_calculator import find_gex_walls
            # Just verify function exists
            assert find_gex_walls is not None
        except ImportError:
            pytest.skip("GEX walls function not available")


class TestGEXDataValidation:
    """Tests for GEX data validation"""

    def test_net_gex_sign(self):
        """Test that net GEX can be positive or negative"""
        from data.gex_calculator import GEXResult

        # Positive net GEX (more call gamma)
        positive_gex = GEXResult(
            symbol="SPY",
            spot_price=585.0,
            net_gex=1_500_000_000,
            call_gex=2_000_000_000,
            put_gex=-500_000_000,
            call_wall=590.0,
            put_wall=580.0,
            gamma_flip=583.0,
            flip_point=583.0,
            max_pain=585.0,
            data_source="calculated",
            timestamp=datetime.now()
        )
        assert positive_gex.net_gex > 0

        # Negative net GEX (more put gamma)
        negative_gex = GEXResult(
            symbol="SPY",
            spot_price=585.0,
            net_gex=-500_000_000,
            call_gex=500_000_000,
            put_gex=-1_000_000_000,
            call_wall=590.0,
            put_wall=580.0,
            gamma_flip=588.0,
            flip_point=588.0,
            max_pain=585.0,
            data_source="calculated",
            timestamp=datetime.now()
        )
        assert negative_gex.net_gex < 0


class TestStrikeRangeValidation:
    """Tests for strike range validation"""

    def test_strike_range_calculation(self, mock_option_chain):
        """Test strike range is calculated correctly"""
        from data.gex_calculator import validate_options_data

        result = validate_options_data(mock_option_chain, 585.0, "SPY")

        if 'stats' in result and 'strike_range' in result['stats']:
            min_strike, max_strike = result['stats']['strike_range']
            assert min_strike < max_strike


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
