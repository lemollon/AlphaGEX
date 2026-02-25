"""
Tests for Feature 4: Config Persistence.
"""

from unittest.mock import MagicMock, patch


class TestConfigApply:
    """Test that DB config overrides are applied at trader init."""

    def test_default_config_unchanged(self, mock_config, mock_db):
        """When no DB config, factory defaults remain unchanged."""
        from trading.trader import Trader

        mock_db.load_config.return_value = None

        with patch('trading.trader.SignalGenerator'), \
             patch('trading.trader.TradingDatabase', return_value=mock_db):
            trader = Trader(mock_config)

        assert trader.config.sd_multiplier == 1.2
        assert trader.config.profit_target_pct == 30.0
        assert trader.config.max_contracts == 10

    def test_db_overrides_applied(self, mock_config, mock_db):
        """DB config overrides should be applied to the BotConfig."""
        from trading.trader import Trader

        mock_db.load_config.return_value = {
            'sd_multiplier': 1.5,
            'profit_target_pct': 40.0,
            'max_contracts': 5,
        }

        with patch('trading.trader.SignalGenerator'), \
             patch('trading.trader.TradingDatabase', return_value=mock_db):
            trader = Trader(mock_config)

        assert trader.config.sd_multiplier == 1.5
        assert trader.config.profit_target_pct == 40.0
        assert trader.config.max_contracts == 5
        # Unchanged fields stay default
        assert trader.config.spread_width == 5.0

    def test_partial_overrides(self, mock_config, mock_db):
        """Only overridden fields change, rest stay at factory defaults."""
        from trading.trader import Trader

        mock_db.load_config.return_value = {
            'vix_skip': 28.0,
        }

        with patch('trading.trader.SignalGenerator'), \
             patch('trading.trader.TradingDatabase', return_value=mock_db):
            trader = Trader(mock_config)

        assert trader.config.vix_skip == 28.0
        assert trader.config.sd_multiplier == 1.2  # unchanged


class TestConfigValidation:
    """Test BotConfig.validate() for sanity checks."""

    def test_valid_config(self, mock_config):
        """Default config should pass validation."""
        valid, msg = mock_config.validate()
        assert valid is True

    def test_invalid_starting_capital(self, mock_config):
        """Zero starting capital should fail validation."""
        mock_config.starting_capital = 0
        valid, msg = mock_config.validate()
        assert valid is False

    def test_invalid_spread_width(self, mock_config):
        """Negative spread width should fail validation."""
        mock_config.spread_width = -1
        valid, msg = mock_config.validate()
        assert valid is False

    def test_invalid_profit_target(self, mock_config):
        """Profit target of 100% should fail validation."""
        mock_config.profit_target_pct = 100.0
        valid, msg = mock_config.validate()
        assert valid is False
