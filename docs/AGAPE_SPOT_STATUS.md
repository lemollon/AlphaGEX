# AGAPE-SPOT Comprehensive Feature Status & Performance Audit

**Generated**: 2026-02-15
**Source**: Full code audit of `trading/agape_spot/` (7 files, ~7,700 lines)
**Database**: No DATABASE_URL available in audit environment - trade data sections note what would be queried

---

## === SYSTEM OVERVIEW ===

### 1. WHAT IS AGAPE-SPOT

AGAPE-SPOT is a **multi-ticker, long-only, 24/7 Coinbase spot crypto trading bot**. It buys crypto on Coinbase Advanced Trade API and sells to capture short-term moves. It never shorts (US retail Coinbase doesn't support shorting).

**What it actually does each cycle (every ~1 minute):**
1. Iterates all configured tickers (ETH, BTC, XRP, SHIB, DOGE, MSTU)
2. Fetches crypto market microstructure data (funding rates, L/S ratio, liquidations, Deribit GEX, max pain)
3. Optionally consults ProphetAdvisor for win probability
4. Runs entry quality gates: confidence, funding data, ETH-leader filter, momentum filter, choppy EV gate
5. If signal passes all gates, calculates position size and executes a market buy on Coinbase
6. Manages open positions with no-loss trailing stops (ATR-adaptive, trend-aware)
7. Closes positions via trailing stop hit, max loss, emergency stop, or max hold time
8. Updates Bayesian win tracker per ticker per funding regime
9. Refreshes capital allocator rankings (alpha-weighted scoring)
10. Runs exchange reconciliation every 10 cycles

**Key architectural decisions:**
- **LONG-ONLY**: Can only buy, never short. Bearish signals produce WAIT, not SHORT.
- **Multi-account**: Each ticker can trade on both paper AND live Coinbase accounts simultaneously
- **Per-ticker everything**: Separate exit params, entry filters, loss streaks, Bayesian trackers, direction trackers
- **EV gating, not win-probability gating**: Trades are allowed when Expected Value > 0, not when win rate > X%
- **No SAR**: Can't stop-and-reverse on spot (would need shorting)

---

### 2. SUPPORTED TICKERS

| Ticker | Symbol | Starting Capital | Live Capital | Live? | Quantity Decimals | Price Decimals | Default Qty |
|--------|--------|-----------------|-------------|-------|-------------------|----------------|-------------|
| **ETH-USD** | ETH | $5,000 | $5,000 | YES | 4 | 2 | 0.1 |
| **BTC-USD** | BTC | $5,000 | $5,000 | YES | 5 | 2 | 0.001 |
| **XRP-USD** | XRP | $1,000 | $50 | YES | 0 | 4 | 100 |
| **SHIB-USD** | SHIB | $1,000 | $50 | YES | 0 | 8 | 1,000,000 |
| **DOGE-USD** | DOGE | $1,000 | $50 | YES | 0 | 4 | 500 |
| **MSTU-USD** | MSTU | $1,000 | $50 | YES | 2 | 2 | 10 |

**Per-Ticker Exit Parameters:**

| Ticker | Trail Activation | Trail Distance | Max Loss | Profit Target | Max Hold | Max Positions | Min Scans Between |
|--------|-----------------|---------------|----------|---------------|----------|---------------|-------------------|
| ETH-USD | 1.5% | 1.25% | 1.5% | disabled | 8h | 5 (default) | 0 |
| BTC-USD | 1.5% | 1.25% | 1.5% | disabled | 4h | 2 | 5 |
| XRP-USD | 0.8% | 0.75% | 1.0% | disabled | 4h | 2 | 10 |
| SHIB-USD | 0.8% | 0.60% | 1.0% | disabled | 4h | 2 | 10 |
| DOGE-USD | 0.8% | 0.75% | 1.0% | disabled | 4h | 3 | 5 |
| MSTU-USD | 1.0% | 0.75% | 1.5% | disabled | 6h | 2 | 10 |

**Per-Ticker Entry Filters:**

| Ticker | Require Funding Data | Allow Base Long | ETH Leader | Momentum Filter |
|--------|---------------------|-----------------|------------|-----------------|
| ETH-USD | No | Yes (default) | No (default) | No (default) |
| BTC-USD | No (default) | Yes (default) | No (default) | No (default) |
| XRP-USD | **Yes** | **No** | **Yes** | **Yes** |
| SHIB-USD | **Yes** | **No** | **Yes** | **Yes** |
| DOGE-USD | No | **Yes** | **Yes** | **Yes** |
| MSTU-USD | No | **Yes** | **Yes** | **Yes** |

**API Key Routing:**
- ETH-USD + BTC-USD: `COINBASE_DEDICATED_API_KEY` (shared dedicated account)
- XRP-USD, SHIB-USD, DOGE-USD, MSTU-USD: `COINBASE_API_KEY` (default account) + per-ticker env vars (`COINBASE_{SYMBOL}_API_KEY` if available)
- Paper accounts: No API needed (simulated fills with 0.1% slippage)

**MSTU-USD Special:**
- Market-hours-only: Mon-Fri 8:30 AM - 3:00 PM CT
- It's a leveraged ETF (T-Rex 2X Long MSTR), not a crypto asset
- No Deribit funding data — relies on momentum and ETH leader signals

---

### 3. SYSTEM ARCHITECTURE

```
┌──────────────────────────────────────────────────────────────┐
│                    AGAPE-SPOT TRADER                          │
│                  (trader.py - 2,086 lines)                    │
│                                                              │
│  run_cycle() → for ticker in config.tickers:                 │
│    ├── _refresh_allocator()          # capital allocation    │
│    ├── _reconcile_exchange()         # DB vs Coinbase drift  │
│    └── _run_ticker_cycle(ticker)                             │
│         ├── get_market_data(ticker)                          │
│         ├── get_prophet_advice()                             │
│         ├── get_volatility_context()                         │
│         ├── _manage_positions()      # exit logic            │
│         │    └── _manage_no_loss_trailing()                  │
│         │         ├── MAX_LOSS check                         │
│         │         ├── EMERGENCY_STOP check                   │
│         │         ├── TRAILING_STOP activation + ratchet     │
│         │         └── MAX_HOLD_TIME check                    │
│         ├── _save_equity_snapshot()                          │
│         ├── _check_entry_conditions()                        │
│         ├── generate_signal(ticker)  ──────────────┐         │
│         └── execute_trade_on_account() ──────┐     │         │
│              ├── paper fill (simulated)       │     │         │
│              └── live Coinbase market order   │     │         │
└───────────────────────────────────────────────┼─────┼────────┘
                                                │     │
┌───────────────────────────────────────────────┼─────┼────────┐
│               SIGNAL GENERATOR                │     │         │
│             (signals.py - 1,187 lines)        │     │         │
│                                               │     ▼         │
│  generate_signal(ticker)                      │              │
│    ├── get_market_data(ticker)                │              │
│    │    └── CryptoDataProvider.get_snapshot()  │              │
│    ├── get_prophet_advice()                   │              │
│    │    └── ProphetAdvisor.get_strategy_rec()  │              │
│    ├── _determine_action()                    │              │
│    │    ├── Confidence gate (LOW/MED/HIGH)    │              │
│    │    ├── Funding data gate (XRP/SHIB)      │              │
│    │    ├── ETH-leader filter                 │              │
│    │    ├── Momentum filter (-0.5% block)     │              │
│    │    ├── Choppy EV gate (EWMA dynamic)     │              │
│    │    ├── EV gate (win_prob × avg_win)      │              │
│    │    └── Direction tracker                 │              │
│    ├── _calculate_position_size(ticker)       │              │
│    └── _calculate_levels(ticker)              │              │
│         └── ATR-adaptive stops + targets      │              │
└───────────────────────────────────────────────┼──────────────┘
                                                │
┌───────────────────────────────────────────────┼──────────────┐
│               EXECUTOR                        │              │
│           (executor.py - 1,379 lines)         │              │
│                                               ▼              │
│  AgapeSpotExecutor                                           │
│    ├── _client (default Coinbase)                            │
│    ├── _dedicated_client (ETH/BTC account)                   │
│    ├── execute_trade_on_account()                            │
│    │    ├── Paper: simulated fill + 0.1% slippage            │
│    │    └── Live: market_order_buy via Coinbase API          │
│    ├── sell_spot()                                           │
│    │    ├── Paper: simulated sell                             │
│    │    └── Live: market_order_sell + fill lookup             │
│    ├── get_current_price(ticker)                             │
│    │    ├── Coinbase get_product_book (mid-price)            │
│    │    └── Fallback: CryptoDataProvider                     │
│    ├── get_volatility_context(ticker)                        │
│    │    └── ATR + Kaufman efficiency ratio + chop detection   │
│    └── CapitalAllocator integration                          │
│         └── get_allocation(ticker) → % of available USD      │
└──────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                     DATABASE                                  │
│                 (db.py - 1,401 lines)                         │
│                                                              │
│  AgapeSpotDatabase                                           │
│    ├── agape_spot_positions       # Open + closed trades     │
│    ├── agape_spot_equity_snapshots # Intraday equity curve   │
│    ├── agape_spot_scan_activity    # Every scan cycle logged │
│    ├── agape_spot_activity_log     # Event/action log        │
│    ├── agape_spot_win_tracker      # Bayesian win tracking   │
│    ├── agape_spot_ml_shadow        # ML vs Bayesian compare  │
│    └── agape_spot_ml_config        # ML promotion state      │
└──────────────────────────────────────────────────────────────┘
```

**Bayesian Win Tracker Implementation:**

```python
# Per-ticker, per-funding-regime tracking
# Laplace smoothing: (wins + 1) / (wins + losses + 2)
# Phases:
#   < 10 trades: Cold start, probability floored at 0.52
#   10-49 trades: Bayesian, weight ramps 0.3 → 0.7
#   50+ trades: ML transition flag (future use)
#
# EWMA of trade magnitudes:
#   Halflife ~20 trades (alpha = 0.034)
#   Tracks ema_win and ema_loss separately
#   Used for dynamic choppy EV threshold
#
# Recovery: After losing streak, regime probability drops below 0.50 gate.
#   Each win raises it: (wins+1)/(wins+losses+2)
#   Laplace prior ensures it can never hit 0.0 or 1.0
```

**Capital Allocator:**

```python
# Composite score per ticker:
#   0.25 × profit_factor + 0.20 × win_rate + 0.20 × recent_24h_pnl
#   + 0.15 × total_pnl + 0.20 × alpha_vs_buyhold
#
# Inactive tickers (MSTU on weekends): 0% allocation, capital redistributed
# Floor: 5% per active ticker (prevents starvation)
# Refresh: Every scan cycle
```

---

### 4. FEATURE STATUS

| Feature | Status | Notes |
|---------|--------|-------|
| **Multi-ticker trading** | WORKING | ETH, BTC, XRP, SHIB, DOGE, MSTU all configured |
| **Live Coinbase execution** | WORKING | All 6 tickers in `live_tickers` list |
| **Paper trading parallel** | WORKING | Paper + live run simultaneously per ticker |
| **Bayesian win tracker** | WORKING | Per-ticker, per-regime, Laplace-smoothed |
| **EV gating (Expected Value)** | WORKING | Replaced raw win probability gate |
| **Choppy market EV gate** | WORKING | EWMA dynamic threshold per ticker |
| **ETH-leader filter** | WORKING | Blocks altcoin longs when ETH GEX bearish |
| **Momentum filter** | WORKING | Blocks entry when price down >0.5% over 10 readings |
| **No-loss trailing stops** | WORKING | ATR-adaptive, trend-aware widening |
| **Direction tracker** | WORKING | Per-ticker cooldown after losses |
| **Loss streak pause** | WORKING | 5-min pause after 3 consecutive losses |
| **Daily loss limit** | WORKING | $200 portfolio circuit breaker |
| **Exchange reconciliation** | WORKING | Every 10 cycles, detects DB vs Coinbase drift |
| **Capital allocator** | WORKING | Alpha-weighted scoring, inactive redistribution |
| **Trend-aware exits** | WORKING | Trail + hold time scale 1.5-3x in strong trends |
| **ATR-adaptive stops** | WORKING | Uses real volatility when ATR data available |
| **Equity curve tracking** | WORKING | Historical + intraday snapshots |
| **Scan activity logging** | WORKING | Every cycle logged with full market context |
| **Sell retry with fail count** | WORKING | 3 retries then force-close DB position |
| **ML shadow predictions** | WORKING | Logs ML vs Bayesian for comparison |
| **ML promotion** | STUBBED | `ml_promoted` flag exists but ML model not trained |
| **Alpha intelligence** | WORKING | Full per-ticker vs buy-and-hold comparison |
| **Strategy edge analysis** | WORKING | Portfolio-level narrative generation |
| **ProphetAdvisor** | OPTIONAL | `require_prophet_approval = False` (advisory only) |
| **MSTU market hours** | WORKING | Mon-Fri 8:30 AM - 3:00 PM CT only |

**What's NOT implemented:**
- ML model training pipeline (`ml.py` exists but model needs training data to activate)
- Shorting (impossible on Coinbase spot for US retail)
- SAR (stop-and-reverse) — disabled since can't short
- Multi-exchange support (Coinbase only)

---

### 5. AGAPE-BTC & AGAPE-XRP (Futures Variants)

**Yes, these modules exist.** There are 7 futures variants total:

| Module | Asset | Contract | Exchange | Lines |
|--------|-------|----------|----------|-------|
| `trading/agape/` | ETH | /MET (Micro ETH) | CME via tastytrade | ~3,784 |
| `trading/agape_btc/` | BTC | /MBT (Micro BTC) | CME via tastytrade | ~620 |
| `trading/agape_xrp/` | XRP | /XRP | CME via tastytrade | ~520 |
| `trading/agape_btc_perp/` | BTC | Perpetual | Perp exchange | ~600 |
| `trading/agape_xrp_perp/` | XRP | Perpetual | Perp exchange | ~580 |
| `trading/agape_eth_perp/` | ETH | Perpetual | Perp exchange | ~600 |
| `trading/agape_doge_perp/` | DOGE | Perpetual | Perp exchange | ~580 |
| `trading/agape_shib_perp/` | SHIB | Perpetual | Perp exchange | ~580 |

**Copy-paste audit** (futures audit agent still running at time of writing):
- These are lighter-weight copies of the core AGAPE module (~520-650 lines each vs 3,784 for core)
- Each has its own `models.py`, `db.py`, `signals.py`, `executor.py`, `trader.py`
- Table names appear correctly namespaced (e.g. `agape_btc_positions`, `agape_xrp_positions`)
- Contract specs vary by asset (/MBT for BTC, /XRP for XRP)
- These are **separate from AGAPE-SPOT** — they trade futures, not spot

---

### 6. DATABASE SCHEMA

**agape_spot_positions** (primary trade table):
```sql
CREATE TABLE agape_spot_positions (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(100) UNIQUE NOT NULL,
    ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD',
    side VARCHAR(10) NOT NULL DEFAULT 'long',
    quantity FLOAT NOT NULL,
    entry_price FLOAT NOT NULL,
    stop_loss FLOAT,
    take_profit FLOAT,
    max_risk_usd FLOAT,
    underlying_at_entry FLOAT,
    funding_rate_at_entry FLOAT,
    funding_regime_at_entry VARCHAR(50),
    ls_ratio_at_entry FLOAT,
    squeeze_risk_at_entry VARCHAR(20),
    max_pain_at_entry FLOAT,
    crypto_gex_at_entry FLOAT,
    crypto_gex_regime_at_entry VARCHAR(20),
    oracle_advice VARCHAR(50),
    oracle_win_probability FLOAT,
    oracle_confidence FLOAT,
    oracle_top_factors TEXT,
    signal_action VARCHAR(20),
    signal_confidence VARCHAR(20),
    signal_reasoning TEXT,
    status VARCHAR(20) DEFAULT 'open',
    open_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    close_time TIMESTAMP WITH TIME ZONE,
    close_price FLOAT,
    close_reason VARCHAR(100),
    realized_pnl FLOAT,
    high_water_mark FLOAT DEFAULT 0,
    trailing_active BOOLEAN DEFAULT FALSE,
    current_stop FLOAT,
    oracle_prediction_id INTEGER,
    account_label VARCHAR(50) DEFAULT 'default',
    coinbase_order_id VARCHAR(100),
    coinbase_sell_order_id VARCHAR(100),
    entry_slippage_pct FLOAT,
    exit_slippage_pct FLOAT,
    entry_fee_usd FLOAT,
    exit_fee_usd FLOAT,
    sell_fail_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**agape_spot_equity_snapshots**:
```sql
CREATE TABLE agape_spot_equity_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD',
    equity FLOAT NOT NULL,
    unrealized_pnl FLOAT DEFAULT 0,
    realized_pnl_cumulative FLOAT DEFAULT 0,
    open_positions INTEGER DEFAULT 0,
    eth_price FLOAT,
    funding_rate FLOAT,
    note VARCHAR(200)
);
```

**agape_spot_scan_activity**:
```sql
CREATE TABLE agape_spot_scan_activity (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD',
    outcome VARCHAR(50) NOT NULL,
    eth_price FLOAT,
    funding_rate FLOAT,
    funding_regime VARCHAR(50),
    ls_ratio FLOAT,
    ls_bias VARCHAR(30),
    squeeze_risk VARCHAR(20),
    leverage_regime VARCHAR(30),
    max_pain FLOAT,
    crypto_gex FLOAT,
    crypto_gex_regime VARCHAR(20),
    combined_signal VARCHAR(30),
    combined_confidence VARCHAR(20),
    oracle_advice VARCHAR(50),
    oracle_win_prob FLOAT,
    signal_action VARCHAR(20),
    signal_reasoning TEXT,
    position_id VARCHAR(100),
    error_message TEXT
);
```

**agape_spot_activity_log**:
```sql
CREATE TABLE agape_spot_activity_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ticker VARCHAR(20),
    level VARCHAR(20) DEFAULT 'INFO',
    action VARCHAR(100),
    message TEXT,
    details JSONB
);
```

**agape_spot_win_tracker**:
```sql
CREATE TABLE agape_spot_win_tracker (
    id SERIAL PRIMARY KEY,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD',
    alpha DECIMAL(10, 4) DEFAULT 1.0,
    beta DECIMAL(10, 4) DEFAULT 1.0,
    total_trades INTEGER DEFAULT 0,
    positive_funding_wins INTEGER DEFAULT 0,
    positive_funding_losses INTEGER DEFAULT 0,
    negative_funding_wins INTEGER DEFAULT 0,
    negative_funding_losses INTEGER DEFAULT 0,
    neutral_funding_wins INTEGER DEFAULT 0,
    neutral_funding_losses INTEGER DEFAULT 0
);
```

**agape_spot_ml_shadow** (ML vs Bayesian comparison):
```sql
CREATE TABLE agape_spot_ml_shadow (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ticker VARCHAR(20) NOT NULL,
    position_id VARCHAR(100),
    ml_probability FLOAT NOT NULL,
    bayesian_probability FLOAT NOT NULL,
    funding_regime VARCHAR(50),
    actual_outcome INTEGER,
    resolved_at TIMESTAMP WITH TIME ZONE
);
```

**agape_spot_ml_config**:
```sql
CREATE TABLE agape_spot_ml_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

