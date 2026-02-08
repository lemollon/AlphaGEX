"""
Comprehensive Tests for Trader Scheduler

Tests the autonomous trading scheduler including:
- Scheduler initialization
- Market hours detection
- Bot scheduling logic (LAZARUS, CORNERSTONE, FORTRESS, SOLOMON)
- State persistence and recovery
- Heartbeat logging

Run with: pytest tests/test_trader_scheduler.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TestCapitalAllocation:
    """Tests for capital allocation configuration"""

    def test_capital_allocation_sums_to_total(self):
        """Test that capital allocation sums correctly"""
        from scheduler.trader_scheduler import CAPITAL_ALLOCATION

        total = (
            CAPITAL_ALLOCATION['LAZARUS'] +
            CAPITAL_ALLOCATION['CORNERSTONE'] +
            CAPITAL_ALLOCATION['FORTRESS'] +
            CAPITAL_ALLOCATION['RESERVE']
        )

        assert total == CAPITAL_ALLOCATION['TOTAL']
        assert CAPITAL_ALLOCATION['TOTAL'] == 1_000_000

    def test_capital_allocation_percentages(self):
        """Test capital allocation percentages"""
        from scheduler.trader_scheduler import CAPITAL_ALLOCATION

        total = CAPITAL_ALLOCATION['TOTAL']

        # LAZARUS should be 30%
        assert CAPITAL_ALLOCATION['LAZARUS'] == 300_000
        # CORNERSTONE should be 40%
        assert CAPITAL_ALLOCATION['CORNERSTONE'] == 400_000
        # FORTRESS should be 20%
        assert CAPITAL_ALLOCATION['FORTRESS'] == 200_000
        # RESERVE should be 10%
        assert CAPITAL_ALLOCATION['RESERVE'] == 100_000


class TestSchedulerInitialization:
    """Tests for scheduler initialization"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.ATLAS_AVAILABLE', False)
    @patch('scheduler.trader_scheduler.ARES_AVAILABLE', False)
    @patch('scheduler.trader_scheduler.SOLOMON_AVAILABLE', False)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_scheduler_init_minimal(self, mock_conn, mock_api, mock_trader):
        """Test scheduler initializes with minimal dependencies"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()
        mock_api.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        assert scheduler.trader is not None
        assert scheduler.is_running is False
        assert scheduler.execution_count == 0

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', False)
    def test_scheduler_handles_missing_apscheduler(self):
        """Test scheduler handles missing APScheduler gracefully"""
        from scheduler.trader_scheduler import AutonomousTraderScheduler

        # Should not raise even without APScheduler
        scheduler = AutonomousTraderScheduler()
        assert scheduler.scheduler is None
        assert scheduler.is_running is False


class TestMarketHoursDetection:
    """Tests for market hours detection"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_is_market_open_during_hours(self, mock_conn, mock_api, mock_trader):
        """Test market is detected as open during trading hours"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        # Mock time during market hours (10:00 AM CT on a Monday)
        with patch('scheduler.trader_scheduler.datetime') as mock_datetime:
            mock_now = datetime(2024, 12, 23, 10, 0, 0, tzinfo=CENTRAL_TZ)  # Monday
            mock_datetime.now.return_value = mock_now

            result = scheduler.is_market_open()
            assert result is True

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_is_market_closed_weekend(self, mock_conn, mock_api, mock_trader):
        """Test market is detected as closed on weekends"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        # Mock time on Saturday
        with patch('scheduler.trader_scheduler.datetime') as mock_datetime:
            mock_now = datetime(2024, 12, 21, 10, 0, 0, tzinfo=CENTRAL_TZ)  # Saturday
            mock_datetime.now.return_value = mock_now

            result = scheduler.is_market_open()
            assert result is False

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_is_market_closed_after_hours(self, mock_conn, mock_api, mock_trader):
        """Test market is detected as closed after hours"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        # Mock time after market close (4:00 PM CT)
        with patch('scheduler.trader_scheduler.datetime') as mock_datetime:
            mock_now = datetime(2024, 12, 23, 16, 0, 0, tzinfo=CENTRAL_TZ)  # Monday 4 PM
            mock_datetime.now.return_value = mock_now

            result = scheduler.is_market_open()
            assert result is False


class TestStatePersistence:
    """Tests for scheduler state persistence"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_save_state(self, mock_conn, mock_api, mock_trader):
        """Test saving scheduler state to database"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()
        scheduler.is_running = True
        scheduler.execution_count = 5

        scheduler._save_state()

        # Verify UPDATE was called
        mock_cursor.execute.assert_called()

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_load_state(self, mock_conn, mock_api, mock_trader):
        """Test loading scheduler state from database"""
        mock_cursor = MagicMock()
        # Return saved state
        mock_cursor.fetchone.return_value = (1, None, None, 10, 0, None)
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        # Execution count should be loaded from saved state
        assert scheduler.execution_count == 10

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_mark_auto_restart(self, mock_conn, mock_api, mock_trader):
        """Test marking scheduler for auto-restart"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        scheduler._mark_auto_restart("Test restart")

        # Verify UPDATE was called
        mock_cursor.execute.assert_called()


