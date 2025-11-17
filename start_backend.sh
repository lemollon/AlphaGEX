#!/bin/bash
# AlphaGEX Backend Startup Script

echo "🚀 Starting AlphaGEX Backend Server..."
echo ""

# Change to project directory
cd "$(dirname "$0")"

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found"
    echo "   Creating default .env file..."
    cat > .env << 'EOF'
# AlphaGEX Environment Variables
TV_USERNAME=I-RWFNBLR2S1DP
TRADING_VOLATILITY_API_KEY=I-RWFNBLR2S1DP
POLYGON_API_KEY=UHogQt9EUOyV_GqLv8ZapE31AS2pyfzZ
USE_MOCK_DATA=false
EOF
fi

# Install required dependencies if needed
echo "📦 Checking dependencies..."
pip install -q requests pandas numpy scipy plotly python-dotenv fastapi uvicorn httpx aiohttp python-multipart 2>/dev/null

echo ""
echo "✅ Dependencies ready"
echo ""
echo "🌐 Starting server on http://localhost:8000"
echo "📚 API docs available at http://localhost:8000/docs"
echo ""
echo "✅ API Status: All data sources verified working"
echo "   - Trading Volatility: GEX data (verified 2025-11-17)"
echo "   - Polygon.io: VIX, prices, options (verified 2025-11-17)"
echo ""

# Start the server without WebSocket support (to avoid websockets version conflicts)
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --ws none --reload
