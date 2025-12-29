"""
SPX WHEEL TRADING ALERTS SYSTEM

Sends email notifications for critical trading events:
- Position expiring
- Stop loss triggered
- Position went ITM
- Divergence from backtest exceeds threshold
- Daily summary
- Errors/failures

Configure email in environment:
    ALERT_EMAIL=shairan2016@gmail.com
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=your-email@gmail.com
    SMTP_PASSWORD=your-app-password

For Gmail, use an App Password (not your main password):
https://support.google.com/accounts/answer/185833
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
import json
import logging
from zoneinfo import ZoneInfo

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")

logger = logging.getLogger(__name__)

# Default recipient
DEFAULT_ALERT_EMAIL = "shairan2016@gmail.com"


class AlertLevel:
    """Alert severity levels"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    DAILY = "DAILY"


class TradingAlerts:
    """
    Email alert system for SPX wheel trading.

    Sends notifications for:
    - Stop loss triggers
    - Position expirations
    - ITM warnings
    - Performance divergence
    - Daily summaries
    """

    def __init__(self):
        self.recipient = os.getenv('ALERT_EMAIL', DEFAULT_ALERT_EMAIL)
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')

        # Track sent alerts to avoid spam
        self._sent_alerts: Dict[str, datetime] = {}
        self._cooldown_minutes = 60  # Don't repeat same alert within this time

        # Alert history for dashboard
        self.alert_history: List[Dict] = []

    def _can_send_alert(self, alert_key: str) -> bool:
        """Check if we should send this alert (cooldown check)"""
        if alert_key not in self._sent_alerts:
            return True

        last_sent = self._sent_alerts[alert_key]
        minutes_elapsed = (datetime.now(CENTRAL_TZ) - last_sent).total_seconds() / 60
        return minutes_elapsed >= self._cooldown_minutes

    def _record_alert(self, alert_key: str, level: str, subject: str, body: str):
        """Record alert in history"""
        self._sent_alerts[alert_key] = datetime.now(CENTRAL_TZ)
        self.alert_history.append({
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
            'level': level,
            'subject': subject,
            'body': body[:500],  # Truncate for storage
            'key': alert_key
        })
        # Keep only last 100 alerts
        if len(self.alert_history) > 100:
            self.alert_history = self.alert_history[-100:]

    def send_email(self, subject: str, body: str, level: str = AlertLevel.INFO) -> bool:
        """
        Send email alert.

        Returns True if sent successfully, False otherwise.
        """
        if not self.smtp_user or not self.smtp_password:
            logger.warning(f"Email not configured - logging alert instead: {subject}")
            print(f"\n{'='*60}")
            print(f"ALERT [{level}]: {subject}")
            print(f"{'='*60}")
            print(body)
            print(f"{'='*60}\n")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_user
            msg['To'] = self.recipient
            msg['Subject'] = f"[SPX WHEEL {level}] {subject}"

            # Add timestamp and level to body
            full_body = f"""
SPX WHEEL TRADING ALERT
=======================
Level: {level}
Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S')}

{body}

---
This is an automated alert from your SPX Wheel Trading System.
Dashboard: http://localhost:5000
            """

            msg.attach(MIMEText(full_body, 'plain'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Alert sent: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            print(f"EMAIL ALERT FAILED: {subject}")
            print(f"Error: {e}")
            return False

    # === SPECIFIC ALERT TYPES ===

    def alert_stop_loss_triggered(self, position: Dict, current_price: float, loss_pct: float):
        """Alert when stop loss is triggered"""
        alert_key = f"stop_loss_{position.get('id')}"

        if not self._can_send_alert(alert_key):
            return

        subject = f"STOP LOSS TRIGGERED - {position.get('option_ticker')}"
        body = f"""
STOP LOSS TRIGGERED!

Position Details:
- Ticker: {position.get('option_ticker')}
- Strike: ${position.get('strike'):,.0f}
- Entry Price: ${position.get('entry_price'):.2f}
- Current Price: ${current_price:.2f}
- Loss: {loss_pct:.1f}%

ACTION REQUIRED: Position should be closed immediately.

The option price has increased beyond your stop loss threshold,
indicating significant losses on this position.
        """

        self.send_email(subject, body, AlertLevel.CRITICAL)
        self._record_alert(alert_key, AlertLevel.CRITICAL, subject, body)

    def alert_position_itm(self, position: Dict, spot_price: float, intrinsic_value: float):
        """Alert when position goes in-the-money"""
        alert_key = f"itm_{position.get('id')}_{datetime.now(CENTRAL_TZ).strftime('%Y%m%d')}"

        if not self._can_send_alert(alert_key):
            return

        subject = f"POSITION ITM - {position.get('option_ticker')}"
        body = f"""
POSITION IS IN-THE-MONEY!

Position Details:
- Ticker: {position.get('option_ticker')}
- Strike: ${position.get('strike'):,.0f}
- Current SPX: ${spot_price:,.2f}
- Intrinsic Value: ${intrinsic_value:.2f}
- Expiration: {position.get('expiration')}

Your put is currently in-the-money. If SPX closes below your strike
at expiration, you will incur a cash settlement loss.

Potential Loss if Settles Here: ${intrinsic_value * 100 * position.get('contracts', 1):,.2f}
        """

        self.send_email(subject, body, AlertLevel.WARNING)
        self._record_alert(alert_key, AlertLevel.WARNING, subject, body)

    def alert_position_expiring(self, position: Dict, dte: int, spot_price: float):
        """Alert when position is about to expire"""
        alert_key = f"expiring_{position.get('id')}"

        if not self._can_send_alert(alert_key):
            return

        is_itm = spot_price < position.get('strike', 0)
        status = "IN-THE-MONEY (will settle for loss)" if is_itm else "OUT-OF-MONEY (will expire worthless)"

        subject = f"POSITION EXPIRING IN {dte} DAYS - {position.get('option_ticker')}"
        body = f"""
POSITION EXPIRING SOON!

Position Details:
- Ticker: {position.get('option_ticker')}
- Strike: ${position.get('strike'):,.0f}
- Expiration: {position.get('expiration')}
- Days to Expiration: {dte}
- Current SPX: ${spot_price:,.2f}
- Status: {status}

Premium Received: ${position.get('premium_received'):,.2f}

{'Consider rolling this position if you want to avoid settlement.' if is_itm else 'Position should expire worthless - full premium profit.'}
        """

        self.send_email(subject, body, AlertLevel.INFO)
        self._record_alert(alert_key, AlertLevel.INFO, subject, body)

    def alert_divergence(self, live_win_rate: float, backtest_win_rate: float, divergence: float):
        """Alert when live performance diverges significantly from backtest"""
        alert_key = f"divergence_{datetime.now(CENTRAL_TZ).strftime('%Y%m%d')}"

        if not self._can_send_alert(alert_key):
            return

        subject = f"PERFORMANCE DIVERGENCE: {divergence:+.1f}%"
        body = f"""
SIGNIFICANT PERFORMANCE DIVERGENCE DETECTED!

Backtest Expected Win Rate: {backtest_win_rate:.1f}%
Live Actual Win Rate: {live_win_rate:.1f}%
Divergence: {divergence:+.1f}%

This indicates your live trading results are significantly different
from what the backtest predicted.

RECOMMENDED ACTION:
- Review recent trades for issues
- Check if market conditions have changed
- Consider re-running calibration with recent data
- Verify data quality in both backtest and live
        """

        self.send_email(subject, body, AlertLevel.WARNING)
        self._record_alert(alert_key, AlertLevel.WARNING, subject, body)

    def alert_trade_executed(self, trade_type: str, position: Dict, mode: str):
        """Alert when a trade is executed"""
        alert_key = f"trade_{position.get('id')}_{trade_type}"

        if not self._can_send_alert(alert_key):
            return

        subject = f"TRADE EXECUTED: {trade_type} - {position.get('option_ticker')}"
        body = f"""
TRADE EXECUTED ({mode.upper()} MODE)

Action: {trade_type}
Ticker: {position.get('option_ticker')}
Strike: ${position.get('strike'):,.0f}
Expiration: {position.get('expiration')}
Contracts: {position.get('contracts', 1)}
Price: ${position.get('entry_price', 0):.2f}
Premium: ${position.get('premium_received', 0):,.2f}

Price Source: {position.get('price_source', 'UNKNOWN')}
        """

        self.send_email(subject, body, AlertLevel.INFO)
        self._record_alert(alert_key, AlertLevel.INFO, subject, body)

    def alert_daily_summary(self, summary: Dict):
        """Send daily trading summary"""
        alert_key = f"daily_{datetime.now(CENTRAL_TZ).strftime('%Y%m%d')}"

        subject = f"DAILY SUMMARY - {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')}"
        body = f"""
DAILY SPX WHEEL TRADING SUMMARY
===============================

ACCOUNT STATUS:
- Total Equity: ${summary.get('total_equity', 0):,.2f}
- Daily P&L: ${summary.get('daily_pnl', 0):,.2f}
- Cumulative P&L: ${summary.get('cumulative_pnl', 0):,.2f}

POSITIONS:
- Open Positions: {summary.get('open_positions', 0)}
- Trades Today: {summary.get('trades_today', 0)}
- Positions Expiring This Week: {summary.get('expiring_soon', 0)}

PERFORMANCE VS BACKTEST:
- Live Win Rate: {summary.get('live_win_rate', 0):.1f}%
- Backtest Win Rate: {summary.get('backtest_win_rate', 0):.1f}%
- Divergence: {summary.get('divergence', 0):+.1f}%

DATA QUALITY:
- Real Data: {summary.get('real_data_pct', 0):.1f}%
- Estimated: {summary.get('estimated_data_pct', 0):.1f}%

{summary.get('notes', '')}
        """

        self.send_email(subject, body, AlertLevel.DAILY)
        self._record_alert(alert_key, AlertLevel.DAILY, subject, body)

    def alert_error(self, error_type: str, error_message: str, context: Dict = None):
        """Alert on system errors"""
        alert_key = f"error_{error_type}_{datetime.now(CENTRAL_TZ).strftime('%Y%m%d%H')}"

        if not self._can_send_alert(alert_key):
            return

        subject = f"SYSTEM ERROR: {error_type}"
        body = f"""
SYSTEM ERROR DETECTED!

Error Type: {error_type}
Message: {error_message}
Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S')}

Context:
{json.dumps(context, indent=2, default=str) if context else 'No additional context'}

Please check the system logs and dashboard for more details.
        """

        self.send_email(subject, body, AlertLevel.CRITICAL)
        self._record_alert(alert_key, AlertLevel.CRITICAL, subject, body)

    def alert_position_reconciliation_mismatch(self, db_positions: List, broker_positions: List):
        """Alert when database doesn't match broker"""
        alert_key = f"reconciliation_{datetime.now(CENTRAL_TZ).strftime('%Y%m%d')}"

        if not self._can_send_alert(alert_key):
            return

        subject = "POSITION RECONCILIATION MISMATCH!"
        body = f"""
POSITION MISMATCH BETWEEN DATABASE AND BROKER!

Database shows {len(db_positions)} positions
Broker shows {len(broker_positions)} positions

DATABASE POSITIONS:
{chr(10).join([f"  - {p.get('option_ticker')}: {p.get('contracts')} contracts" for p in db_positions]) or '  None'}

BROKER POSITIONS:
{chr(10).join([f"  - {p.get('symbol')}: {p.get('quantity')} contracts" for p in broker_positions]) or '  None'}

ACTION REQUIRED: Manually verify and reconcile positions!
        """

        self.send_email(subject, body, AlertLevel.CRITICAL)
        self._record_alert(alert_key, AlertLevel.CRITICAL, subject, body)


# Global alerts instance
_alerts = None


def get_alerts() -> TradingAlerts:
    """Get global alerts instance"""
    global _alerts
    if _alerts is None:
        _alerts = TradingAlerts()
    return _alerts


def send_alert(subject: str, body: str, level: str = AlertLevel.INFO) -> bool:
    """Convenience function to send alert"""
    return get_alerts().send_email(subject, body, level)


# === SAVE ALERTS TO DATABASE ===

def save_alert_to_db(alert_type: str, level: str, subject: str, body: str, position_id: int = None):
    """Save alert to database for dashboard display"""
    try:
        import sys
        sys.path.insert(0, '/home/user/AlphaGEX')
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # NOTE: Table 'spx_wheel_alerts' is defined in db/config_and_database.py (single source of truth)

        cursor.execute('''
            INSERT INTO spx_wheel_alerts (alert_type, level, subject, body, position_id)
            VALUES (%s, %s, %s, %s, %s)
        ''', (alert_type, level, subject, body[:1000], position_id))

        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to save alert to DB: {e}")


if __name__ == "__main__":
    # Test the alert system
    print("Testing SPX Wheel Alert System")
    print("="*50)

    alerts = get_alerts()

    print(f"Recipient: {alerts.recipient}")
    print(f"SMTP Server: {alerts.smtp_server}")
    print(f"SMTP User: {alerts.smtp_user or 'NOT CONFIGURED'}")

    # Send test alert
    alerts.send_email(
        "Test Alert",
        "This is a test alert from the SPX Wheel Trading System.\n\nIf you received this, alerts are working!",
        AlertLevel.INFO
    )
