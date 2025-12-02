"""
Tests for Autonomous Decision Bridge

Verifies the integration between the autonomous trader and the decision logger.
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.autonomous_decision_bridge import DecisionBridge, get_decision_bridge
from trading.decision_logger import DecisionType, DataSource


class TestDecisionBridge:
    """Test the DecisionBridge class"""

    def test_bridge_creation(self):
        """Test creating a decision bridge"""
        bridge = DecisionBridge()
        assert bridge is not None
        assert bridge.logger is not None

    def test_singleton_bridge(self):
        """Test singleton pattern for bridge"""
        bridge1 = get_decision_bridge()
        bridge2 = get_decision_bridge()
        assert bridge1 is bridge2


class TestTradeExecutionLogging:
    """Test trade execution logging"""

    @pytest.fixture
    def bridge(self):
        return DecisionBridge()

    @pytest.fixture
    def mock_trade_data(self):
        return {
            'symbol': 'SPY',
            'strike': 450.0,
            'dte': 7,
            'option_type': 'call',
            'strategy': 'GEX_MOMENTUM',
            'signal_reason': 'Strong gamma support',
            'confidence': 75,
            'target_pct': 50,
            'stop_pct': 30,
            'expiration': '2024-01-19'
        }

    @pytest.fixture
    def mock_gex_data(self):
        return {
            'spot_price': 455.50,
            'net_gex': 500000000,
            'flip_point': 445.0,
            'call_wall': 460.0,
            'put_wall': 440.0,
            'vix': 15.5,
            'mm_state': 'LONG_GAMMA',
            'trend': 'BULLISH'
        }

    @pytest.fixture
    def mock_option_data(self):
        return {
            'bid': 2.50,
            'ask': 2.60,
            'mid': 2.55,
            'last': 2.52,
            'delta': 0.35,
            'gamma': 0.02,
            'theta': -0.05,
            'iv': 0.18,
            'is_delayed': False
        }

    def test_log_trade_execution(self, bridge, mock_trade_data, mock_gex_data, mock_option_data):
        """Test logging a trade execution"""
        with patch.object(bridge.logger, 'log_decision') as mock_log:
            mock_log.return_value = 'DEC-TEST-001'

            decision_id = bridge.log_trade_execution(
                trade_data=mock_trade_data,
                gex_data=mock_gex_data,
                option_data=mock_option_data,
                contracts=2,
                entry_price=2.55
            )

            assert decision_id == 'DEC-TEST-001'
            mock_log.assert_called_once()

            # Check the decision was built correctly
            logged_decision = mock_log.call_args[0][0]
            assert logged_decision.action == 'BUY'
            assert logged_decision.symbol == 'SPY'
            assert logged_decision.strategy == 'GEX_MOMENTUM'
            assert logged_decision.position_size_contracts == 2
            assert logged_decision.decision_type == DecisionType.ENTRY_SIGNAL

    def test_option_snapshot_created(self, bridge, mock_trade_data, mock_gex_data, mock_option_data):
        """Test that option snapshot includes all pricing data"""
        with patch.object(bridge.logger, 'log_decision') as mock_log:
            mock_log.return_value = 'DEC-TEST-002'

            bridge.log_trade_execution(
                trade_data=mock_trade_data,
                gex_data=mock_gex_data,
                option_data=mock_option_data,
                contracts=1,
                entry_price=2.55
            )

            logged_decision = mock_log.call_args[0][0]
            option_snap = logged_decision.option_snapshot

            assert option_snap.bid == 2.50
            assert option_snap.ask == 2.60
            assert option_snap.price == 2.55
            assert option_snap.strike == 450.0
            assert option_snap.delta == 0.35

    def test_market_context_created(self, bridge, mock_trade_data, mock_gex_data, mock_option_data):
        """Test that market context is captured"""
        with patch.object(bridge.logger, 'log_decision') as mock_log:
            mock_log.return_value = 'DEC-TEST-003'

            bridge.log_trade_execution(
                trade_data=mock_trade_data,
                gex_data=mock_gex_data,
                option_data=mock_option_data,
                contracts=1,
                entry_price=2.55
            )

            logged_decision = mock_log.call_args[0][0]
            context = logged_decision.market_context

            assert context.spot_price == 455.50
            assert context.vix == 15.5
            assert context.net_gex == 500000000
            assert context.flip_point == 445.0


class TestNoTradeLogging:
    """Test logging when no trade is taken"""

    @pytest.fixture
    def bridge(self):
        return DecisionBridge()

    def test_log_no_trade(self, bridge):
        """Test logging a no-trade decision"""
        with patch.object(bridge.logger, 'log_decision') as mock_log:
            mock_log.return_value = 'DEC-SKIP-001'

            decision_id = bridge.log_no_trade(
                symbol='SPY',
                spot_price=450.0,
                reason='Risk limit exceeded',
                gex_data={'vix': 25.0, 'mm_state': 'SHORT_GAMMA'}
            )

            assert decision_id == 'DEC-SKIP-001'

            logged_decision = mock_log.call_args[0][0]
            assert logged_decision.action == 'SKIP'
            assert logged_decision.decision_type == DecisionType.NO_TRADE
            assert logged_decision.passed_risk_checks == False


class TestDataSourceDetection:
    """Test data source detection"""

    @pytest.fixture
    def bridge(self):
        return DecisionBridge()

    def test_detect_delayed_data(self, bridge):
        """Test detection of delayed (historical) data"""
        option_data = {'is_delayed': True}
        source = bridge._determine_option_source(option_data)
        assert source == DataSource.POLYGON_HISTORICAL

    def test_detect_calculated_data(self, bridge):
        """Test detection of calculated data"""
        option_data = {'theoretical_price': 2.50}
        source = bridge._determine_option_source(option_data)
        assert source == DataSource.CALCULATED

    def test_detect_tradier_data(self, bridge):
        """Test detection of Tradier data"""
        option_data = {'from_tradier': True}
        source = bridge._determine_option_source(option_data)
        assert source == DataSource.TRADIER_LIVE

    def test_detect_realtime_default(self, bridge):
        """Test default to realtime"""
        option_data = {}
        source = bridge._determine_option_source(option_data)
        assert source == DataSource.POLYGON_REALTIME


class TestRiskFactorExtraction:
    """Test risk factor extraction"""

    @pytest.fixture
    def bridge(self):
        return DecisionBridge()

    def test_extract_high_vix_risk(self, bridge):
        """Test high VIX is flagged as risk"""
        risks = bridge._extract_risk_factors({}, {'vix': 30})
        assert any('VIX' in r for r in risks)

    def test_extract_short_gamma_risk(self, bridge):
        """Test short gamma is flagged as risk"""
        risks = bridge._extract_risk_factors({}, {'mm_state': 'SHORT_GAMMA'})
        assert any('gamma' in r.lower() for r in risks)

    def test_extract_near_expiration_risk(self, bridge):
        """Test near expiration is flagged"""
        risks = bridge._extract_risk_factors({'near_expiration': True}, {})
        assert any('expiration' in r.lower() for r in risks)


class TestSupportingFactorExtraction:
    """Test supporting factor extraction"""

    @pytest.fixture
    def bridge(self):
        return DecisionBridge()

    def test_extract_strong_signal(self, bridge):
        """Test high signal strength is noted"""
        factors = bridge._extract_supporting_factors({'signal_strength': 85}, {})
        assert any('signal strength' in f.lower() for f in factors)

    def test_extract_positive_gamma(self, bridge):
        """Test positive gamma is noted"""
        factors = bridge._extract_supporting_factors({}, {'mm_state': 'LONG_GAMMA'})
        assert any('gamma' in f.lower() for f in factors)

    def test_extract_psychology_trap(self, bridge):
        """Test psychology trap is noted"""
        factors = bridge._extract_supporting_factors(
            {'psychology_trap': 'Liberation Setup'}, {}
        )
        assert any('psychology' in f.lower() or 'trap' in f.lower() for f in factors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
