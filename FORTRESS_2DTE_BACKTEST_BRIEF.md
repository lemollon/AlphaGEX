# FORTRESS 2DTE Iron Condor Backtest - Comprehensive Brief

## What This Document Is

This is a complete context brief for building a **production-grade backtester** for the FORTRESS trading bot, which recently switched from **0DTE to 2-3DTE SPY Iron Condors**. The backtest must validate this change with historical data before the bot continues live trading.

---

## 1. FORTRESS Bot - Current Live Configuration

FORTRESS is a **SPY Iron Condor** bot. Here are the exact production parameters from `trading/fortress_v2/models.py`:

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Ticker** | SPY | Always SPY, never SPX |
| **Strategy** | Iron Condor (Bull Put + Bear Call) | 4-leg credit spread |
| **min_dte** | 3 | Changed from 0DTE in Feb 2026. Minimum 3 **trading days** to expiration |
| **sd_multiplier** | 1.2 | Strikes placed 1.2 standard deviations outside expected move |
| **spread_width** | $5.00 | Distance between short and long strikes |
| **risk_per_trade_pct** | 15% | Risk 15% of capital per trade |
| **max_contracts** | 75 | Liquidity cap |
| **max_trades_per_day** | 3 | Allow re-entries |
| **min_win_probability** | 42% | Prophet/ML must predict >= 42% |
| **profit_target_pct** | 50% | Close at 50% of max profit |
| **use_stop_loss** | False | No stop loss (force exit only) |
| **vix_skip** | 32.0 (MODERATE preset) | Skip when VIX > 32 (but code only blocks VIX > 50) |
| **entry_start** | 08:30 CT | Market open |
| **entry_end** | 14:45 CT | Stop new entries 15 min before close |
| **force_exit** | 14:50 CT | Force close all 10 min before close |
| **capital** | $100,000 | Starting capital |

### Strategy Presets (5 risk profiles to backtest)

| Preset | VIX Skip | SD Multiplier | Estimated Win Rate |
|--------|----------|---------------|-------------------|
| BASELINE | None | 1.2 | 96.5% |
| CONSERVATIVE | VIX > 35 | 1.2 | 97.0% |
| **MODERATE** (default) | VIX > 32 | 1.2 | 98.5% |
| AGGRESSIVE | VIX > 30 | 1.2 | 99.0% |
| WIDE_STRIKES | VIX > 32 | 1.3 | 99.2% |

### Why the Change from 0DTE to 2-3DTE

- **0DTE SPY ICs had no premium** - credits were $0.02-0.05, making commissions dominate
- **$5-wide spreads + 3DTE** gives enough theta to collect meaningful credit ($0.20-0.50+)
- **1.2 SD** provides 20% more cushion than the old 1.0 SD (which was breached ~32% of the time)
- **$9,500+ in losses** occurred Jan 29 - Feb 6 2026 from GEX-wall-based strikes at 0.6-0.9 SD

### Strike Selection (Pure Math - No ML Override)

```python
# From signals.py calculate_strikes()
MIN_SD_FLOOR = 1.2
sd = max(config.sd_multiplier, MIN_SD_FLOOR)

expected_move = spot * (vix / 100) / sqrt(252)

put_short = floor(spot - sd * expected_move)    # Round down (away from spot)
call_short = ceil(spot + sd * expected_move)     # Round up (away from spot)
put_long = put_short - spread_width              # $5 below short put
call_long = call_short + spread_width            # $5 above short call
```

### Expiration Selection (Trading Days, Not Calendar Days)

```python
# From signals.py _get_target_expiration()
# min_dte = 3 means 3 TRADING days out (skips weekends, holidays)
# Monday -> Thursday, Tuesday -> Friday, Wednesday -> next Monday, etc.
```

---

## 2. Available Data Sources for Backtesting

### 2A. ORAT Database (PRIMARY - Your Own Data)

**Connection**: `ORAT_DATABASE_URL` environment variable, accessible via Render shell with PSQL command.

#### Table: `orat_options_eod` (Main Options Data)

