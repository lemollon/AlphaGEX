"""
AI Copilot API routes - Claude AI integration for market analysis and trade advice.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import api_client, claude_ai, get_connection

router = APIRouter(prefix="/api/ai", tags=["AI Copilot"])


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
        symbol = request.get('symbol', 'SPY').upper()
        query = request.get('query', '')
        market_data = request.get('market_data', {})
        gamma_intel = request.get('gamma_intel')

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # If no market data provided, fetch it
        if not market_data:
            gex_data = api_client.get_net_gamma(symbol)
            market_data = {
                'net_gex': gex_data.get('net_gex', 0),
                'spot_price': gex_data.get('spot_price', 0),
                'flip_point': gex_data.get('flip_point', 0),
                'symbol': symbol
            }

        ai_response = claude_ai.analyze_market(
            market_data=market_data,
            user_query=query,
            gamma_intel=gamma_intel
        )

        return {
            "success": True,
            "symbol": symbol,
            "query": query,
            "response": ai_response,
            "timestamp": datetime.now().isoformat()
        }

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
        from ai_strategy_optimizer import StrategyOptimizerAgent

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
        from ai_strategy_optimizer import StrategyOptimizerAgent

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
        from ai_trade_advisor import SmartTradeAdvisor

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
        from ai_trade_advisor import SmartTradeAdvisor

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
        from ai_trade_advisor import SmartTradeAdvisor

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
        from ai_trade_advisor import SmartTradeAdvisor

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
                context,
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
                'context': row[4],
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
                context,
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
                    'context': row[4],
                    'session_id': row[5]
                }
            }
        else:
            return {"success": False, "error": "Conversation not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}
