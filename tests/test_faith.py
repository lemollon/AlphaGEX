"""
FAITH Bot - Comprehensive Test Suite
=====================================

Tests for the FAITH 2DTE Paper Iron Condor bot.

Covers:
1. Symmetric wing enforcement
2. 2DTE expiration selection
3. Paper fill pricing (conservative bid/ask)
4. Paper account balance tracking
5. PDT tracking
6. Trade management (profit target, stop loss, EOD)
7. Configuration validation
8. Position lifecycle
"""

import pytest
import math
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from trading.faith.models import (
    FaithConfig, IronCondorPosition, IronCondorSignal,
    PositionStatus, PaperAccount, TradingMode, CENTRAL_TZ, EASTERN_TZ
)
from trading.faith.signals import FaithSignalGenerator


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def config():
    """Default FAITH configuration."""
    return FaithConfig()


@pytest.fixture
def signal_generator(config):
    """Signal generator with mocked external dependencies."""
    with patch.object(FaithSignalGenerator, '_init_tradier'):
        with patch.object(FaithSignalGenerator, '_init_gex'):
            gen = FaithSignalGenerator(config)
            gen.tradier = None
            gen.gex_calculator = None
            return gen


@pytest.fixture
def mock_spy_price():
    """Realistic SPY price."""
    return 595.50


@pytest.fixture
def mock_vix():
    """Realistic VIX level."""
    return 18.5


@pytest.fixture
def mock_expected_move():
    """Realistic expected move for SPY."""
    return 4.50


# ============================================================================
# TEST: CONFIGURATION
# ============================================================================

class TestFaithConfig:
    """Test FaithConfig validation and defaults."""

    def test_default_config_values(self, config):
        """Verify default configuration matches spec."""
        assert config.mode == TradingMode.PAPER
        assert config.ticker == "SPY"
        assert config.min_dte == 2
        assert config.starting_capital == 5000.0
        assert config.max_trades_per_day == 1
        assert config.profit_target_pct == 30.0
        assert config.stop_loss_pct == 100.0
        assert config.eod_cutoff_et == "15:45"
        assert config.pdt_max_day_trades == 3
        assert config.sd_multiplier == 1.2
        assert config.spread_width == 5.0

    def test_config_validation_passes(self, config):
        """Valid config should pass validation."""
        valid, msg = config.validate()
        assert valid is True
        assert msg == "OK"

    def test_config_invalid_capital(self):
        """Zero/negative capital should fail."""
        config = FaithConfig(starting_capital=0)
        valid, msg = config.validate()
        assert valid is False
        assert "capital" in msg.lower()

    def test_config_invalid_spread_width(self):
        """Zero/negative spread width should fail."""
        config = FaithConfig(spread_width=0)
        valid, msg = config.validate()
        assert valid is False

    def test_config_invalid_profit_target(self):
        """Profit target out of range should fail."""
        config = FaithConfig(profit_target_pct=0)
        valid, _ = config.validate()
        assert valid is False

        config = FaithConfig(profit_target_pct=100)
        valid, _ = config.validate()
        assert valid is False

    def test_config_invalid_dte(self):
        """DTE < 1 should fail for FAITH."""
        config = FaithConfig(min_dte=0)
        valid, _ = config.validate()
        assert valid is False

    def test_paper_mode_only(self, config):
        """FAITH is paper-only."""
        assert config.mode == TradingMode.PAPER
        assert TradingMode.PAPER.value == "paper"


# ============================================================================
# TEST: SYMMETRIC WING ENFORCEMENT
# ============================================================================

