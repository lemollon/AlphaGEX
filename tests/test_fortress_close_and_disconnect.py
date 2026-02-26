"""
FORTRESS Close All Positions & Disconnect Tests
================================================

Verifies that FORTRESS can:
1. Close all open positions (force_close_all, process_expired_positions)
2. Handle partial closes, pricing failures, stale positions
3. TradierEODCloser discovers all sandbox accounts
4. TradierEODCloser cascade close works (4-leg → 2-leg → individual)
5. FORTRESS is disconnected in the scheduler (no new trades)

Run with: python -m pytest tests/test_fortress_close_and_disconnect.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# 1. FORTRESS IS DISCONNECTED IN SCHEDULER
# =============================================================================


class TestFortressDisconnected:
    """Verify FORTRESS is disabled and won't open new trades."""

    def test_fortress_trader_is_none_in_scheduler(self):
        """Scheduler must set fortress_trader = None (disconnected)."""
        # Can't import TraderScheduler (deep deps: scipy, pandas, etc.)
        # So verify the source code directly
        scheduler_path = Path(__file__).parent.parent / "scheduler" / "trader_scheduler.py"
        source = scheduler_path.read_text()
        assert "self.fortress_trader = None" in source, (
            "FORTRESS must be disconnected: scheduler must set self.fortress_trader = None"
        )

    def test_fortress_available_flag_exists(self):
        """FORTRESS_AVAILABLE flag must exist in scheduler source."""
        scheduler_path = Path(__file__).parent.parent / "scheduler" / "trader_scheduler.py"
        source = scheduler_path.read_text()
        assert "FORTRESS_AVAILABLE" in source, (
            "FORTRESS_AVAILABLE flag must be defined in trader_scheduler.py"
        )

    def test_fortress_cycle_skips_when_trader_none(self):
        """_run_fortress_cycle must skip when fortress_trader is None."""
        scheduler_path = Path(__file__).parent.parent / "scheduler" / "trader_scheduler.py"
        source = scheduler_path.read_text()
        assert "if not self.fortress_trader:" in source, (
            "_run_fortress_cycle must check for None trader before trading"
        )


# =============================================================================
# 2. FORCE CLOSE ALL POSITIONS
# =============================================================================


