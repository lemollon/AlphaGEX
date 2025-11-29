"""
Gamma Alert System - Notify users of extreme gamma events
Supports: Email, extensible to Telegram/Discord

This module provides alert logic without any UI dependencies.
"""

from datetime import datetime
import pytz
from typing import Dict, List
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logger = logging.getLogger(__name__)


class GammaAlertSystem:
    """Send alerts for extreme gamma cliff days and opportunities"""

    def __init__(self, email_config: Dict = None):
        """
        Args:
            email_config: {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'sender_email': 'your@email.com',
                'sender_password': 'app_password',
                'recipient_email': 'trader@email.com'
            }
        """
        self.email_config = email_config or {}
        self.email_enabled = bool(self.email_config.get('sender_email'))

    def check_and_alert(self, gamma_intel: Dict, symbol: str, spot_price: float) -> List[Dict]:
        """
        Check all gamma views and send alerts if needed

        Args:
            gamma_intel: Full 3-view gamma intelligence
            symbol: Ticker
            spot_price: Current price

        Returns:
            List of alert dictionaries
        """
        alerts = []

        if not gamma_intel.get('success'):
            return alerts

        # Check View 1: Daily Impact
        daily = gamma_intel['daily_impact']
        if daily['risk_level'] in ['EXTREME', 'ELEVATED']:
            alerts.append(self._create_daily_impact_alert(daily, symbol, spot_price))

        # Check View 3: Highest risk day this week
        vol_potential = gamma_intel['volatility_potential']
        highest_risk = vol_potential.get('highest_risk_day')

        if highest_risk and highest_risk['vol_pct'] > 60:
            # Calculate days until
            current_day = gamma_intel.get('current_day')
            highest_day = highest_risk['day_name']

            # If tomorrow or today
            if highest_risk['is_today'] or self._is_tomorrow(current_day, highest_day):
                alerts.append(self._create_gamma_cliff_alert(highest_risk, symbol, spot_price))

        # Check View 2: Major weekly decay (>70%)
        weekly = gamma_intel['weekly_evolution']
        if weekly['total_decay_pct'] > 70:
            alerts.append(self._create_weekly_decay_alert(weekly, symbol))

        # Send all alerts
        for alert in alerts:
            self._send_alert(alert)

        return alerts

    def _create_daily_impact_alert(self, daily: Dict, symbol: str, spot_price: float) -> Dict:
        """Create alert for extreme daily gamma decay"""
        return {
            'type': 'DAILY_IMPACT',
            'severity': 'HIGH' if daily['risk_level'] == 'EXTREME' else 'MEDIUM',
            'title': f"🚨 {daily['risk_level']} Gamma Decay: {symbol}",
            'message': f"""
{symbol} @ ${spot_price:.2f}

**Today's Gamma Decay: {daily['impact_pct']:.0f}%**
Risk Level: {daily['risk_level']}

Current Gamma: ${daily['today_total_gamma']/1e9:.2f}B
After 4pm: ${daily['tomorrow_total_gamma']/1e9:.2f}B
Expiring Today: ${daily['expiring_today']/1e9:.2f}B

**Top Strategy:**
{daily['strategies'][0]['name'] if daily['strategies'] else 'Review dashboard'}

Strike: {daily['strategies'][0].get('strike', 'N/A')}
Expiration: {daily['strategies'][0].get('expiration', 'N/A')}
Entry: {daily['strategies'][0].get('entry_time', 'N/A')}

⚠️ Tomorrow's market will have {daily['impact_pct']:.0f}% less gamma support.
Expect sharper directional moves.
            """.strip(),
            'action_url': f'/AlphaGEX?symbol={symbol}'
        }

    def _create_gamma_cliff_alert(self, highest_risk: Dict, symbol: str, spot_price: float) -> Dict:
        """Create alert for upcoming gamma cliff day"""
        return {
            'type': 'GAMMA_CLIFF',
            'severity': 'CRITICAL',
            'title': f"🔶 Gamma Cliff Coming: {symbol}",
            'message': f"""
{symbol} @ ${spot_price:.2f}

**{highest_risk['day_name']}: {highest_risk['vol_pct']:.0f}% Gamma Decay**
Risk Level: {highest_risk['risk_level']}

This is a MAJOR gamma expiration day.

Expiring: ${highest_risk['expiring_gamma']/1e9:.2f}B
Total Available: ${highest_risk['total_available']/1e9:.2f}B

⚠️ Prepare for volatility spike on {highest_risk['day_name']}.

**Recommended Actions:**
1. Reduce position size 30-50%
2. Widen stop losses
3. Consider ATM straddle for vol capture
4. Or sit in cash if uncomfortable

Check dashboard for specific strategies.
            """.strip(),
            'action_url': f'/AlphaGEX?symbol={symbol}'
        }

    def _create_weekly_decay_alert(self, weekly: Dict, symbol: str) -> Dict:
        """Create alert for major weekly gamma decay"""
        return {
            'type': 'WEEKLY_DECAY',
            'severity': 'MEDIUM',
            'title': f"📊 Major OPEX Week: {symbol}",
            'message': f"""
{symbol} - High Gamma Decay Week

**Total Weekly Decay: {weekly['total_decay_pct']:.0f}%**
Pattern: {weekly['decay_pattern']}

Monday: ${weekly['monday_baseline']/1e9:.2f}B (100%)
Friday: ${weekly['friday_end']/1e9:.2f}B ({weekly['daily_breakdown'][-1]['pct_of_week']:.0f}%)

**Trading Plan:**
- Early Week (Mon-Wed): Sell premium, iron condors
- Late Week (Thu-Fri): Switch to directional, buy delta

This is a major OPEX week. Plan your week accordingly.
            """.strip(),
            'action_url': f'/AlphaGEX?symbol={symbol}'
        }

    def _send_alert(self, alert: Dict):
        """Send alert via all enabled channels"""
        # Log the alert
        self._log_alert(alert)

        # Email (if configured)
        if self.email_enabled:
            try:
                self._send_email_alert(alert)
            except Exception as e:
                logger.warning(f"Could not send email alert: {e}")

    def _log_alert(self, alert: Dict):
        """Log alert to logger"""
        severity = alert.get('severity', 'INFO')
        title = alert.get('title', 'Alert')
        message = alert.get('message', '')

        if severity == 'CRITICAL':
            logger.critical(f"{title}\n{message}")
        elif severity == 'HIGH':
            logger.error(f"{title}\n{message}")
        elif severity == 'MEDIUM':
            logger.warning(f"{title}\n{message}")
        else:
            logger.info(f"{title}\n{message}")

    def _send_email_alert(self, alert: Dict):
        """Send email alert"""
        if not self.email_enabled:
            return

        msg = MIMEMultipart('alternative')
        msg['Subject'] = alert['title']
        msg['From'] = self.email_config['sender_email']
        msg['To'] = self.email_config['recipient_email']

        # Plain text version
        text_body = alert['message']

        # HTML version
        html_body = f"""
<html>
  <body style='font-family: Arial, sans-serif; color: #333;'>
    <h2 style='color: {"#FF4444" if alert["severity"] == "CRITICAL" else "#FFB800"};'>
        {alert['title']}
    </h2>
    <div style='white-space: pre-wrap; line-height: 1.6;'>
        {alert['message']}
    </div>
    <hr>
    <p><small>Generated by AlphaGEX at {datetime.now(pytz.timezone('America/New_York')).strftime('%Y-%m-%d %I:%M %p ET')}</small></p>
  </body>
</html>
        """

        part1 = MIMEText(text_body, 'plain')
        part2 = MIMEText(html_body, 'html')

        msg.attach(part1)
        msg.attach(part2)

        # Send
        with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
            server.starttls()
            server.login(self.email_config['sender_email'], self.email_config['sender_password'])
            server.send_message(msg)

    def _is_tomorrow(self, current_day: str, target_day: str) -> bool:
        """Check if target_day is tomorrow relative to current_day"""
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

        if current_day not in days_order or target_day not in days_order:
            return False

        current_idx = days_order.index(current_day)
        target_idx = days_order.index(target_day)

        return (target_idx - current_idx) == 1 or (current_idx == 4 and target_idx == 0)


# Usage example:
"""
# In your trading code:

alert_system = GammaAlertSystem(email_config={
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': os.environ.get('ALERT_EMAIL'),
    'sender_password': os.environ.get('ALERT_PASSWORD'),
    'recipient_email': os.environ.get('TRADER_EMAIL')
})

# Check for alerts
alerts = alert_system.check_and_alert(gamma_intel, symbol='SPY', spot_price=585.25)

# Alerts are automatically logged and emailed
"""
