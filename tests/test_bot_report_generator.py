"""
Tests for Bot Report Generator

Tests cover:
1. Database table creation schema validation
2. Claude response parsing (various formats and edge cases)
3. Date/timezone edge cases

Author: AlphaGEX
Date: January 2025
"""

import json
import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from zoneinfo import ZoneInfo

# Import the functions we're testing
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.bot_report_generator import (
    _safe_json_dumps,
    _safe_get,
    _extract_claude_response_text,
    _parse_claude_json_response,
    VALID_BOTS,
    BOT_POSITION_TABLES,
    CENTRAL_TZ,
)


# =============================================================================
# TEST 1: DATABASE TABLE CREATION
# =============================================================================

class TestDatabaseTableCreation:
    """Tests for database table creation and schema validation."""

    def test_all_bots_have_position_tables(self):
        """Verify all valid bots have position table mappings."""
        for bot in VALID_BOTS:
            assert bot in BOT_POSITION_TABLES, f"Bot {bot} missing from BOT_POSITION_TABLES"
            assert BOT_POSITION_TABLES[bot] == f"{bot}_positions", f"Unexpected table name for {bot}"

    def test_valid_bots_list(self):
        """Verify VALID_BOTS contains expected bots."""
        expected_bots = ['ares', 'athena', 'titan', 'pegasus', 'icarus']
        assert VALID_BOTS == expected_bots, f"VALID_BOTS mismatch: {VALID_BOTS}"

    @patch('backend.services.bot_report_generator.get_connection')
    @patch('backend.services.bot_report_generator.DB_AVAILABLE', True)
    def test_ensure_report_tables_creates_all_tables(self, mock_get_conn):
        """Verify table creation SQL is called for all bots."""
        from backend.services.bot_report_generator import _ensure_report_tables_exist

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        result = _ensure_report_tables_exist()

        # Should have been called for each bot (table + date_idx + pnl_idx = 3 calls per bot)
        assert mock_cursor.execute.call_count == len(VALID_BOTS) * 3
        assert mock_conn.commit.called
        assert mock_conn.close.called

    @patch('backend.services.bot_report_generator.get_connection')
    @patch('backend.services.bot_report_generator.DB_AVAILABLE', True)
    def test_table_schema_has_required_columns(self, mock_get_conn):
        """Verify CREATE TABLE SQL includes all required columns."""
        from backend.services.bot_report_generator import _ensure_report_tables_exist

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        _ensure_report_tables_exist()

        # Get the CREATE TABLE call
        create_calls = [call for call in mock_cursor.execute.call_args_list
                       if 'CREATE TABLE' in str(call)]
        assert len(create_calls) >= 1, "No CREATE TABLE calls found"

        create_sql = str(create_calls[0])

        # Required columns
        required_columns = [
            'report_date',
            'trades_data',
            'intraday_ticks',
            'scan_activity',
            'market_context',
            'trade_analyses',
            'daily_summary',
            'lessons_learned',
            'total_pnl',
            'trade_count',
            'win_count',
            'loss_count',
            'generated_at',
            'generation_model',
        ]

        for col in required_columns:
            assert col in create_sql, f"Required column '{col}' not found in CREATE TABLE"

    @patch('backend.services.bot_report_generator.DB_AVAILABLE', False)
    def test_table_creation_handles_no_database(self):
        """Verify graceful handling when database is unavailable."""
        from backend.services.bot_report_generator import _ensure_report_tables_exist

        result = _ensure_report_tables_exist()
        assert result == False, "Should return False when DB not available"

    @patch('backend.services.bot_report_generator.get_connection')
    @patch('backend.services.bot_report_generator.DB_AVAILABLE', True)
    def test_table_creation_handles_db_error(self, mock_get_conn):
        """Verify error handling during table creation."""
        from backend.services.bot_report_generator import _ensure_report_tables_exist

        mock_get_conn.side_effect = Exception("Database connection failed")

        result = _ensure_report_tables_exist()
        assert result == False, "Should return False on DB error"


# =============================================================================
# TEST 2: CLAUDE RESPONSE PARSING
# =============================================================================

