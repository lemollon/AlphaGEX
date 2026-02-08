# AlphaGEX System Status & Verification Guide
**Generated: 2025-11-28**

## 🎯 CURRENT SYSTEM ARCHITECTURE

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                          │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   TRADIER API ──────────┐                                                      │
│   (Real-time quotes)    │                                                      │
│                         ▼                                                      │
│                  ┌──────────────────┐                                          │
│   POLYGON API ──▶│ UNIFIED DATA     │◀── TRADING VOLATILITY API               │
│   (Options/GEX)  │ PROVIDER         │    (GEX/Gamma data)                      │
│                  └────────┬─────────┘                                          │
│                           │                                                    │
└───────────────────────────┼────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                         DECISION LAYER                                         │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                   MARKET REGIME CLASSIFIER                              │  │
│   │  ─────────────────────────────────────────────────────────────────────  │  │
│   │  Inputs:                        │  Output:                              │  │
│   │  • Spot price                   │  • recommended_action                 │  │
│   │  • Net GEX (+/-$B)              │    - SELL_PREMIUM                     │  │
│   │  • Gamma flip point             │    - BUY_CALLS                        │  │
│   │  • IV Rank (0-100%)             │    - BUY_PUTS                         │  │
│   │  • VIX level                    │    - STAY_FLAT                        │  │
│   │  • Momentum (1h, 4h)            │  • confidence (0-100%)                │  │
│   │  • Trend (MA20, MA50)           │  • max_position_size                  │  │
│   │                                 │  • stop_loss_pct                      │  │
│   │                                 │  • profit_target_pct                  │  │
│   └─────────────────────────────────┴───────────────────────────────────────┘  │
│                                      │                                         │
│                                      ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                    STRATEGY SELECTION                                   │  │
│   │  ─────────────────────────────────────────────────────────────────────  │  │
│   │  SELL_PREMIUM + Trend:          │  BUY Direction:                       │  │
│   │  • UPTREND    → Bull Put Spread │  • BUY_CALLS → Long Call              │  │
│   │  • DOWNTREND  → Bear Call Spread│  • BUY_PUTS  → Long Put               │  │
│   │  • RANGE      → Iron Condor     │                                       │  │
│   └─────────────────────────────────┴───────────────────────────────────────┘  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                        EXECUTION LAYER                                         │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   ┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐  │
│   │  POSITION SIZER     │   │  TRADE EXECUTOR     │   │  POSITION MANAGER   │  │
│   │  (Kelly Criterion)  │   │  (Entry Logic)      │   │  (Exit Logic)       │  │
│   │                     │   │                     │   │                     │  │
│   │  1. Get stats       │   │  1. Get prices      │   │  1. Check targets   │  │
│   │  2. Calculate Kelly │──▶│  2. Validate liquidity──▶│  2. Check stops     │  │
│   │  3. VIX adjustment  │   │  3. Execute entry   │   │  3. Check time      │  │
│   │  4. Cap to max %    │   │  4. Record position │   │  4. Execute exit    │  │
│   └─────────────────────┘   └─────────────────────┘   └──────────┬──────────┘  │
│                                                                   │            │
└───────────────────────────────────────────────────────────────────┼────────────┘
                                                                    │
                                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                        FEEDBACK LAYER                                          │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                   PERFORMANCE TRACKER                                   │  │
│   │  ─────────────────────────────────────────────────────────────────────  │  │
│   │                                                                         │  │
│   │  Trade Closed ─────▶ Calculate Win Rate ─────▶ Update Strategy Stats    │  │
│   │                                │                        │               │  │
│   │                                ▼                        ▼               │  │
│   │                      Calculate Avg Win/Loss      Next Trade Uses        │  │
│   │                                │                 Updated Kelly          │  │
│   │                                ▼                        │               │  │
│   │                      Calculate Expectancy               │               │  │
│   │                                │                        │               │  │
│   │                                └────────────────────────┘               │  │
│   │                                                                         │  │
│   │  FEEDBACK LOOP CLOSES: Live Results → Strategy Stats → Future Sizing    │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 THE DECISION MATRIX

