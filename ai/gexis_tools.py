"""
GEXIS Agentic Tools - Actions GEXIS can execute

This module provides tools that GEXIS can use to:
- Query databases
- Fetch real-time market data
- Control trading bots
- Generate analysis
- Check economic calendar
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# ECONOMIC CALENDAR - Major Market Moving Events
# =============================================================================

ECONOMIC_EVENTS = {
    "FOMC": {
        "name": "Federal Reserve Interest Rate Decision",
        "impact": "HIGH",
        "description": "Federal Open Market Committee announces interest rate decisions and monetary policy. Can cause major market volatility.",
        "typical_dates": "8 times per year, roughly every 6 weeks",
        "trading_advice": "Reduce position size before announcement. Wait 30-60 min after for volatility to settle."
    },
    "CPI": {
        "name": "Consumer Price Index",
        "impact": "HIGH",
        "description": "Key inflation measure. Higher than expected = hawkish Fed = bearish. Lower = bullish.",
        "typical_dates": "Monthly, usually 2nd week",
        "trading_advice": "Major volatility event. Consider reducing Iron Condor wings or sitting out."
    },
    "PPI": {
        "name": "Producer Price Index",
        "impact": "MEDIUM-HIGH",
        "description": "Wholesale inflation measure. Leading indicator for CPI.",
        "typical_dates": "Monthly, usually day before or after CPI",
        "trading_advice": "Often causes sympathy moves with CPI expectations."
    },
    "NFP": {
        "name": "Non-Farm Payrolls (Jobs Report)",
        "impact": "HIGH",
        "description": "Employment data release. Strong jobs = hawkish Fed. Weak = dovish.",
        "typical_dates": "First Friday of each month, 8:30 AM ET",
        "trading_advice": "Major volatility. Avoid 0DTE trades on NFP Friday mornings."
    },
    "GDP": {
        "name": "Gross Domestic Product",
        "impact": "MEDIUM-HIGH",
        "description": "Quarterly economic growth measure.",
        "typical_dates": "Quarterly (advance, preliminary, final readings)",
        "trading_advice": "Less volatile than CPI/NFP but can move markets on surprises."
    },
    "PCE": {
        "name": "Personal Consumption Expenditures",
        "impact": "HIGH",
        "description": "Fed's preferred inflation measure. Core PCE is key.",
        "typical_dates": "Monthly, last week of month",
        "trading_advice": "Important for Fed policy expectations. Trade cautiously."
    },
    "OPEX": {
        "name": "Monthly Options Expiration",
        "impact": "MEDIUM",
        "description": "Third Friday of each month. Increased volume and gamma effects.",
        "typical_dates": "Third Friday monthly",
        "trading_advice": "Gamma exposure intensifies. Good for premium sellers if positioned correctly."
    },
    "QUAD_WITCH": {
        "name": "Quadruple Witching",
        "impact": "HIGH",
        "description": "Quarterly expiration of stock options, index options, index futures, and single stock futures.",
        "typical_dates": "Third Friday of March, June, September, December",
        "trading_advice": "Extreme volume and volatility. Pin risk elevated. Consider closing positions early."
    },
    "VIX_EXP": {
        "name": "VIX Expiration",
        "impact": "MEDIUM",
        "description": "VIX options and futures expiration. Usually Wednesday before third Friday.",
        "typical_dates": "Wednesday before monthly OPEX",
        "trading_advice": "Can cause VIX mean reversion. Watch for unusual VIX moves."
    },
    "EARNINGS": {
        "name": "Major Earnings (AAPL, MSFT, NVDA, etc.)",
        "impact": "HIGH for individual stocks",
        "description": "Quarterly earnings from mega-cap tech can move SPX.",
        "typical_dates": "Varies by company, check earnings calendar",
        "trading_advice": "Mega-cap earnings can move SPX 1-2%. Adjust Iron Condor strikes accordingly."
    }
}

# 2025 Key Economic Dates (Update regularly)
CALENDAR_2025 = [
    {"date": "2025-01-10", "event": "NFP", "time": "8:30 AM ET"},
    {"date": "2025-01-14", "event": "PPI", "time": "8:30 AM ET"},
    {"date": "2025-01-15", "event": "CPI", "time": "8:30 AM ET"},
    {"date": "2025-01-17", "event": "OPEX", "time": "All day"},
    {"date": "2025-01-29", "event": "FOMC", "time": "2:00 PM ET"},
    {"date": "2025-01-31", "event": "PCE", "time": "8:30 AM ET"},
    {"date": "2025-02-07", "event": "NFP", "time": "8:30 AM ET"},
    {"date": "2025-02-12", "event": "CPI", "time": "8:30 AM ET"},
    {"date": "2025-02-13", "event": "PPI", "time": "8:30 AM ET"},
    {"date": "2025-02-21", "event": "OPEX", "time": "All day"},
    {"date": "2025-03-07", "event": "NFP", "time": "8:30 AM ET"},
    {"date": "2025-03-12", "event": "CPI", "time": "8:30 AM ET"},
    {"date": "2025-03-13", "event": "PPI", "time": "8:30 AM ET"},
    {"date": "2025-03-19", "event": "FOMC", "time": "2:00 PM ET"},
    {"date": "2025-03-21", "event": "QUAD_WITCH", "time": "All day"},
    {"date": "2025-03-28", "event": "PCE", "time": "8:30 AM ET"},
    # Continue adding dates...
]


def get_upcoming_events(days_ahead: int = 7) -> List[Dict]:
    """Get economic events in the next N days"""
    today = datetime.now().date()
    upcoming = []

    for event in CALENDAR_2025:
        event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        days_until = (event_date - today).days

        if 0 <= days_until <= days_ahead:
            event_info = ECONOMIC_EVENTS.get(event["event"], {})
            upcoming.append({
                "date": event["date"],
                "days_until": days_until,
                "event": event["event"],
                "name": event_info.get("name", event["event"]),
                "time": event.get("time", "TBD"),
                "impact": event_info.get("impact", "MEDIUM"),
                "trading_advice": event_info.get("trading_advice", ""),
            })

    return sorted(upcoming, key=lambda x: x["days_until"])


def get_event_info(event_type: str) -> Dict:
    """Get detailed info about a specific event type"""
    return ECONOMIC_EVENTS.get(event_type.upper(), {
        "name": event_type,
        "impact": "UNKNOWN",
        "description": "No information available for this event type."
    })


# =============================================================================
# DATABASE TOOLS
# =============================================================================

def query_database(query: str, params: tuple = None) -> List[Dict]:
    """
    Execute a read-only database query

    GEXIS can use this to fetch:
    - Position data
    - Historical trades
    - Performance metrics
    - Configuration values
    """
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Security: Only allow SELECT queries
        if not query.strip().upper().startswith("SELECT"):
            return {"error": "Only SELECT queries allowed"}

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.commit()

        results = []
        for row in rows:
            results.append(dict(zip(columns, row)))

        conn.close()
        return results

    except Exception as e:
        logger.error(f"Database query error: {e}")
        return {"error": str(e)}


def get_ares_positions() -> Dict:
    """Get all ARES positions with P&L"""
    try:
        results = query_database("""
            SELECT position_id, open_date, expiration, status,
                   put_spread, call_spread, contracts, total_credit,
                   realized_pnl, close_date
            FROM ares_positions
            ORDER BY open_date DESC
            LIMIT 20
        """)

        if isinstance(results, dict) and "error" in results:
            return results

        open_positions = [p for p in results if p.get("status") == "open"]
        closed_positions = [p for p in results if p.get("status") in ("closed", "expired")]

        total_pnl = sum(p.get("realized_pnl", 0) or 0 for p in closed_positions)

        return {
            "open_count": len(open_positions),
            "closed_count": len(closed_positions),
            "total_pnl": total_pnl,
            "open_positions": open_positions,
            "recent_closed": closed_positions[:5]
        }
    except Exception as e:
        return {"error": str(e)}


def get_probability_weights() -> Dict:
    """Get current probability system weights"""
    try:
        results = query_database("""
            SELECT weight_name, gex_wall_strength, volatility_impact,
                   psychology_signal, mm_positioning, historical_pattern,
                   calibration_count, active, timestamp
            FROM probability_weights
            WHERE active = TRUE
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        if results and not isinstance(results, dict):
            return results[0] if results else {"message": "No active weights found"}
        return results
    except Exception as e:
        return {"error": str(e)}


