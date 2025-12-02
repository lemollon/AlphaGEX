"""
Tests for Wheel + Premium Portfolio Backtester

Tests:
1. Capital allocation logic
2. Strategy selection based on regime
3. Strike calculations for iron condors and spreads
4. Premium estimation
5. Trade outcome simulation
6. Risk management
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


class TestPremiumPortfolioImports:
    """Test that all imports work correctly"""

    def test_import_module(self):
        """Test module imports"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester,
            PremiumStrategy,
            MarketRegime,
            PremiumTrade,
            PortfolioState
        )
        assert PremiumPortfolioBacktester is not None
        assert PremiumStrategy is not None

    def test_premium_strategy_enum(self):
        """Test PremiumStrategy enum values"""
        from backtest.premium_portfolio_backtest import PremiumStrategy

        assert PremiumStrategy.IRON_CONDOR.value == "IRON_CONDOR"
        assert PremiumStrategy.BULL_PUT_SPREAD.value == "BULL_PUT_SPREAD"
        assert PremiumStrategy.BEAR_CALL_SPREAD.value == "BEAR_CALL_SPREAD"

    def test_market_regime_enum(self):
        """Test MarketRegime enum values"""
        from backtest.premium_portfolio_backtest import MarketRegime

        assert MarketRegime.LOW_VOL_BULLISH.value == "LOW_VOL_BULLISH"
        assert MarketRegime.HIGH_VOL_NEUTRAL.value == "HIGH_VOL_NEUTRAL"


class TestCapitalAllocation:
    """Test capital allocation logic"""

    def test_default_allocation(self):
        """Test default allocation percentages"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(
            symbol='SPY',
            start_date='2023-01-01',
            end_date='2023-12-31',
            initial_capital=100000
        )

        assert bt.wheel_allocation == 0.65
        assert bt.premium_allocation == 0.30
        assert bt.cash_reserve == 0.05

        # Should sum to 100%
        total = bt.wheel_allocation + bt.premium_allocation + bt.cash_reserve
        assert total == pytest.approx(1.0)

    def test_custom_allocation(self):
        """Test custom allocation"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(
            wheel_allocation=0.70,
            premium_allocation=0.25,
            cash_reserve=0.05,
            initial_capital=100000
        )

        assert bt.wheel_allocation == 0.70
        assert bt.premium_allocation == 0.25

    def test_wheel_capital_calculation(self):
        """Test wheel capital is correctly calculated"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(
            wheel_allocation=0.60,
            initial_capital=100000
        )

        # Wheel backtester should have 60% of capital
        expected_wheel_capital = 100000 * 0.60
        assert bt.wheel_backtester.initial_capital == expected_wheel_capital


class TestRegimeDetection:
    """Test market regime detection"""

    def test_low_vol_bullish(self):
        """Test LOW_VOL_BULLISH regime detection"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, MarketRegime
        )

        bt = PremiumPortfolioBacktester()
        row = pd.Series({'HV': 0.15, 'trend': 'bullish'})

        regime = bt.detect_market_regime(row)
        assert regime == MarketRegime.LOW_VOL_BULLISH

    def test_high_vol_bearish(self):
        """Test HIGH_VOL_BEARISH regime detection"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, MarketRegime
        )

        bt = PremiumPortfolioBacktester()
        row = pd.Series({'HV': 0.35, 'trend': 'bearish'})

        regime = bt.detect_market_regime(row)
        assert regime == MarketRegime.HIGH_VOL_BEARISH

    def test_low_vol_neutral(self):
        """Test LOW_VOL_NEUTRAL regime detection"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, MarketRegime
        )

        bt = PremiumPortfolioBacktester()
        row = pd.Series({'HV': 0.18, 'trend': 'neutral'})

        regime = bt.detect_market_regime(row)
        assert regime == MarketRegime.LOW_VOL_NEUTRAL


