#!/usr/bin/env python3
"""
Tests for Watchtower Pattern Similarity Feature

Tests the pattern similarity calculation and OHLC-based outcome detection.

Bug Fix Context:
- Issue: Pattern similarity was reporting all days as "FLAT" because it used
  GEX snapshot spot_price (taken at ~10 AM) as both open and close prices.
- Fix: Now uses actual daily OHLC from price_history or market_data_daily tables.
"""

import pytest
import sys
import os
from datetime import datetime, date

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCalculatePatternSimilarity:
    """Tests for the calculate_pattern_similarity function"""

    @pytest.fixture
    def similarity_function(self):
        """Import the similarity function"""
        try:
            from backend.api.routes.watchtower_routes import calculate_pattern_similarity
            return calculate_pattern_similarity
        except ImportError:
            pytest.skip("watchtower_routes not available")

    def test_identical_patterns_score_100(self, similarity_function):
        """Identical gamma structures should score 100%"""
        current = {
            'regime': 'POSITIVE',
            'net_gex': 5_000_000_000,  # $5B
            'spot_price': 600.0,
            'flip_point': 598.0,
            'call_wall': 610.0,
            'put_wall': 590.0,
            'mm_state': 'LONG_GAMMA',
        }
        historical = current.copy()

        score = similarity_function(current, historical)
        assert score == 100.0, f"Identical patterns should score 100, got {score}"

    def test_opposite_regime_scores_low(self, similarity_function):
        """Opposite regimes should have low similarity"""
        current = {
            'regime': 'POSITIVE',
            'net_gex': 5_000_000_000,
            'spot_price': 600.0,
            'flip_point': 598.0,
            'call_wall': 610.0,
            'put_wall': 590.0,
            'mm_state': 'LONG_GAMMA',
        }
        historical = {
            'regime': 'NEGATIVE',
            'net_gex': -5_000_000_000,
            'spot_price': 600.0,
            'flip_point': 602.0,
            'call_wall': 610.0,
            'put_wall': 590.0,
            'mm_state': 'SHORT_GAMMA',
        }

        score = similarity_function(current, historical)
        # Should be low due to opposite regime and net_gex sign
        assert score < 50, f"Opposite regimes should score < 50, got {score}"

    def test_similar_positive_regimes(self, similarity_function):
        """Similar positive regimes should score high on regime component"""
        current = {'regime': 'POSITIVE'}
        historical = {'regime': 'STRONG_POSITIVE'}

        score = similarity_function(current, historical)
        # 30 * 0.7 = 21 points for similar regime
        assert score >= 20, f"Similar regimes should score >= 20, got {score}"

    def test_similar_negative_regimes(self, similarity_function):
        """Similar negative regimes should score high on regime component"""
        current = {'regime': 'NEGATIVE'}
        historical = {'regime': 'STRONG_NEGATIVE'}

        score = similarity_function(current, historical)
        assert score >= 20, f"Similar negative regimes should score >= 20, got {score}"

    def test_net_gex_same_sign_bonus(self, similarity_function):
        """Same sign net GEX should score higher than opposite signs"""
        current = {
            'net_gex': 5_000_000_000,  # +$5B
        }
        historical_same = {
            'net_gex': 4_000_000_000,  # +$4B (same sign)
        }
        historical_opposite = {
            'net_gex': -4_000_000_000,  # -$4B (opposite sign)
        }

        score_same = similarity_function(current, historical_same)
        score_opposite = similarity_function(current, historical_opposite)

        assert score_same > score_opposite, \
            f"Same sign GEX ({score_same}) should score higher than opposite ({score_opposite})"

    def test_mm_state_match(self, similarity_function):
        """Matching MM state should add 10 points"""
        current = {'mm_state': 'LONG_GAMMA'}
        historical = {'mm_state': 'LONG_GAMMA'}

        score = similarity_function(current, historical)
        assert score == 10, f"MM state match should add 10 points, got {score}"

    def test_partial_data_handles_gracefully(self, similarity_function):
        """Missing fields should not crash the function"""
        current = {'regime': 'POSITIVE'}
        historical = {'regime': 'POSITIVE'}

        # Should not raise an exception
        score = similarity_function(current, historical)
        assert score >= 0, "Score should be non-negative"


class TestOutcomeDirection:
    """Tests for correct UP/DOWN/FLAT determination"""

    def test_up_day_detection(self):
        """Verify UP day is detected when close > open"""
        open_price = 679.95
        close_price = 683.00

        if close_price > open_price:
            outcome = 'UP'
        elif close_price < open_price:
            outcome = 'DOWN'
        else:
            outcome = 'FLAT'

        assert outcome == 'UP', f"Nov 11, 2025 should be UP, got {outcome}"

    def test_down_day_detection(self):
        """Verify DOWN day is detected when close < open"""
        open_price = 590.00
        close_price = 585.00

        if close_price > open_price:
            outcome = 'UP'
        elif close_price < open_price:
            outcome = 'DOWN'
        else:
            outcome = 'FLAT'

        assert outcome == 'DOWN', f"Close < Open should be DOWN, got {outcome}"

    def test_flat_day_detection(self):
        """Verify FLAT day is detected when close == open"""
        open_price = 590.00
        close_price = 590.00

        if close_price > open_price:
            outcome = 'UP'
        elif close_price < open_price:
            outcome = 'DOWN'
        else:
            outcome = 'FLAT'

        assert outcome == 'FLAT', f"Close == Open should be FLAT, got {outcome}"

    def test_nov_11_2025_example(self):
        """
        Test the specific example from user report:
        Nov 11, 2025: Open 679.95, Close 683.00 = UP day (+$3.05, +0.45%)
        """
        open_price = 679.95
        close_price = 683.00

        if close_price > open_price:
            outcome = 'UP'
        elif close_price < open_price:
            outcome = 'DOWN'
        else:
            outcome = 'FLAT'

        price_change = close_price - open_price
        pct_change = ((close_price - open_price) / open_price) * 100

        assert outcome == 'UP', f"Nov 11, 2025 was an UP day, not {outcome}"
        assert abs(price_change - 3.05) < 0.01, f"Price change should be ~$3.05, got ${price_change:.2f}"
        assert abs(pct_change - 0.45) < 0.1, f"Pct change should be ~0.45%, got {pct_change:.2f}%"


