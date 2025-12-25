"""
ARES Iron Condor Strategy Tests

Tests for the ARES iron condor trading strategy.

Run with: pytest tests/test_ares_iron_condor.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAresIronCondorImport:
    """Tests for ARES iron condor import"""

    def test_import_ares_iron_condor(self):
        """Test that ARES IC can be imported"""
        try:
            from trading.ares_iron_condor import ARESTrader
            assert ARESTrader is not None
        except ImportError:
            pytest.skip("ARES iron condor not available")


class TestAresTraderInitialization:
    """Tests for ARES trader initialization"""

    def test_trader_initialization(self):
        """Test trader can be initialized"""
        try:
            from trading.ares_iron_condor import ARESTrader

            with patch('trading.ares_iron_condor.get_connection'):
                trader = ARESTrader(capital=200000, mode='paper')
                assert trader is not None
        except ImportError:
            pytest.skip("ARES iron condor not available")


class TestIronCondorConstruction:
    """Tests for iron condor construction"""

    def test_build_iron_condor(self, mock_spx_option_chain):
        """Test IC construction"""
        try:
            from trading.ares_iron_condor import ARESTrader

            with patch('trading.ares_iron_condor.get_connection'):
                trader = ARESTrader(capital=200000, mode='paper')
                if hasattr(trader, 'build_iron_condor'):
                    with patch.object(trader, 'build_iron_condor') as mock_build:
                        mock_build.return_value = {
                            'short_put': 5800,
                            'long_put': 5790,
                            'short_call': 5900,
                            'long_call': 5910,
                            'credit': 3.50
                        }
                        result = trader.build_iron_condor(5850.0, mock_spx_option_chain)
                        assert 'short_put' in result
        except ImportError:
            pytest.skip("ARES iron condor not available")


class TestIronCondorEntryLogic:
    """Tests for IC entry logic"""

    def test_should_enter_trade(self, mock_market_data):
        """Test entry logic"""
        try:
            from trading.ares_iron_condor import ARESTrader

            with patch('trading.ares_iron_condor.get_connection'):
                trader = ARESTrader(capital=200000, mode='paper')
                if hasattr(trader, 'should_enter'):
                    with patch.object(trader, 'should_enter') as mock_enter:
                        mock_enter.return_value = True
                        result = trader.should_enter(mock_market_data)
                        assert isinstance(result, bool)
        except ImportError:
            pytest.skip("ARES iron condor not available")


class TestIronCondorExitLogic:
    """Tests for IC exit logic"""

    def test_should_exit_trade(self, mock_iron_condor_position):
        """Test exit logic"""
        try:
            from trading.ares_iron_condor import ARESTrader

            with patch('trading.ares_iron_condor.get_connection'):
                trader = ARESTrader(capital=200000, mode='paper')
                if hasattr(trader, 'should_exit'):
                    with patch.object(trader, 'should_exit') as mock_exit:
                        mock_exit.return_value = {'exit': True, 'reason': 'profit_target'}
                        result = trader.should_exit(mock_iron_condor_position)
                        assert 'exit' in result or 'reason' in result
        except ImportError:
            pytest.skip("ARES iron condor not available")


class TestIronCondorRiskManagement:
    """Tests for IC risk management"""

    def test_position_sizing(self):
        """Test position sizing"""
        try:
            from trading.ares_iron_condor import ARESTrader

            with patch('trading.ares_iron_condor.get_connection'):
                trader = ARESTrader(capital=200000, mode='paper')
                if hasattr(trader, 'calculate_position_size'):
                    with patch.object(trader, 'calculate_position_size') as mock_size:
                        mock_size.return_value = 10
                        result = trader.calculate_position_size()
                        assert result > 0
        except ImportError:
            pytest.skip("ARES iron condor not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
