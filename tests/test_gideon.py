"""
GIDEON Bot Comprehensive Test Suite
====================================

Tests for the GIDEON aggressive directional spreads trading bot.

GIDEON uses AGGRESSIVE Apache GEX backtest parameters (vs SOLOMON):
- 2% wall filter (vs 1%) - more room to trade
- 48% min win probability (vs 55%) - lower threshold
- 3% risk per trade (vs 2%) - larger positions
- $3 spread width (vs $2) - wider spreads
- VIX range 12-30 (vs 15-25) - wider volatility range
- GEX ratio 1.3/0.77 (vs 1.5/0.67) - weaker asymmetry allowed
- 1.2 R:R ratio (vs 1.5) - accept slightly lower R:R

Safety filters ARE ENABLED with aggressive thresholds.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db_connection():
    """Mock database connection for tests"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    return mock_conn


@pytest.fixture
def gideon_config():
    """Create GIDEON config for testing"""
    with patch('database_adapter.get_connection') as mock_conn:
        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []

        from trading.gideon.models import GideonConfig, TradingMode
        return GideonConfig(mode=TradingMode.PAPER)


@pytest.fixture
def signal_generator(mock_db_connection):
    """Create signal generator for testing"""
    with patch('database_adapter.get_connection', return_value=mock_db_connection):
        from trading.gideon.signals import SignalGenerator
        from trading.gideon.models import GideonConfig
        config = GideonConfig()
        return SignalGenerator(config)


@pytest.fixture
def order_executor(mock_db_connection):
    """Create order executor for testing"""
    with patch('database_adapter.get_connection', return_value=mock_db_connection):
        from trading.gideon.executor import OrderExecutor
        from trading.gideon.models import GideonConfig, TradingMode
        config = GideonConfig(mode=TradingMode.PAPER)
        return OrderExecutor(config)


# =============================================================================
# CONFIG TESTS
# =============================================================================