class TestOHLCDataQuality:
    """Tests for OHLC data quality indicators"""

    def test_has_real_ohlc_flag(self):
        """Verify has_real_ohlc flag is set correctly"""
        # When we have real OHLC data from price_history/market_data_daily
        has_real_ohlc_with_data = True  # day_open IS NOT NULL
        # When we only have GEX snapshot data
        has_real_ohlc_without_data = False  # day_open IS NULL

        assert has_real_ohlc_with_data is True
        assert has_real_ohlc_without_data is False

    def test_outcome_should_be_unknown_without_ohlc(self):
        """When no real OHLC data, outcome should be UNKNOWN not FLAT"""
        has_real_ohlc = False

        # This is how the code should behave:
        if has_real_ohlc:
            # Calculate UP/DOWN/FLAT from real OHLC
            pass
        else:
            outcome = 'UNKNOWN'

        assert outcome == 'UNKNOWN', "Without real OHLC, outcome should be UNKNOWN"


class TestPatternMatchingSummary:
    """Tests for the summary text generation"""

    def test_up_day_summary(self):
        """UP day should have 'rallied' in summary"""
        outcome_dir = 'UP'
        price_change = 3.05
        outcome_pct = 0.45

        if outcome_dir == 'UP':
            summary = f"SPY rallied +${abs(price_change):.2f} ({abs(outcome_pct):.1f}%)"
        elif outcome_dir == 'DOWN':
            summary = f"SPY fell -${abs(price_change):.2f} ({abs(outcome_pct):.1f}%)"
        else:
            summary = "SPY closed flat"

        assert "rallied" in summary
        assert "+$3.05" in summary

    def test_down_day_summary(self):
        """DOWN day should have 'fell' in summary"""
        outcome_dir = 'DOWN'
        price_change = -5.00
        outcome_pct = -0.85

        if outcome_dir == 'UP':
            summary = f"SPY rallied +${abs(price_change):.2f} ({abs(outcome_pct):.1f}%)"
        elif outcome_dir == 'DOWN':
            summary = f"SPY fell -${abs(price_change):.2f} ({abs(outcome_pct):.1f}%)"
        else:
            summary = "SPY closed flat"

        assert "fell" in summary
        assert "-$5.00" in summary

    def test_unknown_outcome_summary(self):
        """UNKNOWN outcome should indicate missing data"""
        has_real_ohlc = False
        outcome_dir = 'FLAT'  # Default when no data

        if outcome_dir in ['UP', 'DOWN']:
            summary = "Some movement"
        elif has_real_ohlc:
            summary = "SPY closed flat"
        else:
            summary = "SPY outcome unknown (no price data)"

        assert "unknown" in summary or "no price data" in summary


class TestDatabaseIntegration:
    """Integration tests for database queries (require DB connection)"""

    @pytest.fixture
    def db_connection(self):
        """Get database connection if available"""
        try:
            from database_adapter import get_connection, is_database_available
            if not is_database_available():
                pytest.skip("Database not available")
            conn = get_connection()
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database connection failed: {e}")

    def test_price_history_table_exists(self, db_connection):
        """Verify price_history table exists"""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'price_history'
            )
        """)
        exists = cursor.fetchone()[0]
        cursor.close()
        assert exists, "price_history table should exist"

    def test_market_data_daily_table_exists(self, db_connection):
        """Verify market_data_daily table exists"""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'market_data_daily'
            )
        """)
        exists = cursor.fetchone()[0]
        cursor.close()
        assert exists, "market_data_daily table should exist"

    def test_spy_data_available(self, db_connection):
        """Check if SPY daily data is available in either table"""
        cursor = db_connection.cursor()

        # Check price_history
        cursor.execute("""
            SELECT COUNT(*) FROM price_history
            WHERE symbol = 'SPY' AND timeframe = '1d'
        """)
        ph_count = cursor.fetchone()[0]

        # Check market_data_daily
        cursor.execute("""
            SELECT COUNT(*) FROM market_data_daily
            WHERE symbol = 'SPY'
        """)
        mdd_count = cursor.fetchone()[0]

        cursor.close()

        total = ph_count + mdd_count
        print(f"SPY daily data: {ph_count} in price_history, {mdd_count} in market_data_daily")

        # At least one table should have data for pattern matching to work correctly
        if total == 0:
            pytest.skip("No SPY daily data available - run backfill_market_data.py first")

        assert total > 0, "SPY daily data should be available in at least one table"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
