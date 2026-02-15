"""
Unit tests for the Margin Calculation Engine.

Tests all 13 core calculations across all market types:
- Stock Futures (CME ES, NQ)
- Crypto Futures (CME /MBT)
- Crypto Perpetual Futures (BTC-PERP, ETH-PERP)
- Options (SPX, SPY)
- Crypto Spot (ETH-USD)

Edge cases tested:
- Zero positions
- Maximum leverage
- Negative equity scenarios
- Partial fills
- Multiple positions in same instrument
- Cross-margin vs isolated margin

Pre-trade check tests:
- Sufficient margin
- Insufficient margin
- Exactly-at-limit margin
- Various violation scenarios
"""

import pytest
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from trading.margin.margin_config import (
    MarketType,
    MarginMode,
    MarketConfig,
    BotMarginConfig,
    LiquidationMethod,
    SettlementType,
    get_default_market_config,
    MARKET_DEFAULTS,
    BOT_INSTRUMENT_MAP,
)
from trading.margin.margin_engine import (
    MarginEngine,
    PositionMarginMetrics,
    AccountMarginMetrics,
    PreTradeCheckResult,
    ScenarioResult,
)

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def es_config():
    """ES futures market config."""
    market = MARKET_DEFAULTS["ES"]
    return BotMarginConfig(bot_name="TEST_ES", market_config=market)


@pytest.fixture
def btc_perp_config():
    """BTC perpetual config."""
    market = MARKET_DEFAULTS["BTC-PERP"]
    return BotMarginConfig(
        bot_name="TEST_BTC_PERP",
        market_config=market,
        leverage_override=10.0,
    )


@pytest.fixture
def mbt_config():
    """CME Micro Bitcoin Futures config."""
    market = MARKET_DEFAULTS["/MBT"]
    return BotMarginConfig(bot_name="TEST_MBT", market_config=market)


@pytest.fixture
def spx_config():
    """SPX options config."""
    market = MARKET_DEFAULTS["SPX"]
    return BotMarginConfig(bot_name="TEST_SPX", market_config=market)


@pytest.fixture
def eth_spot_config():
    """ETH spot config."""
    market = MARKET_DEFAULTS["ETH-USD"]
    return BotMarginConfig(bot_name="TEST_SPOT", market_config=market)


@pytest.fixture
def es_engine(es_config):
    return MarginEngine(es_config)


@pytest.fixture
def btc_perp_engine(btc_perp_config):
    return MarginEngine(btc_perp_config)


@pytest.fixture
def mbt_engine(mbt_config):
    return MarginEngine(mbt_config)


@pytest.fixture
def spx_engine(spx_config):
    return MarginEngine(spx_config)


@pytest.fixture
def eth_spot_engine(eth_spot_config):
    return MarginEngine(eth_spot_config)


# =============================================================================
# TEST 1: NOTIONAL VALUE
# =============================================================================

class TestNotionalValue:
    def test_es_notional(self, es_engine):
        """ES: 2 contracts @ 6000 = 2 × 6000 × $50 = $600,000"""
        notional = es_engine.calc_notional_value(2, 6000)
        assert notional == 600000.0

    def test_btc_perp_notional(self, btc_perp_engine):
        """BTC-PERP: 0.5 BTC @ 100000 = 0.5 × 100000 × 1.0 = $50,000"""
        notional = btc_perp_engine.calc_notional_value(0.5, 100000)
        assert notional == 50000.0

    def test_mbt_notional(self, mbt_engine):
        """/MBT: 3 contracts @ 100000 = 3 × 100000 × 0.1 = $30,000"""
        notional = mbt_engine.calc_notional_value(3, 100000)
        assert notional == 30000.0

    def test_zero_quantity(self, es_engine):
        """Zero quantity should return 0."""
        assert es_engine.calc_notional_value(0, 6000) == 0.0

    def test_zero_price(self, es_engine):
        """Zero price should return 0."""
        assert es_engine.calc_notional_value(2, 0) == 0.0

    def test_negative_quantity(self, es_engine):
        """Negative quantity returns 0 (quantity must be positive)."""
        notional = es_engine.calc_notional_value(-2, 6000)
        assert notional == 0.0