| Column | Type | Purpose |
|--------|------|---------|
| trade_date | DATE | Snapshot date |
| ticker | VARCHAR(10) | SPX, SPXW, SPY, VIX |
| expiration_date | DATE | Option expiration |
| strike | DECIMAL(10,2) | Strike price |
| call_bid / call_ask / call_mid | DECIMAL(10,4) | Call prices |
| put_bid / put_ask / put_mid | DECIMAL(10,4) | Put prices |
| delta | DECIMAL(10,6) | Greek delta |
| gamma | DECIMAL(10,6) | Greek gamma (CRITICAL for GEX) |
| theta | DECIMAL(10,4) | Greek theta |
| vega | DECIMAL(10,4) | Greek vega |
| rho | DECIMAL(10,6) | Greek rho |
| call_iv / put_iv | DECIMAL(10,6) | Implied volatility |
| underlying_price | DECIMAL(10,2) | Spot price |
| dte | INTEGER | Days to expiration |
| call_oi / put_oi | INTEGER | Open interest (for GEX) |
| call_volume / put_volume | INTEGER | Volume |

**Key Indexes**: trade_date, ticker, dte, strike, (trade_date, ticker), 0DTE partial index

**Critical Query for 2DTE Backtest**:
```sql
SELECT strike, underlying_price, put_bid, put_ask, call_bid, call_ask,
       delta, gamma, put_iv, call_iv, call_oi, put_oi, expiration_date, dte
FROM orat_options_eod
WHERE ticker = 'SPY'
  AND trade_date = %s
  AND dte BETWEEN 1 AND 4  -- Target 2-3DTE, allow some range
  AND gamma IS NOT NULL
  AND gamma > 0
  AND (call_oi > 0 OR put_oi > 0)
ORDER BY expiration_date, strike
```

#### Table: `underlying_prices` (OHLC)

| Column | Type |
|--------|------|
| trade_date | DATE |
| symbol | VARCHAR(10) |
| open / high / low / close | DECIMAL(10,2) |
| volume | BIGINT |

#### Table: `vix_history`

| Column | Type |
|--------|------|
| trade_date | DATE (UNIQUE) |
| open / high / low / close | DECIMAL(8,2) |

### 2B. Pre-Computed GEX Tables (from ORAT)

#### Table: `gex_daily`

Pre-calculated daily GEX metrics. Formula: `GEX = gamma * OI * 100 * spot^2`

| Column | Type | Purpose |
|--------|------|---------|
| trade_date | DATE | |
| symbol | VARCHAR(10) | |
| spot_price | NUMERIC(12,4) | |
| net_gex | NUMERIC(20,2) | Call GEX - Put GEX |
| call_wall | NUMERIC(12,4) | Resistance level |
| put_wall | NUMERIC(12,4) | Support level |
| flip_point | NUMERIC(12,4) | Where GEX crosses zero |
| gex_regime | VARCHAR(20) | POSITIVE, NEGATIVE, NEUTRAL |
| gex_normalized | NUMERIC(20,10) | GEX / spot^2 (scale-independent) |
| distance_to_flip_pct | NUMERIC(10,4) | |
| between_walls | BOOLEAN | |

#### Table: `gex_structure_daily` (For ML Features)

Per-day gamma structure with magnets, flip points, and price action labels. Has columns for `spot_open`, `spot_close`, `magnet_1/2/3_strike`, `gamma_imbalance_pct`, `open_in_pin_zone`, `price_change_pct`, etc.

#### Table: `gex_strikes` (Per-Strike Gamma)

Per-strike breakdown with `call_gamma`, `put_gamma`, `net_gamma`, `distance_from_spot_pct`.

### 2C. Data Availability Check

Run this to see what you have:
```sql
-- Check ORAT date range and ticker coverage
SELECT ticker, MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date)
FROM orat_options_eod
GROUP BY ticker;

-- Check 2DTE data availability for SPY
SELECT COUNT(DISTINCT trade_date) as days,
       MIN(trade_date) as first_date,
       MAX(trade_date) as last_date,
       AVG(underlying_price) as avg_price
FROM orat_options_eod
WHERE ticker = 'SPY' AND dte BETWEEN 1 AND 4;

-- Check GEX daily coverage
SELECT symbol, MIN(trade_date), MAX(trade_date), COUNT(*)
FROM gex_daily
GROUP BY symbol;

-- Check VIX coverage
SELECT MIN(trade_date), MAX(trade_date), COUNT(*) FROM vix_history;
```

### 2D. Free External Data Sources (Supplement ORAT)

#### Best Free GitHub Datasets