def get_trading_stats(days: int = 30) -> Dict:
    """Get trading statistics for the last N days"""
    try:
        results = query_database(f"""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winners,
                SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losers,
                SUM(realized_pnl) as total_pnl,
                AVG(realized_pnl) as avg_pnl,
                MAX(realized_pnl) as best_trade,
                MIN(realized_pnl) as worst_trade
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            AND close_date >= NOW() - INTERVAL '{days} days'
        """)

        if results and not isinstance(results, dict):
            stats = results[0]
            total = stats.get("total_trades", 0) or 0
            winners = stats.get("winners", 0) or 0
            stats["win_rate"] = (winners / total * 100) if total > 0 else 0
            return stats
        return results
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# MARKET DATA TOOLS
# =============================================================================

def fetch_market_data(symbol: str = "SPY") -> Dict:
    """Fetch current market data for a symbol"""
    try:
        api_base = os.getenv("API_URL", "https://alphagex-api.onrender.com")
        response = requests.get(f"{api_base}/api/gex/{symbol}", timeout=10)

        if response.status_code == 200:
            return response.json().get("data", {})
        return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def fetch_ares_market_data() -> Dict:
    """Fetch ARES-specific market data (SPX, SPY, VIX, expected moves)"""
    try:
        api_base = os.getenv("API_URL", "https://alphagex-api.onrender.com")
        response = requests.get(f"{api_base}/api/ares/market-data", timeout=10)

        if response.status_code == 200:
            return response.json().get("data", {})
        return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def fetch_vix_data() -> Dict:
    """Fetch current VIX data and term structure"""
    try:
        api_base = os.getenv("API_URL", "https://alphagex-api.onrender.com")
        response = requests.get(f"{api_base}/api/vix/current", timeout=10)

        if response.status_code == 200:
            return response.json().get("data", {})
        return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# BOT CONTROL TOOLS