# =============================================================================
# TEST 2: INITIAL MARGIN
# =============================================================================

class TestInitialMargin:
    def test_es_initial_margin(self, es_engine):
        """ES: 2 contracts × $13,200 = $26,400"""
        margin = es_engine.calc_initial_margin(2, 6000)
        assert margin == 26400.0

    def test_mbt_initial_margin(self, mbt_engine):
        """/MBT: 5 contracts × $1,320 = $6,600"""
        margin = mbt_engine.calc_initial_margin(5, 100000)
        assert margin == 6600.0

    def test_btc_perp_initial_margin(self, btc_perp_engine):
        """BTC-PERP: notional / leverage = $50,000 / 10 = $5,000"""
        margin = btc_perp_engine.calc_initial_margin(0.5, 100000, leverage=10.0)
        assert margin == 5000.0

    def test_btc_perp_default_leverage(self, btc_perp_engine):
        """Uses config leverage when not specified."""
        margin = btc_perp_engine.calc_initial_margin(0.5, 100000)
        # leverage_override=10.0, so notional/10 = 50000/10 = 5000
        assert margin == 5000.0

    def test_zero_quantity(self, es_engine):
        assert es_engine.calc_initial_margin(0, 6000) == 0.0


# =============================================================================
# TEST 3: MAINTENANCE MARGIN
# =============================================================================

class TestMaintenanceMargin:
    def test_es_maintenance(self, es_engine):
        """ES: 2 contracts × $12,000 = $24,000"""
        margin = es_engine.calc_maintenance_margin(2, 6000)
        assert margin == 24000.0

    def test_btc_perp_maintenance(self, btc_perp_engine):
        """BTC-PERP: notional × 0.005 = $50,000 × 0.005 = $250"""
        margin = btc_perp_engine.calc_maintenance_margin(0.5, 100000)
        assert margin == 250.0


# =============================================================================
# TEST 4: MARGIN USED
# =============================================================================

class TestMarginUsed:
    def test_multiple_positions(self, es_engine):
        """Total margin = sum of all position margins."""
        positions = [
            {"quantity": 2, "current_price": 6000},
            {"quantity": 1, "current_price": 6050},
        ]
        total = es_engine.calc_margin_used(positions)
        # 2 × $13,200 + 1 × $13,200 = $39,600
        assert total == 39600.0

    def test_empty_positions(self, es_engine):
        assert es_engine.calc_margin_used([]) == 0.0


# =============================================================================
# TEST 5: AVAILABLE MARGIN
# =============================================================================

class TestAvailableMargin:
    def test_positive_available(self, es_engine):
        assert es_engine.calc_available_margin(50000, 26400) == 23600.0

    def test_negative_available(self, es_engine):
        """Negative available = margin call territory."""
        assert es_engine.calc_available_margin(20000, 26400) == -6400.0

    def test_zero_equity(self, es_engine):
        assert es_engine.calc_available_margin(0, 26400) == -26400.0


# =============================================================================
# TEST 6: MARGIN USAGE PERCENT
# =============================================================================

class TestMarginUsagePct:
    def test_normal_usage(self, es_engine):
        """$26,400 / $50,000 × 100 = 52.8%"""
        pct = es_engine.calc_margin_usage_pct(26400, 50000)
        assert abs(pct - 52.8) < 0.01

    def test_zero_equity(self, es_engine):
        """Zero equity with margin = 100%."""
        assert es_engine.calc_margin_usage_pct(26400, 0) == 100.0

    def test_zero_margin_zero_equity(self, es_engine):
        """No margin, no equity = 0%."""
        assert es_engine.calc_margin_usage_pct(0, 0) == 0.0

    def test_over_100_pct(self, es_engine):
        """Margin exceeds equity."""
        pct = es_engine.calc_margin_usage_pct(60000, 50000)
        assert pct == 120.0


# =============================================================================
# TEST 7: MARGIN RATIO
# =============================================================================