class TestClaudeResponseParsing:
    """Tests for Claude API response parsing."""

    def test_extract_text_from_valid_response(self):
        """Test extraction from a properly formatted Claude response."""
        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = "  This is the response text  "
        mock_response.content = [mock_content_block]

        result = _extract_claude_response_text(mock_response)
        assert result == "This is the response text"

    def test_extract_text_from_none_response(self):
        """Test handling of None response."""
        result = _extract_claude_response_text(None)
        assert result is None

    def test_extract_text_from_empty_content(self):
        """Test handling of response with empty content list."""
        mock_response = Mock()
        mock_response.content = []

        result = _extract_claude_response_text(mock_response)
        assert result is None

    def test_extract_text_from_response_without_content_attr(self):
        """Test handling of response missing content attribute."""
        mock_response = Mock(spec=[])  # No attributes

        result = _extract_claude_response_text(mock_response)
        assert result is None

    def test_extract_text_from_content_block_without_text(self):
        """Test handling of content block missing text attribute."""
        mock_response = Mock()
        mock_content_block = Mock(spec=[])  # No text attribute
        mock_response.content = [mock_content_block]

        result = _extract_claude_response_text(mock_response)
        assert result is None

    def test_parse_json_from_plain_json(self):
        """Test parsing plain JSON without code blocks."""
        json_text = '{"key": "value", "number": 42}'
        result = _parse_claude_json_response(json_text)

        assert result == {"key": "value", "number": 42}

    def test_parse_json_from_markdown_code_block(self):
        """Test parsing JSON wrapped in ```json code block."""
        json_text = '''Here's the analysis:

```json
{
    "entry_analysis": {
        "quality": "GOOD",
        "reasoning": "Strong GEX support"
    },
    "lesson": "Trust the levels"
}
```

That's the result.'''

        result = _parse_claude_json_response(json_text)

        assert result is not None
        assert result["entry_analysis"]["quality"] == "GOOD"
        assert result["lesson"] == "Trust the levels"

    def test_parse_json_from_generic_code_block(self):
        """Test parsing JSON wrapped in generic ``` code block."""
        json_text = '''```
{"status": "success", "data": [1, 2, 3]}
```'''

        result = _parse_claude_json_response(json_text)

        assert result == {"status": "success", "data": [1, 2, 3]}

    def test_parse_json_handles_none_input(self):
        """Test handling of None input."""
        result = _parse_claude_json_response(None)
        assert result is None

    def test_parse_json_handles_empty_string(self):
        """Test handling of empty string."""
        result = _parse_claude_json_response("")
        assert result is None

    def test_parse_json_handles_invalid_json(self):
        """Test handling of malformed JSON."""
        result = _parse_claude_json_response("this is not json at all")
        assert result is None

    def test_parse_json_handles_incomplete_json(self):
        """Test handling of truncated/incomplete JSON."""
        result = _parse_claude_json_response('{"key": "value", "incomplete":')
        assert result is None

    def test_parse_json_with_nested_objects(self):
        """Test parsing deeply nested JSON structures."""
        json_text = '''{
            "trade_analyses": [
                {
                    "position_id": "POS001",
                    "entry_analysis": {
                        "quality": "GOOD",
                        "reasoning": "Test"
                    },
                    "key_timestamps": [
                        {"time": "09:30", "event": "Entry", "price": 585.50}
                    ]
                }
            ],
            "lessons_learned": ["Lesson 1", "Lesson 2"]
        }'''

        result = _parse_claude_json_response(json_text)

        assert result is not None
        assert len(result["trade_analyses"]) == 1
        assert result["trade_analyses"][0]["position_id"] == "POS001"
        assert len(result["lessons_learned"]) == 2

    def test_parse_json_with_unicode(self):
        """Test parsing JSON with unicode characters."""
        json_text = '{"message": "Price moved ↑ significantly", "emoji": "🎯"}'
        result = _parse_claude_json_response(json_text)

        assert result is not None
        assert "↑" in result["message"]
        assert result["emoji"] == "🎯"

    def test_parse_json_with_special_characters(self):
        """Test parsing JSON with special characters in strings."""
        json_text = '{"reasoning": "Price broke through $585.50 resistance\\nNew high formed"}'
        result = _parse_claude_json_response(json_text)

        assert result is not None
        assert "$585.50" in result["reasoning"]


# =============================================================================
# TEST 3: DATE/TIMEZONE EDGE CASES
# =============================================================================

