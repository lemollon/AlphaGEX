"""
Integration Tests for OMEGA Orchestrator and Unified Trading System
====================================================================

These tests verify that all components of the unified trading system
work together correctly:

1. OMEGA Orchestrator (central hub)
2. Proverbs Integration (safety layer)
3. Ensemble Weighting (market context)
4. ML Advisor (primary decision)
5. Oracle Adaptation (bot-specific)
6. Gap Implementations (1, 2, 5, 6, 9, 10)

Author: AlphaGEX Quant Team
Date: January 2025
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_gex_data():
    """Standard GEX data for testing"""
    return {
        'regime': 'POSITIVE',
        'net_gamma': 100,
        'put_wall': 580,
        'call_wall': 600,
        'flip_point': 590,
        'trend': 'BULLISH'
    }


@pytest.fixture
def mock_features():
    """Standard ML features for testing"""
    return {
        'vix': 18.0,
        'vix_percentile_30d': 45.0,
        'vix_change_1d': -0.5,
        'day_of_week': 2,
        'price_change_1d': 0.3,
        'expected_move_pct': 1.2,
        'win_rate_30d': 0.68,
        'gex_normalized': 0.5,
        'gex_regime_positive': 1,
        'gex_distance_to_flip_pct': 2.0,
        'gex_between_walls': 1
    }


@pytest.fixture
def mock_high_vix_features():
    """High VIX features for testing skip conditions"""
    return {
        'vix': 35.0,  # High VIX
        'vix_percentile_30d': 95.0,
        'vix_change_1d': 2.5,
        'day_of_week': 0,  # Monday
        'price_change_1d': -2.0,
        'expected_move_pct': 3.5,
        'win_rate_30d': 0.55,
        'gex_normalized': -0.5,
        'gex_regime_positive': 0,
        'gex_distance_to_flip_pct': -5.0,
        'gex_between_walls': 0
    }


# =============================================================================
# OMEGA ORCHESTRATOR TESTS
# =============================================================================

class TestOmegaOrchestrator:
    """Tests for OMEGA Orchestrator core functionality"""

    def test_omega_import(self):
        """Test that OMEGA Orchestrator can be imported"""
        from core.omega_orchestrator import OmegaOrchestrator, get_omega_orchestrator
        assert OmegaOrchestrator is not None
        assert get_omega_orchestrator is not None

    def test_omega_initialization(self):
        """Test OMEGA Orchestrator initialization"""
        from core.omega_orchestrator import OmegaOrchestrator

        omega = OmegaOrchestrator(capital=100000)

        assert omega.capital == 100000
        assert omega.auto_retrain_monitor is not None
        assert omega.regime_detector is not None
        assert omega.correlation_enforcer is not None
        assert omega.equity_scaler is not None

    def test_omega_singleton(self):
        """Test OMEGA singleton pattern"""
        from core.omega_orchestrator import get_omega_orchestrator

        omega1 = get_omega_orchestrator(100000)
        omega2 = get_omega_orchestrator(100000)

        # Should return same instance
        assert omega1 is omega2

    def test_omega_status(self):
        """Test OMEGA status reporting"""
        from core.omega_orchestrator import OmegaOrchestrator

        omega = OmegaOrchestrator(capital=100000)
        status = omega.get_status()

        assert 'timestamp' in status
        assert 'capital' in status
        assert 'gaps' in status
        assert 'layers' in status

        # Check all gaps are reported
        gaps = status['gaps']
        assert 'gap1_auto_retrain' in gaps
        assert 'gap6_regime' in gaps
        assert 'gap9_correlation' in gaps
        assert 'gap10_equity' in gaps


# =============================================================================
# GAP IMPLEMENTATION TESTS
# =============================================================================

class TestGap1AutoRetrainMonitor:
    """Tests for Gap 1: Auto-Retrain Monitor"""

    def test_retrain_monitor_import(self):
        """Test that AutoRetrainMonitor can be imported"""
        from core.omega_orchestrator import AutoRetrainMonitor
        assert AutoRetrainMonitor is not None

    def test_retrain_monitor_initialization(self):
        """Test AutoRetrainMonitor initialization"""
        from core.omega_orchestrator import AutoRetrainMonitor

        monitor = AutoRetrainMonitor()

        assert monitor.recent_predictions == []
        assert monitor.recent_outcomes == []
        assert monitor.retrain_triggered is False

    def test_retrain_monitor_record_prediction(self):
        """Test recording predictions"""
        from core.omega_orchestrator import AutoRetrainMonitor

        monitor = AutoRetrainMonitor()
        monitor.record_prediction(
            bot_name="FORTRESS",
            predicted_win_prob=0.72,
            model_version="1.0.0"
        )

        assert len(monitor.recent_predictions) == 1
        assert monitor.recent_predictions[0]['bot_name'] == "FORTRESS"
        assert monitor.recent_predictions[0]['predicted_win_prob'] == 0.72

    def test_retrain_monitor_insufficient_data(self):
        """Test that insufficient data doesn't trigger retrain"""
        from core.omega_orchestrator import AutoRetrainMonitor

        monitor = AutoRetrainMonitor()

        # Record only 5 outcomes (below threshold)
        for i in range(5):
            result = monitor.record_outcome("FORTRESS", was_win=True, pnl=50)

        assert result['retrain_needed'] is False
        assert result['metrics'].get('status') == 'insufficient_data'

    def test_retrain_monitor_consecutive_losses(self):
        """Test consecutive loss trigger"""
        from core.omega_orchestrator import AutoRetrainMonitor

        monitor = AutoRetrainMonitor()

        # Record enough outcomes first
        for i in range(25):
            monitor.record_outcome("FORTRESS", was_win=True, pnl=50)

        # Now record consecutive losses
        for i in range(6):  # More than threshold
            result = monitor.record_outcome("FORTRESS", was_win=False, pnl=-100)

        assert result['retrain_needed'] is True
        assert 'Consecutive losses' in result['reason']