1. **philippdubach/options-dataset-hist** - SPY options 2008-2025, 53M+ contracts with Greeks
   - Parquet files: `pd.read_parquet('data/parquet_spy/options_2024.parquet')`
   - Has: strike, expiration, bid, ask, IV, delta, gamma, theta, vega, OI
   - Filter: `(expiration - quote_date).days == 2` for 2DTE

2. **philippdubach/options-data** - 100+ US equities, Parquet on Cloudflare R2
   - Download: `curl -O "https://static.philippdubach.com/data/options/spy/options.parquet"`

3. **DoltHub dolthub/options** - 2,098 symbols, 2019-2024, SQL-queryable
   - Install Dolt, `dolt clone dolthub/options`, query with SQL

4. **sirnfs/OptionSuite** - Bundled SPX data 1990-2017 (iVolatility source)

#### Free Backtesting Frameworks

1. **michaelchu/optopsy** - Python, 28 strategies including Iron Condors
   - `pip install optopsy`
   - `op.iron_condor(data, slippage="liquidity")`

2. **QuantConnect/Lean** - SPX minute-resolution options from 2012, free on platform

3. **lambdaclass/options_backtester** - Simple CSV-based Python backtester

---

## 3. Existing Backtest Infrastructure

### Existing Backtester: `backtest/zero_dte_realistic.py`

This is the closest existing backtester. It:
- Queries ORAT `orat_options_eod` for 0DTE options (`dte <= 1`)
- Uses Yahoo Finance for SPX OHLC and VIX
- Applies realistic costs: $0.65/leg commission, $0.10 slippage, 100 contract cap
- Settles at EOD close price
- Exports to CSV

**Key Limitation**: Only does `dte <= 1` (0DTE). Needs modification for 2-3DTE.

### GEX Calculator: `quant/chronicles_gex_calculator.py`

Calculates GEX from ORAT data for any date:
```python
GEX_strike = gamma * OI * 100 * spot^2
Net_GEX = sum(Call_GEX) - sum(Put_GEX)
```

Returns: `net_gex`, `call_wall`, `put_wall`, `flip_point`, `gex_regime`, `gex_normalized`, `distance_to_flip_pct`, `between_walls`

### ML Advisor: `quant/fortress_ml_advisor.py`

XGBoost classifier trained on backtest results. Features (V3):
- `vix`, `vix_percentile_30d`, `vix_change_1d`
- `day_of_week_sin`, `day_of_week_cos` (cyclical encoding)
- `price_change_1d`, `expected_move_pct`
- `volatility_risk_premium` (IV - realized_vol_5d)
- `win_rate_60d` (rolling)
- `gex_normalized`, `gex_regime_positive`, `gex_distance_to_flip_pct`, `gex_between_walls`

### Backtest Results Storage

Results go to:
- `zero_dte_backtest_results` - Summary (win rate, Sharpe, drawdown, config JSON)
- `zero_dte_backtest_trades` - Individual trades (entry/exit/strikes/P&L/outcome)
- `zero_dte_equity_curve` - Daily equity snapshots

### All Backtest Files (20 files in `backtest/`)

| File | Strategy |
|------|----------|
| `zero_dte_iron_condor.py` | 0DTE IC (basic) |
| `zero_dte_realistic.py` | 0DTE IC with costs |
| `zero_dte_aggressive.py` | 0DTE IC aggressive |
| `zero_dte_hybrid_fixed.py` | Hybrid DTE IC |
| `zero_dte_hybrid_scaling.py` | Auto-scaling IC |
| `zero_dte_vrp_strategy.py` | Volatility risk premium |
| `zero_dte_bull_put_spread.py` | Bull put only |
| `backtest_gex_strategies.py` | GEX-based signals |
| `backtest_options_strategies.py` | 11 strategy configs |
| `backtest_framework.py` | Base classes |
| `wheel_backtest.py` | Wheel strategy |
| `real_wheel_backtest.py` | Wheel with Polygon |
| `spx_premium_backtest.py` | SPX puts |
| `premium_portfolio_backtest.py` | Portfolio mix |
| `psychology_backtest.py` | Trap patterns |
| `autonomous_backtest_engine.py` | Pattern validation |
| `enhanced_backtest_optimizer.py` | Optimization tables |
| `backfill_market_data.py` | Yahoo data import |
| `strategy_report.py` | Report generation |

---

## 4. What the Backtest Must Do

### Core Requirements

