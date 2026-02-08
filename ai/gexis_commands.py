"""
GEXIS Commands - Extended command set for GEXIS.

New commands:
- /market-hours - Market hours and status
- /strategy-performance - Bot strategy comparison
- /suggestion - Proactive trade suggestions
- /risk - Portfolio risk summary
- /greeks - Portfolio Greeks summary
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo

from .gexis_cache import gexis_cache, GEXISCache
from .gexis_tracing import gexis_tracer, trace_command

logger = logging.getLogger(__name__)

# User name from personality
USER_NAME = "Optionist Prime"

# US Eastern timezone for market hours
ET = ZoneInfo("America/New_York")


# =============================================================================
# MARKET HOURS COMMAND
# =============================================================================

# Market holidays 2025 (NYSE)
MARKET_HOLIDAYS_2025 = [
    "2025-01-01",  # New Year's Day
    "2025-01-20",  # MLK Day
    "2025-02-17",  # Presidents Day
    "2025-04-18",  # Good Friday
    "2025-05-26",  # Memorial Day
    "2025-06-19",  # Juneteenth
    "2025-07-04",  # Independence Day
    "2025-09-01",  # Labor Day
    "2025-11-27",  # Thanksgiving
    "2025-12-25",  # Christmas
]

# Early close days (1:00 PM ET)
EARLY_CLOSE_DAYS_2025 = [
    "2025-07-03",  # Day before Independence Day
    "2025-11-28",  # Day after Thanksgiving
    "2025-12-24",  # Christmas Eve
]


def get_market_hours_info() -> Dict[str, Any]:
    """
    Get comprehensive market hours information.

    Returns:
        Dictionary with market status, hours, and upcoming events
    """
    now_et = datetime.now(ET)
    today_str = now_et.strftime("%Y-%m-%d")
    weekday = now_et.weekday()  # 0 = Monday, 6 = Sunday

    # Check if today is a holiday
    is_holiday = today_str in MARKET_HOLIDAYS_2025
    is_early_close = today_str in EARLY_CLOSE_DAYS_2025
    is_weekend = weekday >= 5

    # Regular market hours
    market_open_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close_time = now_et.replace(
        hour=13 if is_early_close else 16,
        minute=0, second=0, microsecond=0
    )

    # Extended hours
    premarket_open = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
    afterhours_close = now_et.replace(hour=20, minute=0, second=0, microsecond=0)

    # Determine current market status
    if is_holiday:
        status = "CLOSED_HOLIDAY"
        status_detail = "Market closed for holiday"
    elif is_weekend:
        status = "CLOSED_WEEKEND"
        status_detail = "Market closed for weekend"
    elif now_et < premarket_open:
        status = "CLOSED"
        status_detail = "Pre-market opens at 4:00 AM ET"
    elif now_et < market_open_time:
        status = "PREMARKET"
        status_detail = "Pre-market session active"
    elif now_et < market_close_time:
        status = "OPEN"
        status_detail = "Regular market hours" + (" (Early close today)" if is_early_close else "")
    elif now_et < afterhours_close:
        status = "AFTERHOURS"
        status_detail = "After-hours session active"
    else:
        status = "CLOSED"
        status_detail = "Market closed for the day"

    # Calculate time until next event
    if status == "CLOSED" and now_et < premarket_open:
        next_event = "Pre-market opens"
        time_until = premarket_open - now_et
    elif status == "PREMARKET":
        next_event = "Market opens"
        time_until = market_open_time - now_et
    elif status == "OPEN":
        next_event = "Market closes"
        time_until = market_close_time - now_et
    elif status == "AFTERHOURS":
        next_event = "After-hours ends"
        time_until = afterhours_close - now_et
    else:
        # Find next trading day
        next_day = now_et + timedelta(days=1)
        while next_day.weekday() >= 5 or next_day.strftime("%Y-%m-%d") in MARKET_HOLIDAYS_2025:
            next_day += timedelta(days=1)
        next_open = next_day.replace(hour=9, minute=30, second=0, microsecond=0)
        next_event = f"Market opens ({next_day.strftime('%A')})"
        time_until = next_open - now_et

    # Format time until
    hours, remainder = divmod(int(time_until.total_seconds()), 3600)
    minutes = remainder // 60

    if hours > 0:
        time_until_str = f"{hours}h {minutes}m"
    else:
        time_until_str = f"{minutes}m"

    return {
        "status": status,
        "status_detail": status_detail,
        "is_trading_day": not (is_holiday or is_weekend),
        "is_early_close": is_early_close,
        "current_time_et": now_et.strftime("%I:%M %p ET"),
        "market_open": "9:30 AM ET",
        "market_close": "1:00 PM ET" if is_early_close else "4:00 PM ET",
        "next_event": next_event,
        "time_until_next": time_until_str,
        "premarket_hours": "4:00 AM - 9:30 AM ET",
        "afterhours": "4:00 PM - 8:00 PM ET"
    }


@trace_command("market_hours")
def execute_market_hours_command() -> Dict[str, Any]:
    """
    Execute /market-hours command.

    Returns:
        Command result with market hours info
    """
    info = get_market_hours_info()

    # Build response text
    status_emoji = {
        "OPEN": "OPEN",
        "PREMARKET": "PRE-MARKET",
        "AFTERHOURS": "AFTER-HOURS",
        "CLOSED": "CLOSED",
        "CLOSED_HOLIDAY": "CLOSED (Holiday)",
        "CLOSED_WEEKEND": "CLOSED (Weekend)"
    }

    response = f"Market Hours Report, {USER_NAME}:\n\n"
    response += f"Status: {status_emoji.get(info['status'], info['status'])}\n"
    response += f"Current Time: {info['current_time_et']}\n\n"

    if info['is_trading_day']:
        response += f"Today's Hours:\n"
        response += f"  Regular: {info['market_open']} - {info['market_close']}\n"
        response += f"  Pre-market: {info['premarket_hours']}\n"
        response += f"  After-hours: {info['afterhours']}\n\n"

    response += f"Next: {info['next_event']} in {info['time_until_next']}"

    if info['is_early_close']:
        response += f"\n\nNote: Early close today at 1:00 PM ET"

    return {
        "success": True,
        "command": "/market-hours",
        "response": response,
        "data": info,
        "type": "market_hours"
    }


# =============================================================================
# STRATEGY PERFORMANCE COMMAND
# =============================================================================

def get_strategy_performance(days: int = 30) -> Dict[str, Any]:
    """
    Get performance comparison across all trading bots/strategies.

    Args:
        days: Number of days to analyze

    Returns:
        Dictionary with performance data per strategy
    """
    try:
        from backend.utils.db import get_connection
    except ImportError:
        logger.error("Database connection unavailable - cannot fetch strategy performance")
        return {"error": "Database connection unavailable"}

    conn = get_connection()
    try:
        c = conn.cursor()

        strategies = {}
        for bot in ["FORTRESS", "SOLOMON", "PEGASUS", "PHOENIX"]:
            try:
                c.execute("""
                    SELECT
                        COUNT(*) as trades,
                        COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
                        COALESCE(SUM(realized_pnl), 0) as total_pnl,
                        COALESCE(AVG(realized_pnl), 0) as avg_pnl,
                        COALESCE(MAX(realized_pnl), 0) as best_trade,
                        COALESCE(MIN(realized_pnl), 0) as worst_trade,
                        COALESCE(AVG(EXTRACT(EPOCH FROM (closed_at - opened_at)) / 60), 0) as avg_hold_minutes
                    FROM autonomous_positions
                    WHERE bot_name = %s
                        AND status = 'closed'
                        AND COALESCE(closed_at, created_at) >= NOW() - INTERVAL '%s days'
                """, (bot, days))

                row = c.fetchone()
                if row and row[0] > 0:
                    strategies[bot] = {
                        "trades": row[0],
                        "win_rate": round(row[1] / row[0] * 100, 1) if row[0] > 0 else 0,
                        "total_pnl": round(float(row[2]), 2),
                        "avg_pnl": round(float(row[3]), 2),
                        "best_trade": round(float(row[4]), 2),
                        "worst_trade": round(float(row[5]), 2),
                        "avg_hold_minutes": round(float(row[6]), 0)
                    }
                else:
                    strategies[bot] = {"trades": 0, "win_rate": 0, "total_pnl": 0}
            except Exception as e:
                logger.error(f"Error fetching {bot} performance: {e}")
                strategies[bot] = {"trades": 0, "win_rate": 0, "total_pnl": 0, "error": str(e)}

        return strategies
    finally:
        conn.close()


@trace_command("strategy_performance")
def execute_strategy_performance_command(days: int = 30) -> Dict[str, Any]:
    """
    Execute /strategy-performance command.

    Args:
        days: Number of days to analyze

    Returns:
        Command result with strategy comparison
    """
    # Check cache first
    cache_key = f"strategy_perf:{days}"
    cached = gexis_cache.get(cache_key)
    if cached:
        return cached

    performance = get_strategy_performance(days)

    # Build response text
    response = f"Strategy Performance ({days} Days), {USER_NAME}:\n\n"

    # Sort by total P&L
    sorted_bots = sorted(
        performance.items(),
        key=lambda x: x[1].get("total_pnl", 0),
        reverse=True
    )

    for i, (bot, stats) in enumerate(sorted_bots, 1):
        if stats.get("trades", 0) == 0:
            response += f"{i}. {bot}: No trades in period\n"
            continue

        pnl = stats.get("total_pnl", 0)
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

        response += f"{i}. {bot}:\n"
        response += f"   Trades: {stats['trades']} | Win Rate: {stats['win_rate']}%\n"
        response += f"   Total P&L: {pnl_str} | Avg: ${stats.get('avg_pnl', 0):.2f}\n"
        response += f"   Best: ${stats.get('best_trade', 0):.2f} | Worst: ${stats.get('worst_trade', 0):.2f}\n"
        if stats.get('avg_hold_minutes'):
            response += f"   Avg Hold: {int(stats['avg_hold_minutes'])} min\n"
        response += "\n"

    # Summary
    total_pnl = sum(s.get("total_pnl", 0) for s in performance.values())
    total_trades = sum(s.get("trades", 0) for s in performance.values())
    total_pnl_str = f"+${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"

    response += f"Combined: {total_trades} trades, {total_pnl_str} P&L"

    result = {
        "success": True,
        "command": "/strategy-performance",
        "response": response,
        "data": performance,
        "period_days": days,
        "type": "strategy_performance"
    }

    # Cache for 5 minutes
    gexis_cache.set(cache_key, result, ttl=300)

    return result


# =============================================================================
# SUGGESTION COMMAND
# =============================================================================

def generate_trade_suggestion() -> Dict[str, Any]:
    """
    Generate proactive trade suggestions based on current market conditions.

    Returns:
        Dictionary with trade suggestions
    """
    from .gexis_tools import fetch_ares_market_data, get_upcoming_events, is_market_open

    suggestions = []
    warnings = []

    # Get market data
    try:
        market = fetch_ares_market_data()
    except Exception:
        market = {}

    # Get upcoming events
    try:
        events = get_upcoming_events(3)
    except Exception:
        events = []

    # Check if market is open
    market_open = is_market_open()

    # Analyze VIX
    vix = market.get("vix", 0) if market else 0
    if vix:
        if vix < 15:
            suggestions.append({
                "type": "opportunity",
                "title": "Low VIX Environment",
                "detail": f"VIX at {vix:.1f} - Premium is compressed. Consider wider wings on Iron Condors or wait for better premium.",
                "confidence": "medium"
            })
        elif vix > 25:
            suggestions.append({
                "type": "caution",
                "title": "Elevated VIX",
                "detail": f"VIX at {vix:.1f} - High volatility environment. Reduce position sizes and tighten stops.",
                "confidence": "high"
            })
            warnings.append("Elevated volatility - trade cautiously")
        else:
            suggestions.append({
                "type": "opportunity",
                "title": "Normal VIX Environment",
                "detail": f"VIX at {vix:.1f} - Favorable conditions for premium selling strategies.",
                "confidence": "high"
            })

    # Check GEX
    spy = market.get("spy", {}) if market else {}
    net_gex = spy.get("net_gex")
    if net_gex:
        if net_gex > 0:
            suggestions.append({
                "type": "insight",
                "title": "Positive GEX",
                "detail": "Dealer gamma is positive - expect mean-reverting, range-bound action. Iron Condors favorable.",
                "confidence": "high"
            })
        else:
            suggestions.append({
                "type": "caution",
                "title": "Negative GEX",
                "detail": "Dealer gamma is negative - expect amplified moves. Consider directional plays or sit out.",
                "confidence": "high"
            })
            warnings.append("Negative GEX - increased volatility risk")

    # Check for high-impact events
    high_impact_soon = [e for e in events if e["impact"] == "HIGH" and e["days_until"] <= 1]
    if high_impact_soon:
        event = high_impact_soon[0]
        warnings.append(f"High-impact event: {event['name']} on {event['date']}")
        suggestions.append({
            "type": "caution",
            "title": f"Upcoming: {event['name']}",
            "detail": f"{event.get('trading_advice', 'Consider reducing exposure before the event.')}",
            "confidence": "high"
        })

    # Market hours suggestion
    if not market_open:
        suggestions.append({
            "type": "info",
            "title": "Market Closed",
            "detail": "Good time to review positions, plan tomorrow's trades, and analyze recent performance.",
            "confidence": "high"
        })

    # Default suggestion if none generated
    if not suggestions:
        suggestions.append({
            "type": "neutral",
            "title": "Standard Conditions",
            "detail": "No significant opportunities or risks detected. Proceed with standard trading plan.",
            "confidence": "medium"
        })

    return {
        "suggestions": suggestions,
        "warnings": warnings,
        "market_open": market_open,
        "vix": vix,
        "events_upcoming": len(events)
    }


@trace_command("suggestion")
def execute_suggestion_command() -> Dict[str, Any]:
    """
    Execute /suggestion command.

    Returns:
        Command result with trade suggestions
    """
    # Check cache (short TTL since conditions change)
    cached = gexis_cache.get("suggestion:current")
    if cached:
        return cached

    data = generate_trade_suggestion()

    # Build response text
    response = f"Trade Suggestions, {USER_NAME}:\n\n"

    # Add warnings first
    if data["warnings"]:
        response += "Warnings:\n"
        for warning in data["warnings"]:
            response += f"  - {warning}\n"
        response += "\n"

    # Add suggestions
    for i, sugg in enumerate(data["suggestions"], 1):
        type_prefix = {
            "opportunity": "[Opportunity]",
            "caution": "[Caution]",
            "insight": "[Insight]",
            "info": "[Info]",
            "neutral": "[Status]"
        }.get(sugg["type"], "")

        response += f"{i}. {type_prefix} {sugg['title']}\n"
        response += f"   {sugg['detail']}\n"
        response += f"   Confidence: {sugg['confidence'].upper()}\n\n"

    # Footer
    if data["market_open"]:
        response += "Market is currently open. Good luck with your trades!"
    else:
        response += "Market is currently closed. Use this time to prepare."

    result = {
        "success": True,
        "command": "/suggestion",
        "response": response,
        "data": data,
        "type": "suggestion"
    }

    # Cache for 2 minutes
    gexis_cache.set("suggestion:current", result, ttl=120)

    return result


# =============================================================================
# RISK SUMMARY COMMAND
# =============================================================================

def get_portfolio_risk() -> Dict[str, Any]:
    """
    Get portfolio risk summary.

    Returns:
        Dictionary with risk metrics
    """
    try:
        from backend.utils.db import get_connection
    except ImportError:
        logger.error("Database connection unavailable - cannot fetch portfolio risk")
        return {"error": "Database connection unavailable"}

    conn = get_connection()
    try:
        c = conn.cursor()

        # Get open positions summary
        c.execute("""
            SELECT
                COUNT(*) as position_count,
                COALESCE(SUM(contracts * entry_price * 100), 0) as total_exposure,
                COALESCE(SUM(CASE WHEN unrealized_pnl < 0 THEN unrealized_pnl ELSE 0 END), 0) as current_loss,
                COALESCE(SUM(unrealized_pnl), 0) as total_unrealized
            FROM autonomous_positions
            WHERE status = 'open'
        """)
        row = c.fetchone()

        # Get concentration by symbol
        c.execute("""
            SELECT symbol, COUNT(*) as count
            FROM autonomous_positions
            WHERE status = 'open'
            GROUP BY symbol
            ORDER BY count DESC
            LIMIT 5
        """)
        concentration_rows = c.fetchall()

        total_positions = row[0] if row else 0
        concentration = {}
        if concentration_rows and total_positions > 0:
            for sym_row in concentration_rows:
                concentration[sym_row[0]] = round(sym_row[1] / total_positions * 100, 1)

        return {
            "total_positions": total_positions,
            "total_exposure": round(float(row[1]), 2) if row else 0,
            "current_loss": round(float(row[2]), 2) if row else 0,
            "total_unrealized": round(float(row[3]), 2) if row else 0,
            "concentration": concentration
        }

    except Exception as e:
        logger.error(f"Error fetching portfolio risk: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


@trace_command("risk")
def execute_risk_command() -> Dict[str, Any]:
    """
    Execute /risk command.

    Returns:
        Command result with portfolio risk summary
    """
    risk = get_portfolio_risk()

    if "error" in risk:
        return {
            "success": False,
            "command": "/risk",
            "error": risk["error"],
            "type": "risk"
        }

    response = f"Portfolio Risk Summary, {USER_NAME}:\n\n"
    response += f"Open Positions: {risk['total_positions']}\n"
    response += f"Total Exposure: ${risk['total_exposure']:,.2f}\n"

    unrealized = risk.get('total_unrealized', 0)
    unrealized_str = f"+${unrealized:.2f}" if unrealized >= 0 else f"-${abs(unrealized):.2f}"
    response += f"Unrealized P&L: {unrealized_str}\n"

    if risk.get("current_loss", 0) < 0:
        response += f"Positions at Loss: ${abs(risk['current_loss']):.2f}\n"

    if risk.get("concentration"):
        response += "\nConcentration:\n"
        for symbol, pct in risk["concentration"].items():
            response += f"  {symbol}: {pct}%\n"

    return {
        "success": True,
        "command": "/risk",
        "response": response,
        "data": risk,
        "type": "risk"
    }


# =============================================================================
# COMMAND REGISTRY
# =============================================================================

EXTENDED_COMMANDS = {
    "/market-hours": {
        "description": "Market hours and current status",
        "handler": execute_market_hours_command
    },
    "/strategy-performance": {
        "description": "Compare bot strategy performance",
        "handler": execute_strategy_performance_command
    },
    "/suggestion": {
        "description": "Get proactive trade suggestions",
        "handler": execute_suggestion_command
    },
    "/risk": {
        "description": "Portfolio risk summary",
        "handler": execute_risk_command
    }
}


def execute_extended_command(command: str, args: List[str] = None) -> Optional[Dict[str, Any]]:
    """
    Execute an extended command if it exists.

    Args:
        command: Command name (with /)
        args: Optional command arguments

    Returns:
        Command result or None if command not found
    """
    args = args or []

    if command not in EXTENDED_COMMANDS:
        return None

    handler = EXTENDED_COMMANDS[command]["handler"]

    # Handle commands with arguments
    if command == "/strategy-performance" and args:
        try:
            days = int(args[0])
            return handler(days=days)
        except ValueError:
            pass

    return handler()