class TestStrategySelection:
    """Test strategy selection based on regime"""

    def test_iron_condor_for_neutral(self):
        """Test iron condor selected for neutral regimes"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, MarketRegime, PremiumStrategy
        )

        bt = PremiumPortfolioBacktester()

        strategy = bt.select_premium_strategy(MarketRegime.LOW_VOL_NEUTRAL)
        assert strategy == PremiumStrategy.IRON_CONDOR

        strategy = bt.select_premium_strategy(MarketRegime.HIGH_VOL_NEUTRAL)
        assert strategy == PremiumStrategy.IRON_CONDOR

    def test_bull_put_for_bullish(self):
        """Test bull put spread for bullish regimes"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, MarketRegime, PremiumStrategy
        )

        bt = PremiumPortfolioBacktester()

        strategy = bt.select_premium_strategy(MarketRegime.LOW_VOL_BULLISH)
        assert strategy == PremiumStrategy.BULL_PUT_SPREAD

    def test_bear_call_for_bearish(self):
        """Test bear call spread for bearish regimes"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, MarketRegime, PremiumStrategy
        )

        bt = PremiumPortfolioBacktester()

        strategy = bt.select_premium_strategy(MarketRegime.HIGH_VOL_BEARISH)
        assert strategy == PremiumStrategy.BEAR_CALL_SPREAD


class TestStrikeCalculations:
    """Test strike price calculations"""

    def test_iron_condor_strikes(self):
        """Test iron condor strike calculation"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(iron_condor_width=0.10)

        spot = 450.0
        vol = 0.20
        dte = 45

        put_long, put_short, call_short, call_long = bt.calculate_iron_condor_strikes(
            spot, vol, dte
        )

        # Put side should be below spot
        assert put_short < spot
        assert put_long < put_short

        # Call side should be above spot
        assert call_short > spot
        assert call_long > call_short

        # Wings should be roughly equal distance from center
        put_width = put_short - put_long
        call_width = call_long - call_short
        assert put_width == pytest.approx(call_width, rel=0.2)

    def test_bull_put_spread_strikes(self):
        """Test bull put spread strike calculation"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(spread_width=5)

        spot = 450.0
        vol = 0.20
        dte = 45

        long_strike, short_strike = bt.calculate_spread_strikes(
            spot, vol, dte, is_put_spread=True
        )

        # Both strikes below spot for puts
        assert short_strike < spot
        assert long_strike < short_strike

        # Width should be spread_width
        assert short_strike - long_strike == 5

    def test_bear_call_spread_strikes(self):
        """Test bear call spread strike calculation"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(spread_width=5)

        spot = 450.0
        vol = 0.20
        dte = 45

        long_strike, short_strike = bt.calculate_spread_strikes(
            spot, vol, dte, is_put_spread=False
        )

        # Both strikes above spot for calls
        assert short_strike > spot
        assert long_strike > short_strike

        # Width should be spread_width
        assert long_strike - short_strike == 5


