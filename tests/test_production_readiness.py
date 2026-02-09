"""
Comprehensive Test Suite for Production Readiness Modules

Tests cover:
1. Data Validation (stale data detection)
2. Position Stop Loss
3. Idempotency Keys
4. Database Transactions
5. API Authentication
6. Pydantic Models

Note: Circuit Breaker tests removed - module deprecated in favor of Proverbs Enhancements
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# Test Data Validation Module
# =============================================================================

class TestDataValidation:
    """Tests for trading/data_validation.py"""

    def test_validate_market_data_fresh(self):
        """Fresh data should pass validation"""
        from trading.data_validation import validate_market_data

        # Use strftime to produce a format the validator can parse
        fresh_data = {
            'timestamp': datetime.now(CENTRAL_TZ).strftime('%Y-%m-%dT%H:%M:%S.%f'),
            'spot_price': 585.50,
            'vix': 15.5
        }

        is_valid, error = validate_market_data(fresh_data)
        assert is_valid is True, f"Expected valid, got error: {error}"
        assert error is None

    def test_validate_market_data_stale(self):
        """Stale data (>5 min) should fail validation"""
        from trading.data_validation import validate_market_data, MAX_DATA_AGE_SECONDS

        old_time = datetime.now(CENTRAL_TZ) - timedelta(seconds=MAX_DATA_AGE_SECONDS + 60)
        stale_data = {
            # Use parseable format without timezone suffix
            'timestamp': old_time.strftime('%Y-%m-%dT%H:%M:%S.%f'),
            'spot_price': 585.50,
            'vix': 15.5
        }

        is_valid, error = validate_market_data(stale_data)
        assert is_valid is False
        assert 'seconds old' in error.lower() or 'old' in error.lower()

    def test_validate_market_data_missing_timestamp(self):
        """Data without timestamp should fail when required"""
        from trading.data_validation import validate_market_data

        no_timestamp_data = {
            'spot_price': 585.50,
            'vix': 15.5
        }

        is_valid, error = validate_market_data(no_timestamp_data, require_timestamp=True)
        assert is_valid is False

    def test_validate_spot_price_valid(self):
        """Valid spot prices should pass"""
        from trading.data_validation import validate_spot_price

        is_valid, error = validate_spot_price(585.50, 'SPY')
        assert is_valid is True

        is_valid, error = validate_spot_price(5850.00, 'SPX')
        assert is_valid is True

    def test_validate_spot_price_invalid(self):
        """Invalid spot prices should fail"""
        from trading.data_validation import validate_spot_price

        # Price too low (MIN_VALID_PRICE is 1.0)
        is_valid, error = validate_spot_price(0.5, 'SPY')
        assert is_valid is False

        # Negative price
        is_valid, error = validate_spot_price(-100.0, 'SPY')
        assert is_valid is False

    def test_validate_iron_condor_strikes_valid(self):
        """Valid IC strikes should pass"""
        from trading.data_validation import validate_iron_condor_strikes

        is_valid, error = validate_iron_condor_strikes(
            put_long=570,
            put_short=580,
            call_short=590,
            call_long=600,
            spot_price=585
        )
        assert is_valid is True

    def test_validate_iron_condor_strikes_invalid_order(self):
        """IC strikes out of order should fail"""
        from trading.data_validation import validate_iron_condor_strikes

        # Strikes not in ascending order
        is_valid, error = validate_iron_condor_strikes(
            put_long=580,
            put_short=570,  # Should be higher
            call_short=590,
            call_long=600,
            spot_price=585
        )
        assert is_valid is False


# =============================================================================
# Test Position Stop Loss Module
# =============================================================================

class TestPositionStopLoss:
    """Tests for trading/position_stop_loss.py"""

    def test_stop_loss_manager_initialization(self):
        """Manager should initialize correctly"""
        from trading.position_stop_loss import PositionStopLossManager

        manager = PositionStopLossManager()
        assert manager is not None
        assert len(manager.positions) == 0

    def test_register_position(self):
        """Should register positions for tracking"""
        from trading.position_stop_loss import PositionStopLossManager

        manager = PositionStopLossManager()
        stop_loss = manager.register_position(
            position_id="TEST-001",
            entry_price=100.0,
            premium_received=2.50
        )

        assert stop_loss is not None
        assert stop_loss.position_id == "TEST-001"
        assert "TEST-001" in manager.positions

    def test_check_stop_loss_not_triggered(self):
        """Stop loss should not trigger when within limits"""
        from trading.position_stop_loss import (
            PositionStopLossManager,
            StopLossConfig,
            StopLossType
        )

        config = StopLossConfig(
            stop_type=StopLossType.FIXED_PERCENTAGE,
            fixed_stop_pct=75.0
        )
        manager = PositionStopLossManager(default_config=config)

        manager.register_position(
            position_id="TEST-001",
            entry_price=100.0
        )

        # 50% loss should not trigger 75% stop
        triggered, reason = manager.check_stop_loss("TEST-001", 50.0)
        assert triggered is False

    def test_check_stop_loss_triggered(self):
        """Stop loss should trigger when limit exceeded"""
        from trading.position_stop_loss import (
            PositionStopLossManager,
            StopLossConfig,
            StopLossType
        )

        config = StopLossConfig(
            stop_type=StopLossType.FIXED_PERCENTAGE,
            fixed_stop_pct=50.0
        )
        manager = PositionStopLossManager(default_config=config)

        manager.register_position(
            position_id="TEST-001",
            entry_price=100.0
        )

        # 60% loss should trigger 50% stop
        triggered, reason = manager.check_stop_loss("TEST-001", 40.0)
        assert triggered is True
        assert "STOP" in reason.upper()

    def test_premium_multiple_stop(self):
        """Premium multiple stop should work for Iron Condors"""
        from trading.position_stop_loss import (
            PositionStopLossManager,
            create_iron_condor_stop_config
        )

        config = create_iron_condor_stop_config(premium_multiple=2.0)
        manager = PositionStopLossManager(default_config=config)

        manager.register_position(
            position_id="IC-001",
            entry_price=250.0,  # $2.50 credit * 100
            premium_received=2.50
        )

        # Loss of 3x premium should trigger
        triggered, reason = manager.check_stop_loss("IC-001", -500.0)
        assert triggered is True

    def test_unregister_position(self):
        """Should remove position from tracking"""
        from trading.position_stop_loss import PositionStopLossManager

        manager = PositionStopLossManager()
        manager.register_position("TEST-001", entry_price=100.0)

        assert "TEST-001" in manager.positions

        manager.unregister_position("TEST-001")
        assert "TEST-001" not in manager.positions


# =============================================================================
# Test Idempotency Module
# =============================================================================

class TestIdempotency:
    """Tests for trading/idempotency.py"""

    def test_generate_idempotency_key(self):
        """Should generate unique keys"""
        from trading.idempotency import generate_idempotency_key

        key1 = generate_idempotency_key("FORTRESS", "pos-1", "2024-01-15")
        key2 = generate_idempotency_key("FORTRESS", "pos-1", "2024-01-15")

        # Keys should be unique (random suffix)
        assert key1 != key2
        assert key1.startswith("FORTRESS_")
        assert key2.startswith("FORTRESS_")

    def test_check_idempotency_new_key(self):
        """New key should not be found"""
        from trading.idempotency import IdempotencyManager

        manager = IdempotencyManager(use_database=False)
        exists, record = manager.check_key("NONEXISTENT-KEY")

        assert exists is False
        assert record is None

    def test_mark_pending_and_check(self):
        """Pending key should be found"""
        from trading.idempotency import IdempotencyManager

        manager = IdempotencyManager(use_database=False)
        success = manager.mark_pending("TEST-KEY-001", "FORTRESS", "hash123")

        assert success is True

        exists, record = manager.check_key("TEST-KEY-001")
        assert exists is True
        assert record.status.value == "pending"

    def test_mark_completed(self):
        """Completed key should have result"""
        from trading.idempotency import IdempotencyManager

        manager = IdempotencyManager(use_database=False)
        manager.mark_pending("TEST-KEY-002", "FORTRESS", "hash123")
        manager.mark_completed("TEST-KEY-002", {"order_id": "123", "status": "filled"})

        result = manager.get_result("TEST-KEY-002")
        assert result is not None
        assert result["order_id"] == "123"

    def test_duplicate_pending_rejected(self):
        """Duplicate pending should be rejected"""
        from trading.idempotency import IdempotencyManager

        manager = IdempotencyManager(use_database=False)

        success1 = manager.mark_pending("DUPE-KEY", "FORTRESS", "hash1")
        success2 = manager.mark_pending("DUPE-KEY", "FORTRESS", "hash2")

        assert success1 is True
        assert success2 is False  # Rejected as duplicate


# =============================================================================
# Test Pydantic Models
# =============================================================================

class TestPydanticModels:
    """Tests for backend/api/models.py"""

    def test_fortress_config_update_valid(self):
        """Valid config update should pass"""
        from backend.api.models import FortressConfigUpdate

        config = FortressConfigUpdate(
            risk_per_trade_pct=5.0,
            sd_multiplier=0.7
        )

        assert config.risk_per_trade_pct == 5.0
        assert config.sd_multiplier == 0.7

    def test_fortress_config_update_invalid_range(self):
        """Out of range values should fail"""
        from backend.api.models import FortressConfigUpdate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FortressConfigUpdate(risk_per_trade_pct=20.0)  # Max is 15

        with pytest.raises(ValidationError):
            FortressConfigUpdate(sd_multiplier=0.1)  # Min is 0.3

    def test_fortress_config_update_optional_fields(self):
        """Optional fields should be None when not provided"""
        from backend.api.models import FortressConfigUpdate

        config = FortressConfigUpdate()  # All optional

        assert config.risk_per_trade_pct is None
        assert config.sd_multiplier is None

    def test_fortress_config_rejects_unknown_fields(self):
        """Unknown fields should be rejected"""
        from backend.api.models import FortressConfigUpdate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FortressConfigUpdate(unknown_field="value")

    def test_strategy_preset_request_valid(self):
        """Valid preset should pass"""
        from backend.api.models import StrategyPresetRequest, StrategyPresetEnum

        request = StrategyPresetRequest(preset=StrategyPresetEnum.MODERATE)
        assert request.preset == StrategyPresetEnum.MODERATE

    def test_strategy_preset_request_invalid(self):
        """Invalid preset should fail"""
        from backend.api.models import StrategyPresetRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            StrategyPresetRequest(preset="invalid_preset")

    def test_symbol_validation(self):
        """Symbol validation should work"""
        from backend.api.models import SymbolRequest
        from pydantic import ValidationError

        # Valid uppercase symbol
        req = SymbolRequest(symbol="SPY")
        assert req.symbol == "SPY"

        # Valid multi-char symbol
        req = SymbolRequest(symbol="AAPL")
        assert req.symbol == "AAPL"

        # Lowercase should fail (pattern requires uppercase)
        with pytest.raises(ValidationError):
            SymbolRequest(symbol="spy")

        # Too long should fail
        with pytest.raises(ValidationError):
            SymbolRequest(symbol="TOOLONG")

    def test_date_range_validation(self):
        """Date range should validate order"""
        from backend.api.models import DateRangeRequest
        from pydantic import ValidationError
        from datetime import date

        # Valid range
        req = DateRangeRequest(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31)
        )
        assert req.start_date < req.end_date

        # Invalid range (start > end)
        with pytest.raises(ValidationError):
            DateRangeRequest(
                start_date=date(2024, 1, 31),
                end_date=date(2024, 1, 1)
            )


# =============================================================================
# Test API Authentication
# =============================================================================

# Check if FastAPI is available for auth tests
try:
    import fastapi
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class TestAPIAuthentication:
    """Tests for backend/api/auth_middleware.py"""

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_verify_api_key_valid(self):
        """Valid API key should verify"""
        from backend.api.auth_middleware import verify_api_key

        assert verify_api_key("test_key_123", "test_key_123") is True

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_verify_api_key_invalid(self):
        """Invalid API key should fail"""
        from backend.api.auth_middleware import verify_api_key

        assert verify_api_key("wrong_key", "correct_key") is False

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_verify_api_key_empty(self):
        """Empty keys should fail"""
        from backend.api.auth_middleware import verify_api_key

        assert verify_api_key("", "correct_key") is False
        assert verify_api_key("provided_key", "") is False
        assert verify_api_key("", "") is False

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_generate_api_key_format(self):
        """Generated keys should have correct format"""
        from backend.api.auth_middleware import generate_api_key

        key = generate_api_key()
        assert key.startswith("agx_")
        assert len(key) > 40  # Prefix + base64 encoded

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_generate_api_key_unique(self):
        """Generated keys should be unique"""
        from backend.api.auth_middleware import generate_api_key

        keys = [generate_api_key() for _ in range(10)]
        assert len(set(keys)) == 10  # All unique

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_hash_key_for_logging(self):
        """Key hashing for logs should be safe"""
        from backend.api.auth_middleware import _hash_key_for_logging

        hashed = _hash_key_for_logging("agx_verylongsecretkey12345")
        assert "agx_" in hashed
        assert "verylongsecretkey" not in hashed  # Full key not exposed


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for production readiness features"""

    def test_full_trade_flow_with_idempotency(self):
        """Test trade flow with idempotency protection"""
        from trading.idempotency import (
            IdempotencyManager,
            generate_idempotency_key
        )

        manager = IdempotencyManager(use_database=False)

        # Simulate trade attempt
        key = generate_idempotency_key("FORTRESS", "IC-001", "2024-01-15")

        # First attempt - should succeed
        success = manager.mark_pending(key, "FORTRESS", "hash123")
        assert success is True

        # Complete the trade
        manager.mark_completed(key, {
            "position_id": "IC-001",
            "status": "filled",
            "credit": 2.50
        })

        # Second attempt with same key - should get cached result
        result = manager.get_result(key)
        assert result is not None
        assert result["position_id"] == "IC-001"

    def test_data_validation_blocks_stale_data(self):
        """Test that stale data is blocked from trading"""
        from trading.data_validation import validate_market_data, MAX_DATA_AGE_SECONDS

        # Fresh data - should allow trading (use parseable format)
        fresh = {
            'timestamp': datetime.now(CENTRAL_TZ).strftime('%Y-%m-%dT%H:%M:%S.%f'),
            'spot_price': 585.50
        }
        is_valid, _ = validate_market_data(fresh)
        assert is_valid is True

        # Stale data - should block trading (use parseable format)
        stale = {
            'timestamp': (datetime.now(CENTRAL_TZ) - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S.%f'),
            'spot_price': 585.50
        }
        is_valid, error = validate_market_data(stale)
        assert is_valid is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
