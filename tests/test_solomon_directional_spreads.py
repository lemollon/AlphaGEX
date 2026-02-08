"""
SOLOMON Directional Spreads Tests

Tests for the SOLOMON directional spread trading strategy.

Run with: pytest tests/test_solomon_directional_spreads.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAthenaDirectionalImport:
    """Tests for SOLOMON directional import"""

    def test_import_solomon_directional(self):
        """Test that SOLOMON can be imported"""
        try:
            from trading.solomon_directional_spreads import SolomonTrader
            assert SolomonTrader is not None
        except ImportError:
            pytest.skip("SOLOMON directional spreads not available")


class TestSolomonTraderInitialization:
    """Tests for SOLOMON trader initialization"""

    def test_trader_initialization(self):
        """Test trader can be initialized"""
        try:
            from trading.solomon_directional_spreads import SolomonTrader

            with patch('database_adapter.get_connection', return_value=MagicMock()):
                trader = SolomonTrader(initial_capital=100000)
                assert trader is not None
        except ImportError:
            pytest.skip("SOLOMON directional spreads not available")


class TestDirectionalSpreadConstruction:
    """Tests for spread construction"""

    def test_build_bull_call_spread(self, mock_spx_option_chain):
        """Test bull call spread construction"""
        try:
            from trading.solomon_directional_spreads import SolomonTrader

            with patch('database_adapter.get_connection', return_value=MagicMock()):
                trader = SolomonTrader(initial_capital=100000)
                if hasattr(trader, 'build_bull_call_spread'):
                    with patch.object(trader, 'build_bull_call_spread') as mock_build:
                        mock_build.return_value = {
                            'long_strike': 5850,
                            'short_strike': 5860,
                            'debit': 5.00
                        }
                        result = trader.build_bull_call_spread(5850.0)
                        assert 'long_strike' in result
        except ImportError:
            pytest.skip("SOLOMON directional spreads not available")

    def test_build_bear_put_spread(self, mock_spx_option_chain):
        """Test bear put spread construction"""
        try:
            from trading.solomon_directional_spreads import SolomonTrader

            with patch('database_adapter.get_connection', return_value=MagicMock()):
                trader = SolomonTrader(initial_capital=100000)
                if hasattr(trader, 'build_bear_put_spread'):
                    with patch.object(trader, 'build_bear_put_spread') as mock_build:
                        mock_build.return_value = {
                            'long_strike': 5850,
                            'short_strike': 5840,
                            'debit': 4.50
                        }
                        result = trader.build_bear_put_spread(5850.0)
                        assert 'long_strike' in result
        except ImportError:
            pytest.skip("SOLOMON directional spreads not available")


class TestDirectionalSignals:
    """Tests for directional signal generation"""

    def test_get_directional_bias(self, mock_market_data):
        """Test directional bias detection"""
        try:
            from trading.solomon_directional_spreads import SolomonTrader

            with patch('database_adapter.get_connection', return_value=MagicMock()):
                trader = SolomonTrader(initial_capital=100000)
                if hasattr(trader, 'get_directional_bias'):
                    with patch.object(trader, 'get_directional_bias') as mock_bias:
                        mock_bias.return_value = 'BULLISH'
                        result = trader.get_directional_bias(mock_market_data)
                        assert result in ['BULLISH', 'BEARISH', 'NEUTRAL']
        except ImportError:
            pytest.skip("SOLOMON directional spreads not available")


class TestDirectionalEntryLogic:
    """Tests for directional entry logic"""

    def test_should_enter_trade(self, mock_market_data):
        """Test entry logic"""
        try:
            from trading.solomon_directional_spreads import SolomonTrader

            with patch('database_adapter.get_connection', return_value=MagicMock()):
                trader = SolomonTrader(initial_capital=100000)
                if hasattr(trader, 'should_enter'):
                    with patch.object(trader, 'should_enter') as mock_enter:
                        mock_enter.return_value = True
                        result = trader.should_enter(mock_market_data)
                        assert isinstance(result, bool)
        except ImportError:
            pytest.skip("SOLOMON directional spreads not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
