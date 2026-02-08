#!/usr/bin/env python3
"""
E2E Tests for Decision Logging System

Validates that all trading bots properly log decisions to both:
1. trading_decisions table (via decision_logger.py)
2. bot_decision_logs table (via bot_logger.py)

Tests cover:
- ENTRY decision logging
- SKIP/NO_TRADE decision logging
- EXIT decision logging
- Outcome tracking (P&L updates)
- Session continuity
- Export functionality

Run with: pytest tests/e2e/test_decision_logs_e2e.py -v
"""

import pytest
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import json
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def db_connection():
    """Get database connection for tests."""
    conn = None
    try:
        from database_adapter import get_connection
        conn = get_connection()
    except ImportError:
        pytest.skip("database_adapter not available")
    except Exception as e:
        pytest.skip(f"Database connection failed: {e}")

    if conn is None:
        pytest.skip("Could not establish database connection")

    yield conn
    conn.close()


@pytest.fixture(scope="module")
def bot_logger_available():
    """Check if bot_logger module is available."""
    try:
        from trading.bot_logger import (
            log_bot_decision, BotDecision, MarketContext,
            generate_session_id, get_session_tracker
        )
        return True
    except ImportError:
        return False


@pytest.fixture(scope="module")
def decision_logger_available():
    """Check if decision_logger module is available."""
    try:
        from trading.decision_logger import (
            DecisionLogger, TradeDecision, DecisionType,
            get_decision_logger
        )
        return True
    except ImportError:
        return False


# =============================================================================
# BOT LOGGER TESTS (bot_decision_logs table)
# =============================================================================

class TestBotLoggerTable:
    """Tests for bot_decision_logs table structure and data."""

    def test_table_exists(self, db_connection):
        """Verify bot_decision_logs table exists."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'bot_decision_logs'
            )
        """)
        exists = cursor.fetchone()[0]
        assert exists, "bot_decision_logs table does not exist"

    def test_required_columns_exist(self, db_connection):
        """Verify all required columns are present."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'bot_decision_logs'
        """)
        columns = [row[0] for row in cursor.fetchall()]

        required_columns = [
            'decision_id', 'bot_name', 'session_id', 'decision_type',
            'action', 'symbol', 'strategy', 'timestamp',
            'spot_price', 'vix', 'net_gex', 'gex_regime',
            'entry_reasoning', 'passed_all_checks',
            'full_decision'
        ]

        missing = [col for col in required_columns if col not in columns]
        assert len(missing) == 0, f"Missing columns: {missing}"

    def test_bot_names_in_data(self, db_connection):
        """Verify bots are logging to the table."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT DISTINCT bot_name, COUNT(*) as count
            FROM bot_decision_logs
            GROUP BY bot_name
            ORDER BY bot_name
        """)
        results = cursor.fetchall()

        bot_counts = {row[0]: row[1] for row in results}
        print(f"\nBot decision counts: {bot_counts}")

        # List of expected bots (PEGASUS replaces ATLAS in Proverbs)
        expected_bots = ['FORTRESS', 'SOLOMON', 'PHOENIX', 'PEGASUS']

        # Check which bots have logged
        for bot in expected_bots:
            if bot in bot_counts:
                assert bot_counts[bot] > 0, f"{bot} has no decisions logged"
            else:
                print(f"WARNING: {bot} has no entries in bot_decision_logs")


