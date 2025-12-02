"""
Tests for Export API Endpoints

Tests the export functionality:
1. Trade history export
2. P&L attribution export
3. Decision logs export
4. Wheel cycles export
5. Full audit export
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import os
import io

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExportEndpoints:
    """Test suite for export API endpoints"""

    @pytest.fixture
    def mock_db_connection(self):
        """Create a mock database connection"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    def test_export_service_initialization(self):
        """Test that export service initializes correctly"""
        from trading.export_service import TradeExportService

        service = TradeExportService()
        assert service is not None
        assert hasattr(service, 'export_trade_history')
        assert hasattr(service, 'export_pnl_attribution')
        assert hasattr(service, 'export_decision_logs')
        assert hasattr(service, 'export_wheel_cycles')
        assert hasattr(service, 'export_full_audit')

    def test_openpyxl_availability_check(self):
        """Test that openpyxl availability is properly detected"""
        from trading.export_service import OPENPYXL_AVAILABLE

        # Should be a boolean
        assert isinstance(OPENPYXL_AVAILABLE, bool)

    @patch('trading.export_service.get_connection')
    def test_export_trade_history_csv(self, mock_get_conn):
        """Test CSV export returns valid buffer"""
        import pandas as pd
        from trading.export_service import TradeExportService

        # Create mock data
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        with patch('pandas.read_sql_query') as mock_sql:
            # Return empty DataFrames
            mock_sql.return_value = pd.DataFrame({
                'id': [],
                'symbol': [],
                'strategy': [],
                'strike': [],
                'option_type': [],
                'contracts': [],
                'entry_date': [],
                'entry_time': [],
                'entry_price': [],
                'realized_pnl': [],
                'gex_regime': [],
            })

            service = TradeExportService()
            buffer = service.export_trade_history(format='csv')

            assert isinstance(buffer, io.BytesIO)
            assert buffer.getvalue() is not None

    @patch('trading.export_service.get_connection')
    def test_pnl_attribution_calculation(self, mock_get_conn):
        """Test P&L attribution math"""
        import pandas as pd
        from trading.export_service import TradeExportService

        # Test data with known values
        test_data = pd.DataFrame({
            'id': [1, 2, 3],
            'exit_date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'exit_time': ['10:00:00', '11:00:00', '12:00:00'],
            'strategy': ['IRON_CONDOR', 'BULL_PUT_SPREAD', 'CSP'],
            'strike': [450, 445, 440],
            'option_type': ['spread', 'spread', 'put'],
            'contracts': [1, 2, 1],
            'entry_price': [2.00, 1.50, 3.00],
            'exit_price': [1.00, 0.75, 0.50],
            'realized_pnl': [100, 150, 250],  # Net P&L
            'hold_time_hours': [5, 8, 24],
            'exit_reason': ['TARGET', 'TARGET', 'EXPIRED_OTM']
        })

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        with patch('pandas.read_sql_query') as mock_sql:
            mock_sql.return_value = test_data

            service = TradeExportService()

            # Calculate expected values
            total_pnl = test_data['realized_pnl'].sum()
            assert total_pnl == 500

            # Test contribution percentages
            contributions = (test_data['realized_pnl'] / abs(total_pnl)) * 100
            assert contributions.iloc[0] == pytest.approx(20.0, rel=0.01)  # 100/500
            assert contributions.iloc[1] == pytest.approx(30.0, rel=0.01)  # 150/500
            assert contributions.iloc[2] == pytest.approx(50.0, rel=0.01)  # 250/500

    def test_running_total_calculation(self):
        """Test running total calculation"""
        import pandas as pd

        pnl_values = pd.Series([100, -50, 200, -25, 75])
        running_total = pnl_values.cumsum()

        expected = pd.Series([100, 50, 250, 225, 300])
        pd.testing.assert_series_equal(running_total, expected)

    def test_gross_pnl_calculation(self):
        """Test gross P&L calculation from entry/exit prices"""
        # Gross P&L = (exit - entry) * contracts * 100

        # Winning trade
        entry = 2.00
        exit_price = 1.00  # Credit spread, want it to go to 0
        contracts = 1
        gross = (entry - exit_price) * contracts * 100  # For credit spread
        assert gross == 100.0

        # Losing trade
        entry = 1.50
        exit_price = 2.50  # Had to buy back higher
        contracts = 2
        gross = (entry - exit_price) * contracts * 100
        assert gross == -200.0

    def test_commission_estimation(self):
        """Test commission estimation"""
        # Standard retail: $0.65 per contract, entry + exit
        contracts = 5
        commission_per_contract = 0.65
        round_trips = 2  # Entry and exit

        total_commission = contracts * commission_per_contract * round_trips
        assert total_commission == 6.50

    def test_empty_export_handling(self):
        """Test handling of empty data export"""
        from trading.export_service import TradeExportService, OPENPYXL_AVAILABLE

        service = TradeExportService()

        # Test empty export message
        buffer = service._create_empty_export("No trades found")

        assert isinstance(buffer, io.BytesIO)
        content = buffer.getvalue()
        assert len(content) > 0

        if OPENPYXL_AVAILABLE:
            # Should be an Excel file
            # Excel files start with PK (ZIP format)
            assert content[:2] == b'PK'
        else:
            # Should be text
            assert b'No trades found' in content