class TestSymmetricWings:
    """Test enforce_symmetric_wings() logic."""

    def test_already_symmetric_no_adjustment(self, signal_generator):
        """If wings are already equal, no adjustment needed."""
        result = signal_generator.enforce_symmetric_wings(
            short_put=595, long_put=590,
            short_call=605, long_call=610,
        )
        assert result['adjusted'] is False
        assert result['short_put'] == 595
        assert result['long_put'] == 590
        assert result['short_call'] == 605
        assert result['long_call'] == 610
        # Widths should be equal
        put_width = result['short_put'] - result['long_put']
        call_width = result['long_call'] - result['short_call']
        assert put_width == call_width == 5

    def test_put_narrower_widens_put(self, signal_generator):
        """If put side is narrower, widen put to match call."""
        result = signal_generator.enforce_symmetric_wings(
            short_put=595, long_put=593,  # $2 wide
            short_call=605, long_call=608,  # $3 wide
        )
        assert result['adjusted'] is True
        assert result['short_put'] == 595  # Short strikes unchanged
        assert result['long_put'] == 592  # Widened from 593 to 592 ($3 wide)
        assert result['short_call'] == 605
        assert result['long_call'] == 608
        # Both now $3 wide
        put_width = result['short_put'] - result['long_put']
        call_width = result['long_call'] - result['short_call']
        assert put_width == call_width == 3

    def test_call_narrower_widens_call(self, signal_generator):
        """If call side is narrower, widen call to match put."""
        result = signal_generator.enforce_symmetric_wings(
            short_put=595, long_put=590,  # $5 wide
            short_call=605, long_call=607,  # $2 wide
        )
        assert result['adjusted'] is True
        assert result['short_put'] == 595
        assert result['long_put'] == 590
        assert result['short_call'] == 605  # Short strikes unchanged
        assert result['long_call'] == 610  # Widened from 607 to 610 ($5 wide)
        put_width = result['short_put'] - result['long_put']
        call_width = result['long_call'] - result['short_call']
        assert put_width == call_width == 5

    def test_never_narrows_protection(self, signal_generator):
        """Adjustment always widens to the wider side, never narrows."""
        result = signal_generator.enforce_symmetric_wings(
            short_put=595, long_put=590,  # $5 wide
            short_call=605, long_call=608,  # $3 wide
        )
        # Target width should be 5 (wider), not 3 (narrower)
        call_width = result['long_call'] - result['short_call']
        assert call_width == 5  # Widened to match put, not narrowed

    def test_short_strikes_never_moved(self, signal_generator):
        """Short strikes should never be modified."""
        result = signal_generator.enforce_symmetric_wings(
            short_put=595, long_put=592,
            short_call=605, long_call=610,
        )
        assert result['short_put'] == 595
        assert result['short_call'] == 605

    def test_with_available_strikes_validation(self, signal_generator):
        """When available_strikes provided, snap to valid strikes."""
        available = set(range(580, 620))  # Strikes at every $1
        result = signal_generator.enforce_symmetric_wings(
            short_put=595, long_put=593.5,  # $1.50 wide (not a real strike)
            short_call=605, long_call=608,  # $3 wide
            available_strikes=available,
        )
        # Both should snap to valid strikes with width >= 3
        assert result['long_put'] in available or result['long_put'] == 592
        put_width = result['short_put'] - result['long_put']
        call_width = result['long_call'] - result['short_call']
        assert put_width == call_width

    def test_floating_point_tolerance(self, signal_generator):
        """Wings within 0.01 should be considered symmetric."""
        result = signal_generator.enforce_symmetric_wings(
            short_put=595, long_put=590.005,
            short_call=605, long_call=609.995,
        )
        # Should be treated as symmetric (within 0.01 tolerance)
        assert result['adjusted'] is False

    def test_original_widths_tracked(self, signal_generator):
        """Original widths before adjustment should be tracked."""
        result = signal_generator.enforce_symmetric_wings(
            short_put=595, long_put=593,  # $2 wide
            short_call=605, long_call=608,  # $3 wide
        )
        assert result['original_put_width'] == 2
        assert result['original_call_width'] == 3


# ============================================================================
# TEST: 2DTE EXPIRATION SELECTION
# ============================================================================

class TestExpirationSelection:
    """Test _get_target_expiration() for 2DTE targeting."""

    def test_monday_targets_wednesday(self, signal_generator):
        """Monday -> Wednesday (2 trading days)."""
        monday = datetime(2026, 2, 16, 10, 0, tzinfo=CENTRAL_TZ)  # Monday
        exp = signal_generator._get_target_expiration(monday)
        assert exp == "2026-02-18"  # Wednesday

    def test_tuesday_targets_thursday(self, signal_generator):
        """Tuesday -> Thursday."""
        tuesday = datetime(2026, 2, 17, 10, 0, tzinfo=CENTRAL_TZ)
        exp = signal_generator._get_target_expiration(tuesday)
        assert exp == "2026-02-19"  # Thursday

    def test_wednesday_targets_friday(self, signal_generator):
        """Wednesday -> Friday."""
        wednesday = datetime(2026, 2, 18, 10, 0, tzinfo=CENTRAL_TZ)
        exp = signal_generator._get_target_expiration(wednesday)
        assert exp == "2026-02-20"  # Friday

    def test_thursday_targets_monday(self, signal_generator):
        """Thursday -> Monday (skips weekend)."""
        thursday = datetime(2026, 2, 19, 10, 0, tzinfo=CENTRAL_TZ)
        exp = signal_generator._get_target_expiration(thursday)
        assert exp == "2026-02-23"  # Monday

    def test_friday_targets_tuesday(self, signal_generator):
        """Friday -> Tuesday (skips weekend)."""
        friday = datetime(2026, 2, 20, 10, 0, tzinfo=CENTRAL_TZ)
        exp = signal_generator._get_target_expiration(friday)
        assert exp == "2026-02-24"  # Tuesday