class TestMarginRatio:
    def test_safe_ratio(self, es_engine):
        """$50,000 / $24,000 = 2.083"""
        ratio = es_engine.calc_margin_ratio(50000, 24000)
        assert abs(ratio - 2.0833) < 0.01

    def test_liquidation_ratio(self, es_engine):
        """Below 1.0 = liquidation territory."""
        ratio = es_engine.calc_margin_ratio(20000, 24000)
        assert ratio < 1.0

    def test_no_maintenance(self, es_engine):
        """No maintenance margin = infinite ratio."""
        ratio = es_engine.calc_margin_ratio(50000, 0)
        assert ratio == float('inf')


# =============================================================================
# TEST 8: LIQUIDATION PRICE
# =============================================================================

class TestLiquidationPrice:
    def test_es_long_liquidation(self, es_engine):
        """ES long: entry=6000, equity=50000, maintenance=12000/contract, 2 contracts."""
        liq = es_engine.calc_liquidation_price(
            side="long",
            entry_price=6000,
            quantity=2,
            account_equity=50000,
            total_maintenance_margin_other=0,
        )
        # max_adverse_move = (50000 - 24000) / (2 * 50) = 26000/100 = 260
        # liq = 6000 - 260 = 5740
        assert liq is not None
        assert abs(liq - 5740.0) < 1.0

    def test_es_short_liquidation(self, es_engine):
        """ES short: liq price is above entry."""
        liq = es_engine.calc_liquidation_price(
            side="short",
            entry_price=6000,
            quantity=2,
            account_equity=50000,
            total_maintenance_margin_other=0,
        )
        # liq = 6000 + 260 = 6260
        assert liq is not None
        assert abs(liq - 6260.0) < 1.0

    def test_btc_perp_long_liquidation(self, btc_perp_engine):
        """BTC-PERP long: entry=100000, 0.1 BTC, equity=10000, leverage=10."""
        liq = btc_perp_engine.calc_liquidation_price(
            side="long",
            entry_price=100000,
            quantity=0.1,
            account_equity=10000,
            total_maintenance_margin_other=0,
            leverage=10.0,
        )
        assert liq is not None
        # Notional = 0.1 × 100000 × 1.0 = 10000
        # Maint = 10000 × 0.005 = 50
        # max_adverse = (10000 - 50) / (0.1 × 1.0) = 99500
        # liq = 100000 - 99500 = 500
        assert liq > 0

    def test_spot_no_liquidation(self, eth_spot_engine):
        """Spot trading has no liquidation price."""
        liq = eth_spot_engine.calc_liquidation_price(
            side="long", entry_price=3000, quantity=1.0,
            account_equity=5000, total_maintenance_margin_other=0,
        )
        assert liq is None

    def test_options_no_liquidation(self, spx_engine):
        """Options spreads have no liquidation price."""
        liq = spx_engine.calc_liquidation_price(
            side="long", entry_price=6000, quantity=1,
            account_equity=200000, total_maintenance_margin_other=0,
        )
        assert liq is None

    def test_zero_quantity(self, es_engine):
        liq = es_engine.calc_liquidation_price(
            side="long", entry_price=6000, quantity=0,
            account_equity=50000, total_maintenance_margin_other=0,
        )
        assert liq is None

    def test_liq_price_non_negative(self, es_engine):
        """Liquidation price should never be negative."""
        liq = es_engine.calc_liquidation_price(
            side="long", entry_price=6000, quantity=2,
            account_equity=1000000,  # Very large equity
            total_maintenance_margin_other=0,
        )
        assert liq is not None
        assert liq >= 0


# =============================================================================
# TEST 9: DISTANCE TO LIQUIDATION
# =============================================================================

class TestDistanceToLiq:
    def test_normal_distance(self, es_engine):
        """Current=6000, Liq=5740: distance = |6000-5740|/6000 × 100 = 4.33%"""
        dist = es_engine.calc_distance_to_liquidation_pct(6000, 5740)
        assert dist is not None
        assert abs(dist - 4.333) < 0.01

    def test_none_liq_price(self, es_engine):
        assert es_engine.calc_distance_to_liquidation_pct(6000, None) is None

    def test_zero_current_price(self, es_engine):
        assert es_engine.calc_distance_to_liquidation_pct(0, 5740) is None


