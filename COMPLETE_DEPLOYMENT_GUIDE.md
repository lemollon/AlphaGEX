# 🚀 AlphaGEX Complete Deployment Guide

## 🎯 Complete Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USERS                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│   SERVICE 1: STREAMLIT FRONTEND                                 │
│   https://alphagex-app.onrender.com                            │
│                                                                 │
│   ✅ GEX Dashboard                                             │
│   ✅ Live Charts                                               │
│   ✅ AI Copilot Chat                                          │
│   ✅ Autonomous Trader Dashboard                              │
│   ✅ Paper Trading Interface                                  │
│   ✅ Performance Analytics                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│   SERVICE 2: FASTAPI BACKEND                                    │
│   https://alphagex-api.onrender.com                            │
│                                                                 │
│   ✅ REST API Endpoints                                        │
│   ✅ Real-time WebSocket                                       │
│   ✅ Data Processing                                           │
│   ✅ Claude AI Integration                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│   SERVICE 3: AUTONOMOUS TRADER                                  │
│   (Background Worker - No URL)                                  │
│                                                                 │
│   ✅ 24/7 Trading Bot                                          │
│   ✅ 1 SPY Trade Per Day                                       │
│   ✅ Auto Position Management                                  │
│   ✅ Logging & Tracking                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  DATABASE        │
                    │  PostgreSQL      │
                    │  (Render)        │
                    └──────────────────┘
```

---

## 📋 What's Currently Live

### ✅ Service 2: Backend API
**Status:** LIVE ✅
**URL:** https://alphagex-api.onrender.com
**Service ID:** `srv-d413d9vgi27c73d4r1fg`

### ❌ Service 1: Frontend App
**Status:** NOT DEPLOYED ❌
**Expected URL:** https://alphagex-app.onrender.com
**Needs:** Manual deployment or render.yaml push

### ❌ Service 3: Autonomous Trader
**Status:** NOT RUNNING ❌
**Needs:** Manual deployment or render.yaml push

---

## 🚀 Deployment Steps

### Option A: Deploy All Services via render.yaml (Recommended)

**Step 1: Commit Updated render.yaml**
```bash
git add render.yaml
git commit -m "Add complete 3-service architecture"
git push origin main
```

**Step 2: Go to Render Dashboard**
1. Visit: https://dashboard.render.com
2. Click "New" → "Blueprint"
3. Connect your GitHub repo: `lemollon/AlphaGEX`
4. Select `render.yaml`
5. Click "Apply"

Render will automatically create:
- ✅ `alphagex-app` (Streamlit frontend)
- ✅ `alphagex-api` (already exists)
- ✅ `alphagex-trader` (autonomous worker)
- ✅ `alphagex-db` (PostgreSQL database)

**Step 3: Set Environment Variables**

For each service, go to Settings → Environment Variables and add:

**alphagex-app (Frontend):**
- `CLAUDE_API_KEY` - Your Anthropic API key
- `TV_USERNAME` - Trading Volatility username
- `TRADING_VOLATILITY_API_KEY` - Trading Volatility API key

**alphagex-api (Backend):**
- Already configured ✅

**alphagex-trader (Worker):**
- `TV_USERNAME` - Trading Volatility username
- `TRADING_VOLATILITY_API_KEY` - Trading Volatility API key

---

### Option B: Deploy Services Manually

#### Deploy Streamlit Frontend
1. Go to Render Dashboard
2. Click "New" → "Web Service"
3. Connect GitHub repo: `lemollon/AlphaGEX`
4. Configure:
   - **Name:** `alphagex-app`
   - **Branch:** `main`
   - **Build Command:** `pip install --no-cache-dir -r requirements.txt`
   - **Start Command:** `streamlit run gex_copilot.py --server.port=8501 --server.address=0.0.0.0`
5. Add environment variables (see above)
6. Click "Create Web Service"

#### Deploy Autonomous Trader
1. Go to Render Dashboard
2. Click "New" → "Background Worker"
3. Connect GitHub repo: `lemollon/AlphaGEX`
4. Configure:
   - **Name:** `alphagex-trader`
   - **Branch:** `main`
   - **Build Command:** `pip install --no-cache-dir -r requirements.txt`
   - **Start Command:** `python autonomous_scheduler.py --mode continuous --interval 60`
5. Add environment variables (see above)
6. Click "Create Worker"

---

## 🎯 After Deployment: Verify Everything Works

### 1. Check Frontend (5 minutes after deploy)
**URL:** https://alphagex-app.onrender.com

**Expected:**
- ✅ Streamlit app loads
- ✅ GEX dashboard visible
- ✅ Can enter SPY symbol
- ✅ Charts render
- ✅ AI chat works (if API key set)

### 2. Check Backend API (Already Live)
**URL:** https://alphagex-api.onrender.com/health

**Expected:**
```json
{
  "status": "healthy",
  "market": { "open": true/false },
  "services": { "api_client": "operational" }
}
```

### 3. Check Autonomous Trader (Check logs)
**Dashboard:** https://dashboard.render.com → `alphagex-trader` → Logs

**Expected (during market hours):**
```
🤖 AUTONOMOUS TRADER CYCLE - 2025-10-30 10:00:00
🔍 MORNING SESSION - Checking for new trade opportunity...
✅ SUCCESS: Opened position #1
📊 PERFORMANCE SUMMARY:
   Starting Capital: $5,000
   Current Value: $5,000.00
   Total P&L: $0.00 (+0.00%)