class TestPhoenixScheduling:
    """Tests for LAZARUS (0DTE) bot scheduling"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_phoenix_trade_logic_market_open(self, mock_conn, mock_api, mock_trader):
        """Test LAZARUS trading logic during market hours"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        mock_trader_instance = MagicMock()
        mock_trader_instance.find_and_execute_daily_trade.return_value = None
        mock_trader_instance.auto_manage_positions.return_value = []
        mock_trader.return_value = mock_trader_instance

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        # Mock market as open
        with patch.object(scheduler, 'is_market_open', return_value=True):
            with patch.object(scheduler, '_save_heartbeat'):
                with patch.object(scheduler, '_log_no_trade_decision'):
                    scheduler.scheduled_trade_logic()

        # Should have called trader methods
        mock_trader_instance.find_and_execute_daily_trade.assert_called_once()
        mock_trader_instance.auto_manage_positions.assert_called_once()

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_phoenix_trade_logic_market_closed(self, mock_conn, mock_api, mock_trader):
        """Test LAZARUS trading logic when market closed"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        # Mock market as closed
        with patch.object(scheduler, 'is_market_open', return_value=False):
            with patch.object(scheduler, '_save_heartbeat'):
                scheduler.scheduled_trade_logic()

        # Should NOT have called trading methods
        scheduler.trader.find_and_execute_daily_trade.assert_not_called()


class TestAtlasScheduling:
    """Tests for CORNERSTONE (SPX Wheel) bot scheduling"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.ATLAS_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.SPXWheelTrader')
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_atlas_initialization(self, mock_conn, mock_api, mock_trader, mock_wheel):
        """Test CORNERSTONE trader initialization"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()
        mock_wheel.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        assert scheduler.cornerstone_trader is not None

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.ATLAS_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.PROVERBS_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.get_proverbs')
    @patch('scheduler.trader_scheduler.SPXWheelTrader')
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_atlas_respects_kill_switch(self, mock_conn, mock_api, mock_trader, mock_wheel, mock_proverbs):
        """Test CORNERSTONE respects Proverbs kill switch"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        mock_atlas = MagicMock()
        mock_wheel.return_value = mock_atlas

        mock_proverbs_instance = MagicMock()
        mock_proverbs_instance.is_bot_killed.return_value = True  # Kill switch active
        mock_proverbs.return_value = mock_proverbs_instance

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        with patch.object(scheduler, 'is_market_open', return_value=True):
            with patch.object(scheduler, '_save_heartbeat'):
                scheduler.scheduled_atlas_logic()

        # Should NOT have run daily cycle due to kill switch
        mock_atlas.run_daily_cycle.assert_not_called()


