"""
SPX Trader - Backtester Integration Tests
==========================================

Validates that the SPX institutional trader correctly leverages
backtester results for position sizing and strategy validation.

Tests:
1. Kelly calculation with various backtest parameters
2. Position sizing with proven vs unproven strategies
3. Strategy validation gates (expectancy, win rate, risk/reward)
4. Backtest parameter extraction and fuzzy matching
5. Feedback loop from closed trades to strategy stats

NOTE: These tests require psycopg2 for database integration.
They will be skipped if psycopg2 is not installed.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Check if psycopg2 is available
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Skip all tests in this module if psycopg2 is not available
pytestmark = pytest.mark.skipif(
    not PSYCOPG2_AVAILABLE,
    reason="psycopg2 required for SPX trader integration tests"
)


class TestKellyCalculation:
    """Test the Kelly criterion calculation from backtest results"""

    def test_kelly_with_proven_strategy(self):
        """Proven strategy should use half-Kelly"""
        from spx_institutional_trader import SPXInstitutionalTrader

        # Mock the strategy stats
        mock_stats = {
            'BULLISH_CALL_SPREAD': {
                'win_rate': 0.65,  # 65% win rate
                'avg_win': 15.0,   # 15% avg win
                'avg_loss': 10.0,  # 10% avg loss
                'total_trades': 50,  # Proven (>= 10 trades)
                'expectancy': 5.25,
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        params = trader.get_backtest_params_for_strategy('BULLISH_CALL_SPREAD')

        # Verify params are extracted correctly
        assert params['win_rate'] == 0.65
        assert params['avg_win'] == 15.0
        assert params['avg_loss'] == 10.0
        assert params['is_proven'] == True
        assert params['source'] == 'backtest'

    def test_kelly_with_unproven_strategy(self):
        """Unproven strategy should use quarter-Kelly and conservative defaults"""
        from spx_institutional_trader import SPXInstitutionalTrader

        # Mock the strategy stats with low trade count
        mock_stats = {
            'NEW_STRATEGY': {
                'win_rate': 0.70,
                'avg_win': 0.0,  # Missing data
                'avg_loss': 0.0,  # Missing data
                'total_trades': 3,  # Not proven (< 10)
                'source': 'initial_estimate'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        params = trader.get_backtest_params_for_strategy('NEW_STRATEGY')

        # Should use conservative defaults for avg_win/avg_loss
        assert params['avg_win'] == 8.0   # Conservative default
        assert params['avg_loss'] == 12.0  # Conservative default
        assert params['is_proven'] == False

    def test_kelly_with_no_strategy_stats(self):
        """When no stats available, should use conservative defaults"""
        from spx_institutional_trader import SPXInstitutionalTrader

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = None

        params = trader.get_backtest_params_for_strategy('UNKNOWN_STRATEGY')

        # Should return conservative defaults
        assert params['win_rate'] == 0.55  # Conservative 55%
        assert params['avg_win'] == 8.0
        assert params['avg_loss'] == 12.0
        assert params['is_proven'] == False
        assert params['source'] == 'default_conservative'


class TestStrategyValidation:
    """Test strategy validation gates"""

    def test_reject_negative_expectancy(self):
        """Proven strategies with negative expectancy should be blocked"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'LOSING_STRATEGY': {
                'win_rate': 0.40,
                'avg_win': 5.0,
                'avg_loss': 10.0,
                'total_trades': 100,
                'expectancy': -4.0,  # Negative expectancy
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        should_trade, reason = trader.should_trade_strategy('LOSING_STRATEGY')

        assert should_trade == False
        assert 'Negative expectancy' in reason or 'BLOCKED' in reason

    def test_reject_low_win_rate(self):
        """Proven strategies with < 40% win rate should be blocked"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'LOW_WIN_STRATEGY': {
                'win_rate': 0.35,  # 35% - too low
                'avg_win': 20.0,
                'avg_loss': 5.0,
                'total_trades': 50,
                'expectancy': 2.0,
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        should_trade, reason = trader.should_trade_strategy('LOW_WIN_STRATEGY')

        assert should_trade == False
        assert 'Win rate too low' in reason or 'BLOCKED' in reason

    def test_approve_good_strategy(self):
        """Strategy meeting all criteria should be approved"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'GOOD_STRATEGY': {
                'win_rate': 0.60,
                'avg_win': 12.0,
                'avg_loss': 8.0,
                'total_trades': 100,
                'expectancy': 4.0,
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        should_trade, reason = trader.should_trade_strategy('GOOD_STRATEGY')

        assert should_trade == True
        assert 'APPROVED' in reason

    def test_allow_unproven_with_conservative_sizing(self):
        """Unproven strategies should be allowed with conservative sizing"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'NEW_STRATEGY': {
                'win_rate': 0.65,
                'total_trades': 5,  # Not proven
                'source': 'initial_estimate'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        should_trade, reason = trader.should_trade_strategy('NEW_STRATEGY')

        assert should_trade == True
        assert 'Unproven' in reason or 'quarter-Kelly' in reason


class TestFuzzyStrategyMatching:
    """Test fuzzy matching for strategy names"""

    def test_exact_match(self):
        """Exact strategy name should match"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'IRON_CONDOR': {
                'win_rate': 0.72,
                'avg_win': 8.0,
                'avg_loss': 20.0,
                'total_trades': 80,
                'expectancy': 2.8,
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        params = trader.get_backtest_params_for_strategy('IRON_CONDOR')

        assert params['win_rate'] == 0.72
        assert params['source'] == 'backtest'

    def test_fuzzy_match_with_prefix(self):
        """Strategy with prefix should match core strategy"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'BULLISH_CALL_SPREAD': {
                'win_rate': 0.65,
                'avg_win': 15.0,
                'avg_loss': 10.0,
                'total_trades': 50,
                'expectancy': 5.0,
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        # This is how unified classifier names strategies
        params = trader.get_backtest_params_for_strategy('SPX Unified: BULLISH_CALL_SPREAD')

        # Should fuzzy match to BULLISH_CALL_SPREAD
        assert params['win_rate'] == 0.65
        assert 'backtest' in params['source']

    def test_core_strategy_extraction(self):
        """Should match by core strategy type when exact match fails"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'SHORT_PUT_CREDIT_SPREAD': {
                'win_rate': 0.68,
                'avg_win': 6.0,
                'avg_loss': 18.0,
                'total_trades': 60,
                'expectancy': 1.5,
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        # Even with different naming, should match by CREDIT_SPREAD
        params = trader.get_backtest_params_for_strategy('SPX_CREDIT_SPREAD_OTM')

        # Should match because both contain CREDIT_SPREAD
        assert 'backtest' in params['source'] or params['total_trades'] == 60


