"""
End-to-End Test: V2 Bot Audit Trail Storage
=============================================

Verifies that FORTRESS V2, SOLOMON V2, and ANCHOR V2 properly store
all Oracle/Kronos audit trail data in the database.

This is critical for live trading - we need FULL visibility into
why trades were made.
"""

import pytest
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import Mock, patch, MagicMock

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# FORTRESS V2 AUDIT TRAIL TESTS
# =============================================================================

class TestARESV2AuditTrail:
    """Test FORTRESS V2 Iron Condor stores full Oracle/Kronos context"""

    def test_signal_captures_oracle_context(self):
        """Verify signal captures all Oracle prediction details"""
        from trading.fortress_v2.models import IronCondorSignal

        # Create signal with full Oracle context
        signal = IronCondorSignal(
            spot_price=585.50,
            vix=18.5,
            expected_move=8.75,
            call_wall=595.0,
            put_wall=575.0,
            gex_regime="POSITIVE_GAMMA",
            # Kronos context
            flip_point=582.0,
            net_gex=1500000000,
            # Strike selection
            put_short=572.0,
            put_long=570.0,
            call_short=598.0,
            call_long=600.0,
            expiration="2024-12-30",
            # Credits
            estimated_put_credit=0.45,
            estimated_call_credit=0.42,
            total_credit=0.87,
            max_loss=113.0,
            max_profit=87.0,
            # Oracle context (CRITICAL)
            confidence=0.78,
            reasoning="VIX=18.5, GEX-Protected | Oracle: ENTER (78%) | Win Prob: 72% | Top Factor: vix_level",
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_top_factors=[
                {"factor": "vix_level", "impact": 0.35},
                {"factor": "gex_regime", "impact": 0.28},
            ],
            oracle_suggested_sd=1.0,
            oracle_use_gex_walls=True,
            oracle_probabilities={"win": 0.72, "loss": 0.28},
        )

        # Verify all context is captured
        assert signal.flip_point == 582.0
        assert signal.net_gex == 1500000000
        assert signal.oracle_win_probability == 0.72
        assert signal.oracle_advice == "ENTER"
        assert len(signal.oracle_top_factors) == 2
        assert signal.oracle_top_factors[0]["factor"] == "vix_level"
        assert signal.oracle_use_gex_walls is True
        assert "vix_level" in signal.reasoning

    def test_position_stores_oracle_context(self):
        """Verify position stores all Oracle context from signal"""
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        position = IronCondorPosition(
            position_id="FORTRESS-20241230-ABC123",
            ticker="SPY",
            expiration="2024-12-30",
            put_short_strike=572.0,
            put_long_strike=570.0,
            put_credit=0.45,
            call_short_strike=598.0,
            call_long_strike=600.0,
            call_credit=0.42,
            contracts=5,
            spread_width=2.0,
            total_credit=0.87,
            max_loss=565.0,
            max_profit=435.0,
            underlying_at_entry=585.50,
            vix_at_entry=18.5,
            expected_move=8.75,
            call_wall=595.0,
            put_wall=575.0,
            gex_regime="POSITIVE_GAMMA",
            # Kronos context
            flip_point=582.0,
            net_gex=1500000000,
            # Oracle context
            oracle_confidence=0.78,
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_reasoning="VIX=18.5, GEX-Protected | Oracle: ENTER (78%)",
            oracle_top_factors='[{"factor": "vix_level", "impact": 0.35}]',
            oracle_use_gex_walls=True,
            status=PositionStatus.OPEN,
            open_time=datetime.now(CENTRAL_TZ),
        )

        # Verify all context stored
        assert position.flip_point == 582.0
        assert position.net_gex == 1500000000
        assert position.oracle_win_probability == 0.72
        assert position.oracle_advice == "ENTER"
        assert "vix_level" in position.oracle_top_factors
        assert position.oracle_use_gex_walls is True

        # Verify to_dict includes all context
        data = position.to_dict()
        assert data["flip_point"] == 582.0
        assert data["net_gex"] == 1500000000
        assert data["oracle_win_probability"] == 0.72
        assert data["oracle_advice"] == "ENTER"

    @patch("trading.fortress_v2.db.get_connection")
    def test_db_saves_oracle_context(self, mock_get_conn):
        """Verify DB layer saves all Oracle/Kronos columns"""
        from trading.fortress_v2.db import FortressDatabase
        from trading.fortress_v2.models import IronCondorPosition, PositionStatus

        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Create position with full context
        position = IronCondorPosition(
            position_id="FORTRESS-TEST-001",
            ticker="SPY",
            expiration="2024-12-30",
            put_short_strike=572.0,
            put_long_strike=570.0,
            put_credit=0.45,
            call_short_strike=598.0,
            call_long_strike=600.0,
            call_credit=0.42,
            contracts=5,
            spread_width=2.0,
            total_credit=0.87,
            max_loss=565.0,
            max_profit=435.0,
            underlying_at_entry=585.50,
            vix_at_entry=18.5,
            expected_move=8.75,
            # Kronos context
            flip_point=582.0,
            net_gex=1500000000,
            # Oracle context
            oracle_confidence=0.78,
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_reasoning="Test reasoning",
            oracle_top_factors='[{"factor": "vix_level", "impact": 0.35}]',
            oracle_use_gex_walls=True,
            status=PositionStatus.OPEN,
            open_time=datetime.now(CENTRAL_TZ),
        )

        # Save position
        db = FortressDatabase()
        db.save_position(position)

        # Verify INSERT was called with Oracle columns
        insert_call = mock_cursor.execute.call_args_list[-1]
        sql = insert_call[0][0]
        params = insert_call[0][1]

        # Check SQL includes Oracle columns
        assert "flip_point" in sql
        assert "net_gex" in sql
        assert "oracle_win_probability" in sql
        assert "oracle_advice" in sql
        assert "oracle_top_factors" in sql
        assert "oracle_use_gex_walls" in sql

        # Check params include Oracle values
        assert 582.0 in params  # flip_point
        assert 1500000000 in params  # net_gex
        assert 0.72 in params  # oracle_win_probability
        assert "ENTER" in params  # oracle_advice