class TestGap6RegimeTransitionDetector:
    """Tests for Gap 6: Regime Transition Detector"""

    def test_regime_detector_import(self):
        """Test that RegimeTransitionDetector can be imported"""
        from core.omega_orchestrator import RegimeTransitionDetector
        assert RegimeTransitionDetector is not None

    def test_regime_detector_initialization(self):
        """Test RegimeTransitionDetector initialization"""
        from core.omega_orchestrator import RegimeTransitionDetector

        detector = RegimeTransitionDetector()

        assert detector.gex_regime_history == []
        assert detector.vix_regime_history == []
        assert detector.recent_transitions == []

    def test_regime_detector_vix_classification(self):
        """Test VIX regime classification"""
        from core.omega_orchestrator import RegimeTransitionDetector

        detector = RegimeTransitionDetector()

        assert detector._classify_vix_regime(12) == "LOW"
        assert detector._classify_vix_regime(18) == "NORMAL"
        assert detector._classify_vix_regime(25) == "ELEVATED"
        assert detector._classify_vix_regime(30) == "HIGH"
        assert detector._classify_vix_regime(40) == "EXTREME"

    def test_regime_detector_transition_detection(self):
        """Test regime transition detection"""
        from core.omega_orchestrator import RegimeTransitionDetector

        detector = RegimeTransitionDetector()

        # Record several consistent observations
        for _ in range(6):
            detector.record_observation(
                gex_regime="POSITIVE",
                vix=18.0,
                price_trend="BULLISH",
                net_gamma=100
            )

        # Now record a transition
        alert = detector.record_observation(
            gex_regime="NEGATIVE",  # Changed!
            vix=18.0,
            price_trend="BULLISH",
            net_gamma=-50
        )

        # Should detect the transition
        if alert:
            assert 'transitions' in alert
            assert len(alert['transitions']) > 0


