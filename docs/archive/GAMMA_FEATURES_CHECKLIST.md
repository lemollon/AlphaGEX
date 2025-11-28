# Gamma Intelligence Features - Complete Testing Checklist

## 🎯 GOAL: Every feature must help users make money trading options

Every section should have:
1. ✅ **Clear data visualization**
2. ✅ **"How to Make Money" explanation**
3. ✅ **Specific trading actionable guidance**
4. ✅ **Evidence-based thresholds cited**

---

## Page 1: `/gamma` - Gamma Intelligence

### Overview Tab

#### ✅ **Key Metrics** (Should Always Show)
- [ ] Total Gamma (green/red color)
- [ ] GEX Ratio
- [ ] Vanna Exposure
- [ ] Charm Decay

**How to Use**: Each metric should have tooltip or nearby text explaining trading significance

---

#### ✅ **Market Regime** (Should Always Show)
- [ ] State (Positive/Negative/Neutral Gamma)
- [ ] Volatility (Low/Moderate/High)
- [ ] Trend (Bullish/Bearish/Neutral)

**How to Make Money**:
- Positive Gamma + Low Vol = Sell premium (Iron Condors)
- Negative Gamma + High Vol = Buy directional options
- Should be explained in UI

---

#### ⚠️ **Gamma Exposure by Strike** (PRIMARY ISSUE - Often Not Showing)

**What Should Display**:
```
Strike     Call Gamma    Put Gamma    Net Gamma
$670       $2.4M        -$1.8M       $0.6M     ====[green bar]====
$675 ⚡     $3.1M        -$2.9M       $0.2M     ==[bar]==
$680 🔼     $5.2M        -$1.1M       $4.1M     ===========[long bar]======
$685       $2.8M        -$3.5M       -$0.7M    ====[red bar]====
$690 🔽     $1.2M        -$4.8M       -$3.6M    ========[long red bar]====
```

**Visual Bars**:
- Two bars per strike (green for call gamma, red for put gamma)
- Bar width = percentage of max gamma

**Indicators**:
- ⚡ = GEX Flip Point (where net gamma = 0)
- 🔼 = Call Wall (highest call gamma concentration)
- 🔽 = Put Wall (highest put gamma concentration)

**Money-Making Instruction Should Say**:
> 💰 HOW TO MAKE MONEY: Use gamma walls (🔼 Call Wall / 🔽 Put Wall) as profit targets. Price tends to move toward highest gamma concentrations. Trade toward the flip point (⚡) for directional plays.

**If Not Showing**:
1. Check browser console (F12) - look for:
   ```
   === FETCHING GAMMA INTELLIGENCE ===
   Intelligence data: { has_strikes: false, strikes_count: 0, ... }
   ```

2. Backend issue: `profile.get('strikes')` is empty
   - `get_gex_profile()` may be failing to fetch from Trading Volatility API
   - Rate limiting or API timeout

3. Fallback message should show:
   > No Strike Data Available
   >
   > Strike-level gamma data is required to display this chart. The backend may be unable to fetch detailed GEX profile data.
   > Check browser console (F12) for errors, or try refreshing the page.
   >
   > [Retry Loading Data] button

**Expected Backend Call Flow**:
```
frontend → GET /api/gamma/SPY/intelligence
  ↓
backend → api_client.get_net_gamma('SPY')  ✅ This works
  ↓
backend → api_client.get_gex_profile('SPY')  ⚠️ This may fail
  ↓
backend → profile['strikes']  ← Returns empty if API fails
  ↓
frontend → intelligence.strikes  ← Empty = chart doesn't show
```

---

#### ✅ **Key Observations** (Should Always Show)
- [ ] 3 bullet points with gamma insights
- [ ] Auto-generated from current market data

---

#### ✅ **Trading Implications** (Should Always Show)
- [ ] 3 bullet points with actionable trading guidance
- [ ] Tells you what to do (buy/sell, which instruments)

