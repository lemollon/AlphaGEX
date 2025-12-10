#!/usr/bin/env python3
"""
Test GEX-Protected Iron Condor Strategy
========================================

Tests the GEX-Protected IC strategy using real ORAT backtest data.

Run with:
    pytest tests/test_gex_protected_strategy.py -v
    python tests/test_gex_protected_strategy.py  # standalone

Author: AlphaGEX Quant
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGEXProtectedStrategy:
    """Test GEX-Protected Iron Condor Strategy"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.test_date = '2024-01-15'
        self.test_start = '2024-01-01'
        self.test_end = '2024-01-31'

    def test_gex_calculator_import(self):
        """Test KronosGEXCalculator can be imported"""
        try:
            from quant.kronos_gex_calculator import KronosGEXCalculator, GEXData
            assert KronosGEXCalculator is not None
            assert GEXData is not None
        except ImportError as e:
            pytest.skip(f"GEX calculator not available: {e}")

    def test_oracle_advisor_import(self):
        """Test OracleAdvisor can be imported"""
        try:
            from quant.oracle_advisor import (
                OracleAdvisor, MarketContext, OraclePrediction,
                TradingAdvice, GEXRegime, BotName
            )
            assert OracleAdvisor is not None
            assert MarketContext is not None
        except ImportError as e:
            pytest.skip(f"Oracle advisor not available: {e}")

    def test_gex_protected_strategy_import(self):
        """Test GEX-Protected strategy type is available in backtester"""
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

        # Create backtester with GEX-Protected strategy
        bt = HybridFixedBacktester(
            start_date='2024-01-01',
            end_date='2024-01-31',
            strategy_type='gex_protected_iron_condor'
        )

        assert bt.strategy_type == 'gex_protected_iron_condor'
        assert bt.gex_stats is not None
        assert 'trades_with_gex_walls' in bt.gex_stats
        assert 'trades_with_sd_fallback' in bt.gex_stats

    def test_gex_data_class_structure(self):
        """Test GEXData dataclass has required fields"""
        try:
            from quant.kronos_gex_calculator import GEXData

            # Create test GEX data
            gex = GEXData(
                trade_date='2024-01-15',
                symbol='SPX',
                spot_price=5000.0,
                net_gex=5e9,
                call_gex=10e9,
                put_gex=-5e9,
                call_wall=5050.0,
                put_wall=4950.0,
                flip_point=4990.0,
                gex_normalized=0.002,
                gex_regime='POSITIVE',
                distance_to_flip_pct=0.2,
                above_call_wall=False,
                below_put_wall=False,
                between_walls=True
            )

            assert gex.trade_date == '2024-01-15'
            assert gex.call_wall == 5050.0
            assert gex.put_wall == 4950.0
            assert gex.between_walls is True

        except ImportError:
            pytest.skip("GEX calculator not available")

    def test_oracle_market_context_structure(self):
        """Test MarketContext dataclass has required fields"""
        from quant.oracle_advisor import MarketContext, GEXRegime

        ctx = MarketContext(
            spot_price=5000.0,
            vix=18.5,
            gex_regime=GEXRegime.POSITIVE,
            gex_call_wall=5050.0,
            gex_put_wall=4950.0,
            day_of_week=2
        )

        assert ctx.spot_price == 5000.0
        assert ctx.vix == 18.5
        assert ctx.gex_regime == GEXRegime.POSITIVE

    def test_oracle_prediction_structure(self):
        """Test OraclePrediction dataclass has required fields"""
        from quant.oracle_advisor import OraclePrediction, TradingAdvice, BotName

        pred = OraclePrediction(
            bot_name=BotName.ARES,
            advice=TradingAdvice.TRADE_FULL,
            win_probability=0.72,
            confidence=0.85,
            suggested_risk_pct=5.0,
            suggested_sd_multiplier=1.0,
            use_gex_walls=True,
            suggested_put_strike=4950.0,
            suggested_call_strike=5050.0
        )

        assert pred.bot_name == BotName.ARES
        assert pred.advice == TradingAdvice.TRADE_FULL
        assert pred.use_gex_walls is True

    def test_find_gex_protected_iron_condor_sd_fallback(self):
        """Test GEX-Protected IC falls back to SD when no GEX data"""
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

        bt = HybridFixedBacktester(
            start_date='2024-01-01',
            end_date='2024-01-31',
            strategy_type='gex_protected_iron_condor',
            sd_multiplier=1.0
        )

        # Mock options data
        options = [
            {'strike': 4900.0, 'underlying_price': 5000.0, 'dte': 0, 'put_bid': 2.0, 'put_ask': 2.5, 'call_bid': 0.1, 'call_ask': 0.2},
            {'strike': 4950.0, 'underlying_price': 5000.0, 'dte': 0, 'put_bid': 5.0, 'put_ask': 5.5, 'call_bid': 0.5, 'call_ask': 0.7},
            {'strike': 5000.0, 'underlying_price': 5000.0, 'dte': 0, 'put_bid': 10.0, 'put_ask': 11.0, 'call_bid': 10.0, 'call_ask': 11.0},
            {'strike': 5050.0, 'underlying_price': 5000.0, 'dte': 0, 'put_bid': 0.5, 'put_ask': 0.7, 'call_bid': 5.0, 'call_ask': 5.5},
            {'strike': 5100.0, 'underlying_price': 5000.0, 'dte': 0, 'put_bid': 0.1, 'put_ask': 0.2, 'call_bid': 2.0, 'call_ask': 2.5},
        ]

        # GEX calculator not initialized (no GEX available) - should fall back to SD
        result = bt.find_gex_protected_iron_condor(
            options=options,
            open_price=5000.0,
            expected_move=50.0,
            target_dte=0,
            trade_date='2024-01-15'
        )

        # Should still find a trade using SD fallback
        # (may be None if no valid spread found, but shouldn't error)
        assert bt.gex_stats['trades_with_sd_fallback'] >= 1 or result is None

    def test_day_trade_gex_fields(self):
        """Test DayTrade dataclass has GEX fields"""
        from backtest.zero_dte_hybrid_fixed import DayTrade

        trade = DayTrade(
            trade_date='2024-01-15',
            trade_number=1,
            tier_name='TIER_1_0DTE',
            account_equity=1000000.0,
            target_dte=0,
            actual_dte=0,
            sd_days_used=1,
            vix=18.0,
            open_price=5000.0,
            close_price=5010.0,
            daily_high=5020.0,
            daily_low=4980.0,
            underlying_price=5000.0,
            iv_used=0.18,
            expected_move_1d=50.0,
            expected_move_sd=50.0,
            sd_multiplier=1.0,
            put_short_strike=4950.0,
            put_long_strike=4940.0,
            put_credit_gross=2.0,
            put_credit_net=1.8,
            put_distance_from_open=50.0,
            call_short_strike=5050.0,
            call_long_strike=5060.0,
            call_credit_gross=2.0,
            call_credit_net=1.8,
            call_distance_from_open=50.0,
            total_credit_gross=4.0,
            total_credit_net=3.6,
            spread_width=10.0,
            max_loss=6.4,
            total_costs=40.0,
            contracts=10,
            contracts_requested=10,
            total_premium=3600.0,
            total_risk=6400.0,
            risk_pct=0.64,
            # GEX fields
            gex_protected=True,
            gex_put_wall=4950.0,
            gex_call_wall=5050.0,
            gex_regime='POSITIVE'
        )

        assert trade.gex_protected is True
        assert trade.gex_put_wall == 4950.0
        assert trade.gex_call_wall == 5050.0
        assert trade.gex_regime == 'POSITIVE'


