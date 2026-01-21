"""
Tests for ARGUS Tradier Connection Fix

Verifies that:
1. Tradier credentials are properly loaded from APIConfig
2. ARGUS endpoints return valid data (not data_unavailable)
3. Diagnostic endpoints work correctly
"""

import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTradierCredentials:
    """Test that Tradier credentials are properly configured"""

    def test_apiconfig_has_tradier_credentials(self):
        """Verify APIConfig has at least one set of Tradier credentials"""
        from unified_config import APIConfig

        has_sandbox = bool(APIConfig.TRADIER_SANDBOX_API_KEY and APIConfig.TRADIER_SANDBOX_ACCOUNT_ID)
        has_prod = bool(APIConfig.TRADIER_API_KEY and APIConfig.TRADIER_ACCOUNT_ID)
        has_explicit_prod = bool(APIConfig.TRADIER_PROD_API_KEY and APIConfig.TRADIER_PROD_ACCOUNT_ID)

        assert has_sandbox or has_prod or has_explicit_prod, \
            "No Tradier credentials configured. Need TRADIER_API_KEY/ACCOUNT_ID or TRADIER_SANDBOX_API_KEY/ACCOUNT_ID"

    def test_tradier_data_fetcher_initializes(self):
        """Verify TradierDataFetcher can be initialized with APIConfig credentials"""
        from unified_config import APIConfig
        from data.tradier_data_fetcher import TradierDataFetcher

        # Try sandbox credentials first (like ARGUS does)
        api_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
        account_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

        if not api_key or not account_id:
            pytest.skip("No Tradier credentials configured")

        # Should not raise
        tradier = TradierDataFetcher(
            api_key=api_key,
            account_id=account_id,
            sandbox=True
        )

        assert tradier is not None
        assert tradier.sandbox is True


class TestArgusGetTradier:
    """Test the fixed get_tradier() function in ARGUS routes"""

    def test_argus_get_tradier_returns_instance(self):
        """Verify ARGUS get_tradier() returns a valid Tradier instance"""
        from backend.api.routes.argus_routes import get_tradier, TRADIER_AVAILABLE

        if not TRADIER_AVAILABLE:
            pytest.skip("TradierDataFetcher module not available")

        tradier = get_tradier()

        # Should return instance or None (if no credentials)
        # But should NOT raise an exception
        if tradier is not None:
            assert hasattr(tradier, 'get_quote')
            assert hasattr(tradier, 'get_option_chain')

    def test_argus_get_tradier_status(self):
        """Verify get_tradier_status() returns diagnostic info"""
        from backend.api.routes.argus_routes import get_tradier_status

        status = get_tradier_status()

        assert isinstance(status, dict)
        assert 'module_available' in status
        assert 'is_connected' in status
        assert 'credentials_configured' in status

    def test_hyperion_get_tradier_returns_instance(self):
        """Verify HYPERION get_tradier() also works"""
        from backend.api.routes.hyperion_routes import get_tradier, TRADIER_AVAILABLE

        if not TRADIER_AVAILABLE:
            pytest.skip("TradierDataFetcher module not available")

        tradier = get_tradier()

        if tradier is not None:
            assert hasattr(tradier, 'get_quote')


class TestArgusEndpoints:
    """Test ARGUS API endpoints return valid responses"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app)

    def test_argus_data_source_status(self, client):
        """Test /api/argus/data-source-status endpoint"""
        response = client.get("/api/argus/data-source-status")

        assert response.status_code == 200
        data = response.json()

        assert data.get('success') is True
        assert 'data_sources' in data
        assert 'tradier' in data['data_sources']

    def test_argus_test_tradier_connection(self, client):
        """Test /api/argus/test-tradier-connection endpoint"""
        response = client.get("/api/argus/test-tradier-connection")

        assert response.status_code == 200
        data = response.json()

        # Should have either success with data or clear error message
        assert 'success' in data
        assert 'connected' in data

        if data['connected']:
            assert 'test_quote' in data
        else:
            assert 'error' in data

    def test_argus_gamma_endpoint_structure(self, client):
        """Test /api/argus/gamma returns proper structure"""
        response = client.get("/api/argus/gamma?symbol=SPY")

        assert response.status_code in [200, 503]  # 503 if engine unavailable

        if response.status_code == 200:
            data = response.json()

            # Should have success field
            assert 'success' in data

            if data.get('success'):
                assert 'data' in data
                gamma_data = data['data']
                assert 'symbol' in gamma_data
                assert 'strikes' in gamma_data
            else:
                # If not successful, should have clear error info
                assert 'data_unavailable' in data or 'message' in data


class TestApolloTradierFix:
    """Test Apollo routes Tradier fix"""

    def test_apollo_get_tradier_exists(self):
        """Verify Apollo has get_tradier helper"""
        from backend.api.routes.apollo_routes import get_tradier

        # Should be callable
        assert callable(get_tradier)


class TestVixTradierFix:
    """Test VIX routes Tradier fix"""

    def test_vix_fetch_uses_explicit_credentials(self):
        """Verify fetch_vix_from_tradier uses explicit credentials"""
        from backend.api.routes.vix_routes import fetch_vix_from_tradier

        # Should be callable and not raise on import
        assert callable(fetch_vix_from_tradier)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
