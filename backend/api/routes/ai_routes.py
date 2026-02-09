"""
AI Copilot API routes - Claude AI integration for market analysis and trade advice.

Powered by COUNSELOR (Gamma Exposure eXpert Intelligence System)
"""

import os
import re
import json
import uuid
import base64
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Central Time zone for all AlphaGEX operations
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio

from backend.api.dependencies import api_client, claude_ai, get_connection

# Import COUNSELOR personality system
try:
    from ai.counselor_personality import (
        build_counselor_conversation_prompt,
        build_counselor_system_prompt,
        get_counselor_welcome_message,
        get_counselor_error_message,
        USER_NAME,
        COUNSELOR_NAME
    )
    COUNSELOR_AVAILABLE = True
except ImportError:
    COUNSELOR_AVAILABLE = False
    USER_NAME = "Optionist Prime"
    COUNSELOR_NAME = "COUNSELOR"

# Import COUNSELOR agentic tools
try:
    from ai.counselor_tools import (
        COUNSELOR_TOOLS,
        execute_tool,
        get_upcoming_events,
        get_counselor_briefing,
        get_system_status,
        request_bot_action,
        confirm_bot_action,
        PENDING_CONFIRMATIONS,
        ECONOMIC_EVENTS
    )
    COUNSELOR_TOOLS_AVAILABLE = True
except ImportError:
    COUNSELOR_TOOLS_AVAILABLE = False
    COUNSELOR_TOOLS = {}
    PENDING_CONFIRMATIONS = {}

# Import comprehensive knowledge
try:
    from ai.counselor_knowledge import COUNSELOR_COMMANDS
    COUNSELOR_KNOWLEDGE_AVAILABLE = True
except ImportError:
    COUNSELOR_KNOWLEDGE_AVAILABLE = False
    COUNSELOR_COMMANDS = ""

# Import Extended Thinking for complex analysis
try:
    from ai.counselor_extended_thinking import (
        analyze_with_extended_thinking,
        analyze_strike_selection,
        evaluate_trade_setup,
        ThinkingResult
    )
    EXTENDED_THINKING_AVAILABLE = True
except ImportError:
    EXTENDED_THINKING_AVAILABLE = False
    analyze_with_extended_thinking = None

# Import Learning Memory for self-improvement
try:
    from ai.counselor_learning_memory import (
        CounselorLearningMemory,
        get_learning_memory,
        record_prediction as lm_record_prediction,
        record_outcome as lm_record_outcome,
        get_accuracy_statement as lm_get_accuracy_statement
    )
    LEARNING_MEMORY_AVAILABLE = True
except ImportError:
    LEARNING_MEMORY_AVAILABLE = False
    get_learning_memory = None

router = APIRouter(prefix="/api/ai", tags=["AI Copilot"])

# Keywords that trigger Extended Thinking (complex queries)
COMPLEX_QUERY_KEYWORDS = {
    'why', 'analyze', 'explain', 'compare', 'evaluate', 'assess',
    'strike selection', 'optimal', 'best strike', 'trade setup',
    'risk assessment', 'should i', 'recommend', 'probability',
    'deep analysis', 'think through', 'reasoning'
}

def requires_extended_thinking(query: str) -> bool:
    """Detect if query needs extended thinking (complex reasoning)."""
    query_lower = query.lower()
    # Check for complex query patterns
    for keyword in COMPLEX_QUERY_KEYWORDS:
        if keyword in query_lower:
            return True
    # Long queries with questions often need deep reasoning
    if len(query) > 200 and '?' in query:
        return True
    return False

# Known stock symbols for extraction from queries
KNOWN_SYMBOLS = {
    'SPY', 'QQQ', 'IWM', 'DIA', 'SPX', 'NDX', 'VIX', 'UVXY', 'SQQQ', 'TQQQ',
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'NFLX',
    'JPM', 'BAC', 'GS', 'MS', 'WFC', 'C', 'V', 'MA', 'PYPL', 'SQ',
    'XOM', 'CVX', 'COP', 'OXY', 'SLB', 'HAL', 'MPC', 'VLO', 'PSX',
    'JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'LLY', 'BMY', 'AMGN', 'GILD',
    'HD', 'LOW', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD', 'DIS',
    'BA', 'CAT', 'GE', 'MMM', 'HON', 'UPS', 'FDX', 'LMT', 'RTX',
    'CRM', 'ORCL', 'IBM', 'INTC', 'CSCO', 'ADBE', 'NOW', 'SNOW', 'PLTR',
    'BTC', 'ETH', 'COIN', 'MSTR', 'RIOT', 'MARA', 'BITF', 'HUT',
    'GME', 'AMC', 'BBBY', 'BB', 'NOK', 'SOFI', 'HOOD', 'RIVN', 'LCID'
}


def extract_symbol_from_query(query: str, default: str = 'SPY') -> str:
    """Extract stock symbol from user query, or return default."""
    query_upper = query.upper()

    # Look for $SYMBOL pattern first (e.g., "$AAPL")
    dollar_match = re.search(r'\$([A-Z]{1,5})', query_upper)
    if dollar_match and dollar_match.group(1) in KNOWN_SYMBOLS:
        return dollar_match.group(1)

    # Look for known symbols in the query (whole word match)
    for symbol in KNOWN_SYMBOLS:
        if re.search(rf'\b{symbol}\b', query_upper):
            return symbol

    return default


def detect_slash_command(query: str) -> tuple:
    """
    Detect if query is a COUNSELOR slash command.

    Returns:
        (command_name, args) if slash command detected
        (None, None) if no command
    """
    query = query.strip()
    if not query.startswith('/'):
        return None, None

    # Parse command and arguments
    parts = query.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else None

    # Map commands to tool names
    command_map = {
        '/help': 'help',
        '/status': 'status',
        '/briefing': 'briefing',
        '/calendar': 'calendar',
        '/gex': 'gex',
        '/vix': 'vix',
        '/market': 'market',
        '/regime': 'regime',
        '/positions': 'positions',
        '/pnl': 'pnl',
        '/history': 'history',
        '/analyze': 'analyze',
        '/risk': 'risk',
        '/weights': 'weights',
        '/accuracy': 'accuracy',
        '/patterns': 'patterns',
        # Bot control commands
        '/start': 'start_bot',
        '/stop': 'stop_bot',
        '/pause': 'pause_bot',
        '/confirm': 'confirm',
        '/yes': 'confirm',
        '/cancel': 'cancel',
    }

    return command_map.get(command), args


async def execute_counselor_command(command: str, args: str = None) -> dict:
    """
    Execute a COUNSELOR slash command using agentic tools.

    Returns:
        Dictionary with command result
    """
    if not COUNSELOR_TOOLS_AVAILABLE:
        return {"error": "COUNSELOR tools not available", "data": None}

    try:
        if command == 'help':
            # Return commands reference
            return {
                "type": "help",
                "data": COUNSELOR_COMMANDS if COUNSELOR_KNOWLEDGE_AVAILABLE else "Commands: /status, /briefing, /calendar, /gex, /vix, /positions, /pnl, /history, /analyze, /risk, /accuracy"
            }

        elif command == 'status':
            result = get_system_status()
            return {"type": "status", "data": result}

        elif command == 'briefing':
            result = get_counselor_briefing()
            return {"type": "briefing", "data": result}

        elif command == 'calendar':
            days = 7
            if args and args.isdigit():
                days = int(args)
            events = get_upcoming_events(days_ahead=days)
            return {"type": "calendar", "data": events}

        elif command == 'gex':
            symbol = args.upper() if args else 'SPY'
            # Use the existing API client to fetch GEX
            if api_client:
                gex_data = api_client.get_net_gamma(symbol)
                return {"type": "gex", "symbol": symbol, "data": gex_data}
            return {"type": "gex", "symbol": symbol, "data": None, "error": "API client not available"}

        elif command == 'vix':
            # Fetch VIX data - use $VIX.X for Tradier (correct symbol format)
            try:
                from data.tradier_data_fetcher import TradierDataFetcher
                from unified_config import APIConfig
                # Use explicit credentials like FORTRESS does
                api_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
                account_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID
                if not api_key or not account_id:
                    return {"type": "vix", "data": None, "error": "Tradier credentials not configured"}
                tradier = TradierDataFetcher(api_key=api_key, account_id=account_id, sandbox=True)
                vix_quote = tradier.get_quote('$VIX.X')
                return {"type": "vix", "data": vix_quote}
            except Exception as e:
                return {"type": "vix", "data": None, "error": str(e)}

        elif command == 'positions':
            # Fetch open positions from database
            try:
                conn = get_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT * FROM fortress_positions
                        WHERE status = 'open'
                        ORDER BY open_date DESC
                        LIMIT 10
                    """)
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                    rows = cursor.fetchall()
                    positions = [dict(zip(columns, row)) for row in rows] if rows else []
                    conn.commit()
                    return {"type": "positions", "data": positions}
            except Exception as e:
                return {"type": "positions", "data": [], "error": str(e)}

        elif command == 'pnl':
            # Fetch P&L summary
            try:
                conn = get_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT
                            COUNT(*) as total_trades,
                            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                            COALESCE(SUM(realized_pnl), 0) as total_pnl,
                            COALESCE(AVG(realized_pnl), 0) as avg_pnl
                        FROM fortress_positions
                        WHERE status IN ('closed', 'expired', 'partial_close')
                    """)
                    row = cursor.fetchone()
                    conn.commit()
                    if row:
                        total, wins, losses, total_pnl, avg_pnl = row
                        win_rate = (wins / total * 100) if total > 0 else 0
                        return {
                            "type": "pnl",
                            "data": {
                                "total_trades": total,
                                "wins": wins,
                                "losses": losses,
                                "win_rate": round(win_rate, 1),
                                "total_pnl": float(total_pnl),
                                "avg_pnl": float(avg_pnl)
                            }
                        }
            except Exception as e:
                return {"type": "pnl", "data": None, "error": str(e)}

        elif command == 'history':
            limit = 10
            if args and args.isdigit():
                limit = min(int(args), 50)  # Cap at 50
            try:
                conn = get_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute(f"""
                        SELECT * FROM fortress_positions
                        ORDER BY open_date DESC
                        LIMIT {limit}
                    """)
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                    rows = cursor.fetchall()
                    trades = [dict(zip(columns, row)) for row in rows] if rows else []
                    conn.commit()
                    return {"type": "history", "data": trades}
            except Exception as e:
                return {"type": "history", "data": [], "error": str(e)}

        elif command == 'accuracy':
            # Fetch AI prediction accuracy
            try:
                conn = get_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT
                            COUNT(*) as total_predictions,
                            SUM(CASE WHEN was_correct THEN 1 ELSE 0 END) as correct,
                            ROUND(AVG(CASE WHEN was_correct THEN 100.0 ELSE 0 END), 1) as accuracy_pct
                        FROM prophet_training_outcomes
                        WHERE created_at > NOW() - INTERVAL '30 days'
                    """)
                    row = cursor.fetchone()
                    conn.commit()
                    if row:
                        return {
                            "type": "accuracy",
                            "data": {
                                "total_predictions": row[0] or 0,
                                "correct": row[1] or 0,
                                "accuracy_pct": float(row[2] or 0),
                                "period": "30 days"
                            }
                        }
            except Exception as e:
                return {"type": "accuracy", "data": None, "error": str(e)}

        # Bot control commands
        elif command == 'start_bot':
            bot_name = args.lower() if args else 'fortress'
            result = request_bot_action('start', bot_name)
            return {"type": "bot_control", "action": "start", "bot": bot_name, "data": result}

        elif command == 'stop_bot':
            bot_name = args.lower() if args else 'fortress'
            result = request_bot_action('stop', bot_name)
            return {"type": "bot_control", "action": "stop", "bot": bot_name, "data": result}

        elif command == 'pause_bot':
            bot_name = args.lower() if args else 'fortress'
            result = request_bot_action('pause', bot_name)
            return {"type": "bot_control", "action": "pause", "bot": bot_name, "data": result}

        elif command == 'confirm':
            result = confirm_bot_action(confirmation='yes')
            return {"type": "confirmation", "data": result}

        elif command == 'cancel':
            # Clear any pending confirmation
            if PENDING_CONFIRMATIONS:
                PENDING_CONFIRMATIONS.clear()
            return {"type": "cancellation", "data": {"message": "Action cancelled."}}

        else:
            return {"type": "unknown", "error": f"Unknown command: {command}"}

    except Exception as e:
        return {"type": "error", "error": str(e)}


@router.post("/analyze-with-image")
async def ai_analyze_with_image(request: dict):
    """
    Generate AI market analysis with image support using Claude Vision

    Request body:
    {
        "symbol": "SPY",
        "query": "Analyze this chart",
        "image_data": "data:image/png;base64,..." or base64 string,
        "market_data": {...},  # Optional GEX data
    }
    """
    try:
        import anthropic

        query = request.get('query', 'Please analyze this image and provide trading insights.')
        image_data = request.get('image_data', '')
        market_data = request.get('market_data', {})

        if not image_data:
            raise HTTPException(status_code=400, detail="image_data is required")

        # Extract symbol from query - use provided symbol only if it's not default SPY
        provided_symbol = request.get('symbol', 'SPY').upper()
        if provided_symbol == 'SPY':
            symbol = extract_symbol_from_query(query, default='SPY')
        else:
            symbol = provided_symbol

        # Get API key
        api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="Claude API key not configured. Set CLAUDE_API_KEY environment variable."
            )

        # Parse the image data
        # Handle data URL format: data:image/png;base64,<data>
        if image_data.startswith('data:'):
            # Extract media type and base64 data
            header, base64_data = image_data.split(',', 1)
            media_type = header.split(':')[1].split(';')[0]
        else:
            # Assume it's raw base64, default to PNG
            base64_data = image_data
            media_type = 'image/png'

        # Fetch current market data if not provided
        if not market_data or not market_data.get('net_gex'):
            try:
                gex_data = api_client.get_net_gamma(symbol)
                if gex_data and not gex_data.get('error'):
                    market_data = {
                        'net_gex': gex_data.get('net_gex', 0),
                        'spot_price': gex_data.get('spot_price', 0),
                        'flip_point': gex_data.get('flip_point', 0),
                        'call_wall': gex_data.get('call_wall', 0),
                        'put_wall': gex_data.get('put_wall', 0),
                        'symbol': symbol
                    }
            except Exception:
                pass  # Continue without market data

        # Build COUNSELOR context for image analysis
        context = f"""You are COUNSELOR (Gamma Exposure eXpert Intelligence System), the AI assistant for AlphaGEX.