---

#### ✅ **Greeks Summary** (Should Always Show)
- [ ] Risk Reversal
- [ ] Skew Index
- [ ] Call Gamma
- [ ] Put Gamma

---

### Position Impact Tab

#### ⚠️ **Position Simulator** (Should Always Show - Check for Overlap)

**Issue Reported**: "Content overlapping"

**Should Display**:
```
[Option Type: Call ▼] [Strike: 450] [Quantity: 10] [Calculate Impact]

Position Gamma: +$2,450
Delta Impact: +0.65
Theta Decay: -$125/day
```

**Check For**:
- [ ] All input fields visible and not overlapping
- [ ] Results section below inputs (not on top of)
- [ ] Proper spacing between sections

---

#### ⚠️ **Exposure Impact Over Price Range** (PRIMARY ISSUE - Often Not Showing)

**What Should Display**:
```
$670  [-2.1%]  |████████████ -$2.1M| (red bar)
$675  [-0.8%]  |████ -$0.8M|
$680  [+0.5%]  |██ +$0.5M| (green bar)
$685  [+1.7%]  |████████ +$1.7M|
$690  [+2.9%]  |████████████████ +$2.9M|

Current Spot: $676.11
Flip Point: $678.74
Distance to Flip: +0.39%
```

**Money-Making Instruction Should Say**:
> 💰 HOW TO MAKE MONEY: Identify where net gamma changes sign. Positive gamma (green) = range-bound, sell premium. Negative gamma (red) = trending, buy directional options. Use flip point as key decision level.

**If Not Showing**:
- Same issue as "Gamma Exposure by Strike" - no strikes data
- Check `intelligence.strikes && intelligence.strikes.length > 0`

---

#### ✅ **Risk Analysis** (Should Always Show)
- [ ] Max Profit Potential
- [ ] Max Loss Potential
- [ ] Break-Even Point

---

### Historical Analysis Tab

#### ⚠️ **Gamma Exposure Trends** (PRIMARY ISSUE - Often Not Showing)

**What Should Display**:
```
Net GEX Over Time:
Nov 01  $680.15  |████████████████████ $2.1B|
Nov 02  $682.40  |████████████████ $1.8B|
Nov 03  $679.20  |███████████ $1.2B|
Nov 04  $681.95  |████████ $0.9B|
Nov 05  $676.11  |████ $0.5B|

Implied Volatility Trend:
Nov 01  |██████████ 45.2%|
Nov 02  |████████████ 52.1%|
Nov 03  |██████████████ 61.8%|
Nov 04  |████████ 38.9%|
Nov 05  |███████ 32.5%|
```

**Money-Making Instruction Should Say**:
> 💰 HOW TO MAKE MONEY: Identify trend changes in GEX. When GEX flips from positive to negative = buy calls on dips. When GEX flips from negative to positive = sell premium. Rising IV = buy straddles, falling IV = sell spreads.

**If Not Showing**:
1. Check browser console for:
   ```
   === FETCHING HISTORICAL DATA ===
   Symbol: SPY
   Historical data received: { count: 0, sample: null }
   ```

2. Backend issue: `api_client.get_historical_gamma()` returns empty
   - Trading Volatility API `/gex/history` endpoint may be failing
   - Rate limiting

3. Loading state stuck:
   - Check if `loadingHistory` is true forever
   - Network timeout

**Expected Behavior**:
- Fetches automatically when switching to Historical Analysis tab
- Only fetches once (not on every tab switch)
- If empty, shows: "No historical data available"

---

#### ✅ **30-Day Statistics** (Should Show When Historical Data Exists)
- [ ] Avg Net GEX
- [ ] Max GEX
- [ ] Min GEX
- [ ] Avg IV
- [ ] Avg Put/Call Ratio

**All values should be calculated** from `historicalData` array, not hardcoded.

---

