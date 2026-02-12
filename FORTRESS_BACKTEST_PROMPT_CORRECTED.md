# FORTRESS 2-3DTE Iron Condor — Master Backtesting Prompt (Code-Verified)

> **This prompt was cross-referenced against the actual FORTRESS codebase on 2026-02-11.**
> Every parameter, formula, and decision path was verified against the live production code.
> Discrepancies from the original draft are marked with ⚠️ CORRECTION.

-----

## ROLE & CONTEXT

You are an expert quantitative options strategist and Python developer specializing in short-dated iron condor backtesting. You have deep knowledge of options Greeks, volatility surfaces, dealer gamma positioning, and realistic execution modeling.

You are helping me backtest **FORTRESS**, a **3-trading-day DTE** Iron Condor bot that trades **SPY** options. FORTRESS is part of the AlphaGEX autonomous trading platform which includes multiple bots (ARES, ATHENA, TITAN, PEGASUS, ICARUS, PROMETHEUS, PHOENIX, ATLAS), AI/ML advisory systems (Prophet, SAGE, ORION, FortressMLAdvisor), and a GEXIS AI assistant.

-----

## FORTRESS BOT SPECIFICATION — VERIFIED FROM SOURCE CODE

### ⚠️ CORRECTION: DTE is 3, Not 2

The live `FortressConfig` in `trading/fortress_v2/models.py:235` specifies:

```python
min_dte: int = 3  # Minimum 3 trading days to expiration
```

The `_get_target_expiration()` method in `signals.py:176-213` counts **trading days** (skipping weekends and market holidays via `MarketCalendar`):

```
Monday    → Thursday  (3 trading days)
Tuesday   → Friday    (3 trading days)
Wednesday → next Monday (3 trading days, skips weekend)
Thursday  → next Tuesday (3 trading days, skips weekend)
Friday    → next Wednesday (3 trading days, skips weekend)
```

**The backtest MUST test DTE = 0, 1, 2, 3, 4, 5 to find the optimal value. The current live setting of 3 is what needs validation.**

### Strategy Overview

- **Instrument:** SPY options (always SPY, never SPX)
- **Structure:** Iron Condor (sell OTM put spread + sell OTM call spread)
- **DTE at Entry:** 3 trading days to expiration (changed from 0DTE in Feb 2026)
- **Goal:** Collect premium from time decay while SPY stays within a defined range
- **Max Risk:** Defined by spread width ($5 per contract)

### Exact Production Parameters (from `trading/fortress_v2/models.py`)

| Parameter | Value | Source Line | Notes |
|-----------|-------|-------------|-------|
| ticker | SPY | models.py:221 | Always SPY |
| min_dte | 3 | models.py:235 | 3 **trading** days, not calendar days |
| sd_multiplier | 1.2 | models.py:229 | Hard floor enforced at 1.2 in signals.py:434 |
| spread_width | $5.00 | models.py:230 | Was $2 (too narrow for premium) |
| risk_per_trade_pct | 15% | models.py:239 | Of total capital |
| max_contracts | 75 | models.py:240 | Liquidity cap |
| max_trades_per_day | 3 | models.py:241 | Allows re-entry after profitable close |
| min_win_probability | 42% | models.py:245 | ML must predict >= 42% |
| profit_target_pct | 50% | models.py:248 | Close when IC value drops to 50% of credit |
| use_stop_loss | False | models.py:249 | No stop loss in production |
| stop_loss_multiple | 2.0 | models.py:250 | Only active if use_stop_loss=True |
| capital | $100,000 | models.py:238 | Starting capital (overridden by Tradier balance) |
| entry_start | 08:30 CT | models.py:253 | Market open |
| entry_end | 14:45 CT | models.py:254 | Stop new entries 15 min before close |
| force_exit | 14:50 CT | models.py:255 | Force close 10 min before market close |

### ⚠️ CORRECTION: VIX Filter is Effectively Disabled

The `MODERATE` preset defines `vix_skip: 32.0`, but the actual `check_vix_filter()` method in `signals.py:361-373` **ignores presets** and only blocks at VIX > 50:

```python
def check_vix_filter(self, vix: float) -> Tuple[bool, str]:
    # VIX filter - only block in extreme conditions (VIX > 50)
    if vix > 50:
        return False, f"VIX ({vix:.1f}) extremely elevated - market crisis conditions"
    return True, f"VIX={vix:.1f} - trading allowed"
```

