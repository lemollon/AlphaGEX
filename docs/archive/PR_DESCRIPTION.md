# Fix Render Deployment: Add Startup Script for Proper Module Imports

## Summary
- Fix exit status 127 error during Render deployment
- Add `start.sh` startup script to properly launch FastAPI from project root
- Update `render.yaml` build configuration to install all dependencies

## Problem
The FastAPI backend was failing to start on Render with exit status 127 (command not found). This was caused by:
- Backend imports modules from parent directory (`core_classes_and_engines.py`, `intelligence_and_strategies.py`)
- Build command only installed `backend/requirements.txt`, missing root dependencies
- Start command ran from wrong directory, couldn't find modules

## Solution

### 1. Created `start.sh`
Startup script that:
- Runs from project root directory
- Ensures proper Python path for module imports
- Launches uvicorn with correct host/port configuration

```bash
#!/bin/bash
# AlphaGEX API Startup Script for Render
set -e  # Exit on error

echo "🚀 Starting AlphaGEX API..."
cd "$(dirname "$0")"
python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### 2. Updated `render.yaml`
Changed build configuration:
- **Old Build Command**: `pip install -r backend/requirements.txt`
- **New Build Command**: `pip install -r requirements.txt`
- **Old Start Command**: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
- **New Start Command**: `./start.sh`

This ensures all dependencies (pandas, numpy, yfinance, anthropic, etc.) are installed from the root requirements.txt.

## Files Changed
- **start.sh** (new): Startup script for Render deployment
- **render.yaml**: Updated build and start commands

## Test Plan
- [ ] Deploy to Render and verify build succeeds
- [ ] Verify health endpoint returns healthy status: `GET /health`
- [ ] Test GEX endpoint: `GET /api/gex/SPY`
- [ ] Test Gamma Intelligence endpoint: `GET /api/gamma/SPY/intelligence`
- [ ] Verify API docs accessible at `/docs`

## Deployment Instructions
After merging, update Render service settings:

1. Go to Render Dashboard → `alphagex-api` service → Settings
2. **Build Command**: `pip install -r requirements.txt`
3. **Start Command**: `./start.sh`
4. Save Changes and trigger Manual Deploy

## Technical Details

### Module Import Chain
```
backend/main.py
  ↓ imports
core_classes_and_engines.py
  ↓ requires
pandas, numpy, yfinance, requests, scipy
  ↓ imports
intelligence_and_strategies.py
  ↓ requires
anthropic, streamlit, pytz
  ↓ imports
config_and_database.py
```

### Why This Fix Works
- Running from project root makes all modules accessible via sys.path
- Installing root requirements.txt includes ALL dependencies
- Startup script ensures consistent execution environment

## Related Issues
Fixes deployment error: `Exited with status 127` (command not found)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