# =============================================================================
# SOLOMON V2 AUDIT TRAIL TESTS
# =============================================================================

class TestATHENAV2AuditTrail:
    """Test SOLOMON V2 Directional Spreads stores full ML/Kronos context"""

    def test_signal_captures_ml_context(self):
        """Verify signal captures all ML prediction details"""
        from trading.solomon_v2.models import TradeSignal, SpreadType

        signal = TradeSignal(
            direction="BULLISH",
            spread_type=SpreadType.BULL_CALL,
            spot_price=585.50,
            vix=18.5,
            call_wall=595.0,
            put_wall=575.0,
            gex_regime="POSITIVE_GAMMA",
            long_strike=583.0,
            short_strike=585.0,
            expiration="2024-12-30",
            estimated_debit=0.85,
            max_profit=115.0,
            max_loss=85.0,
            rr_ratio=1.35,
            confidence=0.75,
            reasoning="BULLISH near PUT_WALL | ML: 68% win | Top: gex_regime",
            # Kronos context
            flip_point=582.0,
            net_gex=1500000000,
            # ML context
            ml_model_name="directional_xgb_v2",
            ml_win_probability=0.68,
            ml_top_features='[{"feature": "gex_regime", "importance": 0.32}]',
            # Wall proximity
            wall_type="PUT_WALL",
            wall_distance_pct=1.79,
        )

        # Verify all context captured
        assert signal.flip_point == 582.0
        assert signal.net_gex == 1500000000
        assert signal.ml_model_name == "directional_xgb_v2"
        assert signal.ml_win_probability == 0.68
        assert signal.wall_type == "PUT_WALL"
        assert signal.wall_distance_pct == 1.79

    def test_position_stores_ml_context(self):
        """Verify position stores all ML context from signal"""
        from trading.solomon_v2.models import SpreadPosition, SpreadType, PositionStatus

        position = SpreadPosition(
            position_id="SOLOMON-20241230-DEF456",
            spread_type=SpreadType.BULL_CALL,
            ticker="SPY",
            long_strike=583.0,
            short_strike=585.0,
            expiration="2024-12-30",
            entry_debit=0.85,
            contracts=10,
            max_profit=1150.0,
            max_loss=850.0,
            underlying_at_entry=585.50,
            call_wall=595.0,
            put_wall=575.0,
            gex_regime="POSITIVE_GAMMA",
            vix_at_entry=18.5,
            # Kronos context
            flip_point=582.0,
            net_gex=1500000000,
            # ML context
            oracle_confidence=0.75,
            ml_direction="BULLISH",
            ml_confidence=0.75,
            ml_model_name="directional_xgb_v2",
            ml_win_probability=0.68,
            ml_top_features='[{"feature": "gex_regime", "importance": 0.32}]',
            # Wall proximity
            wall_type="PUT_WALL",
            wall_distance_pct=1.79,
            trade_reasoning="BULLISH near PUT_WALL | ML: 68% win",
            status=PositionStatus.OPEN,
            open_time=datetime.now(CENTRAL_TZ),
        )

        # Verify all context stored
        assert position.flip_point == 582.0
        assert position.net_gex == 1500000000
        assert position.ml_model_name == "directional_xgb_v2"
        assert position.ml_win_probability == 0.68
        assert position.wall_type == "PUT_WALL"
        assert position.wall_distance_pct == 1.79
        assert "PUT_WALL" in position.trade_reasoning

    @patch("trading.solomon_v2.db.get_connection")
    def test_db_saves_ml_context(self, mock_get_conn):
        """Verify DB layer saves all ML/Kronos columns"""
        from trading.solomon_v2.db import SolomonDatabase
        from trading.solomon_v2.models import SpreadPosition, SpreadType, PositionStatus

        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        position = SpreadPosition(
            position_id="SOLOMON-TEST-001",
            spread_type=SpreadType.BULL_CALL,
            ticker="SPY",
            long_strike=583.0,
            short_strike=585.0,
            expiration="2024-12-30",
            entry_debit=0.85,
            contracts=10,
            max_profit=1150.0,
            max_loss=850.0,
            underlying_at_entry=585.50,
            # Kronos context
            flip_point=582.0,
            net_gex=1500000000,
            # ML context
            ml_model_name="directional_xgb_v2",
            ml_win_probability=0.68,
            ml_top_features='[{"feature": "gex_regime", "importance": 0.32}]',
            wall_type="PUT_WALL",
            wall_distance_pct=1.79,
            trade_reasoning="Test reasoning",
            status=PositionStatus.OPEN,
            open_time=datetime.now(CENTRAL_TZ),
        )

        db = SolomonDatabase()
        db.save_position(position)

        # Verify INSERT includes ML columns
        insert_call = mock_cursor.execute.call_args_list[-1]
        sql = insert_call[0][0]
        params = insert_call[0][1]

        assert "flip_point" in sql
        assert "net_gex" in sql
        assert "ml_model_name" in sql
        assert "ml_win_probability" in sql
        assert "ml_top_features" in sql
        assert "wall_type" in sql
        assert "wall_distance_pct" in sql
        assert "trade_reasoning" in sql