Additionally, Prophet's VIX skips are explicitly disabled in `trader.py:767-769`:
```python
prediction = self.prophet.get_fortress_advice(
    vix_hard_skip=0.0,          # Disabled
    vix_monday_friday_skip=0.0,  # Disabled
    vix_streak_skip=0.0,         # Disabled
)
```

**The backtest should test BOTH behaviors:**
1. Current live behavior: trade at any VIX (only skip VIX > 50)
2. Intended behavior: skip when VIX > preset threshold (25, 30, 32, 35)

### ⚠️ CORRECTION: Strike Selection is Pure SD Math Only

The live `calculate_strikes()` method in `signals.py:412-490` was **intentionally stripped down** in Feb 2026 after $9,500+ in losses from GEX-wall-based strikes. The code comment explains:

```python
"""
FIX (Feb 2026): Removed Prophet/GEX wall strike tiers.
Prophet was suggesting strikes at 0.6-0.9 SD (based on GEX walls + tiny buffer)
that bypassed validation, causing $9,500+ in losses (Jan 29 - Feb 6).
Prophet still decides WHETHER to trade - strikes are now pure math.
"""
```

**The ONLY strike selection method in production:**
```python
MIN_SD_FLOOR = 1.2  # Hard minimum, cannot go below
sd = max(config.sd_multiplier, MIN_SD_FLOOR)
effective_em = max(expected_move, spot_price * 0.005)  # Min 0.5% EM

put_short = math.floor(spot_price - sd * effective_em)   # Round DOWN (away from spot)
call_short = math.ceil(spot_price + sd * effective_em)    # Round UP (away from spot)
put_long = put_short - spread_width                        # $5 below
call_long = call_short + spread_width                      # $5 above
```

**However, the backtest SHOULD test alternative methods for comparison:**
1. **SD-based (current live):** 1.0, 1.1, 1.2, 1.3, 1.5 SD
2. **Fixed Delta:** ~16 delta (~1 SD), ~10 delta (~1.3 SD)
3. **GEX Wall Anchored:** Place at nearest gamma wall ±buffer (the OLD method that caused losses)
4. **Percentage OTM:** 0.5%, 1.0%, 1.5%, 2.0%
5. **ATR-Based:** N × 14-day ATR from spot

### Expected Move Formula — ⚠️ IMPORTANT BUG TO TEST

The live formula in `signals.py:350-359` calculates a **1-day** expected move regardless of DTE:

```python
def _calculate_expected_move(self, spot: float, vix: float) -> float:
    annual_factor = math.sqrt(252)  # Trading days per year
    daily_vol = (vix / 100) / annual_factor
    expected_move = spot * daily_vol
    return round(expected_move, 2)
```

For **3DTE**, the expected move should theoretically scale by `sqrt(DTE)`:
```python
expected_move_3dte = spot * (vix / 100) / sqrt(252) * sqrt(3)  # ~1.73x daily
```