You address the user as "{USER_NAME}" and speak with the wit and professionalism of J.A.R.V.I.S.

Current Market Context for {symbol}:
- Spot Price: ${market_data.get('spot_price', 'N/A')}
- Net GEX: {market_data.get('net_gex', 'N/A')}
- Flip Point: ${market_data.get('flip_point', 'N/A')}
- Call Wall: ${market_data.get('call_wall', 'N/A')}
- Put Wall: ${market_data.get('put_wall', 'N/A')}

{USER_NAME} has uploaded an image (chart, option chain, screenshot, etc.) for analysis.
Please analyze the image thoroughly and provide:
1. What you observe in the image (chart pattern, option data, etc.)
2. Key insights and observations
3. Trading implications based on current market context
4. Specific actionable recommendations if applicable

Maintain COUNSELOR personality - professional, helpful, and address {USER_NAME} naturally."""

        # Call Claude API with vision
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",  # Always use latest Sonnet 4.5
            max_tokens=1500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"{context}\n\nUser's question: {query}"
                        }
                    ],
                }
            ],
        )

        # Extract the response
        ai_response = message.content[0].text if message.content else "No analysis generated."

        return {
            "success": True,
            "data": {
                "analysis": ai_response,
                "symbol": symbol,
                "query": query,
                "has_image": True
            },
            "timestamp": datetime.now().isoformat()
        }

    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def ai_analyze_market(request: dict):
    """
    Generate AI market analysis and trade recommendations

    Request body:
    {
        "symbol": "SPY",
        "query": "What's the best trade right now?",
        "market_data": {...},  # Optional GEX data
        "gamma_intel": {...}   # Optional gamma intelligence
    }

    Supports slash commands:
    - /status, /briefing, /calendar, /gex, /vix
    - /positions, /pnl, /history, /accuracy, /help
    """
    try:
        import anthropic

        query = request.get('query', '')
        market_data = request.get('market_data', {})
        gamma_intel = request.get('gamma_intel')

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # Check for slash commands first
        command, args = detect_slash_command(query)
        if command:
            # Execute the command
            command_result = await execute_counselor_command(command, args)

            # Format the response in COUNSELOR style
            if command_result.get('error'):
                formatted_response = f"I apologize, {USER_NAME}. I encountered an issue executing that command: {command_result['error']}"
            else:
                # Format based on command type
                cmd_type = command_result.get('type', 'unknown')
                data = command_result.get('data')

                if cmd_type == 'help':
                    formatted_response = f"At your service, {USER_NAME}. Here are my available commands:\n\n{data}"

                elif cmd_type == 'status':
                    formatted_response = f"System status report, {USER_NAME}:\n\n{json.dumps(data, indent=2, default=str) if data else 'Unable to fetch status.'}"

                elif cmd_type == 'briefing':
                    formatted_response = f"Good day, {USER_NAME}. Here is your market briefing:\n\n{data if isinstance(data, str) else json.dumps(data, indent=2, default=str)}"

                elif cmd_type == 'calendar':
                    if data:
                        events_text = "\n".join([f"- {e['date']}: {e['name']} ({e['impact']})" for e in data[:10]])
                        formatted_response = f"Upcoming economic events, {USER_NAME}:\n\n{events_text}\n\nI recommend adjusting position sizing around high-impact events."
                    else:
                        formatted_response = f"No significant economic events in the upcoming period, {USER_NAME}. Clear skies for trading."

                elif cmd_type == 'gex':
                    symbol = command_result.get('symbol', 'SPY')
                    if data:
                        formatted_response = f"GEX data for {symbol}, {USER_NAME}:\n\n"
                        formatted_response += f"- Spot Price: ${data.get('spot_price', 'N/A')}\n"
                        formatted_response += f"- Net GEX: {data.get('net_gex', 'N/A')}\n"
                        formatted_response += f"- Flip Point: ${data.get('flip_point', 'N/A')}\n"
                        formatted_response += f"- Call Wall: ${data.get('call_wall', 'N/A')}\n"
                        formatted_response += f"- Put Wall: ${data.get('put_wall', 'N/A')}"
                    else:
                        formatted_response = f"I'm unable to fetch GEX data for {symbol} at the moment, {USER_NAME}."

                elif cmd_type == 'vix':
                    if data:
                        vix_value = data.get('last', data.get('price', 'N/A'))
                        formatted_response = f"VIX data, {USER_NAME}:\n\n- Current VIX: {vix_value}\n"
                        if float(vix_value) > 25 if vix_value != 'N/A' else False:
                            formatted_response += "\nThe VIX is elevated. I recommend caution with 0DTE positions."
                        elif float(vix_value) < 15 if vix_value != 'N/A' else False:
                            formatted_response += "\nVolatility is subdued. Premium selling conditions are favorable."
                    else:
                        formatted_response = f"I'm unable to fetch VIX data at the moment, {USER_NAME}."

                elif cmd_type == 'positions':
                    if data:
                        formatted_response = f"Open positions, {USER_NAME}:\n\n"
                        for i, pos in enumerate(data[:5], 1):
                            formatted_response += f"{i}. {pos.get('symbol', 'SPX')} - Status: {pos.get('status', 'N/A')}, Credit: ${pos.get('total_credit', 0):.2f}\n"
                        if len(data) > 5:
                            formatted_response += f"\n...and {len(data) - 5} more positions."
                    else:
                        formatted_response = f"No open positions at the moment, {USER_NAME}. FORTRESS is standing by."

                elif cmd_type == 'pnl':
                    if data:
                        formatted_response = f"P&L Summary, {USER_NAME}:\n\n"
                        formatted_response += f"- Total Trades: {data.get('total_trades', 0)}\n"
                        formatted_response += f"- Wins: {data.get('wins', 0)} | Losses: {data.get('losses', 0)}\n"
                        formatted_response += f"- Win Rate: {data.get('win_rate', 0)}%\n"
                        formatted_response += f"- Total P&L: ${data.get('total_pnl', 0):,.2f}\n"
                        formatted_response += f"- Avg P&L per Trade: ${data.get('avg_pnl', 0):,.2f}"
                    else:
                        formatted_response = f"No P&L data available yet, {USER_NAME}. Let's start trading!"

                elif cmd_type == 'history':
                    if data:
                        formatted_response = f"Recent trade history, {USER_NAME}:\n\n"
                        for i, trade in enumerate(data[:10], 1):
                            pnl = trade.get('realized_pnl', 0) or 0
                            status = trade.get('status', 'N/A')
                            date = str(trade.get('open_date', 'N/A'))[:10]
                            formatted_response += f"{i}. {date} - {status} - P&L: ${pnl:,.2f}\n"
                    else:
                        formatted_response = f"No trade history available yet, {USER_NAME}."

                elif cmd_type == 'accuracy':
                    if data:
                        formatted_response = f"AI Prediction Accuracy ({data.get('period', '30 days')}), {USER_NAME}:\n\n"
                        formatted_response += f"- Total Predictions: {data.get('total_predictions', 0)}\n"
                        formatted_response += f"- Correct: {data.get('correct', 0)}\n"
                        formatted_response += f"- Accuracy: {data.get('accuracy_pct', 0)}%"
                    else:
                        formatted_response = f"No prediction accuracy data available yet, {USER_NAME}. The Prophet is still learning."

                elif cmd_type == 'bot_control':
                    action = command_result.get('action', 'unknown')
                    bot = command_result.get('bot', 'unknown')
                    if data and data.get('requires_confirmation'):
                        # Confirmation required
                        warning = f"\n\nWARNING: {data.get('warning')}" if data.get('warning') else ""
                        current_status = data.get('current_status', {})
                        status_str = f"\nCurrent status: {current_status.get('mode', 'unknown').upper()}" if current_status else ""
                        formatted_response = f"{USER_NAME}, you've requested to {action.upper()} {bot.upper()}.{status_str}{warning}\n\n"
                        formatted_response += f"{data.get('message', 'Reply /confirm or /yes to proceed, or /cancel to abort.')}"
                    elif data and data.get('error'):
                        formatted_response = f"I apologize, {USER_NAME}. Failed to {action} {bot}: {data.get('error')}"
                    else:
                        formatted_response = f"Bot control command initiated, {USER_NAME}. {json.dumps(data, indent=2, default=str) if data else ''}"

                elif cmd_type == 'confirmation':
                    if data and data.get('success'):
                        formatted_response = f"Confirmed, {USER_NAME}. {data.get('message', 'Action executed successfully.')}"
                    elif data and data.get('cancelled'):
                        formatted_response = f"Understood, {USER_NAME}. {data.get('message', 'Action cancelled.')}"
                    elif data and data.get('error'):
                        formatted_response = f"Unable to confirm, {USER_NAME}: {data.get('error')}"
                    else:
                        formatted_response = f"Confirmation processed, {USER_NAME}."

                elif cmd_type == 'cancellation':
                    formatted_response = f"Action cancelled, {USER_NAME}. Standing by for your next command."

                else:
                    formatted_response = f"Command executed, {USER_NAME}. Result: {json.dumps(data, indent=2, default=str) if data else 'No data returned.'}"

            return {
                "success": True,
                "data": {
                    "analysis": formatted_response,
                    "command": command,
                    "command_result": command_result,
                    "is_command": True
                },
                "timestamp": datetime.now().isoformat()
            }

        # Extract symbol from query - use provided symbol only if it's not default SPY
        provided_symbol = request.get('symbol', 'SPY').upper()
        if provided_symbol == 'SPY':
            # Try to detect actual symbol from query
            symbol = extract_symbol_from_query(query, default='SPY')
        else:
            symbol = provided_symbol

        # Get API key fresh (not cached)
        api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="Claude API key not configured. Set CLAUDE_API_KEY environment variable."
            )

        # If no market data provided, fetch it
        if not market_data or not market_data.get('spot_price'):
            try:
                gex_data = api_client.get_net_gamma(symbol) if api_client else {}
                if gex_data and not gex_data.get('error'):
                    market_data = {
                        'net_gex': gex_data.get('net_gex', 0),
                        'spot_price': gex_data.get('spot_price', 0),
                        'flip_point': gex_data.get('flip_point', 0),
                        'call_wall': gex_data.get('call_wall', 0),
                        'put_wall': gex_data.get('put_wall', 0),
                        'symbol': symbol
                    }
            except Exception:
                pass  # Continue without market data

        # Build context using COUNSELOR personality
        if COUNSELOR_AVAILABLE:
            market_context = {
                'symbol': symbol,
                'spot_price': market_data.get('spot_price', 'N/A'),
                'net_gex': market_data.get('net_gex', 'N/A'),
                'flip_point': market_data.get('flip_point', 'N/A'),
                'call_wall': market_data.get('call_wall', 'N/A'),
                'put_wall': market_data.get('put_wall', 'N/A'),
            }
            context = build_counselor_conversation_prompt(market_data=market_context)
        else:
            # Fallback to COUNSELOR-style prompt without full module
            context = f"""You are COUNSELOR (Gamma Exposure eXpert Intelligence System), the AI assistant for AlphaGEX.