# =============================================================================
# ANCHOR V2 AUDIT TRAIL TESTS
# =============================================================================

class TestANCHORV2AuditTrail:
    """Test ANCHOR V2 SPX Iron Condor stores full Oracle/Kronos context"""

    def test_signal_captures_oracle_context(self):
        """Verify signal captures all Oracle prediction details"""
        from trading.anchor.models import IronCondorSignal

        signal = IronCondorSignal(
            spot_price=5855.0,
            vix=18.5,
            expected_move=87.5,
            call_wall=5950.0,
            put_wall=5750.0,
            gex_regime="POSITIVE_GAMMA",
            # Kronos context
            flip_point=5820.0,
            net_gex=1500000000,
            # Strikes
            put_short=5720.0,
            put_long=5710.0,
            call_short=5980.0,
            call_long=5990.0,
            expiration="2024-12-30",
            # Credits
            estimated_put_credit=2.50,
            estimated_call_credit=2.30,
            total_credit=4.80,
            max_loss=520.0,
            max_profit=480.0,
            # Signal quality
            confidence=0.78,
            reasoning="SPX VIX=18.5, EM=$88 | GEX-Protected | Oracle: ENTER (78%)",
            # Oracle context
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_top_factors=[
                {"factor": "vix_level", "impact": 0.35},
                {"factor": "gex_regime", "impact": 0.28},
            ],
            oracle_suggested_sd=1.0,
            oracle_use_gex_walls=True,
            oracle_probabilities={"win": 0.72, "loss": 0.28},
        )

        # Verify all context captured
        assert signal.flip_point == 5820.0
        assert signal.net_gex == 1500000000
        assert signal.oracle_win_probability == 0.72
        assert signal.oracle_advice == "ENTER"
        assert len(signal.oracle_top_factors) == 2
        assert signal.oracle_use_gex_walls is True

    def test_position_stores_oracle_context(self):
        """Verify position stores all Oracle context"""
        from trading.anchor.models import IronCondorPosition, PositionStatus

        position = IronCondorPosition(
            position_id="ANCHOR-20241230-GHI789",
            ticker="SPX",
            expiration="2024-12-30",
            put_short_strike=5720.0,
            put_long_strike=5710.0,
            put_credit=2.50,
            call_short_strike=5980.0,
            call_long_strike=5990.0,
            call_credit=2.30,
            contracts=2,
            spread_width=10.0,
            total_credit=4.80,
            max_loss=1040.0,
            max_profit=960.0,
            underlying_at_entry=5855.0,
            vix_at_entry=18.5,
            expected_move=87.5,
            call_wall=5950.0,
            put_wall=5750.0,
            gex_regime="POSITIVE_GAMMA",
            # Kronos context
            flip_point=5820.0,
            net_gex=1500000000,
            # Oracle context
            oracle_confidence=0.78,
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_reasoning="SPX VIX=18.5 | Oracle: ENTER (78%)",
            oracle_top_factors='[{"factor": "vix_level", "impact": 0.35}]',
            oracle_use_gex_walls=True,
            status=PositionStatus.OPEN,
            open_time=datetime.now(CENTRAL_TZ),
        )

        # Verify all context stored
        assert position.flip_point == 5820.0
        assert position.net_gex == 1500000000
        assert position.oracle_win_probability == 0.72
        assert position.oracle_advice == "ENTER"
        assert position.oracle_use_gex_walls is True

        # Verify to_dict includes all context
        data = position.to_dict()
        assert data["flip_point"] == 5820.0
        assert data["net_gex"] == 1500000000
        assert data["oracle_win_probability"] == 0.72

    @patch("trading.anchor.db.get_connection")
    def test_db_saves_oracle_context(self, mock_get_conn):
        """Verify DB layer saves all Oracle/Kronos columns"""
        from trading.anchor.db import AnchorDatabase
        from trading.anchor.models import IronCondorPosition, PositionStatus

        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        position = IronCondorPosition(
            position_id="ANCHOR-TEST-001",
            ticker="SPX",
            expiration="2024-12-30",
            put_short_strike=5720.0,
            put_long_strike=5710.0,
            put_credit=2.50,
            call_short_strike=5980.0,
            call_long_strike=5990.0,
            call_credit=2.30,
            contracts=2,
            spread_width=10.0,
            total_credit=4.80,
            max_loss=1040.0,
            max_profit=960.0,
            underlying_at_entry=5855.0,
            # Kronos context
            flip_point=5820.0,
            net_gex=1500000000,
            # Oracle context
            oracle_confidence=0.78,
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_reasoning="Test reasoning",
            oracle_top_factors='[{"factor": "vix_level", "impact": 0.35}]',
            oracle_use_gex_walls=True,
            status=PositionStatus.OPEN,
            open_time=datetime.now(CENTRAL_TZ),
        )

        db = AnchorDatabase()
        db.save_position(position)

        # Verify INSERT includes Oracle columns
        insert_call = mock_cursor.execute.call_args_list[-1]
        sql = insert_call[0][0]

        assert "flip_point" in sql
        assert "net_gex" in sql
        assert "oracle_win_probability" in sql
        assert "oracle_advice" in sql
        assert "oracle_top_factors" in sql
        assert "oracle_use_gex_walls" in sql


