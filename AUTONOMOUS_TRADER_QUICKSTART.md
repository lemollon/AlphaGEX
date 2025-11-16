# 🤖 Autonomous Trader - Quick Start Guide

## **3-Step Deployment** 🚀

### **Step 1: Setup (One-Time)**
```bash
cd /home/user/AlphaGEX
./setup_autonomous_trader.sh
```

**What this does:**
- ✅ Creates Python virtual environment
- ✅ Installs all dependencies (pandas, langchain, yfinance, etc.)
- ✅ Tests imports
- ✅ Takes ~3-5 minutes

---

### **Step 2: Test (Recommended)**
```bash
./test_autonomous_trader.sh
```

**What this does:**
- ✅ Runs one test cycle
- ✅ Fetches live SPY GEX data
- ✅ Creates database
- ✅ Logs decision-making
- ✅ Does NOT execute real trades
- ✅ Takes ~30 seconds

**Expected output:**
```
✅ Trader initialized
✅ GEX data received:
   Net GEX: $-2.10B
   Spot Price: $576.25
   Flip Point: $580.50
✅ TEST COMPLETE
```

---

### **Step 3: Deploy (Auto-Running)**
```bash
# Option A: With sudo (recommended - uses systemd)
sudo ./deploy_autonomous_trader.sh

# Option B: Without sudo (uses screen/nohup)
./deploy_autonomous_trader.sh
```

**What this does:**
- ✅ Starts autonomous trader in background
- ✅ Checks every 5 minutes during market hours
- ✅ Auto-restarts if it crashes
- ✅ Logs everything to `logs/trader.log`

**With systemd (Option A):**
```bash
# Status
sudo systemctl status alphagex-trader

# Logs (live)
sudo journalctl -u alphagex-trader -f

# Stop
sudo systemctl stop alphagex-trader

# Restart
sudo systemctl restart alphagex-trader
```

**With screen/nohup (Option B):**
```bash
# Logs (live)
tail -f logs/trader.log

# Attach to screen
screen -r alphagex-trader

# Stop
kill $(cat logs/trader.pid)
```

---

## **Monitoring & Alerts** 📊

### **Dashboard**
View real-time status at:
- **Frontend:** http://localhost:3000/trader
- **API Health:** http://localhost:8000/api/autonomous/health
- **Logs:** http://localhost:8000/api/autonomous/logs

### **Setup Email Alerts**

Edit `autonomous_monitoring.py`:
```python
monitor.add_email_alert(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    from_email="your-email@gmail.com",
    to_email="your-email@gmail.com",
    password="your-gmail-app-password"  # Not your regular password!
)
```

Then run monitoring:
```bash
# Run once
python3 autonomous_monitoring.py

# Or add to crontab for hourly checks
crontab -e
# Add: 0 * * * * cd /home/user/AlphaGEX && python3 autonomous_monitoring.py
```

### **Setup Slack/Discord Webhook**
```python
monitor.add_webhook_alert("https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
```

---

## **What It Does Automatically** ⚡

### **Continuous Operation (Always Running)**
The autonomous trader runs **24/7** in the background, but only actively trades during market hours:

**🟢 MARKET HOURS (8:30 AM - 3:00 PM CT, Mon-Fri)**
Every 5 minutes:
```
├── Check if already traded today
├── Fetch SPY GEX data from Trading Volatility API
├── Analyze market regime:
│   ├── Negative GEX below flip? → BUY CALLS (squeeze)
│   ├── Negative GEX above flip? → BUY PUTS (breakdown)
│   ├── Positive GEX? → Directional based on flip
│   └── Neutral? → Trade toward flip point
├── Use AI (Claude Haiku) to select best strike
├── Use ML model to predict success probability
├── Check risk limits (drawdown, daily loss, position size)
├── Calculate position size (Kelly Criterion)
├── Execute trade if conditions met
└── Log EVERYTHING to database
```

**🔴 OUTSIDE MARKET HOURS**
- Sleeps until market opens
- Auto-wakes at 8:30 AM CT Monday-Friday
- No API calls, no resource usage

**GUARANTEED:** Minimum 1 trade per day (3-level fallback)

---

## **Database & Logs** 📝

### **Database File**
`autonomous_trader.db` contains:
- **trades** - All executed trades
- **autonomous_trader_logs** - Decision-making logs (50+ columns)
- **strategy_competition** - Performance by strategy
- **backtest_results** - Historical pattern validation

