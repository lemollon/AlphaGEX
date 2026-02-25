"""
Tests for Feature 2: Force-Close (P&L calculation + account update).
"""

from unittest.mock import MagicMock, call


class TestForceClose:
    """Test close_paper_position P&L math and side effects."""

    def test_winning_trade_pnl(self, mock_config, mock_db, mock_position):
        """Winning trade: credit 0.45, close 0.15 → P&L = (0.45-0.15)*100*2 = $60."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        success, pnl = executor.close_paper_position(mock_position, 0.15, "profit_target")

        assert success is True
        assert pnl == 60.0  # (0.45 - 0.15) * 100 * 2

    def test_losing_trade_pnl(self, mock_config, mock_db, mock_position):
        """Losing trade: credit 0.45, close 0.90 → P&L = (0.45-0.90)*100*2 = -$90."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        success, pnl = executor.close_paper_position(mock_position, 0.90, "stop_loss")

        assert success is True
        assert pnl == -90.0  # (0.45 - 0.90) * 100 * 2

    def test_full_credit_kept_on_expiration(self, mock_config, mock_db, mock_position):
        """Expired worthless: close at 0 → full credit kept as profit."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        success, pnl = executor.close_paper_position(mock_position, 0.0, "EXPIRED")

        assert success is True
        assert pnl == 90.0  # 0.45 * 100 * 2

    def test_collateral_refund_on_close(self, mock_config, mock_db, mock_position):
        """Closing should refund collateral (negative collateral_change)."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        executor.close_paper_position(mock_position, 0.15, "profit_target")

        # Check update_paper_balance was called with negative collateral
        balance_call = mock_db.update_paper_balance.call_args
        assert balance_call.kwargs['collateral_change'] == -910.0
        assert balance_call.kwargs['realized_pnl'] == 60.0

    def test_equity_snapshot_saved(self, mock_config, mock_db, mock_position):
        """Closing should save an equity snapshot."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        executor.close_paper_position(mock_position, 0.15, "profit_target")

        mock_db.save_equity_snapshot.assert_called_once()

    def test_pdt_close_updated(self, mock_config, mock_db, mock_position):
        """Closing should update the PDT log."""
        from trading.executor import PaperExecutor

        executor = PaperExecutor(mock_config, mock_db)
        executor.close_paper_position(mock_position, 0.15, "profit_target")

        mock_db.update_pdt_close.assert_called_once()
        pdt_call = mock_db.update_pdt_close.call_args
        assert pdt_call.kwargs['position_id'] == "FLAME-20260225-ABC123"
        assert pdt_call.kwargs['pnl'] == 60.0

    def test_close_fails_gracefully(self, mock_config, mock_db, mock_position):
        """If DB close fails, return (False, 0)."""
        from trading.executor import PaperExecutor

        mock_db.close_position.return_value = False
        executor = PaperExecutor(mock_config, mock_db)
        success, pnl = executor.close_paper_position(mock_position, 0.15, "profit_target")

        assert success is False
        assert pnl == 0