1. **Simulate FORTRESS 2-3DTE SPY Iron Condors** using exact production parameters
2. **Use ORAT historical data** as primary data source (real bid/ask, Greeks, OI)
3. **Test all 5 presets** (BASELINE, CONSERVATIVE, MODERATE, AGGRESSIVE, WIDE_STRIKES)
4. **Include GEX analysis** - test GEX-filtered vs unfiltered performance
5. **Realistic costs** - commissions, slippage, liquidity caps
6. **Multi-year analysis** - use all available ORAT SPY data
7. **Compare 0DTE vs 2DTE vs 3DTE** - quantify the improvement (or not)

### Settlement Logic for 2-3DTE (Different from 0DTE!)

**This is the critical difference from existing backtests:**

For 0DTE: Position settles at EOD close. Simple.

For 2-3DTE: Position lives across multiple days. Must handle:
- **Intraday exit** at 50% profit target (need intraday price data or estimate)
- **Force exit** at 14:50 CT on expiration day
- **Settlement at expiration** if held to expiry
- **Mark-to-market** across multiple days
- **Price at exit** using option pricing (not just underlying settlement)

**Option Price Estimation for Exit** (when ORAT only has EOD snapshots):
- Use Black-Scholes with current underlying price, time to expiry, and IV
- OR use ORAT data from the exit date's snapshot for the same expiration
- For intraday exits, interpolate between open and close

### Parameter Sweep

Test these combinations (minimum):

| Parameter | Values to Test |
|-----------|---------------|
| DTE | 0, 1, 2, 3, 4, 5 |
| SD Multiplier | 1.0, 1.1, 1.2, 1.3, 1.5 |
| Spread Width | $2, $3, $5, $7, $10 |
| Risk Per Trade | 5%, 10%, 15%, 20% |
| Profit Target | 25%, 50%, 75%, hold to expiry |
| VIX Filter | None, >25, >30, >32, >35 |

### Metrics to Calculate

| Metric | Formula |
|--------|---------|
| Win Rate | wins / total_trades |
| Profit Factor | total_wins / abs(total_losses) |
| Sharpe Ratio | mean(daily_returns) / std(daily_returns) * sqrt(252) |
| Sortino Ratio | mean(daily_returns) / downside_deviation * sqrt(252) |
| Max Drawdown | max peak-to-trough loss % |
| Avg Monthly Return | geometric mean of monthly returns |
| Expectancy | (win_rate * avg_win) - (loss_rate * avg_loss) |
| Kelly Criterion | (win_rate * avg_win/avg_loss - (1-win_rate)) / (avg_win/avg_loss) |
| Cost Drag | total_costs / gross_profit |
| Calmar Ratio | annualized_return / max_drawdown |

### GEX Integration Tests

1. **Baseline**: No GEX filter (trade every day)
2. **GEX Regime Filter**: Only trade when GEX is POSITIVE (mean-reversion = safer for ICs)
3. **Wall Proximity Filter**: Only trade when price is between walls
4. **Flip Point Filter**: Only trade when distance to flip > X%
5. **Combined**: Regime + Wall + Flip filters together

---

## 5. Implementation Plan

### Phase 1: Data Audit
1. Connect to ORAT database via Render shell
2. Run availability queries (Section 2C)
3. Verify SPY 2-3DTE data exists with bid/ask and Greeks
4. Check date range coverage
5. Identify any data gaps

### Phase 2: Build Core Backtester
1. Fork `backtest/zero_dte_realistic.py` to `backtest/fortress_2dte_backtest.py`
2. Modify ORAT queries for `dte BETWEEN 1 AND 5`
3. Implement multi-day position holding (not just EOD settlement)
4. Add option price estimation for intraday exits (BSM or ORAT lookup)
5. Implement profit target exit logic across days
6. Implement force exit logic on expiration day

### Phase 3: Match Production Parameters
1. Use exact `FortressConfig` defaults from `trading/fortress_v2/models.py`
2. Implement all 5 preset configurations
3. Match strike selection logic from `signals.py calculate_strikes()`
4. Match expected move calculation: `spot * (vix/100) / sqrt(252)`
5. Add realistic costs: $0.65/leg, $0.10 slippage, 75 contract cap

### Phase 4: GEX Integration
1. Use `chronicles_gex_calculator.py` to enrich each trade date with GEX data
2. OR query pre-computed `gex_daily` table
3. Add GEX filtering options to backtester
4. Test all GEX filter combinations