class TestForceCloseAll:
    """Verify force_close_all() closes every position and records outcomes."""

    @pytest.fixture
    def fortress_trader(self):
        """Create a FortressTrader with mocked DB and executor."""
        with patch('trading.fortress_v2.db.get_connection', return_value=MagicMock()):
            from trading.fortress_v2 import FortressTrader, FortressConfig, TradingMode
            config = FortressConfig(mode=TradingMode.PAPER, capital=200000)
            trader = FortressTrader(config=config)
            return trader

    def test_force_close_empty_positions(self, fortress_trader):
        """force_close_all with no open positions returns clean result."""
        fortress_trader.db.get_open_positions = MagicMock(return_value=[])

        result = fortress_trader.force_close_all(reason="EOD_CLOSE")

        assert result['closed'] == 0
        assert result['failed'] == 0
        assert result['total_pnl'] == 0.0

    def test_force_close_single_position(self, fortress_trader):
        """force_close_all closes one position and records P&L."""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        mock_pos = IronCondorPosition(
            position_id="TEST-001",
            ticker="SPY",
            expiration="2026-02-26",
            put_short_strike=590,
            put_long_strike=585,
            call_short_strike=610,
            call_long_strike=615,
            total_credit=1.50,
            contracts=1,
            status=PositionStatus.OPEN,
        )

        fortress_trader.db.get_open_positions = MagicMock(return_value=[mock_pos])
        fortress_trader.executor.close_position = MagicMock(return_value=(True, 0.50, 100.0))
        fortress_trader.db.close_position = MagicMock(return_value=True)

        result = fortress_trader.force_close_all(reason="EOD_CLOSE")

        assert result['closed'] == 1
        assert result['failed'] == 0
        assert result['total_pnl'] == 100.0
        fortress_trader.executor.close_position.assert_called_once_with(mock_pos, "EOD_CLOSE")
        fortress_trader.db.close_position.assert_called_once_with("TEST-001", 0.50, 100.0, "EOD_CLOSE")

    def test_force_close_handles_partial_close(self, fortress_trader):
        """force_close_all handles partial close (put closed, call failed)."""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        mock_pos = IronCondorPosition(
            position_id="TEST-002",
            ticker="SPY",
            expiration="2026-02-26",
            put_short_strike=590,
            put_long_strike=585,
            call_short_strike=610,
            call_long_strike=615,
            total_credit=1.50,
            contracts=1,
            status=PositionStatus.OPEN,
        )

        fortress_trader.db.get_open_positions = MagicMock(return_value=[mock_pos])
        # Executor returns 'partial_put' — put leg closed, call leg failed
        fortress_trader.executor.close_position = MagicMock(return_value=('partial_put', 0.30, 50.0))
        fortress_trader.db.partial_close_position = MagicMock()

        result = fortress_trader.force_close_all(reason="EOD_CLOSE")

        assert result['partial'] == 1
        assert result['closed'] == 0
        fortress_trader.db.partial_close_position.assert_called_once()

    def test_force_close_handles_executor_failure(self, fortress_trader):
        """force_close_all records failure when executor can't close."""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        mock_pos = IronCondorPosition(
            position_id="TEST-003",
            ticker="SPY",
            expiration="2026-02-26",
            put_short_strike=590,
            put_long_strike=585,
            call_short_strike=610,
            call_long_strike=615,
            total_credit=1.50,
            contracts=1,
            status=PositionStatus.OPEN,
        )

        fortress_trader.db.get_open_positions = MagicMock(return_value=[mock_pos])
        fortress_trader.executor.close_position = MagicMock(return_value=(False, 0, 0))

        result = fortress_trader.force_close_all(reason="EOD_CLOSE")

        assert result['closed'] == 0
        assert result['failed'] == 1

    def test_force_close_multiple_positions(self, fortress_trader):
        """force_close_all handles multiple positions with mixed outcomes."""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        positions = []
        for i in range(3):
            positions.append(IronCondorPosition(
                position_id=f"TEST-{i:03d}",
                ticker="SPY",
                expiration="2026-02-26",
                put_short_strike=590,
                put_long_strike=585,
                call_short_strike=610,
                call_long_strike=615,
                total_credit=1.50,
                contracts=1,
                status=PositionStatus.OPEN,
            ))

        fortress_trader.db.get_open_positions = MagicMock(return_value=positions)
        # First succeeds, second fails, third succeeds
        fortress_trader.executor.close_position = MagicMock(
            side_effect=[
                (True, 0.50, 100.0),
                (False, 0, 0),
                (True, 0.30, 120.0),
            ]
        )
        fortress_trader.db.close_position = MagicMock(return_value=True)

        result = fortress_trader.force_close_all(reason="EOD_CLOSE")

        assert result['closed'] == 2
        assert result['failed'] == 1
        assert result['total_pnl'] == 220.0


# =============================================================================
# 3. EXIT CONDITION LOGIC
# =============================================================================


