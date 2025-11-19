#!/bin/bash
# AlphaGEX Data Collector Management Script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_NAME="alphagex-collector"
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$LOG_DIR/collector.pid"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}=====================================================================${NC}"
    echo -e "${BLUE}  AlphaGEX Data Collector Manager${NC}"
    echo -e "${BLUE}=====================================================================${NC}"
}

start_collector() {
    echo -e "\n${YELLOW}Starting data collector...${NC}"

    # Check if already running
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${RED}✗ Collector is already running (PID: $PID)${NC}"
            return 1
        else
            rm "$PID_FILE"
        fi
    fi

    # Start the collector in background
    cd "$SCRIPT_DIR"
    nohup python3 automated_data_collector.py > "$LOG_DIR/data_collector.log" 2>&1 &
    echo $! > "$PID_FILE"

    sleep 2

    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Data collector started successfully (PID: $(cat $PID_FILE))${NC}"
        echo -e "  Logs: $LOG_DIR/data_collector.log"
        echo -e "  Use './manage_collector.sh logs' to view output"
    else
        echo -e "${RED}✗ Failed to start data collector${NC}"
        rm "$PID_FILE"
        return 1
    fi
}

stop_collector() {
    echo -e "\n${YELLOW}Stopping data collector...${NC}"

    if [ ! -f "$PID_FILE" ]; then
        echo -e "${RED}✗ Collector is not running (no PID file found)${NC}"
        return 1
    fi

    PID=$(cat "$PID_FILE")

    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        sleep 2

        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠ Forcing stop...${NC}"
            kill -9 $PID
        fi

        rm "$PID_FILE"
        echo -e "${GREEN}✓ Data collector stopped${NC}"
    else
        echo -e "${RED}✗ Collector process not found (stale PID file)${NC}"
        rm "$PID_FILE"
    fi
}

status_collector() {
    echo -e "\n${YELLOW}Checking collector status...${NC}"

    if [ ! -f "$PID_FILE" ]; then
        echo -e "${RED}✗ Status: Not Running${NC}"
        return 1
    fi

    PID=$(cat "$PID_FILE")

    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Status: Running (PID: $PID)${NC}"

        # Show recent activity
        if [ -f "$LOG_DIR/data_collector.log" ]; then
            echo -e "\n${BLUE}Recent Activity:${NC}"
            tail -15 "$LOG_DIR/data_collector.log" | grep -E "(Running|completed|failed|Skipping)" | tail -5
        fi

        # Show uptime
        START_TIME=$(ps -p $PID -o lstart=)
        echo -e "\n${BLUE}Started:${NC} $START_TIME"

    else
        echo -e "${RED}✗ Status: Not Running (stale PID file)${NC}"
        rm "$PID_FILE"
        return 1
    fi
}

view_logs() {
    echo -e "\n${YELLOW}Showing live logs (Ctrl+C to exit)...${NC}\n"

    if [ ! -f "$LOG_DIR/data_collector.log" ]; then
        echo -e "${RED}✗ Log file not found${NC}"
        return 1
    fi

    tail -f "$LOG_DIR/data_collector.log"
}

restart_collector() {
    stop_collector
    sleep 1
    start_collector
}

install_service() {
    echo -e "\n${YELLOW}Installing systemd service...${NC}"

    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}✗ Please run with sudo: sudo ./manage_collector.sh install${NC}"
        return 1
    fi

    # Copy service file
    cp "$SCRIPT_DIR/alphagex-collector.service" /etc/systemd/system/

    # Reload systemd
    systemctl daemon-reload

    # Enable service
    systemctl enable alphagex-collector.service

    echo -e "${GREEN}✓ Service installed and enabled${NC}"
    echo -e "  Start with: sudo systemctl start alphagex-collector"
    echo -e "  Status: sudo systemctl status alphagex-collector"
    echo -e "  Logs: sudo journalctl -u alphagex-collector -f"
}

show_help() {
    print_header
    echo -e "\n${BLUE}Usage:${NC} ./manage_collector.sh [command]"
    echo -e "\n${BLUE}Commands:${NC}"
    echo -e "  ${GREEN}start${NC}       Start the data collector"
    echo -e "  ${GREEN}stop${NC}        Stop the data collector"
    echo -e "  ${GREEN}restart${NC}     Restart the data collector"
    echo -e "  ${GREEN}status${NC}      Check collector status"
    echo -e "  ${GREEN}logs${NC}        View live logs"
    echo -e "  ${GREEN}install${NC}     Install as systemd service (requires sudo)"
    echo -e "  ${GREEN}help${NC}        Show this help message"
    echo ""
}

# Main
print_header

case "$1" in
    start)
        start_collector
        ;;
    stop)
        stop_collector
        ;;
    restart)
        restart_collector
        ;;
    status)
        status_collector
        ;;
    logs)
        view_logs
        ;;
    install)
        install_service
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac

exit 0