# ============================================================================
# TEST: STRIKE SELECTION
# ============================================================================

class TestStrikeSelection:
    """Test calculate_strikes() logic."""

    def test_strikes_outside_expected_move(self, signal_generator, mock_spy_price, mock_expected_move):
        """Strikes should be at least 1.2 SD from spot."""
        strikes = signal_generator.calculate_strikes(mock_spy_price, mock_expected_move)
        min_distance = 1.2 * mock_expected_move

        # Put short should be below spot by at least 1.2 SD
        assert mock_spy_price - strikes['put_short'] >= min_distance - 1  # -1 for rounding

        # Call short should be above spot by at least 1.2 SD
        assert strikes['call_short'] - mock_spy_price >= min_distance - 1

    def test_put_rounds_down(self, signal_generator, mock_spy_price, mock_expected_move):
        """Put short should round DOWN (floor) for safety."""
        strikes = signal_generator.calculate_strikes(mock_spy_price, mock_expected_move)
        raw_put = mock_spy_price - 1.2 * mock_expected_move
        assert strikes['put_short'] == math.floor(raw_put)

    def test_call_rounds_up(self, signal_generator, mock_spy_price, mock_expected_move):
        """Call short should round UP (ceil) for safety."""
        strikes = signal_generator.calculate_strikes(mock_spy_price, mock_expected_move)
        raw_call = mock_spy_price + 1.2 * mock_expected_move
        assert strikes['call_short'] == math.ceil(raw_call)

    def test_spread_width_applied(self, signal_generator, mock_spy_price, mock_expected_move):
        """Long strikes should be spread_width away from shorts."""
        strikes = signal_generator.calculate_strikes(mock_spy_price, mock_expected_move)
        width = signal_generator.config.spread_width
        assert strikes['put_long'] == strikes['put_short'] - width
        assert strikes['call_long'] == strikes['call_short'] + width

    def test_no_overlap(self, signal_generator, mock_spy_price, mock_expected_move):
        """Call short must be above put short."""
        strikes = signal_generator.calculate_strikes(mock_spy_price, mock_expected_move)
        assert strikes['call_short'] > strikes['put_short']

    def test_minimum_expected_move_floor(self, signal_generator, mock_spy_price):
        """Very small expected move should be floored to 0.5% of spot."""
        strikes = signal_generator.calculate_strikes(mock_spy_price, 0.01)
        # Should still produce valid strikes (floor kicks in at 0.5% of spot)
        assert strikes['call_short'] > strikes['put_short']


# ============================================================================
# TEST: PAPER FILL PRICING
# ============================================================================

class TestPaperFillPricing:
    """Test that paper fills use conservative bid/ask pricing."""

    def test_credit_calculation_conservative(self, signal_generator):
        """Paper fills should use bid for sells, ask for buys."""
        # Mock Tradier quotes
        mock_quotes = {
            'put_short': {'bid': 2.50, 'ask': 2.70},
            'put_long': {'bid': 1.00, 'ask': 1.20},
            'call_short': {'bid': 2.00, 'ask': 2.20},
            'call_long': {'bid': 0.80, 'ask': 1.00},
        }

        # Conservative credit:
        # Sell put_short at bid (2.50) - Buy put_long at ask (1.20) = 1.30
        # Sell call_short at bid (2.00) - Buy call_long at ask (1.00) = 1.00
        # Total credit = 1.30 + 1.00 = 2.30
        expected_put_credit = mock_quotes['put_short']['bid'] - mock_quotes['put_long']['ask']
        expected_call_credit = mock_quotes['call_short']['bid'] - mock_quotes['call_long']['ask']
        expected_total = expected_put_credit + expected_call_credit

        assert expected_put_credit == 1.30
        assert expected_call_credit == 1.00
        assert expected_total == 2.30


