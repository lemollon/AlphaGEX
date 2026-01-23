"""
Bot Daily Report Generator

Generates end-of-day reports for trading bots with:
- Trade-by-trade analysis
- Intraday price action from Yahoo Finance
- Claude AI analysis with anti-hallucination constraints
- Archive storage for ML training

Author: AlphaGEX
Date: January 2025
"""

import json
import logging
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple, Union
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Claude model to use
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _safe_json_dumps(obj: Any, default_value: str = "{}") -> str:
    """
    Safely serialize object to JSON string.

    Handles Decimal, datetime, date, and other non-serializable types.
    Returns default_value on failure.
    """
    def json_serializer(o):
        if isinstance(o, Decimal):
            return float(o)
        elif isinstance(o, (datetime, date)):
            return o.isoformat()
        elif hasattr(o, '__dict__'):
            return str(o)
        else:
            return str(o)

    try:
        return json.dumps(obj, default=json_serializer)
    except Exception as e:
        logger.warning(f"JSON serialization failed: {e}")
        return default_value


def _safe_get(d: Optional[Dict], *keys, default=None):
    """
    Safely get nested dictionary values.

    Usage: _safe_get(data, "level1", "level2", default="N/A")
    """
    if d is None:
        return default

    result = d
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
        else:
            return default
        if result is None:
            return default

    return result if result is not None else default


@contextmanager
def _db_connection():
    """
    Context manager for database connections.

    Ensures connection is always closed, even on error.
    Rolls back on exception.
    """
    conn = None
    try:
        conn = get_connection()
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _extract_claude_response_text(message: Any) -> Optional[str]:
    """
    Safely extract text from a Claude API response.

    Args:
        message: The response from client.messages.create()

    Returns:
        The text content, or None if extraction fails
    """
    try:
        if message is None:
            logger.warning("Claude response is None")
            return None

        if not hasattr(message, 'content'):
            logger.warning("Claude response has no 'content' attribute")
            return None

        if not message.content:
            logger.warning("Claude response content is empty")
            return None

        first_block = message.content[0]

        if not hasattr(first_block, 'text'):
            logger.warning(f"First content block has no 'text' attribute: {type(first_block)}")
            return None

        return first_block.text.strip()

    except (IndexError, AttributeError, TypeError) as e:
        logger.warning(f"Could not extract text from Claude response: {e}")
        return None


def _parse_claude_json_response(response_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Parse JSON from Claude's response, handling markdown code blocks.

    Args:
        response_text: The raw text from Claude

    Returns:
        Parsed JSON dict, or None if parsing fails
    """
    if not response_text:
        return None

    try:
        # Handle potential markdown code blocks
        text = response_text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            # Try to extract from generic code block
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]

        return json.loads(text.strip())

    except (json.JSONDecodeError, IndexError, ValueError) as e:
        logger.warning(f"Could not parse Claude JSON response: {e}")
        logger.debug(f"Response text was: {response_text[:500] if response_text else 'None'}")
        return None


# Valid bot names
VALID_BOTS = ['ares', 'athena', 'titan', 'pegasus', 'icarus']

# Bot position table mapping
BOT_POSITION_TABLES = {
    'ares': 'ares_positions',
    'athena': 'athena_positions',
    'titan': 'titan_positions',
    'pegasus': 'pegasus_positions',
    'icarus': 'icarus_positions',
}

# Bot scan activity source
# Some bots use unified scan_activity, others have their own tables
BOT_SCAN_SOURCES = {
    'ares': 'scan_activity',
    'athena': 'scan_activity',
    'titan': 'scan_activity',
    'pegasus': 'scan_activity',
    'icarus': 'scan_activity',
}

# Database connection
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    get_connection = None

# Yahoo intraday fetcher
try:
    from backend.services.yahoo_intraday import (
        fetch_ticks_for_trades,
        fetch_vix_history,
        find_high_low_during_trade,
        find_level_tests,
        BOT_SYMBOLS,
        YFINANCE_AVAILABLE
    )
    # Only mark as available if yfinance is actually installed
    YAHOO_AVAILABLE = YFINANCE_AVAILABLE
except ImportError:
    YAHOO_AVAILABLE = False
    YFINANCE_AVAILABLE = False
    logger.warning("Yahoo intraday service not available")

# Claude API
try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    logger.warning("Anthropic SDK not available")


# =============================================================================
# DATABASE TABLE INITIALIZATION
# =============================================================================

def _ensure_report_tables_exist():
    """Create report tables for all bots."""
    if not DB_AVAILABLE:
        logger.warning("Database not available - cannot create report tables")
        return False

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        for bot in VALID_BOTS:
            table_name = f"{bot}_daily_reports"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,

                    -- Unique key
                    report_date DATE UNIQUE NOT NULL,

                    -- Raw data (JSONB for ML training)
                    trades_data JSONB NOT NULL DEFAULT '[]',
                    intraday_ticks JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    scan_activity JSONB NOT NULL DEFAULT '[]',
                    market_context JSONB NOT NULL DEFAULT '{{}}'::jsonb,

                    -- Generated analysis
                    trade_analyses JSONB NOT NULL DEFAULT '[]',
                    daily_summary TEXT,
                    lessons_learned TEXT[] DEFAULT ARRAY[]::TEXT[],

                    -- Metrics (for quick queries)
                    total_pnl DECIMAL(12,2) DEFAULT 0,
                    trade_count INTEGER DEFAULT 0,
                    win_count INTEGER DEFAULT 0,
                    loss_count INTEGER DEFAULT 0,

                    -- Metadata
                    generated_at TIMESTAMP WITH TIME ZONE,
                    generation_model VARCHAR(50),
                    generation_duration_ms INTEGER,
                    archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Create index for date queries
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {table_name}_date_idx
                ON {table_name}(report_date)
            """)

            logger.info(f"Ensured table {table_name} exists")

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"Error creating report tables: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# Initialize tables on module import
_ensure_report_tables_exist()


# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_closed_trades_for_date(bot: str, report_date: date) -> List[Dict[str, Any]]:
    """
    Fetch all closed trades for a bot on a specific date.

    Args:
        bot: Bot name (lowercase)
        report_date: Date to fetch trades for

    Returns:
        List of trade dicts
    """
    if not DB_AVAILABLE:
        return []

    table = BOT_POSITION_TABLES.get(bot)
    if not table:
        logger.error(f"Unknown bot: {bot}")
        return []

    try:
        with _db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"""
                SELECT *
                FROM {table}
                WHERE status IN ('closed', 'expired')
                AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
                ORDER BY close_time ASC
            """, (report_date,))

            columns = [desc[0] for desc in cursor.description]
            trades = []

            for row in cursor.fetchall():
                trade = dict(zip(columns, row))
                # Convert Decimal to float for JSON serialization
                for key, value in trade.items():
                    if isinstance(value, Decimal):
                        trade[key] = float(value)
                    elif isinstance(value, datetime):
                        trade[key] = value.isoformat()
                    elif isinstance(value, date):
                        trade[key] = value.isoformat()
                trades.append(trade)

            logger.info(f"Fetched {len(trades)} closed trades for {bot} on {report_date}")
            return trades

    except Exception as e:
        logger.error(f"Error fetching trades for {bot}: {e}")
        return []


def fetch_scan_activity_for_date(bot: str, report_date: date) -> List[Dict[str, Any]]:
    """
    Fetch scan activity for a bot on a specific date.

    Args:
        bot: Bot name (lowercase)
        report_date: Date to fetch scans for

    Returns:
        List of scan activity dicts
    """
    if not DB_AVAILABLE:
        return []

    source_table = BOT_SCAN_SOURCES.get(bot, 'scan_activity')

    try:
        with _db_connection() as conn:
            cursor = conn.cursor()

            # Check if table exists and has bot_name column
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'bot_name'
            """, (source_table,))
            has_bot_column = cursor.fetchone() is not None

            if has_bot_column:
                cursor.execute(f"""
                    SELECT *
                    FROM {source_table}
                    WHERE bot_name = %s
                    AND DATE(timestamp AT TIME ZONE 'America/Chicago') = %s
                    ORDER BY timestamp ASC
                """, (bot.upper(), report_date))
            else:
                cursor.execute(f"""
                    SELECT *
                    FROM {source_table}
                    WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = %s
                    ORDER BY timestamp ASC
                """, (report_date,))

            columns = [desc[0] for desc in cursor.description]
            scans = []

            for row in cursor.fetchall():
                scan = dict(zip(columns, row))
                # Convert types for JSON
                for key, value in scan.items():
                    if isinstance(value, Decimal):
                        scan[key] = float(value)
                    elif isinstance(value, datetime):
                        scan[key] = value.isoformat()
                    elif isinstance(value, date):
                        scan[key] = value.isoformat()
                scans.append(scan)

            logger.info(f"Fetched {len(scans)} scans for {bot} on {report_date}")
            return scans

    except Exception as e:
        logger.error(f"Error fetching scan activity for {bot}: {e}")
        return []


def build_market_context(
    scans: List[Dict[str, Any]],
    report_date: date
) -> Dict[str, Any]:
    """
    Build market context from scan activity.

    Extracts VIX levels, GEX data, and key events throughout the day.
    """
    context = {
        "date": report_date.isoformat(),
        "vix_history": [],
        "gex_snapshots": [],
        "events": [],
        "summary": {}
    }

    if not scans:
        return context

    vix_values = []
    gex_regimes = []

    for scan in scans:
        timestamp = scan.get("timestamp", scan.get("scan_time"))

        # Extract VIX
        vix = scan.get("vix")
        if vix:
            vix_values.append(vix)
            context["vix_history"].append({
                "timestamp": timestamp,
                "vix": vix
            })

        # Extract GEX data
        gex_regime = scan.get("gex_regime")
        if gex_regime:
            gex_regimes.append(gex_regime)
            context["gex_snapshots"].append({
                "timestamp": timestamp,
                "regime": gex_regime,
                "call_wall": scan.get("call_wall"),
                "put_wall": scan.get("put_wall"),
                "flip_point": scan.get("flip_point"),
                "net_gex": scan.get("net_gex")
            })

        # Check for events
        if scan.get("is_fomc_day"):
            context["events"].append({"type": "FOMC", "timestamp": timestamp})
        if scan.get("is_cpi_day"):
            context["events"].append({"type": "CPI", "timestamp": timestamp})

    # Build summary
    if vix_values:
        context["summary"]["vix_open"] = vix_values[0]
        context["summary"]["vix_close"] = vix_values[-1]
        context["summary"]["vix_high"] = max(vix_values)
        context["summary"]["vix_low"] = min(vix_values)

    if gex_regimes:
        # Count regime occurrences
        from collections import Counter
        regime_counts = Counter(gex_regimes)
        context["summary"]["dominant_regime"] = regime_counts.most_common(1)[0][0]
        context["summary"]["regime_changes"] = len(set(gex_regimes))

    return context


# =============================================================================
# CLAUDE AI ANALYSIS
# =============================================================================

TRADE_ANALYSIS_PROMPT = """You are a trading analyst reviewing a bot's trade.
You must ONLY reference data provided - never speculate or infer.