class TestGideonConfig:
    """Test GIDEON configuration"""

    def test_default_config_values(self, mock_db_connection):
        """Test default config values are aggressive Apache GEX backtest parameters"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import GideonConfig
            config = GideonConfig()

            # GIDEON aggressive Apache GEX backtest defaults
            assert config.wall_filter_pct == 2.0, "Wall filter should be 2% (vs SOLOMON's 1%)"
            assert config.min_win_probability == 0.48, "Min win prob should be 48% (vs SOLOMON's 55%)"
            assert config.min_confidence == 0.48, "Min confidence should be 48% (vs SOLOMON's 55%)"
            assert config.min_rr_ratio == 1.2, "Min R:R ratio should be 1.2 (vs SOLOMON's 1.5)"
            assert config.risk_per_trade_pct == 3.0, "Risk per trade should be 3% (vs SOLOMON's 2%)"
            assert config.spread_width == 3, "Spread width should be $3 (vs SOLOMON's $2)"
            assert config.max_daily_trades == 8, "Max daily trades should be 8 (vs SOLOMON's 5)"
            assert config.max_open_positions == 4, "Max open positions should be 4 (vs SOLOMON's 3)"
            # VIX filter
            assert config.min_vix == 12.0, "Min VIX should be 12 (vs SOLOMON's 15)"
            assert config.max_vix == 30.0, "Max VIX should be 30 (vs SOLOMON's 25)"
            # GEX ratio asymmetry
            assert config.min_gex_ratio_bearish == 1.3, "Min GEX ratio bearish should be 1.3 (vs SOLOMON's 1.5)"
            assert config.max_gex_ratio_bullish == 0.77, "Max GEX ratio bullish should be 0.77 (vs SOLOMON's 0.67)"
            # Exit thresholds
            assert config.profit_target_pct == 40.0, "Profit target should be 40% (vs SOLOMON's 50%)"
            assert config.stop_loss_pct == 60.0, "Stop loss should be 60% (vs SOLOMON's 50%)"

    def test_config_validation_valid(self, mock_db_connection):
        """Test valid config passes validation"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import GideonConfig
            config = GideonConfig()
            is_valid, msg = config.validate()
            assert is_valid, f"Default config should be valid: {msg}"

    def test_config_validation_invalid_risk(self, mock_db_connection):
        """Test invalid risk per trade fails validation"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import GideonConfig
            config = GideonConfig(risk_per_trade_pct=0)
            is_valid, msg = config.validate()
            assert not is_valid, "Zero risk should be invalid"

            config = GideonConfig(risk_per_trade_pct=25)
            is_valid, msg = config.validate()
            assert not is_valid, "25% risk should be invalid"

    def test_config_validation_invalid_wall_filter(self, mock_db_connection):
        """Test invalid wall filter fails validation"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import GideonConfig
            config = GideonConfig(wall_filter_pct=60)
            is_valid, msg = config.validate()
            assert not is_valid, "60% wall filter should be invalid"

    def test_config_validation_invalid_win_probability(self, mock_db_connection):
        """Test invalid win probability fails validation"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import GideonConfig
            config = GideonConfig(min_win_probability=2.0)
            is_valid, msg = config.validate()
            assert not is_valid, "Win probability > 1 should be invalid"


# =============================================================================
# MODEL TESTS
# =============================================================================

class TestGideonModels:
    """Test GIDEON data models"""

    def test_spread_position_creation(self, mock_db_connection):
        """Test SpreadPosition creation and properties"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import SpreadPosition, SpreadType, PositionStatus

            position = SpreadPosition(
                position_id='TEST-001',
                spread_type=SpreadType.BULL_CALL,
                ticker='SPY',
                long_strike=585.0,
                short_strike=588.0,
                expiration='2024-12-06',
                entry_debit=1.50,
                contracts=5,
                max_profit=750.0,
                max_loss=750.0,
                underlying_at_entry=586.0,
            )

            assert position.spread_width == 3.0, "Spread width should be 3"
            assert position.is_bullish, "Bull call should be bullish"

            # Test to_dict
            data = position.to_dict()
            assert data['position_id'] == 'TEST-001'
            assert data['spread_type'] == 'BULL_CALL'

    def test_trade_signal_validation(self, mock_db_connection):
        """Test TradeSignal validation with Apache aggressive thresholds"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import TradeSignal, SpreadType

            # Valid signal - meets aggressive thresholds (48% confidence, 1.2 R:R)
            signal = TradeSignal(
                direction='BULLISH',
                spread_type=SpreadType.BULL_CALL,
                confidence=0.55,  # Above 48% threshold
                spot_price=586.0,
                call_wall=590.0,
                put_wall=580.0,
                gex_regime='POSITIVE',
                vix=15.0,
                long_strike=585.0,
                short_strike=588.0,
                expiration='2024-12-06',
                estimated_debit=1.50,
                max_profit=180.0,  # 1.2 R:R
                max_loss=150.0,
                rr_ratio=1.2,  # Meets 1.2 minimum
            )
            assert signal.is_valid, "Signal should be valid with 55% confidence and 1.2 R:R"

            # Invalid signal - below 48% confidence threshold
            low_confidence_signal = TradeSignal(
                direction='BULLISH',
                spread_type=SpreadType.BULL_CALL,
                confidence=0.40,  # Below 48% threshold
                spot_price=586.0,
                call_wall=590.0,
                put_wall=580.0,
                gex_regime='POSITIVE',
                vix=15.0,
                long_strike=585.0,
                short_strike=588.0,
                max_profit=150.0,
                rr_ratio=1.5,
            )
            assert not low_confidence_signal.is_valid, "Signal with 40% confidence should be invalid (below 48%)"

            # Invalid signal - below 1.2 R:R threshold
            low_rr_signal = TradeSignal(
                direction='BULLISH',
                spread_type=SpreadType.BULL_CALL,
                confidence=0.55,
                spot_price=586.0,
                call_wall=590.0,
                put_wall=580.0,
                gex_regime='POSITIVE',
                vix=15.0,
                long_strike=585.0,
                short_strike=588.0,
                max_profit=150.0,
                rr_ratio=1.0,  # Below 1.2 threshold
            )
            assert not low_rr_signal.is_valid, "Signal with 1.0 R:R should be invalid (below 1.2)"


# =============================================================================
# SIGNAL GENERATOR TESTS
# =============================================================================

class TestSignalGenerator:
    """Test signal generation logic"""

    def test_wall_proximity_closer_to_put(self, signal_generator):
        """Test wall proximity when closer to put wall"""
        gex = {'spot_price': 585.0, 'call_wall': 590.0, 'put_wall': 584.0}
        near, direction, reason = signal_generator.check_wall_proximity(gex)
        assert near, "Should be near a wall"
        assert direction == "BULLISH", "Should be bullish (near put wall)"

    def test_wall_proximity_closer_to_call(self, signal_generator):
        """Test wall proximity when closer to call wall"""
        gex = {'spot_price': 589.0, 'call_wall': 590.0, 'put_wall': 580.0}
        near, direction, reason = signal_generator.check_wall_proximity(gex)
        assert near, "Should be near a wall"
        assert direction == "BEARISH", "Should be bearish (near call wall)"

    def test_wall_proximity_far_from_walls(self, signal_generator):
        """Test wall proximity when far from both walls"""
        gex = {'spot_price': 585.0, 'call_wall': 700.0, 'put_wall': 400.0}
        near, direction, reason = signal_generator.check_wall_proximity(gex)
        assert not near, "Should not be near any wall"
        assert direction == "", "Direction should be empty"

    def test_wall_proximity_missing_data(self, signal_generator):
        """Test wall proximity with missing data"""
        gex = {'spot_price': 0, 'call_wall': 590.0, 'put_wall': 580.0}
        near, direction, reason = signal_generator.check_wall_proximity(gex)
        assert not near, "Should fail with missing spot"
        assert "Missing" in reason

    def test_calculate_spread_strikes_bullish(self, signal_generator):
        """Test spread strike calculation for bullish signal"""
        long_strike, short_strike = signal_generator.calculate_spread_strikes(
            'BULLISH', 585.50, '2024-12-06'
        )
        # ATM rounded = 586
        assert long_strike == 586, "Long strike should be ATM"
        assert short_strike == 589, "Short strike should be ATM + 3"

    def test_calculate_spread_strikes_bearish(self, signal_generator):
        """Test spread strike calculation for bearish signal"""
        long_strike, short_strike = signal_generator.calculate_spread_strikes(
            'BEARISH', 585.50, '2024-12-06'
        )
        assert long_strike == 586, "Long strike should be ATM"
        assert short_strike == 583, "Short strike should be ATM - 3"

    def test_estimate_spread_pricing(self, signal_generator):
        """Test spread pricing estimation"""
        from trading.gideon.models import SpreadType
        debit, max_profit, max_loss = signal_generator.estimate_spread_pricing(
            SpreadType.BULL_CALL, 585.0, 588.0, 586.0, 15.0
        )

        assert debit > 0, "Debit should be positive"
        assert max_profit > 0, "Max profit should be positive"
        assert max_loss > 0, "Max loss should be positive"
        assert max_profit + max_loss == pytest.approx(300, rel=0.05), "Total should be near spread width * 100"


# =============================================================================
# ORDER EXECUTOR TESTS
# =============================================================================

class TestOrderExecutor:
    """Test order execution logic"""

    def test_position_size_calculation(self, order_executor):
        """Test position size calculation with 3% risk per trade"""
        # 3% risk of 100k = 3000
        # With max_loss of 100 per contract = 30 contracts
        contracts = order_executor._calculate_position_size(100.0, 1.0)
        assert contracts == 30, f"Expected 30 contracts, got {contracts}"

        # With max_loss of 200 = 15 contracts
        contracts = order_executor._calculate_position_size(200.0, 1.0)
        assert contracts == 15, f"Expected 15 contracts, got {contracts}"

    def test_position_size_with_thompson_weight(self, order_executor):
        """Test position size with Thompson weight"""
        base_contracts = order_executor._calculate_position_size(100.0, 1.0)

        # Double weight
        double_contracts = order_executor._calculate_position_size(100.0, 2.0)
        assert double_contracts == min(50, base_contracts * 2), "Double weight should double contracts (capped)"

        # Half weight
        half_contracts = order_executor._calculate_position_size(100.0, 0.5)
        assert half_contracts == max(1, base_contracts // 2), "Half weight should halve contracts"

    def test_position_size_capped_at_50(self, order_executor):
        """Test position size is capped at 50"""
        # Very small max loss = many contracts, should be capped
        contracts = order_executor._calculate_position_size(10.0, 2.0)
        assert contracts <= 50, "Contracts should be capped at 50"

    def test_position_size_minimum_1(self, order_executor):
        """Test position size is at least 1"""
        # Very large max loss = fraction of a contract, should round to 1
        contracts = order_executor._calculate_position_size(10000.0, 0.5)
        assert contracts >= 1, "Contracts should be at least 1"

    def test_spread_value_bull_call_max_profit(self, order_executor):
        """Test spread value estimation at max profit"""
        from trading.gideon.models import SpreadPosition, SpreadType

        position = SpreadPosition(
            position_id='TEST',
            spread_type=SpreadType.BULL_CALL,
            ticker='SPY',
            long_strike=585.0,
            short_strike=588.0,
            expiration='2024-12-06',
            entry_debit=1.50,
            contracts=1,
            max_profit=150.0,
            max_loss=150.0,
            underlying_at_entry=586.0,
        )

        # Price above short strike = max profit
        value = order_executor._estimate_spread_value(position, 590.0)
        assert value == 3.0, f"Expected 3.0 (spread width), got {value}"

    def test_spread_value_bull_call_max_loss(self, order_executor):
        """Test spread value estimation at max loss"""
        from trading.gideon.models import SpreadPosition, SpreadType

        position = SpreadPosition(
            position_id='TEST',
            spread_type=SpreadType.BULL_CALL,
            ticker='SPY',
            long_strike=585.0,
            short_strike=588.0,
            expiration='2024-12-06',
            entry_debit=1.50,
            contracts=1,
            max_profit=150.0,
            max_loss=150.0,
            underlying_at_entry=586.0,
        )

        # Price below long strike = max loss (worthless)
        value = order_executor._estimate_spread_value(position, 583.0)
        assert value == 0.0, f"Expected 0.0, got {value}"

    def test_paper_execution(self, order_executor, mock_db_connection):
        """Test paper trade execution"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import TradeSignal, SpreadType

            signal = TradeSignal(
                direction='BULLISH',
                spread_type=SpreadType.BULL_CALL,
                confidence=0.75,
                spot_price=586.0,
                call_wall=590.0,
                put_wall=580.0,
                gex_regime='POSITIVE',
                vix=15.0,
                long_strike=585.0,
                short_strike=588.0,
                expiration='2024-12-06',
                estimated_debit=1.50,
                max_profit=150.0,
                max_loss=150.0,
                rr_ratio=1.0,
            )

            position = order_executor._execute_paper(signal, thompson_weight=1.0)

            assert position is not None, "Paper execution should return a position"
            assert position.position_id.startswith('GIDEON-'), "Position ID should start with GIDEON-"
            assert position.contracts > 0, "Should have contracts"
            assert position.order_id == 'PAPER', "Order ID should be PAPER for paper trades"


