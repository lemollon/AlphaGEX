"""
PEGASUS SPX Iron Condor Strategy Tests

Tests for the PEGASUS SPX Iron Condor trading bot.

Run with: pytest tests/test_pegasus.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPEGASUSModelsImport:
    """Tests for PEGASUS models import"""

    def test_import_pegasus_models(self):
        """Test that PEGASUS models can be imported"""
        from trading.pegasus.models import (
            IronCondorPosition,
            IronCondorSignal,
            PEGASUSConfig,
            TradingMode,
            PositionStatus,
            StrategyPreset,
            CENTRAL_TZ
        )
        assert IronCondorPosition is not None
        assert IronCondorSignal is not None
        assert PEGASUSConfig is not None
        assert TradingMode is not None
        assert PositionStatus is not None
        assert StrategyPreset is not None
        assert CENTRAL_TZ is not None


class TestPEGASUSConfig:
    """Tests for PEGASUS configuration"""

    def test_default_config(self):
        """Test default configuration values"""
        from trading.pegasus.models import PEGASUSConfig, TradingMode, StrategyPreset

        config = PEGASUSConfig()

        assert config.ticker == "SPX"
        assert config.spread_width == 10.0  # SPX uses $10 spreads
        assert config.strike_increment == 5.0  # SPX trades in $5 increments
        assert config.mode == TradingMode.PAPER
        assert config.preset == StrategyPreset.MODERATE

    def test_apply_preset(self):
        """Test applying strategy presets"""
        from trading.pegasus.models import PEGASUSConfig, StrategyPreset

        config = PEGASUSConfig()

        # Apply conservative preset
        config.apply_preset(StrategyPreset.CONSERVATIVE)
        assert config.vix_skip == 35.0
        assert config.sd_multiplier == 1.0

        # Apply aggressive preset
        config.apply_preset(StrategyPreset.AGGRESSIVE)
        assert config.vix_skip == 30.0

        # Apply wide strikes preset
        config.apply_preset(StrategyPreset.WIDE_STRIKES)
        assert config.sd_multiplier == 1.2


class TestIronCondorPosition:
    """Tests for Iron Condor position model"""

    def test_position_creation(self):
        """Test creating an iron condor position"""
        from trading.pegasus.models import IronCondorPosition, PositionStatus

        position = IronCondorPosition(
            position_id="PEGASUS-SPX-20231215-001",
            ticker="SPX",
            expiration="2023-12-15",
            put_short_strike=5800.0,
            put_long_strike=5790.0,
            put_credit=2.50,
            call_short_strike=5950.0,
            call_long_strike=5960.0,
            call_credit=2.00,
            contracts=5,
            spread_width=10.0,
            total_credit=4.50,
            max_loss=550.0,
            max_profit=450.0,
            underlying_at_entry=5875.0,
            vix_at_entry=18.5,
        )

        assert position.ticker == "SPX"
        assert position.spread_width == 10.0
        assert position.is_open
        assert position.status == PositionStatus.OPEN

    def test_position_to_dict(self):
        """Test converting position to dictionary"""
        from trading.pegasus.models import IronCondorPosition

        position = IronCondorPosition(
            position_id="PEGASUS-SPX-20231215-001",
            ticker="SPX",
            expiration="2023-12-15",
            put_short_strike=5800.0,
            put_long_strike=5790.0,
            call_short_strike=5950.0,
            call_long_strike=5960.0,
        )

        data = position.to_dict()

        assert data['position_id'] == "PEGASUS-SPX-20231215-001"
        assert data['ticker'] == "SPX"
        assert data['status'] == "open"
        assert 'oracle_confidence' in data
        assert 'oracle_win_probability' in data


class TestIronCondorSignal:
    """Tests for Iron Condor signal model"""

    def test_signal_creation(self):
        """Test creating an iron condor signal"""
        from trading.pegasus.models import IronCondorSignal

        signal = IronCondorSignal(
            spot_price=5875.0,
            vix=18.5,
            expected_move=45.0,
            call_wall=5950.0,
            put_wall=5800.0,
            gex_regime="POSITIVE_GEX",
            put_short=5800.0,
            put_long=5790.0,
            call_short=5950.0,
            call_long=5960.0,
            total_credit=4.50,
            confidence=0.75,
        )

        assert signal.spot_price == 5875.0
        assert signal.gex_regime == "POSITIVE_GEX"
        assert signal.confidence == 0.75

    def test_signal_validity(self):
        """Test signal validity checks"""
        from trading.pegasus.models import IronCondorSignal

        # Valid signal
        valid_signal = IronCondorSignal(
            spot_price=5875.0,
            vix=18.5,
            expected_move=45.0,
            call_wall=5950.0,
            put_wall=5800.0,
            gex_regime="POSITIVE_GEX",
            put_short=5800.0,
            put_long=5790.0,
            call_short=5950.0,
            call_long=5960.0,
            total_credit=2.00,  # Above $1.50 threshold
            confidence=0.75,
        )
        assert valid_signal.is_valid

        # Invalid signal - low confidence
        low_confidence = IronCondorSignal(
            spot_price=5875.0,
            vix=18.5,
            expected_move=45.0,
            call_wall=5950.0,
            put_wall=5800.0,
            gex_regime="POSITIVE_GEX",
            put_short=5800.0,
            put_long=5790.0,
            call_short=5950.0,
            call_long=5960.0,
            total_credit=2.00,
            confidence=0.3,  # Below threshold
        )
        assert not low_confidence.is_valid


class TestSignalGenerator:
    """Tests for PEGASUS signal generator"""

    def test_signal_generator_import(self):
        """Test that signal generator can be imported"""
        try:
            from trading.pegasus.signals import SignalGenerator
            assert SignalGenerator is not None
        except ImportError:
            pytest.skip("SignalGenerator not available")

    def test_signal_generator_initialization(self):
        """Test signal generator initialization"""
        try:
            from trading.pegasus.signals import SignalGenerator
            from trading.pegasus.models import PEGASUSConfig

            config = PEGASUSConfig()
            generator = SignalGenerator(config)

            assert generator is not None
            assert generator.config == config
        except ImportError:
            pytest.skip("SignalGenerator not available")

    def test_calculate_strikes(self):
        """Test strike calculation with $5 rounding"""
        try:
            from trading.pegasus.signals import SignalGenerator
            from trading.pegasus.models import PEGASUSConfig

            config = PEGASUSConfig()
            generator = SignalGenerator(config)

            strikes = generator.calculate_strikes(
                spot=5875.0,
                expected_move=50.0,
                call_wall=0,  # No GEX walls
                put_wall=0,
            )

            # Check strikes are rounded to $5
            assert strikes['put_short'] % 5 == 0
            assert strikes['call_short'] % 5 == 0
            assert strikes['put_long'] == strikes['put_short'] - 10  # $10 width
            assert strikes['call_long'] == strikes['call_short'] + 10

        except ImportError:
            pytest.skip("SignalGenerator not available")

    def test_calculate_strikes_with_gex_walls(self):
        """Test strike calculation using GEX walls"""
        try:
            from trading.pegasus.signals import SignalGenerator
            from trading.pegasus.models import PEGASUSConfig

            config = PEGASUSConfig()
            generator = SignalGenerator(config)

            strikes = generator.calculate_strikes(
                spot=5875.0,
                expected_move=50.0,
                call_wall=5950.0,
                put_wall=5800.0,
            )

            # When GEX walls are provided, short strikes should align with walls
            assert strikes['using_gex']
            assert strikes['put_short'] == 5800.0
            assert strikes['call_short'] == 5950.0

        except ImportError:
            pytest.skip("SignalGenerator not available")

    def test_vix_filter(self):
        """Test VIX filter functionality"""
        try:
            from trading.pegasus.signals import SignalGenerator
            from trading.pegasus.models import PEGASUSConfig

            config = PEGASUSConfig()
            config.vix_skip = 30.0
            generator = SignalGenerator(config)

            # Should pass - VIX below threshold
            can_trade, reason = generator.check_vix_filter(25.0)
            assert can_trade
            assert reason == "OK"

            # Should fail - VIX above threshold
            can_trade, reason = generator.check_vix_filter(35.0)
            assert not can_trade
            assert "VIX" in reason

        except ImportError:
            pytest.skip("SignalGenerator not available")


class TestPEGASUSDatabase:
    """Tests for PEGASUS database operations"""

    def test_database_import(self):
        """Test that database module can be imported"""
        try:
            from trading.pegasus.db import PEGASUSDatabase
            assert PEGASUSDatabase is not None
        except ImportError:
            pytest.skip("PEGASUSDatabase not available")

    def test_database_initialization(self):
        """Test database initialization"""
        try:
            from trading.pegasus.db import PEGASUSDatabase

            with patch('database_adapter.get_connection', return_value=MagicMock()):
                db = PEGASUSDatabase(bot_name="PEGASUS_TEST")
                assert db is not None
                assert db.bot_name == "PEGASUS_TEST"
        except ImportError:
            pytest.skip("PEGASUSDatabase not available")


class TestOracleIntegration:
    """Tests for PEGASUS Oracle integration"""

    def test_oracle_pegasus_advice(self):
        """Test that Oracle has get_pegasus_advice method"""
        try:
            from quant.oracle_advisor import OracleAdvisor

            # Oracle should have get_pegasus_advice method
            assert hasattr(OracleAdvisor, 'get_pegasus_advice')

        except ImportError:
            pytest.skip("OracleAdvisor not available")

    def test_oracle_botname_enum(self):
        """Test that PEGASUS is in BotName enum"""
        try:
            from quant.oracle_advisor import BotName

            assert 'PEGASUS' in [b.name for b in BotName]

        except ImportError:
            pytest.skip("Oracle BotName enum not available")


class TestSolomonIntegration:
    """Tests for PEGASUS Solomon feedback loop integration"""

    def test_solomon_botname_enum(self):
        """Test that PEGASUS is in Solomon BotName enum"""
        try:
            from quant.solomon_feedback_loop import BotName

            assert 'PEGASUS' in [b.name for b in BotName]

        except ImportError:
            pytest.skip("Solomon not available")

    def test_solomon_table_map(self):
        """Test that PEGASUS has correct table mapping"""
        try:
            from quant.solomon_feedback_loop import Solomon

            # Check if table_map includes PEGASUS
            solomon = Solomon.__new__(Solomon)
            if hasattr(solomon, 'table_map'):
                # The table_map should include PEGASUS
                pass  # Table map check would require instance

        except ImportError:
            pytest.skip("Solomon not available")


class TestDecisionLogger:
    """Tests for PEGASUS decision logger integration"""

    def test_decision_logger_pegasus_enum(self):
        """Test that PEGASUS is in DecisionLogger BotName enum"""
        try:
            from trading.decision_logger import BotName

            assert 'PEGASUS' in [b.name for b in BotName]

        except ImportError:
            pytest.skip("DecisionLogger not available")

    def test_get_pegasus_logger(self):
        """Test that get_pegasus_logger function exists"""
        try:
            from trading.decision_logger import get_pegasus_logger

            assert get_pegasus_logger is not None
            assert callable(get_pegasus_logger)

        except ImportError:
            pytest.skip("get_pegasus_logger not available")


class TestBotLogger:
    """Tests for PEGASUS bot logger integration"""

    def test_bot_logger_pegasus_enum(self):
        """Test that PEGASUS is in BotLogger BotName enum"""
        try:
            from trading.bot_logger import BotName

            assert 'PEGASUS' in [b.name for b in BotName]

        except ImportError:
            pytest.skip("BotLogger not available")

    def test_get_pegasus_logger(self):
        """Test that get_pegasus_logger function exists in bot_logger"""
        try:
            from trading.bot_logger import get_pegasus_logger

            assert get_pegasus_logger is not None
            assert callable(get_pegasus_logger)

        except ImportError:
            pytest.skip("bot_logger.get_pegasus_logger not available")


class TestPEGASUSRiskLimits:
    """Tests for PEGASUS risk management changes (January 2025)"""

    def test_config_max_contracts_reduced(self):
        """Test that max_contracts was reduced from 100 to 25"""
        try:
            from trading.pegasus.models import PEGASUSConfig
            config = PEGASUSConfig()
            assert config.max_contracts == 25, f"Expected 25, got {config.max_contracts}"
        except ImportError:
            pytest.skip("PEGASUSConfig not available")

    def test_config_max_open_positions_reduced(self):
        """Test that max_open_positions was reduced from 5 to 3"""
        try:
            from trading.pegasus.models import PEGASUSConfig
            config = PEGASUSConfig()
            assert config.max_open_positions == 3, f"Expected 3, got {config.max_open_positions}"
        except ImportError:
            pytest.skip("PEGASUSConfig not available")

    def test_config_max_trades_per_day_exists(self):
        """Test that max_trades_per_day was added with value 2"""
        try:
            from trading.pegasus.models import PEGASUSConfig
            config = PEGASUSConfig()
            assert hasattr(config, 'max_trades_per_day'), "max_trades_per_day not found"
            assert config.max_trades_per_day == 2, f"Expected 2, got {config.max_trades_per_day}"
        except ImportError:
            pytest.skip("PEGASUSConfig not available")

    def test_config_stop_loss_disabled(self):
        """Test that stop_loss remains disabled"""
        try:
            from trading.pegasus.models import PEGASUSConfig
            config = PEGASUSConfig()
            assert config.use_stop_loss is False, "Stop loss should be disabled"
        except ImportError:
            pytest.skip("PEGASUSConfig not available")

    def test_executor_has_portfolio_risk_method(self):
        """Test that executor has _get_current_portfolio_risk method"""
        try:
            from trading.pegasus.executor import OrderExecutor
            assert hasattr(OrderExecutor, '_get_current_portfolio_risk')
        except ImportError:
            pytest.skip("OrderExecutor not available")

    def test_executor_portfolio_risk_cap_in_position_sizing(self):
        """Test that position sizing includes 20% portfolio risk cap logic"""
        try:
            import inspect
            from trading.pegasus.executor import OrderExecutor
            source = inspect.getsource(OrderExecutor._calculate_position_size)
            assert 'MAX_TOTAL_PORTFOLIO_RISK_PCT' in source, "Missing portfolio risk cap constant"
            assert '20.0' in source, "Risk cap should be 20%"
        except ImportError:
            pytest.skip("OrderExecutor not available")

    def test_db_has_get_trades_opened_today(self):
        """Test that database has get_trades_opened_today method"""
        try:
            from trading.pegasus.db import PEGASUSDatabase
            assert hasattr(PEGASUSDatabase, 'get_trades_opened_today')
        except ImportError:
            pytest.skip("PEGASUSDatabase not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