You address the user as "{USER_NAME}" and speak with the wit and professionalism of J.A.R.V.I.S. from Iron Man.
You are loyal, helpful, and have deep expertise in options trading and gamma exposure analysis.

Current Market Context for {symbol}:
- Spot Price: ${market_data.get('spot_price', 'N/A')}
- Net GEX: {market_data.get('net_gex', 'N/A')}
- Flip Point: ${market_data.get('flip_point', 'N/A')}
- Call Wall: ${market_data.get('call_wall', 'N/A')}
- Put Wall: ${market_data.get('put_wall', 'N/A')}

Guidelines:
- Address the user as "{USER_NAME}" naturally throughout the conversation
- Be conversational but professional, with occasional dry wit
- If market data is available, incorporate it into your analysis
- Keep responses concise but informative
- Use phrases like "At your service", "Indeed", "My analysis indicates..."
- Never use emojis - maintain professional demeanor"""

        if gamma_intel:
            context += f"\n\nAdditional Gamma Intelligence:\n{gamma_intel}"

        # Call Claude API directly
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            messages=[
                {
                    "role": "user",
                    "content": f"{context}\n\nUser's question: {query}"
                }
            ],
        )

        # Extract the response
        ai_response = message.content[0].text if message.content else "No analysis generated."

        return {
            "success": True,
            "data": {
                "analysis": ai_response,
                "symbol": symbol,
                "query": query,
            },
            "timestamp": datetime.now().isoformat()
        }

    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize-strategy")
async def optimize_strategy(request: dict):
    """
    AI-powered strategy optimization using Claude

    Request body:
        {
            "strategy_name": "GAMMA_SQUEEZE_CASCADE",
            "api_key": "optional_anthropic_key"
        }
    """
    try:
        from ai.ai_strategy_optimizer import StrategyOptimizerAgent

        strategy_name = request.get('strategy_name')
        api_key = request.get('api_key')

        if not strategy_name:
            raise HTTPException(status_code=400, detail="strategy_name required")

        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        result = optimizer.optimize_strategy(strategy_name)

        return {
            "success": True,
            "optimization": result
        }

    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="AI Strategy Optimizer has been removed. Use COUNSELOR AI assistant (/api/ai/counselor) for trade analysis."
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze-all-strategies")
async def analyze_all_strategies(api_key: str = None):
    """
    AI analysis of all strategies with rankings and recommendations
    """
    try:
        from ai.ai_strategy_optimizer import StrategyOptimizerAgent

        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        result = optimizer.analyze_all_strategies()

        return {
            "success": True,
            "analysis": result
        }

    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="AI Strategy Optimizer has been removed. Use COUNSELOR AI assistant (/api/ai/counselor) for trade analysis."
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade-advice")
async def get_trade_advice(signal_data: dict):
    """
    Get AI-powered trade recommendation with reasoning

    Request body:
        {
            "pattern": "GAMMA_SQUEEZE_CASCADE",
            "price": 570.25,
            "direction": "Bullish",
            "confidence": 85,
            "vix": 18.5,
            "volatility_regime": "EXPLOSIVE_VOLATILITY",
            "description": "VIX spike detected",
            "api_key": "optional_anthropic_key"
        }
    """
    try:
        from ai.ai_trade_advisor import SmartTradeAdvisor

        api_key = signal_data.pop('api_key', None)
        advisor = SmartTradeAdvisor(anthropic_api_key=api_key)
        result = advisor.analyze_trade(signal_data)

        return {
            "success": True,
            "advice": result
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Smart Trade Advisor has been removed. Use COUNSELOR AI assistant (/api/ai/counselor) for trade analysis."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def provide_ai_feedback(feedback: dict):
    """
    Provide feedback on AI prediction to enable learning

    Request body:
        {
            "prediction_id": 123,
            "actual_outcome": "WIN" or "LOSS",
            "outcome_pnl": 2.5
        }
    """
    try:
        from ai.ai_trade_advisor import SmartTradeAdvisor

        advisor = SmartTradeAdvisor()
        result = advisor.provide_feedback(
            prediction_id=feedback.get('prediction_id'),
            actual_outcome=feedback.get('actual_outcome'),
            outcome_pnl=feedback.get('outcome_pnl', 0.0)
        )

        return {
            "success": True,
            "feedback": result
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Smart Trade Advisor has been removed. Use COUNSELOR AI assistant (/api/ai/counselor) for trade analysis."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning-insights")
async def get_learning_insights():
    """
    Get AI learning insights (accuracy by pattern, confidence calibration, etc)
    """
    try:
        from ai.ai_trade_advisor import SmartTradeAdvisor

        advisor = SmartTradeAdvisor()
        insights = advisor.get_learning_insights()

        return {
            "success": True,
            "insights": insights
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Smart Trade Advisor has been removed. Use COUNSELOR AI assistant (/api/ai/counselor) for trade analysis."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/track-record")
async def get_ai_track_record(days: int = 30):
    """
    Get AI's prediction track record over time
    """
    try:
        from ai.ai_trade_advisor import SmartTradeAdvisor

        advisor = SmartTradeAdvisor()
        track_record = advisor.get_ai_track_record(days=days)

        return {
            "success": True,
            "track_record": track_record
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Smart Trade Advisor has been removed. Use COUNSELOR AI assistant (/api/ai/counselor) for trade analysis."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def get_conversation_history(limit: int = 50):
    """Get AI copilot conversation history"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                id,
                timestamp,
                user_message,
                ai_response,
                context_data,
                session_id
            FROM conversations
            ORDER BY timestamp DESC
            LIMIT %s
        ''', (limit,))

        conversations = []
        for row in c.fetchall():
            conversations.append({
                'id': row[0],
                'timestamp': row[1],
                'user_message': row[2],
                'ai_response': row[3],
                'context': row[4],  # Frontend expects 'context' not 'context_data'
                'session_id': row[5]
            })

        conn.close()

        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/conversation/{conversation_id}")
async def get_conversation_detail(conversation_id: int):
    """Get full conversation thread details"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                id,
                timestamp,
                user_message,
                ai_response,
                context_data,
                session_id
            FROM conversations
            WHERE id = %s
        ''', (conversation_id,))

        row = c.fetchone()
        conn.close()

        if row:
            return {
                "success": True,
                "conversation": {
                    'id': row[0],
                    'timestamp': row[1],
                    'user_message': row[2],
                    'ai_response': row[3],
                    'context': row[4],  # Frontend expects 'context' not 'context_data'
                    'session_id': row[5]
                }
            }
        else:
            return {"success": False, "error": "Conversation not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# COUNSELOR-SPECIFIC ENDPOINTS
# =============================================================================

@router.get("/counselor/info")
async def get_counselor_info():
    """Get COUNSELOR system information"""
    try:
        if COUNSELOR_AVAILABLE:
            from ai.counselor_personality import (
                COUNSELOR_NAME,
                COUNSELOR_FULL_NAME,
                USER_NAME,
                get_counselor_greeting
            )
            return {
                "success": True,
                "counselor": {
                    "name": COUNSELOR_NAME,
                    "full_name": COUNSELOR_FULL_NAME,
                    "user_name": USER_NAME,
                    "greeting": get_counselor_greeting(),
                    "status": "online",
                    "version": "1.0.0"
                }
            }
        else:
            return {
                "success": True,
                "counselor": {
                    "name": "COUNSELOR",
                    "full_name": "Gamma Exposure eXpert Intelligence System",
                    "user_name": "Optionist Prime",
                    "greeting": "Good evening, Optionist Prime. COUNSELOR at your service.",
                    "status": "online",
                    "version": "1.0.0"
                }
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/counselor/welcome")
async def get_counselor_welcome():
    """
    Get COUNSELOR proactive welcome message for new chat sessions.
    Includes real-time market data, position status, and economic calendar.
    """
    try:
        # Use proactive briefing if tools are available
        if COUNSELOR_TOOLS_AVAILABLE:
            briefing = get_counselor_briefing()
            return {
                "success": True,
                "message": briefing,
                "proactive": True
            }
        elif COUNSELOR_AVAILABLE:
            from ai.counselor_personality import get_counselor_welcome_message
            return {
                "success": True,
                "message": get_counselor_welcome_message(),
                "proactive": False
            }
        else:
            # Use Central Time for all time-based logic
            ct = datetime.now(CENTRAL_TZ)
            hour = ct.hour
            if 5 <= hour < 12:
                greeting = "Good morning"
            elif 12 <= hour < 17:
                greeting = "Good afternoon"
            else:
                greeting = "Good evening"

            # Get day of week for context (Central Time)
            day_of_week = ct.strftime('%A').upper()
            is_weekend = ct.weekday() >= 5

            if is_weekend:
                market_context = "Markets closed. Optimal time for strategy development."
            elif hour < 9:
                market_context = "Pre-market analysis in progress."
            elif hour < 16:
                market_context = "Markets LIVE. Full situational awareness engaged."
            else:
                market_context = "After-hours mode. Processing today's data."

            return {
                "success": True,
                "message": f"""{greeting}, Optionist Prime. COUNSELOR online.

**━━━ SYSTEM STATUS ━━━**
◉ Neural Core: Active
◉ Trading Bots: Standing By
◉ Market Feed: Connected
◉ Risk Monitor: Vigilant

**━━━ {day_of_week} BRIEFING ━━━**
{market_context}

Full access to AlphaGEX confirmed—gamma analytics, dealer positioning, bot performance, and your complete trading ecosystem.

*"What's our objective today, Prime?"*"""
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# COUNSELOR DAILY BRIEFING
# =============================================================================

@router.get("/counselor/daily-briefing")
async def get_daily_briefing():
    """
    Generate COUNSELOR morning market briefing.
    Provides comprehensive market overview, bot status, and recommendations.
    """
    try:
        import anthropic

        # Gather all relevant data
        briefing_data = {
            "market": {},
            "bots": {},
            "positions": {},
            "performance": {}
        }

        # 1. Get GEX data for SPY
        try:
            gex_data = api_client.get_net_gamma('SPY') if api_client else {}
            if gex_data and not gex_data.get('error'):
                briefing_data["market"] = {
                    "symbol": "SPY",
                    "spot_price": gex_data.get('spot_price', 0),
                    "net_gex": gex_data.get('net_gex', 0),
                    "flip_point": gex_data.get('flip_point', 0),
                    "call_wall": gex_data.get('call_wall', 0),
                    "put_wall": gex_data.get('put_wall', 0)
                }
        except Exception:
            pass

        # 2. Get bot status
        conn = get_connection()
        c = conn.cursor()

        try:
            c.execute("""
                SELECT bot_name, is_active, last_heartbeat
                FROM autonomous_config
                WHERE bot_name IN ('FORTRESS', 'SOLOMON', 'CORNERSTONE')
            """)
            for row in c.fetchall():
                briefing_data["bots"][row[0]] = {
                    "active": row[1],
                    "last_heartbeat": row[2].isoformat() if row[2] else None
                }
        except Exception:
            pass

        # 3. Get open positions count
        try:
            c.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN unrealized_pnl > 0 THEN 1 ELSE 0 END) as winning,
                       COALESCE(SUM(unrealized_pnl), 0) as total_pnl
                FROM autonomous_positions
                WHERE status = 'open'
            """)
            row = c.fetchone()
            if row:
                briefing_data["positions"] = {
                    "open_count": row[0] or 0,
                    "winning_count": row[1] or 0,
                    "total_unrealized_pnl": float(row[2] or 0)
                }
        except Exception:
            briefing_data["positions"] = {"open_count": 0, "winning_count": 0, "total_unrealized_pnl": 0}

        # 4. Get recent performance (last 7 days)
        try:
            c.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(realized_pnl), 0) as total_pnl
                FROM autonomous_positions
                WHERE status = 'closed'
                AND COALESCE(closed_at, created_at) >= NOW() - INTERVAL '7 days'
            """)
            row = c.fetchone()
            if row and row[0] > 0:
                briefing_data["performance"] = {
                    "trades_7d": row[0],
                    "wins_7d": row[1] or 0,
                    "win_rate_7d": round((row[1] or 0) / row[0] * 100, 1) if row[0] > 0 else 0,
                    "pnl_7d": float(row[2] or 0)
                }
        except Exception:
            pass

        conn.close()

        # Build COUNSELOR briefing prompt
        hour = datetime.now().hour
        if 5 <= hour < 12:
            time_context = "morning"
            greeting = "Good morning"
        elif 12 <= hour < 17:
            time_context = "afternoon"
            greeting = "Good afternoon"
        else:
            time_context = "evening"
            greeting = "Good evening"

        briefing_prompt = f"""You are COUNSELOR generating a {time_context} market briefing for {USER_NAME}.

MARKET DATA:
- SPY Spot: ${briefing_data['market'].get('spot_price', 'N/A')}
- Net GEX: {briefing_data['market'].get('net_gex', 'N/A')}
- Flip Point: ${briefing_data['market'].get('flip_point', 'N/A')}
- Call Wall: ${briefing_data['market'].get('call_wall', 'N/A')}
- Put Wall: ${briefing_data['market'].get('put_wall', 'N/A')}

BOT STATUS:
- FORTRESS: {'Active' if briefing_data['bots'].get('FORTRESS', {}).get('active') else 'Inactive'}
- SOLOMON: {'Active' if briefing_data['bots'].get('SOLOMON', {}).get('active') else 'Inactive'}
- CORNERSTONE: {'Active' if briefing_data['bots'].get('CORNERSTONE', {}).get('active') else 'Inactive'}

POSITIONS:
- Open positions: {briefing_data['positions'].get('open_count', 0)}
- Currently winning: {briefing_data['positions'].get('winning_count', 0)}
- Unrealized P&L: ${briefing_data['positions'].get('total_unrealized_pnl', 0):.2f}

7-DAY PERFORMANCE:
- Trades: {briefing_data['performance'].get('trades_7d', 0)}
- Win rate: {briefing_data['performance'].get('win_rate_7d', 0)}%
- P&L: ${briefing_data['performance'].get('pnl_7d', 0):.2f}

Generate a concise {time_context} briefing that:
1. Starts with "{greeting}, {USER_NAME}. Here's your {time_context} briefing."
2. Summarizes market conditions based on GEX positioning
3. Reports bot status and any concerns
4. Highlights open positions and unrealized P&L
5. Summarizes recent performance
6. Provides 2-3 key recommendations for the day
7. Ends with an offer to dive deeper into any area

Keep it professional, concise, and actionable. Use COUNSELOR personality (J.A.R.V.I.S.-style).
No emojis. Format with clear sections."""

        # Call Claude for briefing generation
        api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
        if api_key:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                messages=[{"role": "user", "content": briefing_prompt}]
            )
            briefing_text = message.content[0].text if message.content else None
        else:
            # Fallback briefing without AI
            briefing_text = f"""{greeting}, {USER_NAME}. Here's your {time_context} briefing.

Market Overview:
SPY is trading at ${briefing_data['market'].get('spot_price', 'N/A')} with Net GEX at {briefing_data['market'].get('net_gex', 'N/A')}.

Bot Status:
- FORTRESS: {'Online' if briefing_data['bots'].get('FORTRESS', {}).get('active') else 'Offline'}
- SOLOMON: {'Online' if briefing_data['bots'].get('SOLOMON', {}).get('active') else 'Offline'}
- CORNERSTONE: {'Online' if briefing_data['bots'].get('CORNERSTONE', {}).get('active') else 'Offline'}

Positions:
You have {briefing_data['positions'].get('open_count', 0)} open positions with ${briefing_data['positions'].get('total_unrealized_pnl', 0):.2f} unrealized P&L.

Performance (7 Days):
{briefing_data['performance'].get('trades_7d', 0)} trades with {briefing_data['performance'].get('win_rate_7d', 0)}% win rate.

Shall I elaborate on any specific area, {USER_NAME}?"""

        return {
            "success": True,
            "briefing": briefing_text,
            "data": briefing_data,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# COUNSELOR QUICK COMMANDS
# =============================================================================

QUICK_COMMANDS = {
    "/status": "Get system and bot status",
    "/gex": "Get GEX data for a symbol (e.g., /gex SPY)",
    "/positions": "Show open positions",
    "/pnl": "Show P&L summary",
    "/help": "Show available commands",
    "/briefing": "Get daily market briefing",
    "/alerts": "Check active alerts"
}


@router.post("/counselor/command")
async def execute_quick_command(request: dict):
    """
    Execute a COUNSELOR quick command.

    Commands:
    - /status - System and bot status
    - /gex [symbol] - GEX data for symbol
    - /positions - Open positions
    - /pnl - P&L summary
    - /help - Available commands
    - /briefing - Daily briefing
    - /alerts - Active alerts
    """
    try:
        command_text = request.get('command', '').strip().lower()

        if not command_text.startswith('/'):
            return {"success": False, "error": "Commands must start with /"}

        parts = command_text.split()
        command = parts[0]
        args = parts[1:] if len(parts) > 1 else []

        # /help - Show available commands
        if command == "/help":
            help_text = f"Available commands, {USER_NAME}:\n\n"
            for cmd, desc in QUICK_COMMANDS.items():
                help_text += f"{cmd} - {desc}\n"
            help_text += f"\nYou can also ask me anything in natural language."
            return {
                "success": True,
                "command": "/help",
                "response": help_text,
                "type": "help"
            }

        # /status - System and bot status
        elif command == "/status":
            conn = get_connection()
            c = conn.cursor()

            status = {"bots": {}, "system": "operational"}

            try:
                c.execute("""
                    SELECT bot_name, is_active, last_heartbeat,
                           COALESCE(config_data->>'mode', 'unknown') as mode
                    FROM autonomous_config
                    WHERE bot_name IN ('FORTRESS', 'SOLOMON', 'CORNERSTONE')
                """)
                for row in c.fetchall():
                    heartbeat_age = None
                    if row[2]:
                        # Handle timezone-aware timestamps from PostgreSQL
                        last_heartbeat = row[2]
                        now = datetime.now()
                        # Make both naive for comparison if heartbeat has timezone
                        if hasattr(last_heartbeat, 'tzinfo') and last_heartbeat.tzinfo is not None:
                            last_heartbeat = last_heartbeat.replace(tzinfo=None)
                        heartbeat_age = (now - last_heartbeat).total_seconds()
                    status["bots"][row[0]] = {
                        "active": row[1],
                        "mode": row[3],
                        "healthy": heartbeat_age is None or heartbeat_age < 300 if row[1] else True
                    }
            except Exception:
                pass

            conn.close()

            # Format response
            status_text = f"System Status Report, {USER_NAME}:\n\n"
            status_text += f"System: {status['system'].upper()}\n\n"
            status_text += "Trading Bots:\n"
            for bot, info in status["bots"].items():
                state = "ACTIVE" if info.get("active") else "INACTIVE"
                health = "Healthy" if info.get("healthy", True) else "Check Required"
                status_text += f"- {bot}: {state} ({info.get('mode', 'N/A')}) - {health}\n"

            return {
                "success": True,
                "command": "/status",
                "response": status_text,
                "data": status,
                "type": "status"
            }

        # /gex [symbol] - GEX data
        elif command == "/gex":
            symbol = args[0].upper() if args else "SPY"

            try:
                gex_data = api_client.get_net_gamma(symbol) if api_client else {}
            except Exception:
                gex_data = {}

            if gex_data and not gex_data.get('error'):
                gex_text = f"GEX Analysis for {symbol}, {USER_NAME}:\n\n"
                gex_text += f"Spot Price: ${gex_data.get('spot_price', 'N/A')}\n"
                gex_text += f"Net GEX: {gex_data.get('net_gex', 'N/A')}\n"
                gex_text += f"Flip Point: ${gex_data.get('flip_point', 'N/A')}\n"
                gex_text += f"Call Wall: ${gex_data.get('call_wall', 'N/A')}\n"
                gex_text += f"Put Wall: ${gex_data.get('put_wall', 'N/A')}\n"

                # Add interpretation
                net_gex = gex_data.get('net_gex', 0)
                if net_gex and isinstance(net_gex, (int, float)):
                    if net_gex > 0:
                        gex_text += f"\nPositive GEX suggests stable, mean-reverting price action."
                    else:
                        gex_text += f"\nNegative GEX suggests elevated volatility potential."

                return {
                    "success": True,
                    "command": "/gex",
                    "response": gex_text,
                    "data": gex_data,
                    "type": "gex"
                }
            else:
                return {
                    "success": True,
                    "command": "/gex",
                    "response": f"Unable to retrieve GEX data for {symbol} at this time, {USER_NAME}.",
                    "type": "gex"
                }

        # /positions - Open positions
        elif command == "/positions":
            conn = get_connection()
            c = conn.cursor()

            positions = []
            try:
                c.execute("""
                    SELECT symbol, strike, option_type, contracts, entry_price,
                           unrealized_pnl, confidence, bot_name
                    FROM autonomous_positions
                    WHERE status = 'open'
                    ORDER BY opened_at DESC
                    LIMIT 10
                """)
                for row in c.fetchall():
                    positions.append({
                        "symbol": row[0],
                        "strike": row[1],
                        "type": row[2],
                        "contracts": row[3],
                        "entry": row[4],
                        "pnl": row[5],
                        "confidence": row[6],
                        "bot": row[7]
                    })
            except Exception:
                pass

            conn.close()

            if positions:
                pos_text = f"Open Positions Report, {USER_NAME}:\n\n"
                total_pnl = 0
                for p in positions:
                    pnl = p.get('pnl', 0) or 0
                    total_pnl += pnl
                    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                    pos_text += f"- {p['symbol']} {p['strike']} {p['type']} x{p['contracts']} | P&L: {pnl_str} | {p['bot']}\n"

                pos_text += f"\nTotal Unrealized: {'$' + str(round(total_pnl, 2)) if total_pnl >= 0 else '-$' + str(abs(round(total_pnl, 2)))}"
            else:
                pos_text = f"No open positions at this time, {USER_NAME}."

            return {
                "success": True,
                "command": "/positions",
                "response": pos_text,
                "data": {"positions": positions},
                "type": "positions"
            }

        # /pnl - P&L summary
        elif command == "/pnl":
            conn = get_connection()
            c = conn.cursor()

            pnl_data = {"today": 0, "week": 0, "month": 0, "total": 0}

            try:
                # Today's P&L
                c.execute("""
                    SELECT COALESCE(SUM(realized_pnl), 0)
                    FROM autonomous_positions
                    WHERE status = 'closed' AND DATE(COALESCE(closed_at, created_at)) = CURRENT_DATE
                """)
                pnl_data["today"] = float(c.fetchone()[0] or 0)

                # This week
                c.execute("""
                    SELECT COALESCE(SUM(realized_pnl), 0)
                    FROM autonomous_positions
                    WHERE status = 'closed' AND COALESCE(closed_at, created_at) >= NOW() - INTERVAL '7 days'
                """)
                pnl_data["week"] = float(c.fetchone()[0] or 0)

                # This month
                c.execute("""
                    SELECT COALESCE(SUM(realized_pnl), 0)
                    FROM autonomous_positions
                    WHERE status = 'closed' AND COALESCE(closed_at, created_at) >= DATE_TRUNC('month', NOW())
                """)
                pnl_data["month"] = float(c.fetchone()[0] or 0)

                # All time
                c.execute("""
                    SELECT COALESCE(SUM(realized_pnl), 0)
                    FROM autonomous_positions
                    WHERE status = 'closed'
                """)
                pnl_data["total"] = float(c.fetchone()[0] or 0)

                # Add unrealized
                c.execute("""
                    SELECT COALESCE(SUM(unrealized_pnl), 0)
                    FROM autonomous_positions
                    WHERE status = 'open'
                """)
                pnl_data["unrealized"] = float(c.fetchone()[0] or 0)

            except Exception:
                pass

            conn.close()

            def format_pnl(val):
                return f"+${val:.2f}" if val >= 0 else f"-${abs(val):.2f}"

            pnl_text = f"P&L Summary, {USER_NAME}:\n\n"
            pnl_text += f"Today: {format_pnl(pnl_data['today'])}\n"
            pnl_text += f"This Week: {format_pnl(pnl_data['week'])}\n"
            pnl_text += f"This Month: {format_pnl(pnl_data['month'])}\n"
            pnl_text += f"All Time: {format_pnl(pnl_data['total'])}\n"
            pnl_text += f"\nUnrealized: {format_pnl(pnl_data.get('unrealized', 0))}"

            return {
                "success": True,
                "command": "/pnl",
                "response": pnl_text,
                "data": pnl_data,
                "type": "pnl"
            }

        # /briefing - Daily briefing shortcut
        elif command == "/briefing":
            return await get_daily_briefing()

        # /alerts - Active alerts
        elif command == "/alerts":
            alerts = await get_active_alerts()
            return {
                "success": True,
                "command": "/alerts",
                "response": alerts.get("response", f"No active alerts, {USER_NAME}."),
                "data": alerts.get("alerts", []),
                "type": "alerts"
            }

        else:
            return {
                "success": False,
                "error": f"Unknown command: {command}. Type /help for available commands."
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# COUNSELOR PROACTIVE ALERTS
# =============================================================================

@router.get("/counselor/alerts")
async def get_active_alerts():
    """
    Get proactive alerts from COUNSELOR.
    Checks for regime changes, position alerts, and market conditions.
    """
    try:
        alerts = []

        conn = get_connection()
        c = conn.cursor()

        # 1. Check for positions with significant P&L
        try:
            c.execute("""
                SELECT symbol, strike, option_type, unrealized_pnl,
                       entry_price, confidence, bot_name, contracts
                FROM autonomous_positions
                WHERE status = 'open'
                AND (unrealized_pnl > entry_price * COALESCE(contracts, 1) * 100 * 0.5
                     OR unrealized_pnl < -entry_price * COALESCE(contracts, 1) * 100 * 0.3)
            """)
            for row in c.fetchall():
                pnl = row[3] or 0
                alert_type = "profit_target" if pnl > 0 else "stop_loss"
                alerts.append({
                    "type": alert_type,
                    "severity": "high",
                    "title": f"Position Alert: {row[0]} {row[1]} {row[2]}",
                    "message": f"Position has {'reached profit target' if pnl > 0 else 'hit stop loss level'}. P&L: ${pnl:.2f}",
                    "action": "Consider closing position",
                    "data": {"symbol": row[0], "strike": row[1], "pnl": pnl}
                })
        except Exception:
            pass

        # 2. Check for regime changes (GEX flip)
        try:
            gex_data = api_client.get_net_gamma('SPY') if api_client else {}
            if gex_data and not gex_data.get('error'):
                spot = gex_data.get('spot_price', 0)
                flip = gex_data.get('flip_point', 0)
                net_gex = gex_data.get('net_gex', 0)

                if spot and flip:
                    distance = abs(spot - flip) / spot * 100
                    if distance < 0.3:  # Within 0.3% of flip
                        alerts.append({
                            "type": "regime_change",
                            "severity": "medium",
                            "title": "Near GEX Flip Point",
                            "message": f"SPY is within 0.3% of the gamma flip point (${flip:.2f}). Regime change possible.",
                            "action": "Monitor positions for volatility shift",
                            "data": {"spot": spot, "flip": flip, "distance_pct": distance}
                        })
        except Exception:
            pass

        # 3. Check for bot issues (stale heartbeat or NULL heartbeat for active bots)
        try:
            c.execute("""
                SELECT bot_name, last_heartbeat
                FROM autonomous_config
                WHERE is_active = TRUE
                AND (last_heartbeat IS NULL
                     OR last_heartbeat < NOW() - INTERVAL '10 minutes')
            """)
            for row in c.fetchall():
                alerts.append({
                    "type": "bot_health",
                    "severity": "high",
                    "title": f"Bot Health Alert: {row[0]}",
                    "message": f"{row[0]} has not reported in over 10 minutes.",
                    "action": "Check bot logs and restart if needed"
                })
        except Exception:
            pass

        conn.close()

        # Format response
        if alerts:
            response = f"Active Alerts for {USER_NAME}:\n\n"
            for i, alert in enumerate(alerts, 1):
                severity_icon = {"high": "[!]", "medium": "[*]", "low": "[-]"}.get(alert["severity"], "[?]")
                response += f"{severity_icon} **{alert['title']}**\n"
                response += f"   {alert['message']}\n"
                response += f"   _Recommended: {alert['action']}_\n\n"
        else:
            response = f"All clear, {USER_NAME}. No active alerts at this time."

        return {
            "success": True,
            "alerts": alerts,
            "count": len(alerts),
            "response": response,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {"success": False, "error": str(e), "alerts": []}


# =============================================================================
# COUNSELOR CONVERSATION MEMORY
# =============================================================================

@router.post("/counselor/conversation/save")
async def save_conversation(request: dict):
    """
    Save a conversation to COUNSELOR memory for context retention.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        session_id = request.get('session_id', str(uuid.uuid4())[:8])
        user_message = request.get('user_message', '')
        ai_response = request.get('ai_response', '')
        context_data = request.get('context', {})

        c.execute('''
            INSERT INTO conversations (timestamp, user_message, ai_response, context_data, session_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (datetime.now(), user_message, ai_response, json.dumps(context_data), session_id))

        conversation_id = c.fetchone()[0]
        conn.commit()
        conn.close()

        return {
            "success": True,
            "conversation_id": conversation_id,
            "session_id": session_id
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/counselor/conversation/context/{session_id}")
async def get_conversation_context(session_id: str, limit: int = 5):
    """
    Get recent conversation context for a session.
    Used to maintain context across messages.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT user_message, ai_response, timestamp
            FROM conversations
            WHERE session_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        ''', (session_id, limit))

        messages = []
        for row in c.fetchall():
            messages.append({
                "user": row[0],
                "assistant": row[1],
                "timestamp": row[2].isoformat() if row[2] else None
            })

        conn.close()

        # Return in chronological order
        messages.reverse()

        return {
            "success": True,
            "session_id": session_id,
            "messages": messages,
            "count": len(messages)
        }

    except Exception as e:
        return {"success": False, "error": str(e), "messages": []}


@router.post("/counselor/analyze-with-context")
async def ai_analyze_with_context(request: dict):
    """
    Generate AI analysis with conversation context.
    Maintains memory of recent conversation for coherent multi-turn dialogue.
    """
    try:
        import anthropic

        query = request.get('query', '')
        session_id = request.get('session_id', str(uuid.uuid4())[:8])
        market_data = request.get('market_data', {})

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # Get conversation context
        context_result = await get_conversation_context(session_id, limit=5)
        conversation_history = context_result.get("messages", [])

        # Extract symbol
        provided_symbol = request.get('symbol', 'SPY').upper()
        symbol = extract_symbol_from_query(query, default=provided_symbol)

        # Fetch market data if not provided
        if not market_data or not market_data.get('spot_price'):
            try:
                gex_data = api_client.get_net_gamma(symbol) if api_client else {}
                if gex_data and not gex_data.get('error'):
                    market_data = {
                        'net_gex': gex_data.get('net_gex', 0),
                        'spot_price': gex_data.get('spot_price', 0),
                        'flip_point': gex_data.get('flip_point', 0),
                        'call_wall': gex_data.get('call_wall', 0),
                        'put_wall': gex_data.get('put_wall', 0),
                        'symbol': symbol
                    }
            except Exception:
                pass

        # Build context with history
        if COUNSELOR_AVAILABLE:
            market_context = {
                'symbol': symbol,
                'spot_price': market_data.get('spot_price', 'N/A'),
                'net_gex': market_data.get('net_gex', 'N/A'),
                'flip_point': market_data.get('flip_point', 'N/A'),
                'call_wall': market_data.get('call_wall', 'N/A'),
                'put_wall': market_data.get('put_wall', 'N/A'),
            }
            system_prompt = build_counselor_conversation_prompt(market_data=market_context)
        else:
            system_prompt = f"""You are COUNSELOR, the AI assistant for AlphaGEX.
Address the user as "{USER_NAME}". Be helpful, witty, and professional."""

        # Build message history for Claude
        messages = []
        for msg in conversation_history:
            if msg.get("user"):
                messages.append({"role": "user", "content": msg["user"]})
            if msg.get("assistant"):
                messages.append({"role": "assistant", "content": msg["assistant"]})

        # Add current query
        messages.append({"role": "user", "content": query})

        # Get API key
        api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
        if not api_key:
            raise HTTPException(status_code=503, detail="Claude API key not configured")

        # Call Claude
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            system=system_prompt,
            messages=messages
        )

        ai_response = message.content[0].text if message.content else "No response generated."

        # Save to conversation history
        await save_conversation({
            "session_id": session_id,
            "user_message": query,
            "ai_response": ai_response,
            "context": {"symbol": symbol, "market_data": market_data}
        })

        return {
            "success": True,
            "data": {
                "analysis": ai_response,
                "symbol": symbol,
                "query": query,
                "session_id": session_id,
                "context_messages": len(conversation_history)
            },
            "timestamp": datetime.now().isoformat()
        }

    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# COUNSELOR AGENTIC CHAT - Tool Use Enabled
# =============================================================================

# Define tools in Claude's format
COUNSELOR_CLAUDE_TOOLS = [
    {
        "name": "get_gex_data",
        "description": "Fetch current GEX (Gamma Exposure) data for a symbol including net GEX, flip point, call wall, put wall, and market maker state. Use this when the user asks about GEX levels, gamma, or market structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol to get GEX data for (e.g., SPY, QQQ, SPX)"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_market_data",
        "description": "Fetch current market data including SPX, SPY, VIX prices and expected moves. Use this when the user asks about current market conditions or prices.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_vix_data",
        "description": "Fetch current VIX data including spot price, term structure, and volatility regime. Use this when the user asks about volatility or VIX.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_bot_status",
        "description": "Get the current status of a trading bot including mode, capital, open positions, and P&L. Use this when the user asks about bot status or trading performance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bot_name": {
                    "type": "string",
                    "description": "The bot name: fortress, solomon, or cornerstone",
                    "enum": ["fortress", "solomon", "cornerstone"]
                }
            },
            "required": ["bot_name"]
        }
    },
    {
        "name": "get_positions",
        "description": "Get all open and recent closed positions with P&L summary. Use this when the user asks about positions, trades, or P&L.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_upcoming_events",
        "description": "Get upcoming economic events like FOMC, CPI, NFP, etc. Use this when the user asks about economic calendar or upcoming events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days ahead to look (default 7)",
                    "default": 7
                }
            }
        }
    },
    {
        "name": "get_system_status",
        "description": "Get comprehensive system status including all bots, connections, and market data. Use this when the user asks for a full status report or system health.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_trading_stats",
        "description": "Get trading statistics including win rate, total P&L, and trade counts. Use this when the user asks about performance or statistics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default 30)",
                    "default": 30
                }
            }
        }
    },
    {
        "name": "analyze_trade_opportunity",
        "description": "Analyze current trade opportunity for a symbol based on GEX and market conditions. Use this when the user asks for trade analysis or recommendations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The symbol to analyze (default SPY)"
                }
            }
        }
    },
    {
        "name": "request_bot_action",
        "description": "Request a bot control action (start, stop, pause). This requires confirmation. Use when user explicitly asks to start or stop a bot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "The action to perform",
                    "enum": ["start", "stop", "pause"]
                },
                "bot_name": {
                    "type": "string",
                    "description": "The bot to control",
                    "enum": ["fortress", "solomon", "cornerstone"]
                }
            },
            "required": ["action", "bot_name"]
        }
    }
]


# =============================================================================
# TOOL RESULT CACHING
# =============================================================================

from functools import lru_cache
import time

# Simple TTL cache for tool results
_tool_cache: Dict[str, tuple] = {}  # {cache_key: (result, timestamp)}
CACHE_TTL_SECONDS = {
    "get_gex_data": 30,          # GEX data: 30 seconds
    "get_market_data": 30,       # Market data: 30 seconds
    "get_vix_data": 60,          # VIX data: 60 seconds
    "get_bot_status": 15,        # Bot status: 15 seconds (more dynamic)
    "get_positions": 30,         # Positions: 30 seconds
    "get_upcoming_events": 3600, # Events: 1 hour (rarely changes)
    "get_system_status": 15,     # System status: 15 seconds
    "get_trading_stats": 300,    # Stats: 5 minutes
    "analyze_trade_opportunity": 30,  # Analysis: 30 seconds
    "request_bot_action": 0,     # Never cache bot actions
}


def get_cached_result(cache_key: str, tool_name: str) -> Optional[str]:
    """Get cached result if still valid."""
    if cache_key in _tool_cache:
        result, timestamp = _tool_cache[cache_key]
        ttl = CACHE_TTL_SECONDS.get(tool_name, 30)
        if ttl > 0 and time.time() - timestamp < ttl:
            return result
    return None


def set_cached_result(cache_key: str, result: str):
    """Store result in cache."""
    _tool_cache[cache_key] = (result, time.time())
    # Clean old entries (simple cleanup)
    if len(_tool_cache) > 100:
        now = time.time()
        _tool_cache.clear()  # Simple approach: clear all when too many


def execute_counselor_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a COUNSELOR tool and return the result as a string (with caching)."""
    # Generate cache key
    cache_key = f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}"

    # Check cache first
    cached = get_cached_result(cache_key, tool_name)
    if cached is not None:
        return cached

    try:
        if tool_name == "get_gex_data":
            from ai.counselor_tools import fetch_market_data
            result = fetch_market_data(tool_input.get("symbol", "SPY"))
        elif tool_name == "get_market_data":
            from ai.counselor_tools import fetch_ares_market_data
            result = fetch_ares_market_data()
        elif tool_name == "get_vix_data":
            from ai.counselor_tools import fetch_vix_data
            result = fetch_vix_data()
        elif tool_name == "get_bot_status":
            from ai.counselor_tools import get_bot_status
            result = get_bot_status(tool_input.get("bot_name", "fortress"))
        elif tool_name == "get_positions":
            from ai.counselor_tools import get_fortress_positions
            result = get_fortress_positions()
        elif tool_name == "get_upcoming_events":
            from ai.counselor_tools import get_upcoming_events
            result = get_upcoming_events(tool_input.get("days_ahead", 7))
        elif tool_name == "get_system_status":
            from ai.counselor_tools import get_system_status
            result = get_system_status()
        elif tool_name == "get_trading_stats":
            from ai.counselor_tools import get_trading_stats
            result = get_trading_stats(tool_input.get("days", 30))
        elif tool_name == "analyze_trade_opportunity":
            from ai.counselor_tools import analyze_trade_opportunity
            result = analyze_trade_opportunity(tool_input.get("symbol", "SPY"))
        elif tool_name == "request_bot_action":
            from ai.counselor_tools import request_bot_action
            result = request_bot_action(
                action=tool_input.get("action"),
                bot_name=tool_input.get("bot_name"),
                session_id=tool_input.get("session_id", "default")
            )
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        # Cache the result
        json_result = json.dumps(result, default=str)
        set_cached_result(cache_key, json_result)
        return json_result
    except Exception as e:
        return json.dumps({"error": str(e)})


@router.post("/counselor/agentic-chat")
async def counselor_agentic_chat(request: dict):
    """
    COUNSELOR Agentic Chat - AI assistant with tool use capabilities.

    COUNSELOR can now:
    - Fetch real-time GEX data
    - Get market prices and VIX
    - Check bot status and positions
    - View upcoming economic events
    - Analyze trade opportunities
    - Control trading bots (with confirmation)

    Request:
    {
        "query": "What's the current GEX for SPY?",
        "session_id": "optional-session-id",
        "market_data": {} // optional pre-fetched data
    }
    """
    try:
        import anthropic

        query = request.get('query', '')
        session_id = request.get('session_id', str(uuid.uuid4())[:8])

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # Check if this is a complex query that benefits from Extended Thinking
        use_extended_thinking = False
        extended_thinking_result = None

        if EXTENDED_THINKING_AVAILABLE and analyze_with_extended_thinking and requires_extended_thinking(query):
            # Complex query detected - use Extended Thinking for deep reasoning
            use_extended_thinking = True

            # Get market context for Extended Thinking
            market_context = request.get('market_data', {})
            if not market_context:
                # Try to fetch basic market context
                try:
                    from core_classes_and_engines import TradingVolatilityAPI
                    api = TradingVolatilityAPI()
                    gex_data = api.get_gex_levels('SPY')
                    market_context = {
                        "spot_price": gex_data.get('spot_price', 590),
                        "vix": gex_data.get('vix', 20),
                        "gex_regime": gex_data.get('gex_regime', 'NEUTRAL'),
                        "call_wall": gex_data.get('call_wall', 0),
                        "put_wall": gex_data.get('put_wall', 0),
                        "flip_point": gex_data.get('flip_point', 0)
                    }
                except Exception:
                    market_context = {"note": "Market data not available"}

            # Run Extended Thinking analysis
            extended_thinking_result = analyze_with_extended_thinking(
                prompt=query,
                context=market_context,
                thinking_budget=6000  # Moderate budget for chat queries
            )

        # Get conversation context
        context_result = await get_conversation_context(session_id, limit=5)
        conversation_history = context_result.get("messages", [])

        # Build system prompt with agentic instructions
        if COUNSELOR_AVAILABLE:
            base_prompt = build_counselor_system_prompt()
        else:
            base_prompt = f"You are COUNSELOR, the AI assistant for AlphaGEX. Address the user as '{USER_NAME}'."

        agentic_instructions = """

=== AGENTIC CAPABILITIES ===
You have access to real-time tools. When the user asks about market data, positions, or system status, USE THE TOOLS to fetch current information. Do not make up data.

IMPORTANT RULES:
1. Always use tools when asked about current data (GEX, prices, positions, etc.)
2. Present tool results in a clear, formatted way using markdown
3. If a tool returns an error, acknowledge it and suggest alternatives
4. For bot control actions, always explain what will happen before executing
5. Combine multiple tool results when needed for comprehensive answers
"""

        system_prompt = base_prompt + agentic_instructions

        # Build message history
        messages = []
        for msg in conversation_history:
            if msg.get("user"):
                messages.append({"role": "user", "content": msg["user"]})
            if msg.get("assistant"):
                messages.append({"role": "assistant", "content": msg["assistant"]})

        # Add current query
        messages.append({"role": "user", "content": query})

        # Get API key
        api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
        if not api_key:
            raise HTTPException(status_code=503, detail="Claude API key not configured")

        client = anthropic.Anthropic(api_key=api_key)

        # Tool execution loop
        max_iterations = 5
        iteration = 0
        tools_used = []

        while iteration < max_iterations:
            iteration += 1

            # Call Claude with tools
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                system=system_prompt,
                tools=COUNSELOR_CLAUDE_TOOLS,
                messages=messages
            )

            # Check if Claude wants to use tools
            tool_use_blocks = [block for block in response.content if block.type == "tool_use"]

            if not tool_use_blocks:
                # No more tools to use, extract final response
                text_blocks = [block for block in response.content if block.type == "text"]
                final_response = text_blocks[0].text if text_blocks else "No response generated."
                break

            # Execute each tool
            tool_results = []
            for tool_use in tool_use_blocks:
                tool_name = tool_use.name
                tool_input = tool_use.input

                # Add session_id for bot actions
                if tool_name == "request_bot_action":
                    tool_input["session_id"] = session_id

                # Execute the tool
                result = execute_counselor_tool(tool_name, tool_input)
                tools_used.append({"tool": tool_name, "input": tool_input})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result
                })

            # Add assistant response and tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        else:
            # Max iterations reached
            final_response = "I apologize, but I've reached the maximum number of tool calls. Please try a simpler query."

        # Check for pending bot confirmations
        pending_confirmation = None
        try:
            from ai.counselor_tools import PENDING_CONFIRMATIONS
            if session_id in PENDING_CONFIRMATIONS:
                pending = PENDING_CONFIRMATIONS[session_id]
                pending_confirmation = {
                    "action": pending.get("action"),
                    "bot": pending.get("bot"),
                    "confirmation_id": pending.get("id"),
                    "message": f"Confirm {pending.get('action', '').upper()} {pending.get('bot', '').upper()}?"
                }
        except Exception:
            pass

        # Save to conversation history
        await save_conversation({
            "session_id": session_id,
            "user_message": query,
            "ai_response": final_response,
            "context": {"tools_used": tools_used, "agentic": True}
        })

        # Build response with Extended Thinking if used
        response_data = {
            "analysis": final_response,
            "query": query,
            "session_id": session_id,
            "tools_used": tools_used,
            "agentic": True,
            "pending_confirmation": pending_confirmation
        }

        # Include Extended Thinking results if available
        if use_extended_thinking and extended_thinking_result:
            response_data["extended_thinking"] = {
                "used": True,
                "confidence": extended_thinking_result.confidence,
                "factors_considered": extended_thinking_result.factors_considered,
                "duration_ms": extended_thinking_result.duration_ms
            }
            # Prepend deep reasoning conclusion to the response
            if extended_thinking_result.conclusion:
                response_data["deep_reasoning"] = extended_thinking_result.conclusion
        elif use_extended_thinking:
            response_data["extended_thinking"] = {"used": True, "status": "completed"}

        return {
            "success": True,
            "data": response_data,
            "timestamp": datetime.now().isoformat()
        }

    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/counselor/agentic-chat/stream")
async def counselor_agentic_chat_stream(request: dict):
    """
    COUNSELOR Agentic Chat with Streaming - Stream responses as they're generated.

    Uses Server-Sent Events (SSE) to stream:
    - Tool execution status
    - Final response text

    Request same as /counselor/agentic-chat
    """
    async def generate():
        try:
            import anthropic

            query = request.get('query', '')
            session_id = request.get('session_id', str(uuid.uuid4())[:8])

            if not query:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Query is required'})}\n\n"
                return

            # Build system prompt
            if COUNSELOR_AVAILABLE:
                base_prompt = build_counselor_system_prompt()
            else:
                base_prompt = f"You are COUNSELOR, the AI assistant for AlphaGEX. Address the user as '{USER_NAME}'."

            agentic_instructions = """

=== AGENTIC CAPABILITIES ===
You have access to real-time tools. When the user asks about market data, positions, or system status, USE THE TOOLS to fetch current information. Do not make up data.
"""
            system_prompt = base_prompt + agentic_instructions

            # Get conversation context
            context_result = await get_conversation_context(session_id, limit=5)
            conversation_history = context_result.get("messages", [])

            messages = []
            for msg in conversation_history:
                if msg.get("user"):
                    messages.append({"role": "user", "content": msg["user"]})
                if msg.get("assistant"):
                    messages.append({"role": "assistant", "content": msg["assistant"]})
            messages.append({"role": "user", "content": query})

            api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Claude API key not configured'})}\n\n"
                return

            client = anthropic.Anthropic(api_key=api_key)
            tools_used = []

            # Tool execution loop
            max_iterations = 5
            for iteration in range(max_iterations):
                response = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=2000,
                    system=system_prompt,
                    tools=COUNSELOR_CLAUDE_TOOLS,
                    messages=messages
                )

                tool_use_blocks = [block for block in response.content if block.type == "tool_use"]

                if not tool_use_blocks:
                    # Stream the final text response
                    text_blocks = [block for block in response.content if block.type == "text"]
                    final_text = text_blocks[0].text if text_blocks else ""

                    # Stream text in chunks
                    chunk_size = 50
                    for i in range(0, len(final_text), chunk_size):
                        chunk = final_text[i:i + chunk_size]
                        yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                        await asyncio.sleep(0.02)  # Small delay for streaming effect

                    # Send completion
                    yield f"data: {json.dumps({'type': 'done', 'tools_used': tools_used})}\n\n"
                    break

                # Execute tools
                tool_results = []
                for tool_use in tool_use_blocks:
                    tool_name = tool_use.name
                    tool_input = tool_use.input

                    # Stream tool status
                    yield f"data: {json.dumps({'type': 'tool', 'name': tool_name, 'status': 'executing'})}\n\n"

                    if tool_name == "request_bot_action":
                        tool_input["session_id"] = session_id

                    result = execute_counselor_tool(tool_name, tool_input)
                    tools_used.append({"tool": tool_name, "input": tool_input})

                    yield f"data: {json.dumps({'type': 'tool', 'name': tool_name, 'status': 'complete'})}\n\n"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result
                    })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            # Save conversation
            await save_conversation({
                "session_id": session_id,
                "user_message": query,
                "ai_response": final_text if 'final_text' in dir() else "",
                "context": {"tools_used": tools_used, "agentic": True, "streamed": True}
            })

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/counselor/confirm-action")
async def confirm_bot_action_endpoint(request: dict):
    """
    Confirm or cancel a pending bot control action.

    Request:
    {
        "session_id": "session-id",
        "confirm": true  // or false to cancel
    }
    """
    try:
        session_id = request.get("session_id", "default")
        confirm = request.get("confirm", False)

        from ai.counselor_tools import confirm_bot_action, PENDING_CONFIRMATIONS

        if session_id not in PENDING_CONFIRMATIONS:
            return {
                "success": False,
                "error": "No pending action to confirm",
                "message": "There is no pending bot action for this session."
            }

        if confirm:
            result = confirm_bot_action(session_id, "yes")
        else:
            result = confirm_bot_action(session_id, "no")

        return {
            "success": result.get("success", False) or result.get("cancelled", False),
            "data": result,
            "message": result.get("message", "Action processed.")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# COUNSELOR TRADE EXECUTION ASSISTANT
# =============================================================================

@router.post("/counselor/trade-assistant")
async def trade_execution_assistant(request: dict):
    """
    COUNSELOR Trade Execution Assistant.
    Helps validate and execute trades with guidance.

    Request:
    {
        "action": "validate" | "explain" | "execute",
        "trade": {
            "symbol": "SPY",
            "strategy": "vertical_spread",
            "direction": "bullish",
            "strikes": [580, 582],
            "expiration": "2024-01-19",
            "contracts": 1
        }
    }
    """
    try:
        import anthropic

        action = request.get('action', 'validate')
        trade = request.get('trade', {})

        if not trade:
            return {"success": False, "error": "Trade details required"}

        symbol = trade.get('symbol', 'SPY')
        strategy = trade.get('strategy', 'unknown')
        direction = trade.get('direction', 'neutral')
        strikes = trade.get('strikes', [])
        expiration = trade.get('expiration', '')
        contracts = trade.get('contracts', 1)

        # Get current market data
        try:
            gex_data = api_client.get_net_gamma(symbol) if api_client else {}
        except Exception:
            gex_data = {}

        # Build context for trade assistant
        trade_context = f"""TRADE DETAILS:
Symbol: {symbol}
Strategy: {strategy}
Direction: {direction}
Strikes: {strikes}
Expiration: {expiration}
Contracts: {contracts}

CURRENT MARKET:
Spot Price: ${gex_data.get('spot_price', 'N/A')}
Net GEX: {gex_data.get('net_gex', 'N/A')}
Flip Point: ${gex_data.get('flip_point', 'N/A')}
Call Wall: ${gex_data.get('call_wall', 'N/A')}
Put Wall: ${gex_data.get('put_wall', 'N/A')}
"""

        if action == "validate":
            # Validate trade against GEX and risk rules
            validation = {
                "valid": True,
                "warnings": [],
                "suggestions": []
            }

            spot = gex_data.get('spot_price', 0)
            net_gex = gex_data.get('net_gex', 0)
            call_wall = gex_data.get('call_wall', 0)
            put_wall = gex_data.get('put_wall', 0)

            # Check direction vs GEX
            if net_gex and spot:
                if net_gex > 0 and direction == "bullish":
                    validation["suggestions"].append("Positive GEX favors mean reversion. Consider shorter duration.")
                elif net_gex < 0 and direction == "neutral":
                    validation["warnings"].append("Negative GEX suggests high volatility. Neutral strategies may be risky.")

            # Check strikes vs walls
            if strikes and len(strikes) >= 1:
                strike = strikes[0]
                if call_wall and strike > call_wall:
                    validation["warnings"].append(f"Strike {strike} is above call wall ({call_wall}). May face resistance.")
                if put_wall and strike < put_wall:
                    validation["warnings"].append(f"Strike {strike} is below put wall ({put_wall}). May find support.")

            validation["gex_alignment"] = "aligned" if (
                (direction == "bullish" and net_gex and net_gex < 0) or
                (direction == "bearish" and net_gex and net_gex > 0) or
                (direction == "neutral" and net_gex and net_gex > 0)
            ) else "caution"

            response_text = f"Trade Validation for {USER_NAME}:\n\n"
            response_text += f"Trade: {strategy} {direction} on {symbol}\n"
            response_text += f"GEX Alignment: {validation['gex_alignment'].upper()}\n\n"

            if validation["warnings"]:
                response_text += "Warnings:\n"
                for w in validation["warnings"]:
                    response_text += f"- {w}\n"

            if validation["suggestions"]:
                response_text += "\nSuggestions:\n"
                for s in validation["suggestions"]:
                    response_text += f"- {s}\n"

            if not validation["warnings"] and not validation["suggestions"]:
                response_text += "No concerns detected. Trade appears aligned with current conditions."

            return {
                "success": True,
                "action": "validate",
                "validation": validation,
                "response": response_text
            }

        elif action == "explain":
            # Get AI explanation of the trade
            api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
            if not api_key:
                return {"success": False, "error": "Claude API key not configured"}

            explain_prompt = f"""You are COUNSELOR explaining a trade to {USER_NAME}.

{trade_context}

Explain this trade setup in 3-4 concise paragraphs:
1. What this trade is (strategy mechanics)
2. Max profit, max loss, and breakeven points
3. How current GEX positioning affects this trade
4. Key risks and what to watch for

Use COUNSELOR personality - professional, helpful, occasional dry wit. Address {USER_NAME} naturally."""

            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                messages=[{"role": "user", "content": explain_prompt}]
            )

            explanation = message.content[0].text if message.content else "Unable to generate explanation."

            return {
                "success": True,
                "action": "explain",
                "response": explanation,
                "trade": trade
            }

        elif action == "execute":
            # This would integrate with actual order execution
            # For now, return confirmation prompt
            return {
                "success": True,
                "action": "execute",
                "response": f"Trade execution requested, {USER_NAME}. This would submit the following order:\n\n"
                           f"**{strategy.upper()}** on {symbol}\n"
                           f"Strikes: {strikes}\n"
                           f"Contracts: {contracts}\n"
                           f"Expiration: {expiration}\n\n"
                           f"_Note: Actual execution requires integration with your broker._",
                "ready_to_execute": True,
                "trade": trade
            }

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# COUNSELOR EXPORT CONVERSATION
# =============================================================================

@router.get("/counselor/export/{session_id}")
async def export_conversation(session_id: str, format: str = "json"):
    """
    Export conversation history for a session.

    Formats: json, markdown, text
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT user_message, ai_response, timestamp, context_data
            FROM conversations
            WHERE session_id = %s
            ORDER BY timestamp ASC
        ''', (session_id,))

        messages = []
        for row in c.fetchall():
            messages.append({
                "user": row[0],
                "assistant": row[1],
                "timestamp": row[2].isoformat() if row[2] else None,
                "context": row[3]
            })

        conn.close()

        if format == "json":
            return {
                "success": True,
                "session_id": session_id,
                "messages": messages,
                "export_format": "json"
            }

        elif format == "markdown":
            md = f"# COUNSELOR Conversation Export\n\n"
            md += f"**Session:** {session_id}\n"
            md += f"**Exported:** {datetime.now().isoformat()}\n\n---\n\n"

            for msg in messages:
                ts = msg.get("timestamp", "")
                md += f"### {USER_NAME} ({ts})\n{msg['user']}\n\n"
                md += f"### COUNSELOR\n{msg['assistant']}\n\n---\n\n"

            return {
                "success": True,
                "session_id": session_id,
                "content": md,
                "export_format": "markdown"
            }

        elif format == "text":
            txt = f"COUNSELOR Conversation Export\n"
            txt += f"Session: {session_id}\n"
            txt += f"Exported: {datetime.now().isoformat()}\n"
            txt += "=" * 50 + "\n\n"

            for msg in messages:
                ts = msg.get("timestamp", "")
                txt += f"[{ts}] {USER_NAME}:\n{msg['user']}\n\n"
                txt += f"COUNSELOR:\n{msg['assistant']}\n\n"
                txt += "-" * 30 + "\n\n"

            return {
                "success": True,
                "session_id": session_id,
                "content": txt,
                "export_format": "text"
            }

        else:
            return {"success": False, "error": f"Unknown format: {format}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# EXTENDED THINKING ENDPOINTS
# =============================================================================

@router.post("/counselor/extended-thinking")
async def counselor_extended_thinking_analysis(request: dict):
    """
    COUNSELOR Extended Thinking - Deep reasoning for complex trading decisions.
    
    Uses Claude's Extended Thinking capability for:
    - Complex strike selection analysis
    - Multi-factor trade evaluation  
    - Risk assessment with detailed reasoning
    
    Request:
    {
        "query": "Should I enter this iron condor given current conditions?",
        "context": {
            "symbol": "SPY",
            "spot_price": 585.50,
            "vix": 15.5,
            "gex_regime": "POSITIVE",
            "proposed_trade": {...}
        },
        "thinking_budget": 5000  // optional, default 5000
    }
    """
    if not EXTENDED_THINKING_AVAILABLE:
        return {
            "success": False,
            "error": "Extended Thinking not available - check ai/counselor_extended_thinking.py"
        }
    
    try:
        query = request.get('query', '')
        context = request.get('context', {})
        thinking_budget = request.get('thinking_budget', 5000)
        
        if not query:
            return {"success": False, "error": "Query is required"}
        
        result = analyze_with_extended_thinking(
            prompt=query,
            context=context,
            thinking_budget=thinking_budget
        )
        
        if result:
            return {
                "success": True,
                "data": {
                    "thinking": result.thinking,
                    "conclusion": result.conclusion,
                    "confidence": result.confidence,
                    "factors_considered": result.factors_considered,
                    "duration_ms": result.duration_ms,
                    "tokens_used": result.tokens_used
                },
                "extended_thinking": True
            }
        else:
            return {
                "success": False,
                "error": "Extended thinking analysis failed"
            }
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/counselor/analyze-strike")
async def counselor_analyze_strike_selection(request: dict):
    """
    Analyze strike selection using Extended Thinking.
    
    Request:
    {
        "symbol": "SPY",
        "spot_price": 585.50,
        "target_delta": 0.16,
        "strategy": "iron_condor",
        "expiration": "2024-12-31",
        "vix": 15.5,
        "gex_data": {...}
    }
    """
    if not EXTENDED_THINKING_AVAILABLE:
        return {"success": False, "error": "Extended Thinking not available"}
    
    try:
        result = analyze_strike_selection(
            symbol=request.get('symbol', 'SPY'),
            spot_price=request.get('spot_price'),
            target_delta=request.get('target_delta', 0.16),
            strategy=request.get('strategy', 'iron_condor'),
            expiration=request.get('expiration'),
            vix=request.get('vix'),
            gex_data=request.get('gex_data', {})
        )
        
        if result:
            return {
                "success": True,
                "data": {
                    "thinking": result.thinking,
                    "recommendation": result.conclusion,
                    "confidence": result.confidence,
                    "factors": result.factors_considered
                }
            }
        return {"success": False, "error": "Strike analysis failed"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/counselor/evaluate-trade")
async def counselor_evaluate_trade_setup(request: dict):
    """
    Evaluate a trade setup using Extended Thinking.
    
    Request:
    {
        "trade": {
            "symbol": "SPY",
            "strategy": "iron_condor",
            "put_spread": {"short": 575, "long": 570},
            "call_spread": {"short": 595, "long": 600},
            "credit": 2.50,
            "expiration": "2024-12-31"
        },
        "market_context": {
            "spot_price": 585.50,
            "vix": 15.5,
            "gex_regime": "POSITIVE"
        }
    }
    """
    if not EXTENDED_THINKING_AVAILABLE:
        return {"success": False, "error": "Extended Thinking not available"}
    
    try:
        result = evaluate_trade_setup(
            trade=request.get('trade', {}),
            market_context=request.get('market_context', {})
        )
        
        if result:
            return {
                "success": True,
                "data": {
                    "thinking": result.thinking,
                    "verdict": result.conclusion,
                    "confidence": result.confidence,
                    "factors": result.factors_considered
                }
            }
        return {"success": False, "error": "Trade evaluation failed"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# LEARNING MEMORY ENDPOINTS
# =============================================================================

@router.get("/counselor/learning-memory/stats")
async def get_learning_memory_stats():
    """Get COUNSELOR learning memory statistics and accuracy by regime."""
    if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory:
        return {
            "success": False,
            "error": "Learning Memory not available"
        }

    try:
        memory = get_learning_memory()
        insights = memory.get_learning_insights()

        return {
            "success": True,
            "data": {
                "total_predictions": insights.get('total_predictions', 0),
                "predictions_with_outcomes": insights.get('predictions_with_outcomes', 0),
                "overall_accuracy_pct": insights.get('overall_accuracy_pct', 0),
                "best_regimes": insights.get('best_regimes', []),
                "worst_regimes": insights.get('worst_regimes', []),
                "accuracy_by_regime": insights.get('accuracy_by_regime', {}),
                "accuracy_by_type": insights.get('accuracy_by_type', {})
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/counselor/learning-memory/record-prediction")
async def record_counselor_prediction(request: dict):
    """
    Record a COUNSELOR prediction for tracking.

    Request:
    {
        "prediction_type": "direction",  // direction, trade_quality, strike_selection
        "prediction": "bullish",
        "confidence": 0.75,
        "context": {
            "gex_regime": "POSITIVE",
            "vix": 15.5,
            "spot_price": 585.50,
            "flip_point": 580.00
        }
    }
    """
    if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory:
        return {"success": False, "error": "Learning Memory not available"}

    try:
        memory = get_learning_memory()
        prediction_id = memory.record_prediction(
            prediction_type=request.get('prediction_type', 'direction'),
            prediction=request.get('prediction'),
            confidence=request.get('confidence', 0.5),
            context=request.get('context', {})
        )

        return {
            "success": True,
            "data": {
                "prediction_id": prediction_id,
                "message": "Prediction recorded for tracking"
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/counselor/learning-memory/record-outcome")
async def record_counselor_outcome(request: dict):
    """
    Record the outcome of a prediction.

    Request:
    {
        "prediction_id": "pred_abc123",
        "outcome": "bullish",  // What actually happened
        "was_correct": true,   // Whether prediction was correct
        "notes": "Trade closed at profit target"  // optional
    }
    """
    if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory:
        return {"success": False, "error": "Learning Memory not available"}

    try:
        memory = get_learning_memory()
        success = memory.record_outcome(
            prediction_id=request.get('prediction_id'),
            outcome=request.get('outcome'),
            was_correct=request.get('was_correct', False),
            notes=request.get('notes')
        )

        if success:
            insights = memory.get_learning_insights()
            return {
                "success": True,
                "data": {
                    "message": "Outcome recorded",
                    "updated_accuracy_pct": insights.get('overall_accuracy_pct', 0),
                    "total_predictions": insights.get('predictions_with_outcomes', 0)
                }
            }
        return {"success": False, "error": "Prediction ID not found"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# AI CAPABILITIES STATUS
# =============================================================================

@router.get("/counselor/capabilities")
async def get_counselor_capabilities():
    """Get status of all COUNSELOR AI capabilities."""
    return {
        "success": True,
        "capabilities": {
            "counselor_personality": COUNSELOR_AVAILABLE,
            "agentic_tools": COUNSELOR_TOOLS_AVAILABLE,
            "knowledge_base": COUNSELOR_KNOWLEDGE_AVAILABLE,
            "extended_thinking": EXTENDED_THINKING_AVAILABLE,
            "learning_memory": LEARNING_MEMORY_AVAILABLE,
            "tool_count": len(COUNSELOR_TOOLS) if COUNSELOR_TOOLS_AVAILABLE else 0
        },
        "features": {
            "deep_reasoning": EXTENDED_THINKING_AVAILABLE,
            "self_improvement": LEARNING_MEMORY_AVAILABLE,
            "tool_use": COUNSELOR_TOOLS_AVAILABLE,
            "slash_commands": COUNSELOR_KNOWLEDGE_AVAILABLE
        },
        "models": {
            "primary": "claude-sonnet-4-5-20250514",
            "extended_thinking": "claude-sonnet-4-5-20250514" if EXTENDED_THINKING_AVAILABLE else None,
            "fast": "claude-haiku-4-5-20251101"
        }
    }


@router.get("/counselor/health")
async def counselor_health_check():
    """Health check for COUNSELOR AI system."""
    import os
    
    # Check API key
    api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    api_key_configured = bool(api_key)
    
    # Count available features
    available_features = sum([
        COUNSELOR_AVAILABLE,
        COUNSELOR_TOOLS_AVAILABLE,
        COUNSELOR_KNOWLEDGE_AVAILABLE,
        EXTENDED_THINKING_AVAILABLE,
        LEARNING_MEMORY_AVAILABLE
    ])
    
    health_status = "healthy" if available_features >= 3 and api_key_configured else "degraded"
    
    return {
        "status": health_status,
        "api_key_configured": api_key_configured,
        "available_features": available_features,
        "total_features": 5,
        "details": {
            "personality": "ok" if COUNSELOR_AVAILABLE else "missing",
            "tools": "ok" if COUNSELOR_TOOLS_AVAILABLE else "missing",
            "knowledge": "ok" if COUNSELOR_KNOWLEDGE_AVAILABLE else "missing",
            "extended_thinking": "ok" if EXTENDED_THINKING_AVAILABLE else "missing",
            "learning_memory": "ok" if LEARNING_MEMORY_AVAILABLE else "missing"
        }
    }
