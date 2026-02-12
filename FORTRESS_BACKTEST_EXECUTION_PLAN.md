# FORTRESS Iron Condor — Backtesting Execution Plan & Profitability Proof Framework

> **Code-verified 2026-02-11 against live FORTRESS source.**
> Parameters reconciled with `trading/fortress_v2/models.py`, `signals.py`, `trader.py`.
> Corrections from original draft marked with **[CODE-FIX]**.

-----

## YOUR MISSION

You are building and executing a rigorous backtest for **FORTRESS**, a **3-trading-day DTE** Iron Condor bot trading **SPY** options. Your job is NOT to prove the strategy works — it is to determine IF it works, and if so, under what conditions. You must follow this plan sequentially. Do not skip phases. Do not declare success without passing every gate.

This plan is structured as a **phased execution pipeline** with hard GO/NO-GO gates. If a phase fails its gate, you stop, diagnose, and fix before proceeding.

**[CODE-FIX] DTE is 3 trading days, not 2.** The live config (`models.py:235`) specifies `min_dte: int = 3`. The `_get_target_expiration()` method counts trading days skipping weekends and holidays via `MarketCalendar`. The backtest tests DTE 0-5 to find the optimum, but the baseline uses 3.

-----

## PHASE 0: DATA ACQUISITION & VALIDATION

**Duration:** 1-2 sessions | **Gate:** Clean dataset ready for backtesting

### Tasks

1. **Check ORAT database first** (your own data, higher quality than GitHub):
   ```sql
   -- What do you have?
   SELECT ticker, MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date)
   FROM orat_options_eod GROUP BY ticker;

   -- SPY 2-5 DTE coverage?
   SELECT dte, COUNT(DISTINCT trade_date) as days, MIN(trade_date), MAX(trade_date)
   FROM orat_options_eod WHERE ticker = 'SPY' AND dte BETWEEN 1 AND 5
   GROUP BY dte ORDER BY dte;

   -- Bid-ask quality for 3DTE
   SELECT AVG(call_ask - call_bid) as avg_call_spread,
          AVG(put_ask - put_bid) as avg_put_spread
   FROM orat_options_eod
   WHERE ticker = 'SPY' AND dte BETWEEN 2 AND 4 AND call_bid > 0 AND put_bid > 0;
   ```

2. **If ORAT is insufficient**, download free SPY options data:
   - **Primary:** `https://static.philippdubach.com/data/options/spy/options.parquet` (free, 2008-2025, includes bid/ask/Greeks/IV)
   - **Secondary:** `https://github.com/philippdubach/options-dataset-hist` (yearly parquet files with underlying OHLCV included)

3. Download supplementary data via `yfinance`:
   - SPY daily OHLCV (2018-2025)
   - VIX daily close (^VIX)
   - SPY dividend/ex-dividend dates

4. Build economic calendar:
   - FOMC meeting dates (announcement days)
   - CPI release dates
   - NFP (Non-Farm Payrolls) release dates
   - Quadruple witching / monthly OPEX dates
   - Source: FRED API or manual CSV

5. Data validation checks — run ALL before proceeding:

| Check | Pass Criteria | Action if Fail |
|-------|---------------|----------------|
| Missing trading days | < 2% gaps | Fill or flag |
| Bid = 0 or Ask = 0 | < 1% of rows | Remove those rows |
| Bid > Ask | 0 occurrences | Remove — bad data |
| Ask - Bid > 50% of mid | Flag but keep | Mark as "illiquid" |
| Options with 0 volume AND 0 OI | Flag | Exclude from strike selection |
| Duplicate rows (same date/strike/exp/type) | 0 | Deduplicate |
| NULL values in critical columns | 0 after cleaning | Drop or impute |
| Date alignment: options dates match SPY price dates | 100% match | Investigate gaps |
| 3DTE expirations exist | Confirm daily expiration availability | Adjust DTE logic if needed |

### Deliverable

- `fortress_clean_data.parquet` — Joined dataset: options chain + underlying price + VIX + day features
- `data_quality_report.md` — Summary of all validation checks with pass/fail

### Gate 0: GO/NO-GO