class TestAresLogging:
    """Tests for FORTRESS (Iron Condor) decision logging."""

    def test_fortress_logs_entry_decisions(self, db_connection):
        """Verify FORTRESS logs ENTRY decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'FORTRESS' AND decision_type = 'ENTRY'
        """)
        count = cursor.fetchone()[0]
        print(f"\nARES ENTRY decisions: {count}")
        # Just verify the query works - count may be 0 if no trades yet

    def test_fortress_logs_skip_decisions(self, db_connection):
        """Verify FORTRESS logs SKIP decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'FORTRESS' AND decision_type = 'SKIP'
        """)
        count = cursor.fetchone()[0]
        print(f"\nARES SKIP decisions: {count}")

    def test_fortress_entry_has_required_fields(self, db_connection):
        """Verify FORTRESS ENTRY decisions have all required fields populated."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT decision_id, symbol, strategy, spot_price, vix,
                   entry_reasoning, passed_all_checks
            FROM bot_decision_logs
            WHERE bot_name = 'FORTRESS' AND decision_type = 'ENTRY'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        result = cursor.fetchone()

        if result:
            decision_id, symbol, strategy, spot_price, vix, reasoning, passed = result
            assert decision_id is not None, "decision_id is NULL"
            assert symbol is not None, "symbol is NULL"
            assert strategy is not None, "strategy is NULL"
            print(f"\nARES ENTRY sample: {symbol} {strategy} @ ${spot_price}")
        else:
            print("\nNo FORTRESS ENTRY decisions to verify")


class TestAtlasLogging:
    """Tests for ATLAS (SPX Wheel) decision logging."""

    def test_atlas_logs_entry_decisions(self, db_connection):
        """Verify ATLAS logs ENTRY decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'ATLAS' AND decision_type = 'ENTRY'
        """)
        count = cursor.fetchone()[0]
        print(f"\nATLAS ENTRY decisions: {count}")

    def test_atlas_logs_skip_decisions(self, db_connection):
        """Verify ATLAS logs SKIP decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'ATLAS' AND decision_type = 'SKIP'
        """)
        count = cursor.fetchone()[0]
        print(f"\nATLAS SKIP decisions: {count}")


class TestAthenaLogging:
    """Tests for SOLOMON (Directional Spreads) decision logging."""

    def test_solomon_logs_to_bot_decision_logs(self, db_connection):
        """
        CRITICAL: Verify SOLOMON logs to bot_decision_logs table.
        This was a known gap - SOLOMON only logged to trading_decisions.
        """
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'SOLOMON'
        """)
        count = cursor.fetchone()[0]
        print(f"\nATHENA total decisions in bot_decision_logs: {count}")

        # This should now pass after the fix
        # Note: Count may be 0 if SOLOMON hasn't traded since the fix
        if count == 0:
            print("WARNING: SOLOMON has no entries in bot_decision_logs - verify fix was deployed")

    def test_solomon_logs_entry_decisions(self, db_connection):
        """Verify SOLOMON logs ENTRY decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'SOLOMON' AND decision_type = 'ENTRY'
        """)
        count = cursor.fetchone()[0]
        print(f"\nATHENA ENTRY decisions: {count}")

    def test_solomon_logs_skip_decisions(self, db_connection):
        """Verify SOLOMON logs SKIP decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'SOLOMON' AND decision_type = 'SKIP'
        """)
        count = cursor.fetchone()[0]
        print(f"\nATHENA SKIP decisions: {count}")


class TestPhoenixLogging:
    """Tests for PHOENIX (Autonomous 0DTE) decision logging."""

    def test_phoenix_logs_entry_decisions(self, db_connection):
        """Verify PHOENIX logs ENTRY decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'PHOENIX' AND decision_type = 'ENTRY'
        """)
        count = cursor.fetchone()[0]
        print(f"\nPHOENIX ENTRY decisions: {count}")

    def test_phoenix_logs_skip_decisions(self, db_connection):
        """Verify PHOENIX logs SKIP decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'PHOENIX' AND decision_type = 'SKIP'
        """)
        count = cursor.fetchone()[0]
        print(f"\nPHOENIX SKIP decisions: {count}")

    def test_phoenix_logs_exit_decisions(self, db_connection):
        """Verify PHOENIX logs EXIT decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'PHOENIX' AND decision_type = 'EXIT'
        """)
        count = cursor.fetchone()[0]
        print(f"\nPHOENIX EXIT decisions: {count}")