| IV Rank | Gamma | Trend | VIX | Decision | Confidence | Strategy |
|---------|-------|-------|-----|----------|------------|----------|
| HIGH (60-80%) | POSITIVE | RANGE | Any | SELL_PREMIUM | 85% | Iron Condor |
| HIGH | POSITIVE | UPTREND | Any | SELL_PREMIUM | 70% | Bull Put Spread |
| HIGH | POSITIVE | DOWNTREND | Any | SELL_PREMIUM | 70% | Bear Call Spread |
| Any | NEGATIVE | Below Flip | >25 | BUY_CALLS | 75% | Long Call |
| Any | NEGATIVE | Above Flip | >25 | BUY_PUTS | 75% | Long Put |
| EXTREME_HIGH | Any | RANGE | Any | SELL_PREMIUM | 70% | Iron Condor |
| EXTREME_LOW | Any | UPTREND | <15 | BUY_CALLS | 60% | Long Call |
| EXTREME_LOW | Any | DOWNTREND | <15 | BUY_PUTS | 60% | Long Put |
| * | * | * | * | STAY_FLAT | 30% | No Trade |

---

## 🔑 API VERIFICATION URLs

### Base URL (on Render): `https://your-app.onrender.com`

### 1. Health Check
```
GET /health
```
**Tests:** Server running, database connected

### 2. Market Data (Tradier/Polygon)
```
GET /api/gex/SPY
```
**Tests:** Trading Volatility API key works, GEX data flowing

### 3. Current Price
```
GET /api/price-history?symbol=SPY&range=1d
```
**Tests:** Tradier/Polygon quote data works

### 4. VIX Data
```
GET /api/vix/current
```
**Tests:** VIX data provider works

### 5. Trader Status
```
GET /api/trader/status
```
**Tests:** Autonomous trader initialized, database connection

### 6. Trader Performance
```
GET /api/trader/performance
```
**Tests:** Performance tracking, historical trades

### 7. Open Positions
```
GET /api/trader/positions
```
**Tests:** Position tracking

### 8. Backtest Results
```
GET /api/backtests/results?limit=5
```
**Tests:** Backtester data available

### 9. Strategy Recommendations
```
GET /api/backtests/smart-recommendations
```
**Tests:** Strategy stats integration

### 10. Risk Metrics
```
GET /api/autonomous/risk/metrics
```
**Tests:** Risk management working

---

## ✅ VERIFICATION CHECKLIST

### API Keys Working?
| API | Environment Variable | Test Endpoint | Expected |
|-----|---------------------|---------------|----------|
| Tradier | `TRADIER_API_KEY` | `/api/gex/SPY` | Returns spot_price > 0 |
| Polygon | `POLYGON_API_KEY` | `/api/price-history?symbol=SPY` | Returns OHLC data |
| Trading Vol | `TRADING_VOL_API_KEY` | `/api/gex/SPY` | Returns net_gex ≠ null |
| Database | `DATABASE_URL` | `/health` | status: "healthy" |
| Claude | `ANTHROPIC_API_KEY` | AI reasoning in trades | Optional |

### Data Flow Working?

#### 1. GEX Data Arrives
**Endpoint:** `GET /api/gex/SPY`
**What it does:** Fetches Gamma Exposure (GEX) data from Trading Volatility API, providing net gamma, call/put walls, and flip points.
**Expected Response:**
```json
{
  "symbol": "SPY",
  "spot_price": 585.42,
  "net_gex": 2450000000,
  "call_wall": 590,
  "put_wall": 575,
  "gex_flip_point": 580,
  "timestamp": "2025-12-25T14:30:00Z"
}
```
**Verification:** `net_gex` should be non-null; `spot_price` should match current market price within 0.5%.
**If failing:** Check `TRADING_VOL_API_KEY` environment variable; verify API subscription is active.

#### 2. IV Rank Calculated
**Endpoint:** `GET /api/vix/current`
**What it does:** Fetches current VIX level and calculates IV Rank (percentile of current IV vs. last 252 trading days).
**Expected Response:**
```json
{
  "vix": 18.5,
  "iv_rank": 45,
  "iv_percentile": 42,
  "vix_term_structure": "contango",
  "is_live": true
}
```
**Calculation:** `IV Rank = (Current IV - 52wk Low) / (52wk High - 52wk Low) × 100`
**Verification:** `iv_rank` should be 0-100; `is_live` should be true during market hours.
**If failing:** Check Polygon API key; system falls back to VIX=18 estimate if unavailable.