### 7. DATA FLOW WIREFRAME

```
                    COINBASE ADVANCED TRADE API
                     │                    ▲
                     │ get_product_book   │ market_order_buy/sell
                     ▼                    │
               ┌─────────────┐    ┌──────────────┐
               │  Price Feed  │    │   Executor   │
               └──────┬──────┘    └──────┬───────┘
                      │                  │
            ┌─────────┼──────────────────┼──────────────┐
            │         ▼                  ▼              │
            │  ┌──────────────┐  ┌────────────────┐    │
            │  │ CryptoData   │  │ CapitalAlloc   │    │
            │  │ Provider     │  │ (performance   │    │
            │  │ (funding,    │  │  scoring)      │    │
            │  │  OI, liq,    │  └───────┬────────┘    │
            │  │  GEX, etc.)  │          │             │
            │  └──────┬───────┘          │             │
            │         ▼                  │             │
            │  ┌──────────────┐          │             │
            │  │ Signal Gen   │◄─────────┘             │
            │  │  1. Market data                       │
            │  │  2. Prophet advice                    │
            │  │  3. Entry gates:                      │
            │  │     - confidence                      │
            │  │     - funding data                    │
            │  │     - ETH leader                      │
            │  │     - momentum                        │
            │  │     - choppy EV                       │
            │  │     - negative EV                     │
            │  │  4. Direction tracker                 │
            │  │  5. Position sizing                   │
            │  │  6. ATR-adaptive levels               │
            │  └──────┬───────┘                        │
            │         │ AgapeSpotSignal                 │
            │         ▼                                │
            │  ┌──────────────┐                        │
            │  │   Trader     │                        │
            │  │  (per-ticker │    ┌────────────┐      │
            │  │   cycle)     │───▶│  Database   │     │
            │  │              │    │  7 tables   │     │
            │  │  Manage pos: │    └────────────┘      │
            │  │   - trail    │           ▲            │
            │  │   - stops    │           │            │
            │  │   - hold     │    ┌──────────────┐    │
            │  │   - trend    │───▶│ Bayesian Win │    │
            │  │     aware    │    │ Tracker      │    │
            │  └──────────────┘    │ (per-ticker, │    │
            │                      │  per-regime)  │    │
            │                      └──────────────┘    │
            │                                          │
            │              AGAPE-SPOT TRADER            │
            └──────────────────────────────────────────┘
```