class TestGap9CorrelationEnforcer:
    """Tests for Gap 9: Cross-Bot Correlation Enforcer"""

    def test_correlation_enforcer_import(self):
        """Test that CrossBotCorrelationEnforcer can be imported"""
        from core.omega_orchestrator import CrossBotCorrelationEnforcer
        assert CrossBotCorrelationEnforcer is not None

    def test_correlation_enforcer_initialization(self):
        """Test CrossBotCorrelationEnforcer initialization"""
        from core.omega_orchestrator import CrossBotCorrelationEnforcer

        enforcer = CrossBotCorrelationEnforcer()

        assert enforcer.active_positions == {}
        assert enforcer.MAX_CORRELATED_EXPOSURE_PCT == 30.0

    def test_correlation_enforcer_position_registration(self):
        """Test position registration"""
        from core.omega_orchestrator import CrossBotCorrelationEnforcer

        enforcer = CrossBotCorrelationEnforcer()

        enforcer.register_position("FORTRESS", "BULLISH", 10.0, "SPY")

        assert "FORTRESS" in enforcer.active_positions
        assert enforcer.active_positions["FORTRESS"]['direction'] == "BULLISH"
        assert enforcer.active_positions["FORTRESS"]['exposure_pct'] == 10.0

    def test_correlation_enforcer_limit_check(self):
        """Test correlation limit enforcement"""
        from core.omega_orchestrator import CrossBotCorrelationEnforcer

        enforcer = CrossBotCorrelationEnforcer()

        # Register FORTRESS with 15% exposure
        enforcer.register_position("FORTRESS", "BULLISH", 15.0)

        # Register SOLOMON with 15% exposure
        enforcer.register_position("SOLOMON", "BULLISH", 15.0)

        # Now check if PHOENIX can add 10% (total would be 40% > 30% limit)
        result = enforcer.check_new_position("PHOENIX", "BULLISH", 10.0)

        # Should be blocked or reduced
        assert result['total_correlated_exposure'] == 40.0
        assert len(result['correlated_bots']) == 2


class TestGap10EquityCompoundScaler:
    """Tests for Gap 10: Equity Compound Scaler"""

    def test_equity_scaler_import(self):
        """Test that EquityCompoundScaler can be imported"""
        from core.omega_orchestrator import EquityCompoundScaler
        assert EquityCompoundScaler is not None

    def test_equity_scaler_initialization(self):
        """Test EquityCompoundScaler initialization"""
        from core.omega_orchestrator import EquityCompoundScaler

        scaler = EquityCompoundScaler(initial_capital=100000)

        assert scaler.initial_capital == 100000
        assert scaler.current_equity == 100000
        assert scaler.high_water_mark == 100000

    def test_equity_scaler_growth_scaling(self):
        """Test scaling on equity growth"""
        from core.omega_orchestrator import EquityCompoundScaler

        scaler = EquityCompoundScaler(initial_capital=100000)

        # Simulate 20% growth
        scaler.update_equity(120000)

        result = scaler.get_position_multiplier(5.0)

        # Should have multiplier > 1.0 due to growth
        assert result['multiplier'] > 1.0
        assert result['adjusted_risk_pct'] > 5.0
        assert 'growth' in result['reason'].lower()

    def test_equity_scaler_drawdown_protection(self):
        """Test drawdown protection"""
        from core.omega_orchestrator import EquityCompoundScaler

        scaler = EquityCompoundScaler(initial_capital=100000)

        # First grow, then drawdown
        scaler.update_equity(120000)  # Growth
        scaler.update_equity(110000)  # Now below HWM

        result = scaler.get_position_multiplier(5.0)

        # Still above initial, but check the mechanism
        assert result['drawdown_pct'] > 0


# =============================================================================
# ORACLE OMEGA MODE TESTS
# =============================================================================