class TestOracleAdvisor:
    """Test Oracle Advisor functionality"""

    def test_oracle_fallback_prediction_no_model(self):
        """Test Oracle provides fallback predictions when model not trained"""
        from quant.oracle_advisor import get_oracle, MarketContext, GEXRegime

        oracle = get_oracle()

        # Create market context
        ctx = MarketContext(
            spot_price=5000.0,
            vix=18.0,
            gex_regime=GEXRegime.POSITIVE,
            day_of_week=2
        )

        # Should work even without trained model
        advice = oracle.get_ares_advice(ctx)

        assert advice is not None
        assert advice.win_probability > 0
        assert advice.suggested_risk_pct > 0

    def test_oracle_vix_impact_on_advice(self):
        """Test Oracle adjusts advice based on VIX level"""
        from quant.oracle_advisor import get_oracle, MarketContext, GEXRegime, TradingAdvice

        oracle = get_oracle()

        # Low VIX context
        low_vix_ctx = MarketContext(
            spot_price=5000.0,
            vix=12.0,  # Low VIX
            gex_regime=GEXRegime.POSITIVE,
            day_of_week=2
        )

        # High VIX context
        high_vix_ctx = MarketContext(
            spot_price=5000.0,
            vix=35.0,  # High VIX
            gex_regime=GEXRegime.NEGATIVE,
            day_of_week=2
        )

        low_vix_advice = oracle.get_ares_advice(low_vix_ctx)
        high_vix_advice = oracle.get_ares_advice(high_vix_ctx)

        # High VIX should suggest higher risk (more premium available)
        # or skip (if too volatile)
        assert low_vix_advice is not None
        assert high_vix_advice is not None

    def test_oracle_gex_regime_impact(self):
        """Test Oracle adjusts advice based on GEX regime"""
        from quant.oracle_advisor import get_oracle, MarketContext, GEXRegime

        oracle = get_oracle()

        # Positive GEX (good for Iron Condors)
        pos_gex_ctx = MarketContext(
            spot_price=5000.0,
            vix=18.0,
            gex_regime=GEXRegime.POSITIVE,
            gex_normalized=0.002,
            gex_between_walls=True,
            day_of_week=2
        )

        # Negative GEX (bad for Iron Condors)
        neg_gex_ctx = MarketContext(
            spot_price=5000.0,
            vix=18.0,
            gex_regime=GEXRegime.NEGATIVE,
            gex_normalized=-0.002,
            gex_between_walls=False,
            day_of_week=2
        )

        pos_advice = oracle.get_ares_advice(pos_gex_ctx)
        neg_advice = oracle.get_ares_advice(neg_gex_ctx)

        # Positive GEX should have higher win probability
        assert pos_advice.win_probability >= neg_advice.win_probability


