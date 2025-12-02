#!/bin/bash
# AlphaGEX System Verification Script
# Checks all systems and credentials are working

echo "=============================================="
echo "ALPHAGEX SYSTEM VERIFICATION"
echo "=============================================="
echo "Time: $(date)"
echo ""

# Check environment variables
echo "=== ENVIRONMENT CHECK ==="
if [ -n "$DATABASE_URL" ]; then
    echo "DATABASE_URL: SET"
else
    echo "DATABASE_URL: NOT SET - CRITICAL!"
fi

if [ -n "$POLYGON_API_KEY" ]; then
    echo "POLYGON_API_KEY: SET (${#POLYGON_API_KEY} chars)"
else
    echo "POLYGON_API_KEY: NOT SET"
fi

if [ -n "$TRADIER_API_KEY" ]; then
    echo "TRADIER_API_KEY: SET"
else
    echo "TRADIER_API_KEY: NOT SET"
fi

if [ -n "$TRADING_VOLATILITY_API_KEY" ]; then
    echo "TRADING_VOLATILITY_API_KEY: SET"
else
    echo "TRADING_VOLATILITY_API_KEY: NOT SET"
fi

echo ""
echo "=== DATABASE CONNECTION TEST ==="
python3 << 'EOF'
import os
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
    count = cursor.fetchone()[0]
    print(f"Database connected! {count} tables found")

    # List some key tables
    cursor.execute("""
        SELECT table_name,
               (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as cols
        FROM information_schema.tables t
        WHERE table_schema = 'public'
        ORDER BY table_name
        LIMIT 15
    """)
    print("\nKey tables:")
    for row in cursor.fetchall():
        print(f"  - {row[0]} ({row[1]} columns)")

    conn.close()
except Exception as e:
    print(f"Database connection FAILED: {e}")
EOF

echo ""
echo "=== POLYGON API TEST ==="
python3 << 'EOF'
import os
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

try:
    from data.polygon_data_fetcher import polygon_fetcher

    # Test spot price fetch
    price = polygon_fetcher.get_current_price('SPY')
    if price and price > 0:
        print(f"Polygon API working! SPY price: ${price:.2f}")
    else:
        print("Polygon API: Could not fetch SPY price")

    # Test SPX price
    spx_price = polygon_fetcher.get_current_price('SPX')
    if spx_price and spx_price > 0:
        print(f"SPX price: ${spx_price:.2f}")
    else:
        # Try alternate symbols
        for sym in ['^SPX', '$SPX.X', 'I:SPX']:
            spx_price = polygon_fetcher.get_current_price(sym)
            if spx_price and spx_price > 0:
                print(f"SPX price ({sym}): ${spx_price:.2f}")
                break
        else:
            print("SPX: Could not fetch price (may need different symbol)")

except Exception as e:
    print(f"Polygon API test FAILED: {e}")
EOF

echo ""
echo "=== OPTION DATA TEST ==="
python3 << 'EOF'
import os
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

try:
    from data.polygon_data_fetcher import polygon_fetcher

    # Test options chain
    chain = polygon_fetcher.get_options_chain('SPY')
    if chain and 'options' in chain:
        print(f"Options chain working! {len(chain.get('options', []))} contracts found")
    else:
        print("Options chain: No data returned")

except Exception as e:
    print(f"Options data test FAILED: {e}")
EOF

echo ""
echo "=== DECISION LOGGER TEST ==="
python3 << 'EOF'
import os
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

try:
    from trading.decision_logger import DecisionLogger
    from trading.autonomous_decision_bridge import DecisionBridge

    logger = DecisionLogger()
    bridge = DecisionBridge()
    print("Decision logger and bridge initialized successfully")

except Exception as e:
    print(f"Decision logger test FAILED: {e}")
EOF

echo ""
echo "=== BACKTEST MODULE TEST ==="
python3 << 'EOF'
import os
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

try:
    from backtest.real_wheel_backtest import RealWheelBacktester
    from backtest.spx_premium_backtest import SPXPremiumBacktester

    print("SPY Wheel Backtester: OK")
    print("SPX Premium Backtester: OK")

except Exception as e:
    print(f"Backtest module test FAILED: {e}")
EOF

echo ""
echo "=============================================="
echo "VERIFICATION COMPLETE"
echo "=============================================="