- [ ] All validation checks pass or have documented handling
- [ ] At least 4 years of clean 3DTE data available (2020-2024 minimum)
- [ ] Dataset includes bid, ask, strike, expiration, type, delta (or IV to calculate delta)

-----

## PHASE 1: SINGLE TRADE VALIDATION

**Duration:** 1 session | **Gate:** One trade traces correctly from entry to settlement

### Tasks

1. Pick a specific date (e.g., a Monday with Thursday expiration = 3 trading days)
2. Construct one iron condor **matching FORTRESS production logic exactly**:
   - **[CODE-FIX]** Find the expiration 3 **trading days** out (skip weekends/holidays)
   - **[CODE-FIX]** Select strikes using **SD-based math** (production method), NOT delta:
     ```python
     expected_move = spot * (vix / 100) / sqrt(252)  # 1-day EM (this is what live uses)
     sd = 1.2  # Hard floor from signals.py:434
     put_short = floor(spot - sd * expected_move)
     call_short = ceil(spot + sd * expected_move)
     put_long = put_short - 5  # $5 wide (models.py:230)
     call_long = call_short + 5
     ```
   - Record bid/ask for all 4 legs
3. Calculate:
   - Net credit using **natural prices** (sell at bid, buy at ask) — this is what production uses first
   - Also calculate at mid-price for comparison
   - Max profit = net credit × 100 × contracts
   - Max loss = (spread_width - net credit) × 100 × contracts
   - **[CODE-FIX]** Min credit check: total_credit >= $0.05 (`config.min_credit`)
4. Trace forward through each day to expiration:
   - **[CODE-FIX]** This is a MULTI-DAY position (3DTE = 3 days of exposure)
   - Look up the SAME expiration in ORAT/options data on each intermediate day
   - Mark to market daily
   - Check profit target each day: IC value <= credit × (1 - 50/100) = 50% of entry credit
5. At expiration:
   - Check SPY closing price (4:00 PM ET settlement)
   - Calculate settlement value for each leg
   - Confirm final P&L matches hand calculation
6. **Also construct the same trade using the EM-scaling variant:**
   ```python
   em_scaled = spot * (vix / 100) / sqrt(252) * sqrt(3)  # Scale for 3DTE
   # This puts strikes ~$6 further from spot
   ```
   Compare the two outcomes.

### Deliverable

- Single trade walkthrough document showing every number for BOTH EM variants
- Confirmation that entry pricing, daily MTM, and settlement all compute correctly

### Gate 1: GO/NO-GO

- [ ] Single trade P&L matches hand-calculated expected result
- [ ] Settlement logic handles all 4 outcomes: (a) all OTM, (b) put breached, (c) call breached, (d) both breached
- [ ] Multi-day MTM repricing works correctly (prices exist for intermediate days)
- [ ] EM variant A vs B produces different strikes and different outcomes

-----

## PHASE 2: BASELINE BACKTEST (NO FILTERS, NO OPTIMIZATION)

**Duration:** 2-3 sessions | **Gate:** Baseline stats establish whether there's any edge at all

### Configuration — Production Parameters (no optimization yet)

**[CODE-FIX]** These parameters now match the actual `FortressConfig`:

```
Symbol:             SPY
DTE:                3 (trading days, not calendar)        [CODE-FIX: was 2]
Strike selection:   1.2 SD from spot (pure math)          [CODE-FIX: was "16 delta"]
Wing width:         $5                                    [CODE-FIX: was $2]
Expected move:      spot × (VIX/100) / sqrt(252)          [1-day EM — current live]
Entry time:         Use EOD data on entry day as proxy
Exit:               Hold to expiration (no early exit) for baseline
Slippage:           $0.04 per IC (4 legs × $0.01/leg)
Commissions:        $0.65/contract/leg × 4 legs = $2.60/contract to open
                    If closed early: another $2.60 to close = $5.20 total
                    If expires worthless: $2.60 only
Fill method:        Natural prices (sell at bid, buy at ask) [CODE-FIX: production uses natural first]
Capital:            $100,000                               [CODE-FIX: was $50K]
Risk per trade:     15% of capital ($15,000 max risk)      [CODE-FIX: was $200 fixed]
Max contracts:      75                                     [CODE-FIX: was "1 contract"]
Concurrent trades:  Up to 3 (3DTE means overlap possible)  [CODE-FIX: was "1 at a time"]
Max trades/day:     3                                      [CODE-FIX: new — allows re-entry]
Min credit:         $0.05 per spread                       [CODE-FIX: new]
Filters:            NONE (trade every day, only skip VIX > 50)
Period:             2020-01-01 to 2024-12-31
```