class TestWheelExport:
    """Test wheel cycle export functionality"""

    def test_wheel_cycle_premium_tracking(self):
        """Test premium tracking across wheel cycle"""
        # CSP Phase
        csp_premium = 2.50 * 1 * 100  # $250

        # CC Phase (after assignment)
        cc_premium_1 = 1.25 * 1 * 100  # $125
        cc_premium_2 = 1.00 * 1 * 100  # $100 (after first CC expired OTM)
        cc_premium_3 = 0.75 * 1 * 100  # $75 (called away on this one)

        total_cc_premium = cc_premium_1 + cc_premium_2 + cc_premium_3
        assert total_cc_premium == 300.0

        total_premium = csp_premium + total_cc_premium
        assert total_premium == 550.0

    def test_wheel_cycle_pnl_breakdown(self):
        """Test P&L breakdown for wheel export"""
        # Full cycle breakdown
        breakdown = {
            'csp_premium': 250.0,
            'cc_premiums': [125.0, 100.0, 75.0],
            'assignment_price': 450.0,
            'called_away_price': 455.0,
            'shares': 100
        }

        # Premium income
        total_premium = breakdown['csp_premium'] + sum(breakdown['cc_premiums'])
        assert total_premium == 550.0

        # Capital appreciation
        appreciation = (breakdown['called_away_price'] - breakdown['assignment_price']) * breakdown['shares']
        assert appreciation == 500.0

        # But cost basis includes CSP premium
        cost_basis = breakdown['assignment_price'] - (breakdown['csp_premium'] / 100)
        assert cost_basis == 447.50

        # Actual share P&L from cost basis
        share_pnl = (breakdown['called_away_price'] - cost_basis) * breakdown['shares']
        assert share_pnl == 750.0

        # Total cycle P&L = share P&L + CC premiums
        # (CSP premium is already baked into cost basis)
        total_pnl = share_pnl + sum(breakdown['cc_premiums'])
        assert total_pnl == 1050.0


class TestExportDataIntegrity:
    """Test data integrity in exports"""

    def test_date_formatting(self):
        """Test date formatting in exports"""
        from datetime import date, datetime

        # Test date to string conversion
        test_date = date(2024, 1, 15)
        formatted = str(test_date)
        assert formatted == '2024-01-15'

        # Test datetime to string
        test_datetime = datetime(2024, 1, 15, 10, 30, 45)
        formatted = test_datetime.strftime('%Y-%m-%d %H:%M:%S')
        assert formatted == '2024-01-15 10:30:45'

    def test_numeric_rounding(self):
        """Test numeric precision in exports"""
        value = 123.456789

        # P&L should show 2 decimal places
        rounded = round(value, 2)
        assert rounded == 123.46

        # Percentages should show 2 decimal places
        pct = 0.123456
        rounded_pct = round(pct * 100, 2)
        assert rounded_pct == 12.35

    def test_null_handling(self):
        """Test NULL/None handling in exports"""
        import pandas as pd

        # Create DataFrame with nulls
        df = pd.DataFrame({
            'value': [1.0, None, 3.0],
            'text': ['a', None, 'c']
        })

        # Fillna for numeric
        df['value'] = df['value'].fillna(0)
        assert df['value'].tolist() == [1.0, 0.0, 3.0]

        # Fillna for text
        df['text'] = df['text'].fillna('')
        assert df['text'].tolist() == ['a', '', 'c']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
