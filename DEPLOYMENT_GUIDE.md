# 🚀 AlphaGEX Backend Deployment Guide

Complete step-by-step guide to deploy FastAPI backend to Render with PostgreSQL.

---

## 📋 Prerequisites

- ✅ Render account (free tier available at https://render.com)
- ✅ GitHub repository with latest code
- ✅ Claude API key (from Anthropic)
- ✅ TradingVolatility API key

---

## 🎯 Deployment Overview

We'll deploy:
1. **PostgreSQL Database** - Production database
2. **FastAPI Backend** - API server at `alphagex-api.onrender.com`
3. **Keep Streamlit Running** - Your current app stays live

**Total Time:** ~30-45 minutes

---

## Step 1: Push Code to GitHub

Make sure all the latest code is pushed:

```bash
git status
git add .
git commit -m "Add FastAPI backend with Render config"
git push origin claude/session-011CUbUU2V2WCPfHaqKhJT2s
```

---

## Step 2: Create PostgreSQL Database on Render

### 2.1 Go to Render Dashboard
- Visit https://dashboard.render.com
- Click **"New +"** → **"PostgreSQL"**

### 2.2 Configure Database
- **Name:** `alphagex-db`
- **Database:** `alphagex`
- **User:** `alphagex`
- **Region:** `Oregon (US West)` (or closest to you)
- **Plan:** `Starter` (Free tier - 256MB RAM, 1GB storage)

### 2.3 Create Database
- Click **"Create Database"**
- Wait ~2 minutes for provisioning
- **COPY the connection strings:**
  - Internal Database URL (starts with `postgresql://...`)
  - External Database URL (for local testing)

**Save these URLs - you'll need them!**

---

## Step 3: Deploy FastAPI Backend

### 3.1 Create New Web Service
- Go back to Dashboard
- Click **"New +"** → **"Web Service"**

### 3.2 Connect Repository
- **Connect GitHub repository:** `lemollon/AlphaGEX`
- **Branch:** `claude/session-011CUbUU2V2WCPfHaqKhJT2s` (or your branch)

### 3.3 Configure Service

**Basic Settings:**
- **Name:** `alphagex-api`
- **Region:** `Oregon (US West)`
- **Branch:** `claude/session-011CUbUU2V2WCPfHaqKhJT2s`
- **Runtime:** `Python 3`
- **Build Command:**
  ```bash
  pip install -r backend/requirements.txt
  ```
- **Start Command:**
  ```bash
  cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
  ```

**Advanced Settings:**
- **Health Check Path:** `/health`
- **Plan:** `Starter` (Free tier - 512MB RAM)

### 3.4 Add Environment Variables

Click **"Add Environment Variable"** for each:

| Key | Value | Secret? |
|-----|-------|---------|
| `ENVIRONMENT` | `production` | No |
| `PYTHON_VERSION` | `3.11.0` | No |
| `CLAUDE_API_KEY` | `sk-ant-...` (your key) | **YES** |
| `TRADING_VOLATILITY_API_KEY` | (your key) | **YES** |
| `DATABASE_URL` | (PostgreSQL Internal URL from Step 2) | **YES** |
| `ALLOWED_ORIGINS` | `https://alphagex.vercel.app,http://localhost:3000` | No |

**Important:**
- Mark API keys as "Secret" (eye icon)
- Use the **Internal Database URL** from your PostgreSQL database
- You can add more origins to `ALLOWED_ORIGINS` later

### 3.5 Deploy!
- Click **"Create Web Service"**
- Render will:
  1. Clone your repository
  2. Install dependencies
  3. Start the server
  4. Assign a URL

**Wait 5-10 minutes for first deployment.**

---

## Step 4: Verify Deployment

### 4.1 Check Build Logs
- Click on your service `alphagex-api`
- Go to **"Logs"** tab
- Look for:
  ```
  🚀 AlphaGEX API Starting...
  Application startup complete.
  Uvicorn running on http://0.0.0.0:10000
  ```

### 4.2 Get Your API URL
- Your API URL will be: `https://alphagex-api.onrender.com`
- Or whatever name you chose

### 4.3 Test Endpoints

**Health Check:**
```bash
curl https://alphagex-api.onrender.com/health
```

Should return:
```json
{
  "status": "healthy",
  "timestamp": "2025-10-29T...",
  "market": { "open": true/false },
  "services": { "api_client": "operational" }
}
```

**API Documentation:**
- Visit: `https://alphagex-api.onrender.com/docs`
- You should see Swagger UI with all endpoints!

**Test GEX Endpoint:**
- In Swagger UI, try: `GET /api/gex/SPY`
- Click "Try it out" → "Execute"
- Should return GEX data

**Test Gamma Intelligence:**
- Try: `GET /api/gamma/SPY/intelligence`
- Should return your 3-view gamma analysis

---

## Step 5: Set Up Database (PostgreSQL)

### 5.1 Connect to Database Locally (Optional)

To test the database connection:

```bash
# Install psql if needed
# macOS: brew install postgresql
# Ubuntu: sudo apt-get install postgresql-client

# Connect using External Database URL
psql "postgresql://alphagex:PASSWORD@HOST/alphagex"
```

### 5.2 Initialize Database Schema

We'll create the schema in Week 2, but you can test the connection:

```python
# Test script (save as test_db.py)
import psycopg2
import os

DATABASE_URL = "YOUR_EXTERNAL_DATABASE_URL"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print(f"✅ Connected to PostgreSQL: {version[0]}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
```

Run:
```bash
pip install psycopg2-binary
python test_db.py
```

---

## Step 6: Update Frontend Configuration

Once backend is deployed, update your React frontend config:

**`.env.local` (in frontend directory):**
```bash
NEXT_PUBLIC_API_URL=https://alphagex-api.onrender.com
NEXT_PUBLIC_WS_URL=wss://alphagex-api.onrender.com
NEXT_PUBLIC_ENVIRONMENT=production
```

---

## Step 7: Test Everything

### 7.1 Test from Browser
Visit your API docs: `https://alphagex-api.onrender.com/docs`

Try each endpoint:
- ✅ `GET /health` - Should return healthy status
- ✅ `GET /api/gex/SPY` - Should return GEX data
- ✅ `GET /api/gamma/SPY/intelligence` - Should return 3 views
- ✅ `POST /api/ai/analyze` - Should return AI analysis

### 7.2 Test WebSocket
Open browser console and run:

```javascript
const ws = new WebSocket('wss://alphagex-api.onrender.com/ws/market-data?symbol=SPY');
ws.onopen = () => console.log('Connected!');
ws.onmessage = (e) => console.log('Data:', JSON.parse(e.data));
```

Should receive market data updates every 30 seconds.

### 7.3 Test from Local React App

```typescript
// Test in your React component
const fetchGexData = async () => {
  const response = await fetch('https://alphagex-api.onrender.com/api/gex/SPY');
  const data = await response.json();
  console.log('GEX Data:', data);
};
```

---

## 🎉 Success Checklist

- ✅ PostgreSQL database created
- ✅ Backend deployed to Render
- ✅ Health check returns "healthy"
- ✅ API docs accessible at `/docs`
- ✅ GEX endpoint returns data
- ✅ Gamma intelligence endpoint works
- ✅ AI Copilot endpoint works
- ✅ WebSocket connection works
- ✅ Can access from React frontend

---

## 🔧 Troubleshooting

### Build Failed

**Check logs for:**
```
ModuleNotFoundError: No module named 'xyz'
```

**Fix:** Add missing package to `backend/requirements.txt`

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'core_classes_and_engines'`

**Fix:** Make sure `backend/main.py` has:
```python
# Add parent directory to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
```

### Database Connection Failed

**Error:** `psycopg2.OperationalError: could not connect to server`

**Fix:**
1. Check `DATABASE_URL` in environment variables
2. Use **Internal Database URL** (not External)
3. Wait for database to finish provisioning

### CORS Errors

**Error in browser:** `Access-Control-Allow-Origin`

**Fix:**
1. Add frontend URL to `ALLOWED_ORIGINS` environment variable
2. Restart backend service
3. Clear browser cache

### Health Check Failing

**Service shows "Unhealthy"**

**Fix:**
1. Check logs for errors
2. Verify `/health` endpoint works locally
3. Make sure port `$PORT` is used (not hardcoded)

### WebSocket Connection Failed

**Error:** `WebSocket connection failed`

**Fix:**
1. Use `wss://` (not `ws://`) for production
2. Check firewall/proxy settings
3. Test endpoint in browser console

---

## 📊 Monitoring

### View Logs
```bash
# In Render dashboard
Services → alphagex-api → Logs
```

Watch for:
- Startup messages
- API requests
- Errors
- Health checks

### Check Metrics
- Dashboard → Service → Metrics
- CPU usage
- Memory usage
- Request count
- Response time

### Set Up Alerts
- Dashboard → Service → Settings → Alerts
- Email notifications for:
  - Deploy failures
  - Health check failures
  - High CPU/memory usage

---

## 💰 Cost Breakdown (Free Tier)

| Service | Plan | Cost |
|---------|------|------|
| PostgreSQL | Starter | $0/month (256MB RAM) |
| FastAPI Backend | Starter | $0/month (512MB RAM) |
| Streamlit App (existing) | Starter | $0/month |
| **Total** | | **$0/month** |

**Free tier limits:**
- 750 hours/month compute (per service)
- 256MB RAM (database)
- 512MB RAM (web service)
- 100GB bandwidth

**To upgrade:**
- Standard plan: $7/month (256MB RAM)
- Pro plan: $25/month (2GB RAM)

---

## 🔐 Security Best Practices

### Environment Variables
- ✅ Mark all API keys as "Secret"
- ✅ Never commit `.env` files
- ✅ Rotate keys regularly

### Database
- ✅ Use Internal Database URL (not External)
- ✅ Enable connection pooling
- ✅ Set up backups (Render handles this)

### CORS
- ✅ Only allow specific origins
- ✅ Update when adding new frontend URLs
- ✅ Don't use wildcards (`*`) in production

### HTTPS
- ✅ Render provides free SSL (automatic)
- ✅ All traffic encrypted
- ✅ HTTP redirects to HTTPS

---

## 📚 Useful Commands

### View Service Status
```bash
# Check if service is running
curl https://alphagex-api.onrender.com/health
```

### Trigger Manual Deploy
```bash
# In Render dashboard
Services → alphagex-api → Manual Deploy → Deploy latest commit
```

### View Environment Variables
```bash
# In Render dashboard
Services → alphagex-api → Environment → Environment Variables
```

### Access Database
```bash
# From Render dashboard, get shell access
Services → alphagex-db → Connect → External Connection
```

---

## 🎯 Next Steps

After deployment is successful:

1. **Week 2: Database Migration**
   - Create SQLAlchemy models
   - Run Alembic migrations
   - Migrate data from SQLite

2. **Initialize React Frontend**
   - Run commands from `FRONTEND_SETUP_GUIDE.md`
   - Connect to live backend API

3. **Build UI Components**
   - Status boxes
   - Dashboard layout
   - GEX analysis page

4. **Deploy Frontend to Vercel**
   - Connect GitHub repo
   - Set environment variables
   - Deploy

---

## 📞 Support

### Render Documentation
- https://render.com/docs

### Render Community
- https://community.render.com

### FastAPI Docs
- https://fastapi.tiangolo.com/deployment/

---

## ✅ Deployment Complete!

Your FastAPI backend is now live at: **`https://alphagex-api.onrender.com`**

**What you can do now:**
- ✅ Test all endpoints at `/docs`
- ✅ Connect React frontend to live API
- ✅ Build UI components
- ✅ Show off your professional API to anyone!

**Your Streamlit app is still running** at the original URL - zero downtime! 🎉

---

**Ready to build the React UI!** 🚀