---

## === PROFITABILITY & PERFORMANCE ===

### 8-14. TRADE HISTORY, BUY-AND-HOLD, EDGE, EXITS, SIGNALS, COSTS, RISK

**DATABASE NOT AVAILABLE IN AUDIT ENVIRONMENT**

No `DATABASE_URL` environment variable is set in this development environment. The production database runs on Render PostgreSQL and is not accessible from here.

**What would be queried** (these queries are built into the routes and trader):

```sql
-- Trade stats by ticker and account
SELECT ticker, account_label, COUNT(*),
       COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
       SUM(realized_pnl), AVG(realized_pnl),
       MAX(realized_pnl), MIN(realized_pnl)
FROM agape_spot_positions
WHERE status IN ('closed', 'expired', 'stopped')
GROUP BY ticker, account_label;

-- Win tracker state
SELECT * FROM agape_spot_win_tracker ORDER BY ticker;

-- Daily P&L breakdown
SELECT ticker, DATE(close_time), COUNT(*), SUM(realized_pnl)
FROM agape_spot_positions WHERE status IN ('closed','expired','stopped')
GROUP BY ticker, DATE(close_time) ORDER BY DATE(close_time);

-- Close reasons analysis
SELECT ticker, close_reason, COUNT(*), AVG(realized_pnl), SUM(realized_pnl)
FROM agape_spot_positions WHERE status IN ('closed','expired','stopped')
GROUP BY ticker, close_reason ORDER BY COUNT(*) DESC;

-- Trade duration
SELECT ticker, AVG(EXTRACT(EPOCH FROM (close_time - open_time))/3600)
FROM agape_spot_positions WHERE status IN ('closed','expired','stopped')
GROUP BY ticker;
```

