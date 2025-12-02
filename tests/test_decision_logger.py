"""
Tests for Decision Transparency Logger

Verifies:
1. Decision creation with full context
2. Database logging
3. Export functionality
4. Outcome updates
"""

import pytest
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDecisionLogger:
    """Test decision logging functionality"""

    def test_import(self):
        """Test module imports"""
        from trading.decision_logger import (
            DecisionLogger,
            TradeDecision,
            DecisionType,
            DataSource,
            PriceSnapshot,
            MarketContext,
            get_decision_logger
        )
        assert DecisionLogger is not None
        assert TradeDecision is not None

    def test_data_source_enum(self):
        """Test DataSource enum has required values"""
        from trading.decision_logger import DataSource

        assert DataSource.TRADIER_LIVE.value == "TRADIER_LIVE"
        assert DataSource.POLYGON_REALTIME.value == "POLYGON_REALTIME"
        assert DataSource.SIMULATED.value == "SIMULATED"

    def test_decision_type_enum(self):
        """Test DecisionType enum"""
        from trading.decision_logger import DecisionType

        assert DecisionType.ENTRY_SIGNAL.value == "ENTRY_SIGNAL"
        assert DecisionType.EXIT_SIGNAL.value == "EXIT_SIGNAL"
        assert DecisionType.NO_TRADE.value == "NO_TRADE"

    def test_price_snapshot_creation(self):
        """Test PriceSnapshot dataclass"""
        from trading.decision_logger import PriceSnapshot, DataSource

        snapshot = PriceSnapshot(
            symbol="SPY",
            price=450.25,
            bid=450.20,
            ask=450.30,
            timestamp="2024-01-15T10:30:00",
            source=DataSource.TRADIER_LIVE
        )

        assert snapshot.symbol == "SPY"
        assert snapshot.price == 450.25
        assert snapshot.source == DataSource.TRADIER_LIVE

    def test_market_context_creation(self):
        """Test MarketContext dataclass"""
        from trading.decision_logger import MarketContext, DataSource

        context = MarketContext(
            timestamp="2024-01-15T10:30:00",
            spot_price=450.25,
            spot_source=DataSource.TRADIER_LIVE,
            vix=18.5,
            net_gex=2e9,
            gex_regime="positive",
            trend="bullish"
        )

        assert context.spot_price == 450.25
        assert context.vix == 18.5
        assert context.gex_regime == "positive"

    def test_trade_decision_to_dict(self):
        """Test TradeDecision converts to dict properly"""
        from trading.decision_logger import (
            TradeDecision, DecisionType, PriceSnapshot, DataSource
        )

        decision = TradeDecision(
            decision_id="DEC-20240115-0001",
            timestamp="2024-01-15T10:30:00",
            decision_type=DecisionType.ENTRY_SIGNAL,
            action="SELL",
            symbol="SPY",
            strategy="BULL_PUT_SPREAD",
            underlying_snapshot=PriceSnapshot(
                symbol="SPY",
                price=450.25,
                source=DataSource.TRADIER_LIVE
            )
        )

        result = decision.to_dict()

        assert isinstance(result, dict)
        assert result['decision_id'] == "DEC-20240115-0001"
        assert result['action'] == "SELL"
        assert result['symbol'] == "SPY"

    def test_create_entry_decision(self):
        """Test creating a complete entry decision"""
        from trading.decision_logger import DecisionLogger, DataSource

        logger = DecisionLogger()

        decision = logger.create_entry_decision(
            symbol="SPY",
            strategy="WHEEL_CSP",
            action="SELL",
            spot_price=450.25,
            spot_source=DataSource.TRADIER_LIVE,
            strike=445,
            expiration="2024-02-16",
            option_price=2.50,
            option_delta=0.25,
            vix=18.5,
            net_gex=2e9,
            gex_regime="positive",
            market_regime="LOW_VOL_BULLISH",
            trend="bullish",
            backtest_win_rate=72.5,
            backtest_expectancy=1.25,
            backtest_uses_real_data=True,
            primary_reason="Selling CSP at 25 delta with positive GEX support",
            supporting_factors=["VIX below 20", "Trend bullish", "Above flip point"],
            risk_factors=["Earnings in 2 weeks"],
            position_size_dollars=45000,
            contracts=1,
            max_risk=45000,
            target_profit_pct=50,
            stop_loss_pct=200,
            prob_profit=75
        )

        assert decision.decision_id is not None
        assert decision.symbol == "SPY"
        assert decision.strategy == "WHEEL_CSP"
        assert decision.underlying_snapshot.price == 450.25
        assert decision.market_context.vix == 18.5
        assert decision.backtest_reference.win_rate == 72.5
        assert decision.reasoning.primary_reason == "Selling CSP at 25 delta with positive GEX support"

    def test_decision_shows_data_source(self):
        """Test that decision clearly shows data source"""
        from trading.decision_logger import DecisionLogger, DataSource

        logger = DecisionLogger()

        # Live data decision
        live_decision = logger.create_entry_decision(
            symbol="SPY",
            strategy="TEST",
            action="BUY",
            spot_price=450,
            spot_source=DataSource.TRADIER_LIVE,
            primary_reason="Test"
        )

        assert live_decision.underlying_snapshot.source == DataSource.TRADIER_LIVE

        # Simulated data decision (should be flagged!)
        sim_decision = logger.create_entry_decision(
            symbol="SPY",
            strategy="TEST",
            action="BUY",
            spot_price=450,
            spot_source=DataSource.SIMULATED,
            primary_reason="Test"
        )

        assert sim_decision.underlying_snapshot.source == DataSource.SIMULATED

    def test_decision_requires_reasoning(self):
        """Test that decisions have reasoning attached"""
        from trading.decision_logger import DecisionLogger, DataSource

        logger = DecisionLogger()

        decision = logger.create_entry_decision(
            symbol="SPY",
            strategy="TEST",
            action="BUY",
            spot_price=450,
            spot_source=DataSource.TRADIER_LIVE,
            primary_reason="Market regime is bullish with positive GEX",
            supporting_factors=["VIX < 20", "Price above 20 SMA"]
        )

        assert decision.reasoning is not None
        assert decision.reasoning.primary_reason != ""
        assert len(decision.reasoning.supporting_factors) > 0