#### 3. Regime Classified
**Endpoint:** `GET /api/gex/SPY/regime`
**What it does:** Analyzes market conditions and classifies current regime (POSITIVE_GAMMA, NEGATIVE_GAMMA, NEUTRAL).
**Expected Response:**
```json
{
  "regime": "POSITIVE_GAMMA",
  "confidence": 85,
  "indicators": {
    "gex_signal": "BULLISH",
    "vix_signal": "LOW_VOL",
    "trend_signal": "UPTREND",
    "momentum": "STRONG"
  },
  "recommended_action": "SELL_PREMIUM"
}
```
**Logic:** Located in `core/market_regime_classifier.py`. Uses GEX polarity, VIX level, price vs. moving averages, and momentum indicators.
**Verification:** `regime` should be one of: POSITIVE_GAMMA, NEGATIVE_GAMMA, NEUTRAL. `confidence` should be 0-100.

#### 4. Strategy Selected
**Endpoint:** `GET /api/trader/status`
**What it does:** Shows current trader state including selected strategy based on regime classification.
**Expected Response:**
```json
{
  "status": "ACTIVE",
  "current_strategy": "BULL_PUT_SPREAD",
  "regime": "POSITIVE_GAMMA",
  "last_signal_time": "2025-12-25T14:30:00Z",
  "next_evaluation": "2025-12-25T15:00:00Z",
  "open_positions": 2
}
```
**Strategy Selection Logic:**
- POSITIVE_GAMMA + UPTREND → Bull Put Spread
- POSITIVE_GAMMA + DOWNTREND → Bear Call Spread
- POSITIVE_GAMMA + RANGE → Iron Condor
- NEGATIVE_GAMMA + Below Flip → Long Calls
- NEGATIVE_GAMMA + Above Flip → Long Puts
**Verification:** `current_strategy` should match regime conditions per decision matrix.

#### 5. Position Sized (Kelly Criterion)
**Location:** Trade decision logs in `bot_decision_logs` table
**What it does:** Calculates optimal position size using Kelly Criterion based on historical win rate and avg win/loss.
**Kelly Formula:**
```
Kelly % = (Win Rate × Avg Win - Loss Rate × Avg Loss) / Avg Loss

Example:
- Win Rate: 68%, Avg Win: 15%, Avg Loss: 25%
- Kelly = (0.68 × 15 - 0.32 × 25) / 25 = (10.2 - 8) / 25 = 8.8%
- With 0.5 Kelly fraction: 4.4% of capital per trade
```
**Adjustments Applied:**
1. Half-Kelly (multiply by 0.5) for safety
2. VIX stress reduction: -15% if VIX > 20, -30% if VIX > 30
3. Hard cap: Never exceed 15% of capital per trade
**Verification:** Check `kelly_pct` and `position_size_dollars` in decision logs.

#### 6. Trade Executed
**Endpoint:** `GET /api/trader/positions`
**What it does:** Returns list of open positions with entry details.
**Expected Response:**
```json
{
  "positions": [
    {
      "id": 123,
      "symbol": "SPY",
      "strategy": "BULL_PUT_SPREAD",
      "legs": [
        {"strike": 580, "type": "PUT", "action": "SELL", "contracts": 5},
        {"strike": 575, "type": "PUT", "action": "BUY", "contracts": 5}
      ],
      "entry_price": 1.25,
      "entry_time": "2025-12-25T10:30:00Z",
      "current_price": 0.85,
      "unrealized_pnl": 200,
      "status": "OPEN"
    }
  ]
}
```
**Execution Flow:**
1. Signal generated → Position sizer calculates size → Trade executor validates liquidity
2. Order placed (paper or live via Tradier) → Position recorded in database
3. Order confirmation logged with order_id
**Verification:** Positions should have valid entry_price, contracts, and order details.

#### 7. Exit Monitored
**Location:** `trading/position_monitor.py` runs continuously
**What it does:** Monitors open positions for exit conditions every 60 seconds.
**Exit Conditions Checked:**
1. **Profit Target:** Close at 50% profit (configurable per strategy)
2. **Stop Loss:** Close if option doubles (200% loss on premium sold)
3. **Time Exit:** Close at 7 DTE to avoid gamma risk
4. **Manual Override:** Close if circuit breaker triggered
**Monitoring Query:**
```sql
SELECT * FROM autonomous_positions
WHERE status = 'OPEN'
AND (
  current_pnl_pct >= profit_target_pct OR
  current_pnl_pct <= -stop_loss_pct OR
  dte <= roll_at_dte
)
```
**Verification:** Check `position_monitor.log` for exit evaluations; closed trades appear in `autonomous_closed_trades`.