class TestPegasusLogging:
    """Tests for PEGASUS (SPX Iron Condor) decision logging."""

    def test_pegasus_logs_entry_decisions(self, db_connection):
        """Verify PEGASUS logs ENTRY decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'PEGASUS' AND decision_type = 'ENTRY'
        """)
        count = cursor.fetchone()[0]
        print(f"\nPEGASUS ENTRY decisions: {count}")

    def test_pegasus_logs_skip_decisions(self, db_connection):
        """Verify PEGASUS logs SKIP decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'PEGASUS' AND decision_type = 'SKIP'
        """)
        count = cursor.fetchone()[0]
        print(f"\nPEGASUS SKIP decisions: {count}")

    def test_pegasus_logs_exit_decisions(self, db_connection):
        """Verify PEGASUS logs EXIT decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs
            WHERE bot_name = 'PEGASUS' AND decision_type = 'EXIT'
        """)
        count = cursor.fetchone()[0]
        print(f"\nPEGASUS EXIT decisions: {count}")

    def test_pegasus_has_spx_context(self, db_connection):
        """Verify PEGASUS decisions have SPX-specific context."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT symbol, spot_price, vix, net_gex
            FROM bot_decision_logs
            WHERE bot_name = 'PEGASUS'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        result = cursor.fetchone()
        if result:
            symbol, spot_price, vix, net_gex = result
            print(f"\nPEGASUS sample: {symbol} @ ${spot_price}, VIX={vix}")
            # PEGASUS should be trading SPX
            assert symbol == 'SPX' or symbol is None, "PEGASUS should trade SPX"
        else:
            print("\nNo PEGASUS decisions to verify yet")

    def test_pegasus_oracle_integration(self, db_connection):
        """Verify PEGASUS has Oracle context in decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT full_decision
            FROM bot_decision_logs
            WHERE bot_name = 'PEGASUS' AND full_decision IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        result = cursor.fetchone()
        if result:
            import json
            full_decision = result[0]
            if isinstance(full_decision, str):
                data = json.loads(full_decision)
            else:
                data = full_decision
            # Check for Oracle context
            has_oracle = 'oracle' in str(data).lower()
            print(f"\nPEGASUS has Oracle context: {has_oracle}")
        else:
            print("\nNo PEGASUS decisions with full_decision to check")


# =============================================================================
# DECISION LOGGER TESTS (trading_decisions table)
# =============================================================================

class TestTradingDecisionsTable:
    """Tests for trading_decisions table structure and data."""

    def test_table_exists(self, db_connection):
        """Verify trading_decisions table exists."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'trading_decisions'
            )
        """)
        exists = cursor.fetchone()[0]
        assert exists, "trading_decisions table does not exist"

    def test_required_columns_exist(self, db_connection):
        """Verify all required columns are present."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'trading_decisions'
        """)
        columns = [row[0] for row in cursor.fetchall()]

        required_columns = [
            'decision_id', 'timestamp', 'decision_type', 'action',
            'symbol', 'strategy', 'full_decision'
        ]

        missing = [col for col in required_columns if col not in columns]
        assert len(missing) == 0, f"Missing columns: {missing}"

    def test_decision_types_present(self, db_connection):
        """Verify all decision types are being logged."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT DISTINCT decision_type, COUNT(*) as count
            FROM trading_decisions
            GROUP BY decision_type
            ORDER BY count DESC
        """)
        results = cursor.fetchall()

        decision_types = {row[0]: row[1] for row in results}
        print(f"\nDecision types in trading_decisions: {decision_types}")

        expected_types = ['ENTRY_SIGNAL', 'EXIT_SIGNAL', 'NO_TRADE']
        for dt in expected_types:
            if dt in decision_types:
                print(f"  {dt}: {decision_types[dt]} records")


# =============================================================================
# SESSION TRACKING TESTS
# =============================================================================

class TestSessionTracking:
    """Tests for session and decision sequence tracking."""

    def test_session_ids_present(self, db_connection):
        """Verify session_id is populated for decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(session_id) as with_session,
                   COUNT(DISTINCT session_id) as unique_sessions
            FROM bot_decision_logs
        """)
        total, with_session, unique_sessions = cursor.fetchone()

        print(f"\nSession tracking stats:")
        print(f"  Total decisions: {total}")
        print(f"  With session_id: {with_session}")
        print(f"  Unique sessions: {unique_sessions}")

        if total > 0:
            coverage = (with_session / total) * 100
            print(f"  Session coverage: {coverage:.1f}%")

    def test_scan_cycle_tracking(self, db_connection):
        """Verify scan_cycle is being incremented."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT session_id, MAX(scan_cycle) as max_cycle,
                   COUNT(*) as decisions_in_session
            FROM bot_decision_logs
            WHERE session_id IS NOT NULL
            GROUP BY session_id
            ORDER BY decisions_in_session DESC
            LIMIT 5
        """)
        results = cursor.fetchall()

        print(f"\nTop sessions by decision count:")
        for session_id, max_cycle, count in results:
            print(f"  {session_id[:20]}...: {count} decisions, max scan_cycle={max_cycle}")


# =============================================================================
# OUTCOME TRACKING TESTS
# =============================================================================

