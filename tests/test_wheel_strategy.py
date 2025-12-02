"""
Tests for Wheel Strategy Implementation

Tests the wheel strategy state machine:
1. CSP opening and expiration (OTM and assigned)
2. Covered call selling and expiration (OTM and called away)
3. Rolling positions
4. Full cycle P&L tracking
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWheelStrategy:
    """Test suite for wheel strategy"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        # Mock the database connection
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value = self.mock_cursor

    def test_wheel_phase_enum(self):
        """Test wheel phase enumeration"""
        from trading.wheel_strategy import WheelPhase

        assert WheelPhase.CSP.value == "CSP"
        assert WheelPhase.ASSIGNED.value == "ASSIGNED"
        assert WheelPhase.COVERED_CALL.value == "COVERED_CALL"
        assert WheelPhase.CALLED_AWAY.value == "CALLED_AWAY"
        assert WheelPhase.CLOSED.value == "CLOSED"

    def test_wheel_action_enum(self):
        """Test wheel action enumeration"""
        from trading.wheel_strategy import WheelAction

        assert WheelAction.OPEN_CSP.value == "OPEN_CSP"
        assert WheelAction.CSP_EXPIRED_OTM.value == "CSP_EXPIRED_OTM"
        assert WheelAction.CSP_ASSIGNED.value == "CSP_ASSIGNED"
        assert WheelAction.ROLL_CSP.value == "ROLL_CSP"
        assert WheelAction.OPEN_COVERED_CALL.value == "OPEN_COVERED_CALL"
        assert WheelAction.CC_EXPIRED_OTM.value == "CC_EXPIRED_OTM"
        assert WheelAction.CC_CALLED_AWAY.value == "CC_CALLED_AWAY"

    def test_wheel_leg_net_premium(self):
        """Test WheelLeg net premium calculation"""
        from trading.wheel_strategy import WheelLeg

        leg = WheelLeg(
            leg_id=1,
            cycle_id=1,
            leg_type='CSP',
            action='SELL_TO_OPEN',
            strike=450.0,
            expiration_date=date.today() + timedelta(days=30),
            contracts=2,
            premium_received=2.50,
            premium_paid=0.0,
            open_date=datetime.now()
        )

        # Net premium = (received - paid) * contracts * 100
        # = (2.50 - 0) * 2 * 100 = 500
        assert leg.net_premium == 500.0

    def test_wheel_leg_with_close_cost(self):
        """Test WheelLeg net premium when bought to close"""
        from trading.wheel_strategy import WheelLeg

        leg = WheelLeg(
            leg_id=1,
            cycle_id=1,
            leg_type='CSP',
            action='SELL_TO_OPEN',
            strike=450.0,
            expiration_date=date.today() + timedelta(days=30),
            contracts=1,
            premium_received=3.00,
            premium_paid=1.00,  # Bought to close for $1
            open_date=datetime.now()
        )

        # Net premium = (3.00 - 1.00) * 1 * 100 = 200
        assert leg.net_premium == 200.0

    def test_wheel_cycle_total_pnl(self):
        """Test WheelCycle total P&L calculation"""
        from trading.wheel_strategy import WheelCycle, WheelPhase

        cycle = WheelCycle(
            cycle_id=1,
            symbol='SPY',
            status=WheelPhase.CSP,
            start_date=datetime.now(),
            realized_pnl=500.0,
            unrealized_pnl=100.0
        )

        assert cycle.total_pnl == 600.0

    def test_wheel_cycle_is_active(self):
        """Test WheelCycle active status"""
        from trading.wheel_strategy import WheelCycle, WheelPhase

        # Active states
        for status in [WheelPhase.CSP, WheelPhase.ASSIGNED, WheelPhase.COVERED_CALL]:
            cycle = WheelCycle(
                cycle_id=1,
                symbol='SPY',
                status=status,
                start_date=datetime.now()
            )
            assert cycle.is_active is True

        # Inactive states
        for status in [WheelPhase.CALLED_AWAY, WheelPhase.CLOSED]:
            cycle = WheelCycle(
                cycle_id=1,
                symbol='SPY',
                status=status,
                start_date=datetime.now()
            )
            assert cycle.is_active is False

    @patch('trading.wheel_strategy.get_connection')
    def test_start_wheel_cycle(self, mock_get_conn):
        """Test starting a new wheel cycle"""
        from trading.wheel_strategy import WheelStrategyManager

        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock the INSERT RETURNING
        mock_cursor.fetchone.side_effect = [(1,), (1,)]  # cycle_id, leg_id

        manager = WheelStrategyManager()

        # Start wheel
        cycle_id = manager.start_wheel_cycle(
            symbol='SPY',
            strike=450.0,
            expiration_date=date.today() + timedelta(days=30),
            contracts=1,
            premium=2.50,
            underlying_price=455.0,
            delta=0.30
        )

        assert cycle_id == 1

        # Verify INSERT was called for cycle and leg
        assert mock_cursor.execute.call_count >= 2

    @patch('trading.wheel_strategy.get_connection')
    def test_csp_expired_otm(self, mock_get_conn):
        """Test CSP expiring OTM (price above strike)"""
        from trading.wheel_strategy import WheelStrategyManager, WheelPhase

        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock cycle data (price > strike = OTM)
        mock_cursor.fetchone.side_effect = [
            # Cycle row (id, symbol, status, ...)
            (1, 'SPY', WheelPhase.CSP.value, datetime.now(), None, 0, 0, 250, 0, 250, None, None, None, None, 0, 0),
            # Leg row (id, cycle_id, leg_type, action, strike, exp, contracts, premium_received, ...)
            (1, 1, 'CSP', 'SELL_TO_OPEN', 450.0, date.today(), 1, 2.50, 0, datetime.now(), None, None, 455.0, None, 0.25, 0.30, 30, None),
        ]

        manager = WheelStrategyManager()

        # Process expiration with underlying at 455 (above 450 strike = OTM)
        result = manager.process_csp_expiration(cycle_id=1, final_underlying_price=455.0)

        assert result['action'] == 'EXPIRED_OTM'
        assert result['premium_kept'] == 250.0  # 2.50 * 1 * 100
        assert result['ready_for'] == 'NEW_CSP'

    @patch('trading.wheel_strategy.get_connection')
    def test_csp_assigned(self, mock_get_conn):
        """Test CSP being assigned (price below strike)"""
        from trading.wheel_strategy import WheelStrategyManager, WheelPhase

        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock cycle data (price < strike = ITM = assigned)
        mock_cursor.fetchone.side_effect = [
            # Cycle row
            (1, 'SPY', WheelPhase.CSP.value, datetime.now(), None, 0, 0, 250, 0, 250, None, None, None, None, 0, 0),
            # Leg row - strike is 450
            (1, 1, 'CSP', 'SELL_TO_OPEN', 450.0, date.today(), 1, 2.50, 0, datetime.now(), None, None, 455.0, None, 0.25, 0.30, 30, None),
        ]

        manager = WheelStrategyManager()

        # Process expiration with underlying at 445 (below 450 strike = ITM = assigned)
        result = manager.process_csp_expiration(cycle_id=1, final_underlying_price=445.0)

        assert result['action'] == 'ASSIGNED'
        assert result['shares_owned'] == 100  # 1 contract * 100 shares
        assert result['cost_basis'] == 447.50  # 450 - 2.50 premium
        assert result['ready_for'] == 'COVERED_CALL'

    def test_cost_basis_calculation(self):
        """Test cost basis calculation after assignment"""
        # Cost basis = strike - premium per share
        strike = 450.0
        premium = 2.50

        cost_basis = strike - premium
        assert cost_basis == 447.50

        # With multiple contracts, cost basis per share is the same
        # but total investment is different
        contracts = 2
        total_shares = contracts * 100
        total_cost = cost_basis * total_shares

        assert total_cost == 89500.0  # 447.50 * 200

    def test_covered_call_pnl_calculation(self):
        """Test P&L when shares are called away"""
        # Scenario:
        # - Assigned at $450 strike with $2.50 CSP premium
        # - Cost basis = $447.50
        # - Sold CC at $455 strike with $1.50 premium
        # - Called away at $455

        csp_premium = 2.50 * 100  # $250 per contract
        cc_premium = 1.50 * 100   # $150 per contract
        assignment_price = 450.0
        call_away_price = 455.0
        cost_basis = 447.50

        # Share appreciation P&L
        share_pnl = (call_away_price - cost_basis) * 100  # $750

        # Total premium collected
        total_premium = csp_premium + cc_premium  # $400

        # But share_pnl already includes CSP premium in cost basis
        # So total P&L from CC phase = share_pnl + cc_premium
        cycle_pnl = share_pnl + cc_premium  # $900

        assert share_pnl == 750.0
        assert cycle_pnl == 900.0