#### 8. Stats Updated (Feedback Loop)
**Endpoint:** `GET /api/backtests/results?limit=5`
**What it does:** Returns recent closed trades and updated strategy statistics.
**Expected Response:**
```json
{
  "recent_trades": [...],
  "strategy_stats": {
    "BULL_PUT_SPREAD": {
      "total_trades": 47,
      "win_rate": 68.1,
      "avg_win_pct": 12.5,
      "avg_loss_pct": 22.3,
      "expectancy": 3.42,
      "last_updated": "2025-12-25T16:00:00Z"
    }
  }
}
```
**Feedback Loop Process:**
1. Trade closes → Record to `autonomous_closed_trades`
2. Query last 90 days of trades for this strategy
3. Recalculate win_rate, avg_win, avg_loss, expectancy
4. If 5+ trades exist → Update `strategy_stats.json`
5. Next trade uses updated Kelly calculation
**Verification:** `strategy_stats` should update after each closed trade; expectancy > 0 required for trading.

---

## 🎯 KELLY CRITERION POSITION SIZING

The system uses Kelly Criterion for position sizing:

```
Kelly Fraction = (Win Rate × Avg Win - Loss Rate × Avg Loss) / Avg Loss

Example with Iron Condor:
- Win Rate: 72%
- Avg Win: 12% of premium
- Avg Loss: 35% of premium

Kelly = (0.72 × 12 - 0.28 × 35) / 35
     = (8.64 - 9.8) / 35
     = -0.033 (NEGATIVE = DON'T TRADE!)

This is why backtest validation matters!
```

### Position Size Adjustments:
1. **Confidence Scale:** Kelly × (confidence/100)
2. **VIX Stress:** If VIX > 20: reduce by 15%; if VIX > 30: reduce by 30%
3. **Regime Cap:** High confidence: max 15%, Medium: 10%, Low: 5%

---

## 🔄 FEEDBACK LOOP IN DETAIL

```
TRADE CLOSED
    │
    ▼
┌───────────────────────────────────┐
│ Record to autonomous_closed_trades│
│ - entry_price, exit_price         │
│ - realized_pnl                    │
│ - strategy_name                   │
└───────────────┬───────────────────┘
                │
                ▼
┌───────────────────────────────────┐
│ Query all closed trades           │
│ for this strategy (last 90 days)  │
└───────────────┬───────────────────┘
                │
                ▼
┌───────────────────────────────────┐
│ Calculate:                        │
│ - win_rate = wins / total         │
│ - avg_win = avg(pnl where pnl>0)  │
│ - avg_loss = avg(pnl where pnl<0) │
│ - expectancy = (p×w) - (q×l)      │
└───────────────┬───────────────────┘
                │
                ▼
┌───────────────────────────────────┐
│ If total_trades >= 5:             │
│   Update strategy_stats.json      │
│   Invalidate cache                │
│   Log change to change_log.jsonl  │
└───────────────┬───────────────────┘
                │
                ▼
┌───────────────────────────────────┐
│ NEXT TRADE:                       │
│ Kelly calculation uses NEW stats  │
│ Position size adapts automatically│
└───────────────────────────────────┘
```

---

## 🚨 KNOWN ISSUES & TECHNICAL DEBT

