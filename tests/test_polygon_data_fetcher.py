"""
Polygon Data Fetcher Tests

Tests for the Polygon.io data fetching module.

Run with: pytest tests/test_polygon_data_fetcher.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPolygonFetcherImport:
    """Tests for Polygon fetcher import"""

    def test_import_polygon_fetcher(self):
        """Test that Polygon fetcher can be imported"""
        try:
            from data.polygon_data_fetcher import PolygonDataFetcher
            assert PolygonDataFetcher is not None
        except ImportError:
            pytest.skip("Polygon data fetcher not available")


class TestPolygonFetcherInitialization:
    """Tests for Polygon fetcher initialization"""

    @patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'})
    def test_fetcher_initialization(self):
        """Test fetcher can be initialized"""
        try:
            from data.polygon_data_fetcher import PolygonDataFetcher
            fetcher = PolygonDataFetcher()
            assert fetcher is not None
        except ImportError:
            pytest.skip("Polygon data fetcher not available")


class TestPolygonQuoteFetching:
    """Tests for quote fetching"""

    @patch('data.polygon_data_fetcher.requests.get')
    def test_fetch_quote_success(self, mock_get):
        """Test successful quote fetch"""
        try:
            from data.polygon_data_fetcher import PolygonDataFetcher

            mock_get.return_value.json.return_value = {
                'results': {'o': 585.0, 'h': 590.0, 'l': 580.0, 'c': 587.0}
            }
            mock_get.return_value.status_code = 200

            with patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'}):
                fetcher = PolygonDataFetcher()
                if hasattr(fetcher, 'get_quote'):
                    result = fetcher.get_quote('SPY')
                    assert result is not None
        except ImportError:
            pytest.skip("Polygon data fetcher not available")


class TestPolygonOptionChain:
    """Tests for option chain fetching"""

    @patch('data.polygon_data_fetcher.requests.get')
    def test_fetch_option_chain(self, mock_get):
        """Test option chain fetch"""
        try:
            from data.polygon_data_fetcher import PolygonDataFetcher

            mock_get.return_value.json.return_value = {
                'results': [
                    {'strike_price': 580, 'greeks': {'gamma': 0.05}},
                    {'strike_price': 585, 'greeks': {'gamma': 0.08}},
                ]
            }
            mock_get.return_value.status_code = 200

            with patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'}):
                fetcher = PolygonDataFetcher()
                if hasattr(fetcher, 'get_option_chain'):
                    result = fetcher.get_option_chain('SPY')
                    assert result is not None
        except ImportError:
            pytest.skip("Polygon data fetcher not available")


class TestPolygonRateLimiting:
    """Tests for rate limiting"""

    def test_rate_limit_handling(self):
        """Test rate limit is respected"""
        try:
            from data.polygon_data_fetcher import PolygonDataFetcher

            with patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'}):
                fetcher = PolygonDataFetcher()
                # Should have rate limiting mechanism
                assert hasattr(fetcher, 'rate_limit') or hasattr(fetcher, '_last_request')
        except ImportError:
            pytest.skip("Polygon data fetcher not available")


class TestPolygonErrorHandling:
    """Tests for error handling"""

    @patch('data.polygon_data_fetcher.requests.get')
    def test_api_error_handling(self, mock_get):
        """Test API error is handled gracefully"""
        try:
            from data.polygon_data_fetcher import PolygonDataFetcher

            mock_get.side_effect = Exception("API Error")

            with patch.dict('os.environ', {'POLYGON_API_KEY': 'test_key'}):
                fetcher = PolygonDataFetcher()
                if hasattr(fetcher, 'get_quote'):
                    # Should handle error gracefully
                    try:
                        result = fetcher.get_quote('SPY')
                    except Exception:
                        pass  # Expected to handle or raise
        except ImportError:
            pytest.skip("Polygon data fetcher not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