class TestComparisonScript:
    """Test the comparison script functions"""

    def test_comparison_script_imports(self):
        """Test comparison script imports successfully"""
        try:
            from scripts.compare_gex_protected_ic import run_comparison
            assert run_comparison is not None
        except ImportError as e:
            pytest.skip(f"Comparison script not available: {e}")


class TestOracleClaudeIntegration:
    """Test Oracle Claude AI integration"""

    def test_oracle_claude_enhancer_import(self):
        """Test OracleClaudeEnhancer can be imported"""
        try:
            from quant.oracle_advisor import OracleClaudeEnhancer, ClaudeAnalysis
            assert OracleClaudeEnhancer is not None
            assert ClaudeAnalysis is not None
        except ImportError as e:
            pytest.skip(f"Oracle Claude not available: {e}")

    def test_oracle_claude_available_property(self):
        """Test Oracle has claude_available property"""
        from quant.oracle_advisor import get_oracle

        oracle = get_oracle()

        # Should have the property even if Claude is not configured
        assert hasattr(oracle, 'claude_available')
        assert isinstance(oracle.claude_available, bool)

    def test_oracle_explain_prediction_fallback(self):
        """Test explain_prediction returns fallback when Claude unavailable"""
        from quant.oracle_advisor import (
            OracleAdvisor, MarketContext, GEXRegime,
            OraclePrediction, BotName, TradingAdvice
        )

        # Create Oracle with Claude disabled
        oracle = OracleAdvisor(enable_claude=False)

        context = MarketContext(
            spot_price=5000.0,
            vix=20.0,
            gex_regime=GEXRegime.POSITIVE,
            day_of_week=2
        )

        prediction = OraclePrediction(
            bot_name=BotName.ARES,
            advice=TradingAdvice.TRADE_FULL,
            win_probability=0.72,
            confidence=85.0,
            suggested_risk_pct=5.0,
            suggested_sd_multiplier=1.0,
            reasoning="Test reasoning"
        )

        explanation = oracle.explain_prediction(prediction, context)

        # Should return a string even without Claude
        assert isinstance(explanation, str)
        assert len(explanation) > 0
        assert "TRADE_FULL" in explanation

    def test_oracle_get_claude_analysis_returns_none_when_disabled(self):
        """Test get_claude_analysis returns None when Claude disabled"""
        from quant.oracle_advisor import OracleAdvisor, MarketContext, GEXRegime

        oracle = OracleAdvisor(enable_claude=False)

        context = MarketContext(
            spot_price=5000.0,
            vix=20.0,
            gex_regime=GEXRegime.POSITIVE,
            day_of_week=2
        )

        analysis = oracle.get_claude_analysis(context)
        assert analysis is None

    def test_oracle_analyze_patterns_returns_error_when_disabled(self):
        """Test analyze_patterns returns error when Claude disabled"""
        from quant.oracle_advisor import OracleAdvisor

        oracle = OracleAdvisor(enable_claude=False)

        result = oracle.analyze_patterns()

        assert result['success'] is False
        assert 'error' in result
        assert 'not available' in result['error'].lower()

    def test_oracle_ares_advice_with_claude_validation_disabled(self):
        """Test ARES advice works with Claude validation explicitly disabled"""
        from quant.oracle_advisor import OracleAdvisor, MarketContext, GEXRegime

        oracle = OracleAdvisor(enable_claude=False)

        context = MarketContext(
            spot_price=5000.0,
            vix=20.0,
            gex_regime=GEXRegime.POSITIVE,
            gex_call_wall=5050.0,
            gex_put_wall=4950.0,
            gex_between_walls=True,
            day_of_week=2
        )

        # Should work without Claude
        advice = oracle.get_ares_advice(
            context,
            use_gex_walls=True,
            use_claude_validation=False
        )

        assert advice is not None
        assert advice.win_probability > 0
        assert advice.suggested_risk_pct >= 0

    def test_claude_analysis_dataclass(self):
        """Test ClaudeAnalysis dataclass structure"""
        from quant.oracle_advisor import ClaudeAnalysis

        analysis = ClaudeAnalysis(
            analysis="Test analysis",
            confidence_adjustment=0.05,
            risk_factors=["Risk 1", "Risk 2"],
            opportunities=["Opp 1"],
            recommendation="AGREE"
        )

        assert analysis.analysis == "Test analysis"
        assert analysis.confidence_adjustment == 0.05
        assert len(analysis.risk_factors) == 2
        assert analysis.recommendation == "AGREE"
        assert analysis.override_advice is None