## STRICT RULES
1. Every price claim MUST cite a timestamp from tick_data
2. Every level reference MUST match market_context exactly
3. NEVER say "the market felt" or "traders were nervous"
4. NEVER speculate about "what could have happened"
5. Use exact numbers: "price reached 5945.50 at 10:15" not "around 5945"
6. If data is missing, say "data not available" - don't guess

## TRADE DATA
Position ID: {position_id}
Entry Time: {entry_time}
Exit Time: {exit_time}
Entry Price (underlying): ${entry_price}
P&L: ${pnl}
Close Reason: {close_reason}

## MARKET CONTEXT AT ENTRY
VIX: {vix_at_entry}
Call Wall: {call_wall}
Put Wall: {put_wall}
Flip Point: {flip_point}
GEX Regime: {gex_regime}
Oracle Reasoning: {oracle_reasoning}

## INTRADAY PRICE DATA (selected candles)
{tick_summary}

## PRICE ACTION METRICS
High after entry: ${high_price} at {high_time}
Low after entry: ${low_price} at {low_time}
Levels tested: {levels_tested}

Respond with ONLY valid JSON (no markdown, no explanation):
{{
  "entry_analysis": {{
    "quality": "GOOD|FAIR|POOR",
    "reasoning": "<1-2 sentences citing specific times/prices>"
  }},
  "price_action_summary": "<2-3 sentences describing what happened with timestamps>",
  "exit_analysis": {{
    "was_optimal": true|false,
    "reasoning": "<1-2 sentences>"
  }},
  "why_won_or_lost": "<1-2 sentences with specific price references>",
  "lesson": "<1 actionable sentence for future trades>",
  "key_timestamps": [
    {{"time": "HH:MM", "event": "description", "price": 0.00}}
  ]
}}
"""

DAILY_SUMMARY_PROMPT = """You are summarizing a trading bot's daily performance.
You must ONLY reference the provided data - never speculate.

## RULES
1. Cite specific trade IDs when referencing trades
2. Use exact P&L numbers
3. Reference specific times and prices
4. No speculation about market psychology

## TODAY'S TRADES
{trades_summary}

## MARKET CONTEXT
Date: {date}
VIX Range: {vix_low} - {vix_high}
Dominant GEX Regime: {dominant_regime}
Events: {events}

## INDIVIDUAL TRADE ANALYSES
{trade_analyses}

