"""
Strategy Optimizer API routes - AI-powered strategy optimization.
"""

import json
import os
import traceback
from datetime import datetime

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/optimizer", tags=["Strategy Optimizer"])


@router.get("/analyze/{strategy_name}")
async def optimize_strategy(strategy_name: str):
    """
    AI-powered strategy optimization with dynamic stats integration

    Analyzes strategy performance and provides specific optimization recommendations
    Uses live win rates from auto-updated backtest results
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set. Configure API key to use optimizer."
            )

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent

        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        result = optimizer.optimize_with_dynamic_stats(strategy_name=strategy_name)

        return {
            "success": True,
            "strategy": strategy_name,
            "optimization": result,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Optimizer dependencies not installed: {str(e)}. Run: pip install langchain-anthropic"
        )
    except Exception as e:
        print(f"❌ Error in strategy optimizer: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze-all")
async def optimize_all_strategies():
    """
    AI-powered analysis of ALL strategies with dynamic stats

    Ranks strategies by profitability, identifies top performers,
    and provides resource allocation recommendations
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set. Configure API key to use optimizer."
            )

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent

        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        result = optimizer.optimize_with_dynamic_stats(strategy_name=None)

        return {
            "success": True,
            "optimization": result,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Optimizer dependencies not installed: {str(e)}. Run: pip install langchain-anthropic"
        )
    except Exception as e:
        print(f"❌ Error in strategy optimizer: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommend-trade")
async def get_trade_recommendation(request: dict):
    """
    AI-powered real-time trade recommendation

    Analyzes current market conditions and provides specific trade recommendation
    with entry, stop, target, and confidence level
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set. Configure API key to use optimizer."
            )

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent

        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        result = optimizer.get_trade_recommendation(current_market_data=request)

        return {
            "success": True,
            "trade_recommendation": result,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Optimizer dependencies not installed: {str(e)}. Run: pip install langchain-anthropic"
        )
    except Exception as e:
        print(f"❌ Error getting trade recommendation: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strikes")
async def get_strike_performance(strategy: str = None):
    """
    Get strike-level performance analysis

    Shows which strikes perform best by moneyness, strike distance,
    VIX regime, win rate, and P&L per strike type.
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        strike_data_json = optimizer._analyze_strike_performance(strategy)

        try:
            strike_data = json.loads(strike_data_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            strike_data = {"raw_data": strike_data_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "strike_performance": strike_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in strike performance: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dte")
async def get_dte_optimization(strategy: str = None):
    """
    Get DTE (Days To Expiration) optimization analysis

    Shows which DTE ranges work best (0-3, 4-7, 8-14, 15-30, 30+ DTE).
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        dte_data_json = optimizer._analyze_dte_performance(strategy)

        try:
            dte_data = json.loads(dte_data_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            dte_data = {"raw_data": dte_data_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "dte_optimization": dte_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in DTE optimization: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime-specific")
async def get_regime_optimization(strategy: str = None):
    """
    Get regime-specific optimization analysis

    Different strategies for different regimes (VIX levels, gamma exposure).
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        regime_data_json = optimizer._optimize_by_regime(strategy)

        try:
            regime_data = json.loads(regime_data_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            regime_data = {"raw_data": regime_data_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "regime_optimization": regime_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in regime optimization: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/live-recommendations")
async def get_live_strike_recommendations(request: dict):
    """
    Get real-time strike recommendations for current market

    Based on historical performance + current regime, recommend EXACT strikes to use.
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        required = ['spot_price', 'vix_current']
        for field in required:
            if field not in request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        recommendations = optimizer.get_optimal_strikes_for_current_market(request)

        return {
            "success": True,
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting live recommendations: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/greeks")
async def get_greeks_optimization(strategy: str = None):
    """
    Get Greeks optimization analysis

    Shows which Greek ranges perform best (delta, theta, gamma, vega targets).
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        greeks_data_json = optimizer._optimize_greeks(strategy)

        try:
            greeks_data = json.loads(greeks_data_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            greeks_data = {"raw_data": greeks_data_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "greeks_optimization": greeks_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in Greeks optimization: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-combinations")
async def get_best_combinations(strategy: str = None):
    """
    Find winning combinations of conditions

    Examples: "VIX low + Liberation + 5 DTE + 2% OTM = 78% win rate"
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

        from ai.ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        combinations_json = optimizer._find_best_combinations(strategy)

        try:
            combinations_data = json.loads(combinations_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            combinations_data = {"raw_data": combinations_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "best_combinations": combinations_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error finding best combinations: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
