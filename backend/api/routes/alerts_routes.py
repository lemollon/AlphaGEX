"""
Alerts API routes.

Handles price alerts creation, listing, deletion, and checking.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database_adapter import get_connection

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


class AlertCreate(BaseModel):
    symbol: str
    alert_type: str  # 'price_above', 'price_below', 'gex_flip', 'regime_change'
    condition_value: float
    message: Optional[str] = None


@router.post("/create")
async def create_alert(alert: AlertCreate):
    """Create a new price or GEX alert"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO price_alerts (symbol, alert_type, condition_value, message, active, created_at)
            VALUES (%s, %s, %s, %s, true, NOW())
            RETURNING id
        """, (alert.symbol, alert.alert_type, alert.condition_value, alert.message))
        alert_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        return {
            "success": True,
            "alert_id": alert_id,
            "message": f"Alert created for {alert.symbol}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_alerts(active_only: bool = True):
    """List all alerts"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        if active_only:
            cursor.execute("""
                SELECT id, symbol, alert_type, condition_value, message, active, created_at, triggered_at
                FROM price_alerts
                WHERE active = true
                ORDER BY created_at DESC
            """)
        else:
            cursor.execute("""
                SELECT id, symbol, alert_type, condition_value, message, active, created_at, triggered_at
                FROM price_alerts
                ORDER BY created_at DESC
            """)

        rows = cursor.fetchall()
        conn.close()

        alerts = [{
            "id": row[0],
            "symbol": row[1],
            "alert_type": row[2],
            "condition_value": float(row[3]) if row[3] else None,
            "message": row[4],
            "active": row[5],
            "created_at": str(row[6]),
            "triggered_at": str(row[7]) if row[7] else None
        } for row in rows]

        return {"alerts": alerts, "count": len(alerts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{alert_id}")
async def delete_alert(alert_id: int):
    """Delete an alert"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM price_alerts WHERE id = %s RETURNING id", (alert_id,))
        deleted = cursor.fetchone()
        conn.commit()
        conn.close()

        if deleted:
            return {"success": True, "message": f"Alert {alert_id} deleted"}
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check")
async def check_alerts():
    """Check and trigger any alerts that match current conditions"""
    try:
        # Import at runtime to avoid circular imports
        from backend.main import api_client

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, symbol, alert_type, condition_value, message
            FROM price_alerts
            WHERE active = true
        """)
        alerts = cursor.fetchall()

        triggered = []

        for alert in alerts:
            alert_id, symbol, alert_type, condition_value, message = alert

            # Get current price
            gex_data = api_client.get_net_gamma(symbol)
            if not gex_data or 'error' in gex_data:
                continue

            current_price = gex_data.get('spot_price', 0)
            should_trigger = False

            if alert_type == 'price_above' and current_price >= condition_value:
                should_trigger = True
            elif alert_type == 'price_below' and current_price <= condition_value:
                should_trigger = True

            if should_trigger:
                cursor.execute("""
                    UPDATE price_alerts
                    SET active = false, triggered_at = NOW()
                    WHERE id = %s
                """, (alert_id,))
                triggered.append({
                    "id": alert_id,
                    "symbol": symbol,
                    "type": alert_type,
                    "condition": condition_value,
                    "current_price": current_price,
                    "message": message
                })

        conn.commit()
        conn.close()

        return {"triggered": triggered, "count": len(triggered)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_alert_history(days: int = Query(7, ge=1, le=30)):
    """Get triggered alert history"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, symbol, alert_type, condition_value, message, triggered_at
            FROM price_alerts
            WHERE triggered_at IS NOT NULL
            AND triggered_at > NOW() - INTERVAL '%s days'
            ORDER BY triggered_at DESC
        """, (days,))
        rows = cursor.fetchall()
        conn.close()

        history = [{
            "id": row[0],
            "symbol": row[1],
            "type": row[2],
            "condition": float(row[3]) if row[3] else None,
            "message": row[4],
            "triggered_at": str(row[5])
        } for row in rows]

        return {"history": history, "count": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