# =============================================================================

def get_bot_status(bot_name: str = "ares") -> Dict:
    """Get status of a trading bot"""
    try:
        api_base = os.getenv("API_URL", "https://alphagex-api.onrender.com")
        response = requests.get(f"{api_base}/api/ares/status", timeout=10)

        if response.status_code == 200:
            return response.json().get("data", {})
        return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def get_tradier_status() -> Dict:
    """Get Tradier connection status"""
    try:
        api_base = os.getenv("API_URL", "https://alphagex-api.onrender.com")
        response = requests.get(f"{api_base}/api/ares/tradier-status", timeout=10)

        if response.status_code == 200:
            return response.json().get("data", {})
        return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# ANALYSIS TOOLS
# =============================================================================

def generate_market_briefing() -> str:
    """Generate a morning market briefing"""
    try:
        # Fetch all relevant data
        market_data = fetch_ares_market_data()
        vix_data = fetch_vix_data()
        ares_status = get_bot_status("ares")
        upcoming_events = get_upcoming_events(7)

        # Build briefing
        briefing = []

        # Market data
        if market_data and "error" not in market_data:
            spx = market_data.get("spx", {})
            spy = market_data.get("spy", {})
            vix = market_data.get("vix", 0)

            briefing.append("MARKET DATA:")
            briefing.append(f"  SPX: ${spx.get('price', 'N/A'):,.2f} (Expected Move: ±${spx.get('expected_move', 0):.0f})")
            briefing.append(f"  SPY: ${spy.get('price', 'N/A'):.2f} (Expected Move: ±${spy.get('expected_move', 0):.2f})")
            briefing.append(f"  VIX: {vix:.2f}")

        # VIX analysis
        if vix_data and "error" not in vix_data:
            structure = vix_data.get("structure_type", "unknown")
            regime = vix_data.get("vol_regime", "unknown")
            briefing.append(f"\nVOLATILITY:")
            briefing.append(f"  Term Structure: {structure.upper()}")
            briefing.append(f"  Vol Regime: {regime.upper()}")

        # ARES status
        if ares_status and "error" not in ares_status:
            briefing.append(f"\nARES STATUS:")
            briefing.append(f"  Mode: {ares_status.get('mode', 'unknown')}")
            briefing.append(f"  Capital: ${ares_status.get('capital', 0):,.0f}")
            briefing.append(f"  P&L: ${ares_status.get('total_pnl', 0):,.0f}")
            briefing.append(f"  Open Positions: {ares_status.get('open_positions', 0)}")

        # Upcoming events
        if upcoming_events:
            briefing.append(f"\nUPCOMING EVENTS (Next 7 Days):")
            for event in upcoming_events[:5]:
                days = event["days_until"]
                day_str = "TODAY" if days == 0 else f"in {days} days"
                briefing.append(f"  {event['name']} - {event['date']} ({day_str}) - {event['impact']} IMPACT")

        return "\n".join(briefing)

    except Exception as e:
        return f"Error generating briefing: {e}"