### Why These Differ From the Original Draft

| Parameter | Original Draft | Actual Production | Impact |
|-----------|---------------|-------------------|--------|
| DTE | 2 | 3 | More theta, wider risk window |
| Strike method | 16 delta | 1.2 SD from EM | Different strike placement logic |
| Wing width | $2 | $5 | 2.5x more risk per contract, more premium |
| Capital | $50K | $100K | Different sizing |
| Risk/trade | $200 fixed (1 contract) | 15% of equity ($15K) | Up to 75 contracts, not 1 |
| Concurrent | 1 | 3 max | Capital tied up in multiple positions |
| Fill method | Mid minus slippage | Natural (bid/ask) | More conservative, realistic |

### Tasks

1. Build the trade engine matching FORTRESS logic:
   - For each trading day, count 3 trading days forward (skip weekends/holidays)
   - Calculate expected move: `spot × (VIX/100) / sqrt(252)` (1-day, matching live bug)
   - Select strikes at 1.2 SD: `floor(spot - 1.2×EM)` for put, `ceil(spot + 1.2×EM)` for call
   - Wings $5 wide
   - Get credits from bid/ask (natural fills)
   - Reject if total credit < $0.05
   - Size: `min(floor(0.15 × equity / max_loss_per_contract), 75)`
2. Simulate multi-day lifecycle:
   - **Day 0 (entry):** Record IC, credit, position size
   - **Day 1, Day 2:** Reprice IC using options data for same expiration. Check profit target (50%).
   - **Day 3 (expiration):** Settlement at SPY close
3. Calculate ALL baseline stats

### ALSO run Variant B (EM scaling):
Same as above but with `EM = spot × (VIX/100) / sqrt(252) × sqrt(DTE)`. This is the "potentially correct" formula. Compare side-by-side.

### Gate 2: GO/NO-GO

The baseline must pass **at least 4 of these 6** to proceed:

| Metric | Minimum Threshold | Variant A (1-day EM) | Variant B (scaled EM) |
|--------|-------------------|---------------------|----------------------|
| Win Rate | > 60% | ___ | ___ |
| Profit Factor | > 1.2 | ___ | ___ |
| Average Trade P&L (after costs) | > $0 | ___ | ___ |
| Max Drawdown | < 30% of peak equity | ___ | ___ |
| Sharpe Ratio (annualized) | > 0.5 | ___ | ___ |
| Sample Size | > 200 trades | ___ | ___ |

**Pick the better EM variant and carry it forward.** If Variant B is clearly superior, this identifies a bug fix for production.

**If baseline fails BOTH variants:** The raw strategy has no edge at 3DTE. Test other DTE values (0, 1, 2, 4, 5) before giving up. If no DTE works, the strategy needs fundamental redesign.

-----

## PHASE 2.5: DTE SWEEP (NEW — CRITICAL)

**Duration:** 1-2 sessions | **Gate:** Optimal DTE identified

**[CODE-FIX]** This phase doesn't exist in the original plan. Since FORTRESS recently changed from 0DTE to 3DTE, we MUST validate this was the right move.

### Test Matrix

Using the winning EM variant from Phase 2, with all other params fixed at production values:

| DTE | Win Rate | Profit Factor | Avg Credit | Avg P&L | Sharpe | Max DD | Sample Size |
|-----|----------|---------------|------------|---------|--------|--------|-------------|
| 0 | ___ | ___ | ___ | ___ | ___ | ___ | ___ |
| 1 | ___ | ___ | ___ | ___ | ___ | ___ | ___ |
| 2 | ___ | ___ | ___ | ___ | ___ | ___ | ___ |
| 3 | ___ | ___ | ___ | ___ | ___ | ___ | ___ |
| 4 | ___ | ___ | ___ | ___ | ___ | ___ | ___ |
| 5 | ___ | ___ | ___ | ___ | ___ | ___ | ___ |