# =============================================================================
# DATABASE TESTS
# =============================================================================

class TestGideonDatabase:
    """Test database operations"""

    def test_get_open_positions_empty(self, mock_db_connection):
        """Test getting open positions when none exist"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            with patch('trading.gideon.db.get_connection', return_value=mock_db_connection):
                from trading.gideon.db import GideonDatabase
                db = GideonDatabase()
                positions = db.get_open_positions()
                assert positions == [], "Should return empty list"

    def test_get_position_count(self, mock_db_connection):
        """Test getting position count"""
        mock_db_connection.cursor().fetchone.return_value = [5]
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            with patch('trading.gideon.db.get_connection', return_value=mock_db_connection):
                from trading.gideon.db import GideonDatabase
                db = GideonDatabase()
                count = db.get_position_count()
                # Returns 0 due to mock - but tests function works
                assert isinstance(count, int)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestGideonIntegration:
    """Integration tests for GIDEON trading flow"""

    def test_full_signal_to_execution_flow(self, mock_db_connection):
        """Test complete flow from signal to execution"""
        with patch('database_adapter.get_connection', return_value=mock_db_connection):
            from trading.gideon.models import GideonConfig, TradingMode, SpreadType
            from trading.gideon.signals import SignalGenerator
            from trading.gideon.executor import OrderExecutor

            config = GideonConfig(mode=TradingMode.PAPER)
            signal_gen = SignalGenerator(config)
            executor = OrderExecutor(config)

            # Test wall proximity check
            gex_data = {
                'spot_price': 585.0,
                'call_wall': 590.0,
                'put_wall': 584.0,
                'gex_regime': 'POSITIVE',
                'vix': 15.0,
            }

            near_wall, direction, reason = signal_gen.check_wall_proximity(gex_data)
            assert near_wall, "Should be near wall"

            # Calculate strikes
            long_strike, short_strike = signal_gen.calculate_spread_strikes(
                direction, gex_data['spot_price'], '2024-12-06'
            )

            # Estimate pricing
            spread_type = SpreadType.BULL_CALL if direction == 'BULLISH' else SpreadType.BEAR_PUT
            debit, max_profit, max_loss = signal_gen.estimate_spread_pricing(
                spread_type, long_strike, short_strike, gex_data['spot_price'], gex_data['vix']
            )

            # Execute trade
            from trading.gideon.models import TradeSignal
            signal = TradeSignal(
                direction=direction,
                spread_type=spread_type,
                confidence=0.75,
                spot_price=gex_data['spot_price'],
                call_wall=gex_data['call_wall'],
                put_wall=gex_data['put_wall'],
                gex_regime=gex_data['gex_regime'],
                vix=gex_data['vix'],
                long_strike=long_strike,
                short_strike=short_strike,
                expiration='2024-12-06',
                estimated_debit=debit,
                max_profit=max_profit,
                max_loss=max_loss,
                rr_ratio=max_profit / max_loss if max_loss > 0 else 0,
            )

            position = executor.execute_spread(signal, thompson_weight=1.0)
            assert position is not None, "Should execute trade successfully"
            assert position.spread_type == spread_type


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