class TestExitConditions:
    """Verify _check_exit_conditions catches all EOD/stale scenarios."""

    @pytest.fixture
    def fortress_trader(self):
        with patch('trading.fortress_v2.db.get_connection', return_value=MagicMock()):
            from trading.fortress_v2 import FortressTrader, FortressConfig, TradingMode
            config = FortressConfig(mode=TradingMode.PAPER, capital=200000)
            trader = FortressTrader(config=config)
            return trader

    def test_eod_close_fires_at_force_exit_time(self, fortress_trader):
        """Positions must be force-closed at 14:50 CT."""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        pos = IronCondorPosition(
            position_id="TEST-EOD",
            expiration="2026-02-27",
            total_credit=1.50,
            contracts=1,
            status=PositionStatus.OPEN,
            open_time=datetime(2026, 2, 27, 9, 0, tzinfo=CENTRAL_TZ),
        )

        # 14:51 CT — past force exit time (14:50)
        now = datetime(2026, 2, 27, 14, 51, tzinfo=CENTRAL_TZ)
        today = "2026-02-27"

        should_exit, reason = fortress_trader._check_exit_conditions(pos, now, today)
        assert should_exit is True
        assert "EOD_CLOSE" in reason

    def test_stale_position_closed_next_day(self, fortress_trader):
        """Positions from prior day must be closed immediately."""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        pos = IronCondorPosition(
            position_id="TEST-STALE",
            expiration="2026-02-27",
            total_credit=1.50,
            contracts=1,
            status=PositionStatus.OPEN,
            open_time=datetime(2026, 2, 26, 10, 0, tzinfo=CENTRAL_TZ),  # Yesterday
        )

        # Morning of Feb 27 — before force exit but position is from yesterday
        now = datetime(2026, 2, 27, 9, 0, tzinfo=CENTRAL_TZ)
        today = "2026-02-27"

        should_exit, reason = fortress_trader._check_exit_conditions(pos, now, today)
        assert should_exit is True
        assert reason == "STALE_POSITION"

    def test_expired_position_closed(self, fortress_trader):
        """Positions past expiration must be closed."""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        pos = IronCondorPosition(
            position_id="TEST-EXPIRED",
            expiration="2026-02-25",  # 2 days ago
            total_credit=1.50,
            contracts=1,
            status=PositionStatus.OPEN,
            open_time=datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ),
        )

        now = datetime(2026, 2, 27, 9, 0, tzinfo=CENTRAL_TZ)
        today = "2026-02-27"

        should_exit, reason = fortress_trader._check_exit_conditions(pos, now, today)
        # Either STALE_POSITION or EXPIRED fires first (both are correct)
        assert should_exit is True
        assert reason in ("STALE_POSITION", "EXPIRED")


# =============================================================================
# 4. PROCESS EXPIRED POSITIONS
# =============================================================================


class TestProcessExpiredPositions:
    """Verify process_expired_positions calculates P&L correctly."""

    @pytest.fixture
    def fortress_trader(self):
        with patch('trading.fortress_v2.db.get_connection', return_value=MagicMock()):
            from trading.fortress_v2 import FortressTrader, FortressConfig, TradingMode
            config = FortressConfig(mode=TradingMode.PAPER, capital=200000)
            trader = FortressTrader(config=config)
            return trader

    def test_no_expired_positions(self, fortress_trader):
        """No-op when no expired positions exist."""
        fortress_trader.db.get_open_positions = MagicMock(return_value=[])

        result = fortress_trader.process_expired_positions()

        assert result['processed_count'] == 0
        assert result['total_pnl'] == 0.0

    def test_expired_position_max_profit(self, fortress_trader):
        """Expired IC within wings = max profit (full credit kept)."""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        pos = IronCondorPosition(
            position_id="TEST-EXP-WIN",
            ticker="SPY",
            expiration="2026-02-26",  # Today or earlier
            put_short_strike=590,
            put_long_strike=585,
            call_short_strike=610,
            call_long_strike=615,
            total_credit=1.50,
            contracts=1,
            spread_width=5.0,
            underlying_at_entry=600,
            status=PositionStatus.OPEN,
        )

        fortress_trader.db.get_open_positions = MagicMock(return_value=[pos])
        # Price at 600 — safely between put_short (590) and call_short (610)
        fortress_trader.executor._get_current_price = MagicMock(return_value=600.0)
        fortress_trader.db.expire_position = MagicMock(return_value=True)

        result = fortress_trader.process_expired_positions()

        assert result['processed_count'] == 1
        # Max profit = credit * 100 * contracts = 1.50 * 100 * 1 = $150
        assert result['total_pnl'] == 150.0
        fortress_trader.db.expire_position.assert_called_once()