### Gate 2.5: GO/NO-GO

- [ ] At least one DTE value passes the Phase 2 gate thresholds
- [ ] The optimal DTE is clearly identified (or 2-3 DTEs are comparable = robust)
- [ ] If DTE=3 is NOT the best, document the recommendation to change production

-----

## PHASE 3: FILTER TESTING

**Duration:** 2-3 sessions | **Gate:** Filters improve risk-adjusted returns without destroying trade count

### Test Each Filter Independently

Using the best DTE + EM variant from prior phases:

| Filter | Test Values | Metric to Watch |
|--------|-------------|-----------------|
| VIX Max | 25, 30, 32, 35, 50 (current live) | Does removing high-VIX days improve Sharpe? |
| VIX Spike (1-day change) | > 10%, > 15%, > 20% | Does avoiding spike days reduce max DD? |
| FOMC Days | Skip day-of and day-after | Does win rate improve? |
| CPI/NFP Days | Skip release days | Same |
| Low IV Rank | Skip if IV rank < 15, < 20, < 25 | Does removing low-IV days improve avg credit? |
| Day of Week | Test each day excluded | Are certain days consistently worse? |
| Trend Strength (ADX) | Skip if ADX > 25, > 30 | Does avoiding trends improve win rate? |
| Earnings Season | Skip peak weeks | Is performance worse during earnings? |
| GEX Regime | Only POSITIVE, only between walls | Does GEX filtering help ICs? |
| Min Credit Threshold | $0.05, $0.10, $0.15, $0.20 | Does rejecting low-credit trades help? |
| Consecutive Loss Cooldown | Pause after 3 losses (5 min, 1 hour, 1 day) | Matches PROVERBS behavior |

**[CODE-FIX]** Added GEX regime and min credit filters — these exist in production. Added consecutive loss cooldown — this is how PROVERBS works in production (5-min pause after 3 losses, `trader.py:270-315`).

### For Each Filter, Record:

| Metric | No Filter (Baseline) | With Filter | Delta |
|--------|---------------------|-------------|-------|
| Trade Count | ___ | ___ | ___ |
| Win Rate | ___ | ___ | ___ |
| Profit Factor | ___ | ___ | ___ |
| Sharpe Ratio | ___ | ___ | ___ |
| Max Drawdown | ___ | ___ | ___ |
| Avg Trade P&L | ___ | ___ | ___ |

### Gate 3: GO/NO-GO

- [ ] At least 2 filters improve Sharpe by > 0.1 without reducing trade count by > 40%
- [ ] Combined filters still leave > 150 trades in the sample
- [ ] No single filter is responsible for > 50% of the improvement (fragile)

-----

## PHASE 4: EXIT OPTIMIZATION

**Duration:** 2-3 sessions | **Gate:** Optimal exit rules improve returns vs hold-to-expiration

### Test Exit Strategies

**[CODE-FIX]** The profit target in production is computed as:
```python
# From trader.py:1394-1397
profit_target_value = pos.total_credit * (1 - config.profit_target_pct / 100)
# At 50%: IC must cost <= 50% of original credit to buy back
if current_value <= profit_target_value:
    close
```

**Profit Targets (% of credit to close at):**
- 25%, 50% (production default), 75%, hold to expiration

**Stop Losses (multiple of credit received):**
- None (production default), 1x credit, 1.5x credit, 2x credit (production fallback if enabled)

**Time Exits:**
- Force close at 14:50 CT on expiration day (production default)
- Close EOD day before expiration if > 50% profit
- Close at 3:45 PM ET on expiration day

**Grid (fill each cell with: Sharpe | PF | Win% | Max DD):**

