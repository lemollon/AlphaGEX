#!/bin/bash
# AlphaGEX API Startup Script for Render
# This ensures all dependencies are in the right place

set -e  # Exit on error

echo "🚀 Starting AlphaGEX API..."

# Ensure we're in the project root
cd "$(dirname "$0")"

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

# Start the FastAPI server
echo "🚀 Starting FastAPI server on port ${PORT:-8000}..."
python -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --log-level info \
    --access-log