### High Priority
1. **No test coverage for mixins** - trading/mixins/* have 0% test coverage
2. **SPX trader redundancy** - spx_institutional_trader.py still exists (2,479 lines of duplicate code)
3. **Bare except clauses** - 89 instances of `except:` without specific exceptions

### Medium Priority
4. **Strategy stats cold start** - New strategies use estimates until 10+ trades
5. **Backtest data dependency** - System needs historical data to function
6. **No circuit breaker for API failures** - Could hammer failing APIs

### Low Priority
7. **Psychology routes complexity** - Large codebase, may have redundant logic
8. **Frontend components not tested** - UI could break silently

---

## 📈 IS THE LOGIC PROFITABLE?

### The Math Behind Profitability

**For the system to be profitable, each strategy needs:**
```
Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss) > 0
```

**Example Strategies from Initial Estimates:**

| Strategy | Win Rate | Avg Win | Avg Loss | Expectancy |
|----------|----------|---------|----------|------------|
| Iron Condor | 72% | 12% | 35% | -1.16% ❌ |
| Bull Put Spread | 68% | 10% | 18% | 1.04% ✅ |
| Negative GEX Squeeze | 75% | 20% | 30% | 7.5% ✅ |
| Long Straddle | 55% | 35% | 20% | 10.25% ✅ |

**CRITICAL INSIGHT:**
The initial Iron Condor estimate is actually NEGATIVE expectancy. The system should BLOCK this strategy until real backtests prove otherwise.

### The Kelly Gate

The system has a built-in profitability gate:
```python
# In position_sizer.py
if kelly_fraction <= 0:
    return None  # DON'T TRADE - negative expectancy
```

This prevents unprofitable strategies from being traded.

---

## 🗄️ DATABASE SCHEMA

### Core Trading Tables

#### `autonomous_positions` - Active Trading Positions
```sql
CREATE TABLE autonomous_positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,              -- SPY, SPX, QQQ
    strategy VARCHAR(50) NOT NULL,            -- BULL_PUT_SPREAD, IRON_CONDOR, etc.
    direction VARCHAR(10),                    -- BULLISH, BEARISH, NEUTRAL

    -- Position Details
    entry_price DECIMAL(10,4),                -- Average entry price per contract
    current_price DECIMAL(10,4),              -- Current mark price
    contracts INTEGER DEFAULT 1,              -- Number of contracts

    -- Legs (for multi-leg strategies)
    legs JSONB,                               -- [{strike, type, action, contracts}]

    -- Risk Management
    stop_loss_pct DECIMAL(5,2) DEFAULT 200,   -- Stop loss percentage
    profit_target_pct DECIMAL(5,2) DEFAULT 50,-- Profit target percentage
    max_loss_dollars DECIMAL(10,2),           -- Maximum dollar loss

    -- Timing
    entry_time TIMESTAMP DEFAULT NOW(),
    expiration DATE,
    dte INTEGER,                              -- Days to expiration

    -- P&L Tracking
    unrealized_pnl DECIMAL(10,2) DEFAULT 0,
    realized_pnl DECIMAL(10,2) DEFAULT 0,

    -- Status
    status VARCHAR(20) DEFAULT 'OPEN',        -- OPEN, CLOSED, EXPIRED, ROLLED
    exit_reason VARCHAR(100),                 -- Why position was closed
    exit_time TIMESTAMP,

    -- Metadata
    order_id VARCHAR(50),                     -- Broker order ID
    decision_id VARCHAR(50),                  -- Links to bot_decision_logs
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### `autonomous_closed_trades` - Historical Trade Records
```sql
CREATE TABLE autonomous_closed_trades (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES autonomous_positions(id),
    symbol VARCHAR(10) NOT NULL,
    strategy VARCHAR(50) NOT NULL,

    -- Entry Details
    entry_price DECIMAL(10,4),
    entry_time TIMESTAMP,
    contracts INTEGER,

    -- Exit Details
    exit_price DECIMAL(10,4),
    exit_time TIMESTAMP,
    exit_reason VARCHAR(100),

    -- P&L
    realized_pnl DECIMAL(10,2),
    pnl_pct DECIMAL(5,2),

    -- Analytics
    hold_duration_hours INTEGER,
    max_drawdown_pct DECIMAL(5,2),
    max_profit_pct DECIMAL(5,2),

    -- Market Context at Entry
    entry_vix DECIMAL(5,2),
    entry_regime VARCHAR(30),
    entry_gex DECIMAL(15,2),

    created_at TIMESTAMP DEFAULT NOW()
);
```

#### `bot_decision_logs` - Trading Decision Audit Trail
```sql
CREATE TABLE bot_decision_logs (
    id SERIAL PRIMARY KEY,
    decision_id VARCHAR(50) UNIQUE NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),

    -- Bot Identity
    bot_name VARCHAR(20) NOT NULL,            -- ATLAS, PROMETHEUS, SOLOMON
    decision_type VARCHAR(30),                -- ENTRY, EXIT, SKIP, ROLL

    -- What/Why/How (Transparency)
    what TEXT,                                -- What action was taken
    why TEXT,                                 -- Why this decision
    how TEXT,                                 -- How it was executed

    -- Trade Details
    symbol VARCHAR(10),
    strategy VARCHAR(50),
    action VARCHAR(20),                       -- BUY, SELL, HOLD

    -- Position Sizing
    kelly_pct DECIMAL(5,2),
    position_size_dollars DECIMAL(10,2),
    position_size_contracts INTEGER,

    -- Market Context
    spot_price DECIMAL(10,2),
    vix DECIMAL(5,2),
    regime VARCHAR(30),

    -- Legs (JSONB for flexibility)
    legs JSONB,

    -- Backtest Reference
    backtest_win_rate DECIMAL(5,2),
    backtest_expectancy DECIMAL(5,2),

    -- Execution
    order_id VARCHAR(50),
    actual_pnl DECIMAL(10,2),

    created_at TIMESTAMP DEFAULT NOW()
);
```

#### `strategy_stats` - Strategy Performance Statistics
```sql
CREATE TABLE strategy_stats (
    id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(50) UNIQUE NOT NULL,

    -- Core Stats
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate DECIMAL(5,2),

    -- P&L Stats
    avg_win_pct DECIMAL(5,2),
    avg_loss_pct DECIMAL(5,2),
    expectancy DECIMAL(5,2),
    profit_factor DECIMAL(5,2),

    -- Risk Stats
    max_drawdown_pct DECIMAL(5,2),
    sharpe_ratio DECIMAL(5,2),

    -- Metadata
    last_trade_date DATE,
    last_updated TIMESTAMP DEFAULT NOW(),

    CONSTRAINT positive_expectancy CHECK (expectancy > 0 OR total_trades < 5)
);
```

#### `gex_data` - Gamma Exposure Cache
```sql
CREATE TABLE gex_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),

    -- Core GEX Data
    net_gex DECIMAL(15,2),
    spot_price DECIMAL(10,2),

    -- Levels
    call_wall DECIMAL(10,2),
    put_wall DECIMAL(10,2),
    gex_flip_point DECIMAL(10,2),

    -- Strike Data (JSONB for flexibility)
    strikes JSONB,

    -- Metadata
    source VARCHAR(30),                       -- TRADING_VOL, CALCULATED
    expiration_date DATE,

    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_gex_symbol_time ON gex_data(symbol, timestamp DESC);
```

#### `spx_wheel_positions` - SPX Wheel Strategy Positions
```sql
CREATE TABLE spx_wheel_positions (
    id SERIAL PRIMARY KEY,
    option_ticker VARCHAR(50) NOT NULL,
    strike DECIMAL(10,2) NOT NULL,
    expiration DATE NOT NULL,
    contracts INTEGER DEFAULT 1,

    -- Entry
    entry_price DECIMAL(10,4),
    premium_received DECIMAL(10,2),
    entry_time TIMESTAMP DEFAULT NOW(),

    -- Exit
    exit_price DECIMAL(10,4),
    settlement_pnl DECIMAL(10,2),
    total_pnl DECIMAL(10,2),

    -- Status
    status VARCHAR(20) DEFAULT 'OPEN',
    closed_at TIMESTAMP,

    -- Parameters Used
    parameters_used JSONB,
    notes TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🔐 ENVIRONMENT VARIABLES

### Required Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/alphagex` | **YES** |
| `TRADIER_API_KEY` | Tradier API key for quotes/orders | `aBcDeFgHiJkLmNoP` | **YES** |
| `TRADIER_ACCOUNT_ID` | Tradier account ID | `12345678` | For LIVE trading |
| `POLYGON_API_KEY` | Polygon.io API key | `xYz123AbC` | **YES** |
| `TRADING_VOL_API_KEY` | Trading Volatility API key | `tv_abc123` | **YES** |

### Optional Variables

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `ANTHROPIC_API_KEY` | Claude API for AI reasoning | None | Enables AI trade explanations |
| `TRADIER_SANDBOX` | Use Tradier sandbox mode | `true` | Set `false` for live trading |
| `LOG_LEVEL` | Logging verbosity | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `ENABLE_PUSH_NOTIFICATIONS` | Enable push alerts | `false` | Requires VAPID keys |
| `VAPID_PUBLIC_KEY` | Push notification public key | None | For web push |
| `VAPID_PRIVATE_KEY` | Push notification private key | None | For web push |

### Frontend Variables (Vercel)

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `https://api.alphagex.com` |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL | `wss://api.alphagex.com/ws` |

### Setting Environment Variables

**Local Development (.env file):**
```bash
# Copy example and fill in values
cp .env.example .env

# Required
DATABASE_URL=postgresql://localhost:5432/alphagex
TRADIER_API_KEY=your_tradier_key
POLYGON_API_KEY=your_polygon_key
TRADING_VOL_API_KEY=your_trading_vol_key

# Optional
TRADIER_SANDBOX=true
LOG_LEVEL=DEBUG
```

**Render (Production):**
1. Go to Dashboard → Environment → Environment Variables
2. Add each variable with production values
3. Restart service after changes

**Vercel (Frontend):**
1. Go to Project Settings → Environment Variables
2. Add `NEXT_PUBLIC_API_URL` pointing to Render backend

---

## 🚀 DEPLOYMENT STEPS

### Backend Deployment (Render)

#### Initial Setup
1. **Create Render Account** at render.com
2. **Connect GitHub Repository**
   - New → Web Service → Connect repo
   - Select `lemollon/AlphaGEX`
3. **Configure Service**
   ```
   Name: alphagex-api
   Environment: Python
   Build Command: pip install -r requirements.txt
   Start Command: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
   ```
4. **Add Environment Variables** (see section above)
5. **Create PostgreSQL Database**
   - New → PostgreSQL
   - Copy `DATABASE_URL` to web service env vars

#### Deploy Updates
```bash
# Commits to main branch auto-deploy
git push origin main

# Or manually trigger in Render dashboard
# Dashboard → Manual Deploy → Deploy latest commit
```

#### Verify Deployment
```bash
# Health check
curl https://your-app.onrender.com/health

# Should return:
{"status": "healthy", "database": "connected", "version": "1.0.0"}
```

### Frontend Deployment (Vercel)

#### Initial Setup
1. **Create Vercel Account** at vercel.com
2. **Import Project**
   - New Project → Import Git Repository
   - Select `lemollon/AlphaGEX`
   - Set Root Directory: `frontend`
3. **Configure Build**
   ```
   Framework Preset: Next.js
   Build Command: npm run build
   Output Directory: .next
   ```
4. **Add Environment Variables**
   ```
   NEXT_PUBLIC_API_URL=https://your-render-app.onrender.com
   ```

#### Deploy Updates
```bash
# Commits to main auto-deploy via Vercel GitHub integration
git push origin main
```

---

## 💾 BACKUP & RECOVERY

### Database Backup Strategy

#### Automatic Backups (Render)
- Render PostgreSQL includes automatic daily backups
- Retention: 7 days on free tier, 30 days on paid
- Access: Dashboard → PostgreSQL → Backups

#### Manual Backup
```bash
# Create backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Compress
gzip backup_$(date +%Y%m%d).sql
```

#### Restore from Backup
```bash
# Drop and recreate database (DESTRUCTIVE)
psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Restore
gunzip -c backup_20251225.sql.gz | psql $DATABASE_URL
```

### Critical Data to Backup

| Table | Priority | Frequency |
|-------|----------|-----------|
| `autonomous_positions` | HIGH | Daily |
| `autonomous_closed_trades` | HIGH | Daily |
| `bot_decision_logs` | MEDIUM | Weekly |
| `strategy_stats` | HIGH | After each trade |
| `spx_wheel_positions` | HIGH | Daily |

### Recovery Procedures

**Scenario: Database Corruption**
1. Stop all trading (set `TRADING_ENABLED=false`)
2. Restore from latest backup
3. Verify data integrity: `SELECT COUNT(*) FROM each_table`
4. Resume trading

**Scenario: Wrong Trade Executed**
1. Do NOT modify database directly
2. Create offsetting trade in broker
3. Add correcting entry to `autonomous_closed_trades`
4. Document in `notes` field

---

## 📊 MONITORING & ALERTING

### Health Check Endpoints

| Endpoint | What it Monitors | Alert If |
|----------|------------------|----------|
| `GET /health` | Server + DB | Status ≠ "healthy" |
| `GET /api/trader/status` | Trader state | status = "ERROR" |
| `GET /api/gex/SPY` | Data pipeline | net_gex = null |

### Key Metrics to Monitor

#### Trading Metrics
- **Open positions count** - Alert if > 10 (unusual)
- **Daily P&L** - Alert if < -$500 (significant loss)
- **Win rate (rolling 20)** - Alert if < 40% (strategy degradation)
- **Time since last trade** - Alert if > 48 hours (may be stuck)

#### System Metrics
- **API response time** - Alert if > 5 seconds
- **Error rate** - Alert if > 5% of requests
- **Database connections** - Alert if > 80% pool used
- **Memory usage** - Alert if > 80% of limit

### Setting Up Alerts

**Render Monitoring:**
1. Dashboard → Metrics → Enable
2. Set alert thresholds for CPU, Memory, Response Time

**External Monitoring (Recommended):**
```bash
# Simple uptime check with cron
*/5 * * * * curl -f https://your-app.onrender.com/health || echo "AlphaGEX DOWN" | mail -s "ALERT" you@email.com
```

**Slack Webhook Integration:**
```python
# In monitoring/alerts_system.py
def send_slack_alert(message: str, level: str = "warning"):
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    requests.post(webhook_url, json={
        "text": f":{level}: AlphaGEX Alert: {message}"
    })
