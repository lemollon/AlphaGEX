#!/bin/bash
# ==========================================================================
# SPX WHEEL POSITION MONITOR
# ==========================================================================
#
# CRITICAL COMPONENT - This monitors your positions for:
# - Stop loss conditions (closes position if threshold breached)
# - ITM warnings (alerts when position goes in-the-money)
# - Expiration warnings (alerts when position approaching expiry)
# - Position reconciliation (verifies DB matches broker)
#
# USAGE:
#   ./run_monitor.sh              # Run once (for cron jobs)
#   ./run_monitor.sh continuous   # Run continuously (background process)
#   ./run_monitor.sh live         # LIVE MODE - will execute stop losses!
#   ./run_monitor.sh continuous live  # Continuous + live
#
# RECOMMENDED SETUP:
#   1. For development: ./run_monitor.sh continuous
#   2. For production: Set up as cron job every 5 minutes
#
# CRON EXAMPLE (run every 5 minutes during market hours):
#   */5 9-16 * * 1-5 /home/user/AlphaGEX/scripts/run_monitor.sh >> /var/log/spx_monitor.log 2>&1
#
# ==========================================================================

# Parse arguments
MODE="paper"
CONTINUOUS=false

for arg in "$@"; do
    case $arg in
        continuous)
            CONTINUOUS=true
            ;;
        live)
            MODE="live"
            ;;
    esac
done

echo "==========================================================================="
echo "SPX WHEEL POSITION MONITOR"
echo "==========================================================================="
echo "Time: $(date)"
echo "Mode: ${MODE^^}"
echo "Continuous: $CONTINUOUS"
echo ""

# Check environment
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    exit 1
fi

# Warning for live mode
if [ "$MODE" == "live" ]; then
    echo "🔴 LIVE MODE - STOP LOSSES WILL BE EXECUTED!"
    if [ "$CONTINUOUS" != true ]; then
        read -p "Continue? (yes/no): " CONFIRM
        if [ "$CONFIRM" != "yes" ]; then
            echo "Aborting."
            exit 0
        fi
    fi
fi

cd /home/user/AlphaGEX

if [ "$CONTINUOUS" == true ]; then
    echo "Starting continuous monitoring (Ctrl+C to stop)..."
    echo "Check interval: 300 seconds (5 minutes)"
    echo "==========================================================================="
    python3 trading/position_monitor.py --continuous --mode $MODE --interval 300
else
    echo "Running single monitoring cycle..."
    echo "==========================================================================="
    python3 trading/position_monitor.py --mode $MODE --once
fi