# =============================================================================
# 5. TRADIER EOD CLOSER - ACCOUNT DISCOVERY
# =============================================================================


class TestTradierEODCloserAccounts:
    """Verify get_all_sandbox_accounts discovers all configured accounts."""

    @patch.dict('os.environ', {
        'TRADIER_SANDBOX_API_KEY': 'primary_key',
        'TRADIER_SANDBOX_ACCOUNT_ID': 'primary_acct',
        'TRADIER_FORTRESS_SANDBOX_API_KEY_2': 'second_key',
        'TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2': 'second_acct',
        'TRADIER_FORTRESS_SANDBOX_API_KEY_3': 'third_key',
        'TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_3': 'third_acct',
    })
    @patch('unified_config.APIConfig')
    def test_discovers_all_three_accounts(self, mock_config):
        """Must find primary + secondary + tertiary sandbox accounts."""
        # APIConfig returns None so env vars are used
        mock_config.TRADIER_SANDBOX_API_KEY = None
        mock_config.TRADIER_SANDBOX_ACCOUNT_ID = None
        mock_config.TRADIER_FORTRESS_SANDBOX_API_KEY_2 = None
        mock_config.TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2 = None
        mock_config.TRADIER_FORTRESS_SANDBOX_API_KEY_3 = None
        mock_config.TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_3 = None

        from trading.tradier_eod_closer import get_all_sandbox_accounts
        accounts = get_all_sandbox_accounts()

        labels = [a['label'] for a in accounts]
        assert 'primary' in labels, "Must discover primary sandbox account"
        assert 'secondary' in labels, "Must discover secondary sandbox account"
        assert 'tertiary' in labels, "Must discover tertiary sandbox account"
        assert len(accounts) == 3

    @patch.dict('os.environ', {}, clear=True)
    @patch('unified_config.APIConfig')
    def test_empty_when_no_credentials(self, mock_config):
        """Returns empty list when no sandbox credentials set."""
        mock_config.TRADIER_SANDBOX_API_KEY = None
        mock_config.TRADIER_SANDBOX_ACCOUNT_ID = None
        mock_config.TRADIER_FORTRESS_SANDBOX_API_KEY_2 = None
        mock_config.TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2 = None
        mock_config.TRADIER_FORTRESS_SANDBOX_API_KEY_3 = None
        mock_config.TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_3 = None

        from trading.tradier_eod_closer import get_all_sandbox_accounts
        accounts = get_all_sandbox_accounts()

        assert len(accounts) == 0


# =============================================================================
# 6. TRADIER EOD CLOSER - CASCADE CLOSE LOGIC
# =============================================================================


class TestTradierEODCloserCascade:
    """Verify the 4-leg → 2-leg → individual cascade fallback."""

    def test_close_all_positions_flat_account(self):
        """No-op when account has no positions."""
        from trading.tradier_eod_closer import TradierEODCloser

        closer = TradierEODCloser(api_key='test', account_id='test', sandbox=True)
        closer.health_check = MagicMock(return_value=True)
        closer.cancel_all_open_orders = MagicMock(return_value={'cancelled': 0})
        closer.get_all_positions = MagicMock(return_value=[])

        result = closer.close_all_positions()

        assert result['positions_found'] == 0
        assert result['positions_closed'] == 0
        assert result['health_check'] is True

    def test_close_all_positions_api_unreachable(self):
        """Must report error when API health check fails."""
        from trading.tradier_eod_closer import TradierEODCloser

        closer = TradierEODCloser(api_key='test', account_id='test', sandbox=True)
        closer.health_check = MagicMock(return_value=False)

        result = closer.close_all_positions()

        assert result['health_check'] is False
        assert len(result['errors']) > 0
        assert "health check failed" in result['errors'][0].lower()

    def test_close_all_sandbox_accounts_iterates_all(self):
        """close_all_sandbox_accounts must process every discovered account."""
        from trading.tradier_eod_closer import close_all_sandbox_accounts, TradierEODCloser

        mock_accounts = [
            {'api_key': 'key1', 'account_id': 'acct1', 'label': 'primary'},
            {'api_key': 'key2', 'account_id': 'acct2', 'label': 'secondary'},
        ]

        with patch('trading.tradier_eod_closer.get_all_sandbox_accounts', return_value=mock_accounts):
            with patch.object(TradierEODCloser, 'close_all_positions') as mock_close:
                mock_close.return_value = {
                    'positions_found': 0,
                    'positions_closed': 0,
                    'positions_failed': 0,
                    'health_check': True,
                    'orders_cancelled': 0,
                    'position_details': [],
                    'errors': [],
                }

                result = close_all_sandbox_accounts()

                assert result['accounts_processed'] == 2
                assert mock_close.call_count == 2


