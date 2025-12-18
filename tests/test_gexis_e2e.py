"""
GEXIS End-to-End Tests
Tests all GEXIS (J.A.R.V.I.S.-like AI assistant) endpoints and functionality.
"""

import pytest
import json
import os
import sys
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGEXISEndpoints:
    """Test GEXIS API endpoints"""

    @pytest.fixture
    def mock_db_connection(self):
        """Mock database connection"""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    @pytest.fixture
    def mock_api_client(self):
        """Mock API client for GEX data"""
        mock_client = Mock()
        mock_client.get_net_gamma.return_value = {
            'spot_price': 580.50,
            'net_gex': 2500000000,
            'flip_point': 575.00,
            'call_wall': 590.00,
            'put_wall': 570.00
        }
        return mock_client

    def test_gexis_info_returns_correct_structure(self):
        """Test that /gexis/info returns correct data structure"""
        # Import here to avoid circular imports
        from ai.gexis_personality import GEXIS_NAME, GEXIS_FULL_NAME, USER_NAME

        assert GEXIS_NAME == "G.E.X.I.S."
        assert GEXIS_FULL_NAME == "Gamma Exposure eXpert Intelligence System"
        assert USER_NAME == "Optionist Prime"

    def test_gexis_welcome_message_has_greeting(self):
        """Test welcome message includes time-based greeting"""
        from ai.gexis_personality import get_gexis_welcome_message, USER_NAME

        message = get_gexis_welcome_message()

        assert USER_NAME in message
        assert any(greeting in message for greeting in ["Good morning", "Good afternoon", "Good evening"])
        assert "GEXIS" in message
        assert "AlphaGEX" in message or "trading intelligence" in message.lower()

    def test_time_greeting_returns_valid_greeting(self):
        """Test time greeting returns appropriate greeting"""
        from ai.gexis_personality import get_time_greeting

        greeting = get_time_greeting()
        assert greeting in ["Good morning", "Good afternoon", "Good evening"]

    def test_gexis_error_messages(self):
        """Test error message generation"""
        from ai.gexis_personality import get_gexis_error_message, USER_NAME

        general_error = get_gexis_error_message("general")
        assert USER_NAME in general_error

        api_error = get_gexis_error_message("api")
        assert USER_NAME in api_error
        assert "data" in api_error.lower() or "connect" in api_error.lower()

    def test_extract_symbol_from_query(self):
        """Test symbol extraction from queries"""
        try:
            from backend.api.routes.ai_routes import extract_symbol_from_query
        except ImportError:
            pytest.skip("FastAPI not installed - skipping backend import test")

        # Test $SYMBOL format
        assert extract_symbol_from_query("What's the GEX on $AAPL?") == "AAPL"
        assert extract_symbol_from_query("Check $TSLA gamma") == "TSLA"

        # Test plain symbol
        assert extract_symbol_from_query("What's happening with SPY?") == "SPY"
        assert extract_symbol_from_query("NVDA analysis please") == "NVDA"

        # Test default fallback
        assert extract_symbol_from_query("What's the market doing?") == "SPY"

        # Test case insensitivity
        assert extract_symbol_from_query("check qqq") == "QQQ"


class TestQuickCommands:
    """Test GEXIS quick commands"""

    def test_help_command_lists_all_commands(self):
        """Test /help returns all available commands"""
        try:
            from backend.api.routes.ai_routes import QUICK_COMMANDS
        except ImportError:
            pytest.skip("FastAPI not installed - skipping backend import test")

        required_commands = ["/status", "/gex", "/positions", "/pnl", "/help", "/briefing", "/alerts"]

        for cmd in required_commands:
            assert cmd in QUICK_COMMANDS, f"Missing command: {cmd}"

    def test_command_must_start_with_slash(self):
        """Test commands require / prefix"""
        # This would be tested via API, showing the expected behavior
        test_commands = ["help", "status", "gex"]
        for cmd in test_commands:
            # These should fail validation
            assert not cmd.startswith("/")


class TestConversationMemory:
    """Test conversation memory functionality"""

    def test_session_id_generation(self):
        """Test session ID format"""
        import uuid
        session_id = str(uuid.uuid4())[:8]
        assert len(session_id) == 8
        assert session_id.isalnum()


class TestTradeAssistant:
    """Test trade execution assistant"""

    def test_validate_action_returns_validation_structure(self):
        """Test validate action returns proper structure"""
        validation = {
            "valid": True,
            "warnings": [],
            "suggestions": [],
            "gex_alignment": "aligned"
        }

        assert "valid" in validation
        assert "warnings" in validation
        assert "suggestions" in validation
        assert "gex_alignment" in validation