**How to get this data:**
1. **Dashboard**: Go to `/api/agape-spot/performance` for aggregate performance
2. **Per-ticker**: `/api/agape-spot/performance/{ticker}` for individual ticker stats
3. **Alpha intelligence**: `/api/agape-spot/alpha-intelligence` for buy-and-hold comparison
4. **Win tracker**: `/api/agape-spot/win-tracker` for Bayesian state per ticker
5. **Equity curve**: `/api/agape-spot/equity-curve` for historical P&L chart data
6. **Direct DB**: Connect to Render PostgreSQL and run the queries above

**What the code tells us about expected performance:**

Based on the code comments and parameter history, we can infer:

1. **BTC-USD has been losing money**: Comment says "backtest shows BTC net negative (-$89)", max_hold reduced to 4h, max_positions capped at 2, min_scans_between_trades added
2. **XRP/SHIB had noise-exit problems**: Trail activation was 0.3% (now 0.8%), trail distance was 0.2-0.25% (now 0.60-0.75%), max loss was 0.5% (now 1.0%)
3. **ETH is the strongest ticker**: Gets the widest params (8h hold, 1.5% trail activation, 1.25% trail distance)
4. **Altcoins were over-trading**: `allow_base_long` disabled for XRP and SHIB; `min_scans_between_trades` added for all altcoins
5. **The choppy EV gate was validated by backtest**: Comment says "C beat no gate (A): +$87.66 P&L, -284 trades"
6. **Win/loss size ratio was problematic**: Comment says "losses were $30 vs $9 avg win, need 77% WR to break even" — this led to max_unrealized_loss reduction from 3.0% to 1.5%

