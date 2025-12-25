"""
SOLOMON Notifications System
============================

Multi-channel notification system for Solomon feedback loop alerts:
- Slack webhooks
- Discord webhooks
- Email (via SendGrid or SMTP)
- Push notifications (via existing push system)

Notification triggers:
- New proposals created
- Degradation detected
- Kill switch activated/deactivated
- Rollback executed
- Consecutive losses threshold
- Daily digest

Author: AlphaGEX Quant
Date: 2024-12
"""

import os
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class NotificationChannel(Enum):
    """Available notification channels"""
    SLACK = "SLACK"
    DISCORD = "DISCORD"
    EMAIL = "EMAIL"
    PUSH = "PUSH"
    DATABASE = "DATABASE"  # Always log to DB


class NotificationPriority(Enum):
    """Notification priority levels"""
    LOW = "LOW"           # Daily digest only
    MEDIUM = "MEDIUM"     # Slack/Discord
    HIGH = "HIGH"         # All channels
    CRITICAL = "CRITICAL" # All channels + immediate


class NotificationType(Enum):
    """Types of notifications"""
    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    PROPOSAL_APPROVED = "PROPOSAL_APPROVED"
    PROPOSAL_REJECTED = "PROPOSAL_REJECTED"
    PROPOSAL_EXPIRED = "PROPOSAL_EXPIRED"
    DEGRADATION_DETECTED = "DEGRADATION_DETECTED"
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    KILL_SWITCH_DEACTIVATED = "KILL_SWITCH_DEACTIVATED"
    ROLLBACK_EXECUTED = "ROLLBACK_EXECUTED"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    MODEL_RETRAINED = "MODEL_RETRAINED"
    DAILY_DIGEST = "DAILY_DIGEST"
    WEEKEND_ANALYSIS = "WEEKEND_ANALYSIS"
    MAX_DAILY_LOSS = "MAX_DAILY_LOSS"
    PERFORMANCE_ALERT = "PERFORMANCE_ALERT"


@dataclass
class Notification:
    """A notification to be sent"""
    notification_type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    bot_name: str = ""
    data: Dict = field(default_factory=dict)
    channels: List[NotificationChannel] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))

    def to_dict(self) -> Dict:
        return {
            'type': self.notification_type.value,
            'priority': self.priority.value,
            'title': self.title,
            'message': self.message,
            'bot_name': self.bot_name,
            'data': self.data,
            'channels': [c.value for c in self.channels],
            'created_at': self.created_at.isoformat()
        }