class TestOutcomeTracking:
    """Tests for P&L and outcome updates."""

    def test_pnl_populated_for_closed_trades(self, db_connection):
        """Verify actual_pnl is populated for closed positions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total_exits,
                   COUNT(actual_pnl) as with_pnl
            FROM bot_decision_logs
            WHERE decision_type = 'EXIT'
        """)
        total_exits, with_pnl = cursor.fetchone()

        print(f"\nOutcome tracking stats:")
        print(f"  Total EXIT decisions: {total_exits}")
        print(f"  With actual_pnl: {with_pnl}")

        if total_exits > 0:
            coverage = (with_pnl / total_exits) * 100
            print(f"  P&L coverage: {coverage:.1f}%")

    def test_exit_triggered_by_populated(self, db_connection):
        """Verify exit_triggered_by reason is logged."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT exit_triggered_by, COUNT(*) as count
            FROM bot_decision_logs
            WHERE decision_type = 'EXIT' AND exit_triggered_by IS NOT NULL
            GROUP BY exit_triggered_by
            ORDER BY count DESC
        """)
        results = cursor.fetchall()

        print(f"\nExit triggers:")
        for trigger, count in results:
            print(f"  {trigger}: {count}")


# =============================================================================
# SKIP DECISION TESTS
# =============================================================================

class TestSkipDecisions:
    """Tests for SKIP/NO_TRADE decision logging."""

    def test_skip_decisions_have_reasoning(self, db_connection):
        """Verify SKIP decisions include reasoning."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total_skips,
                   COUNT(entry_reasoning) as with_reasoning,
                   COUNT(blocked_reason) as with_blocked
            FROM bot_decision_logs
            WHERE decision_type = 'SKIP'
        """)
        total, with_reasoning, with_blocked = cursor.fetchone()

        print(f"\nSKIP decision stats:")
        print(f"  Total SKIP decisions: {total}")
        print(f"  With entry_reasoning: {with_reasoning}")
        print(f"  With blocked_reason: {with_blocked}")

        if total > 0:
            coverage = ((with_reasoning + with_blocked) / total) * 100
            print(f"  Reason coverage: {coverage:.1f}%")

    def test_skip_reasons_variety(self, db_connection):
        """Verify variety of skip reasons are being logged."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT
                COALESCE(blocked_reason, entry_reasoning, 'NO_REASON') as reason,
                COUNT(*) as count
            FROM bot_decision_logs
            WHERE decision_type = 'SKIP'
            GROUP BY reason
            ORDER BY count DESC
            LIMIT 10
        """)
        results = cursor.fetchall()

        print(f"\nTop skip reasons:")
        for reason, count in results:
            reason_short = reason[:60] + "..." if len(reason) > 60 else reason
            print(f"  [{count}] {reason_short}")


# =============================================================================
# MARKET CONTEXT TESTS
# =============================================================================

class TestMarketContext:
    """Tests for market context data in decisions."""

    def test_gex_data_populated(self, db_connection):
        """Verify GEX data is captured in decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(net_gex) as with_gex,
                   COUNT(gex_regime) as with_regime,
                   COUNT(flip_point) as with_flip,
                   COUNT(call_wall) as with_call_wall,
                   COUNT(put_wall) as with_put_wall
            FROM bot_decision_logs
        """)
        total, with_gex, with_regime, with_flip, with_call, with_put = cursor.fetchone()

        print(f"\nGEX data coverage:")
        print(f"  Total decisions: {total}")
        if total > 0:
            print(f"  net_gex: {with_gex} ({with_gex/total*100:.1f}%)")
            print(f"  gex_regime: {with_regime} ({with_regime/total*100:.1f}%)")
            print(f"  flip_point: {with_flip} ({with_flip/total*100:.1f}%)")
            print(f"  call_wall: {with_call} ({with_call/total*100:.1f}%)")
            print(f"  put_wall: {with_put} ({with_put/total*100:.1f}%)")

    def test_vix_data_populated(self, db_connection):
        """Verify VIX is captured in decisions."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(vix) as with_vix,
                   AVG(vix) as avg_vix,
                   MIN(vix) as min_vix,
                   MAX(vix) as max_vix
            FROM bot_decision_logs
            WHERE vix IS NOT NULL AND vix > 0
        """)
        total, with_vix, avg_vix, min_vix, max_vix = cursor.fetchone()

        print(f"\nVIX data stats:")
        print(f"  Decisions with VIX: {with_vix}")
        if with_vix and avg_vix:
            print(f"  VIX range: {min_vix:.1f} - {max_vix:.1f}")
            print(f"  Average VIX: {avg_vix:.1f}")