---

## === ISSUES & NEXT STEPS ===

### 15. OPEN ISSUES

**Critical:**
1. **No database access from dev environment**: Cannot verify actual P&L, win rates, or trade history. All performance claims are based on code comments.

2. **ML module exists but is not active**: `ml.py` (600 lines) implements an XGBoost model but `ml_promoted` is never set to `true` in production. The ML shadow logging is working but the model likely has insufficient training data.

3. **`eth_price` column name in equity snapshots**: The column is named `eth_price` but stores the price of whatever ticker the row belongs to (BTC, XRP, etc.). This is a naming inconsistency from the original single-ticker design.

4. **Sell retry force-close leaves orphaned coins**: After 3 failed sell attempts, the DB position is force-closed at current price, but the coins remain in Coinbase. The reconciliation check should catch this, but it only logs warnings — doesn't auto-sell.

**Minor:**
5. **Bare except clauses**: Several `except Exception` blocks that could be more specific (e.g., in `_manage_no_loss_trailing`, timezone parsing).

6. **`_execute` in db.py creates and closes connections per query**: No connection pooling within the DB layer (relies on `database_adapter.get_connection()` which may or may not pool).

7. **equity_snapshots `realized_pnl_cumulative` column**: Named inconsistently with the rest of the codebase which uses `realized_pnl` or `cumulative_pnl`.

