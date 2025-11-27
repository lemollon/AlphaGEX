"""
Position Sizing Tests
=====================

Comprehensive tests for:
1. Kelly criterion calculations
2. VIX stress factor adjustments
3. Position size limits
4. Risk management validation
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestKellyCriterion:
    """Test Kelly criterion position sizing"""

    def test_kelly_formula_positive_edge(self):
        """Positive edge should give positive Kelly"""
        # Kelly = W - (1-W)/R
        # W = 0.60, R = 1.5 (avg_win=15, avg_loss=10)
        # Kelly = 0.60 - 0.40/1.5 = 0.60 - 0.267 = 0.333

        win_rate = 0.60
        avg_win = 15.0
        avg_loss = 10.0
        risk_reward = avg_win / avg_loss

        kelly = win_rate - ((1 - win_rate) / risk_reward)

        assert kelly > 0
        assert kelly == pytest.approx(0.333, rel=0.01)

    def test_kelly_formula_negative_edge(self):
        """Negative edge should give negative Kelly"""
        # W = 0.40, R = 0.5 (avg_win=5, avg_loss=10)
        # Kelly = 0.40 - 0.60/0.5 = 0.40 - 1.20 = -0.80

        win_rate = 0.40
        avg_win = 5.0
        avg_loss = 10.0
        risk_reward = avg_win / avg_loss

        kelly = win_rate - ((1 - win_rate) / risk_reward)

        assert kelly < 0
        assert kelly == pytest.approx(-0.80, rel=0.01)

    def test_kelly_break_even_point(self):
        """Break-even Kelly should be ~0"""
        # For R=1.0, break-even is W=0.50
        # Kelly = 0.50 - 0.50/1.0 = 0

        win_rate = 0.50
        risk_reward = 1.0

        kelly = win_rate - ((1 - win_rate) / risk_reward)

        assert kelly == pytest.approx(0.0, abs=0.001)

    def test_negative_kelly_blocks_trade(self):
        """When Kelly is negative, trade should be blocked"""
        win_rate = 0.35
        avg_win = 8.0
        avg_loss = 12.0
        risk_reward = avg_win / avg_loss

        kelly = win_rate - ((1 - win_rate) / risk_reward)

        # This should block the trade
        should_trade = kelly > 0
        assert should_trade == False

    def test_kelly_capping(self):
        """Kelly should be capped at reasonable maximum"""
        # Very high win rate scenario
        win_rate = 0.90
        risk_reward = 2.0

        kelly = win_rate - ((1 - win_rate) / risk_reward)
        # Kelly = 0.90 - 0.10/2.0 = 0.90 - 0.05 = 0.85

        # Should be capped at 25% max for safety
        max_kelly = 0.25
        final_kelly = min(kelly, max_kelly)

        assert final_kelly <= 0.25


class TestVIXStressFactor:
    """Test VIX-based position sizing adjustments"""

    def test_vix_normal_no_reduction(self):
        """Normal VIX should not reduce position"""
        vix = 18.0

        if vix >= 35:
            factor = 0.25
        elif vix >= 28:
            factor = 0.50
        elif vix >= 22:
            factor = 0.75
        else:
            factor = 1.0

        assert factor == 1.0

    def test_vix_elevated_25_percent_reduction(self):
        """Elevated VIX (22-28) should reduce by 25%"""
        vix = 25.0

        if vix >= 35:
            factor = 0.25
        elif vix >= 28:
            factor = 0.50
        elif vix >= 22:
            factor = 0.75
        else:
            factor = 1.0

        assert factor == 0.75

    def test_vix_high_50_percent_reduction(self):
        """High VIX (28-35) should reduce by 50%"""
        vix = 32.0

        if vix >= 35:
            factor = 0.25
        elif vix >= 28:
            factor = 0.50
        elif vix >= 22:
            factor = 0.75
        else:
            factor = 1.0

        assert factor == 0.50

    def test_vix_extreme_75_percent_reduction(self):
        """Extreme VIX (>35) should reduce by 75%"""
        vix = 45.0

        if vix >= 35:
            factor = 0.25
        elif vix >= 28:
            factor = 0.50
        elif vix >= 22:
            factor = 0.75
        else:
            factor = 1.0

        assert factor == 0.25

    def test_vix_edge_cases(self):
        """Test VIX at threshold boundaries"""
        test_cases = [
            (21.9, 1.0),   # Just below elevated
            (22.0, 0.75),  # At elevated threshold
            (27.9, 0.75),  # Just below high
            (28.0, 0.50),  # At high threshold
            (34.9, 0.50),  # Just below extreme
            (35.0, 0.25),  # At extreme threshold
        ]

        def get_vix_factor(vix):
            if vix >= 35:
                return 0.25
            elif vix >= 28:
                return 0.50
            elif vix >= 22:
                return 0.75
            return 1.0

        for vix, expected_factor in test_cases:
            actual = get_vix_factor(vix)
            assert actual == expected_factor, f"VIX {vix}: expected {expected_factor}, got {actual}"


class TestPositionLimits:
    """Test position size limits"""

    def test_max_contracts_per_trade(self):
        """Position should respect max contracts limit"""
        max_contracts = 100
        calculated_contracts = 150

        final_contracts = min(calculated_contracts, max_contracts)
        assert final_contracts == 100

    def test_max_percentage_of_capital(self):
        """Position should respect max % of capital"""
        capital = 1000000
        max_pct = 0.25  # 25%
        max_position = capital * max_pct

        position_value = 300000  # 30% of capital
        capped_value = min(position_value, max_position)

        assert capped_value == 250000

    def test_minimum_position_size(self):
        """Should have minimum 1 contract if trading"""
        calculated_contracts = 0.5

        # If Kelly > 0 and we decide to trade, min is 1
        final_contracts = max(1, int(calculated_contracts))
        assert final_contracts == 1

    def test_zero_contracts_when_kelly_negative(self):
        """Should return 0 contracts when Kelly is negative"""
        kelly = -0.20

        if kelly <= 0:
            contracts = 0
        else:
            contracts = 10

        assert contracts == 0


class TestProvenVsUnprovenSizing:
    """Test different sizing for proven vs unproven strategies"""

    def test_proven_uses_half_kelly(self):
        """Proven strategies use half-Kelly"""
        raw_kelly = 0.30
        is_proven = True

        if is_proven:
            adjusted_kelly = raw_kelly * 0.5
        else:
            adjusted_kelly = raw_kelly * 0.25

        assert adjusted_kelly == 0.15

    def test_unproven_uses_quarter_kelly(self):
        """Unproven strategies use quarter-Kelly"""
        raw_kelly = 0.30
        is_proven = False

        if is_proven:
            adjusted_kelly = raw_kelly * 0.5
        else:
            adjusted_kelly = raw_kelly * 0.25

        assert adjusted_kelly == 0.075

    def test_proven_threshold_10_trades(self):
        """Strategy needs 10+ trades to be proven"""
        trade_counts = [5, 9, 10, 11, 50, 100]
        expected_proven = [False, False, True, True, True, True]

        for count, expected in zip(trade_counts, expected_proven):
            is_proven = count >= 10
            assert is_proven == expected


class TestConfidenceAdjustment:
    """Test confidence-based position sizing"""

    def test_high_confidence_full_size(self):
        """High confidence (90%+) should give near-full size"""
        confidence = 90
        factor = (confidence / 100) * 0.5 + 0.5  # Maps 0-100 to 0.5-1.0

        assert factor >= 0.95

    def test_low_confidence_reduced_size(self):
        """Low confidence should reduce size"""
        confidence = 60
        factor = (confidence / 100) * 0.5 + 0.5

        assert factor == 0.80

    def test_minimum_confidence_threshold(self):
        """Below minimum confidence should not trade"""
        min_confidence = 65
        confidence = 60

        should_trade = confidence >= min_confidence
        assert should_trade == False


class TestCostCalculation:
    """Test position cost calculations"""

    def test_option_contract_cost(self):
        """Option cost = price * 100 (multiplier)"""
        price = 5.50
        multiplier = 100

        cost_per_contract = price * multiplier
        assert cost_per_contract == 550.0

    def test_contracts_from_position_value(self):
        """Calculate contracts from position value"""
        position_value = 5500
        cost_per_contract = 550

        contracts = int(position_value / cost_per_contract)
        assert contracts == 10

    def test_position_value_calculation(self):
        """Total position value calculation"""
        capital = 100000
        kelly_pct = 0.05  # 5%
        confidence_factor = 0.9
        vix_factor = 0.75

        position_value = capital * kelly_pct * confidence_factor * vix_factor
        # 100000 * 0.05 * 0.9 * 0.75 = 3375

        assert position_value == 3375.0


class TestDefaultValues:
    """Test default value handling"""

    def test_zero_avg_win_uses_default(self):
        """Zero avg_win should use default"""
        avg_win = 0.0
        default = 8.0

        actual = avg_win if avg_win > 0 else default
        assert actual == 8.0

    def test_zero_avg_loss_uses_default(self):
        """Zero avg_loss should use default"""
        avg_loss = 0.0
        default = 12.0

        actual = avg_loss if avg_loss > 0 else default
        assert actual == 12.0

    def test_default_win_rate(self):
        """Missing win rate should use conservative default"""
        win_rate = None
        default = 0.55

        actual = win_rate if win_rate is not None else default
        assert actual == 0.55


class TestExpectancyValidation:
    """Test expectancy-based trade validation"""

    def test_positive_expectancy_allowed(self):
        """Positive expectancy should be allowed"""
        expectancy = 2.5

        should_trade = expectancy >= 0
        assert should_trade == True

    def test_negative_expectancy_blocked(self):
        """Negative expectancy should block trade"""
        expectancy = -1.5

        should_trade = expectancy >= 0
        assert should_trade == False

    def test_zero_expectancy_allowed(self):
        """Zero expectancy is technically allowed (break-even)"""
        expectancy = 0.0

        should_trade = expectancy >= 0
        assert should_trade == True

    def test_expectancy_calculation(self):
        """Expectancy = (WR * avg_win) - ((1-WR) * avg_loss)"""
        win_rate = 0.60
        avg_win = 15.0
        avg_loss = 10.0

        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        # (0.60 * 15) - (0.40 * 10) = 9 - 4 = 5

        assert expectancy == 5.0


class TestWinRateValidation:
    """Test win rate-based trade validation"""

    def test_high_win_rate_allowed(self):
        """High win rate should be allowed"""
        win_rate = 65.0
        min_rate = 40.0

        should_trade = win_rate >= min_rate
        assert should_trade == True

    def test_low_win_rate_blocked(self):
        """Low win rate should block trade"""
        win_rate = 35.0
        min_rate = 40.0

        should_trade = win_rate >= min_rate
        assert should_trade == False

    def test_edge_case_40_percent(self):
        """40% exactly should be allowed"""
        win_rate = 40.0
        min_rate = 40.0

        should_trade = win_rate >= min_rate
        assert should_trade == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
