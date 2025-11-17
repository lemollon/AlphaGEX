#!/bin/bash
# Test the Autonomous Trader - Manual Dry Run

set -e

echo "================================================"
echo "🧪 Autonomous Trader Test Run"
echo "================================================"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "✓ Activating virtual environment..."
    source venv/bin/activate
fi

# Set test mode environment variable
export TRADER_TEST_MODE=true

echo "🤖 Running autonomous trader test cycle..."
echo "   This will:"
echo "   - Initialize the trader"
echo "   - Create database if needed"
echo "   - Fetch live GEX data"
echo "   - Analyze market conditions"
echo "   - Log decision-making process"
echo "   - NOT execute real trades (test mode)"
echo ""

python3 << 'EOF'
import sys
import traceback
from datetime import datetime

print(f"⏰ Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

try:
    # Import required modules
    print("📦 Importing modules...")
    from autonomous_paper_trader import AutonomousPaperTrader
    from core_classes_and_engines import TradingVolatilityAPI
    print("✅ Imports successful\n")

    # Initialize trader
    print("🤖 Initializing autonomous trader...")
    trader = AutonomousPaperTrader()
    print(f"✅ Trader initialized")
    print(f"   Database: {trader.db_path}")
    print(f"   Capital: ${trader.capital:,.2f}")
    print(f"   Mode: {trader.mode}\n")

    # Initialize API client
    print("📡 Initializing API client...")
    api_client = TradingVolatilityAPI()
    print("✅ API client ready\n")

    # Update live status
    print("📊 Updating live status...")
    trader.update_live_status(
        status='TESTING',
        action='Running test cycle',
        analysis='Manual test run initiated'
    )
    print("✅ Status updated\n")

    # Try to fetch GEX data
    print("📈 Fetching SPY GEX data...")
    try:
        gex_data = api_client.get_net_gamma('SPY')
        if gex_data and 'error' not in gex_data:
            print("✅ GEX data received:")
            print(f"   Net GEX: ${gex_data.get('net_gex', 0)/1e9:.2f}B")
            print(f"   Spot Price: ${gex_data.get('spot_price', 0):.2f}")
            print(f"   Flip Point: ${gex_data.get('flip_point', 0):.2f}")
            print(f"   Call Wall: ${gex_data.get('call_wall', 0):.2f}")
            print(f"   Put Wall: ${gex_data.get('put_wall', 0):.2f}")
        else:
            print(f"⚠️  API returned error: {gex_data.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"⚠️  Failed to fetch GEX data: {e}")

    print("\n" + "="*50)
    print("✅ TEST COMPLETE")
    print("="*50)
    print("\n📝 Next steps:")
    print("   1. Check database: ls -lh autonomous_trader.db")
    print("   2. View logs: sqlite3 autonomous_trader.db 'SELECT * FROM autonomous_trader_logs LIMIT 5'")
    print("   3. Deploy with: ./deploy_autonomous_trader.sh")

except Exception as e:
    print(f"\n❌ TEST FAILED")
    print(f"Error: {e}")
    print("\nStack trace:")
    traceback.print_exc()
    sys.exit(1)

EOF

echo ""
echo "================================================"
echo "Test run complete!"
echo "================================================"