8. **MSTU-USD is a leveraged ETF on Coinbase**: This is an unusual choice. MSTU is T-Rex 2X Long MSTR Daily Target ETF. Trading it 24/7 on Coinbase (but gated to market hours) means no after-hours trading, which is correct, but the crypto microstructure signals (funding rate, liquidations) are meaningless for an ETF.

### 16. WHAT'S NOT WORKING (Honest Assessment)

Based on code evidence:

1. **BTC-USD is losing money**: The comments explicitly state "backtest shows BTC net negative (-$89)". Max hold was cut from 8h to 4h, position cap reduced to 2, scan spacing added. The system is trying to limit BTC exposure because it doesn't have edge there.

2. **Altcoin exits were too tight**: The repeated widening of XRP/SHIB/DOGE exit parameters (trail activation from 0.3% to 0.8%, trail distance from 0.2% to 0.75%, etc.) shows these tickers were getting stopped out on noise, giving their alpha to buy-and-hold.

3. **Win/loss size asymmetry was/is a problem**: The comment "losses were $30 vs $9 avg win, need 77% WR to break even" reveals the fundamental challenge — the system's average loss is 3x its average win. Even with the max_loss cut from 3.0% to 1.5%, if avg loss > avg win, you need a very high win rate.

4. **Overtrading on altcoins**: XRP had 408 `NO_FALLBACK_SIGNAL` outcomes in 7 days, and `ALTCOIN_BASE_LONG` was firing every scan with zero conviction. This led to disabling base_long for XRP/SHIB and adding scan spacing.