### Phase 5: Parameter Optimization
1. Run DTE sweep (0-5) with other params fixed
2. Run SD sweep (1.0-1.5) with other params fixed
3. Run spread width sweep ($2-$10)
4. Run combined optimization (grid search or Bayesian)
5. Use walk-forward validation (not just in-sample)

### Phase 6: ML Retraining
1. Run full backtest with best parameters
2. Feed results to `fortress_ml_advisor.train_from_chronicles()`
3. Validate ML model on held-out period
4. Compare ML-filtered vs unfiltered performance

### Phase 7: Reporting
1. Store results in `zero_dte_backtest_results` table
2. Generate equity curves and store in `zero_dte_equity_curve`
3. Export trade-by-trade CSV
4. Generate comparison report: 0DTE vs 2DTE vs 3DTE
5. Calculate all metrics from Section 4

---

## 6. Key Code Files to Reference

| File | Path | Purpose |
|------|------|---------|
| Fortress Config | `trading/fortress_v2/models.py` | Exact parameters, presets |
| Signal Generation | `trading/fortress_v2/signals.py` | Strike calc, expiration selection, credit estimation |
| Existing Backtester | `backtest/zero_dte_realistic.py` | Starting point (modify for 2DTE) |
| GEX Calculator | `quant/chronicles_gex_calculator.py` | GEX from ORAT data |
| ML Advisor | `quant/fortress_ml_advisor.py` | ML training on backtest results |
| Prophet Advisor | `quant/prophet_advisor.py` | Multi-bot advisory (get_fortress_advice) |
| ORAT Schema | `scripts/create_backtest_schema.py` | All table definitions |
| ORAT Import | `scripts/import_orat_data.py` | Data import pipeline |
| GEX Daily | `scripts/populate_gex_daily.py` | Pre-compute GEX metrics |
| GEX Structures | `scripts/populate_gex_structures.py` | Per-strike gamma profiles |
| Backtest Framework | `backtest/backtest_framework.py` | Base classes, Trade dataclass |
| DB Adapter | `database_adapter.py` | PostgreSQL connection pooling |

---

## 7. Technical Constraints

1. **ORAT data is EOD only** - no intraday snapshots. For intraday exit simulation, either:
   - Use BSM to price options at estimated intraday underlying prices
   - Use daily high/low to determine if profit target was hit
   - Assume "worst case" timing (conservative approach)

2. **SPY has daily expirations Mon-Fri** - but ORAT may not have all daily expirations. Check:
   ```sql
   SELECT trade_date, COUNT(DISTINCT expiration_date) as expirations
   FROM orat_options_eod
   WHERE ticker = 'SPY' AND dte BETWEEN 1 AND 5
   GROUP BY trade_date ORDER BY trade_date DESC LIMIT 20;
   ```

3. **GEX calculation requires OI > 0** - some strikes may have zero OI, filter them

4. **FORTRESS uses Tradier production API** for live quotes - backtest uses ORAT bid/ask instead

5. **Walk-forward validation is critical** - don't optimize parameters on the same data you report results on. Use 70/30 or 80/20 time split, or rolling walk-forward windows.

---

## 8. Expected Deliverables

1. **`backtest/fortress_2dte_backtest.py`** - Main backtester engine
2. **Parameter sweep results** - CSV/JSON with all combinations tested
3. **Comparison report** - 0DTE vs 2DTE vs 3DTE with full metrics
4. **GEX filter analysis** - Which GEX filters improve performance
5. **Optimal configuration** - Best parameters for production use
6. **Retrained ML model** - Updated fortress_ml_advisor trained on 2DTE data
7. **Equity curves** - Stored in database and exportable as charts

---

## 9. Quick Start Commands

```bash
# Check ORAT data availability
cd /home/user/AlphaGEX
python -c "
from database_adapter import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute(\"SELECT ticker, MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date) FROM orat_options_eod GROUP BY ticker\")
for row in cur.fetchall():
    print(row)
conn.close()
"

# Run existing 0DTE backtest (baseline comparison)
python backtest/zero_dte_realistic.py --start 2021-01-01 --end 2025-12-01 --ticker SPY --width 5 --sd 1.2

# After building 2DTE backtester:
python backtest/fortress_2dte_backtest.py --start 2021-01-01 --end 2025-12-01 --dte 3 --sd 1.2 --width 5 --risk 15
```