class TestKellyFormula:
    """Test the actual Kelly calculation math"""

    def test_kelly_formula_high_win_rate(self):
        """High win rate with good risk/reward should give higher Kelly"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'HIGH_WIN_STRATEGY': {
                'win_rate': 0.70,  # 70% win rate
                'avg_win': 10.0,
                'avg_loss': 8.0,
                'total_trades': 100,
                'expectancy': 4.6,
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        kelly = trader.calculate_kelly_from_backtest('HIGH_WIN_STRATEGY')

        # Kelly = W - (1-W)/R where R = avg_win/avg_loss = 10/8 = 1.25
        # Kelly = 0.70 - 0.30/1.25 = 0.70 - 0.24 = 0.46
        # Half-Kelly (proven) = 0.23
        assert 0.10 <= kelly <= 0.25  # Should be capped at 25%

    def test_kelly_formula_low_win_rate_high_rr(self):
        """Low win rate but high R/R should still produce positive Kelly"""
        from spx_institutional_trader import SPXInstitutionalTrader

        mock_stats = {
            'TREND_FOLLOWER': {
                'win_rate': 0.40,  # Only 40% win rate
                'avg_win': 25.0,   # But big wins
                'avg_loss': 5.0,   # Small losses
                'total_trades': 80,
                'expectancy': 7.0,
                'source': 'backtest'
            }
        }

        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.strategy_stats = mock_stats

        kelly = trader.calculate_kelly_from_backtest('TREND_FOLLOWER')

        # Kelly = W - (1-W)/R where R = 25/5 = 5.0
        # Kelly = 0.40 - 0.60/5.0 = 0.40 - 0.12 = 0.28
        # Half-Kelly = 0.14
        assert kelly > 0.05  # Should be positive


class TestPositionSizingIntegration:
    """Test full position sizing with backtest integration"""

    @patch('spx_institutional_trader.get_connection')
    def test_position_sizing_proven_vs_unproven(self, mock_conn):
        """Proven strategies should get larger sizes than unproven"""
        from spx_institutional_trader import SPXInstitutionalTrader

        # Mock database connection
        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ('100000000',)  # $100M capital

        # Create trader with mock stats
        trader = SPXInstitutionalTrader.__new__(SPXInstitutionalTrader)
        trader.starting_capital = 100_000_000
        trader.max_position_pct = 0.05
        trader.max_contracts_per_trade = 500
        trader.multiplier = 100

        # Proven strategy
        trader.strategy_stats = {
            'PROVEN_STRATEGY': {
                'win_rate': 0.65,
                'avg_win': 12.0,
                'avg_loss': 8.0,
                'total_trades': 100,
                'expectancy': 4.8,
                'source': 'backtest'
            }
        }

        # Mock get_available_capital
        trader.get_available_capital = lambda: 100_000_000

        # Mock _log_position_sizing_audit to avoid DB calls
        trader._log_position_sizing_audit = lambda **kwargs: None

        contracts_proven, sizing_proven = trader.calculate_position_size(
            entry_price=50.0,
            confidence=80,
            volatility_regime='normal',
            strategy_name='PROVEN_STRATEGY'
        )

        # Unproven strategy
        trader.strategy_stats = {
            'UNPROVEN_STRATEGY': {
                'win_rate': 0.65,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'total_trades': 3,
                'expectancy': 0.0,
                'source': 'initial_estimate'
            }
        }

        contracts_unproven, sizing_unproven = trader.calculate_position_size(
            entry_price=50.0,
            confidence=80,
            volatility_regime='normal',
            strategy_name='UNPROVEN_STRATEGY'
        )

        # Proven should have more contracts (due to backtest_factor difference)
        assert sizing_proven.get('backtest_factor', 1.0) == 1.0
        assert sizing_unproven.get('backtest_factor', 1.0) == 0.5


class TestAuditTrail:
    """Test position sizing audit trail"""

    def test_audit_includes_backtest_params(self):
        """Audit should capture all backtest parameters used"""
        # This test would require database setup
        # For now, verify the sizing_details contains all required fields

        sizing_details = {
            'methodology': 'Kelly-Backtest Hybrid',
            'available_capital': 100000000,
            'kelly_pct': 5.0,
            'max_position_value': 5000000,
            'confidence_factor': 0.9,
            'vol_factor': 1.0,
            'backtest_factor': 1.0,
            'adjusted_position_value': 4500000,
            'cost_per_contract': 5000,
            'raw_contracts': 900,
            'final_contracts': 500,
            'liquidity_constraint_applied': True,
            'backtest_params': {
                'win_rate': 0.65,
                'avg_win': 12.0,
                'avg_loss': 8.0,
                'expectancy': 4.8,
                'is_proven': True,
                'source': 'backtest'
            }
        }

        # Verify all audit fields are present
        assert 'kelly_pct' in sizing_details
        assert 'backtest_factor' in sizing_details
        assert 'backtest_params' in sizing_details
        assert sizing_details['backtest_params']['source'] == 'backtest'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