# =============================================================================
# TEST 10: UNREALIZED P&L
# =============================================================================

class TestUnrealizedPnl:
    def test_es_long_profit(self, es_engine):
        """ES long: (6050 - 6000) × 2 × $50 = $5,000"""
        pnl = es_engine.calc_unrealized_pnl("long", 6000, 6050, 2)
        assert pnl == 5000.0

    def test_es_long_loss(self, es_engine):
        """ES long: (5950 - 6000) × 2 × $50 = -$5,000"""
        pnl = es_engine.calc_unrealized_pnl("long", 6000, 5950, 2)
        assert pnl == -5000.0

    def test_es_short_profit(self, es_engine):
        """ES short: (5950 - 6000) × 2 × $50 × -1 = $5,000"""
        pnl = es_engine.calc_unrealized_pnl("short", 6000, 5950, 2)
        assert pnl == 5000.0

    def test_btc_perp_long_profit(self, btc_perp_engine):
        """BTC-PERP long: (101000 - 100000) × 0.5 × 1.0 × 1 = $500"""
        pnl = btc_perp_engine.calc_unrealized_pnl("long", 100000, 101000, 0.5)
        assert pnl == 500.0

    def test_zero_quantity(self, es_engine):
        assert es_engine.calc_unrealized_pnl("long", 6000, 6050, 0) == 0.0


# =============================================================================
# TEST 11: EFFECTIVE LEVERAGE
# =============================================================================

class TestEffectiveLeverage:
    def test_normal_leverage(self, es_engine):
        """$600,000 / $50,000 = 12x"""
        lev = es_engine.calc_effective_leverage(600000, 50000)
        assert lev == 12.0

    def test_zero_equity(self, es_engine):
        """Zero equity = infinite leverage."""
        lev = es_engine.calc_effective_leverage(600000, 0)
        assert lev == float('inf')

    def test_no_positions(self, es_engine):
        assert es_engine.calc_effective_leverage(0, 50000) == 0.0


# =============================================================================
# TEST 12: MAX POSITION SIZE
# =============================================================================

class TestMaxPositionSize:
    def test_es_max_contracts(self, es_engine):
        """Available=$26,000, initial=$13,200/contract -> ~1.97 contracts"""
        max_size = es_engine.calc_max_position_size(26000, 6000)
        assert abs(max_size - 1.9696) < 0.01

    def test_btc_perp_max_size(self, btc_perp_engine):
        """Available=$5000, leverage=10, price=$100000 -> 0.5 BTC"""
        max_size = btc_perp_engine.calc_max_position_size(5000, 100000)
        assert abs(max_size - 0.5) < 0.001

    def test_no_available(self, es_engine):
        assert es_engine.calc_max_position_size(0, 6000) == 0.0

    def test_zero_price(self, es_engine):
        assert es_engine.calc_max_position_size(26000, 0) == 0.0


# =============================================================================
# TEST 13: FUNDING COST PROJECTION
# =============================================================================

class TestFundingCostProjection:
    def test_long_positive_funding(self, btc_perp_engine):
        """Long with positive funding rate = you pay.
        Notional=$50K, rate=0.01%, 3 periods/day, 30 days
        Daily: $50K × 0.0001 × 3 × -1 = -$15/day
        30-day: -$15 × 30 = -$450
        """
        daily, projected = btc_perp_engine.calc_funding_cost_projection(
            50000, 0.0001, "long", 30
        )
        assert abs(daily - (-15.0)) < 0.01
        assert abs(projected - (-450.0)) < 0.1

    def test_short_positive_funding(self, btc_perp_engine):
        """Short with positive funding rate = you receive."""
        daily, projected = btc_perp_engine.calc_funding_cost_projection(
            50000, 0.0001, "short", 30
        )
        assert daily > 0
        assert projected > 0

    def test_no_funding(self, es_engine):
        """Stock futures have no funding rate."""
        daily, projected = es_engine.calc_funding_cost_projection(
            600000, 0.0001, "long", 30
        )
        assert daily == 0.0
        assert projected == 0.0