|          | No Stop | 1x Stop | 1.5x Stop | 2x Stop |
|----------|---------|---------|-----------|---------|
| **No PT** | Baseline | ___ | ___ | ___ |
| **25% PT** | ___ | ___ | ___ | ___ |
| **50% PT (prod)** | ___ | ___ | ___ | ___ |
| **75% PT** | ___ | ___ | ___ | ___ |

### Gate 4: GO/NO-GO

- [ ] Best exit combo improves Sharpe by > 0.15 vs hold-to-expiration
- [ ] Best exit combo reduces max drawdown by > 15% vs hold-to-expiration
- [ ] Performance improvement is consistent across at least 3 of 4 test years

-----

## PHASE 5: STRIKE SELECTION COMPARISON

**Duration:** 2 sessions | **Gate:** Optimal strike method identified

### Test These Methods (using best filters + exits from prior phases)

**[CODE-FIX]** SD-based is the production method. Others are alternatives to compare against.

| Method | Description | Key Parameter | Production? |
|--------|-------------|---------------|------------|
| **SD-Based** | Strikes at N × expected move from spot | Test 1.0, 1.1, **1.2 (prod)**, 1.3, 1.5 SD | **YES** |
| Fixed Delta | Short strikes at target delta | Test 10d, 16d, 20d, 25d | No |
| OTM Percentage | Fixed % from current price | Test 0.5%, 1.0%, 1.5%, 2.0% | No |
| Expected Move | Place at +/-1x implied expected move | From ATM straddle | No |
| ATR-Based | Strikes at price +/- (N x ATR14) | Test 0.5x, 1.0x, 1.5x ATR | No |

### Wing Width Comparison

**[CODE-FIX]** Production is $5. Test others for comparison:

| Width | Credit Impact | Risk Impact | Notes |
|-------|--------------|-------------|-------|
| $2 | Lower | Lower | Old FORTRESS config (abandoned — no premium) |
| $3 | Medium | Medium | |
| **$5** | Higher | Higher | **Current production** |
| $7 | Higher still | Higher | |
| $10 | Highest | Highest | |

### Gate 5: GO/NO-GO

- [ ] One strike method clearly dominates (> 0.2 Sharpe advantage) OR multiple are comparable (robust)
- [ ] Wing width sweet spot identified with clear risk/reward tradeoff
- [ ] SD-based (production) is either validated or a better alternative is identified

-----

## PHASE 6: WALK-FORWARD VALIDATION

**Duration:** 2 sessions | **Gate:** Strategy isn't overfit

### Method

1. **In-sample:** Optimize on rolling 12-month windows
2. **Out-of-sample:** Test on the next 3 months (no peeking)
3. **Roll forward** by 3 months, repeat

```
Window 1: Train 2020-01 to 2020-12 -> Test 2021-01 to 2021-03
Window 2: Train 2020-04 to 2021-03 -> Test 2021-04 to 2021-06
Window 3: Train 2020-07 to 2021-06 -> Test 2021-07 to 2021-09
... continue through 2024
```

4. Concatenate ALL out-of-sample periods = your "true" performance

### Gate 6: GO/NO-GO