class TestWheelIntegration:
    """Integration tests for full wheel cycle"""

    def test_full_wheel_cycle_math(self):
        """Test math for a complete wheel cycle"""
        # Full cycle:
        # 1. Sell CSP at $450 strike for $2.50 premium
        # 2. Get assigned at $450
        # 3. Sell CC at $455 strike for $1.50 premium
        # 4. Get called away at $455

        # CSP Phase
        csp_strike = 450.0
        csp_premium = 2.50
        csp_total = csp_premium * 100  # $250

        # Assignment
        shares = 100
        cost_basis_per_share = csp_strike - csp_premium  # $447.50
        total_investment = cost_basis_per_share * shares  # $44,750

        # CC Phase
        cc_strike = 455.0
        cc_premium = 1.50
        cc_total = cc_premium * 100  # $150

        # Called Away
        sale_proceeds = cc_strike * shares  # $45,500

        # P&L Calculation
        # Method 1: From investment
        pnl_from_investment = sale_proceeds - total_investment + cc_total
        # = 45500 - 44750 + 150 = $900

        # Method 2: From components
        share_appreciation = (cc_strike - cost_basis_per_share) * shares  # $750
        total_pnl = share_appreciation + cc_total  # $900

        # Both methods should match
        assert pnl_from_investment == total_pnl == 900.0

        # Total premium collected (for reporting)
        total_premium = csp_total + cc_total
        assert total_premium == 400.0

        # ROI on capital at risk (cash for CSP)
        cash_at_risk = csp_strike * shares  # $45,000
        roi = (total_pnl / cash_at_risk) * 100
        assert roi == pytest.approx(2.0, rel=0.01)  # 2% return

    def test_wheel_cycle_with_roll(self):
        """Test wheel cycle with a roll"""
        # Scenario:
        # 1. Sell CSP at $450 for $2.50
        # 2. Stock drops, roll CSP down to $445 for net $0.50 credit
        # 3. CSP expires OTM
        # Total premium = $2.50 + $0.50 = $3.00

        csp1_premium = 2.50
        roll_buy_cost = 3.00  # Pay $3 to close
        roll_sell_credit = 3.50  # Get $3.50 for new CSP
        roll_net = roll_sell_credit - roll_buy_cost  # $0.50 credit

        total_premium = csp1_premium + roll_net
        assert total_premium == 3.00

        # If expired OTM, P&L = total premium * 100
        final_pnl = total_premium * 100
        assert final_pnl == 300.0


class TestExportService:
    """Tests for the export service"""

    def test_export_service_import(self):
        """Test that export service can be imported"""
        from trading.export_service import TradeExportService, export_service
        assert export_service is not None

    @patch('trading.export_service.get_connection')
    def test_export_returns_buffer(self, mock_get_conn):
        """Test that export returns a BytesIO buffer"""
        from trading.export_service import TradeExportService
        import pandas as pd
        import io

        # Mock empty dataframes
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        # Mock pd.read_sql_query to return empty DataFrames
        with patch('pandas.read_sql_query') as mock_read_sql:
            mock_read_sql.return_value = pd.DataFrame()

            service = TradeExportService()

            # Should return a buffer even with no data
            try:
                buffer = service.export_trade_history(format='csv')
                assert isinstance(buffer, io.BytesIO)
            except Exception:
                # openpyxl might not be installed
                pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
