#!/bin/bash
# Start Autonomous Trader - Test Mode
# Run this to start your auto trader locally

echo "🤖 Starting AlphaGEX Autonomous Trader..."
echo ""

# Check if database exists
if [ ! -f "gex_copilot.db" ]; then
    echo "📁 Database doesn't exist - will be created on first run"
fi

echo "⚙️  Configuration:"
echo "   - Starting Capital: $5,000"
echo "   - Max Position Size: 25% ($1,250)"
echo "   - Symbol: SPY"
echo "   - Mode: Paper Trading"
echo ""

echo "🚀 Starting trader in continuous mode..."
echo "   (Press Ctrl+C to stop)"
echo ""

# Run the autonomous scheduler in continuous mode
python3 autonomous_scheduler.py --mode continuous --interval 5

# Note: This will:
# 1. Check for trade opportunities ALL DAY every 5 minutes (9:30 AM - 4:00 PM ET / 8:30 AM - 3:00 PM CT)
# 2. Execute ONE trade per day (automatic daily limiting built-in)
# 3. Manage positions continuously every 5 minutes during market hours
# 4. Log everything to database with full state persistence
