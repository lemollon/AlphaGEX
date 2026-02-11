"""
JUBILEE Box Spread Synthetic Borrowing Tests

Unit tests for the JUBILEE box spread strategy components.

Run with: pytest tests/test_jubilee.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestJubileeModelsImport:
    """Tests for JUBILEE models import"""

    def test_import_jubilee_models(self):
        """Test that JUBILEE models can be imported"""
        from trading.jubilee.models import (
            BoxSpreadPosition,
            BoxSpreadSignal,
            JubileeConfig,
            TradingMode,
            PositionStatus,
            BoxSpreadStatus,
            BorrowingCostAnalysis,
            CapitalDeployment,
            RollDecision,
            DailyBriefing,
        )
        assert BoxSpreadPosition is not None
        assert BoxSpreadSignal is not None
        assert JubileeConfig is not None
        assert TradingMode is not None
        assert PositionStatus is not None
        assert BoxSpreadStatus is not None
        assert BorrowingCostAnalysis is not None
        assert CapitalDeployment is not None
        assert RollDecision is not None
        assert DailyBriefing is not None


class TestJubileeConfig:
    """Tests for JUBILEE configuration"""

    def test_default_config(self):
        """Test default configuration values"""
        from trading.jubilee.models import JubileeConfig, TradingMode

        config = JubileeConfig()

        assert config.ticker == "SPX"  # SPX preferred for European-style
        assert config.strike_width == 50.0  # $50 width default
        assert config.mode == TradingMode.PAPER
        assert config.capital == 500000.0
        assert config.max_implied_rate == 6.0
        assert config.min_rate_advantage == 100  # 100 bps savings required

    def test_config_to_dict(self):
        """Test converting config to dictionary"""
        from trading.jubilee.models import JubileeConfig

        config = JubileeConfig()
        data = config.to_dict()

        assert data['ticker'] == "SPX"
        assert data['mode'] == "paper"
        assert 'allocations' in data
        assert data['allocations']['fortress_pct'] == 35.0
        assert data['allocations']['samson_pct'] == 35.0
        assert data['allocations']['anchor_pct'] == 20.0
        assert data['allocations']['reserve_pct'] == 10.0

    def test_config_from_dict(self):
        """Test creating config from dictionary"""
        from trading.jubilee.models import JubileeConfig, TradingMode

        data = {
            'mode': 'live',
            'ticker': 'SPX',
            'strike_width': 100.0,
            'capital': 1000000.0,
        }

        config = JubileeConfig.from_dict(data)

        assert config.mode == TradingMode.LIVE
        assert config.ticker == "SPX"
        assert config.strike_width == 100.0
        assert config.capital == 1000000.0

    def test_allocation_percentages_sum_to_100(self):
        """Test that default allocations sum to 100%"""
        from trading.jubilee.models import JubileeConfig

        config = JubileeConfig()

        total = (
            config.fortress_allocation_pct +
            config.samson_allocation_pct +
            config.anchor_allocation_pct +
            config.reserve_pct
        )
        assert total == 100.0


class TestBoxSpreadSignal:
    """Tests for BoxSpreadSignal model"""

    def test_signal_creation(self):
        """Test creating a box spread signal"""
        from trading.jubilee.models import BoxSpreadSignal

        signal = BoxSpreadSignal(
            signal_id="SIG-20250130-001",
            signal_time=datetime.now(),
            ticker="SPX",
            spot_price=5950.0,
            lower_strike=5900.0,
            upper_strike=5950.0,
            strike_width=50.0,
            expiration="2025-06-20",
            dte=141,
            theoretical_value=50.0,
            market_bid=49.50,
            market_ask=49.80,
            mid_price=49.65,
            cash_received=49650.0,  # 1 contract
            cash_owed_at_expiration=50000.0,
            borrowing_cost=350.0,
            implied_annual_rate=4.5,
            fed_funds_rate=4.5,
            margin_rate=8.0,
            rate_advantage=350,
            early_assignment_risk="LOW",
            assignment_risk_explanation="SPX is European-style",
            margin_requirement=5000.0,
            margin_pct_of_capital=1.0,
            recommended_contracts=10,
            total_cash_generated=496500.0,
            strategy_explanation="Synthetic borrowing via box spread",
            why_this_expiration="Quarterly expiration with good liquidity",
            why_these_strikes="Centered around current price",
        )

        assert signal.ticker == "SPX"
        assert signal.strike_width == 50.0
        assert signal.implied_annual_rate == 4.5
        assert signal.is_valid is True

    def test_signal_to_dict(self):
        """Test converting signal to dictionary"""
        from trading.jubilee.models import BoxSpreadSignal

        signal = BoxSpreadSignal(
            signal_id="SIG-20250130-001",
            signal_time=datetime.now(),
            ticker="SPX",
            spot_price=5950.0,
            lower_strike=5900.0,
            upper_strike=5950.0,
            strike_width=50.0,
            expiration="2025-06-20",
            dte=141,
            theoretical_value=50.0,
            market_bid=49.50,
            market_ask=49.80,
            mid_price=49.65,
            cash_received=49650.0,
            cash_owed_at_expiration=50000.0,
            borrowing_cost=350.0,
            implied_annual_rate=4.5,
            fed_funds_rate=4.5,
            margin_rate=8.0,
            rate_advantage=350,
            early_assignment_risk="LOW",
            assignment_risk_explanation="SPX is European-style",
            margin_requirement=5000.0,
            margin_pct_of_capital=1.0,
            recommended_contracts=10,
            total_cash_generated=496500.0,
            strategy_explanation="Synthetic borrowing via box spread",
            why_this_expiration="Quarterly expiration",
            why_these_strikes="Centered around current price",
        )

        data = signal.to_dict()

        assert data['signal_id'] == "SIG-20250130-001"
        assert data['ticker'] == "SPX"
        assert data['implied_annual_rate'] == 4.5
        assert data['is_valid'] is True


class TestBoxSpreadPosition:
    """Tests for BoxSpreadPosition model"""

    def test_position_creation(self):
        """Test creating a box spread position"""
        from trading.jubilee.models import BoxSpreadPosition, PositionStatus

        position = BoxSpreadPosition(
            position_id="PROM-SPX-20250130-001",
            ticker="SPX",
            lower_strike=5900.0,
            upper_strike=5950.0,
            strike_width=50.0,
            expiration="2025-06-20",
            dte_at_entry=141,
            current_dte=141,
            call_long_symbol="SPXW250620C05900000",
            call_short_symbol="SPXW250620C05950000",
            put_long_symbol="SPXW250620P05950000",
            put_short_symbol="SPXW250620P05900000",
            call_spread_order_id="ORD-001",
            put_spread_order_id="ORD-002",
            contracts=10,
            entry_credit=49.65,
            total_credit_received=49650.0,
            theoretical_value=50.0,
            total_owed_at_expiration=50000.0,
            borrowing_cost=350.0,
            implied_annual_rate=4.5,
            daily_cost=2.48,
            cost_accrued_to_date=0.0,
            fed_funds_at_entry=4.5,
            margin_rate_at_entry=8.0,
            savings_vs_margin=350.0,
            cash_deployed_to_fortress=17377.50,
            cash_deployed_to_samson=17377.50,
            cash_deployed_to_anchor=9930.0,
            cash_held_in_reserve=4965.0,
            total_cash_deployed=49650.0,
            returns_from_fortress=0.0,
            returns_from_samson=0.0,
            returns_from_anchor=0.0,
            total_ic_returns=0.0,
            net_profit=0.0,
            spot_at_entry=5950.0,
            vix_at_entry=16.5,
            early_assignment_risk="LOW",
            current_margin_used=5000.0,
            margin_cushion=245000.0,
            status=PositionStatus.OPEN,
            open_time=datetime.now(),
        )

        assert position.ticker == "SPX"
        assert position.contracts == 10
        assert position.status == PositionStatus.OPEN
        assert position.total_credit_received == 49650.0

    def test_position_to_dict(self):
        """Test converting position to dictionary"""
        from trading.jubilee.models import BoxSpreadPosition, PositionStatus

        position = BoxSpreadPosition(
            position_id="PROM-SPX-20250130-001",
            ticker="SPX",
            lower_strike=5900.0,
            upper_strike=5950.0,
            strike_width=50.0,
            expiration="2025-06-20",
            dte_at_entry=141,
            current_dte=141,
            call_long_symbol="",
            call_short_symbol="",
            put_long_symbol="",
            put_short_symbol="",
            call_spread_order_id="",
            put_spread_order_id="",
            contracts=10,
            entry_credit=49.65,
            total_credit_received=49650.0,
            theoretical_value=50.0,
            total_owed_at_expiration=50000.0,
            borrowing_cost=350.0,
            implied_annual_rate=4.5,
            daily_cost=2.48,
            cost_accrued_to_date=0.0,
            fed_funds_at_entry=4.5,
            margin_rate_at_entry=8.0,
            savings_vs_margin=350.0,
            cash_deployed_to_fortress=17377.50,
            cash_deployed_to_samson=17377.50,
            cash_deployed_to_anchor=9930.0,
            cash_held_in_reserve=4965.0,
            total_cash_deployed=49650.0,
            returns_from_fortress=0.0,
            returns_from_samson=0.0,
            returns_from_anchor=0.0,
            total_ic_returns=0.0,
            net_profit=0.0,
            spot_at_entry=5950.0,
            vix_at_entry=16.5,
            early_assignment_risk="LOW",
            current_margin_used=5000.0,
            margin_cushion=245000.0,
            status=PositionStatus.OPEN,
            open_time=datetime.now(),
        )

        data = position.to_dict()

        assert data['position_id'] == "PROM-SPX-20250130-001"
        assert data['status'] == "open"
        assert data['implied_annual_rate'] == 4.5


class TestOCCSymbolBuilder:
    """Tests for OCC symbol building functionality"""

    def test_build_occ_symbol_call(self):
        """Test building OCC symbol for a call option"""
        from trading.jubilee.executor import build_occ_symbol

        symbol = build_occ_symbol(
            underlying="SPX",
            expiration="2025-06-20",
            strike=5900.0,
            option_type="call"
        )

        assert symbol == "SPXW250620C05900000"

    def test_build_occ_symbol_put(self):
        """Test building OCC symbol for a put option"""
        from trading.jubilee.executor import build_occ_symbol

        symbol = build_occ_symbol(
            underlying="SPX",
            expiration="2025-06-20",
            strike=5900.0,
            option_type="put"
        )

        assert symbol == "SPXW250620P05900000"

    def test_build_occ_symbol_high_strike(self):
        """Test OCC symbol with high strike price"""
        from trading.jubilee.executor import build_occ_symbol

        symbol = build_occ_symbol(
            underlying="SPX",
            expiration="2025-06-20",
            strike=6000.0,
            option_type="call"
        )

        assert symbol == "SPXW250620C06000000"

    def test_build_occ_symbol_fractional_strike(self):
        """Test OCC symbol with fractional strike"""
        from trading.jubilee.executor import build_occ_symbol

        symbol = build_occ_symbol(
            underlying="SPX",
            expiration="2025-06-20",
            strike=5925.50,
            option_type="call"
        )

        # 5925.50 * 1000 = 5925500
        assert symbol == "SPXW250620C05925500"

    def test_build_occ_symbol_spx_to_spxw(self):
        """Test that SPX is converted to SPXW for weeklies"""
        from trading.jubilee.executor import build_occ_symbol

        symbol = build_occ_symbol(
            underlying="SPX",
            expiration="2025-03-15",
            strike=5800.0,
            option_type="put"
        )

        assert symbol.startswith("SPXW")
        assert "SPX2" not in symbol  # Should not have SPX directly


class TestImpliedRateCalculations:
    """Tests for implied borrowing rate calculations"""

    def test_calculate_implied_rate(self):
        """Test basic implied rate calculation"""
        # Box spread mechanics:
        # - Strike width: $50 (theoretical value = $5000 per contract)
        # - Credit received: $49.65 per share = $4965 per contract
        # - Borrowing cost: $5000 - $4965 = $35 per contract
        # - DTE: 141 days
        # - Annualized rate: (35 / 4965) * (365 / 141) * 100 = 1.82%

        strike_width = 50.0
        theoretical_value = strike_width * 100  # $5000
        credit_received = 49.65 * 100  # $4965
        borrowing_cost = theoretical_value - credit_received  # $35
        dte = 141

        annualized_rate = (borrowing_cost / credit_received) * (365 / dte) * 100

        # Should be approximately 1.82%
        assert 1.5 < annualized_rate < 2.5

    def test_rate_increases_with_lower_credit(self):
        """Test that lower credit means higher borrowing rate"""
        strike_width = 50.0
        theoretical_value = strike_width * 100  # $5000
        dte = 180

        high_credit = 49.80 * 100  # $4980
        low_credit = 49.00 * 100   # $4900

        high_credit_cost = theoretical_value - high_credit
        low_credit_cost = theoretical_value - low_credit

        high_credit_rate = (high_credit_cost / high_credit) * (365 / dte) * 100
        low_credit_rate = (low_credit_cost / low_credit) * (365 / dte) * 100

        # Lower credit should mean higher rate
        assert low_credit_rate > high_credit_rate

    def test_rate_decreases_with_longer_dte(self):
        """Test that longer DTE means lower annualized rate"""
        strike_width = 50.0
        theoretical_value = strike_width * 100  # $5000
        credit = 49.50 * 100  # $4950

        borrowing_cost = theoretical_value - credit

        short_dte = 90
        long_dte = 365

        short_rate = (borrowing_cost / credit) * (365 / short_dte) * 100
        long_rate = (borrowing_cost / credit) * (365 / long_dte) * 100

        # Longer DTE should have lower annualized rate
        assert long_rate < short_rate


class TestPositionStatus:
    """Tests for PositionStatus enum"""

    def test_position_status_values(self):
        """Test all position status values exist"""
        from trading.jubilee.models import PositionStatus

        assert PositionStatus.PENDING.value == "pending"
        assert PositionStatus.OPEN.value == "open"
        assert PositionStatus.CLOSING.value == "closing"
        assert PositionStatus.CLOSED.value == "closed"
        assert PositionStatus.EXPIRED.value == "expired"
        assert PositionStatus.ROLLED.value == "rolled"
        assert PositionStatus.ASSIGNMENT_RISK.value == "assignment_risk"


class TestBoxSpreadStatus:
    """Tests for BoxSpreadStatus enum"""

    def test_box_spread_status_values(self):
        """Test all system status values exist"""
        from trading.jubilee.models import BoxSpreadStatus

        assert BoxSpreadStatus.ACTIVE.value == "active"
        assert BoxSpreadStatus.PAUSED.value == "paused"
        assert BoxSpreadStatus.MARGIN_WARNING.value == "margin_warning"
        assert BoxSpreadStatus.ASSIGNMENT_ALERT.value == "assignment_alert"
        assert BoxSpreadStatus.RATE_UNFAVORABLE.value == "rate_unfavorable"


class TestTradingMode:
    """Tests for TradingMode enum"""

    def test_trading_mode_values(self):
        """Test trading mode values"""
        from trading.jubilee.models import TradingMode

        assert TradingMode.PAPER.value == "paper"
        assert TradingMode.LIVE.value == "live"


class TestJubileeDatabase:
    """Tests for JUBILEE database operations"""

    def test_database_import(self):
        """Test that database module can be imported"""
        try:
            from trading.jubilee.db import JubileeDatabase
            assert JubileeDatabase is not None
        except ImportError:
            pytest.skip("JubileeDatabase not available")

    def test_database_initialization(self):
        """Test database initialization"""
        try:
            from trading.jubilee.db import JubileeDatabase

            with patch('database_adapter.get_connection', return_value=MagicMock()):
                db = JubileeDatabase()
                assert db is not None
        except ImportError:
            pytest.skip("JubileeDatabase not available")


class TestJubileeTrader:
    """Tests for JUBILEE trader"""

    def test_trader_import(self):
        """Test that trader can be imported"""
        try:
            from trading.jubilee.trader import JubileeTrader
            assert JubileeTrader is not None
        except ImportError:
            pytest.skip("JubileeTrader not available")


class TestCapitalDeployment:
    """Tests for CapitalDeployment model"""

    def test_deployment_creation(self):
        """Test creating a capital deployment"""
        from trading.jubilee.models import CapitalDeployment

        deployment = CapitalDeployment(
            deployment_id="DEP-001",
            deployment_time=datetime.now(),
            source_box_position_id="PROM-SPX-20250130-001",
            total_capital_available=100000.0,
            fortress_allocation=35000.0,
            fortress_allocation_pct=35.0,
            fortress_allocation_reasoning="Highest historical performance",
            samson_allocation=35000.0,
            samson_allocation_pct=35.0,
            samson_allocation_reasoning="Strong SPX performance",
            anchor_allocation=20000.0,
            anchor_allocation_pct=20.0,
            anchor_allocation_reasoning="Weekly coverage",
            reserve_amount=10000.0,
            reserve_pct=10.0,
            reserve_reasoning="Buffer for margin calls",
            allocation_method="PERFORMANCE_WEIGHTED",
            methodology_explanation="Based on 30-day performance",
            fortress_returns_to_date=0.0,
            samson_returns_to_date=0.0,
            anchor_returns_to_date=0.0,
            total_returns_to_date=0.0,
            is_active=True,
        )

        assert deployment.total_capital_available == 100000.0
        assert deployment.fortress_allocation == 35000.0
        assert deployment.is_active is True

    def test_deployment_to_dict(self):
        """Test converting deployment to dictionary"""
        from trading.jubilee.models import CapitalDeployment

        deployment = CapitalDeployment(
            deployment_id="DEP-001",
            deployment_time=datetime.now(),
            source_box_position_id="PROM-SPX-20250130-001",
            total_capital_available=100000.0,
            fortress_allocation=35000.0,
            fortress_allocation_pct=35.0,
            fortress_allocation_reasoning="",
            samson_allocation=35000.0,
            samson_allocation_pct=35.0,
            samson_allocation_reasoning="",
            anchor_allocation=20000.0,
            anchor_allocation_pct=20.0,
            anchor_allocation_reasoning="",
            reserve_amount=10000.0,
            reserve_pct=10.0,
            reserve_reasoning="",
            allocation_method="EQUAL",
            methodology_explanation="",
            fortress_returns_to_date=0.0,
            samson_returns_to_date=0.0,
            anchor_returns_to_date=0.0,
            total_returns_to_date=0.0,
            is_active=True,
        )

        data = deployment.to_dict()

        assert data['deployment_id'] == "DEP-001"
        assert 'allocations' in data
        assert data['allocations']['fortress']['amount'] == 35000.0


class TestBorrowingCostAnalysis:
    """Tests for BorrowingCostAnalysis model"""

    def test_analysis_creation(self):
        """Test creating a borrowing cost analysis"""
        from trading.jubilee.models import BorrowingCostAnalysis

        analysis = BorrowingCostAnalysis(
            analysis_time=datetime.now(),
            box_implied_rate=4.5,
            fed_funds_rate=4.5,
            sofr_rate=4.3,
            broker_margin_rate=8.0,
            spread_to_fed_funds=0.0,
            spread_to_margin=-3.5,
            cost_per_100k_monthly=375.0,
            cost_per_100k_annual=4500.0,
            required_ic_return_monthly=0.375,
            current_ic_return_estimate=3.0,
            projected_profit_per_100k=31500.0,
            avg_box_rate_30d=4.4,
            avg_box_rate_90d=4.6,
            rate_trend="STABLE",
            is_favorable=True,
            recommendation="Proceed with box spread",
            reasoning="Rate is favorable vs margin",
        )

        assert analysis.box_implied_rate == 4.5
        assert analysis.is_favorable is True
        assert analysis.spread_to_margin == -3.5  # Negative = savings


class TestRollDecision:
    """Tests for RollDecision model"""

    def test_roll_decision_creation(self):
        """Test creating a roll decision"""
        from trading.jubilee.models import RollDecision

        decision = RollDecision(
            decision_time=datetime.now(),
            current_position_id="PROM-SPX-20250130-001",
            current_expiration="2025-03-20",
            current_dte=25,
            current_implied_rate=4.8,
            target_expiration="2025-06-20",
            target_dte=117,
            target_implied_rate=4.5,
            roll_cost=50.0,
            rate_improvement=-0.3,
            total_borrowing_extension=92,
            should_roll=True,
            decision_reasoning="DTE < 30 and better rate available",
        )

        assert decision.should_roll is True
        assert decision.rate_improvement == -0.3  # Negative = better


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