```

---

## ⏱️ RATE LIMITS

### External API Rate Limits

| API | Limit | Period | Handling |
|-----|-------|--------|----------|
| Trading Volatility | 100 requests | Per minute | Cache for 60s |
| Polygon.io (Free) | 5 requests | Per minute | Cache for 60s |
| Polygon.io (Paid) | Unlimited | - | No caching needed |
| Tradier (Sandbox) | 120 requests | Per minute | Batch requests |
| Tradier (Live) | 120 requests | Per minute | Batch requests |

### Rate Limit Handling

```python
# In data/rate_limiter.py
class RateLimiter:
    def __init__(self, calls_per_minute: int):
        self.calls_per_minute = calls_per_minute
        self.calls = []

    def wait_if_needed(self):
        now = time.time()
        # Remove calls older than 1 minute
        self.calls = [c for c in self.calls if now - c < 60]

        if len(self.calls) >= self.calls_per_minute:
            sleep_time = 60 - (now - self.calls[0])
            time.sleep(sleep_time)

        self.calls.append(now)
```

### Caching Strategy

| Data Type | Cache Duration | Reason |
|-----------|----------------|--------|
| GEX data | 60 seconds | Updates every minute |
| VIX level | 30 seconds | Changes frequently |
| Option quotes | 5 seconds | Real-time needed |
| Strategy stats | 1 hour | Only changes on trade close |

---

## 🔧 ERROR RECOVERY

### Error Categories

#### Level 1: Transient Errors (Auto-Retry)
| Error | Cause | Recovery |
|-------|-------|----------|
| Network timeout | Slow connection | Retry 3x with exponential backoff |
| 429 Too Many Requests | Rate limit hit | Wait and retry after `Retry-After` |
| 503 Service Unavailable | API maintenance | Retry after 30 seconds |

```python
# Auto-retry logic
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((Timeout, ConnectionError))
)
def fetch_gex_data(symbol: str):
    return trading_vol_api.get_gex(symbol)