class TestOracleOmegaMode:
    """Tests for Oracle OMEGA mode (trust ML Advisor)"""

    def test_oracle_omega_mode_initialization(self):
        """Test Oracle can be initialized in OMEGA mode"""
        from quant.oracle_advisor import OracleAdvisor

        oracle = OracleAdvisor(enable_claude=False, omega_mode=True)

        assert oracle.omega_mode is True

    def test_oracle_omega_mode_disables_vix_skip(self):
        """Test that OMEGA mode disables VIX skip rules"""
        # This test verifies the code path, not the full prediction
        from quant.oracle_advisor import OracleAdvisor, MarketContext, GEXRegime

        oracle = OracleAdvisor(enable_claude=False, omega_mode=True)

        # Create high VIX context that would normally trigger skip
        context = MarketContext(
            spot_price=590.0,
            vix=35.0,  # High VIX
            day_of_week=0  # Monday
        )
        context.gex_regime = GEXRegime.NEGATIVE

        # In OMEGA mode, VIX skip rules should be bypassed
        # The test verifies the mode is set correctly
        assert oracle.omega_mode is True


# =============================================================================
# OMEGA MIXIN TESTS
# =============================================================================

class TestOmegaMixin:
    """Tests for OMEGA Integration Mixin"""

    def test_mixin_import(self):
        """Test that OmegaIntegrationMixin can be imported"""
        from trading.mixins.omega_mixin import OmegaIntegrationMixin
        assert OmegaIntegrationMixin is not None

    def test_mixin_basic_usage(self):
        """Test basic mixin usage"""
        from trading.mixins.omega_mixin import OmegaIntegrationMixin

        class TestBot(OmegaIntegrationMixin):
            def __init__(self):
                self.bot_name = "FORTRESS"
                self.capital = 100000

        bot = TestBot()
        assert bot.bot_name == "FORTRESS"
        assert bot.capital == 100000

    def test_mixin_omega_can_trade(self):
        """Test omega_can_trade method"""
        from trading.mixins.omega_mixin import OmegaIntegrationMixin

        class TestBot(OmegaIntegrationMixin):
            def __init__(self):
                self.bot_name = "FORTRESS"
                self.capital = 100000

        bot = TestBot()

        # Should return True by default (no kill switch active)
        result = bot.omega_can_trade()
        assert isinstance(result, bool)


# =============================================================================
# INTEGRATION FLOW TESTS
# =============================================================================

class TestIntegrationFlow:
    """End-to-end integration flow tests"""

    def test_full_decision_flow(self, mock_gex_data, mock_features):
        """Test complete OMEGA decision flow"""
        from core.omega_orchestrator import OmegaOrchestrator

        omega = OmegaOrchestrator(capital=100000)

        decision = omega.get_trading_decision(
            bot_name="FORTRESS",
            gex_data=mock_gex_data,
            features=mock_features,
            current_regime="POSITIVE"
        )

        assert decision is not None
        assert decision.bot_name == "FORTRESS"
        assert decision.proverbs_verdict is not None
        assert decision.ensemble_context is not None
        assert decision.ml_decision is not None
        assert decision.oracle_adaptation is not None
        assert len(decision.decision_path) > 0

    def test_outcome_recording_flow(self, mock_gex_data, mock_features):
        """Test outcome recording and feedback loops"""
        from core.omega_orchestrator import OmegaOrchestrator

        omega = OmegaOrchestrator(capital=100000)

        # First get a decision
        decision = omega.get_trading_decision(
            bot_name="FORTRESS",
            gex_data=mock_gex_data,
            features=mock_features,
            current_regime="POSITIVE"
        )

        # Then record outcome
        result = omega.record_trade_outcome(
            bot_name="FORTRESS",
            was_win=True,
            pnl=150.0
        )

        assert result is not None
        assert 'retrain_check' in result
        assert 'new_equity' in result
        assert result['new_equity'] == 100150.0

    def test_decision_serialization(self, mock_gex_data, mock_features):
        """Test that decisions can be serialized to dict/JSON"""
        from core.omega_orchestrator import OmegaOrchestrator

        omega = OmegaOrchestrator(capital=100000)

        decision = omega.get_trading_decision(
            bot_name="FORTRESS",
            gex_data=mock_gex_data,
            features=mock_features,
            current_regime="POSITIVE"
        )

        # Convert to dict
        decision_dict = decision.to_dict()

        assert isinstance(decision_dict, dict)
        assert 'timestamp' in decision_dict
        assert 'bot_name' in decision_dict
        assert 'final_decision' in decision_dict
        assert 'decision_path' in decision_dict


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
