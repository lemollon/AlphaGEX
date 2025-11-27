"""
Alerts API routes - Price and GEX alerts management.
"""

from fastapi import APIRouter, HTTPException

from api.dependencies import api_client, get_connection

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@router.post("/create")
async def create_alert(request: dict):
    """
    Create a new alert
    Request body:
    {
        "symbol": "SPY",
        "alert_type": "price" | "net_gex" | "flip_point",
        "condition": "above" | "below" | "crosses_above" | "crosses_below",
        "threshold": 600.0,
        "message": "Optional custom message"
    }
    """
    try:
        symbol = request.get('symbol', 'SPY').upper()
        alert_type = request.get('alert_type')
        condition = request.get('condition')
        threshold = request.get('threshold')
        message = request.get('message', '')

        if not all([alert_type, condition, threshold]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Generate default message if not provided
        if not message:
            if alert_type == 'price':
                message = f"{symbol} price {condition} ${threshold}"
            elif alert_type == 'net_gex':
                message = f"{symbol} Net GEX {condition} ${threshold/1e9:.1f}B"
            elif alert_type == 'flip_point':
                message = f"{symbol} {condition} flip point at ${threshold}"

        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            INSERT INTO alerts (symbol, alert_type, condition, threshold, message)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (symbol, alert_type, condition, threshold, message))

        alert_id = c.fetchone()[0]
        conn.commit()
        conn.close()

        return {
            "success": True,
            "alert_id": alert_id,
            "message": "Alert created successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_alerts(status: str = 'active'):
    """Get all alerts with specified status"""
    try:
        import pandas as pd

        conn = get_connection()

        alerts = pd.read_sql_query("""
            SELECT * FROM alerts
            WHERE status = %s
            ORDER BY created_at DESC
        """, conn, params=(status,))

        conn.close()

        return {
            "success": True,
            "data": alerts.to_dict('records') if not alerts.empty else []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{alert_id}")
async def delete_alert(alert_id: int):
    """Delete an alert"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('DELETE FROM alerts WHERE id = %s', (alert_id,))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Alert deleted successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check")
async def check_alerts():
    """
    Check all active alerts against current market data
    This endpoint should be called periodically (e.g., every minute)
    """
    try:
        import pandas as pd

        conn = get_connection()

        # Get all active alerts
        alerts = pd.read_sql_query("""
            SELECT * FROM alerts
            WHERE status = 'active'
        """, conn)

        triggered_alerts = []

        for _, alert in alerts.iterrows():
            symbol = alert['symbol']
            alert_type = alert['alert_type']
            condition = alert['condition']
            threshold = alert['threshold']

            # Fetch current market data
            gex_data = api_client.get_net_gamma(symbol)
            spot_price = gex_data.get('spot_price', 0)
            net_gex = gex_data.get('net_gex', 0)
            flip_point = gex_data.get('flip_point', 0)

            triggered = False
            actual_value = 0

            # Check conditions
            if alert_type == 'price':
                actual_value = spot_price
                if condition == 'above' and spot_price > threshold:
                    triggered = True
                elif condition == 'below' and spot_price < threshold:
                    triggered = True

            elif alert_type == 'net_gex':
                actual_value = net_gex
                if condition == 'above' and net_gex > threshold:
                    triggered = True
                elif condition == 'below' and net_gex < threshold:
                    triggered = True

            elif alert_type == 'flip_point':
                actual_value = spot_price
                if condition == 'crosses_above' and spot_price > flip_point:
                    triggered = True
                elif condition == 'crosses_below' and spot_price < flip_point:
                    triggered = True

            if triggered:
                # Mark alert as triggered
                c = conn.cursor()
                c.execute('''
                    UPDATE alerts
                    SET status = 'triggered', triggered_at = CURRENT_TIMESTAMP, triggered_value = %s
                    WHERE id = %s
                ''', (actual_value, alert['id']))

                # Add to alert history
                c.execute('''
                    INSERT INTO alert_history (
                        alert_id, symbol, alert_type, condition, threshold,
                        actual_value, message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    alert['id'], symbol, alert_type, condition,
                    threshold, actual_value, alert['message']
                ))

                conn.commit()

                triggered_alerts.append({
                    'id': alert['id'],
                    'symbol': symbol,
                    'message': alert['message'],
                    'actual_value': actual_value,
                    'threshold': threshold
                })

        conn.close()

        return {
            "success": True,
            "checked": len(alerts),
            "triggered": len(triggered_alerts),
            "alerts": triggered_alerts
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_alert_history(limit: int = 50):
    """Get alert trigger history"""
    try:
        import pandas as pd

        conn = get_connection()

        history = pd.read_sql_query(f"""
            SELECT * FROM alert_history
            ORDER BY triggered_at DESC
            LIMIT {int(limit)}
        """, conn)

        conn.close()

        return {
            "success": True,
            "data": history.to_dict('records') if not history.empty else []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
