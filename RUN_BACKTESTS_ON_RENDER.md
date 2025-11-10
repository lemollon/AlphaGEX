# How To Run Backtests on Render

## The Problem
Backtests need to be RUN to populate the database. The UI shows "no results" because no backtests have executed yet.

## The Solution

### Option 1: Add Backtest Endpoint to Backend (Recommended)

Add this endpoint to `backend/main.py`:

```python
@app.post("/api/backtest/run")
async def run_backtests(request: dict):
    """
    Run all backtests via API endpoint
    """
    import subprocess

    symbol = request.get('symbol', 'SPY')
    days = request.get('days', 365)

    try:
        result = subprocess.run(
            ['python3', 'run_all_backtests.py', '--symbol', symbol, '--days', str(days)],
            cwd='/opt/render/project/src',  # Render project path
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            return {
                "success": True,
                "message": "Backtests completed successfully",
                "output": result.stdout
            }
        else:
            return {
                "success": False,
                "error": result.stderr,
                "output": result.stdout
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
```

Then from your frontend, call: `POST /api/backtest/run` with `{"symbol": "SPY", "days": 365}`

### Option 2: SSH into Render and Run Manually

```bash
# From Render dashboard:
1. Go to your service
2. Click "Shell" tab
3. Run:
cd /opt/render/project/src
python3 run_all_backtests.py --symbol SPY --days 365
```

### Option 3: Add as a Scheduled Job

In Render dashboard:
1. Create a new "Cron Job"
2. Command: `python3 run_all_backtests.py --symbol SPY --days 365`
3. Schedule: `0 0 * * 0` (Weekly on Sunday at midnight)
4. Environment: Same as your backend service

## Why Backtests Aren't Running Automatically

The backend server (`uvicorn`) just serves API requests. It doesn't automatically run backtests on startup because:
- Backtests take 5-10 minutes to complete
- Would delay server startup
- Needs to be triggered manually or on a schedule

## After Running Backtests

Once backtests complete:
- ✅ Database will have results in `backtest_results` table
- ✅ Frontend will show strategy performance
- ✅ AI Strategy Optimizer will have data to analyze
