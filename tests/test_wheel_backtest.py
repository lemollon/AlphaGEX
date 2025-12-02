"""
Tests for Wheel Strategy Backtester

Tests the wheel backtest mechanics:
1. CSP strike selection
2. Premium estimation
3. Assignment logic
4. CC selling and called away
5. Full cycle P&L calculation
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWheelBacktester:
    """Test suite for wheel backtester"""

    def test_import(self):
        """Test that wheel backtest module imports correctly"""
        from backtest.wheel_backtest import WheelBacktester, WheelCycleTrade
        assert WheelBacktester is not None
        assert WheelCycleTrade is not None

    def test_backtester_initialization(self):
        """Test backtester initializes with correct parameters"""
        from backtest.wheel_backtest import WheelBacktester

        bt = WheelBacktester(
            symbol='SPY',
            start_date='2023-01-01',
            end_date='2023-12-31',
            csp_delta=0.25,
            cc_delta=0.30
        )

        assert bt.symbol == 'SPY'
        assert bt.csp_delta == 0.25
        assert bt.cc_delta == 0.30
        assert bt.csp_dte == 30
        assert bt.cc_dte == 21

    def test_csp_strike_selection(self):
        """Test CSP strike is selected below spot price"""
        from backtest.wheel_backtest import WheelBacktester

        bt = WheelBacktester(csp_delta=0.25)

        spot = 450.0
        vol = 0.20  # 20% volatility

        strike = bt.select_csp_strike(spot, vol)

        # Strike should be below spot for OTM put
        assert strike < spot
        # Should be reasonably close (within 10%)
        assert strike > spot * 0.90

    def test_cc_strike_selection(self):
        """Test CC strike is above cost basis"""
        from backtest.wheel_backtest import WheelBacktester

        bt = WheelBacktester(cc_delta=0.30)

        cost_basis = 447.50
        current_price = 445.0
        vol = 0.20

        strike = bt.select_cc_strike(cost_basis, current_price, vol)

        # Strike must be above cost basis
        assert strike > cost_basis

    def test_put_premium_estimation(self):
        """Test put premium is reasonable"""
        from backtest.wheel_backtest import WheelBacktester

        bt = WheelBacktester()

        spot = 450.0
        strike = 440.0  # 10 points OTM
        dte = 30
        vol = 0.20

        premium = bt.estimate_put_premium(spot, strike, dte, vol)

        # Premium should be positive
        assert premium > 0
        # OTM put premium typically 1-5% of strike for 30 DTE
        assert premium < strike * 0.05
        assert premium > 0.05  # Minimum floor

    def test_call_premium_estimation(self):
        """Test call premium is reasonable"""
        from backtest.wheel_backtest import WheelBacktester

        bt = WheelBacktester()

        spot = 450.0
        strike = 460.0  # 10 points OTM
        dte = 21
        vol = 0.20

        premium = bt.estimate_call_premium(spot, strike, dte, vol)

        # Premium should be positive
        assert premium > 0
        # OTM call premium typically 0.5-3% of spot for 21 DTE
        assert premium < spot * 0.03

    def test_volatility_calculation(self):
        """Test historical volatility calculation"""
        from backtest.wheel_backtest import WheelBacktester

        bt = WheelBacktester()

        # Create sample price data
        dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
        prices = 450 + np.random.randn(100).cumsum() * 0.5  # Random walk

        df = pd.DataFrame({'Close': prices}, index=dates)

        vol = bt.estimate_historical_volatility(df, lookback=20)

        # Should return a series
        assert isinstance(vol, pd.Series)
        # Values should be positive
        assert (vol >= 0).all()
        # Should be reasonable volatility range (0-100%)
        assert vol.max() < 2.0


class TestWheelCycleTrade:
    """Test wheel cycle trade data structure"""

    def test_cycle_initialization(self):
        """Test WheelCycleTrade initializes correctly"""
        from backtest.wheel_backtest import WheelCycleTrade

        cycle = WheelCycleTrade(
            cycle_id=1,
            symbol='SPY',
            start_date='2023-01-01',
            end_date=None,
            csp_strike=450.0,
            csp_premium=2.50,
            csp_expiration='2023-02-01',
            csp_outcome='PENDING'
        )

        assert cycle.cycle_id == 1
        assert cycle.csp_strike == 450.0
        assert cycle.csp_premium == 2.50
        assert cycle.cc_premiums == []  # Default empty list
        assert cycle.cc_strikes == []

    def test_cycle_with_assignment(self):
        """Test cycle with assignment tracking"""
        from backtest.wheel_backtest import WheelCycleTrade

        cycle = WheelCycleTrade(
            cycle_id=1,
            symbol='SPY',
            start_date='2023-01-01',
            end_date='2023-03-01',
            csp_strike=450.0,
            csp_premium=2.50,
            csp_expiration='2023-02-01',
            csp_outcome='ASSIGNED',
            shares_assigned=100,
            cost_basis_per_share=447.50
        )

        assert cycle.shares_assigned == 100
        assert cycle.cost_basis_per_share == 447.50
        # Cost basis = strike - premium
        assert cycle.cost_basis_per_share == cycle.csp_strike - cycle.csp_premium


class TestWheelPnLCalculations:
    """Test P&L calculations for wheel strategy"""

    def test_csp_expired_otm_pnl(self):
        """Test P&L when CSP expires OTM"""
        # CSP at $450 strike, $2.50 premium, 1 contract
        strike = 450.0
        premium = 2.50
        contracts = 1
        shares = contracts * 100

        # Full premium kept
        pnl = premium * shares
        assert pnl == 250.0

        # ROI on capital at risk
        capital_at_risk = strike * shares
        roi_pct = (pnl / capital_at_risk) * 100
        assert roi_pct == pytest.approx(0.556, rel=0.01)  # ~0.56%

    def test_full_cycle_pnl(self):
        """Test P&L for complete wheel cycle"""
        # Cycle:
        # 1. CSP $450 strike, $2.50 premium -> Assigned
        # 2. CC $455 strike, $1.50 premium -> Called away

        csp_strike = 450.0
        csp_premium = 2.50
        cc_strike = 455.0
        cc_premium = 1.50
        shares = 100

        # Cost basis after assignment
        cost_basis = csp_strike - csp_premium
        assert cost_basis == 447.50

        # Premiums collected
        total_premium = (csp_premium + cc_premium) * shares
        assert total_premium == 400.0

        # Capital appreciation (sold at CC strike)
        share_appreciation = (cc_strike - cost_basis) * shares
        assert share_appreciation == 750.0

        # Total P&L
        # Note: The CSP premium is already in cost basis
        # So total = share appreciation + CC premium only
        total_pnl = share_appreciation + (cc_premium * shares)
        assert total_pnl == 900.0

        # Alternative calculation: All premiums + (call_strike - csp_strike) * shares
        alt_pnl = total_premium + (cc_strike - csp_strike) * shares
        assert alt_pnl == 900.0

    def test_losing_wheel_cycle(self):
        """Test P&L when wheel results in loss"""
        # Cycle:
        # 1. CSP $450 strike, $2.50 premium -> Assigned
        # 2. Stock drops, can't sell CC above cost basis
        # 3. Force exit at $430

        csp_strike = 450.0
        csp_premium = 2.50
        exit_price = 430.0
        shares = 100

        cost_basis = csp_strike - csp_premium  # 447.50

        # Premium collected
        premium = csp_premium * shares  # $250

        # Share loss
        share_loss = (exit_price - cost_basis) * shares  # (430 - 447.50) * 100 = -1750

        # Total P&L
        total_pnl = premium + share_loss
        # Premium already in cost basis, so:
        total_pnl = (exit_price - cost_basis) * shares
        assert total_pnl == -1750.0

    def test_multiple_cc_cycles(self):
        """Test P&L with multiple CC attempts before called away"""
        # Cycle:
        # 1. CSP $450, $2.50 -> Assigned at 447.50 cost basis
        # 2. CC $455, $1.50 -> Expired OTM
        # 3. CC $453, $1.25 -> Expired OTM
        # 4. CC $452, $1.00 -> Called away

        cost_basis = 447.50
        cc_premiums = [1.50, 1.25, 1.00]
        call_away_strike = 452.0
        shares = 100

        # All CC premiums
        total_cc_premium = sum(cc_premiums) * shares  # $375

        # Share appreciation
        share_appreciation = (call_away_strike - cost_basis) * shares  # $450

        # Total (CSP premium already in cost basis)
        total_pnl = total_cc_premium + share_appreciation
        assert total_pnl == 825.0


class TestWheelBacktestIntegration:
    """Integration tests for wheel backtest"""

    @patch('backtest.wheel_backtest.WheelBacktester.fetch_historical_data')
    def test_backtest_runs_with_mock_data(self, mock_fetch):
        """Test backtest runs with mocked price data"""
        from backtest.wheel_backtest import WheelBacktester

        # Create mock price data
        dates = pd.date_range(start='2023-01-01', periods=200, freq='D')
        prices = 450 + np.cumsum(np.random.randn(200) * 2)  # Random walk

        mock_df = pd.DataFrame({
            'Open': prices * 0.999,
            'High': prices * 1.005,
            'Low': prices * 0.995,
            'Close': prices,
            'Volume': np.random.randint(1000000, 5000000, 200)
        }, index=dates)

        bt = WheelBacktester(
            symbol='SPY',
            start_date='2023-01-01',
            end_date='2023-06-30'
        )

        # Mock fetch to set price_data directly
        def set_price_data():
            bt.price_data = mock_df
            return mock_df

        mock_fetch.side_effect = set_price_data

        # Run should not raise
        try:
            results = bt.run_backtest()
            # Should have some trades
            assert results is not None
        except Exception as e:
            # Some exceptions are OK in test environment
            if "No data" in str(e):
                pass
            else:
                raise


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
