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
echo ""
echo "Checking streamlit imports in key files:"
echo "config_and_database.py imports:"
head -10 config_and_database.py | grep -E "^import|^from" || echo "  ✓ No imports in first 10 lines (expected)"
echo "intelligence_and_strategies.py imports:"
head -15 intelligence_and_strategies.py | grep -E "streamlit|try:" | head -3
echo ""

# Start the FastAPI server
echo "🚀 Starting FastAPI server..."
python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