```

#### Level 2: Data Errors (Fallback)
| Error | Cause | Recovery |
|-------|-------|----------|
| Missing GEX data | API subscription issue | Use last known value + flag |
| Invalid price | Market closed | Use previous close |
| VIX unavailable | Polygon issue | Use default VIX=18 + flag |

#### Level 3: Critical Errors (Alert + Stop)
| Error | Cause | Recovery |
|-------|-------|----------|
| Database connection lost | DB down | Stop trading, alert, wait |
| Broker API down | Tradier outage | Stop trading, alert |
| Negative Kelly | Strategy losing | Block strategy, review |

### Recovery Runbook

**Scenario: API Returns Empty Data**
```
1. Check: Is market open? (if closed, expected)
2. Check: API key valid? (test in Postman)
3. Check: API status page for outages
4. Action: If temporary, use cached data with "estimated" flag
5. Action: If prolonged, switch to fallback provider or disable feature
```

**Scenario: Trade Execution Failed**
```
1. Check: Order ID in broker dashboard
2. Check: Was order rejected? (insufficient funds, invalid symbol)
3. Check: Was order filled but confirmation lost?
4. Action: If unfilled, log as SKIP with reason
5. Action: If filled but not recorded, manually add to database
6. Action: Never retry order submission automatically
```

**Scenario: Strategy Win Rate Dropping**
```
1. Check: strategy_stats table for recent trades
2. Check: Were losses due to market regime change?
3. Check: Is backtest still valid for current conditions?
4. Action: If win_rate < 40% over 10 trades, pause strategy
5. Action: Run new backtest with recent data
6. Action: Re-enable only if expectancy > 0
```

---

## 🔧 NEXT STEPS

1. **Run verification script** - Test all endpoints on Render
2. **Review backtest data** - Are there enough real trades?
3. **Check strategy stats** - Do they match reality?
4. **Remove SPX duplicate** - Delete spx_institutional_trader.py
5. **Add critical tests** - Cover the mixins
6. **Clean bare excepts** - Specific exception handling