**The backtest MUST compare:**
1. Current behavior: 1-day EM used for all DTE (what's live now)
2. Corrected behavior: EM scaled by sqrt(DTE)
3. This could explain why 1.2 SD with 3DTE feels "tight" — the EM is underestimated

### Strategy Presets (5 configurations from `models.py:54-85`)

| Preset | VIX Skip | SD Multiplier | Est Win Rate |
|--------|----------|---------------|-------------|
| BASELINE | None | 1.2 | 96.5% |
| CONSERVATIVE | VIX > 35 | 1.2 | 97.0% |
| **MODERATE** (default) | VIX > 32 | 1.2 | 98.5% |
| AGGRESSIVE | VIX > 30 | 1.2 | 99.0% |
| WIDE_STRIKES | VIX > 32 | 1.3 | 99.2% |

### Why the Change from 0DTE to 3DTE

From code comments and config history:
- **0DTE SPY ICs had virtually no premium** — credits were $0.02-$0.05
- **Commissions ($5.20/IC) ate 100%+ of profit** at $0.05 credit
- **$5-wide spreads + 3DTE** gives enough theta for $0.20-$0.50+ credit
- **1.2 SD** provides 20% more cushion than old 1.0 SD
- **$9,500+ in losses** Jan 29 - Feb 6 from GEX-wall strikes at 0.6-0.9 SD

### ML Advisory Hierarchy (from `signals.py:130-149`)

⚠️ CORRECTION: The prompt references WISDOM/DISCERNMENT/PROVERBS/STARS as ML systems. The actual FORTRESS code uses:

1. **FortressMLAdvisor** (PRIMARY) — XGBoost trained on CHRONICLES backtests, ~70% win rate
   - File: `quant/fortress_ml_advisor.py`
   - Features: vix, vix_percentile_30d, vix_change_1d, day_of_week_sin/cos, price_change_1d, expected_move_pct, volatility_risk_premium, win_rate_60d, gex_normalized, gex_regime_positive, gex_distance_to_flip_pct, gex_between_walls
   - Output: TRADE_FULL / TRADE_REDUCED / SKIP_TODAY + win_probability + suggested_risk_pct + suggested_sd_multiplier

2. **ProphetAdvisor** (BACKUP) — Only used when FortressMLAdvisor is unavailable
   - File: `quant/prophet_advisor.py`
   - Aggregates: GEX signals + ML predictions + VIX regime
   - Output: Same format as FortressMLAdvisor

3. **PROVERBS** — Not an ML system, it's a feedback loop / guardrail system
   - Consecutive loss tracker: 3 losses → 5-minute cooldown pause
   - Daily loss tracker

4. **CHRONICLES** — Not an ML system, it's the GEX calculator for backtesting
   - File: `quant/chronicles_gex_calculator.py`
   - Calculates GEX from ORAT historical data

### Exit Logic (from `trader.py:1315-1405`)

Exit conditions are checked **in priority order** every 5-minute cycle:

1. **FORCE_EXIT_TIME:** On expiration day, if current time >= force_exit time (14:50 CT)
   - Handles early close days (Christmas Eve, etc.) — exits 10 min before early close
2. **EXPIRED:** Position's expiration is BEFORE today (stale — should have been closed)
3. **PROFIT_TARGET:** Position value ≤ `total_credit × (1 - profit_target_pct/100)`
   - At 50% target: close when IC value drops to 50% of entry credit
4. **STOP_LOSS:** (disabled by default) Position value ≥ `total_credit × stop_loss_multiple`
5. **PRICING_FAILURE_NEAR_EXPIRY:** If pricing fails within 30 min of force exit, close anyway

### Position Sizing (from `executor.py`)

```python
risk_budget = capital * (risk_per_trade_pct / 100)  # 15% of $100K = $15,000
max_loss_per_ic = (spread_width - total_credit) * 100  # Per contract
contracts = min(int(risk_budget / max_loss_per_ic), max_contracts)  # Cap at 75
```

Also integrates Monte Carlo Kelly criterion when available (`quant/monte_carlo_kelly.py`).

-----

## DATA SOURCES

### PRIMARY: Your ORAT Database (Best Quality)

**Connection:** `ORAT_DATABASE_URL` env var, accessible via Render shell PSQL command.

#### Table: `orat_options_eod`

| Column | Type | Purpose |
|--------|------|---------|
| trade_date | DATE | Snapshot date |
| ticker | VARCHAR(10) | SPX, SPXW, SPY, VIX |
| expiration_date | DATE | Option expiration |
| strike | DECIMAL(10,2) | Strike price |
| call_bid / call_ask / call_mid | DECIMAL(10,4) | Call prices |
| put_bid / put_ask / put_mid | DECIMAL(10,4) | Put prices |
| delta | DECIMAL(10,6) | Greek delta |
| gamma | DECIMAL(10,6) | Greek gamma (for GEX) |
| theta | DECIMAL(10,4) | Greek theta |
| vega | DECIMAL(10,4) | Greek vega |
| rho | DECIMAL(10,6) | Greek rho |
| call_iv / put_iv | DECIMAL(10,6) | Implied volatility |
| underlying_price | DECIMAL(10,2) | Spot price |
| dte | INTEGER | Days to expiration |
| call_oi / put_oi | INTEGER | Open interest |
| call_volume / put_volume | INTEGER | Volume |

**Critical query for 3DTE backtest:**
```sql
SELECT strike, underlying_price, expiration_date, dte,
       put_bid, put_ask, call_bid, call_ask,
       delta, gamma, theta, vega, put_iv, call_iv,
       call_oi, put_oi, call_volume, put_volume
FROM orat_options_eod
WHERE ticker = 'SPY'
  AND trade_date = %s
  AND dte BETWEEN 1 AND 5
  AND (put_bid > 0 OR call_bid > 0)
ORDER BY expiration_date, strike
```

#### Pre-computed GEX Tables

**`gex_daily`** — Daily GEX metrics (formula: `GEX = gamma × OI × 100 × spot²`):
- net_gex, call_wall, put_wall, flip_point, gex_regime, gex_normalized, distance_to_flip_pct, between_walls

**`gex_structure_daily`** — Per-day gamma structure with magnets, flip points, ML features

**`gex_strikes`** — Per-strike gamma breakdown

#### Supporting Tables

**`underlying_prices`** — SPY/SPX daily OHLCV
**`vix_history`** — VIX daily OHLCV

#### Data Availability Check (RUN FIRST)

```sql
-- What ORAT data do you have?
SELECT ticker, MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date)
FROM orat_options_eod GROUP BY ticker;

-- How much 2-5 DTE SPY data exists?
SELECT dte, COUNT(DISTINCT trade_date) as days,
       MIN(trade_date), MAX(trade_date)
FROM orat_options_eod
WHERE ticker = 'SPY' AND dte BETWEEN 1 AND 5
GROUP BY dte ORDER BY dte;

-- Average bid-ask spread for 3DTE SPY options
SELECT AVG(call_ask - call_bid) as avg_call_spread,
       AVG(put_ask - put_bid) as avg_put_spread,
       AVG(CASE WHEN call_bid > 0 THEN (call_ask - call_bid) / call_bid ELSE NULL END) as avg_call_spread_pct
FROM orat_options_eod
WHERE ticker = 'SPY' AND dte BETWEEN 2 AND 4
  AND call_bid > 0 AND put_bid > 0;

-- GEX coverage
SELECT symbol, MIN(trade_date), MAX(trade_date), COUNT(*)
FROM gex_daily GROUP BY symbol;

-- VIX coverage
SELECT MIN(trade_date), MAX(trade_date), COUNT(*) FROM vix_history;
```

### SECONDARY: Free GitHub Data (Supplement ORAT)

1. **philippdubach/options-data** — SPY 2008-2025, Greeks, IV, OI
   ```python
   import polars as pl
   df = pl.read_parquet("https://static.philippdubach.com/data/options/spy/options.parquet")
   ```

2. **philippdubach/options-dataset-hist** — SPY/IWM/QQQ, 53M+ contracts, Parquet + SQLite
   ```python
   import pandas as pd
   df = pd.read_parquet('data/parquet_spy/options_2024.parquet')
   ```

3. **DoltHub dolthub/options** — 2019-2024, SQL-queryable
4. **sirnfs/OptionSuite** — Bundled SPX data 1990-2017

### UNDERLYING & VIX: Yahoo Finance

```python
import yfinance as yf
spy = yf.Ticker("SPY").history(start="2008-01-01", end="2026-02-01", interval="1d")
vix = yf.Ticker("^VIX").history(start="2008-01-01", end="2026-02-01")
```

### SUPPLEMENTARY DATA

- **Economic Calendar:** FOMC, CPI, NFP dates from FRED
- **SPY Ex-Dividend Dates:** Via yfinance
- **Market Holidays:** Use `exchange_calendars` or `pandas_market_calendars` Python packages

-----

## BACKTESTING METHODOLOGY

### Phase 1: Data Preparation

1. **Download/connect to data sources** (ORAT first, GitHub data as supplement)
2. **Build master dataset** joining:
   - Options chain (date + strike + expiration + type)
   - Underlying OHLCV
   - VIX level
   - GEX metrics (from `gex_daily` table or calculated)
   - Day of week, trading day encoding
3. **Filter to target DTE** — For each trading day, identify expirations that are N trading days out (use `exchange_calendars` to count trading days, matching FORTRESS's `MarketCalendar`)
4. **Validate data quality:**
   - Missing dates
   - Bid-ask spread > 50% of mid → flag as illiquid
   - Stale quotes (bid=0 or ask=0)
   - Option chain completeness (enough strikes around ATM for IC construction)
   - Document every NULL handling decision

### Phase 2: Feature Engineering

Build the same features FORTRESS uses in production (from `fortress_ml_advisor.py:192-207`):

```python
FEATURE_COLS = [
    'vix',                          # Current VIX level
    'vix_percentile_30d',           # Where VIX sits in 30-day range
    'vix_change_1d',                # 1-day VIX change %
    'day_of_week_sin',              # sin(2π × dow/5)
    'day_of_week_cos',              # cos(2π × dow/5)
    'price_change_1d',              # Yesterday's SPY return %
    'expected_move_pct',            # EM as % of spot
    'volatility_risk_premium',      # IV - realized_vol_5d
    'win_rate_60d',                 # 60-trade rolling win rate
    'gex_normalized',               # net_gex / spot²
    'gex_regime_positive',          # 1 if POSITIVE, 0 otherwise
    'gex_distance_to_flip_pct',     # |spot - flip_point| / spot × 100
    'gex_between_walls',            # 1 if put_wall ≤ spot ≤ call_wall
]
```

Additional features to engineer:
- **VIX Regime:** < 15 = low, 15-22 = normal, 22-28 = elevated, 28-35 = high, > 35 = extreme
- **ATR (14-day):** Average True Range for ATR-based strike selection
- **Trend Strength / Direction:** ADX or rolling regression slope
- **IV Rank / Percentile:** Current IV vs 52-week range
- **GEX Proxy (if no GEX data):** Approximate from OI imbalance at key strikes

### Phase 3: Trade Construction Engine

For each trading day in backtest period:

1. **Check filters:** Should FORTRESS trade today?
2. **Find target expiration:** Count N trading days forward (matching FORTRESS logic)
3. **Get option chain** for that expiration
4. **Select strikes** using the method being tested
5. **Calculate entry credit:**
   - **Natural (conservative):** sell at bid, buy at ask
   - **Mid-price:** (bid + ask) / 2 for each leg
   - **Mid minus slippage:** mid - slippage_per_leg
6. **Validate minimum credit:** total_credit ≥ $0.05 (`config.min_credit`)
7. **Position size:** `min(floor(risk_budget / max_loss_per_contract), max_contracts)`
8. **Record trade:** all 4 strikes, entry credit, max profit, max loss, breakevens

### Phase 4: Trade Lifecycle — Multi-Day Simulation

**This is the critical difference from 0DTE backtesting.**

For each open position, on each subsequent trading day until expiration:

1. **Get the same expiration's option chain** from ORAT on the current date
2. **Reprice the IC:**
   - Look up bid/ask for all 4 legs at today's date with the same expiration
   - Current IC value = (short put ask - long put bid) + (short call ask - long call bid)
   - Or use BSM if ORAT data is missing for that date
3. **Check exit conditions (matching live priority order):**
   a. **FORCE_EXIT:** Is it expiration day AND time ≥ 14:50 CT? → Close at market
   b. **EXPIRED:** Is expiration date < today? → Emergency close
   c. **PROFIT_TARGET:** Is IC value ≤ entry_credit × (1 - profit_target_pct/100)?
      - At 50%: close when IC costs 50% or less of original credit to buy back
   d. **STOP_LOSS:** (if enabled) Is IC value ≥ entry_credit × stop_loss_multiple?
4. **If no exit triggered:** Mark to market, continue to next day
5. **At expiration (no early exit):**
   - Settlement price = SPY close on expiration day
   - Put spread P&L: if SPY ≥ put_short → keep full put credit; if SPY < put_long → max loss
   - Call spread P&L: if SPY ≤ call_short → keep full call credit; if SPY > call_long → max loss
   - Partial breach: intrinsic value calculation

**Intraday exit estimation (when using EOD-only data):**
- Use daily high/low to determine if profit target COULD have been hit intraday
- Conservative: assume profit target hit at worst possible time (end of day)
- Aggressive: assume hit at best possible time (use high/low range)
- Best: use BSM with intraday underlying price estimates

### Phase 5: Slippage & Transaction Cost Modeling

**Model EXACTLY what FORTRESS pays in production.**

1. **Commission:** $0.65/contract/leg × 4 legs = $2.60/contract to open
   - If closed before expiry: another $2.60 to close = $5.20 total
   - If expires worthless: only $2.60 (no close needed)

2. **Slippage on 3DTE SPY options:**
   - SPY 3DTE options typically: $0.01-$0.05 bid-ask spread near ATM, wider on wings
   - 4-leg IC roundtrip slippage: test at $0.04, $0.08, $0.12 per IC
   - 3DTE has slightly wider spreads than 0DTE (less volume on non-0DTE)

3. **Fill assumptions:**
   - Conservative: natural prices (sell at bid, buy at ask)
   - Realistic: mid minus $0.01-0.02 per leg
   - Never assume fills better than mid

4. **Liquidity filter:**
   - Reject strikes with volume < 50 or OI < 100
   - Flag when bid-ask spread > $0.10 on short strikes

### Phase 6: Performance Analysis

**Return Metrics:**
- Total P&L (dollar and %)
- Average / Median trade P&L
- Win rate (%), profit factor
- Expected value per trade
- Annualized return
- Average credit received per IC

**Risk Metrics:**
- Maximum drawdown (dollar and %)
- Maximum consecutive losses
- Largest single loss
- Sharpe ratio (annualized), Sortino ratio, Calmar ratio
- VaR (95%, 99%), CVaR (expected shortfall)
- Average max adverse excursion per trade

**Distribution:**
- P&L distribution histogram
- Skewness, kurtosis
- Tail risk: what % of trades lose > 50% of max loss?
- QQ plot vs normal

**Time Analysis:**
- By day of week, by month, by VIX regime, by GEX regime
- Rolling 30/60/90 trade win rate
- Equity curve with drawdown overlay
- Monthly returns heatmap

**Regime Analysis:**
- VIX < 15 vs 15-22 vs 22-28 vs 28-35 vs 35+
- GEX POSITIVE vs NEGATIVE vs NEUTRAL
- Around FOMC/CPI/earnings
- Trending vs ranging markets
- Correlation of P&L with VIX changes and SPY daily returns

### Phase 7: Parameter Optimization

**DO NOT OVERFIT.**

1. **DTE Sweep (the key question):**
   - Test DTE = 0, 1, 2, 3, 4, 5 with all other params fixed at production values
   - For each DTE, also test the EM scaling question:
     a. EM = 1-day EM (current bug?)
     b. EM = 1-day EM × sqrt(DTE) (theoretically correct)

2. **SD Sweep:** 1.0, 1.1, 1.2, 1.3, 1.5 SD

3. **Spread Width Sweep:** $2, $3, $5, $7, $10

4. **Risk Per Trade Sweep:** 5%, 10%, 15%, 20%

5. **Profit Target Sweep:** 25%, 50%, 75%, hold to expiry

6. **Stop Loss Sweep:** None (current), 1x credit, 1.5x, 2x, 2x width

7. **VIX Filter Sweep:** None (current live), >25, >30, >32, >35

8. **GEX Filter Tests:**
   - No filter (baseline)
   - Only POSITIVE regime
   - Only between walls
   - Distance to flip > 1%
   - Combined

9. **Walk-Forward Analysis:**
   - Train on 12 months, test on next 3 months, roll forward
   - Parameters that work in walk-forward are robust

10. **Monte Carlo:**
    - Shuffle trade order 10,000 times
    - Report: "95% of the time, max drawdown ≤ $X"

11. **Stress Tests:**
    - COVID crash 2020 (VIX > 80)
    - 2022 bear market
    - 2017/2024 low-vol grind
    - Quad witching weeks
    - SPY ex-dividend dates

12. **Out-of-Sample:**
    - Reserve last 6-12 months
    - NEVER touch during optimization

-----

## FILTERS — WHEN NOT TO TRADE

Test each independently, then in combination:

- **VIX Filter:** Skip if VIX > [25, 30, 32, 35, 50] (50 = current live behavior)
- **VIX Spike:** Skip if VIX up > [10%, 15%, 20%] since previous close
- **FOMC/CPI/NFP Days:** Skip on major economic releases
- **Low Premium Filter:** Skip if total credit < [$0.05, $0.10, $0.15, $0.20]
- **GEX Negative Gamma:** Skip when dealers short gamma (amplified moves)
- **Day of Week:** Skip specific days
- **Trend Filter:** Skip if ADX > threshold (strong directional move)
- **IV Rank Filter:** Skip if IV rank < [15, 20, 25] (not enough premium)
- **Earnings Season:** Skip during peak earnings weeks
- **SPY Ex-Dividend:** Skip around ex-div dates
- **Consecutive Loss Cooldown:** Skip for N minutes/hours after 3 consecutive losses (matching PROVERBS behavior: 5-min pause in production)

-----

## CRITICAL REALISM CHECKS

### Things That Kill Iron Condor Backtests

1. **Using mid-price fills** — Real fills are ALWAYS worse. Apply slippage.
2. **Ignoring that 3DTE positions live multiple days** — Must reprice daily, not just at entry and expiration
3. **Wrong expected move scaling** — 1-day EM for 3DTE trades underestimates risk. Test both.
4. **Look-ahead bias** — Never use EOD VIX to make morning entry decisions
5. **Liquidity on wing strikes** — Far OTM 3DTE puts may have $0 bids
6. **Capital allocation with overlapping positions** — 3DTE means up to 3 ICs open simultaneously
7. **Dividend risk on short calls** — SPY pays quarterly; short calls near ex-div have assignment risk
8. **Pin risk at expiration** — SPY between short and long strike = uncertain exposure
9. **After-hours settlement** — SPY options settle at 4:00 PM ET close, not 3:59
10. **Gamma acceleration** — At expiration, $1 SPY move can swing option from worthless to deep ITM

### Realistic Capital Model

- **Starting Capital:** $100,000 (matching production config)
- **Max Allocation Per Trade:** 15% ($15,000 max risk)
- **Concurrent Positions:** Up to 3 (3DTE means positions overlap)
- **Margin Buffer:** Model Reg-T margin requirements
- **Position Sizing:** Fixed risk per trade (% of equity)
- **Compounding:** Test fixed size AND equity-curve position sizing

-----

## EXPECTED MOVE BUG ANALYSIS — CRITICAL TEST

This may be the most important finding. The backtest MUST run a head-to-head comparison:

**Variant A (Current Live — Potentially Bugged):**
```python
EM = spot × (VIX/100) / sqrt(252)  # Always 1-day EM
strikes = spot ± 1.2 × EM           # Same EM regardless of DTE
```

**Variant B (Theoretically Correct):**
```python
EM_daily = spot × (VIX/100) / sqrt(252)
EM_for_dte = EM_daily × sqrt(DTE)   # Scale by sqrt of holding period
strikes = spot ± 1.2 × EM_for_dte
```

At VIX=20, SPY=$600:
- Variant A: EM = $7.56, put_short = $590.93 → $590
- Variant B (3DTE): EM = $13.09, put_short = $584.29 → $584

**Variant B places strikes $6 further from spot.** This means:
- Much higher win rate (strikes further OTM)
- Much lower credit received (further OTM = less premium)
- The trade-off needs quantification

-----

## OUTPUT REQUIREMENTS

### Deliverables

1. **Summary Dashboard:** Win rate, profit factor, Sharpe, max DD, equity curve, monthly heatmap
2. **DTE Comparison Report:** Side-by-side 0DTE vs 1DTE vs 2DTE vs 3DTE vs 4DTE vs 5DTE
3. **EM Scaling Report:** Variant A vs Variant B head-to-head
4. **Parameter Sensitivity Heatmaps:** Sharpe across SD × width, profit target × stop loss
5. **Trade Log CSV:** Every trade with entry/exit/strikes/credit/P&L/reason
6. **Regime Analysis:** Performance by VIX/GEX/trend/day-of-week
7. **Risk Report:** Monte Carlo drawdown distribution, worst-case scenarios
8. **Walk-Forward Report:** In-sample vs out-of-sample degradation
9. **Filter Analysis:** Which filters improve Sharpe without destroying opportunity
10. **Benchmark Comparison:** FORTRESS vs buy-and-hold SPY, vs naked puts, vs 0DTE IC

-----

## IMPLEMENTATION APPROACH

### Tech Stack

- **Python 3.10+**
- **Data:** Polars (fast) or pandas
- **Options Pricing:** py_vollib or scipy for BSM (intraday exit estimation)
- **Visualization:** Plotly (interactive), matplotlib (static), seaborn (heatmaps)
- **Statistics:** scipy.stats, numpy
- **Calendar:** exchange_calendars or pandas_market_calendars
- **Storage:** Parquet locally, PostgreSQL for results

### Project Structure

```
fortress_backtest/
├── data/
│   ├── raw/                  # Downloaded parquet, ORAT exports
│   ├── processed/            # Cleaned master dataset
│   └── economic_calendar/    # FOMC, CPI, NFP dates
├── src/
│   ├── data_loader.py        # Download and prepare data
│   ├── feature_engine.py     # VIX regime, trend, IV rank, GEX features
│   ├── trade_builder.py      # Construct IC from chain (match signals.py logic)
│   ├── simulator.py          # Multi-day lifecycle, exit checks (match trader.py)
│   ├── slippage.py           # Cost models
│   ├── metrics.py            # Performance and risk calculations
│   ├── filters.py            # Trade/no-trade filters
│   └── config.py             # All parameters (match FortressConfig exactly)
├── analysis/
│   ├── parameter_sweep.py    # Grid search
│   ├── walk_forward.py       # Walk-forward optimization
│   ├── monte_carlo.py        # MC drawdown simulation
│   ├── regime_analysis.py    # Performance by regime
│   └── em_scaling_test.py    # Variant A vs B comparison
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_baseline_backtest.ipynb
│   ├── 03_dte_comparison.ipynb
│   ├── 04_em_scaling_analysis.ipynb
│   ├── 05_optimization.ipynb
│   └── 06_final_results.ipynb
├── output/
│   ├── trade_logs/
│   ├── reports/
│   └── charts/
├── tests/
│   └── test_trade_builder.py
├── config.yaml
└── README.md
```

### Config File (config.yaml) — Matches Production

```yaml
fortress:
  symbol: SPY
  strategy: iron_condor

  # ⚠️ CORRECTED: Live is 3, test 0-5
  dte_target: 3

  # Strike selection (live uses SD only)
  strike_method: sd  # sd | delta | otm_pct | gex_wall | atr
  sd_multiplier: 1.2
  sd_floor: 1.2  # Hard minimum, cannot go below
  wing_width: 5  # ⚠️ CORRECTED: Live is $5, not $2

  # Expected move
  em_scaling: false  # false = current live (1-day EM), true = scale by sqrt(DTE)

  # Entry
  entry_start: "08:30"  # CT
  entry_end: "14:45"    # CT

  # Exit
  profit_target_pct: 0.50
  use_stop_loss: false
  stop_loss_multiple: 2.0
  force_exit_time: "14:50"  # CT on expiration day

  # Filters
  # ⚠️ CORRECTED: Live only blocks VIX > 50
  max_vix: 50  # Current live behavior
  min_credit: 0.05
  min_win_probability: 0.42

  # Execution
  slippage_per_contract: 0.05
  commission_per_leg: 0.65  # × 4 legs = $2.60/contract
  fill_method: natural  # natural | mid | mid_minus_slippage

  # Capital
  starting_capital: 100000
  max_risk_per_trade_pct: 0.15  # 15%
  max_contracts: 75
  max_trades_per_day: 3
  position_sizing: fixed_risk  # fixed_risk | fixed_contracts | kelly

  # Backtest period
  start_date: "2018-01-01"
  end_date: "2025-12-31"
  oos_start: "2025-01-01"
```

-----

## EXISTING CODEBASE TO CROSS-REFERENCE

When building the backtest, reference these actual production files:

| File | What to Extract |
|------|----------------|
| `trading/fortress_v2/models.py` | FortressConfig defaults, all presets, IronCondorPosition fields |
| `trading/fortress_v2/signals.py` | calculate_strikes() exact logic, _get_target_expiration(), check_vix_filter(), get_ml_prediction() |
| `trading/fortress_v2/trader.py` | _check_exit_conditions() priority order, _manage_positions(), run_cycle() flow |
| `trading/fortress_v2/executor.py` | close_position(), get_position_current_value(), Kelly sizing |
| `quant/fortress_ml_advisor.py` | FEATURE_COLS, train_from_chronicles(), predict() |
| `quant/chronicles_gex_calculator.py` | GEX formula, get_gex_for_date() |
| `quant/prophet_advisor.py` | get_fortress_advice() |
| `backtest/zero_dte_realistic.py` | Starting point (fork and modify for multi-day) |
| `scripts/create_backtest_schema.py` | orat_options_eod schema |

**Cross-reference backtest results against the FORTRESS tables in production DB:**
- `fortress_positions` — Live trade history
- `fortress_closed_trades` — Actual outcomes
- `fortress_scan_activity` — Every scan decision with market context

-----

## SUCCESS CRITERIA

The backtest is trustworthy ONLY if ALL pass:

1. ✅ Uses real bid/ask data with explicit slippage (never mid-price fills)
2. ✅ Multi-day positions repriced daily (not just entry + expiration)
3. ✅ Transaction costs fully modeled ($0.65/leg, 4 legs, open + close)
4. ✅ Walk-forward shows parameter stability across periods
5. ✅ Out-of-sample within 30% of in-sample performance
6. ✅ Monte Carlo worst-case drawdown survivable with $100K capital
7. ✅ Still profitable after 2× expected slippage (stress test)
8. ✅ Positive expected value: win_rate × avg_win > loss_rate × avg_loss
9. ✅ Sharpe ratio > 1.0 after all costs
10. ✅ Max drawdown < 25% of account
11. ✅ Works across at least 3 VIX regimes

**If ANY criterion fails, the strategy should NOT go live at those parameters. Report what failed and recommend adjustments.**

-----

## FIRST STEPS

1. **Run data availability queries** (Section: Data Availability Check)
2. **If ORAT has SPY 3DTE data:** Use it as primary source
3. **If not:** Download philippdubach data, filter for DTE=3
4. **Build one baseline trade:** Pick one day, construct IC with production params, trace to expiration
5. **Validate that trade** against what the market actually did
6. **Run the EM scaling comparison** (Variant A vs B) — this may change everything
7. **Run DTE sweep** (0-5) — the core question
8. **Full parameter optimization** with walk-forward
9. **Final out-of-sample validation**