def analyze_trade_opportunity(symbol: str = "SPY") -> Dict:
    """Analyze current trade opportunity"""
    try:
        gex_data = fetch_market_data(symbol)
        vix_data = fetch_vix_data()

        analysis = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "recommendation": "NEUTRAL",
            "confidence": 0,
            "reasoning": []
        }

        if gex_data and "error" not in gex_data:
            net_gex = gex_data.get("net_gex", 0)
            regime = gex_data.get("regime", "NEUTRAL")
            mm_state = gex_data.get("mm_state", "NEUTRAL")

            analysis["gex_data"] = {
                "net_gex": net_gex,
                "regime": regime,
                "mm_state": mm_state,
                "flip_point": gex_data.get("flip_point"),
                "call_wall": gex_data.get("call_wall"),
                "put_wall": gex_data.get("put_wall")
            }

            # Simple analysis logic
            if mm_state == "DEFENDING":
                analysis["recommendation"] = "SELL_PREMIUM"
                analysis["confidence"] = 70
                analysis["reasoning"].append("Market makers defending - low volatility expected")
            elif mm_state == "SQUEEZING":
                analysis["recommendation"] = "BUY_DIRECTIONAL"
                analysis["confidence"] = 65
                analysis["reasoning"].append("Squeeze conditions detected - momentum expected")
            elif mm_state == "PANICKING":
                analysis["recommendation"] = "BUY_CALLS"
                analysis["confidence"] = 80
                analysis["reasoning"].append("MM panic - strong upside expected")

        if vix_data and "error" not in vix_data:
            vix_spot = vix_data.get("vix_spot", 0)
            if vix_spot > 25:
                analysis["reasoning"].append(f"High VIX ({vix_spot:.1f}) - elevated premium available")
            elif vix_spot < 15:
                analysis["reasoning"].append(f"Low VIX ({vix_spot:.1f}) - reduced premium, consider smaller size")

        return analysis

    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# TOOL REGISTRY - All tools GEXIS can use
# =============================================================================

GEXIS_TOOLS = {
    # Query tools
    "get_positions": {
        "function": get_ares_positions,
        "description": "Get all ARES positions with P&L summary",
        "category": "query"
    },
    "get_weights": {
        "function": get_probability_weights,
        "description": "Get current probability system weights",
        "category": "query"
    },
    "get_stats": {
        "function": get_trading_stats,
        "description": "Get trading statistics for last 30 days",
        "category": "query"
    },

    # Market data tools
    "get_gex": {
        "function": fetch_market_data,
        "description": "Fetch GEX data for a symbol",
        "category": "market"
    },
    "get_market": {
        "function": fetch_ares_market_data,
        "description": "Get SPX/SPY/VIX market data with expected moves",
        "category": "market"
    },
    "get_vix": {
        "function": fetch_vix_data,
        "description": "Get VIX data and term structure",
        "category": "market"
    },

    # Bot tools
    "bot_status": {
        "function": get_bot_status,
        "description": "Get trading bot status",
        "category": "bot"
    },
    "tradier_status": {
        "function": get_tradier_status,
        "description": "Get Tradier connection status",
        "category": "bot"
    },

    # Analysis tools
    "briefing": {
        "function": generate_market_briefing,
        "description": "Generate morning market briefing",
        "category": "analysis"
    },
    "analyze": {
        "function": analyze_trade_opportunity,
        "description": "Analyze current trade opportunity",
        "category": "analysis"
    },

    # Calendar tools
    "upcoming_events": {
        "function": get_upcoming_events,
        "description": "Get upcoming economic events",
        "category": "calendar"
    },
    "event_info": {
        "function": get_event_info,
        "description": "Get info about a specific event type",
        "category": "calendar"
    }
}


def execute_tool(tool_name: str, **kwargs) -> Any:
    """Execute a GEXIS tool by name"""
    tool = GEXIS_TOOLS.get(tool_name)
    if not tool:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return tool["function"](**kwargs)
    except Exception as e:
        return {"error": f"Tool execution failed: {e}"}


def list_available_tools() -> List[Dict]:
    """List all available GEXIS tools"""
    return [
        {
            "name": name,
            "description": info["description"],
            "category": info["category"]
        }
        for name, info in GEXIS_TOOLS.items()
    ]
