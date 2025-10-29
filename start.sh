#!/bin/bash
# AlphaGEX API Startup Script for Render
# This ensures all dependencies are in the right place

set -e  # Exit on error

echo "🚀 Starting AlphaGEX API..."

# Ensure we're in the project root
cd "$(dirname "$0")"

# Start the FastAPI server
python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