Respond with ONLY valid JSON:
{{
  "daily_summary": "<3-5 sentences summarizing the day's trading with specific references>",
  "total_pnl": {total_pnl},
  "win_rate": "{win_rate}%",
  "lessons_learned": [
    "<lesson 1 - specific and actionable>",
    "<lesson 2 - specific and actionable>"
  ],
  "best_trade": {{
    "position_id": "<id>",
    "reason": "<why it was the best>"
  }},
  "worst_trade": {{
    "position_id": "<id>",
    "reason": "<why it was the worst>"
  }}
}}
"""


def analyze_trade_with_claude(
    trade: Dict[str, Any],
    ticks: List[Dict[str, Any]],
    market_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze a single trade using Claude with anti-hallucination constraints.

    Args:
        trade: Trade data
        ticks: Intraday candles for this trade
        market_context: Market context at trade time

    Returns:
        Analysis dict from Claude
    """
    if not CLAUDE_AVAILABLE:
        return _fallback_trade_analysis(trade, ticks)

    try:
        # Get API key
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if not api_key:
            logger.warning("No Claude API key found")
            return _fallback_trade_analysis(trade, ticks)

        client = anthropic.Anthropic(api_key=api_key)

        # Build tick summary (sample key candles to reduce token usage)
        tick_summary = _build_tick_summary(ticks, trade)

        # Find high/low during trade
        high_low = find_high_low_during_trade(
            ticks,
            trade.get("open_time"),
            trade.get("close_time")
        ) if YAHOO_AVAILABLE and ticks else {"high": None, "low": None}

        # Find level tests
        levels = {
            "call_wall": trade.get("call_wall"),
            "put_wall": trade.get("put_wall"),
            "flip_point": market_context.get("summary", {}).get("flip_point")
        }
        levels_tested = find_level_tests(ticks, levels) if YAHOO_AVAILABLE and ticks else []

        # Format prompt
        prompt = TRADE_ANALYSIS_PROMPT.format(
            position_id=trade.get("position_id", "UNKNOWN"),
            entry_time=trade.get("open_time", "N/A"),
            exit_time=trade.get("close_time", "N/A"),
            entry_price=trade.get("underlying_at_entry", 0),
            pnl=trade.get("realized_pnl", 0),
            close_reason=trade.get("close_reason", "unknown"),
            vix_at_entry=trade.get("vix_at_entry", "N/A"),
            call_wall=trade.get("call_wall", "N/A"),
            put_wall=trade.get("put_wall", "N/A"),
            flip_point=levels.get("flip_point", "N/A"),
            gex_regime=trade.get("gex_regime", "N/A"),
            oracle_reasoning=trade.get("oracle_reasoning", "N/A"),
            tick_summary=tick_summary,
            high_price=high_low.get("high", {}).get("price", "N/A") if high_low.get("high") else "N/A",
            high_time=high_low.get("high", {}).get("timestamp", "N/A") if high_low.get("high") else "N/A",
            low_price=high_low.get("low", {}).get("price", "N/A") if high_low.get("low") else "N/A",
            low_time=high_low.get("low", {}).get("timestamp", "N/A") if high_low.get("low") else "N/A",
            levels_tested=json.dumps(levels_tested[:5]) if levels_tested else "None"
        )

        # Call Claude
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse response safely
        response_text = _extract_claude_response_text(message)
        if not response_text:
            logger.warning("Could not extract text from Claude trade analysis response")
            return _fallback_trade_analysis(trade, ticks)

        analysis = _parse_claude_json_response(response_text)
        if not analysis:
            logger.warning(f"Could not parse Claude trade analysis as JSON: {response_text[:200]}")
            return _fallback_trade_analysis(trade, ticks)

        # Add metadata
        analysis["position_id"] = trade.get("position_id")
        analysis["pnl"] = trade.get("realized_pnl", 0)
        analysis["_generated_by"] = "claude-3-5-sonnet"
        return analysis

    except Exception as e:
        logger.error(f"Error calling Claude for trade analysis: {e}")
        return _fallback_trade_analysis(trade, ticks)


