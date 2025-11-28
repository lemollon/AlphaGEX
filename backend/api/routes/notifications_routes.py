"""
Push Notifications API routes.

Handles web push notification subscription, management, and testing.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database_adapter import get_connection

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


class SubscriptionData(BaseModel):
    endpoint: str
    keys: dict
    user_agent: Optional[str] = None


class NotificationPreferences(BaseModel):
    liberation_alerts: bool = True
    false_floor_alerts: bool = True
    regime_change_alerts: bool = True
    price_alerts: bool = True
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Get VAPID public key for push notification subscription"""
    try:
        from backend.push_notification_service import get_push_service
        push_service = get_push_service()
        return {"vapid_public_key": push_service.vapid_public_key}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Push service unavailable: {e}")


@router.post("/subscribe")
async def subscribe_notifications(subscription: SubscriptionData):
    """Subscribe to push notifications"""
    try:
        from backend.push_notification_service import get_push_service
        push_service = get_push_service()

        subscription_id = push_service.add_subscription(
            endpoint=subscription.endpoint,
            keys=subscription.keys,
            user_agent=subscription.user_agent
        )

        return {
            "success": True,
            "subscription_id": subscription_id,
            "message": "Subscribed to push notifications"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unsubscribe")
async def unsubscribe_notifications(subscription: SubscriptionData):
    """Unsubscribe from push notifications"""
    try:
        from backend.push_notification_service import get_push_service
        push_service = get_push_service()

        success = push_service.remove_subscription(subscription.endpoint)

        if success:
            return {"success": True, "message": "Unsubscribed from push notifications"}
        raise HTTPException(status_code=404, detail="Subscription not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/preferences")
async def update_preferences(preferences: NotificationPreferences, endpoint: str = Query(...)):
    """Update notification preferences for a subscription"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE push_subscriptions
            SET preferences = %s, updated_at = NOW()
            WHERE endpoint = %s
            RETURNING id
        """, (preferences.dict(), endpoint))
        result = cursor.fetchone()
        conn.commit()
        conn.close()

        if result:
            return {"success": True, "message": "Preferences updated"}
        raise HTTPException(status_code=404, detail="Subscription not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def send_test_notification(endpoint: str = Query(...)):
    """Send a test push notification"""
    try:
        from backend.push_notification_service import get_push_service
        push_service = get_push_service()

        success = push_service.send_notification(
            endpoint=endpoint,
            title="Test Notification",
            body="Push notifications are working correctly!",
            data={"type": "test"}
        )

        if success:
            return {"success": True, "message": "Test notification sent"}
        raise HTTPException(status_code=500, detail="Failed to send test notification")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions")
async def list_subscriptions():
    """List all push notification subscriptions (admin)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, endpoint, user_agent, created_at, last_success, failure_count
            FROM push_subscriptions
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        subscriptions = [{
            "id": row[0],
            "endpoint": row[1][:50] + "..." if len(row[1]) > 50 else row[1],
            "user_agent": row[2],
            "created_at": str(row[3]),
            "last_success": str(row[4]) if row[4] else None,
            "failure_count": row[5]
        } for row in rows]

        return {"subscriptions": subscriptions, "count": len(subscriptions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/subscription/{subscription_id}")
async def delete_subscription(subscription_id: int):
    """Delete a push notification subscription"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM push_subscriptions
            WHERE id = %s
            RETURNING id
        """, (subscription_id,))
        deleted = cursor.fetchone()
        conn.commit()
        conn.close()

        if deleted:
            return {"success": True, "message": f"Subscription {subscription_id} deleted"}
        raise HTTPException(status_code=404, detail="Subscription not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
