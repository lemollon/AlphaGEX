"""
Autonomous Trader API Endpoints
Provides REST APIs for all autonomous trader features
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import sys
import os
import psycopg2.extras

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

# Create router
router = APIRouter(prefix="/api/autonomous", tags=["Autonomous Trader"])


# ============================================================================
# AUTONOMOUS TRADER LOGS
# ============================================================================

@router.get("/logs")
async def get_autonomous_logs(
    limit: int = Query(20, ge=1, le=100),
    log_type: Optional[str] = None,
    session_id: Optional[str] = None,
    symbol: Optional[str] = None
):
    """
    Get autonomous trader logs with AI thought process

    Shows:
    - Psychology scan results
    - AI strike selection reasoning
    - Position sizing decisions
    - ML predictions
    - Risk manager decisions
    - Trade executions
    """
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = "SELECT * FROM autonomous_trader_logs WHERE 1=1"
        params = []

        if log_type:
            query += " AND log_type = ?"
            params.append(log_type)

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        c.execute(query, params)
        logs = [dict(row) for row in c.fetchall()]
        conn.close()

        return {
            'success': True,
            'data': logs,
            'count': len(logs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/sessions")
async def get_log_sessions(limit: int = Query(10, ge=1, le=50)):
    """Get list of recent autonomous trader sessions"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute("""
            SELECT
                session_id,
                MIN(timestamp) as start_time,
                MAX(timestamp) as end_time,
                COUNT(*) as log_count,
                COUNT(DISTINCT scan_cycle) as scan_cycles
            FROM autonomous_trader_logs
            WHERE session_id IS NOT NULL
            GROUP BY session_id
            ORDER BY start_time DESC
            LIMIT ?
        """, (limit,))

        sessions = [dict(row) for row in c.fetchall()]
        conn.close()

        return {
            'success': True,
            'data': sessions
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STRATEGY COMPETITION
# ============================================================================

@router.get("/competition/leaderboard")
async def get_competition_leaderboard():
    """
    Get strategy competition leaderboard

    8 strategies competing with equal capital:
    1. Psychology Trap + Liberation
    2. Pure GEX Regime
    3. RSI + Gamma Walls
    4. Liberation Only
    5. Forward GEX Magnets
    6. Conservative
    7. Aggressive
    8. AI-Only (Claude decisions)
    """
    try:
        from autonomous_strategy_competition import get_competition

        competition = get_competition()
        leaderboard = competition.get_leaderboard()

        return {
            'success': True,
            'data': leaderboard,
            'count': len(leaderboard)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competition/strategy/{strategy_id}")
async def get_strategy_performance(strategy_id: str):
    """Get detailed performance for a specific strategy"""
    try:
        from autonomous_strategy_competition import get_competition

        competition = get_competition()
        performance = competition.get_strategy_performance(strategy_id)

        if not performance:
            raise HTTPException(status_code=404, detail="Strategy not found")

        return {
            'success': True,
            'data': performance
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competition/summary")
async def get_competition_summary():
    """Get competition summary with best/worst strategies"""
    try:
        from autonomous_strategy_competition import get_competition

        competition = get_competition()
        summary = competition.get_comparison_summary()

        return {
            'success': True,
            'data': summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SIGNAL-ONLY MODE (No Auto-Execution)
# ============================================================================

@router.get("/signal")
async def get_entry_signal():
    """
    Generate entry signal WITHOUT executing a trade (Signal-Only Mode).

    Perfect for users with 15-minute delayed option data who want to:
    1. See trade recommendations
    2. Get entry price guidance with delay buffer
    3. Manually execute in their broker

    Returns:
    - Trade setup (strategy, strike, option type)
    - Pricing with delayed data handling:
      - displayed_mid: The 15-min delayed price shown
      - estimated_low/high: Likely current price range
      - spread_buffer_pct: Buffer % to account for delay
    - Entry recommendation text
    - Delay warning if data is delayed
    """
    try:
        from autonomous_paper_trader import AutonomousPaperTrader
        from trading_volatility_api import TradingVolatilityAPI

        trader = AutonomousPaperTrader()
        api_client = TradingVolatilityAPI()

        signal = trader.generate_entry_signal(api_client)

        if signal and signal.get('error'):
            return {
                'success': False,
                'error': signal.get('error'),
                'recommendation': signal.get('recommendation', 'Wait for better conditions')
            }

        if not signal or signal.get('signal') is None:
            return {
                'success': True,
                'has_signal': False,
                'reason': signal.get('reason', 'No setup found') if signal else 'No setup found',
                'market_summary': signal.get('market_summary', '') if signal else '',
                'recommendation': signal.get('recommendation', 'Wait for better conditions') if signal else 'Wait'
            }

        return {
            'success': True,
            'has_signal': True,
            'signal': signal
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signal/mode")
async def get_signal_mode():
    """Check if signal-only mode is enabled"""
    try:
        from autonomous_paper_trader import AutonomousPaperTrader

        trader = AutonomousPaperTrader()
        is_signal_only = trader.is_signal_only_mode()

        return {
            'success': True,
            'signal_only_mode': is_signal_only,
            'description': 'When enabled, generates signals without auto-execution'
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signal/mode")
async def set_signal_mode(enabled: bool = True):
    """Enable or disable signal-only mode"""
    try:
        from autonomous_paper_trader import AutonomousPaperTrader

        trader = AutonomousPaperTrader()
        trader.set_signal_only_mode(enabled)

        return {
            'success': True,
            'signal_only_mode': enabled,
            'message': f"Signal-only mode {'enabled' if enabled else 'disabled'}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-status")
async def get_data_status():
    """
    Check Polygon.io subscription tier and data delay status.

    Returns whether option data is real-time (OK) or delayed (DELAYED).
    Options Developer plan = 15-minute delayed data.
    """
    try:
        from polygon_data_fetcher import detect_subscription_tier

        tier_info = detect_subscription_tier()

        return {
            'success': True,
            'data': tier_info,
            'delay_info': {
                'options_delayed': tier_info.get('options_status') == 'DELAYED',
                'delay_minutes': 15 if tier_info.get('options_status') == 'DELAYED' else 0,
                'warning': '⏱️ Options data is 15 minutes delayed. Entry prices will differ from displayed prices.' if tier_info.get('options_status') == 'DELAYED' else None
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BACKTEST RESULTS
# ============================================================================

@router.get("/backtests/all-patterns")
async def get_all_pattern_backtests(lookback_days: int = Query(90, ge=7, le=365)):
    """
    Run backtest on all psychology trap patterns

    Returns ranked results by expectancy
    """
    try:
        from autonomous_backtest_engine import get_backtester

        backtester = get_backtester()
        results = backtester.backtest_all_patterns(lookback_days=lookback_days)

        return {
            'success': True,
            'data': results,
            'count': len(results)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtests/pattern/{pattern_name}")
async def get_pattern_backtest(pattern_name: str, lookback_days: int = Query(90, ge=7, le=365)):
    """Get backtest results for specific pattern"""
    try:
        from autonomous_backtest_engine import get_backtester

        backtester = get_backtester()
        result = backtester.backtest_pattern(pattern_name, lookback_days=lookback_days)

        return {
            'success': True,
            'data': result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtests/liberation-accuracy")
async def get_liberation_accuracy(lookback_days: int = Query(90, ge=7, le=365)):
    """Analyze liberation setup accuracy"""
    try:
        from autonomous_backtest_engine import get_backtester

        backtester = get_backtester()
        analysis = backtester.analyze_liberation_accuracy(lookback_days=lookback_days)

        return {
            'success': True,
            'data': analysis
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtests/false-floor-effectiveness")
async def get_false_floor_effectiveness(lookback_days: int = Query(90, ge=7, le=365)):
    """Analyze false floor detection effectiveness"""
    try:
        from autonomous_backtest_engine import get_backtester

        backtester = get_backtester()
        analysis = backtester.analyze_false_floor_effectiveness(lookback_days=lookback_days)

        return {
            'success': True,
            'data': analysis
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RISK MANAGEMENT
# ============================================================================

@router.get("/risk/status")
async def get_risk_status():
    """
    Get current risk management status

    Returns:
    - Current drawdown vs 15% limit
    - Daily loss vs 5% limit
    - Position size vs 20% limit
    - Correlation vs 50% limit
    - Sharpe ratio
    - Performance metrics
    """
    try:
        from autonomous_risk_manager import get_risk_manager

        risk_manager = get_risk_manager()

        # Get performance metrics
        metrics = risk_manager.get_performance_metrics(days=30)

        # Get current equity values
        current_value = risk_manager._get_current_equity()
        peak_value = risk_manager._get_peak_equity()
        start_of_day_value = risk_manager._get_start_of_day_equity()

        # Calculate current usage of limits
        current_drawdown_pct = ((peak_value - current_value) / peak_value * 100) if peak_value > 0 else 0
        daily_loss_pct = ((start_of_day_value - current_value) / start_of_day_value * 100) if start_of_day_value > 0 else 0

        # Get open positions to calculate exposure
        open_positions = risk_manager._get_open_positions()
        total_exposure = sum(
            pos['unrealized_pnl'] + (pos['entry_price'] * pos['contracts'] * 100)
            for pos in open_positions
        ) if open_positions else 0

        position_size_pct = (total_exposure / current_value * 100) if current_value > 0 else 0

        return {
            'success': True,
            'data': {
                **metrics,
                'current_drawdown_pct': current_drawdown_pct,
                'daily_loss_pct': daily_loss_pct,
                'position_size_pct': position_size_pct,
                'correlation_pct': 0,  # TODO: Calculate actual correlation
                'current_equity': current_value,
                'peak_equity': peak_value,
                'limits': {
                    'max_drawdown': risk_manager.max_drawdown_pct,
                    'daily_loss': risk_manager.daily_loss_limit_pct,
                    'position_size': risk_manager.position_size_limit_pct,
                    'correlation': risk_manager.correlation_limit * 100
                },
                'status': {
                    'max_drawdown': 'HEALTHY' if current_drawdown_pct < risk_manager.max_drawdown_pct else 'BREACH',
                    'daily_loss': 'HEALTHY' if daily_loss_pct < risk_manager.daily_loss_limit_pct else 'BREACH',
                    'position_size': 'HEALTHY' if position_size_pct < risk_manager.position_size_limit_pct else 'BREACH',
                    'correlation': 'HEALTHY'
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk/metrics")
async def get_risk_metrics(days: int = Query(30, ge=1, le=365)):
    """Get detailed risk metrics over time period"""
    try:
        from autonomous_risk_manager import get_risk_manager

        risk_manager = get_risk_manager()
        metrics = risk_manager.get_performance_metrics(days=days)

        return {
            'success': True,
            'data': metrics
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ML PATTERN LEARNING
# ============================================================================

@router.get("/ml/model-status")
async def get_ml_model_status():
    """Get ML model training status and metrics"""
    try:
        from autonomous_ml_pattern_learner import get_pattern_learner, ML_AVAILABLE

        if not ML_AVAILABLE:
            return {
                'success': True,
                'data': {
                    'available': False,
                    'message': 'scikit-learn not installed'
                }
            }

        ml_learner = get_pattern_learner()

        is_trained = ml_learner.model is not None

        return {
            'success': True,
            'data': {
                'available': True,
                'trained': is_trained,
                'feature_importance': ml_learner.feature_importance if is_trained else {},
                'message': 'Model trained and ready' if is_trained else 'Model not yet trained'
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ml/train")
async def train_ml_model(lookback_days: int = Query(180, ge=30, le=365)):
    """Train ML model on historical data"""
    try:
        from autonomous_ml_pattern_learner import get_pattern_learner, ML_AVAILABLE

        if not ML_AVAILABLE:
            raise HTTPException(status_code=400, detail="scikit-learn not installed")

        ml_learner = get_pattern_learner()
        results = ml_learner.train_pattern_classifier(lookback_days=lookback_days)

        if results.get('error'):
            raise HTTPException(status_code=400, detail=results['error'])

        # Save model after training
        ml_learner.save_model()

        return {
            'success': True,
            'data': results
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml/predictions/recent")
async def get_recent_ml_predictions(limit: int = Query(20, ge=1, le=100)):
    """Get recent ML predictions from logs"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute("""
            SELECT
                timestamp,
                symbol,
                pattern_detected,
                confidence_score,
                ai_confidence,
                ai_thought_process
            FROM autonomous_trader_logs
            WHERE log_type = 'AI_EVALUATION'
            AND ai_confidence IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

        predictions = [dict(row) for row in c.fetchall()]
        conn.close()

        return {
            'success': True,
            'data': predictions
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SYSTEM INITIALIZATION
# ============================================================================

@router.post("/initialize")
async def initialize_autonomous_system():
    """
    Initialize autonomous trader system

    Runs:
    - Backtests on all patterns
    - ML model training
    - Strategy competition initialization
    """
    try:
        results = {
            'backtests': {},
            'ml_training': {},
            'competition': {}
        }

        # 1. Run backtests
        try:
            from autonomous_backtest_engine import get_backtester
            backtester = get_backtester()
            backtest_results = backtester.backtest_all_patterns(lookback_days=90)
            results['backtests'] = {
                'success': True,
                'patterns_tested': len(backtest_results)
            }
        except Exception as e:
            results['backtests'] = {
                'success': False,
                'error': str(e)
            }

        # 2. Train ML model
        try:
            from autonomous_ml_pattern_learner import get_pattern_learner, ML_AVAILABLE
            if ML_AVAILABLE:
                ml_learner = get_pattern_learner()
                training_results = ml_learner.train_pattern_classifier(lookback_days=180)
                if not training_results.get('error'):
                    ml_learner.save_model()
                    results['ml_training'] = {
                        'success': True,
                        **training_results
                    }
                else:
                    results['ml_training'] = {
                        'success': False,
                        'error': training_results['error']
                    }
            else:
                results['ml_training'] = {
                    'success': False,
                    'error': 'scikit-learn not available'
                }
        except Exception as e:
            results['ml_training'] = {
                'success': False,
                'error': str(e)
            }

        # 3. Initialize competition
        try:
            from autonomous_strategy_competition import get_competition
            competition = get_competition()
            results['competition'] = {
                'success': True,
                'strategies': len(competition.strategies)
            }
        except Exception as e:
            results['competition'] = {
                'success': False,
                'error': str(e)
            }

        return {
            'success': True,
            'data': results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def autonomous_health_check():
    """Check health of all autonomous trader components"""
    try:
        health = {
            'database_logger': False,
            'ai_reasoning': False,
            'risk_manager': False,
            'ml_learner': False,
            'competition': False,
            'backtester': False
        }

        # Check database logger
        try:
            from autonomous_database_logger import get_database_logger
            logger = get_database_logger('health_check')
            health['database_logger'] = True
        except:
            pass

        # Check AI reasoning
        try:
            from autonomous_ai_reasoning import get_ai_reasoning
            ai = get_ai_reasoning()
            health['ai_reasoning'] = ai is not None
        except:
            pass

        # Check risk manager
        try:
            from autonomous_risk_manager import get_risk_manager
            risk_mgr = get_risk_manager()
            health['risk_manager'] = risk_mgr is not None
        except:
            pass

        # Check ML learner
        try:
            from autonomous_ml_pattern_learner import get_pattern_learner, ML_AVAILABLE
            health['ml_learner'] = ML_AVAILABLE
        except:
            pass

        # Check competition
        try:
            from autonomous_strategy_competition import get_competition
            comp = get_competition()
            health['competition'] = comp is not None
        except:
            pass

        # Check backtester
        try:
            from autonomous_backtest_engine import get_backtester
            bt = get_backtester()
            health['backtester'] = bt is not None
        except:
            pass

        all_healthy = all(health.values())

        return {
            'success': True,
            'healthy': all_healthy,
            'components': health
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