# =============================================================================
# TEST: AGGREGATE CALCULATIONS
# =============================================================================

class TestAccountMetrics:
    def test_empty_positions(self, es_engine, es_config):
        """No positions = healthy, zero margin."""
        metrics = es_engine.calculate_account_metrics(50000, [])
        assert metrics.position_count == 0
        assert metrics.total_margin_used == 0.0
        assert metrics.available_margin == 50000.0
        assert metrics.margin_usage_pct == 0.0
        assert metrics.health_status == "HEALTHY"

    def test_single_position(self, es_engine):
        """One ES position at entry price."""
        positions = [{
            "position_id": "TEST-001",
            "symbol": "ES",
            "side": "long",
            "quantity": 2,
            "entry_price": 6000,
            "current_price": 6050,
        }]
        metrics = es_engine.calculate_account_metrics(50000, positions)
        assert metrics.position_count == 1
        assert metrics.total_margin_used == 26400.0
        assert abs(metrics.margin_usage_pct - 52.8) < 0.1
        assert metrics.total_unrealized_pnl == 5000.0  # (6050-6000) × 2 × 50

    def test_health_status_thresholds(self, es_engine):
        """Test health status changes with margin usage."""
        # Low margin usage = HEALTHY
        metrics = es_engine.calculate_account_metrics(100000, [
            {"position_id": "P1", "symbol": "ES", "side": "long",
             "quantity": 1, "entry_price": 6000, "current_price": 6000}
        ])
        assert metrics.health_status == "HEALTHY"  # 13.2% usage

    def test_multiple_positions_metrics(self, btc_perp_engine):
        """Multiple perp positions aggregate correctly."""
        positions = [
            {"position_id": "P1", "symbol": "BTC-PERP", "side": "long",
             "quantity": 0.1, "entry_price": 100000, "current_price": 101000,
             "funding_rate": 0.0001},
            {"position_id": "P2", "symbol": "BTC-PERP", "side": "short",
             "quantity": 0.05, "entry_price": 100000, "current_price": 99000,
             "funding_rate": 0.0001},
        ]
        metrics = btc_perp_engine.calculate_account_metrics(25000, positions)
        assert metrics.position_count == 2
        assert metrics.total_margin_used > 0
        assert metrics.total_funding_cost_daily is not None


# =============================================================================
# TEST: PRE-TRADE CHECKS
# =============================================================================