#### ✅ **Regime Changes** (Should Show When Historical Data Exists)
- [ ] Auto-detected GEX flips (Positive → Negative or vice versa)
- [ ] Auto-detected IV changes (>10% spikes/drops)
- [ ] Days ago for each change

**Example**:
```
3 days ago: Negative → Positive GEX
7 days ago: IV Spike +15%
12 days ago: Positive → Negative GEX
```

---

#### ✅ **Correlation Analysis** (Should Show When Historical Data Exists)
- [ ] Price vs Net GEX correlation (-1 to +1)
- [ ] Price vs IV correlation
- [ ] Net GEX vs IV correlation
- [ ] Put/Call Ratio vs IV correlation

**Each should have**:
- Bar showing correlation strength
- Label: "Strong/Moderate/Weak positive/negative correlation"

---

### Evidence-Based Footer (MUST BE VISIBLE)

**Should Display at Bottom of Every Page**:
```
📚 EVIDENCE-BASED THRESHOLDS

All gamma metrics, win rates, and risk thresholds are based on: Academic research (Dim, Eraker, Vilkov 2023),
SpotGamma professional analysis, ECB Financial Stability Review 2023, and validated production trading data.
Context-aware adjustments for Friday expirations and high-VIX environments ensure accuracy across all market conditions.
```

**Check**:
- [ ] Footer visible on Overview tab
- [ ] Footer visible on Position Impact tab
- [ ] Footer visible on Historical Analysis tab
- [ ] Proper styling (border, background color)

---

## Page 2: `/gamma/0dte` - 0DTE Gamma Expiration Tracker

### Header Section

#### ✅ **Week Display** (Should Always Show)
- [ ] Current week range: "Week of 2025-11-03 to 2025-11-07"
- [ ] Today highlighted: "Today: Thursday" (or current day)

---

### VIEW 1: TODAY'S IMPACT

#### ✅ **Current Gamma Metrics** (Should Always Show)
- [ ] Current Gamma: $0.87B (green)
- [ ] After 4pm: $0.54B (yellow)
- [ ] Loss Today: -$0.33B (38%) (red)

**Real-Time Calculation**: Should update based on current day and estimated gamma decay

---

#### ✅ **Risk Level** (Should Always Show)
- [ ] Risk box with color coding
- [ ] EXTREME = red
- [ ] HIGH = orange
- [ ] MODERATE = blue
- [ ] LOW = green

---

#### ✅ **HIGH PRIORITY: Fade the Close** (Should Always Show)
- [ ] Red "HIGH PRIORITY" badge
- [ ] Strategy details:
  - Strike: 0.4 delta (first OTM)
  - Expiration: 0DTE or 1DTE
  - Entry: Thursday 3:45pm (or current day)
  - Exit: Tomorrow morning
  - Risk: 30% stop loss, 2-3% account risk

**Money-Making Explanation**:
> Why: Tomorrow loses X% gamma support - moves will be sharper without dealer hedging

---

#### ✅ **MEDIUM PRIORITY: ATM Straddle** (Should Always Show)
- [ ] Yellow "MEDIUM PRIORITY" badge
- [ ] Strategy details
- [ ] Clear entry/exit timing
- [ ] Risk management

---

### VIEW 2: WEEKLY EVOLUTION

#### ✅ **Weekly Gamma Structure Bars** (Should Always Show)
```
Mon 11-03  |████████████████████| $7.0B (100%)
Tue 11-04  |██████████████      | $5.0B (71%)
Wed 11-05  |████████            | $2.9B (42%)
📍Thu 11-06 |██                  | $0.9B (12%)  ← TODAY
Fri 11-07  |█                   | $0.5B (8%)
```

**Visual Requirements**:
- [ ] Gradient bars (green to red)
- [ ] Percentage labels
- [ ] Dollar amounts
- [ ] Today highlighted with 📍

---

