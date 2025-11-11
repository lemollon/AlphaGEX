#!/bin/bash
# Streamlit App Restart Script
# This script helps restart the Streamlit app to pick up code changes

set -e

echo "======================================================================="
echo "🔄 STREAMLIT APP RESTART UTILITY"
echo "======================================================================="
echo ""

# Check if we're in the right directory
if [ ! -f "gex_copilot.py" ]; then
    echo "❌ Error: gex_copilot.py not found"
    echo "   Please run this script from the AlphaGEX root directory"
    exit 1
fi

# Clear Python cache to ensure fresh code
echo "🧹 Step 1: Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
echo "   ✅ Cache cleared"
echo ""

# Show current code version
echo "📋 Step 2: Verifying code version..."
echo "   Git commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "   Git branch: $(git branch --show-current 2>/dev/null || echo 'unknown')"

# Check if directional prediction code exists
if grep -q "SPY DIRECTIONAL FORECAST" gex_copilot.py; then
    echo "   ✅ Directional prediction code found in gex_copilot.py"
else
    echo "   ❌ Directional prediction code NOT found!"
    echo "      You may need to pull the latest code."
    exit 1
fi
echo ""

# Check for running Streamlit processes
echo "🔍 Step 3: Checking for running Streamlit processes..."
STREAMLIT_PIDS=$(pgrep -f "streamlit run" 2>/dev/null || echo "")

if [ -n "$STREAMLIT_PIDS" ]; then
    echo "   Found running Streamlit processes:"
    ps aux | grep "streamlit run" | grep -v grep
    echo ""
    echo "   💀 Killing existing Streamlit processes..."
    kill -9 $STREAMLIT_PIDS 2>/dev/null || true
    sleep 2
    echo "   ✅ Old processes terminated"
else
    echo "   ℹ️  No running Streamlit processes found"
fi
echo ""

# Offer to start the app
echo "======================================================================="
echo "🚀 READY TO START"
echo "======================================================================="
echo ""
echo "The app is ready to run with the latest code."
echo ""
echo "Start the Streamlit app with:"
echo "  streamlit run gex_copilot.py"
echo ""
echo "Or start it in the background:"
echo "  nohup streamlit run gex_copilot.py --server.port 8501 > streamlit.log 2>&1 &"
echo ""
echo "Note: If your app is deployed on Streamlit Cloud or another hosting"
echo "      platform, you'll need to restart it through their interface."
echo ""
echo "======================================================================="
echo ""

read -p "Would you like to start the Streamlit app now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 Starting Streamlit app..."
    echo "   Press Ctrl+C to stop the app"
    echo ""
    streamlit run gex_copilot.py
fi
