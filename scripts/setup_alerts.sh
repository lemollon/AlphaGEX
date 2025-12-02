#!/bin/bash
# ==========================================================================
# EMAIL ALERTS SETUP
# ==========================================================================
#
# Sets up email alerts for the SPX Wheel Trading System.
#
# Your alerts will go to: shairan2016@gmail.com
#
# To use Gmail SMTP, you need to:
# 1. Enable 2-factor authentication on your Gmail account
# 2. Create an App Password: https://myaccount.google.com/apppasswords
# 3. Use that App Password (not your regular password)
#
# ==========================================================================

echo "==========================================================================="
echo "SPX WHEEL EMAIL ALERTS SETUP"
echo "==========================================================================="
echo ""
echo "Your alert email: shairan2016@gmail.com"
echo ""

# Check if .env file exists
ENV_FILE="/home/user/AlphaGEX/.env"

if [ -f "$ENV_FILE" ]; then
    echo "Found existing .env file"
else
    echo "Creating .env file..."
    touch "$ENV_FILE"
fi

# Check for existing alert config
if grep -q "ALERT_EMAIL" "$ENV_FILE" 2>/dev/null; then
    echo "Alert email already configured in .env"
else
    echo "" >> "$ENV_FILE"
    echo "# Email Alerts Configuration" >> "$ENV_FILE"
    echo "ALERT_EMAIL=shairan2016@gmail.com" >> "$ENV_FILE"
    echo "Added ALERT_EMAIL to .env"
fi

echo ""
echo "To enable email sending, you need to configure SMTP:"
echo ""
echo "For Gmail:"
echo "  1. Go to https://myaccount.google.com/apppasswords"
echo "  2. Create an App Password for 'Mail'"
echo "  3. Add to your .env file or export:"
echo ""
echo "     export SMTP_SERVER=smtp.gmail.com"
echo "     export SMTP_PORT=587"
echo "     export SMTP_USER=your-email@gmail.com"
echo "     export SMTP_PASSWORD=your-app-password"
echo ""
echo "==========================================================================="
echo ""

# Test alert system
echo "Testing alert system..."
cd /home/user/AlphaGEX

python3 << 'EOF'
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

from trading.alerts import get_alerts, AlertLevel

alerts = get_alerts()
print(f"\nAlert Configuration:")
print(f"  Recipient: {alerts.recipient}")
print(f"  SMTP Server: {alerts.smtp_server}")
print(f"  SMTP User: {alerts.smtp_user or 'NOT CONFIGURED'}")
print(f"  SMTP Password: {'SET' if alerts.smtp_password else 'NOT SET'}")

if alerts.smtp_user and alerts.smtp_password:
    print("\nSending test email...")
    success = alerts.send_email(
        "Test Alert - SPX Wheel System",
        "This is a test alert from your SPX Wheel Trading System.\n\n"
        "If you received this, your email alerts are configured correctly!\n\n"
        "You will receive alerts for:\n"
        "- Stop loss triggers\n"
        "- Position going ITM\n"
        "- Positions expiring soon\n"
        "- Performance divergence\n"
        "- Daily trading summaries",
        AlertLevel.INFO
    )
    if success:
        print("✓ Test email sent successfully!")
    else:
        print("✗ Failed to send test email")
else:
    print("\n⚠️  Email not fully configured - alerts will be logged to console only")
    print("    Configure SMTP_USER and SMTP_PASSWORD to enable email delivery")
EOF

echo ""
echo "==========================================================================="
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Configure SMTP credentials (see above)"
echo "  2. Run the monitor: ./scripts/run_monitor.sh continuous"
echo "  3. Or set up cron job for production"
echo "==========================================================================="