class SolomonNotifications:
    """
    Multi-channel notification system for Solomon.

    Configuration via environment variables:
    - SOLOMON_SLACK_WEBHOOK: Slack incoming webhook URL
    - SOLOMON_DISCORD_WEBHOOK: Discord webhook URL
    - SOLOMON_EMAIL_ENABLED: Enable email notifications
    - SENDGRID_API_KEY: SendGrid API key for email
    - SOLOMON_NOTIFY_EMAIL: Email address to send to
    """

    def __init__(self):
        # Load configuration from environment
        self.slack_webhook = os.getenv('SOLOMON_SLACK_WEBHOOK') or os.getenv('SLACK_WEBHOOK_URL')
        self.discord_webhook = os.getenv('SOLOMON_DISCORD_WEBHOOK') or os.getenv('DISCORD_WEBHOOK_URL')
        self.email_enabled = os.getenv('SOLOMON_EMAIL_ENABLED', '').lower() == 'true'
        self.notify_email = os.getenv('SOLOMON_NOTIFY_EMAIL')
        self.sendgrid_key = os.getenv('SENDGRID_API_KEY')

        # Track sent notifications to avoid spam
        self._sent_cache: Dict[str, datetime] = {}
        self._cache_duration = timedelta(minutes=30)

        # Log configuration
        channels = []
        if self.slack_webhook:
            channels.append('Slack')
        if self.discord_webhook:
            channels.append('Discord')
        if self.email_enabled and self.notify_email:
            channels.append('Email')

        if channels:
            logger.info(f"Solomon notifications enabled: {', '.join(channels)}")
        else:
            logger.info("Solomon notifications: No external channels configured (DB only)")

    def _should_send(self, notification: Notification) -> bool:
        """Check if we should send this notification (avoid spam)"""
        cache_key = f"{notification.notification_type.value}:{notification.bot_name}:{notification.title}"

        if cache_key in self._sent_cache:
            last_sent = self._sent_cache[cache_key]
            if datetime.now(CENTRAL_TZ) - last_sent < self._cache_duration:
                logger.debug(f"Skipping duplicate notification: {cache_key}")
                return False

        self._sent_cache[cache_key] = datetime.now(CENTRAL_TZ)
        return True

    def send(self, notification: Notification) -> bool:
        """
        Send a notification to all configured channels.

        Returns True if at least one channel succeeded.
        """
        if not self._should_send(notification):
            return True  # Skipped but not an error

        success = False

        # Always log to database
        self._log_to_database(notification)
        success = True

        # Determine channels based on priority
        channels = self._get_channels_for_priority(notification.priority)

        # Send to each channel
        for channel in channels:
            try:
                if channel == NotificationChannel.SLACK and self.slack_webhook:
                    self._send_slack(notification)
                    success = True
                elif channel == NotificationChannel.DISCORD and self.discord_webhook:
                    self._send_discord(notification)
                    success = True
                elif channel == NotificationChannel.EMAIL and self.email_enabled:
                    self._send_email(notification)
                    success = True
                elif channel == NotificationChannel.PUSH:
                    self._send_push(notification)
                    success = True
            except Exception as e:
                logger.error(f"Failed to send {channel.value} notification: {e}")

        return success

    def _get_channels_for_priority(self, priority: NotificationPriority) -> List[NotificationChannel]:
        """Get channels to notify based on priority"""
        if priority == NotificationPriority.CRITICAL:
            return [NotificationChannel.SLACK, NotificationChannel.DISCORD,
                    NotificationChannel.EMAIL, NotificationChannel.PUSH]
        elif priority == NotificationPriority.HIGH:
            return [NotificationChannel.SLACK, NotificationChannel.DISCORD, NotificationChannel.EMAIL]
        elif priority == NotificationPriority.MEDIUM:
            return [NotificationChannel.SLACK, NotificationChannel.DISCORD]
        else:
            return []  # Low priority = digest only

    def _send_slack(self, notification: Notification):
        """Send notification to Slack"""
        if not self.slack_webhook:
            return

        # Build Slack message with blocks for rich formatting
        color = self._get_color_for_type(notification.notification_type)
        emoji = self._get_emoji_for_type(notification.notification_type)

        payload = {
            "attachments": [{
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} {notification.title}",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": notification.message
                        }
                    }
                ]
            }]
        }

        # Add bot name if present
        if notification.bot_name:
            payload["attachments"][0]["blocks"].append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"🤖 *Bot:* {notification.bot_name} | 🕐 {notification.created_at.strftime('%I:%M %p CT')}"
                }]
            })

        # Add data fields if present
        if notification.data:
            fields = []
            for key, value in list(notification.data.items())[:6]:  # Max 6 fields
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key}:* {value}"
                })
            if fields:
                payload["attachments"][0]["blocks"].append({
                    "type": "section",
                    "fields": fields
                })

        response = requests.post(self.slack_webhook, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Slack notification sent: {notification.title}")

    def _send_discord(self, notification: Notification):
        """Send notification to Discord"""
        if not self.discord_webhook:
            return

        color = self._get_discord_color_for_type(notification.notification_type)
        emoji = self._get_emoji_for_type(notification.notification_type)

        embed = {
            "title": f"{emoji} {notification.title}",
            "description": notification.message,
            "color": color,
            "timestamp": notification.created_at.isoformat(),
            "footer": {"text": "Solomon Feedback Loop"}
        }

        if notification.bot_name:
            embed["author"] = {"name": f"Bot: {notification.bot_name}"}

        if notification.data:
            embed["fields"] = [
                {"name": k, "value": str(v), "inline": True}
                for k, v in list(notification.data.items())[:6]
            ]

        payload = {"embeds": [embed]}

        response = requests.post(self.discord_webhook, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Discord notification sent: {notification.title}")

    def _send_email(self, notification: Notification):
        """Send notification via email (SendGrid)"""
        if not self.sendgrid_key or not self.notify_email:
            return

        # Build email content
        subject = f"[Solomon] {notification.title}"
        html_content = f"""
        <h2>{notification.title}</h2>
        <p>{notification.message}</p>
        """

        if notification.bot_name:
            html_content += f"<p><strong>Bot:</strong> {notification.bot_name}</p>"

        if notification.data:
            html_content += "<h3>Details:</h3><ul>"
            for k, v in notification.data.items():
                html_content += f"<li><strong>{k}:</strong> {v}</li>"
            html_content += "</ul>"

        html_content += f"<p><em>Sent at {notification.created_at.strftime('%Y-%m-%d %I:%M %p CT')}</em></p>"

        payload = {
            "personalizations": [{"to": [{"email": self.notify_email}]}],
            "from": {"email": "solomon@alphagex.com", "name": "Solomon"},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_content}]
        }

        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {self.sendgrid_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Email notification sent: {notification.title}")

    def _send_push(self, notification: Notification):
        """Send push notification via existing push system"""
        try:
            from database_adapter import get_connection

            conn = get_connection()
            cursor = conn.cursor()

            # Insert into push notification queue
            cursor.execute("""
                INSERT INTO push_notification_queue (title, body, data, priority, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (
                notification.title,
                notification.message,
                json.dumps(notification.data),
                notification.priority.value
            ))

            conn.commit()
            conn.close()
            logger.info(f"Push notification queued: {notification.title}")
        except Exception as e:
            logger.debug(f"Could not queue push notification: {e}")

    def _log_to_database(self, notification: Notification):
        """Log notification to database for history"""
        try:
            from database_adapter import get_connection

            conn = get_connection()
            cursor = conn.cursor()

            # Ensure table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS solomon_notifications (
                    id SERIAL PRIMARY KEY,
                    notification_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT,
                    bot_name TEXT,
                    data JSONB,
                    channels TEXT[],
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cursor.execute("""
                INSERT INTO solomon_notifications
                (notification_type, priority, title, message, bot_name, data, channels, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                notification.notification_type.value,
                notification.priority.value,
                notification.title,
                notification.message,
                notification.bot_name,
                json.dumps(notification.data),
                [c.value for c in notification.channels],
                notification.created_at
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not log notification to DB: {e}")

    def _get_color_for_type(self, notification_type: NotificationType) -> str:
        """Get Slack color for notification type"""
        colors = {
            NotificationType.PROPOSAL_CREATED: "#FFA500",      # Orange
            NotificationType.PROPOSAL_APPROVED: "#36a64f",     # Green
            NotificationType.PROPOSAL_REJECTED: "#FF6B6B",     # Red
            NotificationType.DEGRADATION_DETECTED: "#FF0000",  # Red
            NotificationType.KILL_SWITCH_ACTIVATED: "#FF0000", # Red
            NotificationType.KILL_SWITCH_DEACTIVATED: "#36a64f", # Green
            NotificationType.ROLLBACK_EXECUTED: "#FFA500",     # Orange
            NotificationType.CONSECUTIVE_LOSSES: "#FF6B6B",    # Red
            NotificationType.MODEL_RETRAINED: "#36a64f",       # Green
            NotificationType.DAILY_DIGEST: "#4A90D9",          # Blue
            NotificationType.MAX_DAILY_LOSS: "#FF0000",        # Red
        }
        return colors.get(notification_type, "#808080")

    def _get_discord_color_for_type(self, notification_type: NotificationType) -> int:
        """Get Discord color (as int) for notification type"""
        colors = {
            NotificationType.PROPOSAL_CREATED: 0xFFA500,
            NotificationType.PROPOSAL_APPROVED: 0x36a64f,
            NotificationType.PROPOSAL_REJECTED: 0xFF6B6B,
            NotificationType.DEGRADATION_DETECTED: 0xFF0000,
            NotificationType.KILL_SWITCH_ACTIVATED: 0xFF0000,
            NotificationType.KILL_SWITCH_DEACTIVATED: 0x36a64f,
            NotificationType.ROLLBACK_EXECUTED: 0xFFA500,
            NotificationType.CONSECUTIVE_LOSSES: 0xFF6B6B,
            NotificationType.MODEL_RETRAINED: 0x36a64f,
            NotificationType.DAILY_DIGEST: 0x4A90D9,
            NotificationType.MAX_DAILY_LOSS: 0xFF0000,
        }
        return colors.get(notification_type, 0x808080)

    def _get_emoji_for_type(self, notification_type: NotificationType) -> str:
        """Get emoji for notification type"""
        emojis = {
            NotificationType.PROPOSAL_CREATED: "📋",
            NotificationType.PROPOSAL_APPROVED: "✅",
            NotificationType.PROPOSAL_REJECTED: "❌",
            NotificationType.PROPOSAL_EXPIRED: "⏰",
            NotificationType.DEGRADATION_DETECTED: "📉",
            NotificationType.KILL_SWITCH_ACTIVATED: "🛑",
            NotificationType.KILL_SWITCH_DEACTIVATED: "🟢",
            NotificationType.ROLLBACK_EXECUTED: "⏪",
            NotificationType.CONSECUTIVE_LOSSES: "💸",
            NotificationType.MODEL_RETRAINED: "🧠",
            NotificationType.DAILY_DIGEST: "📊",
            NotificationType.WEEKEND_ANALYSIS: "📅",
            NotificationType.MAX_DAILY_LOSS: "🚨",
            NotificationType.PERFORMANCE_ALERT: "⚠️",
        }
        return emojis.get(notification_type, "🔔")

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def notify_proposal_created(self, bot_name: str, proposal_id: str, title: str, reason: str):
        """Notify when a new proposal is created"""
        self.send(Notification(
            notification_type=NotificationType.PROPOSAL_CREATED,
            priority=NotificationPriority.MEDIUM,
            title=f"New Proposal: {title}",
            message=f"A new proposal has been created for {bot_name} and requires your approval.\n\n*Reason:* {reason}",
            bot_name=bot_name,
            data={"proposal_id": proposal_id, "reason": reason}
        ))

    def notify_degradation(self, bot_name: str, degradation_pct: float, recent_wr: float, prev_wr: float):
        """Notify when performance degradation is detected"""
        self.send(Notification(
            notification_type=NotificationType.DEGRADATION_DETECTED,
            priority=NotificationPriority.HIGH,
            title=f"Performance Degradation: {bot_name}",
            message=f"⚠️ {bot_name} performance has dropped {degradation_pct:.1f}%\n\nWin rate: {prev_wr:.1f}% → {recent_wr:.1f}%\n\nConsider reviewing recent trades or rolling back to a previous version.",
            bot_name=bot_name,
            data={
                "degradation_pct": f"{degradation_pct:.1f}%",
                "previous_win_rate": f"{prev_wr:.1f}%",
                "current_win_rate": f"{recent_wr:.1f}%"
            }
        ))

    def notify_kill_switch(self, bot_name: str, activated: bool, reason: str, by: str):
        """Notify when kill switch is activated/deactivated"""
        if activated:
            self.send(Notification(
                notification_type=NotificationType.KILL_SWITCH_ACTIVATED,
                priority=NotificationPriority.CRITICAL,
                title=f"KILL SWITCH ACTIVATED: {bot_name}",
                message=f"🛑 Trading has been STOPPED for {bot_name}\n\n*Reason:* {reason}\n*By:* {by}",
                bot_name=bot_name,
                data={"reason": reason, "activated_by": by}
            ))
        else:
            self.send(Notification(
                notification_type=NotificationType.KILL_SWITCH_DEACTIVATED,
                priority=NotificationPriority.MEDIUM,
                title=f"Kill Switch Deactivated: {bot_name}",
                message=f"🟢 Trading has been RESUMED for {bot_name}\n\n*By:* {by}",
                bot_name=bot_name,
                data={"resumed_by": by}
            ))

    def notify_consecutive_losses(self, bot_name: str, loss_count: int, total_loss: float):
        """Notify when consecutive losses threshold is reached"""
        self.send(Notification(
            notification_type=NotificationType.CONSECUTIVE_LOSSES,
            priority=NotificationPriority.HIGH,
            title=f"Consecutive Losses Alert: {bot_name}",
            message=f"💸 {bot_name} has {loss_count} consecutive losses\n\nTotal loss: ${total_loss:,.2f}\n\nConsider activating kill switch or reviewing strategy.",
            bot_name=bot_name,
            data={
                "consecutive_losses": loss_count,
                "total_loss": f"${total_loss:,.2f}"
            }
        ))

    def notify_rollback(self, bot_name: str, from_version: str, to_version: str, reason: str, automatic: bool):
        """Notify when a rollback is executed"""
        self.send(Notification(
            notification_type=NotificationType.ROLLBACK_EXECUTED,
            priority=NotificationPriority.HIGH,
            title=f"Rollback Executed: {bot_name}",
            message=f"⏪ {bot_name} has been rolled back\n\n*From:* v{from_version}\n*To:* v{to_version}\n*Reason:* {reason}\n*Automatic:* {'Yes' if automatic else 'No'}",
            bot_name=bot_name,
            data={
                "from_version": from_version,
                "to_version": to_version,
                "automatic": automatic
            }
        ))

    def notify_max_daily_loss(self, bot_name: str, loss_amount: float, threshold: float):
        """Notify when max daily loss threshold is hit"""
        self.send(Notification(
            notification_type=NotificationType.MAX_DAILY_LOSS,
            priority=NotificationPriority.CRITICAL,
            title=f"MAX DAILY LOSS: {bot_name}",
            message=f"🚨 {bot_name} has hit the maximum daily loss threshold!\n\nLoss: ${loss_amount:,.2f}\nThreshold: ${threshold:,.2f}\n\nKill switch has been automatically activated.",
            bot_name=bot_name,
            data={
                "daily_loss": f"${loss_amount:,.2f}",
                "threshold": f"${threshold:,.2f}"
            }
        ))

    def send_daily_digest(self, summary: Dict):
        """Send daily performance digest"""
        # Build summary message
        message_parts = ["📊 *Daily Trading Summary*\n"]

        for bot_name, data in summary.get('bots', {}).items():
            wins = data.get('wins', 0)
            losses = data.get('losses', 0)
            pnl = data.get('pnl', 0)
            emoji = "🟢" if pnl >= 0 else "🔴"

            message_parts.append(f"{emoji} *{bot_name}:* {wins}W/{losses}L (${pnl:+,.2f})")

        if summary.get('pending_proposals', 0) > 0:
            message_parts.append(f"\n📋 *{summary['pending_proposals']} proposals* awaiting approval")

        if summary.get('alerts', []):
            message_parts.append(f"\n⚠️ *{len(summary['alerts'])} alerts* raised today")

        self.send(Notification(
            notification_type=NotificationType.DAILY_DIGEST,
            priority=NotificationPriority.MEDIUM,
            title="Daily Solomon Digest",
            message="\n".join(message_parts),
            data=summary
        ))


# Singleton
_notifications: Optional[SolomonNotifications] = None


def get_notifications() -> SolomonNotifications:
    """Get or create notifications singleton"""
    global _notifications
    if _notifications is None:
        _notifications = SolomonNotifications()
    return _notifications