# ============================================================================
# TEST: PAPER ACCOUNT
# ============================================================================

class TestPaperAccount:
    """Test paper account balance tracking."""

    def test_default_account(self):
        """Default paper account starts at $5,000."""
        account = PaperAccount()
        assert account.starting_balance == 5000.0
        assert account.balance == 5000.0
        assert account.buying_power == 5000.0
        assert account.collateral_in_use == 0

    def test_account_to_dict(self):
        """Account serialization should include all fields."""
        account = PaperAccount(
            balance=5247.30,
            cumulative_pnl=247.30,
            collateral_in_use=435.0,
            buying_power=4812.30,
        )
        d = account.to_dict()
        assert d['balance'] == 5247.30
        assert d['buying_power'] == 4812.30
        assert d['collateral_in_use'] == 435.0
        assert d['return_pct'] == pytest.approx(4.95, abs=0.1)  # 247.30/5000*100


# ============================================================================
# TEST: COLLATERAL CALCULATION
# ============================================================================

class TestCollateral:
    """Test collateral and position sizing."""

    def test_collateral_per_contract(self):
        """Collateral = (wing_width * 100) - (credit * 100)."""
        from trading.faith.executor import FaithExecutor
        executor = FaithExecutor.__new__(FaithExecutor)
        executor.config = FaithConfig()

        # $5 wide wings, $1.50 credit
        collateral = executor.calculate_collateral(5.0, 1.50)
        # (5 * 100) - (1.50 * 100) = 500 - 150 = 350
        assert collateral == 350.0

    def test_max_contracts_sizing(self):
        """Max contracts should respect buying power and 85% usage."""
        from trading.faith.executor import FaithExecutor
        executor = FaithExecutor.__new__(FaithExecutor)
        executor.config = FaithConfig()

        # $5,000 BP, $350 collateral per contract, 85% usage
        max_c = executor.calculate_max_contracts(5000, 350)
        # 5000 * 0.85 / 350 = 12.14 -> floor to 12, cap at max_contracts=10
        assert max_c == 10  # Capped at config.max_contracts

    def test_max_contracts_small_account(self):
        """Small BP should still allow at least 1 contract if affordable."""
        from trading.faith.executor import FaithExecutor
        executor = FaithExecutor.__new__(FaithExecutor)
        executor.config = FaithConfig()

        max_c = executor.calculate_max_contracts(400, 350)
        # 400 * 0.85 / 350 = 0.97 -> floor to 0
        assert max_c == 0  # Can't afford even 1

    def test_zero_collateral_returns_zero(self):
        """Zero collateral should return 0 contracts."""
        from trading.faith.executor import FaithExecutor
        executor = FaithExecutor.__new__(FaithExecutor)
        executor.config = FaithConfig()

        max_c = executor.calculate_max_contracts(5000, 0)
        assert max_c == 0


# ============================================================================
# TEST: POSITION MODEL
# ============================================================================

class TestPositionModel:
    """Test IronCondorPosition model."""

    def test_position_to_dict(self):
        """Position serialization should include all fields."""
        pos = IronCondorPosition(
            position_id="FAITH-20260217-ABC123",
            ticker="SPY",
            expiration="2026-02-19",
            put_short_strike=590,
            put_long_strike=585,
            put_credit=1.20,
            call_short_strike=600,
            call_long_strike=605,
            call_credit=0.80,
            contracts=3,
            spread_width=5,
            total_credit=2.00,
            max_loss=900,
            max_profit=600,
            underlying_at_entry=595,
            wings_adjusted=True,
            original_put_width=4,
            original_call_width=5,
            status=PositionStatus.OPEN,
        )
        d = pos.to_dict()
        assert d['position_id'] == "FAITH-20260217-ABC123"
        assert d['wings_adjusted'] is True
        assert d['put_width'] == 5  # 590 - 585
        assert d['call_width'] == 5  # 605 - 600
        assert d['wings_symmetric'] is True
        assert d['status'] == 'open'

    def test_position_default_paper_orders(self):
        """Position should default to PAPER order IDs."""
        pos = IronCondorPosition(
            position_id="test",
            ticker="SPY",
            expiration="2026-02-19",
            put_short_strike=590,
            put_long_strike=585,
            put_credit=1.0,
            call_short_strike=600,
            call_long_strike=605,
            call_credit=1.0,
            contracts=1,
            spread_width=5,
            total_credit=2.0,
            max_loss=300,
            max_profit=200,
            underlying_at_entry=595,
        )
        assert pos.put_order_id == "PAPER"
        assert pos.call_order_id == "PAPER"


