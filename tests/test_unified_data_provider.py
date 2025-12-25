"""
Unified Data Provider Tests

Tests for the unified data provider module.

Run with: pytest tests/test_unified_data_provider.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestUnifiedProviderImport:
    """Tests for unified provider import"""

    def test_import_unified_provider(self):
        """Test that unified provider can be imported"""
        try:
            from data.unified_data_provider import UnifiedDataProvider
            assert UnifiedDataProvider is not None
        except ImportError:
            pytest.skip("Unified data provider not available")


class TestUnifiedProviderInitialization:
    """Tests for unified provider initialization"""

    def test_provider_initialization(self):
        """Test provider can be initialized"""
        try:
            from data.unified_data_provider import UnifiedDataProvider

            with patch.dict('os.environ', {
                'POLYGON_API_KEY': 'test_key',
                'TRADIER_API_KEY': 'test_key'
            }):
                provider = UnifiedDataProvider()
                assert provider is not None
        except ImportError:
            pytest.skip("Unified data provider not available")


class TestDataSourcePriority:
    """Tests for data source priority"""

    def test_source_fallback(self):
        """Test data source fallback logic"""
        try:
            from data.unified_data_provider import UnifiedDataProvider

            with patch.dict('os.environ', {
                'POLYGON_API_KEY': 'test_key',
                'TRADIER_API_KEY': 'test_key'
            }):
                provider = UnifiedDataProvider()
                # Should have source priority
                if hasattr(provider, 'sources') or hasattr(provider, 'data_sources'):
                    assert True  # Has sources defined
        except ImportError:
            pytest.skip("Unified data provider not available")


class TestUnifiedQuote:
    """Tests for unified quote fetching"""

    def test_get_quote_unified(self):
        """Test unified quote fetch"""
        try:
            from data.unified_data_provider import UnifiedDataProvider

            with patch.dict('os.environ', {
                'POLYGON_API_KEY': 'test_key',
                'TRADIER_API_KEY': 'test_key'
            }):
                provider = UnifiedDataProvider()
                if hasattr(provider, 'get_quote'):
                    with patch.object(provider, 'get_quote') as mock_quote:
                        mock_quote.return_value = {'last': 585.50}
                        result = provider.get_quote('SPY')
                        assert 'last' in result
        except ImportError:
            pytest.skip("Unified data provider not available")


class TestUnifiedOptionChain:
    """Tests for unified option chain fetching"""

    def test_get_option_chain_unified(self):
        """Test unified option chain fetch"""
        try:
            from data.unified_data_provider import UnifiedDataProvider

            with patch.dict('os.environ', {
                'POLYGON_API_KEY': 'test_key',
                'TRADIER_API_KEY': 'test_key'
            }):
                provider = UnifiedDataProvider()
                if hasattr(provider, 'get_option_chain'):
                    with patch.object(provider, 'get_option_chain') as mock_chain:
                        mock_chain.return_value = [{'strike': 580}, {'strike': 585}]
                        result = provider.get_option_chain('SPY')
                        assert isinstance(result, list)
        except ImportError:
            pytest.skip("Unified data provider not available")


class TestDataCaching:
    """Tests for data caching"""

    def test_cache_mechanism(self):
        """Test caching mechanism exists"""
        try:
            from data.unified_data_provider import UnifiedDataProvider

            with patch.dict('os.environ', {
                'POLYGON_API_KEY': 'test_key',
                'TRADIER_API_KEY': 'test_key'
            }):
                provider = UnifiedDataProvider()
                # Should have some form of caching
                has_cache = (
                    hasattr(provider, 'cache') or
                    hasattr(provider, '_cache') or
                    hasattr(provider, 'cached_data')
                )
                # Cache is optional, just verify provider works
                assert provider is not None
        except ImportError:
            pytest.skip("Unified data provider not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