#### ✅ **Aggressive Theta Farming (Mon-Wed)** (Should Always Show)
- [ ] Green success box
- [ ] Full strategy details with entry/exit
- [ ] Position sizing guidance
- [ ] Why it works explanation

**Money-Making Explanation**:
> Why: Week starts with 100% of gamma - high mean-reversion, options will decay fast

---

#### ✅ **Delta Buying (Thu-Fri)** (Should Always Show)
- [ ] Blue primary box
- [ ] Directional play guidance
- [ ] Strike selection (ATM or first OTM)

---

#### ✅ **Dynamic Position Sizing** (Should Always Show)
```
Mon-Tue: 100% normal size (gamma protects you)
Wed: 75% size (transition)
Thu-Fri: 50% size (gamma gone, vol spikes)
```

**Risk Management Explanation**:
> Why: 92% weekly decay means vol will increase significantly late week

---

### VIEW 3: VOLATILITY CLIFFS

#### ✅ **Daily Risk Grid** (Should Always Show)
```
Monday     Tuesday    Wednesday   Thursday    Friday
  29%        41%         70%         38%        100%
  ⚠️         🔶          🚨       📍 ⚠️         🚨
MODERATE     HIGH      EXTREME    MODERATE    EXTREME
```

**Visual Requirements**:
- [ ] Color-coded boxes
- [ ] Today has 📍 indicator
- [ ] Emoji risk indicators
- [ ] Risk level labels

---

#### ✅ **Pre-Expiration Volatility Scalp** (Should Always Show)
- [ ] Red "HIGH PRIORITY" badge for Friday
- [ ] 0DTE ATM straddle details
- [ ] Entry: Friday 10-11am
- [ ] Exit: Friday 2-3pm (BEFORE 4pm expiration)

**Money-Making Explanation**:
> Why: Friday has 100% gamma decay - massive expiration creates intraday volatility spike. Exit before pin risk at 4pm.

---

#### ✅ **Post-Expiration Directional** (Should Always Show)
- [ ] Yellow "MEDIUM PRIORITY" badge
- [ ] Long calls/puts setup
- [ ] Entry Friday 3:45pm
- [ ] Exit next day morning

---

#### ✅ **The Avoidance Strategy** (Should Always Show)
- [ ] Blue "LOW PRIORITY" badge
- [ ] Cash/sidelines option
- [ ] "Sometimes best trade is no trade"

---

### ACTIONABLE TRADE PLAYBOOK

#### ✅ **0DTE Straddle - Volatility Explosion** (Should Always Show)
```
Current Conditions (LIVE DATA):
- Symbol: SPY
- Net GEX: $0.58B
- Spot Price: $676.11
- Flip Point: $678.74
- Day: Thursday
- Expiration Today: Yes

Trade Structure:
- Buy ATM Call: $676.11 strike
- Buy ATM Put: $676.11 strike
- Expiration: TODAY (0DTE)
- Debit: $1.50 - $2.50 per straddle
- Breakevens: $674.11 / $678.11
```

**Check**:
- [ ] All values update based on selected symbol
- [ ] Spot price is current
- [ ] Breakevens calculated correctly
- [ ] Entry timing: 9:30-10:30 AM ET
- [ ] Exit rules clear
- [ ] Stop loss defined

---

### Evidence-Based Footer (MUST BE VISIBLE)

**Should Display**:
```
📚 EVIDENCE-BASED THRESHOLDS

Thresholds based on: Academic research (Dim, Eraker, Vilkov 2023), SpotGamma professional analysis,
ECB Financial Stability Review 2023, and validated production trading data.
Context-aware adjustments for Friday expirations and high-VIX environments.
```

---

## Common Issues & Solutions

### Issue 1: "Gamma Exposure by Strike Not Showing"

**Root Cause**: Backend `get_gex_profile()` returns empty `strikes` array

