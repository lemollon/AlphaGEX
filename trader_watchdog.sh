#!/bin/bash
# Trader Watchdog - Ensures autonomous trader is ALWAYS running
# This script checks every minute if the trader is running
# If not, it starts it automatically

ALPHAGEX_DIR="/home/user/AlphaGEX"
TRADER_PID_FILE="$ALPHAGEX_DIR/logs/trader.pid"
TRADER_LOG="$ALPHAGEX_DIR/logs/trader.log"
WATCHDOG_LOG="$ALPHAGEX_DIR/logs/watchdog.log"

cd "$ALPHAGEX_DIR"

# Create logs directory
mkdir -p logs

# Function to check if trader is running
is_trader_running() {
    if [ -f "$TRADER_PID_FILE" ]; then
        PID=$(cat "$TRADER_PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            return 0  # Running
        fi
    fi
    return 1  # Not running
}

# Function to start trader
start_trader() {
    echo "[$(date)] Starting autonomous trader..." >> "$WATCHDOG_LOG"

    nohup python3 autonomous_scheduler.py --mode continuous > "$TRADER_LOG" 2> logs/trader.error.log &
    TRADER_PID=$!
    echo $TRADER_PID > "$TRADER_PID_FILE"

    echo "[$(date)] Trader started with PID: $TRADER_PID" >> "$WATCHDOG_LOG"
}

# Main watchdog logic
if is_trader_running; then
    # Trader is running - do nothing (silent)
    exit 0
else
    # Trader is NOT running - start it
    echo "[$(date)] Trader not running - starting..." >> "$WATCHDOG_LOG"
    start_trader
fi