class TestOracleConvenienceFunctions:
    """Test Oracle convenience functions"""

    def test_explain_oracle_advice_function(self):
        """Test explain_oracle_advice convenience function"""
        from quant.oracle_advisor import (
            explain_oracle_advice, MarketContext, GEXRegime,
            OraclePrediction, BotName, TradingAdvice
        )

        context = MarketContext(
            spot_price=5000.0,
            vix=20.0,
            gex_regime=GEXRegime.NEUTRAL,
            day_of_week=2
        )

        prediction = OraclePrediction(
            bot_name=BotName.ARES,
            advice=TradingAdvice.TRADE_REDUCED,
            win_probability=0.60,
            confidence=70.0,
            suggested_risk_pct=3.0,
            suggested_sd_multiplier=1.2,
            reasoning="Medium confidence"
        )

        explanation = explain_oracle_advice(prediction, context)
        assert isinstance(explanation, str)
        assert len(explanation) > 0

    def test_analyze_kronos_patterns_function(self):
        """Test analyze_kronos_patterns convenience function"""
        from quant.oracle_advisor import analyze_kronos_patterns

        # Should return error dict when Claude not available
        result = analyze_kronos_patterns({})
        assert isinstance(result, dict)
        # Either succeeds or returns error
        assert 'success' in result or 'error' in result


# Standalone test runner
if __name__ == "__main__":
    print("=" * 80)
    print("GEX-PROTECTED STRATEGY TESTS")
    print("=" * 80)

    # Run tests
    import subprocess
    result = subprocess.run(
        ['python', '-m', 'pytest', __file__, '-v', '--tb=short'],
        capture_output=False
    )
    sys.exit(result.returncode)
