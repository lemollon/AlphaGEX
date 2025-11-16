#!/bin/bash
# Quick status check for Autonomous Trader

echo "================================================"
echo "🤖 Autonomous Trader Status Check"
echo "================================================"
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Get current Central Time
CT_TIME=$(TZ="America/Chicago" date "+%I:%M %p CT, %A %B %d, %Y")
echo "⏰ Current Time: $CT_TIME"
echo ""

# Check if systemd service is running
if systemctl is-active --quiet alphagex-trader 2>/dev/null; then
    echo "✅ Service Status: RUNNING (systemd)"
    echo "   Command: sudo systemctl status alphagex-trader"
    echo ""

    # Show recent logs
    echo "📜 Recent Activity (last 10 lines):"
    sudo journalctl -u alphagex-trader -n 10 --no-pager

elif ps aux | grep -q "[p]ython.*autonomous_scheduler" 2>/dev/null; then
    PID=$(ps aux | grep "[p]ython.*autonomous_scheduler" | awk '{print $2}')
    echo "✅ Service Status: RUNNING (PID: $PID)"

    # Check if using screen
    if screen -ls | grep -q alphagex-trader; then
        echo "   Type: Screen session"
        echo "   Command: screen -r alphagex-trader"
    else
        echo "   Type: Background process"
        echo "   Command: kill $PID (to stop)"
    fi
    echo ""

    # Show recent logs if available
    if [ -f "logs/trader.log" ]; then
        echo "📜 Recent Activity (last 10 lines):"
        tail -n 10 logs/trader.log
    fi

else
    echo "❌ Service Status: NOT RUNNING"
    echo ""
    echo "To start:"
    echo "   sudo ./deploy_autonomous_trader.sh"
    echo "   OR"
    echo "   python3 autonomous_scheduler.py"
fi

echo ""
echo "================================================"
echo "Database Info"
echo "================================================"

# Check if database exists
if [ -f "autonomous_trader.db" ]; then
    echo "✅ Database: autonomous_trader.db"

    # Get database stats
    python3 << 'PYEOF'
import sqlite3
from datetime import datetime

try:
    conn = sqlite3.connect('autonomous_trader.db')
    cursor = conn.cursor()

    # Get trade count
    cursor.execute("SELECT COUNT(*) FROM trades")
    total_trades = cursor.fetchone()[0]

    # Get today's trades
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM trades WHERE DATE(timestamp) = ?", (today,))
    today_trades = cursor.fetchone()[0]

    # Get total P&L
    cursor.execute("SELECT SUM(realized_pnl) FROM trades WHERE realized_pnl IS NOT NULL")
    total_pnl = cursor.fetchone()[0] or 0

    # Get last trade
    cursor.execute("SELECT timestamp, symbol, action, option_type, strike FROM trades ORDER BY timestamp DESC LIMIT 1")
    last_trade = cursor.fetchone()

    print(f"   Total Trades: {total_trades}")
    print(f"   Today's Trades: {today_trades}")
    print(f"   Total P&L: ${total_pnl:+,.2f}")

    if last_trade:
        print(f"\n   Last Trade:")
        print(f"      {last_trade[0]}")
        print(f"      {last_trade[1]} {last_trade[2]} {last_trade[3]} ${last_trade[4]}")

    conn.close()

except Exception as e:
    print(f"   Error reading database: {e}")
PYEOF

else
    echo "⚠️  Database: Not found (will be created on first run)"
fi

echo ""
echo "================================================"
echo "Market Hours Info"
echo "================================================"

# Check market hours
python3 << 'PYEOF'
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

def is_market_hours():
    ct_now = datetime.now(ZoneInfo("America/Chicago"))
    if ct_now.weekday() >= 5:  # Weekend
        return False
    return dt_time(8, 30) <= ct_now.time() <= dt_time(15, 0)

ct_now = datetime.now(ZoneInfo("America/Chicago"))
is_open = is_market_hours()

if is_open:
    print("🟢 Market Status: OPEN")
    print("   Active trading hours (8:30 AM - 3:00 PM CT)")
else:
    print("🔴 Market Status: CLOSED")
    if ct_now.weekday() >= 5:
        print("   Weekend - Market opens Monday 8:30 AM CT")
    elif ct_now.time() < dt_time(8, 30):
        print("   Pre-market - Opens at 8:30 AM CT")
    else:
        print("   After-hours - Next open: Tomorrow 8:30 AM CT")
PYEOF

echo ""
echo "================================================"
echo "Quick Commands"
echo "================================================"
echo "View logs:   tail -f logs/trader.log"
echo "Stop trader: sudo systemctl stop alphagex-trader"
echo "Start trader: sudo systemctl start alphagex-trader"
echo "Dashboard:   http://localhost:3000/trader"
echo "================================================"
