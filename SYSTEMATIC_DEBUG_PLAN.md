# Systematic Debug Plan - GEX Profile Issues

## Current Issues (To Fix Methodically)

1. ❌ **Too many strikes showing** - Should only show +/- 7 day STD range
2. ❌ **Net gamma not displaying** - Chart shows no data for net gamma
3. ❌ **Call OI missing** - Table shows 0 or blank
4. ❌ **Put OI missing** - Table shows 0 or blank
5. ❌ **P/C Ratio missing** - Table shows 0 or blank

---

## What I Just Added

I've added **comprehensive debug logging** to see exactly what data flows through the system:

### Debug Points:
1. **Raw API strike data** - Shows what fields Trading Volatility returns
2. **Filtered strike count** - Confirms +/- 7 day STD filter is working
3. **Transformed strike data** - Shows what we send to frontend
4. **OI and PCR values** - Confirms if these fields have data

---

## What You Need to Do Now

### Step 1: Redeploy Backend (2 min)

1. Go to: https://dashboard.render.com/
2. Click: `alphagex-api`
3. Click: **"Manual Deploy"**
4. Wait for build to complete

### Step 2: Test and Capture Logs (5 min)

1. Visit: https://alphagex.com/gex
2. Enter: **SPY**
3. Wait for data to load (or show error)
4. Go back to Render dashboard
5. Click on **Logs** tab
6. **Copy the last 100 lines** and paste them here

### Step 3: What to Look For in Logs

Look for these debug lines:

```
DEBUG: Sample strike fields available: [...]
DEBUG: Sample strike data: {...}
DEBUG: First strike fields: [...]
DEBUG: First strike data: {...}
DEBUG: Total strikes (filtered to +/- 7 day STD): XX
DEBUG: Sample transformed level: {...}
DEBUG: Has OI data: call_oi=XXX, put_oi=XXX
DEBUG: Has total_gex: XXX
✅ Returning XX strike levels for SPY (filtered to +/- 7 day STD)
```

---

## Questions I Need Answered From Logs

### Question 1: What fields does the API return?
```
DEBUG: Sample strike fields available: [...]
```

**I need to see**: Is it `call_open_interest` or `callOpenInterest` or `call_oi`?

### Question 2: Does the data have values?
```
DEBUG: Sample strike data: {
  'strike': 675.0,
  'call_gamma': ???,
  'put_gamma': ???,
  'total_gamma': ???,
  'call_oi': ???,       ← Are these 0 or have actual values?
  'put_oi': ???,
  'put_call_ratio': ???
}
```

### Question 3: How many strikes after filtering?
```
DEBUG: Total strikes (filtered to +/- 7 day STD): XX
```

**Should be**: ~20-40 strikes depending on volatility
**If showing 100+**: Filter not working

### Question 4: What does transformed data look like?
```
DEBUG: Sample transformed level: {
  'strike': 675.0,
  'call_gex': ???,
  'put_gex': ???,
  'total_gex': ???,    ← Is this 0?
  'call_oi': ???,
  'put_oi': ???,
  'pcr': ???
}
```

---

## Likely Issues & Fixes

### Issue A: Field Name Mismatch

**If API returns**:
```python
{
  'call_open_interest': 12345,  # Not 'call_oi'
  'put_open_interest': 9876
}
```

**Fix**: Change extraction in `core_classes_and_engines.py` line 1479-1480:
```python
call_oi = float(strike_obj.get('call_open_interest', 0))  # Already correct
put_oi = float(strike_obj.get('put_open_interest', 0))    # Already correct
```

### Issue B: Data is Missing from API

**If API doesn't include OI**:
```python
{
  'strike': 675.0,
  'call_gamma': 1234567,
  'put_gamma': -987654
  # No OI fields!
}
```

**Fix**: Need to use a different API endpoint or accept that OI data isn't available

### Issue C: total_gamma Calculation Wrong

**If total_gamma is always 0**:

Check line 1476 in `core_classes_and_engines.py`:
```python
total_gamma = call_gamma_raw + put_gamma_raw
```

Need to verify `call_gamma_raw` and `put_gamma_raw` have values.

### Issue D: Frontend Not Receiving Data

**If backend logs show good data but frontend still blank**:

Check frontend console (F12 in browser) for errors.

---

## After You Share Logs

Once you share the debug logs, I will:

1. ✅ Identify exact field names from API
2. ✅ Fix any field name mismatches
3. ✅ Verify filtering is working
4. ✅ Fix total_gamma calculation if needed
5. ✅ Ensure data flows to frontend correctly

---

## Why This Approach

I was moving too fast before. This systematic approach will:

1. **See actual API response** - Stop guessing field names
2. **Verify each transformation** - Track data through the pipeline
3. **Identify exact break point** - Find where data disappears
4. **Fix once, correctly** - No more guessing

---

## Summary

**Please:**
1. Redeploy backend
2. Test SPY on https://alphagex.com/gex
3. Copy last 100 lines from Render logs
4. Paste them here

With the actual logs, I can fix all remaining issues in one go.

**Thank you for your patience!** This methodical approach will solve it properly.