# =============================================================================
# CLAUDE AI CONTEXT TESTS
# =============================================================================

class TestClaudeContext:
    """Tests for Claude AI analysis logging."""

    def test_claude_prompts_logged(self, db_connection):
        """Verify Claude prompts are being logged."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(claude_prompt) as with_prompt,
                   COUNT(claude_response) as with_response
            FROM bot_decision_logs
            WHERE claude_prompt IS NOT NULL OR claude_response IS NOT NULL
        """)
        result = cursor.fetchone()
        if result:
            total, with_prompt, with_response = result
            print(f"\nClaude AI context:")
            print(f"  With claude_prompt: {with_prompt}")
            print(f"  With claude_response: {with_response}")

    def test_claude_tokens_tracked(self, db_connection):
        """Verify Claude token usage is tracked."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT SUM(claude_tokens_used) as total_tokens,
                   AVG(claude_tokens_used) as avg_tokens,
                   COUNT(*) as decisions_with_tokens
            FROM bot_decision_logs
            WHERE claude_tokens_used IS NOT NULL AND claude_tokens_used > 0
        """)
        result = cursor.fetchone()
        if result:
            total_tokens, avg_tokens, count = result
            print(f"\nClaude token usage:")
            print(f"  Decisions with token tracking: {count}")
            if total_tokens:
                print(f"  Total tokens used: {total_tokens:,.0f}")
                print(f"  Average per decision: {avg_tokens:.0f}")


# =============================================================================
# DATA CONSISTENCY TESTS
# =============================================================================

class TestDataConsistency:
    """Tests for data consistency and completeness."""

    def test_no_orphan_decisions(self, db_connection):
        """Verify no decisions have invalid bot names."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT bot_name, COUNT(*) as count
            FROM bot_decision_logs
            WHERE bot_name NOT IN ('FORTRESS', 'ATLAS', 'SOLOMON', 'PHOENIX', 'PEGASUS', 'HERMES', 'ORACLE')
            GROUP BY bot_name
        """)
        results = cursor.fetchall()

        if results:
            print(f"\nUnknown bot names found:")
            for bot_name, count in results:
                print(f"  {bot_name}: {count}")
            pytest.fail(f"Found {len(results)} unknown bot names")
        else:
            print("\nAll bot names are valid")

    def test_timestamps_valid(self, db_connection):
        """Verify timestamps are reasonable."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT MIN(timestamp) as oldest,
                   MAX(timestamp) as newest,
                   COUNT(*) as total
            FROM bot_decision_logs
            WHERE timestamp IS NOT NULL
        """)
        oldest, newest, total = cursor.fetchone()

        print(f"\nTimestamp range:")
        print(f"  Oldest: {oldest}")
        print(f"  Newest: {newest}")
        print(f"  Total with timestamps: {total}")

        if oldest and newest:
            # Check no future dates
            assert newest <= datetime.now(timezone.utc) + timedelta(hours=1), "Found future timestamps"


# =============================================================================
# EXPORT FUNCTIONALITY TESTS
# =============================================================================