class TestDateTimezoneEdgeCases:
    """Tests for date and timezone handling."""

    def test_central_timezone_constant(self):
        """Verify CENTRAL_TZ is correctly set."""
        assert CENTRAL_TZ == ZoneInfo("America/Chicago")

    def test_safe_json_dumps_handles_datetime(self):
        """Test JSON serialization of datetime objects."""
        dt = datetime(2025, 1, 15, 14, 30, 0)
        data = {"timestamp": dt}

        result = _safe_json_dumps(data)
        parsed = json.loads(result)

        assert parsed["timestamp"] == "2025-01-15T14:30:00"

    def test_safe_json_dumps_handles_date(self):
        """Test JSON serialization of date objects."""
        d = date(2025, 1, 15)
        data = {"date": d}

        result = _safe_json_dumps(data)
        parsed = json.loads(result)

        assert parsed["date"] == "2025-01-15"

    def test_safe_json_dumps_handles_decimal(self):
        """Test JSON serialization of Decimal objects."""
        data = {
            "pnl": Decimal("123.45"),
            "price": Decimal("-500.00")
        }

        result = _safe_json_dumps(data)
        parsed = json.loads(result)

        assert parsed["pnl"] == 123.45
        assert parsed["price"] == -500.00

    def test_safe_json_dumps_handles_mixed_types(self):
        """Test JSON serialization of mixed data types."""
        data = {
            "date": date(2025, 1, 15),
            "datetime": datetime(2025, 1, 15, 9, 30),
            "decimal": Decimal("585.50"),
            "string": "test",
            "number": 42,
            "list": [1, 2, 3],
            "nested": {
                "inner_decimal": Decimal("10.5"),
                "inner_date": date(2025, 1, 16)
            }
        }

        result = _safe_json_dumps(data)
        parsed = json.loads(result)

        assert parsed["date"] == "2025-01-15"
        assert parsed["datetime"] == "2025-01-15T09:30:00"
        assert parsed["decimal"] == 585.50
        assert parsed["nested"]["inner_decimal"] == 10.5
        assert parsed["nested"]["inner_date"] == "2025-01-16"

    def test_safe_json_dumps_returns_default_on_failure(self):
        """Test fallback to default value on serialization failure."""
        # Create an object that can't be serialized
        class Unpicklable:
            def __repr__(self):
                raise Exception("Cannot represent")

        data = {"bad": Unpicklable()}

        # Should return default without raising
        result = _safe_json_dumps(data, default_value="{}")
        assert result == "{}"

    def test_safe_get_nested_dict(self):
        """Test safe access to nested dictionary values."""
        data = {
            "level1": {
                "level2": {
                    "value": 42
                }
            }
        }

        result = _safe_get(data, "level1", "level2", "value")
        assert result == 42

    def test_safe_get_missing_key(self):
        """Test safe access when key doesn't exist."""
        data = {"exists": "value"}

        result = _safe_get(data, "missing", default="default_value")
        assert result == "default_value"

    def test_safe_get_none_input(self):
        """Test safe access with None input."""
        result = _safe_get(None, "any", "key", default="default")
        assert result == "default"

    def test_safe_get_non_dict_intermediate(self):
        """Test safe access when intermediate value is not a dict."""
        data = {"key": "string_not_dict"}

        result = _safe_get(data, "key", "subkey", default="default")
        assert result == "default"

    def test_date_at_midnight_boundary(self):
        """Test date handling at midnight boundary."""
        # 11:59 PM Central on Jan 15
        before_midnight = datetime(2025, 1, 15, 23, 59, 59, tzinfo=CENTRAL_TZ)
        # 12:01 AM Central on Jan 16
        after_midnight = datetime(2025, 1, 16, 0, 1, 0, tzinfo=CENTRAL_TZ)

        assert before_midnight.date() == date(2025, 1, 15)
        assert after_midnight.date() == date(2025, 1, 16)

    def test_utc_to_central_conversion(self):
        """Test UTC to Central time conversion."""
        utc_time = datetime(2025, 1, 15, 20, 0, 0, tzinfo=ZoneInfo("UTC"))  # 8 PM UTC
        central_time = utc_time.astimezone(CENTRAL_TZ)

        # UTC-6 in winter (CST)
        assert central_time.hour == 14  # 2 PM Central

    def test_market_hours_in_central_time(self):
        """Test market hours are correctly in Central time."""
        market_open = datetime(2025, 1, 15, 8, 30, 0, tzinfo=CENTRAL_TZ)
        market_close = datetime(2025, 1, 15, 15, 0, 0, tzinfo=CENTRAL_TZ)

        # Market open should be 8:30 AM CT
        assert market_open.hour == 8
        assert market_open.minute == 30

        # Market close should be 3:00 PM CT
        assert market_close.hour == 15
        assert market_close.minute == 0

    def test_weekend_date_detection(self):
        """Test detection of weekend dates."""
        saturday = date(2025, 1, 18)  # Saturday
        sunday = date(2025, 1, 19)    # Sunday
        monday = date(2025, 1, 20)    # Monday

        assert saturday.weekday() == 5  # Saturday
        assert sunday.weekday() == 6    # Sunday
        assert monday.weekday() == 0    # Monday

    def test_end_of_month_date(self):
        """Test handling of end-of-month dates."""
        jan_31 = date(2025, 1, 31)
        feb_28 = date(2025, 2, 28)  # 2025 is not a leap year

        # Next day calculations
        next_day_jan = jan_31 + timedelta(days=1)
        next_day_feb = feb_28 + timedelta(days=1)

        assert next_day_jan == date(2025, 2, 1)
        assert next_day_feb == date(2025, 3, 1)


