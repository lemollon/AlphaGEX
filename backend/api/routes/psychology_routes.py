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
        from backend.main import api_client, get_cached_price_data
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
                        "_cached": True
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
            gex_data=gex_data,
            price_data=price_data,
            volume_ratio=volume_ratio,
            save_to_db=True
        )

        return JSONResponse({"analysis": analysis, "market_status": {"is_open": True}})

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
            WHERE timestamp > NOW() - INTERVAL '%s hours'
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

        return {"signals": signals, "count": len(signals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/liberation-setups")
async def get_liberation_setups(days: int = Query(7, ge=1, le=30)):
    """Get recent liberation setup signals"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, spy_price, net_gamma, primary_regime_type,
                   confidence_score, trade_direction, description
            FROM regime_signals
            WHERE primary_regime_type LIKE '%LIBERATION%'
            AND timestamp > NOW() - INTERVAL '%s days'
            ORDER BY timestamp DESC
        """, (days,))
        rows = cursor.fetchall()
        conn.close()

        setups = [{
            "timestamp": str(row[0]),
            "spy_price": float(row[1]) if row[1] else None,
            "net_gamma": float(row[2]) if row[2] else None,
            "regime": row[3],
            "confidence": float(row[4]) if row[4] else None,
            "direction": row[5],
            "description": row[6]
        } for row in rows]

        return {"liberation_setups": setups, "count": len(setups)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/false-floors")
async def get_false_floors(days: int = Query(7, ge=1, le=30)):
    """Get recent false floor signals"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, spy_price, net_gamma, primary_regime_type,
                   confidence_score, trade_direction, description
            FROM regime_signals
            WHERE primary_regime_type LIKE '%FALSE_FLOOR%'
            AND timestamp > NOW() - INTERVAL '%s days'
            ORDER BY timestamp DESC
        """, (days,))
        rows = cursor.fetchall()
        conn.close()

        floors = [{
            "timestamp": str(row[0]),
            "spy_price": float(row[1]) if row[1] else None,
            "net_gamma": float(row[2]) if row[2] else None,
            "regime": row[3],
            "confidence": float(row[4]) if row[4] else None,
            "direction": row[5],
            "description": row[6]
        } for row in rows]

        return {"false_floors": floors, "count": len(floors)}
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
            WHERE timestamp > NOW() - INTERVAL '%s days'
            GROUP BY primary_regime_type
            ORDER BY count DESC
        """, (days,))
        regime_counts = cursor.fetchall()

        # Get average confidence by regime
        cursor.execute("""
            SELECT primary_regime_type, AVG(confidence_score) as avg_confidence
            FROM regime_signals
            WHERE timestamp > NOW() - INTERVAL '%s days'
            GROUP BY primary_regime_type
        """, (days,))
        confidence_by_regime = cursor.fetchall()

        conn.close()

        return {
            "regime_distribution": {row[0]: row[1] for row in regime_counts},
            "confidence_by_regime": {row[0]: float(row[1]) if row[1] else 0 for row in confidence_by_regime},
            "period_days": days
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/overview")
async def get_psychology_performance_overview():
    """Get psychology trading performance overview"""
    try:
        from core.psychology_performance import get_performance_overview
        overview = get_performance_overview()
        return overview
    except ImportError:
        return {"error": "Psychology performance module not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/by-pattern")
async def get_performance_by_pattern():
    """Get performance breakdown by pattern type"""
    try:
        from core.psychology_performance import get_performance_by_pattern
        return get_performance_by_pattern()
    except ImportError:
        return {"error": "Psychology performance module not available"}
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
        return get_recent_signals(limit=limit, pattern_type=pattern_type)
    except ImportError:
        return {"signals": [], "error": "Psychology performance module not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/chart-data")
async def get_chart_data(days: int = Query(30, ge=1, le=90)):
    """Get time series data for psychology performance charts"""
    try:
        from core.psychology_performance import get_chart_data
        return get_chart_data(days=days)
    except ImportError:
        return {"error": "Psychology performance module not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/vix-correlation")
async def get_vix_correlation():
    """Get correlation between VIX levels and psychology pattern performance"""
    try:
        from core.psychology_performance import get_vix_correlation
        return get_vix_correlation()
    except ImportError:
        return {"error": "Psychology performance module not available"}
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
        cursor.execute("""
            SELECT id, timestamp, pattern_type, alert_level, message, spy_price
            FROM psychology_notifications
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()

        notifications = [{
            "id": row[0],
            "timestamp": str(row[1]),
            "pattern_type": row[2],
            "alert_level": row[3],
            "message": row[4],
            "spy_price": float(row[5]) if row[5] else None
        } for row in rows]

        return {"notifications": notifications}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notifications/stats")
async def get_notification_stats():
    """Get notification statistics"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pattern_type, COUNT(*) as count
            FROM psychology_notifications
            WHERE timestamp > NOW() - INTERVAL '7 days'
            GROUP BY pattern_type
        """)
        rows = cursor.fetchall()
        conn.close()

        return {"stats": {row[0]: row[1] for row in rows}, "period": "7 days"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