# =============================================================================
# EXECUTOR INTEGRATION TESTS
# =============================================================================

class TestExecutorPassesFullContext:
    """Test that executors pass full context from signal to position"""

    def test_fortress_executor_passes_oracle_context(self):
        """FORTRESS executor should pass all Oracle context to position"""
        from trading.fortress_v2.executor import OrderExecutor
        from trading.fortress_v2.models import FortressConfig, TradingMode, IronCondorSignal

        config = FortressConfig(mode=TradingMode.PAPER)
        executor = OrderExecutor(config)

        signal = IronCondorSignal(
            spot_price=585.50,
            vix=18.5,
            expected_move=8.75,
            call_wall=595.0,
            put_wall=575.0,
            gex_regime="POSITIVE_GAMMA",
            flip_point=582.0,
            net_gex=1500000000,
            put_short=572.0,
            put_long=570.0,
            call_short=598.0,
            call_long=600.0,
            expiration="2024-12-30",
            estimated_put_credit=0.45,
            estimated_call_credit=0.42,
            total_credit=0.87,
            max_loss=113.0,
            max_profit=87.0,
            confidence=0.78,
            reasoning="Test | Oracle: ENTER (78%)",
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_top_factors=[{"factor": "vix_level", "impact": 0.35}],
            oracle_suggested_sd=1.0,
            oracle_use_gex_walls=True,
            oracle_probabilities={"win": 0.72},
        )

        position = executor.execute_iron_condor(signal)

        # Verify position has Oracle context
        assert position is not None
        assert position.flip_point == 582.0
        assert position.net_gex == 1500000000
        assert position.oracle_win_probability == 0.72
        assert position.oracle_advice == "ENTER"
        assert position.oracle_use_gex_walls is True

    def test_solomon_executor_passes_ml_context(self):
        """SOLOMON executor should pass all ML context to position"""
        from trading.solomon_v2.executor import OrderExecutor
        from trading.solomon_v2.models import SolomonConfig, TradingMode, TradeSignal, SpreadType

        config = SolomonConfig(mode=TradingMode.PAPER)
        executor = OrderExecutor(config)

        signal = TradeSignal(
            direction="BULLISH",
            spread_type=SpreadType.BULL_CALL,
            spot_price=585.50,
            vix=18.5,
            call_wall=595.0,
            put_wall=575.0,
            gex_regime="POSITIVE_GAMMA",
            long_strike=583.0,
            short_strike=585.0,
            expiration="2024-12-30",
            estimated_debit=0.85,
            max_profit=115.0,
            max_loss=85.0,
            rr_ratio=1.35,
            confidence=0.75,
            reasoning="BULLISH | ML: 68% win",
            flip_point=582.0,
            net_gex=1500000000,
            ml_model_name="directional_xgb_v2",
            ml_win_probability=0.68,
            ml_top_features='[{"feature": "gex_regime", "importance": 0.32}]',
            wall_type="PUT_WALL",
            wall_distance_pct=1.79,
        )

        position = executor.execute_spread(signal)

        # Verify position has ML context
        assert position is not None
        assert position.flip_point == 582.0
        assert position.net_gex == 1500000000
        assert position.ml_model_name == "directional_xgb_v2"
        assert position.ml_win_probability == 0.68
        assert position.wall_type == "PUT_WALL"
        assert position.wall_distance_pct == 1.79

    def test_anchor_executor_passes_oracle_context(self):
        """ANCHOR executor should pass all Oracle context to position"""
        from trading.anchor.executor import OrderExecutor
        from trading.anchor.models import AnchorConfig, TradingMode, IronCondorSignal

        config = AnchorConfig(mode=TradingMode.PAPER)
        executor = OrderExecutor(config)

        signal = IronCondorSignal(
            spot_price=5855.0,
            vix=18.5,
            expected_move=87.5,
            call_wall=5950.0,
            put_wall=5750.0,
            gex_regime="POSITIVE_GAMMA",
            flip_point=5820.0,
            net_gex=1500000000,
            put_short=5720.0,
            put_long=5710.0,
            call_short=5980.0,
            call_long=5990.0,
            expiration="2024-12-30",
            estimated_put_credit=2.50,
            estimated_call_credit=2.30,
            total_credit=4.80,
            max_loss=520.0,
            max_profit=480.0,
            confidence=0.78,
            reasoning="SPX | Oracle: ENTER (78%)",
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_top_factors=[{"factor": "vix_level", "impact": 0.35}],
            oracle_suggested_sd=1.0,
            oracle_use_gex_walls=True,
            oracle_probabilities={"win": 0.72},
        )

        position = executor.execute_iron_condor(signal)

        # Verify position has Oracle context
        assert position is not None
        assert position.flip_point == 5820.0
        assert position.net_gex == 1500000000
        assert position.oracle_win_probability == 0.72
        assert position.oracle_advice == "ENTER"
        assert position.oracle_use_gex_walls is True


