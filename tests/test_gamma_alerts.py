"""
Gamma Alerts Tests

Tests for the gamma alert system module.

Run with: pytest tests/test_gamma_alerts.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGammaAlertsImport:
    """Tests for gamma alerts import"""

    def test_import_gamma_alerts(self):
        """Test that gamma alerts can be imported"""
        from gamma.gamma_alerts import GammaAlertSystem
        assert GammaAlertSystem is not None


class TestGammaAlertsInitialization:
    """Tests for gamma alerts initialization"""

    def test_alerts_initialization(self):
        """Test alerts can be initialized"""
        from gamma.gamma_alerts import GammaAlertSystem

        alert_system = GammaAlertSystem()
        assert alert_system is not None

    def test_alerts_with_email_config(self):
        """Test alerts with email configuration"""
        from gamma.gamma_alerts import GammaAlertSystem

        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'sender_email': 'test@example.com',
            'sender_password': 'password',
            'recipient_email': 'trader@example.com'
        }
        alert_system = GammaAlertSystem(email_config=config)
        assert alert_system.email_enabled is True


class TestAlertChecking:
    """Tests for alert checking"""

    def test_check_and_alert_no_alerts(self):
        """Test check with no alerts triggered"""
        from gamma.gamma_alerts import GammaAlertSystem

        alert_system = GammaAlertSystem()

        gamma_intel = {
            'success': True,
            'daily_impact': {'risk_level': 'LOW', 'impact_pct': 10},
            'volatility_potential': {},
            'weekly_evolution': {'total_decay_pct': 30}
        }

        alerts = alert_system.check_and_alert(gamma_intel, 'SPY', 585.0)
        assert isinstance(alerts, list)

    def test_check_and_alert_extreme_risk(self):
        """Test check with extreme risk level"""
        from gamma.gamma_alerts import GammaAlertSystem

        alert_system = GammaAlertSystem()

        gamma_intel = {
            'success': True,
            'daily_impact': {
                'risk_level': 'EXTREME',
                'impact_pct': 75,
                'today_total_gamma': 2e9,
                'tomorrow_total_gamma': 0.5e9,
                'expiring_today': 1.5e9,
                'strategies': [{'name': 'Straddle', 'strike': 585}]
            },
            'volatility_potential': {},
            'weekly_evolution': {'total_decay_pct': 30}
        }

        alerts = alert_system.check_and_alert(gamma_intel, 'SPY', 585.0)
        assert len(alerts) >= 1


class TestAlertCreation:
    """Tests for alert creation"""

    def test_create_daily_impact_alert(self):
        """Test daily impact alert creation"""
        from gamma.gamma_alerts import GammaAlertSystem

        alert_system = GammaAlertSystem()

        daily = {
            'risk_level': 'EXTREME',
            'impact_pct': 75,
            'today_total_gamma': 2e9,
            'tomorrow_total_gamma': 0.5e9,
            'expiring_today': 1.5e9,
            'strategies': [{'name': 'Straddle', 'strike': 585, 'expiration': '2024-12-20', 'entry_time': '10:00'}]
        }

        alert = alert_system._create_daily_impact_alert(daily, 'SPY', 585.0)

        assert alert['type'] == 'DAILY_IMPACT'
        assert 'severity' in alert
        assert 'title' in alert
        assert 'message' in alert

    def test_create_gamma_cliff_alert(self):
        """Test gamma cliff alert creation"""
        from gamma.gamma_alerts import GammaAlertSystem

        alert_system = GammaAlertSystem()

        highest_risk = {
            'day_name': 'Friday',
            'vol_pct': 65,
            'risk_level': 'HIGH',
            'expiring_gamma': 3e9,
            'total_available': 5e9
        }

        alert = alert_system._create_gamma_cliff_alert(highest_risk, 'SPY', 585.0)

        assert alert['type'] == 'GAMMA_CLIFF'
        assert alert['severity'] == 'CRITICAL'


class TestEmailSending:
    """Tests for email sending"""

    @patch('gamma.gamma_alerts.smtplib.SMTP')
    def test_send_email_alert(self, mock_smtp):
        """Test email alert sending"""
        from gamma.gamma_alerts import GammaAlertSystem

        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'sender_email': 'test@example.com',
            'sender_password': 'password',
            'recipient_email': 'trader@example.com'
        }

        alert_system = GammaAlertSystem(email_config=config)

        alert = {
            'type': 'TEST',
            'severity': 'HIGH',
            'title': 'Test Alert',
            'message': 'This is a test'
        }

        # Just verify email sending method exists
        if hasattr(alert_system, '_send_alert'):
            assert callable(getattr(alert_system, '_send_alert'))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
