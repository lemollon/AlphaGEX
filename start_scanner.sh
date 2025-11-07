#!/bin/bash
# Start AlphaGEX Scanner (Backend + Frontend)

echo "🚀 Starting AlphaGEX Scanner..."
echo ""

# Check if API key is set
if [ -z "$TRADING_VOLATILITY_API_KEY" ]; then
    echo "⚠️  WARNING: TRADING_VOLATILITY_API_KEY not set"
    echo "The scanner won't work without it!"
    echo ""
    echo "Set it with:"
    echo "export TRADING_VOLATILITY_API_KEY='your_key_here'"
    echo ""
    read -p "Press Enter to continue anyway or Ctrl+C to exit..."
fi

# Start backend in background
echo "1. Starting backend API on port 8000..."
cd /home/user/AlphaGEX
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# Wait for backend to start
echo "2. Waiting for backend to be ready..."
sleep 3

# Test backend
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✅ Backend is ready!"
else
    echo "   ❌ Backend failed to start. Check backend.log"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# Start frontend
echo "3. Starting frontend on port 3000..."
cd /home/user/AlphaGEX/frontend

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "   Installing dependencies..."
    npm install
fi

echo ""
echo "✅ Backend running at: http://localhost:8000"
echo "✅ Frontend will start at: http://localhost:3000/scanner"
echo ""
echo "📋 Backend logs: tail -f /home/user/AlphaGEX/backend.log"
echo "🛑 To stop: killall -9 uvicorn node"
echo ""

npm run dev
