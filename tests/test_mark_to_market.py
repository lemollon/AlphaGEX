"""
Tests for mark-to-market option pricing calculations.

Tests the mid-price P&L calculation for Iron Condors and vertical spreads.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestGetMidPrice:
    """Tests for mid-price calculation logic."""

    def test_mid_price_from_bid_ask(self):
        """Mid price should be average of bid and ask."""
        from trading.mark_to_market import calculate_ic_mark_to_market

        # Mock quotes with bid/ask
        mock_quotes = {
            'SPXW260126P05900000': {'bid': 0.40, 'ask': 0.80, 'last': 0.50},
            'SPXW260126P05890000': {'bid': 0.10, 'ask': 0.30, 'last': 0.15},
            'SPXW260126C06100000': {'bid': 1.80, 'ask': 2.20, 'last': 1.90},
            'SPXW260126C06110000': {'bid': 0.20, 'ask': 0.40, 'last': 0.25},
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result = calculate_ic_mark_to_market(
                underlying='SPX',
                expiration='2026-01-26',
                put_short_strike=5900,
                put_long_strike=5890,
                call_short_strike=6100,
                call_long_strike=6110,
                contracts=1,
                entry_credit=3.50,
                use_cache=False
            )

        assert result['success'] is True
        # Mid prices: put_short=0.60, put_long=0.20, call_short=2.00, call_long=0.30
        # Put spread close: 0.60 - 0.20 = 0.40
        # Call spread close: 2.00 - 0.30 = 1.70
        # Total close: 2.10
        assert result['current_value'] == pytest.approx(2.10, rel=0.01)
        # Unrealized: (3.50 - 2.10) * 100 = 140
        assert result['unrealized_pnl'] == pytest.approx(140.0, rel=0.01)

    def test_mid_price_fallback_to_last(self):
        """Should fall back to last price if bid/ask unavailable."""
        from trading.mark_to_market import calculate_ic_mark_to_market

        # Mock quotes with only last price (no bid/ask)
        mock_quotes = {
            'SPXW260126P05900000': {'bid': None, 'ask': None, 'last': 0.50},
            'SPXW260126P05890000': {'bid': 0, 'ask': 0, 'last': 0.15},
            'SPXW260126C06100000': {'last': 1.90},
            'SPXW260126C06110000': {'bid': 0.20, 'ask': 0.40, 'last': 0.25},
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result = calculate_ic_mark_to_market(
                underlying='SPX',
                expiration='2026-01-26',
                put_short_strike=5900,
                put_long_strike=5890,
                call_short_strike=6100,
                call_long_strike=6110,
                contracts=1,
                entry_credit=3.50,
                use_cache=False
            )

        assert result['success'] is True
        # Falls back to last for put_short (0.50), put_long (0.15), call_short (1.90)
        # Uses mid for call_long (0.30)


class TestIronCondorPnL:
    """Tests for Iron Condor P&L calculation."""

    def test_profitable_ic_shows_positive_pnl(self):
        """Safe IC position should show positive unrealized P&L."""
        from trading.mark_to_market import calculate_ic_mark_to_market

        # Position is safe - price between short strikes
        # Current value to close is LESS than entry credit
        mock_quotes = {
            'SPXW260126P05900000': {'bid': 0.20, 'ask': 0.40, 'last': 0.30},  # mid=0.30
            'SPXW260126P05890000': {'bid': 0.05, 'ask': 0.15, 'last': 0.10},  # mid=0.10
            'SPXW260126C06100000': {'bid': 0.30, 'ask': 0.50, 'last': 0.40},  # mid=0.40
            'SPXW260126C06110000': {'bid': 0.05, 'ask': 0.15, 'last': 0.10},  # mid=0.10
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result = calculate_ic_mark_to_market(
                underlying='SPX',
                expiration='2026-01-26',
                put_short_strike=5900,
                put_long_strike=5890,
                call_short_strike=6100,
                call_long_strike=6110,
                contracts=1,
                entry_credit=2.00,
                use_cache=False
            )

        assert result['success'] is True
        # Close cost: (0.30-0.10) + (0.40-0.10) = 0.20 + 0.30 = 0.50
        assert result['current_value'] == pytest.approx(0.50, rel=0.01)
        # P&L: (2.00 - 0.50) * 100 = 150 profit
        assert result['unrealized_pnl'] == pytest.approx(150.0, rel=0.01)
        assert result['unrealized_pnl'] > 0, "Safe IC should show profit"

    def test_losing_ic_shows_negative_pnl(self):
        """IC with breached strike should show negative unrealized P&L."""
        from trading.mark_to_market import calculate_ic_mark_to_market

        # Position is losing - short strike breached, high option values
        mock_quotes = {
            'SPXW260126P05900000': {'bid': 2.50, 'ask': 3.50, 'last': 3.00},  # mid=3.00
            'SPXW260126P05890000': {'bid': 1.50, 'ask': 2.50, 'last': 2.00},  # mid=2.00
            'SPXW260126C06100000': {'bid': 0.10, 'ask': 0.20, 'last': 0.15},  # mid=0.15
            'SPXW260126C06110000': {'bid': 0.02, 'ask': 0.08, 'last': 0.05},  # mid=0.05
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result = calculate_ic_mark_to_market(
                underlying='SPX',
                expiration='2026-01-26',
                put_short_strike=5900,
                put_long_strike=5890,
                call_short_strike=6100,
                call_long_strike=6110,
                contracts=1,
                entry_credit=2.00,
                use_cache=False
            )

        assert result['success'] is True
        # Close cost: (3.00-2.00) + (0.15-0.05) = 1.00 + 0.10 = 1.10
        assert result['current_value'] == pytest.approx(1.10, rel=0.01)
        # P&L: (2.00 - 1.10) * 100 = 90 profit (still profitable even with put side pressured)
        assert result['unrealized_pnl'] == pytest.approx(90.0, rel=0.01)

    def test_multiple_contracts_multiplies_pnl(self):
        """P&L should scale with contract count."""
        from trading.mark_to_market import calculate_ic_mark_to_market

        mock_quotes = {
            'SPXW260126P05900000': {'bid': 0.20, 'ask': 0.40, 'last': 0.30},
            'SPXW260126P05890000': {'bid': 0.05, 'ask': 0.15, 'last': 0.10},
            'SPXW260126C06100000': {'bid': 0.30, 'ask': 0.50, 'last': 0.40},
            'SPXW260126C06110000': {'bid': 0.05, 'ask': 0.15, 'last': 0.10},
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result_1 = calculate_ic_mark_to_market(
                underlying='SPX',
                expiration='2026-01-26',
                put_short_strike=5900,
                put_long_strike=5890,
                call_short_strike=6100,
                call_long_strike=6110,
                contracts=1,
                entry_credit=2.00,
                use_cache=False
            )

            result_5 = calculate_ic_mark_to_market(
                underlying='SPX',
                expiration='2026-01-26',
                put_short_strike=5900,
                put_long_strike=5890,
                call_short_strike=6100,
                call_long_strike=6110,
                contracts=5,
                entry_credit=2.00,
                use_cache=False
            )

        assert result_5['unrealized_pnl'] == pytest.approx(result_1['unrealized_pnl'] * 5, rel=0.01)

    def test_returns_leg_prices_as_mid(self):
        """Result should include mid prices for each leg."""
        from trading.mark_to_market import calculate_ic_mark_to_market

        mock_quotes = {
            'SPXW260126P05900000': {'bid': 0.40, 'ask': 0.80, 'last': 0.50},
            'SPXW260126P05890000': {'bid': 0.10, 'ask': 0.30, 'last': 0.15},
            'SPXW260126C06100000': {'bid': 1.80, 'ask': 2.20, 'last': 1.90},
            'SPXW260126C06110000': {'bid': 0.20, 'ask': 0.40, 'last': 0.25},
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result = calculate_ic_mark_to_market(
                underlying='SPX',
                expiration='2026-01-26',
                put_short_strike=5900,
                put_long_strike=5890,
                call_short_strike=6100,
                call_long_strike=6110,
                contracts=1,
                entry_credit=3.50,
                use_cache=False
            )

        assert 'leg_prices' in result
        assert result['leg_prices']['put_short_mid'] == pytest.approx(0.60, rel=0.01)
        assert result['leg_prices']['put_long_mid'] == pytest.approx(0.20, rel=0.01)
        assert result['leg_prices']['call_short_mid'] == pytest.approx(2.00, rel=0.01)
        assert result['leg_prices']['call_long_mid'] == pytest.approx(0.30, rel=0.01)


class TestSpreadPnL:
    """Tests for vertical spread P&L calculation."""

    def test_debit_spread_profit(self):
        """Debit spread with increased value should show profit."""
        from trading.mark_to_market import calculate_spread_mark_to_market

        mock_quotes = {
            'SPY260126C00590000': {'bid': 2.50, 'ask': 2.70, 'last': 2.60},  # mid=2.60
            'SPY260126C00595000': {'bid': 0.80, 'ask': 1.00, 'last': 0.90},  # mid=0.90
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result = calculate_spread_mark_to_market(
                underlying='SPY',
                expiration='2026-01-26',
                long_strike=590,
                short_strike=595,
                spread_type='BULL_CALL',
                contracts=1,
                entry_debit=1.00,
                use_cache=False
            )

        assert result['success'] is True
        # Current value: 2.60 - 0.90 = 1.70
        assert result['current_value'] == pytest.approx(1.70, rel=0.01)
        # P&L: (1.70 - 1.00) * 100 = 70 profit
        assert result['unrealized_pnl'] == pytest.approx(70.0, rel=0.01)

    def test_debit_spread_loss(self):
        """Debit spread with decreased value should show loss."""
        from trading.mark_to_market import calculate_spread_mark_to_market

        mock_quotes = {
            'SPY260126C00590000': {'bid': 0.30, 'ask': 0.50, 'last': 0.40},  # mid=0.40
            'SPY260126C00595000': {'bid': 0.05, 'ask': 0.15, 'last': 0.10},  # mid=0.10
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result = calculate_spread_mark_to_market(
                underlying='SPY',
                expiration='2026-01-26',
                long_strike=590,
                short_strike=595,
                spread_type='BULL_CALL',
                contracts=1,
                entry_debit=1.50,
                use_cache=False
            )

        assert result['success'] is True
        # Current value: 0.40 - 0.10 = 0.30
        assert result['current_value'] == pytest.approx(0.30, rel=0.01)
        # P&L: (0.30 - 1.50) * 100 = -120 loss
        assert result['unrealized_pnl'] == pytest.approx(-120.0, rel=0.01)


class TestMissingQuotes:
    """Tests for handling missing quote data."""

    def test_missing_quote_returns_error(self):
        """Should return error when quotes are missing."""
        from trading.mark_to_market import calculate_ic_mark_to_market

        # Only return 3 of 4 required quotes
        mock_quotes = {
            'SPXW260126P05900000': {'bid': 0.40, 'ask': 0.80, 'last': 0.50},
            'SPXW260126P05890000': {'bid': 0.10, 'ask': 0.30, 'last': 0.15},
            'SPXW260126C06100000': {'bid': 1.80, 'ask': 2.20, 'last': 1.90},
            # Missing call_long quote
        }

        with patch('trading.mark_to_market.get_option_quotes_batch', return_value=mock_quotes):
            result = calculate_ic_mark_to_market(
                underlying='SPX',
                expiration='2026-01-26',
                put_short_strike=5900,
                put_long_strike=5890,
                call_short_strike=6100,
                call_long_strike=6110,
                contracts=1,
                entry_credit=3.50,
                use_cache=False
            )

        assert result['success'] is False
        assert 'call_long' in result['error']