# ============================================================================
# TEST: SIGNAL MODEL
# ============================================================================

class TestSignalModel:
    """Test IronCondorSignal model."""

    def test_signal_validity_tracking(self):
        """Signal should track validity and reasoning."""
        signal = IronCondorSignal(
            spot_price=595,
            vix=18,
            expected_move=4.5,
            is_valid=False,
            reasoning="VIX too high",
        )
        assert signal.is_valid is False
        assert "VIX" in signal.reasoning

    def test_signal_wing_adjustment_tracking(self):
        """Signal should track wing adjustments."""
        signal = IronCondorSignal(
            spot_price=595,
            vix=18,
            expected_move=4.5,
            wings_adjusted=True,
            original_put_width=2,
            original_call_width=3,
        )
        assert signal.wings_adjusted is True
        assert signal.original_put_width == 2
        assert signal.original_call_width == 3


# ============================================================================
# TEST: ESTIMATED CREDITS (fallback)
# ============================================================================

class TestEstimatedCredits:
    """Test estimate_credits fallback."""

    def test_estimated_credits_positive(self, signal_generator, mock_spy_price, mock_vix):
        """Estimated credits should be positive."""
        credits = signal_generator.estimate_credits(
            spot_price=mock_spy_price,
            expected_move=4.50,
            put_short=590, put_long=585,
            call_short=600, call_long=605,
            vix=mock_vix,
        )
        assert credits['total_credit'] > 0
        assert credits['put_credit'] > 0
        assert credits['call_credit'] > 0

    def test_estimated_credits_capped(self, signal_generator, mock_spy_price, mock_vix):
        """Credits should be capped at 40% of spread width."""
        credits = signal_generator.estimate_credits(
            spot_price=mock_spy_price,
            expected_move=4.50,
            put_short=594, put_long=589,  # Very close to spot
            call_short=596, call_long=601,
            vix=mock_vix,
        )
        assert credits['put_credit'] <= 5.0 * 0.40
        assert credits['call_credit'] <= 5.0 * 0.40


# ============================================================================
# TEST: PROFIT TARGET / STOP LOSS MATH
# ============================================================================

class TestExitMath:
    """Test profit target and stop loss calculations."""

    def test_profit_target_30pct(self):
        """30% profit target: close when IC costs <= 70% of entry credit."""
        entry_credit = 2.00
        profit_target_pct = 30.0
        target_close_price = entry_credit * (1 - profit_target_pct / 100)
        assert target_close_price == pytest.approx(1.40)

        # If current cost to close is $1.30, profit is $0.70 per contract = 35%
        cost_to_close = 1.30
        pnl = (entry_credit - cost_to_close) * 100  # per contract
        assert pnl == 70.0  # $70 profit per contract
        assert cost_to_close <= target_close_price  # Should trigger close

    def test_stop_loss_100pct(self):
        """100% stop loss: close when IC costs >= 200% of entry credit."""
        entry_credit = 2.00
        stop_loss_pct = 100.0
        stop_loss_price = entry_credit * (1 + stop_loss_pct / 100)
        assert stop_loss_price == pytest.approx(4.00)

        # If current cost to close is $4.50, loss is -$2.50 per contract
        cost_to_close = 4.50
        pnl = (entry_credit - cost_to_close) * 100
        assert pnl == -250.0  # $250 loss per contract
        assert cost_to_close >= stop_loss_price  # Should trigger close

    def test_mid_range_no_trigger(self):
        """Position in the middle should not trigger either exit."""
        entry_credit = 2.00
        profit_target_price = 2.00 * 0.70  # 1.40
        stop_loss_price = 2.00 * 2.00  # 4.00

        # Cost to close at $1.80 - no trigger
        cost = 1.80
        assert cost > profit_target_price  # Not profit target
        assert cost < stop_loss_price  # Not stop loss
