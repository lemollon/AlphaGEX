"""
Tests for Feature 1: Bot Toggle (db persistence + trader cycle gating).
"""

from unittest.mock import MagicMock, patch


class TestTogglePersistence:
    """Test that toggle persists to DB and is read back each cycle."""

    def test_toggle_enable_persists(self, mock_config, mock_db):
        """toggle(True) should set is_active and call db.set_bot_active."""
        from trading.trader import Trader

        with patch('trading.trader.SignalGenerator'), \
             patch('trading.trader.TradingDatabase', return_value=mock_db):
            trader = Trader(mock_config)
            result = trader.toggle(True)

        assert result['is_active'] is True
        assert trader.is_active is True
        mock_db.set_bot_active.assert_called_once_with(True)

    def test_toggle_disable_persists(self, mock_config, mock_db):
        """toggle(False) should disable and persist."""
        from trading.trader import Trader

        with patch('trading.trader.SignalGenerator'), \
             patch('trading.trader.TradingDatabase', return_value=mock_db):
            trader = Trader(mock_config)
            result = trader.toggle(False)

        assert result['is_active'] is False
        assert trader.is_active is False
        mock_db.set_bot_active.assert_called_once_with(False)

    def test_toggle_logs_config_event(self, mock_config, mock_db):
        """Toggle should log a CONFIG event."""
        from trading.trader import Trader

        with patch('trading.trader.SignalGenerator'), \
             patch('trading.trader.TradingDatabase', return_value=mock_db):
            trader = Trader(mock_config)
            trader.toggle(False)

        # Find the CONFIG log call
        config_calls = [
            c for c in mock_db.log.call_args_list
            if c.args[0] == "CONFIG"
        ]
        assert len(config_calls) >= 1
        assert "disabled" in config_calls[-1].args[1].lower()

    def test_cycle_reads_db_state(self, mock_config, mock_db):
        """_run_cycle_inner should read is_active from DB."""
        from trading.trader import Trader

        mock_db.get_bot_active.return_value = False
        mock_db.get_open_positions.return_value = []

        with patch('trading.trader.SignalGenerator'), \
             patch('trading.trader.TradingDatabase', return_value=mock_db):
            trader = Trader(mock_config)
            # Initially active
            trader.is_active = True
            result = trader.run_cycle()

        # Should have read inactive from DB (trader uses 'inactive' as action string)
        assert result['action'] == 'inactive'
        mock_db.get_bot_active.assert_called()
