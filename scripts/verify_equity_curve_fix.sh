#!/bin/bash
# Quick verification script for equity curve daily P&L aggregation fix
# Run from Render shell: bash scripts/verify_equity_curve_fix.sh

echo "========================================"
echo "EQUITY CURVE DAILY P&L AGGREGATION FIX"
echo "========================================"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we can connect to database
echo "1. Testing database connection..."
if python -c "from database_adapter import get_connection; c = get_connection(); c.close(); print('OK')" 2>/dev/null; then
    echo -e "   ${GREEN}✓ Database connection OK${NC}"
else
    echo -e "   ${RED}✗ Database connection FAILED${NC}"
    exit 1
fi

echo ""
echo "2. Checking for multi-trade days (where aggregation matters)..."
python << 'EOF'
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_adapter import get_connection

conn = get_connection()
cursor = conn.cursor()

bots = [
    ("ARES", "ares_positions"),
    ("TITAN", "titan_positions"),
    ("PEGASUS", "pegasus_positions"),
    ("ATHENA", "athena_positions"),
    ("ICARUS", "icarus_positions"),
]

GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

for bot_name, table in bots:
    cursor.execute(f"""
        SELECT
            DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') as close_date,
            COUNT(*) as trade_count
        FROM {table}
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago')
        HAVING COUNT(*) > 1
        ORDER BY close_date DESC
        LIMIT 3
    """)
    rows = cursor.fetchall()

    if rows:
        print(f"   {GREEN}{bot_name}: {len(rows)}+ days with multiple trades{NC}")
        for date, count in rows[:2]:
            print(f"      - {date}: {count} trades")
    else:
        print(f"   {YELLOW}{bot_name}: No multi-trade days found{NC}")

conn.close()
EOF

echo ""
echo "3. Running comprehensive aggregation test..."
python scripts/test_equity_curve_daily_aggregation.py

EXIT_CODE=$?

echo ""
echo "========================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}VERIFICATION COMPLETE - ALL CHECKS PASSED${NC}"
else
    echo -e "${RED}VERIFICATION FAILED - SEE ERRORS ABOVE${NC}"
fi
echo "========================================"

exit $EXIT_CODE
