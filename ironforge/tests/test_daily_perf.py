"""
Tests for Feature 3: Daily Performance Population.
"""

from unittest.mock import MagicMock, call, ANY


class TestDailyPerfOnOpen:
    """Test that opening a position updates daily_perf."""

    def test_open_calls_daily_perf(self, mock_config, mock_db, mock_signal):
        """open_paper_position should call update_daily_performance with trades_executed=1."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        position = executor.open_paper_position(mock_signal, 2)

        assert position is not None
        # Find the daily perf call
        daily_calls = [
            c for c in mock_db.update_daily_performance.call_args_list
        ]
        assert len(daily_calls) == 1
        summary = daily_calls[0].args[0]
        assert summary.trades_executed == 1
        assert summary.positions_closed == 0
        assert summary.realized_pnl == 0


class TestDailyPerfOnClose:
    """Test that closing a position updates daily_perf."""

    def test_close_calls_daily_perf(self, mock_config, mock_db, mock_position):
        """close_paper_position should call update_daily_performance with positions_closed=1."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        success, pnl = executor.close_paper_position(mock_position, 0.15, "profit_target")

        assert success is True
        daily_calls = [
            c for c in mock_db.update_daily_performance.call_args_list
        ]
        assert len(daily_calls) == 1
        summary = daily_calls[0].args[0]
        assert summary.positions_closed == 1
        assert summary.trades_executed == 0
        assert summary.realized_pnl == 60.0  # (0.45 - 0.15) * 100 * 2

    def test_close_losing_trade_updates_perf(self, mock_config, mock_db, mock_position):
        """Losing trade P&L should flow through to daily_perf."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        executor.close_paper_position(mock_position, 0.90, "stop_loss")

        daily_calls = mock_db.update_daily_performance.call_args_list
        summary = daily_calls[0].args[0]
        assert summary.realized_pnl == -90.0