- [ ] Out-of-sample Sharpe is within 40% of in-sample Sharpe
- [ ] Out-of-sample win rate is within 10 percentage points of in-sample
- [ ] No single OOS quarter has drawdown > 2x the in-sample average max DD
- [ ] Parameters chosen in-sample are stable (don't wildly change each window)

**If this fails: the strategy is overfit. Go back to Phase 2 and simplify.**

-----

## PHASE 7: MONTE CARLO STRESS TEST

**Duration:** 1 session | **Gate:** Worst-case scenarios are survivable

### Method

1. Take the final trade list from Phase 6 (OOS results)
2. Randomly shuffle trade order 10,000 times
3. For each shuffle, calculate max drawdown, max consecutive losses, ending equity
4. Build distributions

### Report These Percentiles

| Metric | 5th %ile (Worst) | 25th %ile | Median | 75th %ile | 95th %ile (Best) |
|--------|-----------------|-----------|--------|-----------|-----------------|
| Max Drawdown ($) | ___ | ___ | ___ | ___ | ___ |
| Max Drawdown (%) | ___ | ___ | ___ | ___ | ___ |
| Max Consecutive Losses | ___ | ___ | ___ | ___ | ___ |
| Ending Equity | ___ | ___ | ___ | ___ | ___ |

### Additional Stress Scenarios

Run the backtest specifically through these periods:
- **COVID crash** (Feb-Mar 2020): VIX > 80, daily 5%+ moves
- **2022 bear market** (Jan-Oct 2022): Sustained downtrend, elevated VIX
- **2017/2024 low-vol grind**: VIX < 15, thin premiums
- **Quad witching weeks**: Monthly OPEX pin risk
- **SPY ex-dividend dates**: Early assignment risk on short calls

### Gate 7: GO/NO-GO

- [ ] 95th percentile worst-case max drawdown < 40% of starting capital
- [ ] 95th percentile max consecutive losses < 10
- [ ] Median ending equity is positive
- [ ] 5th percentile ending equity is still > 70% of starting capital
- [ ] Strategy doesn't blow up in any single stress scenario (DD < 50%)

-----

## PHASE 8: FINAL PROFITABILITY SCORECARD

**Duration:** 1 session | **Gate:** Strategy gets a final GO/NO-GO for live deployment

### The 25 Stats That Prove (or Disprove) FORTRESS Is Profitable

**CATEGORY 1: Does It Make Money?**

| # | Stat | Target | Result | Pass? |
|---|------|--------|--------|-------|
| 1 | Total Net P&L | > $0 | ___ | [ ] |
| 2 | Avg Trade P&L | > $5/trade | ___ | [ ] |
| 3 | Median Trade P&L | > $0 | ___ | [ ] |
| 4 | Win Rate | > 55% | ___ | [ ] |
| 5 | Profit Factor | > 1.3 | ___ | [ ] |
| 6 | Expected Value per Trade | > $3 after costs | ___ | [ ] |
| 7 | Annualized Return on Capital | > 15% | ___ | [ ] |

**CATEGORY 2: Is the Edge Real or Luck?**

| # | Stat | Target | Result | Pass? |
|---|------|--------|--------|-------|
| 8 | Sample Size | > 200 | ___ | [ ] |
| 9 | t-Statistic | > 2.0 (p < 0.05) | ___ | [ ] |
| 10 | Sharpe Ratio (annualized) | > 1.0 | ___ | [ ] |
| 11 | Sortino Ratio | > 1.5 | ___ | [ ] |
| 12 | OOS vs IS Sharpe Ratio | > 0.6 | ___ | [ ] |
| 13 | Walk-Forward Efficiency | > 70% of OOS periods profitable | ___ | [ ] |
| 14 | P&L Skewness | > -0.5 (not extremely left-tailed) | ___ | [ ] |

**CATEGORY 3: Can You Survive the Bad Times?**

| # | Stat | Target | Result | Pass? |
|---|------|--------|--------|-------|
| 15 | Max Drawdown ($) | < 20% of capital | ___ | [ ] |
| 16 | Max Drawdown Duration | < 60 trading days | ___ | [ ] |
| 17 | Max Consecutive Losses | < 8 | ___ | [ ] |
| 18 | Largest Single Loss | < 3% of capital | ___ | [ ] |
| 19 | Calmar Ratio | > 1.0 | ___ | [ ] |
| 20 | 95% VaR (daily) | < 2% of capital | ___ | [ ] |
| 21 | Monte Carlo 95th %ile Max DD | < 30% of capital | ___ | [ ] |

**CATEGORY 4: Is It Robust Across Conditions?**

| # | Stat | Target | Result | Pass? |
|---|------|--------|--------|-------|
| 22 | Performance in VIX < 20 | Profitable | ___ | [ ] |
| 23 | Performance in VIX 20-30 | Profitable OR flat | ___ | [ ] |
| 24 | Performance in VIX > 30 | Not catastrophic (DD < 15%) | ___ | [ ] |
| 25 | Worst Calendar Month | > -8% of capital | ___ | [ ] |

### FINAL VERDICT

| Score | Verdict | Action |
|-------|---------|--------|
| 22-25 passes | GO LIVE | Deploy with full position sizing |
| 18-21 passes | CONDITIONAL GO | Deploy at 50% size, monitor 30 days |
| 14-17 passes | PAPER TRADE | Run paper 60 days, re-evaluate |
| < 14 passes | NO GO | Strategy needs fundamental redesign |

-----

## STATS CALCULATION REFERENCE

```python
import numpy as np
from scipy import stats

# === CORE TRADE METRICS ===
total_trades = len(trades)
winners = trades[trades['pnl'] > 0]
losers = trades[trades['pnl'] <= 0]

win_rate = len(winners) / total_trades
avg_win = winners['pnl'].mean()
avg_loss = abs(losers['pnl'].mean())
profit_factor = winners['pnl'].sum() / abs(losers['pnl'].sum())
expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

# === RISK-ADJUSTED RETURNS ===
daily_returns = equity_curve.pct_change().dropna()
n_days = len(daily_returns)
annualized_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (252 / n_days) - 1
annualized_vol = daily_returns.std() * np.sqrt(252)
risk_free_rate = 0.05  # ~5% fed funds rate 2024-2025
sharpe = (annualized_return - risk_free_rate) / annualized_vol

downside_returns = daily_returns[daily_returns < 0]
downside_vol = downside_returns.std() * np.sqrt(252)
sortino = (annualized_return - risk_free_rate) / downside_vol

# === DRAWDOWN ===
rolling_max = equity_curve.cummax()
drawdown = (equity_curve - rolling_max) / rolling_max
max_drawdown = drawdown.min()
# Max DD duration: longest streak where drawdown < 0
dd_active = (drawdown < 0).astype(int)
dd_groups = dd_active.groupby((dd_active != dd_active.shift()).cumsum())
max_dd_duration = dd_groups.sum().max() if len(dd_groups) > 0 else 0
calmar = annualized_return / abs(max_drawdown)

# === STATISTICAL SIGNIFICANCE ===
t_stat, p_value = stats.ttest_1samp(trades['pnl'], 0)
# t_stat > 2.0 means p < 0.05 = statistically significant edge

# === DISTRIBUTION ===
skewness = trades['pnl'].skew()
kurtosis = trades['pnl'].kurtosis()
var_95 = np.percentile(trades['pnl'], 5)  # 5th percentile = 95% VaR
cvar_95 = trades['pnl'][trades['pnl'] <= var_95].mean()  # Expected shortfall

# === CONSECUTIVE LOSSES ===
is_loss = (trades['pnl'] <= 0).astype(int)
max_consecutive_losses = is_loss.groupby(
    (is_loss != is_loss.shift()).cumsum()
).sum().max()
```

-----

## VISUALIZATION REQUIREMENTS

Charts to generate at each phase:

1. **Equity Curve** — Cumulative P&L with drawdown shaded below
2. **Monthly Returns Heatmap** — Rows = years, columns = months, color = return %
3. **P&L Distribution Histogram** — With normal overlay and skew annotation
4. **Drawdown Chart** — DD % from peak over time
5. **Win Rate Rolling 30-Trade** — Shows if edge is consistent or degrading
6. **Performance by VIX Regime** — Bar chart: win rate + avg P&L by VIX bucket
7. **Performance by Day of Week** — Mon-Fri grouped bars
8. **DTE Comparison Chart** — Side-by-side DTE=0 through DTE=5 (Phase 2.5)
9. **EM Variant Comparison** — Variant A vs B equity curves overlaid
10. **Parameter Sensitivity Heatmap** — Sharpe across SD x wing width grid
11. **Monte Carlo Drawdown Distribution** — Histogram of 10K simulated max DDs
12. **Walk-Forward Equity Curve** — Only OOS periods concatenated

-----

## CROSS-REFERENCE WITH LIVE DATA

After completing the backtest, validate against production:

1. **fortress_closed_trades table:** Pull all historical FORTRESS trades. Compare:
   - Backtest win rate vs live win rate
   - Backtest avg P&L vs live avg P&L
   - If gap > 20%, investigate execution quality

2. **fortress_scan_activity table:** Every scan with market context:
   - Compare backtest trade/no-trade decisions against scan decisions
   - Look for systematic differences (backtest trades when live skipped, or vice versa)

3. **Prophet/FortressMLAdvisor predictions:**
   - Did high-confidence TRADE signals correlate with winning trades?
   - Did SKIP signals correlate with losing days?
   - Validates whether the ML layer adds value

4. **GEX data (gex_daily, gex_structure_daily):**
   - Does `between_walls` actually predict IC success?
   - Does negative gamma correlate with FORTRESS losses?
   - Does `gex_regime = POSITIVE` predict better outcomes?

5. **PROVERBS consecutive loss data:**
   - Were there drawdown periods where a pause would have helped?
   - Does the 5-min cooldown make any statistical difference?

-----

## EXPECTED MOVE BUG — DEDICATED ANALYSIS

**[CODE-FIX]** This section is NEW. The live code has a potential bug that could change everything.

### The Issue

`signals.py:350-359` calculates expected move as:
```python
expected_move = spot * (vix / 100) / sqrt(252)  # ALWAYS 1-day
```

This is used for strike placement regardless of DTE. For 3DTE positions, the theoretically correct formula is:
```python
expected_move_3d = spot * (vix / 100) / sqrt(252) * sqrt(3)  # ~1.73x larger
```

### Concrete Impact (VIX=20, SPY=$600)

| Metric | Variant A (1-day EM, current live) | Variant B (3-day EM, correct?) |
|--------|-----------------------------------|-------------------------------|
| Expected Move | $7.56 | $13.09 |
| Put Short (1.2 SD) | $590.93 -> $590 | $584.29 -> $584 |
| Call Short (1.2 SD) | $609.07 -> $610 | $615.71 -> $616 |
| IC Width (short to short) | $20 | $32 |
| Expected Credit | Higher (closer strikes) | Lower (wider strikes) |
| Expected Win Rate | Lower (tighter) | Higher (wider) |

**Variant A** collects more premium but gets breached more often.
**Variant B** collects less but wins more often.

The backtest MUST determine which produces better risk-adjusted returns.

### If Variant B Wins

This is a production bug fix. Update `signals.py` to:
```python
def _calculate_expected_move(self, spot: float, vix: float, dte: int = 1) -> float:
    annual_factor = math.sqrt(252)
    daily_vol = (vix / 100) / annual_factor
    expected_move = spot * daily_vol * math.sqrt(max(dte, 1))
    return round(expected_move, 2)
```

-----

## WHAT TO DO WITH THE RESULTS

### If FORTRESS Passes (22+ of 25 stats):

1. Document the final parameter set
2. If EM variant B won: deploy the bug fix to `signals.py`
3. If DTE != 3 was better: update `models.py:235` with optimal DTE
4. If VIX filter should be re-enabled: update `check_vix_filter()`
5. Retrain FortressMLAdvisor on the backtest data: `fortress_ml_advisor.train_from_chronicles()`
6. Deploy at 50% size for 30 days as validation
7. Compare live results weekly against backtest expectations

### If FORTRESS Fails:

1. Document exactly which stats failed and by how much
2. Determine if failure is fundamental (no edge) or fixable (wrong params)
3. If fundamental: consider pivoting to different DTE, ticker (SPX?), or structure
4. If fixable: go back to earliest failing phase and iterate
5. Do NOT deploy a failing strategy

### If FORTRESS is Borderline (18-21):

1. Paper trade for 60 days
2. Compare paper results to backtest
3. If paper matches or exceeds backtest: deploy at 25% size
4. If paper underperforms by > 30%: execution assumptions are wrong, revisit slippage

-----

## FIRST STEPS — START HERE

1. **Run ORAT data availability queries** (Phase 0, task 1)
2. If ORAT has SPY 3DTE data: use it. If not: download philippdubach data
3. **Build ONE baseline trade** (Phase 1) with BOTH EM variants
4. **Validate** against hand calculations and (if available) a real FORTRESS trade from `fortress_closed_trades`
5. **Run baseline backtest** (Phase 2) for DTE=3 with both EM variants
6. **Run DTE sweep** (Phase 2.5) to validate 3DTE was the right choice
7. Continue through phases sequentially
