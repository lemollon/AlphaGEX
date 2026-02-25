"""
Tests for Feature 5: IronForge Advisor (Oracle integration).
"""

import pytest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TestAdvisorVIX:
    """Test VIX-based scoring."""

    def test_ideal_vix_boosts_probability(self, mock_config):
        """VIX 18 (ideal range 15-22) should produce high win probability."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ)  # Wednesday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = evaluate(vix=18.0, spot=587.0, expected_move=2.3, dte_mode="2DTE", config=mock_config)

        assert result.win_probability >= 0.75
        assert result.advice == "TRADE_FULL"
        # Check VIX_IDEAL factor present
        factor_names = [f[0] for f in result.top_factors]
        assert "VIX_IDEAL" in factor_names

    def test_high_vix_reduces_probability(self, mock_config):
        """VIX 30 (high risk) should produce lower probability than VIX 18."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ)  # Wednesday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result_high = evaluate(vix=30.0, spot=587.0, expected_move=5.0, dte_mode="2DTE", config=mock_config)
            result_ideal = evaluate(vix=18.0, spot=587.0, expected_move=5.0, dte_mode="2DTE", config=mock_config)

        assert result_high.win_probability < result_ideal.win_probability
        factor_names = [f[0] for f in result_high.top_factors]
        assert "VIX_HIGH_RISK" in factor_names


class TestAdvisorDayOfWeek:
    """Test day-of-week scoring."""

    def test_tuesday_bonus(self, mock_config):
        """Tuesday (optimal) should get DAY_OPTIMAL bonus."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            # Tuesday = weekday 1
            mock_dt.now.return_value = datetime(2026, 2, 24, 10, 0, tzinfo=CENTRAL_TZ)  # Tuesday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = evaluate(vix=18.0, spot=587.0, expected_move=2.3, dte_mode="2DTE", config=mock_config)

        factor_names = [f[0] for f in result.top_factors]
        assert "DAY_OPTIMAL" in factor_names

    def test_friday_penalty(self, mock_config):
        """Friday should get DAY_FRIDAY_RISK penalty."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            # Friday = weekday 4
            mock_dt.now.return_value = datetime(2026, 2, 27, 10, 0, tzinfo=CENTRAL_TZ)  # Friday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = evaluate(vix=18.0, spot=587.0, expected_move=2.3, dte_mode="1DTE", config=mock_config)

        factor_names = [f[0] for f in result.top_factors]
        assert "DAY_FRIDAY_RISK" in factor_names


class TestAdvisorAdvice:
    """Test advice thresholds."""

    def test_skip_below_min_probability(self, mock_config):
        """With bad conditions, advisor should say SKIP."""
        from trading.advisor import evaluate

        mock_config.min_win_probability = 0.60

        with patch('trading.advisor.datetime') as mock_dt:
            # Friday with high VIX, wide EM, 1DTE = worst case
            mock_dt.now.return_value = datetime(2026, 2, 27, 10, 0, tzinfo=CENTRAL_TZ)  # Friday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = evaluate(vix=30.0, spot=587.0, expected_move=15.0, dte_mode="1DTE", config=mock_config)

        assert result.advice == "SKIP"
        assert result.win_probability < 0.50

    def test_trade_full_with_good_conditions(self, mock_config):
        """Ideal conditions should produce TRADE_FULL."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ)  # Wednesday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = evaluate(vix=18.0, spot=587.0, expected_move=2.0, dte_mode="2DTE", config=mock_config)

        assert result.advice == "TRADE_FULL"
        assert result.confidence >= 0.50

    def test_top_factors_populated(self, mock_config):
        """top_factors should always have at least 4 entries."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = evaluate(vix=18.0, spot=587.0, expected_move=2.3, dte_mode="2DTE", config=mock_config)

        assert len(result.top_factors) == 4  # VIX + DOW + EM + DTE


class TestAdvisorDTE:
    """Test DTE mode adjustments."""

    def test_2dte_bonus(self, mock_config):
        """2DTE should get a small bonus (more decay)."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result_2dte = evaluate(vix=18.0, spot=587.0, expected_move=2.3, dte_mode="2DTE", config=mock_config)
            result_1dte = evaluate(vix=18.0, spot=587.0, expected_move=2.3, dte_mode="1DTE", config=mock_config)

        assert result_2dte.win_probability > result_1dte.win_probability


class TestAdvisorConfidence:
    """Test confidence calculation."""

    def test_all_positive_high_confidence(self, mock_config):
        """When all factors are positive, confidence should be high."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            # Wednesday, ideal VIX, tight EM, 2DTE = all positive
            mock_dt.now.return_value = datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = evaluate(vix=18.0, spot=587.0, expected_move=2.0, dte_mode="2DTE", config=mock_config)

        assert result.confidence >= 0.80

    def test_mixed_factors_moderate_confidence(self, mock_config):
        """Mixed positive/negative factors should give moderate confidence."""
        from trading.advisor import evaluate

        with patch('trading.advisor.datetime') as mock_dt:
            # Wednesday (good) but high VIX (bad) and wide EM (bad)
            mock_dt.now.return_value = datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = evaluate(vix=30.0, spot=587.0, expected_move=15.0, dte_mode="2DTE", config=mock_config)

        assert 0.20 <= result.confidence <= 0.70
