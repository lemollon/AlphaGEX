#!/bin/bash
# Deploy Autonomous Trader as Background Service

set -e

echo "================================================"
echo "🚀 Deploying Autonomous Trader"
echo "================================================"
echo ""

# Check if running as root for systemd
if [ "$EUID" -eq 0 ]; then
    USE_SYSTEMD=true
    echo "✓ Running as root - will use systemd service"
else
    USE_SYSTEMD=false
    echo "✓ Running as user - will use screen/nohup"
fi

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✓ Virtual environment activated"
fi

WORK_DIR=$(pwd)
echo "✓ Working directory: $WORK_DIR"

if [ "$USE_SYSTEMD" = true ]; then
    # Create systemd service
    echo "📝 Creating systemd service..."

    cat > /etc/systemd/system/alphagex-trader.service << EOSERVICE
[Unit]
Description=AlphaGEX Autonomous Trader
After=network.target

[Service]
Type=simple
User=$SUDO_USER
WorkingDirectory=$WORK_DIR
Environment="PATH=$WORK_DIR/venv/bin:/usr/local/bin:/usr/bin"
ExecStart=$WORK_DIR/venv/bin/python3 $WORK_DIR/autonomous_scheduler.py
Restart=always
RestartSec=10
StandardOutput=append:$WORK_DIR/logs/trader.log
StandardError=append:$WORK_DIR/logs/trader.error.log

[Install]
WantedBy=multi-user.target
EOSERVICE

    # Create logs directory
    mkdir -p $WORK_DIR/logs
    chown -R $SUDO_USER:$SUDO_USER $WORK_DIR/logs

    # Reload systemd
    systemctl daemon-reload

    # Enable and start service
    systemctl enable alphagex-trader.service
    systemctl start alphagex-trader.service

    echo "✅ Systemd service created and started"
    echo ""
    echo "Useful commands:"
    echo "  - Status: sudo systemctl status alphagex-trader"
    echo "  - Logs: sudo journalctl -u alphagex-trader -f"
    echo "  - Stop: sudo systemctl stop alphagex-trader"
    echo "  - Restart: sudo systemctl restart alphagex-trader"

else
    # Use screen or nohup for non-root deployment
    echo "📝 Deploying as background process..."

    # Create logs directory
    mkdir -p logs

    # Check if screen is available
    if command -v screen &> /dev/null; then
        echo "✓ Using screen for background process"
        screen -dmS alphagex-trader bash -c "source venv/bin/activate && python3 autonomous_scheduler.py > logs/trader.log 2> logs/trader.error.log"
        echo "✅ Started in screen session 'alphagex-trader'"
        echo ""
        echo "Useful commands:"
        echo "  - Attach: screen -r alphagex-trader"
        echo "  - Detach: Ctrl+A, then D"
        echo "  - Kill: screen -X -S alphagex-trader quit"
        echo "  - Logs: tail -f logs/trader.log"
    else
        echo "✓ Using nohup for background process"
        nohup python3 autonomous_scheduler.py > logs/trader.log 2> logs/trader.error.log &
        TRADER_PID=$!
        echo $TRADER_PID > logs/trader.pid
        echo "✅ Started with PID: $TRADER_PID"
        echo ""
        echo "Useful commands:"
        echo "  - Logs: tail -f logs/trader.log"
        echo "  - Stop: kill \$(cat logs/trader.pid)"
        echo "  - Status: ps -p \$(cat logs/trader.pid)"
    fi
fi

echo ""
echo "================================================"
echo "✅ Deployment Complete!"
echo "================================================"
echo ""
echo "📊 Monitor at: http://localhost:8000/api/autonomous/health"
echo "📈 Dashboard at: http://localhost:3000/trader"
echo ""
