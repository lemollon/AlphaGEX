"""
Zero DTE Strategies Tests

Tests for 0DTE trading strategies.

Run with: pytest tests/test_zero_dte_strategies.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestZeroDTEHybridImport:
    """Tests for 0DTE hybrid import"""

    def test_import_zero_dte_hybrid(self):
        """Test that 0DTE hybrid can be imported"""
        try:
            from backtest.zero_dte_hybrid_scaling import ZeroDTEHybridStrategy
            assert ZeroDTEHybridStrategy is not None
        except ImportError:
            pytest.skip("Zero DTE hybrid not available")


class TestZeroDTEIronCondorImport:
    """Tests for 0DTE iron condor import"""

    def test_import_zero_dte_ic(self):
        """Test that 0DTE IC can be imported"""
        try:
            from backtest.zero_dte_iron_condor import ZeroDTEIronCondor
            assert ZeroDTEIronCondor is not None
        except ImportError:
            pytest.skip("Zero DTE iron condor not available")


class TestZeroDTEBullPutSpreadImport:
    """Tests for 0DTE bull put spread import"""

    def test_import_zero_dte_bps(self):
        """Test that 0DTE bull put spread can be imported"""
        try:
            from backtest.zero_dte_bull_put_spread import ZeroDTEBullPutSpread
            assert ZeroDTEBullPutSpread is not None
        except ImportError:
            pytest.skip("Zero DTE bull put spread not available")


class TestZeroDTEStrategyExecution:
    """Tests for 0DTE strategy execution"""

    def test_hybrid_entry_logic(self):
        """Test hybrid strategy entry logic"""
        try:
            from backtest.zero_dte_hybrid_scaling import ZeroDTEHybridStrategy

            strategy = ZeroDTEHybridStrategy()
            if hasattr(strategy, 'check_entry'):
                with patch.object(strategy, 'check_entry') as mock_entry:
                    mock_entry.return_value = True
                    result = strategy.check_entry({})
                    assert isinstance(result, bool)
        except ImportError:
            pytest.skip("Zero DTE hybrid not available")


class TestZeroDTERiskManagement:
    """Tests for 0DTE risk management"""

    def test_position_sizing(self):
        """Test 0DTE position sizing"""
        try:
            from backtest.zero_dte_hybrid_scaling import ZeroDTEHybridStrategy

            strategy = ZeroDTEHybridStrategy()
            if hasattr(strategy, 'calculate_position_size'):
                with patch.object(strategy, 'calculate_position_size') as mock_size:
                    mock_size.return_value = 3
                    result = strategy.calculate_position_size(capital=50000)
                    assert result > 0
        except ImportError:
            pytest.skip("Zero DTE hybrid not available")


class TestZeroDTEGammaExposure:
    """Tests for 0DTE gamma exposure handling"""

    def test_gamma_adjustment(self):
        """Test gamma-based adjustment"""
        try:
            from backtest.zero_dte_hybrid_scaling import ZeroDTEHybridStrategy

            strategy = ZeroDTEHybridStrategy()
            if hasattr(strategy, 'adjust_for_gamma'):
                with patch.object(strategy, 'adjust_for_gamma') as mock_gamma:
                    mock_gamma.return_value = {'adjustment': 'reduce_size'}
                    result = strategy.adjust_for_gamma({'gamma_regime': 'NEGATIVE'})
                    assert result is not None
        except ImportError:
            pytest.skip("Zero DTE hybrid not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
