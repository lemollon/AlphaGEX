"""
Psychology Trap Detection API routes.

Handles psychology regime analysis, RSI multi-timeframe analysis,
liberation setups, false floors, and regime notifications.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
import json

from database_adapter import get_connection

router = APIRouter(prefix="/api/psychology", tags=["Psychology"])


@router.get("/current-regime")
async def get_current_regime(symbol: str = "SPY"):
    """
    Get current psychology trap regime analysis

    Returns complete analysis with:
    - Multi-timeframe RSI
    - Current gamma walls
    - Gamma expiration timeline
    - Forward GEX magnets
    - Regime detection with psychology traps
    """
    # Import at runtime to avoid circular imports
    try:
        from core.psychology_trap_detector import analyze_current_market_complete
        from backend.api.dependencies import api_client
        # get_cached_price_data is only in main.py, so we provide a fallback
        try:
            from backend.main import get_cached_price_data
        except ImportError:
            # Fallback function if main.py isn't fully loaded
            def get_cached_price_data(symbol, current_price):
                return {'1d': [], '4h': [], '1h': [], '15m': [], '5m': []}
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Psychology module not available: {e}")

    try:
        # Get current price and gamma data
        gex_data = api_client.get_net_gamma(symbol)

        if not gex_data or 'error' in gex_data:
            error_type = gex_data.get('error', 'unknown') if gex_data else 'no_data'

            # Try cached data
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT spy_price, net_gamma, primary_regime_type, secondary_regime_type,
                           confidence_score, trade_direction, risk_level, description,
                           rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d, timestamp
                    FROM regime_signals
                    WHERE timestamp > NOW() - INTERVAL '24 hours'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                cached_row = cursor.fetchone()
                conn.close()

                if cached_row:
                    cached_response = {
                        "success": True,
                        "data": {
                            "analysis": {
                                "timestamp": str(cached_row[13]),
                                "spy_price": cached_row[0] or 590.0,
                                "regime": {
                                    "primary_type": cached_row[2] or "NEUTRAL",
                                    "secondary_type": cached_row[3],
                                    "confidence": cached_row[4] or 0.7,
                                    "description": cached_row[7] or "Cached analysis",
                                    "trade_direction": cached_row[5] or "NEUTRAL",
                                    "risk_level": cached_row[6] or "MEDIUM",
                                },
                                "rsi_analysis": {
                                    "individual_rsi": {
                                        "5m": cached_row[8],
                                        "15m": cached_row[9],
                                        "1h": cached_row[10],
                                        "4h": cached_row[11],
                                        "1d": cached_row[12]
                                    }
                                }
                            },
                            "market_status": {"is_open": True},
                            "_cached": True
                        }
                    }
                    return JSONResponse(cached_response)
            except Exception:
                pass

            raise HTTPException(status_code=503, detail=f"GEX data unavailable: {error_type}")

        current_price = gex_data.get('spot_price', 0)
        price_data = get_cached_price_data(symbol, current_price)

        # Calculate volume ratio
        volume_ratio = 1.0
        if len(price_data.get('1d', [])) >= 20:
            recent_volume = price_data['1d'][-1].get('volume', 0)
            avg_volume = sum(d.get('volume', 0) for d in price_data['1d'][-20:]) / 20
            volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0

        # Run full analysis
        analysis = analyze_current_market_complete(
            current_price=current_price,
            price_data=price_data,
            gamma_data=gex_data,
            volume_ratio=volume_ratio
        )

        return JSONResponse({
            "success": True,
            "data": {
                "analysis": analysis,
                "market_status": {"is_open": True}
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_regime_history(
    symbol: str = "SPY",
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get historical regime signals"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, spy_price, net_gamma, primary_regime_type,
                   secondary_regime_type, confidence_score, trade_direction,
                   risk_level, description, rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d
            FROM regime_signals
            WHERE timestamp > NOW() - INTERVAL '1 hour' * %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (hours, limit))
        rows = cursor.fetchall()
        conn.close()

        signals = [{
            "id": row[0],
            "timestamp": str(row[1]),
            "spy_price": float(row[2]) if row[2] else None,
            "net_gamma": float(row[3]) if row[3] else None,
            "primary_regime": row[4],
            "secondary_regime": row[5],
            "confidence": float(row[6]) if row[6] else None,
            "trade_direction": row[7],
            "risk_level": row[8],
            "description": row[9],
            "rsi": {
                "5m": float(row[10]) if row[10] else None,
                "15m": float(row[11]) if row[11] else None,
                "1h": float(row[12]) if row[12] else None,
                "4h": float(row[13]) if row[13] else None,
                "1d": float(row[14]) if row[14] else None
            }
        } for row in rows]

        return {"success": True, "data": signals, "signals": signals, "count": len(signals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/liberation-setups")
async def get_liberation_setups(days: int = Query(7, ge=1, le=30)):
    """Get recent liberation setup signals"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Query only columns known to exist
        cursor.execute("""
            SELECT timestamp, spy_price, primary_regime_type,
                   confidence_score, trade_direction, description
            FROM regime_signals
            WHERE primary_regime_type LIKE '%%LIBERATION%%'
            AND timestamp > NOW() - INTERVAL '1 day' * %s
            ORDER BY timestamp DESC
        """, (days,))
        rows = cursor.fetchall()
        conn.close()

        setups = []
        for row in rows:
            setups.append({
                "timestamp": str(row[0]) if row[0] else None,
                "spy_price": float(row[1]) if len(row) > 1 and row[1] else None,
                "regime": row[2] if len(row) > 2 else None,
                "confidence": float(row[3]) if len(row) > 3 and row[3] else None,
                "direction": row[4] if len(row) > 4 else None,
                "description": row[5] if len(row) > 5 else None
            })

        return {"success": True, "data": setups, "liberation_setups": setups, "count": len(setups)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/false-floors")
async def get_false_floors(days: int = Query(7, ge=1, le=30)):
    """Get recent false floor signals"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Query only columns known to exist
        cursor.execute("""
            SELECT timestamp, spy_price, primary_regime_type,
                   confidence_score, trade_direction, description
            FROM regime_signals
            WHERE primary_regime_type LIKE '%%FALSE_FLOOR%%'
            AND timestamp > NOW() - INTERVAL '1 day' * %s
            ORDER BY timestamp DESC
        """, (days,))
        rows = cursor.fetchall()
        conn.close()

        floors = []
        for row in rows:
            floors.append({
                "timestamp": str(row[0]) if row[0] else None,
                "spy_price": float(row[1]) if len(row) > 1 and row[1] else None,
                "regime": row[2] if len(row) > 2 else None,
                "confidence": float(row[3]) if len(row) > 3 and row[3] else None,
                "direction": row[4] if len(row) > 4 else None,
                "description": row[5] if len(row) > 5 else None
            })

        return {"success": True, "data": floors, "false_floors": floors, "count": len(floors)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_regime_statistics(days: int = Query(30, ge=1, le=90)):
    """Get regime distribution statistics"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get regime distribution
        cursor.execute("""
            SELECT primary_regime_type, COUNT(*) as count
            FROM regime_signals
            WHERE timestamp > NOW() - INTERVAL '1 day' * %s
            GROUP BY primary_regime_type
            ORDER BY count DESC
        """, (days,))
        regime_counts = cursor.fetchall()

        # Get average confidence by regime
        cursor.execute("""
            SELECT primary_regime_type, AVG(confidence_score) as avg_confidence
            FROM regime_signals
            WHERE timestamp > NOW() - INTERVAL '1 day' * %s
            GROUP BY primary_regime_type
        """, (days,))
        confidence_by_regime = cursor.fetchall()

        conn.close()

        stats_data = {
            "regime_distribution": {row[0]: row[1] for row in regime_counts},
            "confidence_by_regime": {row[0]: float(row[1]) if row[1] else 0 for row in confidence_by_regime},
            "period_days": days
        }
        return {"success": True, "data": stats_data, **stats_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/overview")
async def get_psychology_performance_overview():
    """Get psychology trading performance overview"""
    try:
        from core.psychology_performance import get_performance_overview
        overview = get_performance_overview()
        return {"success": True, "data": overview, **overview}
    except ImportError:
        return {"success": False, "error": "Psychology performance module not available", "data": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/by-pattern")
@router.get("/performance/patterns")  # Alias for frontend compatibility
async def get_performance_by_pattern():
    """Get performance breakdown by pattern type"""
    try:
        from core.psychology_performance import get_performance_by_pattern
        result = get_performance_by_pattern()
        patterns = result.get('patterns', []) if isinstance(result, dict) else []
        return {"success": True, "data": patterns, "patterns": patterns}
    except ImportError:
        return {"success": False, "patterns": [], "data": [], "error": "Psychology performance module not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/signals")
async def get_psychology_signals(
    limit: int = Query(50, ge=1, le=500),
    pattern_type: Optional[str] = None
):
    """Get recent psychology signals with outcomes"""
    try:
        from core.psychology_performance import get_recent_signals
        result = get_recent_signals(limit=limit, pattern_type=pattern_type)
        signals = result.get('signals', []) if isinstance(result, dict) else []
        return {"success": True, "data": signals, "signals": signals, "count": len(signals)}
    except ImportError:
        return {"success": False, "signals": [], "data": [], "error": "Psychology performance module not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/chart-data")
async def get_chart_data_endpoint(days: int = Query(30, ge=1, le=90)):
    """Get time series data for psychology performance charts"""
    try:
        from core.psychology_performance import get_chart_data
        result = get_chart_data(days=days)
        return {"success": True, "data": result, **result}
    except ImportError:
        return {"success": False, "error": "Psychology performance module not available", "data": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/vix-correlation")
async def get_vix_correlation_endpoint():
    """Get correlation between VIX levels and psychology pattern performance"""
    try:
        from core.psychology_performance import get_vix_correlation
        result = get_vix_correlation()
        return {"success": True, "data": result, **result}
    except ImportError:
        return {"success": False, "error": "Psychology performance module not available", "data": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notifications/stream")
async def stream_notifications():
    """Server-sent events stream for real-time psychology notifications"""
    try:
        from monitoring.psychology_notifications import notification_manager

        async def event_generator():
            while True:
                notification = await notification_manager.get_next_notification()
                if notification:
                    yield f"data: {json.dumps(notification)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Notification service unavailable")


@router.get("/notifications/history")
async def get_notification_history(limit: int = Query(50, ge=1, le=200)):
    """Get recent psychology notifications"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if table exists first
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'psychology_notifications'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            conn.close()
            return {"success": True, "data": [], "notifications": [], "message": "Notifications table not configured"}

        cursor.execute("""
            SELECT id, timestamp, notification_type, regime_type, severity, message, data
            FROM psychology_notifications
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()

        notifications = [{
            "id": row[0],
            "timestamp": str(row[1]),
            "notification_type": row[2],
            "pattern_type": row[3],
            "alert_level": row[4],
            "message": row[5],
            "data": row[6]
        } for row in rows]

        return {"success": True, "data": notifications, "notifications": notifications}
    except Exception as e:
        # Return empty list on any error
        return {"success": True, "data": [], "notifications": [], "error": str(e)}


@router.get("/notifications/stats")
async def get_notification_stats():
    """Get notification statistics"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if table exists first
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'psychology_notifications'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            conn.close()
            return {"success": True, "data": {"stats": {}, "period": "7 days"}, "stats": {}, "period": "7 days"}

        cursor.execute("""
            SELECT regime_type, COUNT(*) as count
            FROM psychology_notifications
            WHERE timestamp > NOW() - INTERVAL '7 days'
            GROUP BY regime_type
        """)
        rows = cursor.fetchall()
        conn.close()

        stats = {row[0]: row[1] for row in rows if row[0]}
        return {"success": True, "data": {"stats": stats, "period": "7 days"}, "stats": stats, "period": "7 days"}
    except Exception as e:
        return {"success": True, "data": {"stats": {}, "period": "7 days"}, "stats": {}, "period": "7 days"}


@router.get("/rsi-analysis/{symbol}")
async def get_rsi_analysis(symbol: str):
    """Get multi-timeframe RSI analysis for symbol"""
    try:
        from core.psychology_trap_detector import MultiTimeframeRSI
        rsi_analyzer = MultiTimeframeRSI()
        analysis = rsi_analyzer.analyze(symbol)
        return {"symbol": symbol, "rsi_analysis": analysis}
    except ImportError:
        raise HTTPException(status_code=503, detail="RSI analysis module not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quick-check/{symbol}")
async def quick_check(symbol: str):
    """Quick psychology regime check without full analysis"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT primary_regime_type, confidence_score, trade_direction,
                   risk_level, spy_price, timestamp
            FROM regime_signals
            WHERE timestamp > NOW() - INTERVAL '1 hour'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "symbol": symbol,
                "regime": row[0],
                "confidence": float(row[1]) if row[1] else None,
                "direction": row[2],
                "risk": row[3],
                "price": float(row[4]) if row[4] else None,
                "timestamp": str(row[5]),
                "fresh": True
            }
        return {"symbol": symbol, "regime": None, "fresh": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