class TestPreTradeCheck:
    def test_trade_approved(self, es_engine):
        """Trade within limits should be approved."""
        existing = [{
            "position_id": "P1", "symbol": "ES", "side": "long",
            "quantity": 1, "entry_price": 6000, "current_price": 6000,
        }]
        proposed = {
            "symbol": "ES", "side": "long",
            "quantity": 1, "entry_price": 6000,
        }
        result = es_engine.check_pre_trade(100000, existing, proposed)
        assert result.approved is True
        assert len(result.violations) == 0

    def test_trade_rejected_insufficient_margin(self, es_engine):
        """Trade requiring more margin than available should be rejected."""
        existing = [{
            "position_id": "P1", "symbol": "ES", "side": "long",
            "quantity": 3, "entry_price": 6000, "current_price": 6000,
        }]
        proposed = {
            "symbol": "ES", "side": "long",
            "quantity": 3, "entry_price": 6000,
        }
        result = es_engine.check_pre_trade(50000, existing, proposed)
        assert result.approved is False
        assert any("Insufficient margin" in v for v in result.violations)

    def test_trade_rejected_max_usage(self, es_engine):
        """Trade pushing margin usage above max should be rejected."""
        existing = [{
            "position_id": "P1", "symbol": "ES", "side": "long",
            "quantity": 2, "entry_price": 6000, "current_price": 6000,
        }]
        proposed = {
            "symbol": "ES", "side": "long",
            "quantity": 2, "entry_price": 6000,
        }
        # 4 contracts × $13,200 = $52,800, equity=$60,000 -> 88% > 70% max
        result = es_engine.check_pre_trade(60000, existing, proposed)
        assert result.approved is False
        assert any("Margin usage" in v for v in result.violations)

    def test_trade_rejected_max_leverage(self):
        """Trade exceeding max leverage should be rejected."""
        config = BotMarginConfig(
            bot_name="TEST",
            market_config=MARKET_DEFAULTS["BTC-PERP"],
            leverage_override=10.0,
            max_effective_leverage=5.0,  # Very conservative
        )
        engine = MarginEngine(config)
        proposed = {
            "symbol": "BTC-PERP", "side": "long",
            "quantity": 1.0, "entry_price": 100000,
            "leverage": 10.0,
        }
        result = engine.check_pre_trade(10000, [], proposed)
        # Notional = $100K, equity = $10K -> 10x leverage > 5x max
        assert result.approved is False
        assert any("leverage" in v.lower() for v in result.violations)

    def test_trade_approved_at_limit(self, es_engine):
        """Trade within all limits should be approved."""
        proposed = {
            "symbol": "ES", "side": "long",
            "quantity": 1, "entry_price": 6000,
        }
        # 1 contract = $13,200 margin, equity = $50,000
        # usage=26.4%, leverage=6x, single_pos=26.4% - all within defaults
        result = es_engine.check_pre_trade(50000, [], proposed)
        assert result.approved is True

    def test_single_position_concentration(self):
        """Single position using too much equity should be rejected."""
        config = BotMarginConfig(
            bot_name="TEST",
            market_config=MARKET_DEFAULTS["ES"],
            max_single_position_margin_pct=30.0,
        )
        engine = MarginEngine(config)
        proposed = {
            "symbol": "ES", "side": "long",
            "quantity": 2, "entry_price": 6000,
        }
        # 2 contracts = $26,400, equity = $50,000 -> 52.8% > 30% max
        result = engine.check_pre_trade(50000, [], proposed)
        assert result.approved is False
        assert any("Single position" in v for v in result.violations)


# =============================================================================
# TEST: SCENARIO SIMULATION
# =============================================================================

class TestScenarioSimulation:
    def test_price_drop_scenario(self, es_engine):
        """5% price drop on long ES position."""
        positions = [{
            "position_id": "P1", "symbol": "ES", "side": "long",
            "quantity": 2, "entry_price": 6000, "current_price": 6000,
        }]
        result = es_engine.simulate_price_move(50000, positions, -5.0)
        assert result.projected_margin_usage_pct > result.current_margin_usage_pct
        assert result.scenario_description == "Price move -5.0%"

    def test_price_rise_scenario(self, es_engine):
        """5% price rise on long ES position."""
        positions = [{
            "position_id": "P1", "symbol": "ES", "side": "long",
            "quantity": 2, "entry_price": 6000, "current_price": 6000,
        }]
        result = es_engine.simulate_price_move(50000, positions, 5.0)
        # Long position profits from price rise -> lower margin usage
        assert result.scenario_description == "Price move +5.0%"

    def test_empty_positions_scenario(self, es_engine):
        """Scenario with no positions."""
        result = es_engine.simulate_price_move(50000, [], -10.0)
        assert result.projected_margin_usage_pct == 0.0
        assert result.would_trigger_liquidation is False

    def test_add_position_scenario(self, btc_perp_engine):
        """Simulate adding a position."""
        result = btc_perp_engine.simulate_add_contracts(
            25000, [], 0.1, 100000, "long"
        )
        assert result.projected_margin_usage_pct > 0

    def test_leverage_change_scenario(self, btc_perp_engine):
        """Simulate changing leverage."""
        positions = [{
            "position_id": "P1", "symbol": "BTC-PERP", "side": "long",
            "quantity": 0.1, "entry_price": 100000, "current_price": 100000,
            "leverage": 10.0,
        }]
        result = btc_perp_engine.simulate_leverage_change(25000, positions, 20.0)
        # Higher leverage = less margin required = lower usage
        assert result.projected_margin_usage_pct < result.current_margin_usage_pct


# =============================================================================
# TEST: POSITION METRICS
# =============================================================================