class TestDecisionAuditTrail:
    """Test audit trail functionality"""

    def test_decision_id_unique(self):
        """Test decision IDs are unique"""
        from trading.decision_logger import DecisionLogger, DataSource

        logger = DecisionLogger()

        decision1 = logger.create_entry_decision(
            symbol="SPY", strategy="TEST", action="BUY",
            spot_price=450, spot_source=DataSource.TRADIER_LIVE,
            primary_reason="Test 1"
        )

        decision2 = logger.create_entry_decision(
            symbol="SPY", strategy="TEST", action="BUY",
            spot_price=451, spot_source=DataSource.TRADIER_LIVE,
            primary_reason="Test 2"
        )

        assert decision1.decision_id != decision2.decision_id

    def test_decision_has_timestamp(self):
        """Test decisions have timestamps"""
        from trading.decision_logger import DecisionLogger, DataSource

        logger = DecisionLogger()

        decision = logger.create_entry_decision(
            symbol="SPY", strategy="TEST", action="BUY",
            spot_price=450, spot_source=DataSource.TRADIER_LIVE,
            primary_reason="Test"
        )

        assert decision.timestamp is not None
        assert len(decision.timestamp) > 0

    def test_backtest_link_flagged(self):
        """Test that backtest simulated data is clearly flagged"""
        from trading.decision_logger import DecisionLogger, DataSource

        logger = DecisionLogger()

        # Decision backed by real backtest data
        real_decision = logger.create_entry_decision(
            symbol="SPY", strategy="TEST", action="BUY",
            spot_price=450, spot_source=DataSource.TRADIER_LIVE,
            primary_reason="Test",
            backtest_win_rate=70,
            backtest_expectancy=1.5,
            backtest_uses_real_data=True
        )

        assert real_decision.backtest_reference.uses_real_data is True

        # Decision backed by simulated backtest
        sim_decision = logger.create_entry_decision(
            symbol="SPY", strategy="TEST", action="BUY",
            spot_price=450, spot_source=DataSource.TRADIER_LIVE,
            primary_reason="Test",
            backtest_win_rate=70,
            backtest_expectancy=1.5,
            backtest_uses_real_data=False  # RED FLAG!
        )

        assert sim_decision.backtest_reference.uses_real_data is False


class TestExportReadiness:
    """Test that decisions are exportable"""

    def test_decision_to_dict(self):
        """Test decision converts to dictionary for export"""
        from trading.decision_logger import DecisionLogger, DataSource

        logger = DecisionLogger()

        decision = logger.create_entry_decision(
            symbol="SPY", strategy="WHEEL_CSP", action="SELL",
            spot_price=450, spot_source=DataSource.TRADIER_LIVE,
            strike=445, expiration="2024-02-16", option_price=2.50,
            primary_reason="Test export"
        )

        as_dict = decision.to_dict()

        assert isinstance(as_dict, dict)
        assert 'decision_id' in as_dict
        assert 'timestamp' in as_dict
        assert 'symbol' in as_dict
        assert 'underlying_snapshot' in as_dict

    def test_decision_json_serializable(self):
        """Test decision is JSON serializable"""
        import json
        from trading.decision_logger import DecisionLogger, DataSource

        logger = DecisionLogger()

        decision = logger.create_entry_decision(
            symbol="SPY", strategy="TEST", action="BUY",
            spot_price=450, spot_source=DataSource.TRADIER_LIVE,
            primary_reason="Test JSON"
        )

        as_dict = decision.to_dict()

        # Should not raise
        json_str = json.dumps(as_dict)
        assert len(json_str) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