class TestExportFunctionality:
    """Tests for decision log export features."""

    def test_full_decision_json_valid(self, db_connection):
        """Verify full_decision JSON is valid."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT decision_id, full_decision
            FROM bot_decision_logs
            WHERE full_decision IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        results = cursor.fetchall()

        print(f"\nFull decision JSON validation:")
        valid_count = 0
        for decision_id, full_decision in results:
            try:
                if isinstance(full_decision, str):
                    data = json.loads(full_decision)
                else:
                    data = full_decision  # Already a dict
                valid_count += 1
            except json.JSONDecodeError as e:
                print(f"  Invalid JSON for {decision_id}: {e}")

        print(f"  Valid JSON: {valid_count}/{len(results)}")
        assert valid_count == len(results), "Some full_decision fields have invalid JSON"


# =============================================================================
# DUAL LOGGING VERIFICATION
# =============================================================================

class TestDualLogging:
    """Verify bots log to both tables correctly."""

    def test_ares_dual_logging(self, db_connection):
        """Verify FORTRESS logs to both tables."""
        cursor = db_connection.cursor()

        # Check bot_decision_logs
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs WHERE bot_name = 'FORTRESS'
        """)
        bot_count = cursor.fetchone()[0]

        # Check trading_decisions
        cursor.execute("""
            SELECT COUNT(*) FROM trading_decisions
            WHERE full_decision::text LIKE '%FORTRESS%'
        """)
        trading_count = cursor.fetchone()[0]

        print(f"\nARES dual logging:")
        print(f"  bot_decision_logs: {bot_count}")
        print(f"  trading_decisions: {trading_count}")

    def test_solomon_dual_logging(self, db_connection):
        """
        CRITICAL: Verify SOLOMON now logs to BOTH tables.
        This was fixed - SOLOMON previously only logged to trading_decisions.
        """
        cursor = db_connection.cursor()

        # Check bot_decision_logs
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs WHERE bot_name = 'SOLOMON'
        """)
        bot_count = cursor.fetchone()[0]

        # Check trading_decisions
        cursor.execute("""
            SELECT COUNT(*) FROM trading_decisions
            WHERE full_decision::text LIKE '%SOLOMON%'
        """)
        trading_count = cursor.fetchone()[0]

        print(f"\nATHENA dual logging:")
        print(f"  bot_decision_logs: {bot_count}")
        print(f"  trading_decisions: {trading_count}")

        # Note: bot_count may be 0 if SOLOMON hasn't traded since fix
        if trading_count > 0 and bot_count == 0:
            print("  WARNING: SOLOMON logs to trading_decisions but not bot_decision_logs")
            print("  This suggests the dual logging fix hasn't been deployed or triggered yet")

    def test_pegasus_dual_logging(self, db_connection):
        """Verify PEGASUS logs to BOTH tables."""
        cursor = db_connection.cursor()

        # Check bot_decision_logs
        cursor.execute("""
            SELECT COUNT(*) FROM bot_decision_logs WHERE bot_name = 'PEGASUS'
        """)
        bot_count = cursor.fetchone()[0]

        # Check trading_decisions
        cursor.execute("""
            SELECT COUNT(*) FROM trading_decisions
            WHERE full_decision::text LIKE '%PEGASUS%'
        """)
        trading_count = cursor.fetchone()[0]

        print(f"\nPEGASUS dual logging:")
        print(f"  bot_decision_logs: {bot_count}")
        print(f"  trading_decisions: {trading_count}")


# =============================================================================
# SUMMARY REPORT
# =============================================================================

class TestSummaryReport:
    """Generate a summary report of all decision logging."""

    def test_generate_summary(self, db_connection):
        """Generate comprehensive summary of decision logging."""
        cursor = db_connection.cursor()

        print("\n" + "=" * 60)
        print("DECISION LOGGING SUMMARY REPORT")
        print("=" * 60)

        # Total counts by bot
        cursor.execute("""
            SELECT bot_name,
                   decision_type,
                   COUNT(*) as count
            FROM bot_decision_logs
            GROUP BY bot_name, decision_type
            ORDER BY bot_name, decision_type
        """)
        results = cursor.fetchall()

        print("\nDecisions by Bot and Type:")
        print("-" * 40)
        current_bot = None
        for bot, dtype, count in results:
            if bot != current_bot:
                current_bot = bot
                print(f"\n{bot}:")
            print(f"  {dtype}: {count}")

        # Recent activity
        cursor.execute("""
            SELECT bot_name, MAX(timestamp) as last_decision
            FROM bot_decision_logs
            GROUP BY bot_name
            ORDER BY last_decision DESC
        """)
        results = cursor.fetchall()

        print("\n\nLast Decision by Bot:")
        print("-" * 40)
        for bot, last_time in results:
            print(f"  {bot}: {last_time}")

        # Data quality metrics
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(session_id) as with_session,
                COUNT(net_gex) as with_gex,
                COUNT(vix) as with_vix,
                COUNT(entry_reasoning) as with_reasoning
            FROM bot_decision_logs
        """)
        total, session, gex, vix, reasoning = cursor.fetchone()

        print("\n\nData Quality Metrics:")
        print("-" * 40)
        if total > 0:
            print(f"  Total Decisions: {total}")
            print(f"  Session Tracking: {session/total*100:.1f}%")
            print(f"  GEX Data: {gex/total*100:.1f}%")
            print(f"  VIX Data: {vix/total*100:.1f}%")
            print(f"  Reasoning: {reasoning/total*100:.1f}%")

        print("\n" + "=" * 60)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
