#!/bin/bash
# AlphaGEX API Startup Script for Render
# This ensures all dependencies are in the right place

set -e  # Exit on error

echo "🚀 Starting AlphaGEX API..."

# Ensure we're in the project root
cd "$(dirname "$0")"

# CRITICAL: Ensure yfinance is installed for VIX data
echo "📦 Ensuring yfinance is installed..."
pip install --quiet yfinance || echo "⚠️ yfinance install failed"

# Test VIX fetch at startup
echo "🔍 Testing VIX fetch..."
python3 -c "
import yfinance as yf
vix = yf.Ticker('^VIX')
hist = vix.history(period='5d')
if not hist.empty:
    price = hist['Close'].iloc[-1]
    print(f'✅ VIX Price: {price:.2f}')
else:
    print('❌ VIX fetch returned empty data')
" 2>&1 || echo "⚠️ VIX test failed - will use fallback"

# CRITICAL: Set PYTHONPATH to include project root
# This ensures all internal modules (utils, core, data, etc.) are importable
# Fixes "ModuleNotFoundError: No module named 'utils.logging_config'" on Render
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)"
echo "📁 PYTHONPATH: $PYTHONPATH"

# CRITICAL: Clear Python bytecode cache to ensure fresh code
echo "🧹 Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Verification: Show what code version is deployed
echo "📋 Deployment Verification:"
echo "Git commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "Git branch: $(git branch --show-current 2>/dev/null || echo 'unknown')"
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo ""

# Check if backend directory exists
if [ -d "backend" ]; then
    echo "✅ Backend directory found"
    ls -la backend/*.py | head -5
else
    echo "❌ Backend directory not found!"
    exit 1
fi

# Check for required environment variables
echo "🔍 Checking environment variables..."
if [ -z "$TRADING_VOLATILITY_API_KEY" ]; then
    echo "⚠️  WARNING: TRADING_VOLATILITY_API_KEY not set"
fi
if [ -z "$TV_USERNAME" ]; then
    echo "⚠️  WARNING: TV_USERNAME not set"
fi
echo ""

# Start the FastAPI server.
# WEB_CONCURRENCY controls worker count. Default 4 — single-worker default
# was the bottleneck behind p99 latency spiking to 35-38s when the 5 perp
# dashboards each fired multiple sync calls into CoinGlass / Anthropic.
echo "🚀 Starting FastAPI server on port ${PORT:-8000} with ${WEB_CONCURRENCY:-4} workers..."
python -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-4} \
    --log-level info \
    --access-log
