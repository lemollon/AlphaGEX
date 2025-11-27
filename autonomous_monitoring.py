"""
Autonomous Trader Monitoring & Alerting System
Sends notifications when trades execute or errors occur
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from database_adapter import get_connection


class TraderMonitor:
    """Monitor autonomous trader and send alerts"""

    def __init__(self, db_path: str = "autonomous_trader.db"):
        self.db_path = db_path
        self.alert_methods = []

    def add_email_alert(self, smtp_host: str, smtp_port: int,
                       from_email: str, to_email: str, password: str):
        """Add email alerting"""
        self.alert_methods.append({
            'type': 'email',
            'smtp_host': smtp_host,
            'smtp_port': smtp_port,
            'from_email': from_email,
            'to_email': to_email,
            'password': password
        })

    def add_webhook_alert(self, webhook_url: str):
        """Add webhook alerting (Slack, Discord, etc.)"""
        self.alert_methods.append({
            'type': 'webhook',
            'url': webhook_url
        })

    def check_for_new_trades(self) -> List[Dict]:
        """Check for trades executed in last 5 minutes"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get trades from last 5 minutes
            five_mins_ago = (datetime.now() - timedelta(minutes=5)).isoformat()

            cursor.execute("""
                SELECT
                    id, timestamp, symbol, action, option_type,
                    strike, quantity, entry_price, strategy_name
                FROM trades
                WHERE timestamp > %s AND status = 'OPEN'
                ORDER BY timestamp DESC
            """, (five_mins_ago,))

            trades = []
            for row in cursor.fetchall():
                trades.append({
                    'id': row[0],
                    'timestamp': row[1],
                    'symbol': row[2],
                    'action': row[3],
                    'option_type': row[4],
                    'strike': row[5],
                    'quantity': row[6],
                    'entry_price': row[7],
                    'strategy': row[8]
                })

            conn.close()
            return trades

        except Exception as e:
            print(f"Error checking trades: {e}")
            return []

    def check_for_errors(self) -> List[Dict]:
        """Check for recent errors in logs"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get errors from last hour
            one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()

            cursor.execute("""
                SELECT timestamp, log_type, reasoning_summary
                FROM autonomous_trader_logs
                WHERE timestamp > %s
                AND (log_type LIKE '%%ERROR%%' OR log_type LIKE '%%FAILURE%%')
                ORDER BY timestamp DESC
                LIMIT 10
            """, (one_hour_ago,))

            errors = []
            for row in cursor.fetchall():
                errors.append({
                    'timestamp': row[0],
                    'type': row[1],
                    'message': row[2]
                })

            conn.close()
            return errors

        except Exception as e:
            print(f"Error checking logs: {e}")
            return []

    def get_daily_summary(self) -> Dict:
        """Get summary of today's trading activity"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            today = datetime.now().date().isoformat()

            # Count trades today
            cursor.execute("""
                SELECT COUNT(*),
                       SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(realized_pnl) as total_pnl
                FROM trades
                WHERE DATE(timestamp) = %s
            """, (today,))

            row = cursor.fetchone()
            total_trades = row[0] or 0
            wins = row[1] or 0
            total_pnl = row[2] or 0

            # Get current capital
            cursor.execute("SELECT current_capital FROM strategy_competition LIMIT 1")
            capital_row = cursor.fetchone()
            current_capital = capital_row[0] if capital_row else 1000000

            conn.close()

            return {
                'date': today,
                'total_trades': total_trades,
                'winning_trades': wins,
                'win_rate': (wins / total_trades * 100) if total_trades > 0 else 0,
                'total_pnl': total_pnl,
                'current_capital': current_capital
            }

        except Exception as e:
            print(f"Error getting summary: {e}")
            return {}

    def send_trade_alert(self, trade: Dict):
        """Send alert for new trade execution"""
        subject = f"🤖 AlphaGEX Trade: {trade['action']} {trade['symbol']}"

        message = f"""
Autonomous Trader Executed Trade
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Trade Details:
   Symbol: {trade['symbol']}
   Action: {trade['action']}
   Type: {trade['option_type']}
   Strike: ${trade['strike']}
   Quantity: {trade['quantity']} contracts
   Entry Price: ${trade['entry_price']:.2f}
   Strategy: {trade['strategy']}

⏰ Executed: {trade['timestamp']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
View details at: http://localhost:3000/trader
"""

        self._send_alert(subject, message)

    def send_error_alert(self, errors: List[Dict]):
        """Send alert for errors"""
        if not errors:
            return

        subject = f"⚠️ AlphaGEX Trader Errors ({len(errors)})"

        error_list = "\n".join([
            f"   {e['timestamp']}: {e['message']}"
            for e in errors[:5]  # Limit to 5 most recent
        ])

        message = f"""
Autonomous Trader Errors Detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ Recent Errors:
{error_list}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Check logs at: http://localhost:3000/trader
"""

        self._send_alert(subject, message)

    def send_daily_summary(self):
        """Send end-of-day summary"""
        summary = self.get_daily_summary()

        if not summary:
            return

        pnl_emoji = "📈" if summary['total_pnl'] >= 0 else "📉"
        pnl_sign = "+" if summary['total_pnl'] >= 0 else ""

        subject = f"{pnl_emoji} AlphaGEX Daily Summary - {summary['date']}"

        message = f"""
Autonomous Trader Daily Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Trading Activity:
   Total Trades: {summary['total_trades']}
   Winning Trades: {summary['winning_trades']}
   Win Rate: {summary['win_rate']:.1f}%

💰 Performance:
   Daily P&L: {pnl_sign}${summary['total_pnl']:.2f}
   Current Capital: ${summary['current_capital']:,.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
View full details at: http://localhost:3000/trader
"""

        self._send_alert(subject, message)

    def _send_alert(self, subject: str, message: str):
        """Send alert via configured methods"""
        for method in self.alert_methods:
            try:
                if method['type'] == 'email':
                    self._send_email(
                        method['smtp_host'],
                        method['smtp_port'],
                        method['from_email'],
                        method['to_email'],
                        method['password'],
                        subject,
                        message
                    )
                elif method['type'] == 'webhook':
                    self._send_webhook(method['url'], subject, message)

            except Exception as e:
                print(f"Failed to send alert via {method['type']}: {e}")

    def _send_email(self, smtp_host: str, smtp_port: int,
                    from_email: str, to_email: str, password: str,
                    subject: str, message: str):
        """Send email alert"""
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(message, 'plain'))

        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        server.quit()

        print(f"✅ Email sent: {subject}")

    def _send_webhook(self, url: str, subject: str, message: str):
        """Send webhook alert (Slack/Discord format)"""
        import requests

        payload = {
            "text": f"**{subject}**\n```\n{message}\n```"
        }

        response = requests.post(url, json=payload)
        response.raise_for_status()

        print(f"✅ Webhook sent: {subject}")


def run_monitoring_cycle():
    """Run one monitoring cycle - check for trades and errors"""
    monitor = TraderMonitor()

    # Configure alerts (example - customize as needed)
    # monitor.add_email_alert(
    #     smtp_host="smtp.gmail.com",
    #     smtp_port=587,
    #     from_email="your-email@gmail.com",
    #     to_email="your-email@gmail.com",
    #     password="your-app-password"
    # )

    # monitor.add_webhook_alert("https://hooks.slack.com/services/YOUR/WEBHOOK/URL")

    # Check for new trades
    new_trades = monitor.check_for_new_trades()
    for trade in new_trades:
        print(f"📢 New trade detected: {trade['symbol']} {trade['action']}")
        monitor.send_trade_alert(trade)

    # Check for errors
    errors = monitor.check_for_errors()
    if errors:
        print(f"⚠️  {len(errors)} errors detected")
        monitor.send_error_alert(errors)

    # If it's end of day (3:30 PM CT), send summary
    from datetime import datetime
    now = datetime.now()
    if now.hour == 15 and now.minute >= 30:  # After market close
        print("📊 Sending daily summary...")
        monitor.send_daily_summary()


if __name__ == "__main__":
    run_monitoring_cycle()
