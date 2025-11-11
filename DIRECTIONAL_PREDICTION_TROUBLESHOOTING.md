# SPY Directional Prediction - Troubleshooting Guide

## ✅ Status: Code is Committed and Ready

The directional prediction feature has been successfully implemented and committed:
- **Commit**: `47cf79a` - "feat: Add SPY directional prediction with probability to 0DTE section"
- **File**: `gex_copilot.py` (lines 1312-1448)
- **Status**: Pushed to remote branch `claude/find-iexcloud-website-011CV28s5eC2vb1BoCKy9of8`
- **Syntax Check**: ✅ No errors

## 📍 Where to Find It

The prediction appears in the **GEX Analysis** section:

1. Open your AlphaGEX site
2. Navigate to **GEX Analysis** tab
3. Scroll down to **"📊 Gamma Expiration Intelligence - Current Week Only"** section
4. The prediction box appears **immediately after** the week info and **before** "⚡ VIEW 1: TODAY'S IMPACT"

It looks like this:

```
┌─────────────────────────────────────────────┐
│  📈 SPY DIRECTIONAL FORECAST - TODAY        │
│                                             │
│            UPWARD                           │
│         72% Probability                     │
│                                             │
│  Current Price: $567.89                     │
│  Expected Range: $565 - $572 (1.2% range)   │
│  Flip Point: $566.50 (+0.2% from spot)      │
│                                             │
│  Key Factors:                               │
│  • Short gamma + above flip = upside...     │
│  • VIX 17.5 = elevated volatility           │
│  • Monday = high gamma, range-bound bias    │
│                                             │
│  Expected Move: Expect push toward call...  │
└─────────────────────────────────────────────┘
```

## 🔧 Why You Might Not See It

### 1. App Needs Restart (Most Common)
Streamlit apps don't automatically reload code changes. You need to:

**If running locally:**
```bash
# Stop your current Streamlit process (Ctrl+C)
# Then restart it
streamlit run gex_copilot.py
```

**If deployed on Streamlit Cloud:**
- Go to your Streamlit Cloud dashboard
- Click on your app
- Click "Reboot app" or "⋮ → Reboot"
- OR: Streamlit Cloud auto-deploys on git push (wait 2-3 minutes)

**If deployed on a custom server:**
```bash
# SSH into your server
# Find the Streamlit process
ps aux | grep streamlit

# Kill it
kill -9 <process_id>

# Restart the app
streamlit run gex_copilot.py &
```

### 2. Need to Pull Latest Code
If you're running the app from a local clone:

```bash
cd /path/to/AlphaGEX
git fetch origin
git checkout claude/find-iexcloud-website-011CV28s5eC2vb1BoCKy9of8
git pull origin claude/find-iexcloud-website-011CV28s5eC2vb1BoCKy9of8
streamlit run gex_copilot.py
```

### 3. Cache Issue
The prediction might be hidden by cached data:

1. In the **Gamma Expiration Intelligence** section, click the **🔄 Refresh** button
2. Or press **R** in the Streamlit app to rerun
3. Or clear your browser cache (Ctrl+Shift+Delete)

### 4. API Call Failing
The prediction only shows if the gamma intelligence API succeeds. Check for:

- Error messages in the Streamlit app
- Check the console/logs for API errors
- Verify TradingView credentials are set up

## 🧪 Test the Code Locally

Run this script to verify the directional prediction logic works:

```bash
cd /home/user/AlphaGEX
python3 test_directional_prediction.py
```

This will simulate the prediction algorithm and show you output.

## 🔍 Debugging Steps

### Step 1: Verify You Have the Latest Code
```bash
cd /home/user/AlphaGEX
git log --oneline -1
# Should show: 34654c1 fix: Fix 0DTE Week's Gamma Structure refresh to clear correct cache
```

### Step 2: Check the Code Exists
```bash
grep -n "SPY DIRECTIONAL FORECAST" gex_copilot.py
# Should show: 1411:                            {direction_emoji} SPY DIRECTIONAL FORECAST - TODAY
```

### Step 3: Verify No Syntax Errors
```bash
python3 -m py_compile gex_copilot.py && echo "✅ No syntax errors" || echo "❌ Syntax error found"
```

### Step 4: Check Streamlit App Logs
When running Streamlit, look for any errors in the console output.

## 💡 Quick Fix Checklist

- [ ] Latest code pulled from git
- [ ] Streamlit app restarted
- [ ] Browser cache cleared (Ctrl+Shift+R)
- [ ] Looking in correct location (GEX Analysis → Gamma Expiration Intelligence)
- [ ] Clicked 🔄 Refresh button in the section
- [ ] No error messages visible in app

## 📞 Still Not Working?

If you've tried all of the above:

1. Check your Streamlit app console for error messages
2. Verify the API client is initialized correctly
3. Check that `gamma_intel.get('success')` returns `True` (add a debug print if needed)
4. Verify you're looking at the right deployment (not a staging/dev instance)

## 🎯 Expected Behavior

When working correctly, you should see:
- Large colored box (green for UPWARD, red for DOWNWARD, orange for SIDEWAYS)
- Direction text in large font
- Probability percentage (e.g., "72% Probability")
- Current price, expected range, flip point
- Bulleted list of key factors
- Expected move description
- Disclaimer at bottom

The prediction updates whenever you refresh the gamma intelligence data.