**Debug Steps**:
1. Open browser console (F12)
2. Look for log: `Intelligence data: { has_strikes: false, strikes_count: 0 }`
3. Check backend logs for errors from Trading Volatility API

**Solutions**:
- Check Trading Volatility API rate limits (20 per minute for non-realtime)
- Verify `TV_USERNAME` environment variable is set
- Check if API key is valid
- May need to add caching to reduce API calls

---

### Issue 2: "Historical Analysis Charts Not Showing"

**Root Cause**: `get_historical_gamma()` returns empty array

**Debug Steps**:
1. Open console, switch to Historical Analysis tab
2. Look for: `=== FETCHING HISTORICAL DATA ===`
3. Check: `Historical data received: { count: 0 }`

**Solutions**:
- Trading Volatility `/gex/history` endpoint may require different parameters
- May need to increase timeout (currently 120s)
- Check if historical data exists for symbol

---

### Issue 3: "Position Impact Tab Content Overlapping"

**Root Cause**: Flex/grid layout issues or missing container divs

**Debug Steps**:
1. Inspect element in browser
2. Check z-index values
3. Look for missing closing divs

**Solutions**:
- Add proper container divs with spacing
- Use flexbox gap properties
- Check CSS class conflicts

---

### Issue 4: "Scanner Times Out with 18 Symbols"

**Root Cause**: Serial processing takes too long (18 × 3 seconds = 54+ seconds)

**Solution**: Implement per-symbol timeout in backend:
```python
TIMEOUT_PER_SYMBOL = 10  # seconds

# Wrap each symbol scan in try/except with timeout
try:
    result = scan_symbol_with_timeout(symbol, timeout=10)
except TimeoutError:
    print(f"Skipping {symbol} - timeout")
    continue
```

---

### Issue 5: "AI Trade Setups Not Finding Strategies"

**Root Cause**: Not using `STRATEGIES` dict with actual win_rates

**Solution**: See `GAMMA_INTELLIGENCE_FIXES_NEEDED.md` for complete code to replace hardcoded confidence levels with actual strategy configurations.

---

## Testing Protocol

### Step 1: Open Browser Console (F12)
- Keep console open throughout testing
- Look for error messages in red
- Check for successful API calls

### Step 2: Test Each Page Systematically
- Go through this checklist item by item
- Mark what's working ✅ and what's not ❌
- Take screenshots of issues

### Step 3: Record Console Logs
- Copy console output for debugging
- Note which API calls succeed/fail
- Check timing of data fetches

### Step 4: Test with Multiple Symbols
- Try SPY, QQQ, IWM
- See if some work and others don't
- May indicate rate limiting issues

---

## Success Criteria

**A feature is considered "working" when**:
1. ✅ Data displays correctly (no "Coming soon" or empty states)
2. ✅ "How to Make Money" instruction is clear and visible
3. ✅ User understands what action to take from the information
4. ✅ Evidence-based thresholds are cited
5. ✅ No console errors related to that feature

**The website is "complete" when**:
- All checkboxes in this document are ✅
- No "Coming soon" placeholders anywhere
- Every feature has clear profit-making guidance
- Evidence-based research is cited throughout
- All calculations use real data (not mocks/estimates)

---

## Priority Order for Fixes

**🔴 CRITICAL (Fix First)**:
1. Gamma Exposure by Strike not showing
2. Exposure Impact Over Price Range not showing
3. Gamma Exposure Trends not showing

**🟡 HIGH (Fix Soon)**:
4. Scanner timeout with 18 symbols
5. AI Trade Setups not using STRATEGIES win_rates
6. Position Impact tab overlapping content

**🟢 MEDIUM (Enhance)**:
7. Add win rate highlighting (>70% setups)
8. Filter setups to only show >50% win rate
9. Sort setups by win rate (highest first)

**🔵 LOW (Polish)**:
10. Add more tooltips explaining metrics
11. Add contextual help ("What is GEX Flip Point?")
12. Improve mobile responsiveness