# =============================================================================
# JSON SERIALIZATION TESTS
# =============================================================================

class TestJSONSerialization:
    """Test that top_factors are properly serialized to JSON"""

    def test_ares_top_factors_json(self):
        """FORTRESS should serialize oracle_top_factors to JSON string"""
        from trading.fortress_v2.executor import OrderExecutor
        from trading.fortress_v2.models import FortressConfig, TradingMode, IronCondorSignal

        config = FortressConfig(mode=TradingMode.PAPER)
        executor = OrderExecutor(config)

        signal = IronCondorSignal(
            spot_price=585.50,
            vix=18.5,
            expected_move=8.75,
            call_wall=595.0,
            put_wall=575.0,
            gex_regime="POSITIVE_GAMMA",
            flip_point=582.0,
            net_gex=1500000000,
            put_short=572.0,
            put_long=570.0,
            call_short=598.0,
            call_long=600.0,
            expiration="2024-12-30",
            estimated_put_credit=0.45,
            estimated_call_credit=0.42,
            total_credit=0.87,
            max_loss=113.0,
            max_profit=87.0,
            confidence=0.78,
            reasoning="Test",
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_top_factors=[
                {"factor": "vix_level", "impact": 0.35},
                {"factor": "gex_regime", "impact": 0.28},
            ],
            oracle_suggested_sd=1.0,
            oracle_use_gex_walls=True,
            oracle_probabilities={},
        )

        position = executor.execute_iron_condor(signal)

        # Verify oracle_top_factors is JSON string
        assert isinstance(position.oracle_top_factors, str)
        factors = json.loads(position.oracle_top_factors)
        assert len(factors) == 2
        assert factors[0]["factor"] == "vix_level"

    def test_anchor_top_factors_json(self):
        """ANCHOR should serialize oracle_top_factors to JSON string"""
        from trading.anchor.executor import OrderExecutor
        from trading.anchor.models import AnchorConfig, TradingMode, IronCondorSignal

        config = AnchorConfig(mode=TradingMode.PAPER)
        executor = OrderExecutor(config)

        signal = IronCondorSignal(
            spot_price=5855.0,
            vix=18.5,
            expected_move=87.5,
            call_wall=5950.0,
            put_wall=5750.0,
            gex_regime="POSITIVE_GAMMA",
            flip_point=5820.0,
            net_gex=1500000000,
            put_short=5720.0,
            put_long=5710.0,
            call_short=5980.0,
            call_long=5990.0,
            expiration="2024-12-30",
            estimated_put_credit=2.50,
            estimated_call_credit=2.30,
            total_credit=4.80,
            max_loss=520.0,
            max_profit=480.0,
            confidence=0.78,
            reasoning="Test",
            oracle_win_probability=0.72,
            oracle_advice="ENTER",
            oracle_top_factors=[
                {"factor": "vix_level", "impact": 0.35},
                {"factor": "gex_regime", "impact": 0.28},
            ],
            oracle_suggested_sd=1.0,
            oracle_use_gex_walls=True,
            oracle_probabilities={},
        )

        position = executor.execute_iron_condor(signal)

        # Verify oracle_top_factors is JSON string
        assert isinstance(position.oracle_top_factors, str)
        factors = json.loads(position.oracle_top_factors)
        assert len(factors) == 2
        assert factors[0]["factor"] == "vix_level"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