def _fallback_trade_analysis(trade: Dict[str, Any], ticks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate basic analysis without Claude."""
    pnl = trade.get("realized_pnl", 0)
    won = pnl > 0

    return {
        "position_id": trade.get("position_id"),
        "pnl": pnl,
        "entry_analysis": {
            "quality": "FAIR",
            "reasoning": "Automated analysis unavailable - manual review recommended"
        },
        "price_action_summary": f"Trade {'won' if won else 'lost'} ${abs(pnl):.2f}. Close reason: {trade.get('close_reason', 'unknown')}",
        "exit_analysis": {
            "was_optimal": won,
            "reasoning": "Based on P&L outcome"
        },
        "why_won_or_lost": f"{'Profit target reached' if won else 'Stop loss or adverse move'} - {trade.get('close_reason', 'unknown')}",
        "lesson": "Review trade manually for specific insights",
        "key_timestamps": [],
        "_generated_by": "fallback"
    }


def _build_tick_summary(ticks: List[Dict[str, Any]], trade: Dict[str, Any]) -> str:
    """Build a summary of key tick data for the prompt."""
    if not ticks:
        return "No intraday data available"

    def _format_candle(candle: Dict[str, Any], prefix: str = "") -> str:
        """Safely format a candle dict."""
        time_ct = candle.get('time_ct', 'N/A')
        open_p = candle.get('open', 'N/A')
        high_p = candle.get('high', 'N/A')
        low_p = candle.get('low', 'N/A')
        close_p = candle.get('close', 'N/A')
        return f"{prefix}{time_ct} O:{open_p} H:{high_p} L:{low_p} C:{close_p}"

    # Sample key candles: first, last, high, low, and every 15 mins
    summary_lines = []

    # Entry candle
    if ticks:
        try:
            summary_lines.append(_format_candle(ticks[0], "Entry area: "))
        except (IndexError, TypeError) as e:
            logger.warning(f"Could not format entry candle: {e}")

    # Sample every 15 candles (roughly 15 minutes for 1-min data)
    for i in range(0, len(ticks), 15):
        if i > 0 and i < len(ticks) - 1:
            try:
                summary_lines.append(_format_candle(ticks[i]))
            except (IndexError, TypeError) as e:
                logger.warning(f"Could not format candle at index {i}: {e}")

    # Exit candle
    if len(ticks) > 1:
        try:
            summary_lines.append(_format_candle(ticks[-1], "Exit area: "))
        except (IndexError, TypeError) as e:
            logger.warning(f"Could not format exit candle: {e}")

    return "\n".join(summary_lines[:20])  # Limit to 20 lines


def generate_daily_summary_with_claude(
    trades: List[Dict[str, Any]],
    trade_analyses: List[Dict[str, Any]],
    market_context: Dict[str, Any],
    report_date: date
) -> Dict[str, Any]:
    """
    Generate daily summary using Claude.

    Args:
        trades: All trades for the day
        trade_analyses: Individual trade analyses
        market_context: Market context for the day
        report_date: Report date

    Returns:
        Daily summary dict
    """
    if not trades:
        return {
            "daily_summary": "No trades executed today.",
            "total_pnl": 0,
            "win_rate": "N/A",
            "lessons_learned": [],
            "best_trade": None,
            "worst_trade": None
        }

    if not CLAUDE_AVAILABLE:
        return _fallback_daily_summary(trades, trade_analyses)

    try:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if not api_key:
            return _fallback_daily_summary(trades, trade_analyses)

        client = anthropic.Anthropic(api_key=api_key)

        # Build trades summary
        total_pnl = sum(t.get("realized_pnl", 0) for t in trades)
        wins = sum(1 for t in trades if t.get("realized_pnl", 0) > 0)
        win_rate = (wins / len(trades) * 100) if trades else 0

        trades_summary = "\n".join([
            f"- {t.get('position_id')}: P&L ${t.get('realized_pnl', 0):.2f}, Reason: {t.get('close_reason', 'N/A')}"
            for t in trades
        ])

        analyses_summary = "\n".join([
            f"- {a.get('position_id')}: {a.get('why_won_or_lost', 'N/A')}"
            for a in trade_analyses
        ])

        # Market context summary
        ctx_summary = market_context.get("summary", {})
        events = ", ".join([e.get("type", "") for e in market_context.get("events", [])]) or "None"

        prompt = DAILY_SUMMARY_PROMPT.format(
            trades_summary=trades_summary,
            date=report_date.isoformat(),
            vix_low=ctx_summary.get("vix_low", "N/A"),
            vix_high=ctx_summary.get("vix_high", "N/A"),
            dominant_regime=ctx_summary.get("dominant_regime", "N/A"),
            events=events,
            trade_analyses=analyses_summary,
            total_pnl=total_pnl,
            win_rate=f"{win_rate:.1f}"
        )

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse response safely
        response_text = _extract_claude_response_text(message)
        if not response_text:
            logger.warning("Could not extract text from Claude daily summary response")
            return _fallback_daily_summary(trades, trade_analyses)

        summary = _parse_claude_json_response(response_text)
        if not summary:
            logger.warning(f"Could not parse daily summary as JSON: {response_text[:200]}")
            return _fallback_daily_summary(trades, trade_analyses)

        summary["_generated_by"] = "claude-3-5-sonnet"
        return summary

    except Exception as e:
        logger.error(f"Error generating daily summary: {e}")
        return _fallback_daily_summary(trades, trade_analyses)


def _fallback_daily_summary(
    trades: List[Dict[str, Any]],
    trade_analyses: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Generate basic daily summary without Claude."""
    total_pnl = sum(t.get("realized_pnl", 0) for t in trades)
    wins = sum(1 for t in trades if t.get("realized_pnl", 0) > 0)
    losses = len(trades) - wins
    win_rate = (wins / len(trades) * 100) if trades else 0

    # Find best/worst trades
    sorted_trades = sorted(trades, key=lambda x: x.get("realized_pnl", 0), reverse=True)
    best = sorted_trades[0] if sorted_trades else None
    worst = sorted_trades[-1] if sorted_trades else None

    return {
        "daily_summary": f"Executed {len(trades)} trades with {wins} wins and {losses} losses. Total P&L: ${total_pnl:.2f}",
        "total_pnl": total_pnl,
        "win_rate": f"{win_rate:.1f}%",
        "lessons_learned": [
            f"Win rate was {win_rate:.1f}% - {'above' if win_rate >= 50 else 'below'} breakeven",
            "Review individual trades for specific patterns"
        ],
        "best_trade": {
            "position_id": best.get("position_id") if best else None,
            "reason": f"Best P&L: ${best.get('realized_pnl', 0):.2f}" if best else None
        },
        "worst_trade": {
            "position_id": worst.get("position_id") if worst else None,
            "reason": f"Worst P&L: ${worst.get('realized_pnl', 0):.2f}" if worst else None
        },
        "_generated_by": "fallback"
    }


# =============================================================================
# MAIN REPORT GENERATION
# =============================================================================

def generate_report_for_bot(
    bot: str,
    report_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Generate a complete daily report for a bot.

    Args:
        bot: Bot name (lowercase)
        report_date: Date to generate report for (default: today)

    Returns:
        Complete report dict
    """
    bot = bot.lower()
    if bot not in VALID_BOTS:
        raise ValueError(f"Invalid bot: {bot}. Must be one of {VALID_BOTS}")

    if report_date is None:
        report_date = datetime.now(CENTRAL_TZ).date()
    elif isinstance(report_date, str):
        report_date = datetime.strptime(report_date, "%Y-%m-%d").date()

    start_time = time.time()
    logger.info(f"Generating report for {bot.upper()} on {report_date}")

    # Step 1: Fetch closed trades
    trades = fetch_closed_trades_for_date(bot, report_date)

    # If no trades, return None (don't generate empty reports)
    if not trades:
        logger.info(f"No trades for {bot.upper()} on {report_date} - skipping report generation")
        return None

    # Step 2: Fetch scan activity
    scans = fetch_scan_activity_for_date(bot, report_date)

    # Step 3: Fetch intraday ticks from Yahoo
    intraday_ticks = {}
    if YAHOO_AVAILABLE and trades:
        intraday_ticks = fetch_ticks_for_trades(trades, bot)

    # Step 4: Build market context
    market_context = build_market_context(scans, report_date)

    # Step 5: Analyze each trade with Claude
    trade_analyses = []
    for trade in trades:
        position_id = trade.get("position_id")
        ticks = intraday_ticks.get(position_id, [])
        analysis = analyze_trade_with_claude(trade, ticks, market_context)
        trade_analyses.append(analysis)

    # Step 6: Generate daily summary
    daily_summary_data = generate_daily_summary_with_claude(
        trades, trade_analyses, market_context, report_date
    )

    # Calculate metrics
    total_pnl = sum(t.get("realized_pnl", 0) for t in trades)
    win_count = sum(1 for t in trades if t.get("realized_pnl", 0) > 0)
    loss_count = len(trades) - win_count

    generation_time_ms = int((time.time() - start_time) * 1000)

    # Build complete report
    report = {
        "report_date": report_date.isoformat(),
        "bot": bot.upper(),
        "trades_data": trades,
        "intraday_ticks": intraday_ticks,
        "scan_activity": scans,
        "market_context": market_context,
        "trade_analyses": trade_analyses,
        "daily_summary": daily_summary_data.get("daily_summary", ""),
        "lessons_learned": daily_summary_data.get("lessons_learned", []),
        "total_pnl": total_pnl,
        "trade_count": len(trades),
        "win_count": win_count,
        "loss_count": loss_count,
        "generated_at": datetime.now(CENTRAL_TZ).isoformat(),
        "generation_model": "claude-3-5-sonnet" if CLAUDE_AVAILABLE else "fallback",
        "generation_duration_ms": generation_time_ms
    }

    # Step 7: Save to archive
    save_report_to_archive(bot, report)

    logger.info(f"Generated report for {bot.upper()} in {generation_time_ms}ms: {len(trades)} trades, ${total_pnl:.2f} P&L")

    return report


def save_report_to_archive(bot: str, report: Dict[str, Any]) -> bool:
    """
    Save a report to the archive table.

    Args:
        bot: Bot name
        report: Report dict

    Returns:
        True if saved successfully
    """
    if not DB_AVAILABLE:
        logger.warning("Database not available - cannot save report")
        return False

    try:
        with _db_connection() as conn:
            cursor = conn.cursor()

            table_name = f"{bot.lower()}_daily_reports"

            # Use _safe_json_dumps to handle Decimal, datetime, and other types
            cursor.execute(f"""
                INSERT INTO {table_name} (
                    report_date,
                    trades_data,
                    intraday_ticks,
                    scan_activity,
                    market_context,
                    trade_analyses,
                    daily_summary,
                    lessons_learned,
                    total_pnl,
                    trade_count,
                    win_count,
                    loss_count,
                    generated_at,
                    generation_model,
                    generation_duration_ms,
                    archived_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (report_date) DO UPDATE SET
                    trades_data = EXCLUDED.trades_data,
                    intraday_ticks = EXCLUDED.intraday_ticks,
                    scan_activity = EXCLUDED.scan_activity,
                    market_context = EXCLUDED.market_context,
                    trade_analyses = EXCLUDED.trade_analyses,
                    daily_summary = EXCLUDED.daily_summary,
                    lessons_learned = EXCLUDED.lessons_learned,
                    total_pnl = EXCLUDED.total_pnl,
                    trade_count = EXCLUDED.trade_count,
                    win_count = EXCLUDED.win_count,
                    loss_count = EXCLUDED.loss_count,
                    generated_at = EXCLUDED.generated_at,
                    generation_model = EXCLUDED.generation_model,
                    generation_duration_ms = EXCLUDED.generation_duration_ms,
                    archived_at = NOW()
            """, (
                _safe_get(report, "report_date", default=""),
                _safe_json_dumps(_safe_get(report, "trades_data", default=[]), "[]"),
                _safe_json_dumps(_safe_get(report, "intraday_ticks", default={}), "{}"),
                _safe_json_dumps(_safe_get(report, "scan_activity", default=[]), "[]"),
                _safe_json_dumps(_safe_get(report, "market_context", default={}), "{}"),
                _safe_json_dumps(_safe_get(report, "trade_analyses", default=[]), "[]"),
                _safe_get(report, "daily_summary", default=""),
                _safe_get(report, "lessons_learned", default=[]),
                _safe_get(report, "total_pnl", default=0),
                _safe_get(report, "trade_count", default=0),
                _safe_get(report, "win_count", default=0),
                _safe_get(report, "loss_count", default=0),
                _safe_get(report, "generated_at", default=""),
                _safe_get(report, "generation_model", default=""),
                _safe_get(report, "generation_duration_ms", default=0)
            ))

            logger.info(f"Saved report to {table_name} for {_safe_get(report, 'report_date')}")
            return True

    except Exception as e:
        logger.error(f"Error saving report: {e}")
        traceback.print_exc()
        return False


def get_report_from_archive(bot: str, report_date: date) -> Optional[Dict[str, Any]]:
    """
    Retrieve a report from the archive.

    Args:
        bot: Bot name
        report_date: Date to retrieve

    Returns:
        Report dict or None if not found
    """
    if not DB_AVAILABLE:
        return None

    try:
        with _db_connection() as conn:
            cursor = conn.cursor()

            table_name = f"{bot.lower()}_daily_reports"

            cursor.execute(f"""
                SELECT * FROM {table_name}
                WHERE report_date = %s
            """, (report_date,))

            row = cursor.fetchone()

            if not row:
                return None

            # Get columns BEFORE closing connection
            columns = [desc[0] for desc in cursor.description]
            report = dict(zip(columns, row))

            # Convert types
            for key in ['trades_data', 'intraday_ticks', 'scan_activity', 'market_context', 'trade_analyses']:
                if key in report and isinstance(report[key], str):
                    try:
                        report[key] = json.loads(report[key])
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse JSON for {key}")
                        report[key] = {} if key.endswith('ticks') or key.endswith('context') else []

            for key in ['report_date']:
                if key in report and isinstance(report[key], date):
                    report[key] = report[key].isoformat()

            for key in ['generated_at', 'archived_at']:
                if key in report and isinstance(report[key], datetime):
                    report[key] = report[key].isoformat()

            for key in ['total_pnl']:
                if key in report and isinstance(report[key], Decimal):
                    report[key] = float(report[key])

            return report

    except Exception as e:
        logger.error(f"Error retrieving report: {e}")
        return None


def get_archive_list(
    bot: str,
    limit: int = 30,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Get list of archived reports (summary only).

    Args:
        bot: Bot name
        limit: Max reports to return
        offset: Pagination offset

    Returns:
        Tuple of (list of report summaries, total count)
    """
    if not DB_AVAILABLE:
        return [], 0

    try:
        with _db_connection() as conn:
            cursor = conn.cursor()

            table_name = f"{bot.lower()}_daily_reports"

            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count_row = cursor.fetchone()
            total = count_row[0] if count_row else 0

            # Get summaries
            cursor.execute(f"""
                SELECT
                    report_date,
                    total_pnl,
                    trade_count,
                    win_count,
                    loss_count,
                    lessons_learned,
                    generated_at
                FROM {table_name}
                ORDER BY report_date DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))

            reports = []
            for row in cursor.fetchall():
                reports.append({
                    "report_date": row[0].isoformat() if isinstance(row[0], date) else row[0],
                    "total_pnl": float(row[1]) if row[1] else 0,
                    "trade_count": row[2] or 0,
                    "win_count": row[3] or 0,
                    "loss_count": row[4] or 0,
                    "lessons_learned": row[5] or [],
                    "generated_at": row[6].isoformat() if isinstance(row[6], datetime) else row[6]
                })

            return reports, total

    except Exception as e:
        logger.error(f"Error getting archive list: {e}")
        return [], 0


def get_archive_stats(bot: str) -> Dict[str, Any]:
    """
    Get archive statistics for a bot.

    Args:
        bot: Bot name

    Returns:
        Stats dict with total_reports, total_trades, total_wins, total_losses,
        total_pnl, best_day, worst_day, date_range
    """
    if not DB_AVAILABLE:
        return {"total_reports": 0}

    try:
        with _db_connection() as conn:
            cursor = conn.cursor()

            table_name = f"{bot.lower()}_daily_reports"

            # Get aggregate stats
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_reports,
                    MIN(report_date) as oldest_date,
                    MAX(report_date) as newest_date,
                    COALESCE(SUM(trade_count), 0) as total_trades,
                    COALESCE(SUM(win_count), 0) as total_wins,
                    COALESCE(SUM(loss_count), 0) as total_losses,
                    COALESCE(SUM(total_pnl), 0) as total_pnl_all_time,
                    AVG(total_pnl) as avg_daily_pnl
                FROM {table_name}
            """)

            row = cursor.fetchone()

            if not row or row[0] == 0:
                return {"total_reports": 0}

            stats = {
                "total_reports": row[0] or 0,
                "oldest_date": row[1].isoformat() if row[1] else None,
                "newest_date": row[2].isoformat() if row[2] else None,
                "total_trades": row[3] or 0,
                "total_wins": row[4] or 0,
                "total_losses": row[5] or 0,
                "total_pnl": float(row[6]) if row[6] else 0,
                "avg_daily_pnl": float(row[7]) if row[7] else 0,
                "best_day": None,
                "worst_day": None
            }

            # Get best day
            cursor.execute(f"""
                SELECT report_date, total_pnl
                FROM {table_name}
                WHERE total_pnl IS NOT NULL
                ORDER BY total_pnl DESC
                LIMIT 1
            """)
            best_row = cursor.fetchone()
            if best_row:
                stats["best_day"] = {
                    "date": best_row[0].isoformat() if best_row[0] else None,
                    "pnl": float(best_row[1]) if best_row[1] else 0
                }

            # Get worst day
            cursor.execute(f"""
                SELECT report_date, total_pnl
                FROM {table_name}
                WHERE total_pnl IS NOT NULL
                ORDER BY total_pnl ASC
                LIMIT 1
            """)
            worst_row = cursor.fetchone()
            if worst_row:
                stats["worst_day"] = {
                    "date": worst_row[0].isoformat() if worst_row[0] else None,
                    "pnl": float(worst_row[1]) if worst_row[1] else 0
                }

            return stats

    except Exception as e:
        logger.error(f"Error getting archive stats: {e}")
        return {"total_reports": 0, "error": str(e)}


def purge_old_reports(days_to_keep: int = 5 * 365) -> Dict[str, int]:
    """
    Delete reports older than specified days (default 5 years).

    Args:
        days_to_keep: Number of days of reports to keep

    Returns:
        Dict mapping bot name to number of deleted reports
    """
    if not DB_AVAILABLE:
        return {}

    cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).date()
    results = {}

    try:
        with _db_connection() as conn:
            cursor = conn.cursor()

            for bot in VALID_BOTS:
                table_name = f"{bot}_daily_reports"
                cursor.execute(f"""
                    DELETE FROM {table_name}
                    WHERE report_date < %s
                """, (cutoff_date,))
                deleted = cursor.rowcount
                results[bot] = deleted
                if deleted > 0:
                    logger.info(f"Purged {deleted} old reports from {table_name}")

            return results

    except Exception as e:
        logger.error(f"Error purging old reports: {e}")
        return {}
