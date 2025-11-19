#!/bin/bash
# Auto-Start Script for Autonomous Trader
# Add this to your system's crontab to auto-start on boot

ALPHAGEX_DIR="/home/user/AlphaGEX"

cd "$ALPHAGEX_DIR"

# Check if already running
if [ -f "logs/trader.pid" ] && ps -p $(cat logs/trader.pid) > /dev/null 2>&1; then
    echo "Autonomous trader already running (PID: $(cat logs/trader.pid))"
    exit 0
fi

# Create logs directory
mkdir -p logs

# Start the trader
nohup python3 autonomous_scheduler.py --mode continuous > logs/trader.log 2> logs/trader.error.log &
TRADER_PID=$!

# Save PID
echo $TRADER_PID > logs/trader.pid

echo "Autonomous trader started (PID: $TRADER_PID)"
echo "Logs: $ALPHAGEX_DIR/logs/trader.log"
