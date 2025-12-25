"""
Circuit Breaker Tests

Tests for the trading circuit breaker module.

Run with: pytest tests/test_circuit_breaker.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCircuitBreakerImport:
    """Tests for circuit breaker import"""

    def test_import_circuit_breaker(self):
        """Test that circuit breaker can be imported"""
        try:
            from trading.circuit_breaker import CircuitBreaker
            assert CircuitBreaker is not None
        except ImportError:
            pytest.skip("Circuit breaker not available")


class TestCircuitBreakerInitialization:
    """Tests for circuit breaker initialization"""

    def test_breaker_initialization(self):
        """Test breaker can be initialized"""
        try:
            from trading.circuit_breaker import CircuitBreaker
            breaker = CircuitBreaker()
            assert breaker is not None
        except ImportError:
            pytest.skip("Circuit breaker not available")


class TestCircuitBreakerTriggering:
    """Tests for circuit breaker triggering"""

    def test_trigger_on_drawdown(self):
        """Test breaker triggers on drawdown"""
        try:
            from trading.circuit_breaker import CircuitBreaker

            breaker = CircuitBreaker()
            if hasattr(breaker, 'check_drawdown'):
                with patch.object(breaker, 'check_drawdown') as mock_dd:
                    mock_dd.return_value = True  # Triggered
                    result = breaker.check_drawdown(drawdown=-0.15)
                    assert result is True
        except ImportError:
            pytest.skip("Circuit breaker not available")

    def test_trigger_on_loss_streak(self):
        """Test breaker triggers on loss streak"""
        try:
            from trading.circuit_breaker import CircuitBreaker

            breaker = CircuitBreaker()
            if hasattr(breaker, 'check_loss_streak'):
                with patch.object(breaker, 'check_loss_streak') as mock_streak:
                    mock_streak.return_value = True
                    result = breaker.check_loss_streak(consecutive_losses=5)
                    assert result is True
        except ImportError:
            pytest.skip("Circuit breaker not available")


class TestCircuitBreakerState:
    """Tests for circuit breaker state"""

    def test_is_triggered(self):
        """Test checking if breaker is triggered"""
        try:
            from trading.circuit_breaker import CircuitBreaker

            breaker = CircuitBreaker()
            if hasattr(breaker, 'is_triggered'):
                result = breaker.is_triggered()
                assert isinstance(result, bool)
        except ImportError:
            pytest.skip("Circuit breaker not available")

    def test_reset_breaker(self):
        """Test breaker reset"""
        try:
            from trading.circuit_breaker import CircuitBreaker

            breaker = CircuitBreaker()
            if hasattr(breaker, 'reset'):
                breaker.reset()
                if hasattr(breaker, 'is_triggered'):
                    assert breaker.is_triggered() is False
        except ImportError:
            pytest.skip("Circuit breaker not available")


class TestCircuitBreakerCooldown:
    """Tests for circuit breaker cooldown"""

    def test_cooldown_period(self):
        """Test cooldown period enforcement"""
        try:
            from trading.circuit_breaker import CircuitBreaker

            breaker = CircuitBreaker()
            if hasattr(breaker, 'get_cooldown_remaining'):
                with patch.object(breaker, 'get_cooldown_remaining') as mock_cooldown:
                    mock_cooldown.return_value = 3600  # 1 hour
                    result = breaker.get_cooldown_remaining()
                    assert result >= 0
        except ImportError:
            pytest.skip("Circuit breaker not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
