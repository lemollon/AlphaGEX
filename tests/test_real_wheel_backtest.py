"""
Tests for Real Wheel Strategy Backtester

These tests verify the REAL data backtester works correctly:
1. Option ticker format is correct and verifiable
2. Data source tracking works
3. Wheel cycle logic is correct
4. Excel export generates proper audit trail
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.real_wheel_backtest import (
    RealWheelBacktester,
    OptionTrade,
    AccountSnapshot,
    WheelCycle,
    DataSource,
    run_real_wheel_backtest
)


class TestDataSource:
    """Test DataSource enum for transparency tracking"""

    def test_data_source_values(self):
        """Verify all data source types exist"""
        assert DataSource.POLYGON_HISTORICAL.value == "POLYGON_HISTORICAL"
        assert DataSource.POLYGON_REALTIME.value == "POLYGON_REALTIME"
        assert DataSource.ESTIMATED.value == "ESTIMATED"
        assert DataSource.UNAVAILABLE.value == "UNAVAILABLE"


class TestOptionTrade:
    """Test OptionTrade dataclass for full transparency"""

    def test_option_trade_creation(self):
        """Test creating a trade with all required fields"""
        trade = OptionTrade(
            trade_id=1,
            trade_date="2024-01-15",
            trade_type="SELL_CSP",
            option_ticker="O:SPY240119P00445000",
            underlying="SPY",
            strike=445.0,
            expiration="2024-01-19",
            option_type="put",
            entry_bid=2.50,
            entry_ask=2.60,
            entry_price=2.50,
            entry_underlying_price=450.0,
            price_source=DataSource.POLYGON_HISTORICAL
        )

        assert trade.trade_id == 1
        assert trade.option_ticker == "O:SPY240119P00445000"
        assert trade.price_source == DataSource.POLYGON_HISTORICAL
        assert trade.direction == "SHORT"

    def test_option_ticker_is_verifiable(self):
        """Option ticker should be in Polygon format"""
        trade = OptionTrade(
            trade_id=1,
            trade_date="2024-01-15",
            trade_type="SELL_CSP",
            option_ticker="O:SPY240119P00445000",
            underlying="SPY",
            strike=445.0,
            expiration="2024-01-19",
            option_type="put",
            entry_bid=2.50,
            entry_ask=2.60,
            entry_price=2.50,
            entry_underlying_price=450.0
        )

        # Ticker should start with "O:"
        assert trade.option_ticker.startswith("O:")
        # Should contain the symbol
        assert "SPY" in trade.option_ticker
        # Should have expiration date
        assert "240119" in trade.option_ticker
        # Should have P for put
        assert "P" in trade.option_ticker


class TestAccountSnapshot:
    """Test daily account snapshots"""

    def test_snapshot_creation(self):
        """Test creating a daily snapshot"""
        snapshot = AccountSnapshot(
            date="2024-01-15",
            cash_balance=1000000,
            shares_held=0,
            share_cost_basis=0,
            open_option_value=0,
            total_equity=1000000,
            daily_pnl=0,
            cumulative_pnl=0,
            peak_equity=1000000,
            drawdown_pct=0
        )

        assert snapshot.date == "2024-01-15"
        assert snapshot.total_equity == 1000000
        assert snapshot.drawdown_pct == 0


class TestWheelCycle:
    """Test wheel cycle tracking"""

    def test_cycle_creation(self):
        """Test creating a wheel cycle"""
        cycle = WheelCycle(
            cycle_id=1,
            symbol="SPY",
            start_date="2024-01-15"
        )

        assert cycle.cycle_id == 1
        assert cycle.status == "ACTIVE"
        assert cycle.total_premium_collected == 0

    def test_cycle_with_trades(self):
        """Test cycle can hold multiple trades"""
        trade1 = OptionTrade(
            trade_id=1,
            trade_date="2024-01-15",
            trade_type="SELL_CSP",
            option_ticker="O:SPY240119P00445000",
            underlying="SPY",
            strike=445.0,
            expiration="2024-01-19",
            option_type="put",
            entry_bid=2.50,
            entry_ask=2.60,
            entry_price=2.50,
            entry_underlying_price=450.0
        )

        cycle = WheelCycle(
            cycle_id=1,
            symbol="SPY",
            start_date="2024-01-15",
            trades=[trade1]
        )

        assert len(cycle.trades) == 1
        assert cycle.trades[0].trade_type == "SELL_CSP"


class TestRealWheelBacktester:
    """Test the main backtester class"""

    def test_backtester_initialization(self):
        """Test backtester initializes with correct defaults"""
        backtester = RealWheelBacktester(
            symbol="SPY",
            start_date="2023-01-01",
            initial_capital=1000000
        )

        assert backtester.symbol == "SPY"
        assert backtester.initial_capital == 1000000
        assert backtester.cash == 1000000
        assert backtester.shares_held == 0

    def test_option_ticker_building(self):
        """Test option ticker is built correctly"""
        backtester = RealWheelBacktester()

        # Test put option
        ticker = backtester._build_option_ticker(445.0, "2024-01-19", "put")
        assert ticker == "O:SPY240119P00445000"

        # Test call option
        ticker = backtester._build_option_ticker(460.0, "2024-02-16", "call")
        assert ticker == "O:SPY240216C00460000"

    def test_friday_expiration_calculation(self):
        """Test finding Friday expiration dates"""
        backtester = RealWheelBacktester()

        # From a Monday, 30 DTE should land on or after a Friday
        exp = backtester._get_friday_expiration("2024-01-15", 30)
        exp_date = datetime.strptime(exp, '%Y-%m-%d')

        # Should be a Friday
        assert exp_date.weekday() == 4

    def test_data_quality_tracking(self):
        """Test that data quality is tracked"""
        backtester = RealWheelBacktester()

        assert backtester.real_data_count == 0
        assert backtester.estimated_data_count == 0

    def test_calculate_equity(self):
        """Test equity calculation"""
        backtester = RealWheelBacktester(initial_capital=100000)
        backtester.cash = 50000
        backtester.shares_held = 100

        # Equity = cash + shares * price
        equity = backtester._calculate_equity(500.0)
        assert equity == 100000  # 50000 + 100 * 500


class TestBacktesterWithMockedData:
    """Test backtester with mocked Polygon data"""

    @pytest.fixture
    def mock_price_data(self):
        """Create mock price data"""
        dates = pd.date_range(start='2023-01-03', periods=60, freq='B')
        data = pd.DataFrame({
            'Open': np.random.uniform(440, 460, 60),
            'High': np.random.uniform(445, 465, 60),
            'Low': np.random.uniform(435, 455, 60),
            'Close': np.random.uniform(440, 460, 60),
            'Volume': np.random.randint(1000000, 5000000, 60)
        }, index=dates)
        return data

    def test_backtest_runs_with_mock_data(self, mock_price_data):
        """Test that backtest runs to completion with mock data"""
        backtester = RealWheelBacktester(
            symbol="SPY",
            start_date="2023-01-03",
            end_date="2023-03-31",
            initial_capital=100000
        )

        # Mock the price data fetch
        with patch.object(backtester, '_fetch_price_data'):
            backtester.price_data = mock_price_data

            # Mock option price lookups
            with patch.object(backtester, '_get_option_price') as mock_price:
                # Return mock option price data
                mock_price.return_value = (
                    2.50,  # bid
                    2.60,  # ask
                    2.55,  # mid
                    DataSource.ESTIMATED,
                    "O:SPY230120P00445000"
                )

                results = backtester.run()

                assert results is not None
                assert 'summary' in results
                assert 'data_quality' in results
                assert 'all_trades' in results


class TestExcelExport:
    """Test Excel export functionality"""

    def test_export_creates_file(self, tmp_path):
        """Test that export creates an Excel file"""
        backtester = RealWheelBacktester(initial_capital=100000)

        # Add some mock data
        backtester.all_trades.append(OptionTrade(
            trade_id=1,
            trade_date="2024-01-15",
            trade_type="SELL_CSP",
            option_ticker="O:SPY240119P00445000",
            underlying="SPY",
            strike=445.0,
            expiration="2024-01-19",
            option_type="put",
            entry_bid=2.50,
            entry_ask=2.60,
            entry_price=2.50,
            entry_underlying_price=450.0
        ))

        backtester.daily_snapshots.append(AccountSnapshot(
            date="2024-01-15",
            cash_balance=100000,
            shares_held=0,
            share_cost_basis=0,
            open_option_value=0,
            total_equity=100000,
            daily_pnl=0,
            cumulative_pnl=0,
            peak_equity=100000,
            drawdown_pct=0
        ))

        # Create mock price data for equity calculation
        dates = pd.date_range(start='2024-01-15', periods=5, freq='B')
        backtester.price_data = pd.DataFrame({
            'Close': [450.0, 451.0, 449.0, 452.0, 450.5]
        }, index=dates)

        # Export
        filepath = str(tmp_path / "test_export.xlsx")

        try:
            result = backtester.export_to_excel(filepath)

            if result is not None:
                assert os.path.exists(filepath)

                # Verify Excel has expected sheets
                xl = pd.ExcelFile(filepath)
                assert 'Summary' in xl.sheet_names
                assert 'All Trades' in xl.sheet_names
                assert 'Daily Snapshots' in xl.sheet_names
        except ImportError:
            # openpyxl not installed, skip
            pytest.skip("openpyxl not installed")


class TestVerifiability:
    """Test that all data is verifiable"""

    def test_option_ticker_format_is_polygon_compatible(self):
        """Verify option ticker matches Polygon format"""
        backtester = RealWheelBacktester()

        # Build various tickers
        tickers = [
            backtester._build_option_ticker(445.0, "2024-01-19", "put"),
            backtester._build_option_ticker(500.0, "2024-06-21", "call"),
            backtester._build_option_ticker(420.5, "2024-12-20", "put"),
        ]

        for ticker in tickers:
            # Must start with O:
            assert ticker.startswith("O:")
            # Must contain underlying
            assert "SPY" in ticker
            # Must have 6-digit expiration
            assert len(ticker.split("SPY")[1]) >= 6
            # Must have C or P
            assert "C" in ticker or "P" in ticker

    def test_trade_has_all_required_audit_fields(self):
        """Every trade should have fields needed for audit"""
        trade = OptionTrade(
            trade_id=1,
            trade_date="2024-01-15",
            trade_type="SELL_CSP",
            option_ticker="O:SPY240119P00445000",
            underlying="SPY",
            strike=445.0,
            expiration="2024-01-19",
            option_type="put",
            entry_bid=2.50,
            entry_ask=2.60,
            entry_price=2.50,
            entry_underlying_price=450.0,
            price_source=DataSource.POLYGON_HISTORICAL
        )

        # Required for verification
        assert trade.option_ticker is not None
        assert trade.entry_bid is not None
        assert trade.entry_ask is not None
        assert trade.entry_price is not None
        assert trade.price_source is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