```

### 4. Check Database
**Dashboard:** https://dashboard.render.com → `alphagex-db`

**Verify:**
- Database is running
- All services connected

---

## 📊 Feature Checklist

After deployment, verify all features work:

### Frontend Features (alphagex-app)
- [ ] GEX Dashboard loads
- [ ] Can enter symbols (SPY, QQQ, AAPL)
- [ ] Charts display GEX data
- [ ] Flip point calculation shows
- [ ] AI Chat responds (needs Claude API key)
- [ ] Autonomous Trader tab shows
- [ ] Can view trade history
- [ ] Performance metrics display

### Backend Features (alphagex-api)
- [x] `/health` endpoint responds
- [x] `/api/gex/SPY` returns data
- [x] `/docs` shows Swagger UI
- [x] CORS allows frontend requests

### Autonomous Trader Features (alphagex-trader)
- [ ] Starts successfully (check logs)
- [ ] Creates database tables
- [ ] Waits for market hours
- [ ] Executes morning trade (9:30-11:00 AM)
- [ ] Logs actions to database
- [ ] Manages positions hourly

---

## 🔧 Troubleshooting

### Frontend Won't Load
**Symptom:** 500 error or blank page
**Check:**
1. Render logs: https://dashboard.render.com → `alphagex-app` → Logs
2. Look for import errors
3. Verify all dependencies in requirements.txt

**Common fixes:**
```bash
# If streamlit import errors:
pip install streamlit==1.29.0

# If missing dependencies:
pip install -r requirements.txt
```

### Autonomous Trader Not Trading
**Symptom:** No trades in database
**Check:**
1. Is it market hours? (Mon-Fri 9:30 AM - 4:00 PM ET)
2. Check logs for errors
3. Verify API keys are set

**Debug:**
```bash
# Check if database has tables
psql $DATABASE_URL -c "\dt"

# Check trade log
psql $DATABASE_URL -c "SELECT * FROM autonomous_trade_log ORDER BY date DESC LIMIT 10;"
```

### Backend API Slow
**Symptom:** Long response times
**Check:**
1. Trading Volatility API rate limits
2. Render service plan (free tier sleeps after 15 min)
3. Cache settings

---

## 💰 Cost Breakdown (Render Pricing)

### Free Tier (What You Can Start With)
- **Frontend (alphagex-app):** $0/month (750 hours free)
- **Backend (alphagex-api):** $0/month (750 hours free)
- **Worker (alphagex-trader):** $0/month (750 hours free)
- **Database (alphagex-db):** $0/month (90 days free, then $7/month)

**Total:** $0/month for first 90 days, then $7/month

### Paid Tier (If You Outgrow Free)
- **Frontend:** $7/month (Starter plan)
- **Backend:** $7/month (Starter plan)
- **Worker:** $7/month (Starter plan)
- **Database:** $7/month (Starter plan)

**Total:** $28/month (all services always running)

---

## 📈 Next Steps After Deployment

### Week 1: Verify Everything Works
1. ✅ Frontend loads at https://alphagex-app.onrender.com
2. ✅ Backend API responds at https://alphagex-api.onrender.com
3. ✅ Autonomous trader executes first trade
4. ✅ All features accessible

### Week 2-4: Monitor Autonomous Trader
1. Track first 20-30 trades
2. Review performance daily
3. Check win rate and P&L
4. Make notes on what works

### Month 2: Optimize
1. Analyze 30+ trades data
2. Calculate expectancy
3. Adjust strategy if needed
4. Scale up if profitable

### Future: Enhance UX
1. Build React frontend (optional)
2. Add mobile app (optional)
3. Add webhooks/alerts
4. Integrate more features

---

## 🎯 Success Criteria

You'll know deployment is successful when:

✅ **Frontend:** You can visit the URL and use all features
✅ **Backend:** API responds to all endpoints
✅ **Trader:** Executes 1 trade per day during market hours
✅ **Database:** Stores all trades and logs
✅ **Performance:** Win rate and P&L are tracked

---

## 📞 Support Resources

- **Render Status:** https://status.render.com
- **Render Docs:** https://render.com/docs
- **Your Services:** https://dashboard.render.com
- **API Docs:** https://alphagex-api.onrender.com/docs

---

**Ready to deploy? Follow Option A above to get all 3 services running!** 🚀
