"""
Push Notification Service - Backend
Handles browser push notifications using Web Push API

Requires:
    pip install py-vapid pywebpush

VAPID (Voluntary Application Server Identification):
- Authenticates push notifications from your server
- Generate once and store securely
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from database_adapter import get_connection

# Try to import pywebpush, provide helpful error if not installed
try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
except ImportError:
    print("⚠️ pywebpush or py-vapid not installed")
    print("Run: pip install pywebpush py-vapid")
    webpush = None
    Vapid = None

# VAPID keys path (generate once, reuse)
VAPID_PRIVATE_KEY_PATH = Path(__file__).parent / "vapid_private_key.pem"
VAPID_PUBLIC_KEY_PATH = Path(__file__).parent / "vapid_public_key.pem"
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_EMAIL', 'mailto:admin@alphagex.com')


class PushNotificationService:
    """Manage push notification subscriptions and sending"""

    def __init__(self):
        self.vapid_private = None
        self.vapid_public = None
        self._load_or_generate_vapid_keys()

    def _load_or_generate_vapid_keys(self):
        """Load existing VAPID keys or generate new ones"""
        if not Vapid:
            print("⚠️ py-vapid not installed, push notifications disabled")
            return

        try:
            # Try to load existing keys
            if VAPID_PRIVATE_KEY_PATH.exists() and VAPID_PUBLIC_KEY_PATH.exists():
                with open(VAPID_PRIVATE_KEY_PATH, 'r') as f:
                    self.vapid_private = f.read()
                with open(VAPID_PUBLIC_KEY_PATH, 'r') as f:
                    self.vapid_public = f.read()
                print("✅ Loaded existing VAPID keys")
            else:
                # Generate new keys
                print("🔑 Generating new VAPID keys...")
                vapid = Vapid()
                vapid.generate_keys()

                # Save private key
                vapid.save_key(str(VAPID_PRIVATE_KEY_PATH))

                # Save public key
                self.vapid_public = vapid.public_key.public_bytes_raw()
                with open(VAPID_PUBLIC_KEY_PATH, 'wb') as f:
                    f.write(self.vapid_public)

                # Load private key as string
                with open(VAPID_PRIVATE_KEY_PATH, 'r') as f:
                    self.vapid_private = f.read()

                # Convert public key to string
                vapid_instance = Vapid.from_file(str(VAPID_PRIVATE_KEY_PATH))
                self.vapid_public = vapid_instance.public_key.public_bytes_raw().hex()

                print(f"✅ Generated new VAPID keys")
                print(f"📁 Private key: {VAPID_PRIVATE_KEY_PATH}")
                print(f"📁 Public key: {VAPID_PUBLIC_KEY_PATH}")

        except Exception as e:
            print(f"❌ Error loading/generating VAPID keys: {e}")
            self.vapid_private = None
            self.vapid_public = None

    def get_vapid_public_key(self) -> Optional[str]:
        """Get VAPID public key for frontend subscription"""
        if not self.vapid_public:
            return None

        # Convert to base64url format expected by browsers
        try:
            vapid = Vapid.from_file(str(VAPID_PRIVATE_KEY_PATH))
            import base64
            public_key_bytes = vapid.public_key.public_bytes_raw()
            return base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').rstrip('=')
        except Exception as e:
            print(f"❌ Error getting VAPID public key: {e}")
            return None

    def save_subscription(self, subscription: Dict, preferences: Dict = None) -> bool:
        """
        Save push subscription to database

        Args:
            subscription: Push subscription object from browser
            preferences: User notification preferences

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            endpoint = subscription.get('endpoint')
            keys = subscription.get('keys', {})
            p256dh = keys.get('p256dh', '')
            auth = keys.get('auth', '')

            if not endpoint or not p256dh or not auth:
                print("❌ Invalid subscription object")
                return False

            preferences_json = json.dumps(preferences) if preferences else None

            # Insert or update subscription
            c.execute('''
                INSERT INTO push_subscriptions (endpoint, p256dh, auth, preferences, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    p256dh = excluded.p256dh,
                    auth = excluded.auth,
                    preferences = excluded.preferences,
                    updated_at = excluded.updated_at
            ''', (endpoint, p256dh, auth, preferences_json, datetime.now().isoformat()))

            conn.commit()
            conn.close()

            print(f"✅ Saved push subscription: {endpoint[:50]}...")
            return True

        except Exception as e:
            print(f"❌ Error saving subscription: {e}")
            return False

    def update_preferences(self, endpoint: str, preferences: Dict) -> bool:
        """Update notification preferences for a subscription"""
        try:
            conn = get_connection()
            c = conn.cursor()

            preferences_json = json.dumps(preferences)

            c.execute('''
                UPDATE push_subscriptions
                SET preferences = ?, updated_at = ?
                WHERE endpoint = ?
            ''', (preferences_json, datetime.now().isoformat(), endpoint))

            conn.commit()
            rows_affected = c.rowcount
            conn.close()

            if rows_affected > 0:
                print(f"✅ Updated preferences for subscription")
                return True
            else:
                print(f"⚠️ No subscription found with endpoint")
                return False

        except Exception as e:
            print(f"❌ Error updating preferences: {e}")
            return False

    def remove_subscription(self, endpoint: str) -> bool:
        """Remove push subscription from database"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute('DELETE FROM push_subscriptions WHERE endpoint = ?', (endpoint,))

            conn.commit()
            rows_affected = c.rowcount
            conn.close()

            if rows_affected > 0:
                print(f"✅ Removed push subscription")
                return True
            else:
                print(f"⚠️ No subscription found")
                return False

        except Exception as e:
            print(f"❌ Error removing subscription: {e}")
            return False

    def get_all_subscriptions(self, filter_preferences: Dict = None) -> List[Dict]:
        """
        Get all active push subscriptions

        Args:
            filter_preferences: Optional dict to filter by preferences
                                e.g., {'criticalAlerts': True}

        Returns:
            List of subscription dicts
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute('SELECT endpoint, p256dh, auth, preferences FROM push_subscriptions')
            rows = c.fetchall()
            conn.close()

            subscriptions = []
            for row in rows:
                endpoint, p256dh, auth, prefs_json = row
                prefs = json.loads(prefs_json) if prefs_json else {}

                # Filter by preferences if specified
                if filter_preferences:
                    match = all(prefs.get(k) == v for k, v in filter_preferences.items())
                    if not match:
                        continue

                subscriptions.append({
                    'endpoint': endpoint,
                    'keys': {
                        'p256dh': p256dh,
                        'auth': auth
                    },
                    'preferences': prefs
                })

            return subscriptions

        except Exception as e:
            print(f"❌ Error getting subscriptions: {e}")
            return []

    def send_notification(
        self,
        subscription: Dict,
        title: str,
        body: str,
        data: Dict = None,
        urgency: str = 'normal'
    ) -> bool:
        """
        Send push notification to a single subscription

        Args:
            subscription: Subscription dict with endpoint and keys
            title: Notification title
            body: Notification body
            data: Additional data to include
            urgency: 'very-low', 'low', 'normal', 'high'

        Returns:
            True if successful, False otherwise
        """
        if not webpush:
            print("⚠️ pywebpush not installed, cannot send notifications")
            return False

        if not self.vapid_private:
            print("⚠️ VAPID keys not configured")
            return False

        try:
            payload = {
                'title': title,
                'body': body,
                'icon': '/icons/icon-192x192.png',
                'badge': '/icons/badge-96x96.png',
                'data': data or {}
            }

            webpush(
                subscription_info=subscription,
                data=json.dumps(payload),
                vapid_private_key=self.vapid_private,
                vapid_claims={
                    "sub": VAPID_CLAIMS_EMAIL
                },
                ttl=86400,  # 24 hours
                urgency=urgency
            )

            return True

        except WebPushException as e:
            print(f"⚠️ WebPush failed: {e}")

            # If subscription is invalid (410 Gone), remove it
            if e.response and e.response.status_code == 410:
                endpoint = subscription.get('endpoint')
                if endpoint:
                    print(f"🗑️ Removing expired subscription: {endpoint[:50]}...")
                    self.remove_subscription(endpoint)

            return False

        except Exception as e:
            print(f"❌ Error sending notification: {e}")
            return False

    def broadcast_notification(
        self,
        title: str,
        body: str,
        alert_level: str = 'HIGH',
        alert_type: str = None,
        data: Dict = None
    ) -> Dict[str, int]:
        """
        Broadcast notification to all subscribed users

        Filters by user preferences (alert level and type)

        Args:
            title: Notification title
            body: Notification body
            alert_level: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
            alert_type: 'liberation', 'false_floor', 'regime_change', etc.
            data: Additional data

        Returns:
            Dict with sent, failed, skipped counts
        """
        stats = {'sent': 0, 'failed': 0, 'skipped': 0}

        # Get all subscriptions
        subscriptions = self.get_all_subscriptions()

        for sub in subscriptions:
            prefs = sub.get('preferences', {})

            # Check if notifications are enabled
            if not prefs.get('enabled', True):
                stats['skipped'] += 1
                continue

            # Check alert level preferences
            if alert_level == 'CRITICAL' and not prefs.get('criticalAlerts', True):
                stats['skipped'] += 1
                continue

            if alert_level == 'HIGH' and not prefs.get('highAlerts', True):
                stats['skipped'] += 1
                continue

            # Check alert type preferences
            if alert_type:
                if alert_type == 'liberation' and not prefs.get('liberationSetups', True):
                    stats['skipped'] += 1
                    continue
                if alert_type == 'false_floor' and not prefs.get('falseFloors', True):
                    stats['skipped'] += 1
                    continue
                if alert_type == 'regime_change' and not prefs.get('regimeChanges', True):
                    stats['skipped'] += 1
                    continue

            # Determine urgency based on alert level
            urgency = 'high' if alert_level == 'CRITICAL' else 'normal'

            # Send notification
            success = self.send_notification(
                subscription=sub,
                title=title,
                body=body,
                data=data,
                urgency=urgency
            )

            if success:
                stats['sent'] += 1
            else:
                stats['failed'] += 1

        print(f"📢 Broadcast complete: {stats['sent']} sent, {stats['failed']} failed, {stats['skipped']} skipped")
        return stats


# Singleton instance
_push_service_instance = None


def get_push_service() -> PushNotificationService:
    """Get singleton push notification service instance"""
    global _push_service_instance
    if _push_service_instance is None:
        _push_service_instance = PushNotificationService()
    return _push_service_instance
