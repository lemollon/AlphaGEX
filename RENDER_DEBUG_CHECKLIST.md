# Render Service Debug Checklist

## Check These in Render Dashboard

### 1. Service Status
- Go to: https://dashboard.render.com/
- Click on: **alphagex-api**
- What color is the status indicator?
  - [ ] 🟢 Green = "Live"
  - [ ] 🟡 Yellow = "Deploying"
  - [ ] 🔴 Red = "Failed"
  - [ ] ⚪ Gray = "Suspended"

### 2. Latest Deploy Status
In the service page:
- What does it say under "Latest Deploy"?
  - [ ] "Live" with green checkmark
  - [ ] "Deploy failed"
  - [ ] "Build failed"
  - [ ] Something else: ___________

### 3. Check Logs (CRITICAL)
- Click the **"Logs"** tab
- Look at the MOST RECENT logs
- Do you see:
  - [ ] "🚀 Starting AlphaGEX API..."
  - [ ] "Application startup complete"
  - [ ] "Uvicorn running on..."
  - [ ] Red ERROR messages
  - [ ] ImportError or ModuleNotFoundError
  - [ ] "Address already in use"

**Copy the last 50 lines of logs here:**
```
[PASTE LOGS HERE]
```

### 4. Health Check Status
- In the service settings, find "Health Check Path"
- Is it set to: `/health` ?
- Look for "Health Check" section in logs
- Do you see:
  - [ ] "Health check passed"
  - [ ] "Health check failed"
  - [ ] No health check messages

### 5. Environment Variables
- Click **"Environment"** tab
- Are these set?
  - [ ] TRADING_VOLATILITY_API_KEY = I-RWFNBLR2S1DP
  - [ ] TV_USERNAME = I-RWFNBLR2S1DP
  - [ ] ENVIRONMENT = production
  - [ ] ALLOWED_ORIGINS (contains https://alphagex.com)

### 6. Events Tab
- Click **"Events"** tab
- What's the most recent event?
  - [ ] "Deploy live"
  - [ ] "Deploy failed"
  - [ ] "Suspended"
  - [ ] Something else: ___________

### 7. Settings → Service Details
- What is the **Start Command**?
  - Expected: `./start.sh`
  - Actual: ___________

- What is the **Build Command**?
  - Expected: `chmod +x verify_deployment.sh && ./verify_deployment.sh && pip install --no-cache-dir -r requirements-render.txt`
  - Actual: ___________

### 8. Try Manual Actions
- [ ] Click "Manual Deploy" → "Clear build cache & deploy"
- [ ] Wait for deploy to complete
- [ ] Check logs during deploy
- [ ] Test URL after deploy: `curl https://alphagex-api.onrender.com/health`

## Common Issues and Fixes

### Issue 1: Service showing "Live" but returning 403
**Cause**: Service failed to start properly, Render proxy returns 403
**Fix**: Check logs for startup errors

### Issue 2: Health check failing
**Cause**: `/health` endpoint not responding
**Fix**: Ensure FastAPI is actually starting on correct port

### Issue 3: Port binding error
**Cause**: Service trying to bind to wrong port
**Fix**: Ensure start.sh uses `${PORT}` environment variable

### Issue 4: Import errors
**Cause**: Dependencies not installed or wrong Python path
**Fix**: Check build logs for pip install errors

### Issue 5: Database connection error
**Cause**: DATABASE_URL pointing to non-existent database
**Fix**: Check if alphagex-db database exists

## What to Share

Please share:
1. **Service status** (Green/Yellow/Red/Gray)
2. **Last 50 lines of logs**
3. **Latest deploy status**
4. **Any error messages you see**

This will help identify the exact issue.
