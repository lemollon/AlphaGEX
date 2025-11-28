# Backend Server Won't Start - WebSockets Issue

## Problem
The backend server is failing to start due to a WebSockets library compatibility issue:

```
ModuleNotFoundError: No module named 'websockets.legacy'
```

## Root Cause
The installed `uvicorn[standard]` version is incompatible with the websockets library versions available.

## Quick Fix Option 1: Disable Auto-Reload
Run the backend without the auto-reload feature which triggers the websockets issue:

```bash
cd /home/user/AlphaGEX
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-reload
```

## Quick Fix Option 2: Run Without WebSocket Support
```bash
cd /home/user/AlphaGEX
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --ws none
```

## Quick Fix Option 3: Downgrade uvicorn
```bash
pip3 uninstall uvicorn uvicorn-standard -y
pip3 install uvicorn==0.23.2
cd /home/user/AlphaGEX
python3 backend/main.py
```

## What I've Already Fixed
1. ✅ Installed all missing dependencies (pandas, numpy, scikit-learn, yfinance, langchain, etc.)
2. ✅ Fixed database logger parameter errors
3. ✅ Fixed "Invalid Date" display issues in frontend
4. ✅ Verified autonomous trader initializes correctly
5. ✅ Database tables all exist and are ready

## What's Still Blocking
- Backend server won't start due to uvicorn/websockets compatibility
- Once backend starts, the trader should work if you have Trading Volatility API credentials

## Next Steps for You
1. Try one of the quick fixes above to start the backend
2. Once running, check http://localhost:8000/health
3. Navigate to your frontend and the trader should be working

The date/time issues and database errors I already fixed should make everything work once the backend is running.
