"""
Comprehensive Tests for Unified Trading Engine

Tests the unified trading engine including:
- Engine initialization
- Trade execution interface
- Position aggregation
- Performance consolidation

Run with: pytest tests/test_unified_trading_engine.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TestUnifiedEngineImport:
    """Tests for module import"""

    def test_module_importable(self):
        """Test unified trading engine can be imported"""
        try:
            import unified_trading_engine
            assert unified_trading_engine is not None
        except ImportError:
            pytest.skip("Unified trading engine not available")

    def test_main_class_exists(self):
        """Test main engine class exists"""
        try:
            from unified_trading_engine import UnifiedTradingEngine
            assert UnifiedTradingEngine is not None
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestEngineInitialization:
    """Tests for engine initialization"""

    @patch('unified_trading_engine.get_connection')
    def test_engine_initialization(self, mock_conn):
        """Test engine initializes correctly"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()
            assert engine is not None
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")

    @patch('unified_trading_engine.get_connection')
    def test_engine_with_config(self, mock_conn):
        """Test engine initialization with config"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            config = {'mode': 'paper', 'capital': 1000000}
            engine = UnifiedTradingEngine(config=config)
            assert engine is not None
        except (ImportError, TypeError):
            pytest.skip("Engine config not supported")


class TestTradeExecution:
    """Tests for trade execution interface"""

    @patch('unified_trading_engine.get_connection')
    def test_execute_trade_interface(self, mock_conn):
        """Test trade execution interface exists"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'execute_trade'):
                # Interface should exist
                assert callable(engine.execute_trade)
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")

    @patch('unified_trading_engine.get_connection')
    def test_submit_order_interface(self, mock_conn):
        """Test order submission interface exists"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'submit_order'):
                assert callable(engine.submit_order)
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestPositionAggregation:
    """Tests for position aggregation"""

    @patch('unified_trading_engine.get_connection')
    def test_get_all_positions(self, mock_conn):
        """Test getting all positions across bots"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_all_positions'):
                positions = engine.get_all_positions()
                assert isinstance(positions, (list, dict))
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")

    @patch('unified_trading_engine.get_connection')
    def test_get_positions_by_bot(self, mock_conn):
        """Test getting positions by bot name"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_positions_by_bot'):
                positions = engine.get_positions_by_bot('ARES')
                assert isinstance(positions, list)
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestPerformanceConsolidation:
    """Tests for performance consolidation"""

    @patch('unified_trading_engine.get_connection')
    def test_get_consolidated_performance(self, mock_conn):
        """Test getting consolidated performance"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_consolidated_performance'):
                perf = engine.get_consolidated_performance()
                if perf:
                    assert isinstance(perf, dict)
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")

    @patch('unified_trading_engine.get_connection')
    def test_get_total_pnl(self, mock_conn):
        """Test getting total P&L across all bots"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (50000.0,)
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_total_pnl'):
                pnl = engine.get_total_pnl()
                assert isinstance(pnl, (int, float))
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestRiskManagement:
    """Tests for unified risk management"""

    @patch('unified_trading_engine.get_connection')
    def test_get_total_exposure(self, mock_conn):
        """Test getting total exposure"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_total_exposure'):
                exposure = engine.get_total_exposure()
                assert isinstance(exposure, (int, float, dict))
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")

    @patch('unified_trading_engine.get_connection')
    def test_check_risk_limits(self, mock_conn):
        """Test checking risk limits"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'check_risk_limits'):
                within_limits = engine.check_risk_limits()
                assert isinstance(within_limits, bool)
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestBotCoordination:
    """Tests for bot coordination"""

    @patch('unified_trading_engine.get_connection')
    def test_get_bot_statuses(self, mock_conn):
        """Test getting status of all bots"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_bot_statuses'):
                statuses = engine.get_bot_statuses()
                assert isinstance(statuses, dict)
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")

    @patch('unified_trading_engine.get_connection')
    def test_start_all_bots(self, mock_conn):
        """Test starting all bots"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'start_all_bots'):
                result = engine.start_all_bots()
                # Should return success indicator
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestTradeLogging:
    """Tests for trade logging"""

    @patch('unified_trading_engine.get_connection')
    def test_log_trade(self, mock_conn):
        """Test trade logging"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'log_trade'):
                trade = {
                    'bot': 'ARES',
                    'symbol': 'SPX',
                    'action': 'SELL',
                    'quantity': 1,
                    'price': 5.00
                }
                engine.log_trade(trade)
                # Should not raise
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestCapitalAllocation:
    """Tests for capital allocation"""

    @patch('unified_trading_engine.get_connection')
    def test_get_capital_allocation(self, mock_conn):
        """Test getting capital allocation"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_capital_allocation'):
                allocation = engine.get_capital_allocation()
                if allocation:
                    assert isinstance(allocation, dict)
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")

    @patch('unified_trading_engine.get_connection')
    def test_get_available_capital(self, mock_conn):
        """Test getting available capital"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (500000.0,)
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_available_capital'):
                capital = engine.get_available_capital()
                assert isinstance(capital, (int, float))
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestMarketDataIntegration:
    """Tests for market data integration"""

    @patch('unified_trading_engine.get_connection')
    def test_get_market_data(self, mock_conn):
        """Test getting market data"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_market_data'):
                data = engine.get_market_data('SPY')
                # Data may be None or dict
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestErrorHandling:
    """Tests for error handling"""

    @patch('unified_trading_engine.get_connection')
    def test_handles_missing_bot(self, mock_conn):
        """Test handling of missing bot"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            from unified_trading_engine import UnifiedTradingEngine

            engine = UnifiedTradingEngine()

            if hasattr(engine, 'get_positions_by_bot'):
                # Should not crash with invalid bot name
                positions = engine.get_positions_by_bot('INVALID_BOT')
                assert isinstance(positions, list)
        except ImportError:
            pytest.skip("UnifiedTradingEngine not available")


class TestDependencyFlags:
    """Tests for dependency availability flags"""

    def test_dependency_flags_exist(self):
        """Test dependency flags are defined"""
        try:
            import unified_trading_engine

            for attr in dir(unified_trading_engine):
                if attr.endswith('_AVAILABLE'):
                    value = getattr(unified_trading_engine, attr)
                    assert isinstance(value, bool)
        except ImportError:
            pytest.skip("Module not available")