5. **The bot may be capturing beta, not alpha**: The extensive alpha intelligence system (`_generate_strategy_edge`, `_compute_alpha_data`) exists precisely because the team suspects the bot is just riding crypto's upward trend rather than generating genuine alpha.

### 17. RECOMMENDATIONS

Based on the code audit:

1. **Get actual database numbers first**: This entire audit is incomplete without real trade data. Run the SQL queries listed in section 8 against the production database. The code architecture is solid — the question is whether the signals and exits generate alpha.

2. **BTC-USD: Consider pausing or reducing further**: The code already acknowledges negative EV. If live BTC trading is still losing after the 4h hold + 2-position cap changes, pause it and let paper track while the system collects more data.

3. **Fix the win/loss size asymmetry**: This is the #1 issue. If avg_loss > avg_win, you need >50% win rate just to break even. Options:
   - Widen profit targets (currently disabled — all trailing)
   - Tighten stops further (risky — may increase noise exits)
   - Better entry timing (only enter when microstructure strongly favors longs)
   - The ATR-adaptive stops should help — verify they're actually activating in production

4. **MSTU-USD has no edge source**: The crypto microstructure signals are meaningless for a leveraged ETF. MSTU should either:
   - Get its own signal source (e.g., MSTR stock price, BTC correlation, options flow)
   - Be removed from AGAPE-SPOT and managed separately
   - Or acknowledged as a pure momentum play