class TestPremiumEstimation:
    """Test premium estimation"""

    def test_spread_premium_positive(self):
        """Test spread premium is positive"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester()

        premium = bt.estimate_spread_premium(
            spot=450,
            short_strike=440,
            long_strike=435,
            vol=0.20,
            dte=45,
            is_put=True
        )

        assert premium > 0
        assert premium < 5  # Less than width

    def test_iron_condor_premium(self):
        """Test iron condor premium calculation"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester()

        premium = bt.estimate_iron_condor_premium(
            spot=450,
            put_long=420,
            put_short=430,
            call_short=470,
            call_long=480,
            vol=0.20,
            dte=45
        )

        assert premium > 0
        # Should be sum of put and call credit
        # Not more than total width
        assert premium < 20

    def test_higher_vol_more_premium(self):
        """Test that higher vol gives more premium"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester()

        low_vol_premium = bt.estimate_spread_premium(
            spot=450, short_strike=440, long_strike=435,
            vol=0.15, dte=45, is_put=True
        )

        high_vol_premium = bt.estimate_spread_premium(
            spot=450, short_strike=440, long_strike=435,
            vol=0.30, dte=45, is_put=True
        )

        assert high_vol_premium > low_vol_premium


class TestTradeOutcomes:
    """Test trade outcome simulation"""

    def test_iron_condor_max_profit(self):
        """Test iron condor max profit when price in center"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, PremiumTrade, PremiumStrategy
        )

        bt = PremiumPortfolioBacktester()

        trade = PremiumTrade(
            trade_id=1,
            strategy=PremiumStrategy.IRON_CONDOR,
            symbol='SPY',
            entry_date='2023-01-01',
            exit_date=None,
            short_strike=430,      # Put short
            long_strike=420,       # Put long
            short_strike_2=470,    # Call short
            long_strike_2=480,     # Call long
            contracts=1,
            premium_received=2.50,
            max_loss=750,          # $10 width - $2.50 premium
            underlying_at_entry=450
        )

        # Price expires at 450 (in the sweet spot)
        result = bt.simulate_premium_trade_outcome(trade, exit_price=450, days_held=45)

        assert result.outcome == "MAX_PROFIT"
        assert result.pnl == 250  # $2.50 * 100

    def test_bull_put_spread_max_profit(self):
        """Test bull put spread max profit when price above short strike"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, PremiumTrade, PremiumStrategy
        )

        bt = PremiumPortfolioBacktester()

        trade = PremiumTrade(
            trade_id=1,
            strategy=PremiumStrategy.BULL_PUT_SPREAD,
            symbol='SPY',
            entry_date='2023-01-01',
            exit_date=None,
            short_strike=440,
            long_strike=435,
            contracts=1,
            premium_received=1.50,
            max_loss=350,
            underlying_at_entry=450
        )

        # Price expires above short strike
        result = bt.simulate_premium_trade_outcome(trade, exit_price=445, days_held=45)

        assert result.outcome == "MAX_PROFIT"
        assert result.pnl == 150  # $1.50 * 100

    def test_bull_put_spread_loss(self):
        """Test bull put spread loss when price below long strike"""
        from backtest.premium_portfolio_backtest import (
            PremiumPortfolioBacktester, PremiumTrade, PremiumStrategy
        )

        bt = PremiumPortfolioBacktester()

        trade = PremiumTrade(
            trade_id=1,
            strategy=PremiumStrategy.BULL_PUT_SPREAD,
            symbol='SPY',
            entry_date='2023-01-01',
            exit_date=None,
            short_strike=440,
            long_strike=435,
            contracts=1,
            premium_received=1.50,
            max_loss=350,
            underlying_at_entry=450
        )

        # Price expires below long strike - max loss
        result = bt.simulate_premium_trade_outcome(trade, exit_price=430, days_held=45)

        assert result.outcome == "LOSS"
        assert result.pnl == -350


class TestRiskManagement:
    """Test risk management features"""

    def test_max_positions_limit(self):
        """Test max positions parameter"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(max_positions=3)
        assert bt.max_positions == 3

    def test_profit_target(self):
        """Test profit target parameter"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(profit_target_pct=0.50)
        assert bt.profit_target_pct == 0.50

    def test_stop_loss(self):
        """Test stop loss parameter"""
        from backtest.premium_portfolio_backtest import PremiumPortfolioBacktester

        bt = PremiumPortfolioBacktester(stop_loss_pct=2.0)
        assert bt.stop_loss_pct == 2.0


class TestPremiumTrade:
    """Test PremiumTrade dataclass"""

    def test_trade_initialization(self):
        """Test PremiumTrade initializes correctly"""
        from backtest.premium_portfolio_backtest import PremiumTrade, PremiumStrategy

        trade = PremiumTrade(
            trade_id=1,
            strategy=PremiumStrategy.IRON_CONDOR,
            symbol='SPY',
            entry_date='2023-01-01',
            exit_date=None,
            short_strike=440,
            long_strike=430,
            contracts=2,
            premium_received=3.00,
            max_loss=1400
        )

        assert trade.trade_id == 1
        assert trade.strategy == PremiumStrategy.IRON_CONDOR
        assert trade.contracts == 2
        assert trade.premium_received == 3.00
        assert trade.outcome == "OPEN"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
