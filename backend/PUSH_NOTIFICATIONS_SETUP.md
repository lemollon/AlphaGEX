# Push Notifications Setup Guide

## Overview

AlphaGEX supports browser push notifications for real-time alerts about critical market events, liberation setups, false floors, and regime changes.

## Prerequisites

### Python Dependencies

Install the required Python packages:

```bash
pip install pywebpush py-vapid
```

Or add to your `requirements.txt`:
```
pywebpush>=1.14.0
py-vapid>=1.9.0
```

## Setup Steps

### 1. Generate VAPID Keys (Automatic)

VAPID keys are automatically generated on first run. The keys will be stored in:
- `/home/user/AlphaGEX/backend/vapid_private_key.pem`
- `/home/user/AlphaGEX/backend/vapid_public_key.pem`

**IMPORTANT:** Keep these keys secure and backed up. They authenticate your push notifications.

### 2. Set VAPID Email (Optional)

Set the email address to be used in VAPID claims:

```bash
export VAPID_EMAIL="mailto:admin@alphagex.com"
```

Or add to your `.env` file:
```
VAPID_EMAIL=mailto:admin@alphagex.com
```

### 3. Start Backend Server

```bash
cd backend
python main.py
```

The server will:
- Load or generate VAPID keys
- Initialize the push_subscriptions database table
- Expose push notification API endpoints

### 4. Enable Notifications in Frontend

1. Open AlphaGEX web app
2. Navigate to Settings → Notifications
3. Click "Enable Notifications"
4. Grant browser permission when prompted
5. Configure your alert preferences

## API Endpoints

### Get VAPID Public Key
```
GET /api/notifications/vapid-public-key
```

Returns the public key needed for browser subscriptions.

### Subscribe to Notifications
```
POST /api/notifications/subscribe
Content-Type: application/json

{
  "subscription": {
    "endpoint": "https://fcm.googleapis.com/fcm/send/...",
    "keys": {
      "p256dh": "...",
      "auth": "..."
    }
  },
  "preferences": {
    "enabled": true,
    "criticalAlerts": true,
    "highAlerts": true,
    "liberationSetups": true,
    "falseFloors": true,
    "regimeChanges": true,
    "sound": true
  }
}
```

### Update Preferences
```
PUT /api/notifications/preferences
Content-Type: application/json

{
  "preferences": {
    "enabled": true,
    "criticalAlerts": true,
    ...
  }
}
```

### Unsubscribe
```
POST /api/notifications/unsubscribe
Content-Type: application/json

{
  "endpoint": "https://fcm.googleapis.com/fcm/send/..."
}
```

### Send Test Notification
```
POST /api/notifications/test
```

Broadcasts a test notification to all subscribed users.

## Integration with Psychology Trap Detector

To automatically send push notifications when alerts fire, integrate with the psychology trap detector:

```python
from push_notification_service import get_push_service

push_service = get_push_service()

# Send notification for liberation setup
push_service.broadcast_notification(
    title="Liberation Setup Detected",
    body=f"SPY gamma wall at ${strike} expires in {days} days",
    alert_level="HIGH",
    alert_type="liberation",
    data={
        "symbol": "SPY",
        "strike": strike,
        "expiration": expiration_date
    }
)

# Send notification for regime change
push_service.broadcast_notification(
    title="CRITICAL Regime Change",
    body="Market flipped from Long Gamma to Short Gamma - High volatility expected",
    alert_level="CRITICAL",
    alert_type="regime_change",
    data={
        "regime": "SHORT_GAMMA"
    }
)
```

## Browser Compatibility

Push notifications are supported in:
- ✅ Chrome 50+
- ✅ Firefox 44+
- ✅ Edge 17+
- ✅ Opera 42+
- ✅ Safari 16+ (macOS 13+, iOS 16.4+)

**Not supported:**
- ❌ Internet Explorer
- ❌ Safari < 16
- ❌ iOS Safari < 16.4

## Database Schema

The push notification system uses the `push_subscriptions` table:

```sql
CREATE TABLE push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT UNIQUE NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    preferences TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

## Troubleshooting

### "Push notifications not available"

This means the pywebpush or py-vapid libraries are not installed. Run:
```bash
pip install pywebpush py-vapid
```

### "VAPID key not available"

The VAPID keys failed to generate. Check:
1. Write permissions in the backend directory
2. py-vapid library is installed correctly

### Notifications not appearing

Check:
1. Browser permissions are granted
2. Service worker is registered (check DevTools → Application → Service Workers)
3. User preferences allow the specific alert type
4. Backend server is running

### "Invalid subscription" or 410 errors

The browser subscription has expired. The service automatically removes expired subscriptions. The user should:
1. Refresh the page
2. Re-enable notifications

## Production Considerations

### Security

1. **VAPID Keys**: Never commit VAPID keys to version control. Add to `.gitignore`:
   ```
   backend/vapid_*.pem
   ```

2. **HTTPS Required**: Push notifications only work over HTTPS in production.

3. **CORS**: Ensure your backend allows requests from your frontend domain.

### Performance

- Push notifications are sent asynchronously
- Failed subscriptions are automatically removed
- TTL (Time To Live) is set to 24 hours for notifications

### Scaling

For high-volume notifications:
1. Consider using a message queue (Redis, RabbitMQ)
2. Batch notifications instead of sending individually
3. Implement rate limiting per user

### Monitoring

Monitor notification delivery:
```python
stats = push_service.broadcast_notification(...)
print(f"Sent: {stats['sent']}, Failed: {stats['failed']}, Skipped: {stats['skipped']}")
```

## Optional: Email and SMS Notifications

For email and SMS notifications:

### Email (SendGrid, AWS SES, etc.)
```bash
pip install sendgrid
# or
pip install boto3  # for AWS SES
```

### SMS (Twilio)
```bash
pip install twilio
```

Add to `push_notification_service.py` to send multi-channel alerts.

## Testing

### Test from Python
```python
from push_notification_service import get_push_service

service = get_push_service()

# Get all subscriptions
subs = service.get_all_subscriptions()
print(f"Active subscriptions: {len(subs)}")

# Send test notification
stats = service.broadcast_notification(
    title="Test",
    body="Testing push notifications",
    alert_level="HIGH"
)
print(stats)
```

### Test from Browser
1. Open DevTools Console
2. Run:
```javascript
fetch('/api/notifications/test', { method: 'POST' })
  .then(r => r.json())
  .then(d => console.log(d))
```

## Next Steps

1. ✅ Backend push notification service created
2. ✅ Database schema added
3. ✅ API endpoints implemented
4. ✅ Frontend service worker created
5. ✅ Frontend notification settings UI created
6. 🔄 Integrate with psychology trap detector to automatically send alerts
7. 🔄 Add email notification support (optional)
8. 🔄 Add SMS notification support (optional)

## Support

For issues or questions:
- Check browser console for errors
- Check backend logs for push notification errors
- Verify VAPID keys are generated correctly
- Test with the `/api/notifications/test` endpoint