### **View Logs**
```bash
# Recent trades
sqlite3 autonomous_trader.db "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10"

# AI thought process
sqlite3 autonomous_trader.db "SELECT timestamp, log_type, reasoning_summary FROM autonomous_trader_logs ORDER BY timestamp DESC LIMIT 20"

# Strategy leaderboard
sqlite3 autonomous_trader.db "SELECT strategy_name, win_rate, total_pnl, sharpe_ratio FROM strategy_competition ORDER BY total_pnl DESC"
```

---

## **Troubleshooting** 🔧

### **"Module not found" error**
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Re-run setup
./setup_autonomous_trader.sh
```

### **"API key not configured" error**
```bash
# Set environment variable
export TRADING_VOLATILITY_API_KEY="your_key_here"

# Or add to .env file
echo "TRADING_VOLATILITY_API_KEY=your_key_here" >> .env
```

### **Trader not executing trades**
```bash
# Check if it's running
ps aux | grep autonomous_scheduler

# Check logs
tail -f logs/trader.log

# Verify market hours (8:30 AM - 3:00 PM CT, Mon-Fri)
date
```

### **Database locked error**
```bash
# Stop trader first
sudo systemctl stop alphagex-trader  # OR kill $(cat logs/trader.pid)

# Then access database
sqlite3 autonomous_trader.db
```

---

## **Performance Tuning** ⚙️

### **Adjust Risk Limits**
Edit `autonomous_risk_manager.py`:
```python
self.limits = {
    'max_drawdown': 15,      # % - Stop trading if down 15%
    'daily_loss': 5,          # % - Max loss per day
    'position_size': 20,      # % - Max per trade
    'correlation': 50         # % - Correlation exposure
}
```

### **Change Position Sizing**
Edit `autonomous_paper_trader.py`:
```python
MAX_POSITION_SIZE_PCT = 0.25  # 25% of capital per trade
MAX_EXPOSURE_PCT = 0.50       # 50% total exposure
```

### **Modify Check Frequency**
Edit `autonomous_scheduler.py`:
```python
CHECK_INTERVAL_MINUTES = 5  # Change to 10 for less frequent checks
```

---

## **Advanced Features** 🧠

### **8 Strategy Competition**
The trader runs 8 strategies simultaneously with equal capital:
1. Psychology Trap + Liberation (full system)
2. Pure GEX Regime
3. RSI + Gamma Walls
4. Liberation Only
5. Forward GEX Magnets
6. Conservative (85%+ confidence)
7. Aggressive (60%+ confidence)
8. AI-Only (Claude decides)

View leaderboard in UI or:
```bash
sqlite3 autonomous_trader.db "SELECT * FROM strategy_competition ORDER BY current_capital DESC"
```

### **AI Reasoning**
Every strike selection uses Claude Haiku to analyze:
- Why this strike?
- What are alternatives?
- Expected outcome?

View in logs:
```bash
sqlite3 autonomous_trader.db "SELECT strike_selection_reason FROM autonomous_trader_logs WHERE log_type='STRIKE_SELECTION' ORDER BY timestamp DESC LIMIT 5"
```

### **ML Pattern Learning**
Random Forest model predicts success based on:
- RSI (5 timeframes)
- GEX metrics
- VIX level
- Liberation events
- False floors
- Forward magnets

View predictions:
```bash
sqlite3 autonomous_trader.db "SELECT ai_confidence, ml_confidence_boost FROM autonomous_trader_logs WHERE log_type='AI_EVALUATION' ORDER BY timestamp DESC LIMIT 10"
```

---

## **FAQ** ❓

**Q: How much does it trade per day?**
A: MINIMUM 1 trade guaranteed (multi-level fallback). Typically 1-3 trades depending on market conditions.

**Q: What if the API is down?**
A: It retries 3 times, then skips that cycle. Will try again in 5 minutes.

**Q: Can I run multiple instances?**
A: NO - Database will lock. Only run one instance.

**Q: Does it trade at night?**
A: NO - Only during market hours (8:30 AM - 3:00 PM CT, Mon-Fri).

**Q: Can I backtest before deploying?**
A: YES - Run `python3 autonomous_backtest_engine.py` to see historical performance.

**Q: How do I stop it?**
A: `sudo systemctl stop alphagex-trader` (or `kill $(cat logs/trader.pid)`)

---

## **Next Steps** 🎯

1. ✅ Run setup
2. ✅ Test it
3. ✅ Deploy it
4. ✅ Monitor for 1 week
5. ✅ Review logs and performance
6. ✅ Adjust risk parameters if needed
7. ✅ Let it compound!

**This is automated income.** Let it run and watch the money printer go brrrr 🚀

---

**Need help?** Check logs first:
```bash
tail -f logs/trader.log
sqlite3 autonomous_trader.db "SELECT * FROM autonomous_trader_logs ORDER BY timestamp DESC LIMIT 20"
```
