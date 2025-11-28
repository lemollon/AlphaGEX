"""
Push Notification API routes - Browser push notification management.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

# Import push notification service
try:
    import sys
    from pathlib import Path
    backend_dir = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(backend_dir))
    from push_notification_service import get_push_service
    push_service = get_push_service()
    push_notifications_available = True
except Exception as e:
    print(f"⚠️ Push notifications not available in route module: {e}")
    push_service = None
    push_notifications_available = False


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """
    Get VAPID public key for push notification subscriptions
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    public_key = push_service.get_vapid_public_key()

    if not public_key:
        raise HTTPException(status_code=500, detail="VAPID key not available")

    return {
        "success": True,
        "public_key": public_key
    }


@router.post("/subscribe")
async def subscribe_to_push_notifications(request: dict):
    """
    Subscribe to push notifications

    Request body:
    {
        "subscription": {
            "endpoint": "https://...",
            "keys": {"p256dh": "...", "auth": "..."}
        },
        "preferences": {
            "enabled": true,
            "criticalAlerts": true,
            ...
        }
    }
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        subscription = request.get('subscription')
        preferences = request.get('preferences', {})

        if not subscription:
            raise HTTPException(status_code=400, detail="Subscription object required")

        success = push_service.save_subscription(subscription, preferences)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save subscription")

        return {
            "success": True,
            "message": "Subscription saved successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error subscribing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unsubscribe")
async def unsubscribe_from_push_notifications(request: dict):
    """
    Unsubscribe from push notifications
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        endpoint = request.get('endpoint')

        if not endpoint:
            raise HTTPException(status_code=400, detail="Endpoint required")

        success = push_service.remove_subscription(endpoint)

        return {
            "success": True,
            "message": "Unsubscribed successfully" if success else "Subscription not found"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error unsubscribing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/preferences")
async def update_notification_preferences(request: dict):
    """
    Update notification preferences
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        endpoint = request.get('endpoint')
        preferences = request.get('preferences', {})

        if not preferences:
            raise HTTPException(status_code=400, detail="Preferences required")

        # If no endpoint provided, update first subscription (single-user mode)
        if not endpoint:
            subscriptions = push_service.get_all_subscriptions()
            if not subscriptions:
                raise HTTPException(status_code=404, detail="No subscriptions found")
            endpoint = subscriptions[0]['endpoint']

        success = push_service.update_preferences(endpoint, preferences)

        if not success:
            raise HTTPException(status_code=404, detail="Subscription not found")

        return {
            "success": True,
            "message": "Preferences updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def send_test_notification():
    """
    Send test push notification to all subscribed users
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        stats = push_service.broadcast_notification(
            title="Test Alert",
            body="This is a test notification from AlphaGEX",
            alert_level="HIGH",
            data={"type": "test"}
        )

        return {
            "success": True,
            "message": "Test notification sent",
            "stats": stats
        }

    except Exception as e:
        print(f"❌ Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions")
async def get_subscriptions():
    """Get all push notification subscriptions"""
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        subscriptions = push_service.get_all_subscriptions()
        return {
            "success": True,
            "subscriptions": subscriptions,
            "total": len(subscriptions)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/subscription/{subscription_id}")
async def delete_subscription(subscription_id: str):
    """Delete a specific subscription"""
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        success = push_service.remove_subscription_by_id(subscription_id)
        return {
            "success": success,
            "message": "Subscription deleted" if success else "Subscription not found"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