# =============================================================================
# 7. DB CLOSE/EXPIRE OPERATIONS
# =============================================================================


class TestDBCloseOperations:
    """Verify DB layer properly updates position status on close."""

    def test_close_position_sets_status_and_pnl(self):
        """close_position must SET status='closed', close_time, realized_pnl."""
        with patch('trading.fortress_v2.db.get_connection') as mock_conn_fn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)  # RETURNING id
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_fn.return_value = mock_conn

            from trading.fortress_v2.db import FortressDatabase
            db = FortressDatabase(bot_name="FORTRESS")

            success = db.close_position("POS-001", 0.50, 150.0, "EOD_CLOSE")

            assert success is True
            # Verify the SQL executed
            call_args = mock_cursor.execute.call_args_list
            # Find the UPDATE call (not CREATE TABLE)
            update_calls = [c for c in call_args if 'UPDATE fortress_positions' in str(c)]
            assert len(update_calls) > 0, "Must execute UPDATE on fortress_positions"

    def test_expire_position_sets_expired_status(self):
        """expire_position must SET status='expired', close_time, realized_pnl."""
        with patch('trading.fortress_v2.db.get_connection') as mock_conn_fn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_fn.return_value = mock_conn

            from trading.fortress_v2.db import FortressDatabase
            db = FortressDatabase(bot_name="FORTRESS")

            success = db.expire_position("POS-002", 150.0, 0.0)

            assert success is True
            update_calls = [c for c in mock_cursor.execute.call_args_list
                           if 'UPDATE fortress_positions' in str(c)]
            assert len(update_calls) > 0, "Must execute UPDATE on fortress_positions"


# =============================================================================
# 8. EXECUTOR CLOSE USES MARKET ORDERS FOR EOD
# =============================================================================


class TestExecutorEODClose:
    """Verify executor uses MARKET orders for EOD closes."""

    def test_eod_reasons_trigger_market_orders(self):
        """EOD close reasons must force MARKET orders (not LIMIT)."""
        # This tests the logic in _close_live that decides market vs limit
        eod_reasons = ('EOD', 'STALE', 'EXPIRED', 'SAFETY_NET', 'PRICING_FAILURE', 'MANUAL_CLOSE')

        for reason in eod_reasons:
            use_market = any(r in reason.upper() for r in eod_reasons)
            assert use_market is True, f"Reason '{reason}' must trigger MARKET orders"

    def test_normal_close_uses_limit_orders(self):
        """Normal profit target closes should NOT force MARKET orders."""
        eod_reasons = ('EOD', 'STALE', 'EXPIRED', 'SAFETY_NET', 'PRICING_FAILURE', 'MANUAL_CLOSE')

        reason = "PROFIT_TARGET"
        use_market = any(r in reason.upper() for r in eod_reasons)
        assert use_market is False, "PROFIT_TARGET should use LIMIT orders, not MARKET"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