class TestAresScheduling:
    """Tests for FORTRESS (Iron Condor) bot scheduling"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.ARES_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.FortressTrader')
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_ares_initialization(self, mock_conn, mock_api, mock_trader, mock_ares):
        """Test FORTRESS trader initialization"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()
        mock_ares.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        assert scheduler.fortress_trader is not None


class TestAthenaScheduling:
    """Tests for SOLOMON (Directional Spreads) bot scheduling"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.SOLOMON_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.SolomonTrader')
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_solomon_initialization(self, mock_conn, mock_api, mock_trader, mock_solomon):
        """Test SOLOMON trader initialization"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()
        mock_solomon.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        assert scheduler.solomon_trader is not None


class TestHeartbeatLogging:
    """Tests for heartbeat logging"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_save_heartbeat(self, mock_conn, mock_api, mock_trader):
        """Test heartbeat saving"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        if hasattr(scheduler, '_save_heartbeat'):
            scheduler._save_heartbeat('LAZARUS', 'SCAN_COMPLETE', {'test': True})
            # Should not raise


class TestErrorHandling:
    """Tests for error handling"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_trade_logic_handles_exception(self, mock_conn, mock_api, mock_trader):
        """Test that trade logic handles exceptions gracefully"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        mock_trader_instance = MagicMock()
        mock_trader_instance.find_and_execute_daily_trade.side_effect = Exception("Test error")
        mock_trader.return_value = mock_trader_instance

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        with patch.object(scheduler, 'is_market_open', return_value=True):
            with patch.object(scheduler, '_save_heartbeat'):
                # Should not raise - should handle gracefully
                scheduler.scheduled_trade_logic()

        # Error should be captured
        assert scheduler.last_error is not None
        assert 'Test error' in str(scheduler.last_error.get('error', ''))


class TestSchedulerStartStop:
    """Tests for scheduler start/stop"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.BackgroundScheduler')
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_start_scheduler(self, mock_conn, mock_api, mock_trader, mock_bg_scheduler):
        """Test starting the scheduler"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        mock_scheduler = MagicMock()
        mock_bg_scheduler.return_value = mock_scheduler

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()

        if hasattr(scheduler, 'start'):
            scheduler.start()
            assert scheduler.is_running is True

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.BackgroundScheduler')
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_stop_scheduler(self, mock_conn, mock_api, mock_trader, mock_bg_scheduler):
        """Test stopping the scheduler"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_trader.return_value = MagicMock()

        mock_scheduler = MagicMock()
        mock_bg_scheduler.return_value = mock_scheduler

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()
        scheduler.is_running = True

        if hasattr(scheduler, 'stop'):
            scheduler.stop()
            assert scheduler.is_running is False


class TestExecutionTracking:
    """Tests for execution count tracking"""

    @patch('scheduler.trader_scheduler.APSCHEDULER_AVAILABLE', True)
    @patch('scheduler.trader_scheduler.AutonomousPaperTrader')
    @patch('scheduler.trader_scheduler.TradingVolatilityAPI')
    @patch('scheduler.trader_scheduler.get_connection')
    def test_execution_count_increments(self, mock_conn, mock_api, mock_trader):
        """Test that execution count increments after trade logic"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        mock_trader_instance = MagicMock()
        mock_trader_instance.find_and_execute_daily_trade.return_value = None
        mock_trader_instance.auto_manage_positions.return_value = []
        mock_trader.return_value = mock_trader_instance

        from scheduler.trader_scheduler import AutonomousTraderScheduler
        scheduler = AutonomousTraderScheduler()
        initial_count = scheduler.execution_count

        with patch.object(scheduler, 'is_market_open', return_value=True):
            with patch.object(scheduler, '_save_heartbeat'):
                with patch.object(scheduler, '_log_no_trade_decision'):
                    with patch.object(scheduler, '_save_state'):
                        scheduler.scheduled_trade_logic()

        assert scheduler.execution_count == initial_count + 1