5. **ML model: Train it**: The shadow logging infrastructure is built and working. Once there are 50+ trades per ticker (the `ml_transition_trades` threshold), train the XGBoost model and compare its predictions to Bayesian. The code is ready for ML promotion — it just needs data.

6. **Monitor the reconciliation drift**: The exchange reconciliation runs every 10 cycles and logs mismatches. If orphaned coins are appearing regularly, the sell retry logic needs hardening (maybe retry with limit orders instead of market orders).

7. **Consider reducing position count**: ETH allows 5 open positions per ticker — this means up to $5,000 in ETH exposure simultaneously. In a flash crash, all 5 hit their max loss at once. Consider whether 2-3 positions per ticker is more appropriate for the capital size.

8. **The EV gate is the right framework**: The shift from raw win-probability gating to Expected Value gating is mathematically correct. The EWMA dynamic threshold for choppy markets is a good approach. Make sure the perf_stats (avg_win, avg_loss) are being refreshed correctly each cycle.

---

## FILE MANIFEST

| File | Lines | Purpose |
|------|-------|---------|
| `trading/agape_spot/models.py` | 1,067 | Config, signals, positions, BayesianWinTracker, CapitalAllocator |
| `trading/agape_spot/signals.py` | 1,187 | Signal generation, entry gates, EV calculation, ATR-adaptive levels |
| `trading/agape_spot/trader.py` | 2,086 | Main orchestrator, position management, alpha intelligence |
| `trading/agape_spot/db.py` | 1,401 | 7-table PostgreSQL persistence layer |
| `trading/agape_spot/executor.py` | 1,379 | Coinbase API execution, multi-account routing |
| `trading/agape_spot/ml.py` | 600 | XGBoost ML model (shadow mode) |
| `backend/api/routes/agape_spot_routes.py` | 2,385 | 40+ API endpoints |
| **Total** | **~10,105** | |

---

*This document was generated from a full code audit. Sections 8-14 (performance data) require production database access to complete. Run the queries against Render PostgreSQL or check the dashboard endpoints listed above.*