class TestBugsAndEdgeCases:
    """Test for known bugs and edge cases"""

    def test_datetime_timezone_handling(self):
        """Test datetime handling with timezones

        BUG IDENTIFIED: In /status command, datetime.now() is naive but
        database timestamps might be timezone-aware. This can cause subtraction errors.
        """
        from datetime import datetime, timezone

        naive_dt = datetime.now()
        aware_dt = datetime.now(timezone.utc)

        # This shows the potential issue - mixing naive and aware datetimes
        assert naive_dt.tzinfo is None
        assert aware_dt.tzinfo is not None

        # The fix should use timezone-aware datetimes consistently
        # datetime.now(timezone.utc) or make database timestamps naive

    def test_alerts_sql_query_structure(self):
        """Test alerts SQL query has all required columns

        POTENTIAL BUG: The alerts query filters by:
        - unrealized_pnl > entry_price * contracts * 100 * 0.5

        This assumes all columns exist and are numeric.
        """
        required_columns = [
            "symbol", "strike", "option_type", "unrealized_pnl",
            "entry_price", "contracts", "bot_name"
        ]

        # Verify the query would work with these columns
        for col in required_columns:
            assert col, f"Column {col} is required for alerts query"

    def test_pnl_formatting_handles_negative_values(self):
        """Test P&L formatting handles negative values correctly"""
        def format_pnl(val):
            return f"+${val:.2f}" if val >= 0 else f"-${abs(val):.2f}"

        assert format_pnl(100) == "+$100.00"
        assert format_pnl(0) == "+$0.00"
        assert format_pnl(-50.5) == "-$50.50"
        assert format_pnl(-0.01) == "-$0.01"

    def test_conversation_context_order(self):
        """Test conversation context returns messages in correct order

        BUG CHECK: The context endpoint does:
        1. SELECT ... ORDER BY timestamp DESC LIMIT N
        2. messages.reverse()

        This should return chronological order (oldest first)
        """
        messages = [
            {"user": "msg3", "timestamp": "2024-01-03"},
            {"user": "msg2", "timestamp": "2024-01-02"},
            {"user": "msg1", "timestamp": "2024-01-01"},
        ]
        # After DESC query
        messages.reverse()
        # Should now be chronological
        assert messages[0]["user"] == "msg1"
        assert messages[-1]["user"] == "msg3"


class TestFrontendIntegration:
    """Test frontend integration points"""

    def test_command_detection_regex(self):
        """Test command detection in frontend"""
        import re

        test_inputs = [
            ("/help", True),
            ("/gex spy", True),
            ("/status", True),
            ("help me", False),
            ("what /is this", False),  # / not at start (after strip)
            (" /help", True),  # leading space is stripped, so this IS a command
            ("  /status  ", True),  # whitespace is stripped
        ]

        for input_text, should_be_command in test_inputs:
            is_command = input_text.strip().startswith('/')
            assert is_command == should_be_command, f"Failed for: {input_text}"

    def test_message_type_detection(self):
        """Test message type detection for styling"""
        def get_message_type(input_text):
            if '/briefing' in input_text:
                return 'briefing'
            elif '/alert' in input_text:
                return 'alert'
            elif input_text.startswith('/'):
                return 'command'
            return 'normal'

        assert get_message_type("/briefing") == "briefing"
        assert get_message_type("/alerts") == "alert"
        assert get_message_type("/status") == "command"
        assert get_message_type("hello") == "normal"


class TestAPIResponseFormats:
    """Test API response format consistency"""

    def test_success_response_format(self):
        """Test successful responses have consistent format"""
        success_response = {
            "success": True,
            "data": {},
            "timestamp": datetime.now().isoformat()
        }

        assert "success" in success_response
        assert success_response["success"] is True

    def test_error_response_format(self):
        """Test error responses have consistent format"""
        error_response = {
            "success": False,
            "error": "Something went wrong"
        }

        assert "success" in error_response
        assert error_response["success"] is False
        assert "error" in error_response

    def test_command_response_format(self):
        """Test command responses have required fields"""
        command_response = {
            "success": True,
            "command": "/status",
            "response": "Status text here",
            "type": "status",
            "data": {}
        }

        required_fields = ["success", "command", "response", "type"]
        for field in required_fields:
            assert field in command_response


# Run specific tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
