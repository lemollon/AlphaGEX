"""
AI Copilot API routes - Claude AI integration for market analysis and trade advice.

Powered by GEXIS (Gamma Exposure eXpert Intelligence System)
"""

import os
import re
import base64
from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import api_client, claude_ai, get_connection

# Import GEXIS personality system
try:
    from ai.gexis_personality import (
        build_gexis_conversation_prompt,
        get_gexis_welcome_message,
        get_gexis_error_message,
        USER_NAME,
        GEXIS_NAME
    )
    GEXIS_AVAILABLE = True
except ImportError:
    GEXIS_AVAILABLE = False
    USER_NAME = "Optionist Prime"
    GEXIS_NAME = "GEXIS"

router = APIRouter(prefix="/api/ai", tags=["AI Copilot"])

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

        # Build GEXIS context for image analysis
        context = f"""You are GEXIS (Gamma Exposure eXpert Intelligence System), the AI assistant for AlphaGEX.
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

Maintain GEXIS personality - professional, helpful, and address {USER_NAME} naturally."""

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
    """
    try:
        import anthropic

        query = request.get('query', '')
        market_data = request.get('market_data', {})
        gamma_intel = request.get('gamma_intel')

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

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

        # Build context using GEXIS personality
        if GEXIS_AVAILABLE:
            market_context = {
                'symbol': symbol,
                'spot_price': market_data.get('spot_price', 'N/A'),
                'net_gex': market_data.get('net_gex', 'N/A'),
                'flip_point': market_data.get('flip_point', 'N/A'),
                'call_wall': market_data.get('call_wall', 'N/A'),
                'put_wall': market_data.get('put_wall', 'N/A'),
            }
            context = build_gexis_conversation_prompt(market_data=market_context)
        else:
            # Fallback to GEXIS-style prompt without full module
            context = f"""You are GEXIS (Gamma Exposure eXpert Intelligence System), the AI assistant for AlphaGEX.

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
            detail="AI Strategy Optimizer requires langchain. Install with: pip install langchain langchain-anthropic"
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
            detail="AI Strategy Optimizer requires langchain. Install with: pip install langchain langchain-anthropic"
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
# GEXIS-SPECIFIC ENDPOINTS
# =============================================================================

@router.get("/gexis/info")
async def get_gexis_info():
    """Get GEXIS system information"""
    try:
        if GEXIS_AVAILABLE:
            from ai.gexis_personality import (
                GEXIS_NAME,
                GEXIS_FULL_NAME,
                USER_NAME,
                get_gexis_greeting
            )
            return {
                "success": True,
                "gexis": {
                    "name": GEXIS_NAME,
                    "full_name": GEXIS_FULL_NAME,
                    "user_name": USER_NAME,
                    "greeting": get_gexis_greeting(),
                    "status": "online",
                    "version": "1.0.0"
                }
            }
        else:
            return {
                "success": True,
                "gexis": {
                    "name": "GEXIS",
                    "full_name": "Gamma Exposure eXpert Intelligence System",
                    "user_name": "Optionist Prime",
                    "greeting": "Good evening, Optionist Prime. GEXIS at your service.",
                    "status": "online",
                    "version": "1.0.0"
                }
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/gexis/welcome")
async def get_gexis_welcome():
    """Get GEXIS welcome message for new chat sessions"""
    try:
        if GEXIS_AVAILABLE:
            from ai.gexis_personality import get_gexis_welcome_message
            return {
                "success": True,
                "message": get_gexis_welcome_message()
            }
        else:
            from datetime import datetime
            hour = datetime.now().hour
            if 5 <= hour < 12:
                greeting = "Good morning"
            elif 12 <= hour < 17:
                greeting = "Good afternoon"
            else:
                greeting = "Good evening"

            return {
                "success": True,
                "message": f"""{greeting}, Optionist Prime. GEXIS online and at your service.

All systems are operational. I have full access to AlphaGEX's trading intelligence, including:
- Real-time GEX analysis and market maker positioning
- ARES, APACHE, and ATLAS bot status monitoring
- Trade recommendations and probability analysis
- Your trading history and performance insights

How may I assist you today?"""
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