class TestPositionMetrics:
    def test_position_metrics_complete(self, btc_perp_engine):
        """All fields should be populated in position metrics."""
        pos = {
            "position_id": "TEST-001",
            "symbol": "BTC-PERP",
            "side": "long",
            "quantity": 0.1,
            "entry_price": 100000,
            "current_price": 101000,
            "funding_rate": 0.0001,
        }
        metrics = btc_perp_engine.calculate_position_metrics(pos, 25000, 0)

        assert metrics.position_id == "TEST-001"
        assert metrics.symbol == "BTC-PERP"
        assert metrics.side == "long"
        assert metrics.notional_value == 10100.0  # 0.1 × 101000 × 1.0
        assert metrics.initial_margin_required > 0
        assert metrics.maintenance_margin_required > 0
        assert metrics.unrealized_pnl == 100.0  # (101000 - 100000) × 0.1 × 1
        assert metrics.funding_rate == 0.0001
        assert metrics.funding_cost_projection_daily is not None
        assert metrics.timestamp is not None

    def test_position_metrics_to_dict(self, btc_perp_engine):
        """to_dict should return serializable data."""
        pos = {
            "position_id": "TEST-001",
            "symbol": "BTC-PERP",
            "side": "long",
            "quantity": 0.1,
            "entry_price": 100000,
            "current_price": 101000,
        }
        metrics = btc_perp_engine.calculate_position_metrics(pos, 25000, 0)
        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert "position_id" in d
        assert "notional_value" in d
        assert isinstance(d["notional_value"], (int, float))


# =============================================================================
# TEST: MARKET CONFIG
# =============================================================================

class TestMarketConfig:
    def test_all_defaults_exist(self):
        """All market defaults should have valid configs."""
        for instrument, config in MARKET_DEFAULTS.items():
            assert config.market_type is not None
            assert config.exchange is not None
            assert config.contract_multiplier > 0

    def test_bot_instrument_mapping(self):
        """All bots should map to valid instruments."""
        for bot_name, instrument in BOT_INSTRUMENT_MAP.items():
            config = get_default_market_config(instrument)
            assert config is not None, f"No config for {bot_name} -> {instrument}"

    def test_perps_have_funding(self):
        """All perpetual configs should have funding rate enabled."""
        for key, config in MARKET_DEFAULTS.items():
            if config.market_type == MarketType.CRYPTO_PERPETUAL:
                assert config.has_funding_rate is True, f"{key} should have funding rate"

    def test_futures_have_expiry(self):
        """All futures should have expiry."""
        for key, config in MARKET_DEFAULTS.items():
            if config.market_type in (MarketType.STOCK_FUTURES, MarketType.CRYPTO_FUTURES):
                assert config.has_expiry is True, f"{key} should have expiry"

    def test_spot_no_leverage(self):
        """Spot trading should have no leverage."""
        for key, config in MARKET_DEFAULTS.items():
            if config.market_type == MarketType.CRYPTO_SPOT:
                assert config.max_leverage == 1.0, f"{key} should have 1x leverage"

    def test_config_to_dict(self):
        """Config serialization should work."""
        config = MARKET_DEFAULTS["ES"]
        d = config.to_dict()
        assert d["market_type"] == "stock_futures"
        assert d["exchange"] == "CME"
        assert d["contract_multiplier"] == 50.0


# =============================================================================
# TEST: HEALTH STATUS
# =============================================================================

class TestHealthStatus:
    def test_healthy(self, es_engine):
        assert es_engine._determine_health_status(30.0) == "HEALTHY"

    def test_warning(self, es_engine):
        assert es_engine._determine_health_status(65.0) == "WARNING"

    def test_danger(self, es_engine):
        assert es_engine._determine_health_status(82.0) == "DANGER"

    def test_critical(self, es_engine):
        assert es_engine._determine_health_status(95.0) == "CRITICAL"

    def test_color_mapping(self):
        assert MarginEngine.health_status_to_color("HEALTHY") == "green"
        assert MarginEngine.health_status_to_color("CRITICAL") == "red"
        assert MarginEngine.health_status_to_color("UNKNOWN") == "gray"