# =============================================================================
# TEST: SAFE_JSON_DUMPS EDGE CASES
# =============================================================================

class TestSafeJsonDumpsEdgeCases:
    """Additional edge case tests for _safe_json_dumps."""

    def test_empty_dict(self):
        """Test serialization of empty dict."""
        result = _safe_json_dumps({})
        assert result == "{}"

    def test_empty_list(self):
        """Test serialization of empty list."""
        result = _safe_json_dumps([])
        assert result == "[]"

    def test_nested_empty_structures(self):
        """Test serialization of nested empty structures."""
        data = {"empty_list": [], "empty_dict": {}, "none": None}
        result = _safe_json_dumps(data)
        parsed = json.loads(result)

        assert parsed["empty_list"] == []
        assert parsed["empty_dict"] == {}
        assert parsed["none"] is None

    def test_very_large_decimal(self):
        """Test serialization of very large Decimal."""
        data = {"large": Decimal("999999999999.99")}
        result = _safe_json_dumps(data)
        parsed = json.loads(result)

        assert parsed["large"] == 999999999999.99

    def test_very_small_decimal(self):
        """Test serialization of very small Decimal."""
        data = {"small": Decimal("0.0000001")}
        result = _safe_json_dumps(data)
        parsed = json.loads(result)

        assert abs(parsed["small"] - 0.0000001) < 0.00000001


# =============================================================================
# INTEGRATION TESTS (require mocked DB)
# =============================================================================

class TestFetchFunctions:
    """Tests for data fetching functions with mocked database."""

    @patch('backend.services.bot_report_generator._db_connection')
    @patch('backend.services.bot_report_generator.DB_AVAILABLE', True)
    def test_fetch_closed_trades_converts_decimals(self, mock_db_conn):
        """Test that fetched trades have Decimals converted to floats."""
        from backend.services.bot_report_generator import fetch_closed_trades_for_date

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [
            ('id',), ('pnl',), ('entry_price',), ('close_time',)
        ]
        mock_cursor.fetchall.return_value = [
            (1, Decimal('123.45'), Decimal('585.50'), datetime(2025, 1, 15, 14, 30))
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_db_conn.return_value.__exit__ = Mock(return_value=False)

        trades = fetch_closed_trades_for_date('ares', date(2025, 1, 15))

        assert len(trades) == 1
        assert isinstance(trades[0]['pnl'], float)
        assert trades[0]['pnl'] == 123.45
        assert isinstance(trades[0]['entry_price'], float)

    @patch('backend.services.bot_report_generator.DB_AVAILABLE', False)
    def test_fetch_closed_trades_handles_no_db(self):
        """Test graceful handling when DB is unavailable."""
        from backend.services.bot_report_generator import fetch_closed_trades_for_date

        trades = fetch_closed_trades_for_date('ares', date(2025, 1, 15))
        assert trades == []

    def test_fetch_closed_trades_rejects_invalid_bot(self):
        """Test that invalid bot names are rejected."""
        from backend.services.bot_report_generator import fetch_closed_trades_for_date

        trades = fetch_closed_trades_for_date('invalid_bot', date(2025, 1, 15))
        assert trades == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
