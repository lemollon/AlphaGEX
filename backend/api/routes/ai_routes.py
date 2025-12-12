"""
AI Copilot API routes - Claude AI integration for market analysis and trade advice.
"""

import os
import base64
from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import api_client, claude_ai, get_connection

router = APIRouter(prefix="/api/ai", tags=["AI Copilot"])


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

        symbol = request.get('symbol', 'SPY').upper()
        query = request.get('query', 'Please analyze this image and provide trading insights.')
        image_data = request.get('image_data', '')
        market_data = request.get('market_data', {})

        if not image_data:
            raise HTTPException(status_code=400, detail="image_data is required")

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

        # Build context
        context = f"""You are an expert options trader and market analyst for AlphaGEX platform.

Current Market Context for {symbol}:
- Spot Price: ${market_data.get('spot_price', 'N/A')}
- Net GEX: {market_data.get('net_gex', 'N/A')}
- Flip Point: ${market_data.get('flip_point', 'N/A')}
- Call Wall: ${market_data.get('call_wall', 'N/A')}
- Put Wall: ${market_data.get('put_wall', 'N/A')}

The user has uploaded an image (chart, option chain, screenshot, etc.) for analysis.
Please analyze the image thoroughly and provide:
1. What you see in the image (chart pattern, option data, etc.)
2. Key observations and insights
3. Trading implications based on current market context
4. Specific actionable recommendations if applicable

Be concise but thorough. Focus on practical trading insights."""

        # Call Claude API with vision
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-latest",  # Always use latest Sonnet 4.5
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

        symbol = request.get('symbol', 'SPY').upper()
        query = request.get('query', '')
        market_data = request.get('market_data', {})
        gamma_intel = request.get('gamma_intel')

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

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

        # Build context for Claude
        context = f"""You are an expert AI trading assistant for AlphaGEX, a gamma exposure (GEX) analysis platform.

You should be conversational, helpful, and engaging. Answer questions naturally like a knowledgeable friend who happens to be an expert trader.

Current Market Context for {symbol}:
- Spot Price: ${market_data.get('spot_price', 'N/A')}
- Net GEX: {market_data.get('net_gex', 'N/A')}
- Flip Point: ${market_data.get('flip_point', 'N/A')}
- Call Wall: ${market_data.get('call_wall', 'N/A')}
- Put Wall: ${market_data.get('put_wall', 'N/A')}

Guidelines:
- Be conversational and natural, not robotic or templated
- If asked general questions, answer them helpfully
- Only provide trading analysis when specifically asked about trades or market analysis
- If market data is available, incorporate it into your analysis when relevant
- Keep responses concise but informative"""

        if gamma_intel:
            context += f"\n\nAdditional Gamma Intelligence:\n{gamma_intel}"

        # Call Claude API directly
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-latest",
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
