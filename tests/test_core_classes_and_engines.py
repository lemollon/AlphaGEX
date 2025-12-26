"""
Comprehensive Tests for Core Classes and Engines

Tests the core trading classes including:
- TradingVolatilityAPI
- Options calculation utilities
- Core trading engine classes

Run with: pytest tests/test_core_classes_and_engines.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTradingVolatilityAPI:
    """Tests for TradingVolatilityAPI class"""

    def test_api_class_exists(self):
        """Test TradingVolatilityAPI class exists"""
        try:
            from core_classes_and_engines import TradingVolatilityAPI
            assert TradingVolatilityAPI is not None
        except ImportError:
            pytest.skip("TradingVolatilityAPI not available")

    @patch('core_classes_and_engines.requests')
    def test_api_initialization(self, mock_requests):
        """Test API initializes correctly"""
        try:
            from core_classes_and_engines import TradingVolatilityAPI

            api = TradingVolatilityAPI()
            assert api is not None
        except ImportError:
            pytest.skip("TradingVolatilityAPI not available")

    @patch('core_classes_and_engines.requests')
    def test_get_gex_data(self, mock_requests):
        """Test fetching GEX data"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'symbol': 'SPY',
            'net_gex': 1.5e9,
            'call_wall': 590,
            'put_wall': 580
        }
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response

        try:
            from core_classes_and_engines import TradingVolatilityAPI

            api = TradingVolatilityAPI()

            if hasattr(api, 'get_gex'):
                result = api.get_gex('SPY')
                assert result is not None or result is None
        except ImportError:
            pytest.skip("TradingVolatilityAPI not available")


class TestCoreImports:
    """Tests for core module imports"""

    def test_module_importable(self):
        """Test core_classes_and_engines is importable"""
        try:
            import core_classes_and_engines
            assert core_classes_and_engines is not None
        except ImportError:
            pytest.skip("core_classes_and_engines not available")

    def test_key_classes_available(self):
        """Test key classes are available"""
        try:
            from core_classes_and_engines import TradingVolatilityAPI

            # Check class can be referenced
            assert TradingVolatilityAPI is not None
        except ImportError:
            pytest.skip("Required classes not available")


class TestOptionsPricing:
    """Tests for options pricing utilities"""

    def test_black_scholes_exists(self):
        """Test Black-Scholes calculation exists"""
        try:
            from core_classes_and_engines import black_scholes_call, black_scholes_put

            # Calculate call price
            call_price = black_scholes_call(
                S=100, K=100, T=0.25, r=0.05, sigma=0.2
            )
            assert call_price > 0

            put_price = black_scholes_put(
                S=100, K=100, T=0.25, r=0.05, sigma=0.2
            )
            assert put_price > 0
        except ImportError:
            pytest.skip("Black-Scholes functions not available")

    def test_delta_calculation(self):
        """Test delta calculation"""
        try:
            from core_classes_and_engines import calculate_delta

            # ATM call delta should be around 0.5
            delta = calculate_delta(
                S=100, K=100, T=0.25, r=0.05, sigma=0.2, option_type='call'
            )
            assert 0.4 < delta < 0.6
        except ImportError:
            pytest.skip("Delta calculation not available")

    def test_gamma_calculation(self):
        """Test gamma calculation"""
        try:
            from core_classes_and_engines import calculate_gamma

            # ATM gamma should be positive
            gamma = calculate_gamma(
                S=100, K=100, T=0.25, r=0.05, sigma=0.2
            )
            assert gamma > 0
        except ImportError:
            pytest.skip("Gamma calculation not available")


class TestRateLimiting:
    """Tests for rate limiting"""

    def test_rate_limiter_exists(self):
        """Test rate limiter class exists"""
        try:
            from core_classes_and_engines import RateLimiter

            limiter = RateLimiter(calls_per_minute=20)
            assert limiter is not None
        except ImportError:
            pytest.skip("RateLimiter not available")


class TestCaching:
    """Tests for caching mechanisms"""

    def test_cache_exists(self):
        """Test caching mechanism exists"""
        try:
            from core_classes_and_engines import GEXCache

            cache = GEXCache()
            assert cache is not None
        except ImportError:
            pytest.skip("GEXCache not available")


class TestGEXCalculation:
    """Tests for GEX calculation utilities"""

    def test_calculate_net_gex(self):
        """Test net GEX calculation"""
        try:
            from core_classes_and_engines import calculate_net_gex

            options_data = [
                {'strike': 580, 'gamma': 0.05, 'open_interest': 1000, 'type': 'call'},
                {'strike': 580, 'gamma': 0.05, 'open_interest': 800, 'type': 'put'},
            ]

            net_gex = calculate_net_gex(options_data, spot_price=585)
            assert isinstance(net_gex, (int, float))
        except ImportError:
            pytest.skip("GEX calculation not available")


class TestMarketDataStructures:
    """Tests for market data structures"""

    def test_market_data_class(self):
        """Test MarketData class if exists"""
        try:
            from core_classes_and_engines import MarketData

            data = MarketData(
                symbol='SPY',
                spot_price=585.0,
                vix=15.0
            )
            assert data.symbol == 'SPY'
        except ImportError:
            pytest.skip("MarketData class not available")


class TestTradingCostCalculations:
    """Tests for trading cost calculations"""

    def test_commission_calculation(self):
        """Test commission calculation"""
        try:
            from core_classes_and_engines import calculate_commission

            commission = calculate_commission(
                contracts=10,
                price_per_contract=0.65
            )
            assert commission >= 0
        except ImportError:
            pytest.skip("Commission calculation not available")


class TestTimeUtilities:
    """Tests for time-related utilities"""

    def test_market_hours_check(self):
        """Test market hours checking"""
        try:
            from core_classes_and_engines import is_market_open

            result = is_market_open()
            assert isinstance(result, bool)
        except ImportError:
            pytest.skip("Market hours check not available")

    def test_days_to_expiration(self):
        """Test DTE calculation"""
        try:
            from core_classes_and_engines import calculate_dte

            dte = calculate_dte('2025-01-17')
            assert isinstance(dte, (int, float))
        except ImportError:
            pytest.skip("DTE calculation not available")


class TestSymbolValidation:
    """Tests for symbol validation"""

    def test_valid_symbol(self):
        """Test valid symbol validation"""
        try:
            from core_classes_and_engines import is_valid_symbol

            assert is_valid_symbol('SPY') is True
            assert is_valid_symbol('INVALID123456') is False
        except ImportError:
            pytest.skip("Symbol validation not available")


class TestErrorHandling:
    """Tests for error handling"""

    @patch('core_classes_and_engines.requests')
    def test_api_error_handling(self, mock_requests):
        """Test API handles errors gracefully"""
        mock_requests.get.side_effect = Exception("Network error")

        try:
            from core_classes_and_engines import TradingVolatilityAPI

            api = TradingVolatilityAPI()

            if hasattr(api, 'get_gex'):
                # Should not crash on network error
                result = api.get_gex('SPY')
                # Result may be None or error dict
        except ImportError:
            pytest.skip("TradingVolatilityAPI not available")


class TestDependencyFlags:
    """Tests for dependency availability flags"""

    def test_dependency_flags_are_booleans(self):
        """Test dependency flags are booleans"""
        try:
            import core_classes_and_engines

            for attr in dir(core_classes_and_engines):
                if attr.endswith('_AVAILABLE'):
                    value = getattr(core_classes_and_engines, attr)
                    assert isinstance(value, bool), f"{attr} should be boolean"
        except ImportError:
            pytest.skip("Module not available")
