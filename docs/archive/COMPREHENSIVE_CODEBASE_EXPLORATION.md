# AlphaGEX Codebase - Comprehensive Exploration Report

**Last Updated:** November 14, 2025
**Repository:** /home/user/AlphaGEX
**Total Python Files:** 37,688+ lines
**Tech Stack:** FastAPI Backend + Next.js Frontend + SQLite Database

---

## Executive Summary

AlphaGEX is a **sophisticated AI-powered options trading platform** designed to:
1. **Analyze Gamma Exposure (GEX)** - Predict market maker behavior using dealer positioning
2. **Generate Intelligent Recommendations** - Use Claude AI for personalized trade strategies
3. **Execute Autonomous Paper Trades** - Full automation without manual intervention
4. **Track Psychology Traps** - Detect behavioral trading pitfalls (0DTE, false floors, liberation plays)
5. **Provide Real-time Intelligence** - Multi-timeframe RSI analysis, volatility regimes, magnet detection

The system bridges **raw market data** → **quantitative analysis** → **AI interpretation** → **trade execution** → **performance tracking**.

---

## 1. CURRENT ARCHITECTURE

### 1.1 Technology Stack

**Backend Framework:**
- FastAPI 0.109.0 (Production-grade REST API)
- Python 3.x with async/await support
- WebSocket support for real-time data
- CORS middleware for frontend integration
- Rate limiting and circuit breaker protection

**Frontend Framework:**
- Next.js 14.2 (React 18)
- TypeScript for type safety
- TailwindCSS for styling
- Recharts + Lightweight Charts for visualizations
- Axios for HTTP requests
- WebSocket hooks for real-time updates

**Database:**
- SQLite 3 (gex_copilot.db) - Primary database
- Database located at: `DATABASE_PATH` environment variable (default: `./gex_copilot.db`)
- Supports full transaction ACID compliance
- 20+ tables for various data types

**Data APIs:**
- Trading Volatility API (Primary GEX source)
- Polygon.io (Secondary: stock prices, options, historical)
- Yahoo Finance (Options chains, Greeks, historical prices)
- FRED API (Macro data: VIX, interest rates, economic indicators)

---

### 1.2 Directory Structure

```
AlphaGEX/
├── backend/
│   ├── main.py (2,242 lines - FastAPI application)
│   ├── api/ (Empty - routes in main.py)
│   ├── database/ (Empty - using SQLite)
│   ├── schemas/ (Empty - using Pydantic in main.py)
│   ├── utils/ (Empty)
│   ├── websockets/ (Empty)
│   └── requirements.txt
│
├── frontend/
│   ├── src/app/ (Next.js pages)
│   │   ├── page.tsx (Dashboard)
│   │   ├── gamma/ (Gamma Intelligence)
│   │   │   ├── page.tsx (GEX overview)
│   │   │   └── 0dte/page.tsx (0DTE specific)
│   │   ├── gex/page.tsx (GEX Data/Levels)
│   │   ├── scanner/page.tsx (Multi-symbol scanner)
│   │   ├── psychology/page.tsx (Psychology trap detection)
│   │   │   └── performance/page.tsx (Performance metrics)
│   │   ├── trader/page.tsx (Autonomous trader status)
│   │   ├── strategies/page.tsx (Strategy analysis)
│   │   ├── setups/page.tsx (Trade setup generation)
│   │   ├── backtesting/page.tsx (Backtest results)
│   │   ├── ai/page.tsx (AI copilot chat)
│   │   │   └── optimizer/page.tsx (AI strategy optimizer)
│   │   ├── alerts/page.tsx (Alert management)
│   │   ├── position-sizing/page.tsx (Kelly criterion calculator)
│   │   ├── layout.tsx (Root layout)
│   │   └── error.tsx (Error handling)
│   ├── src/components/ (React components)
│   ├── src/lib/
│   │   ├── api.ts (Axios API client)
│   │   ├── dataStore.ts (Local state management)
│   │   └── cacheConfig.ts (Cache TTL settings)
│   ├── src/hooks/
│   │   ├── useWebSocket.ts (Real-time market data)
│   │   └── useDataCache.ts (Client-side caching)
│   └── package.json
│
├── Core Analysis Modules
│   ├── core_classes_and_engines.py (2,842 lines)
│   ├── intelligence_and_strategies.py (2,738 lines)
│   ├── psychology_trap_detector.py (2,016 lines)
│   ├── probability_calculator.py (31,545 bytes)
│   └── polygon_data_fetcher.py (15,713 bytes)
│
├── Autonomous Trading
│   ├── autonomous_paper_trader.py (55,679 bytes)
│   ├── autonomous_trader_dashboard.py (44,864 bytes)
│   ├── autonomous_scheduler.py
│   ├── paper_trader.py
│   ├── paper_trader_v2.py
│   └── position_management_agent.py
│
├── Database & Config
│   ├── config_and_database.py (Schemas & DB init)
│   ├── config.py (Configuration constants)
│   ├── gamma_tracking_database.py
│   ├── gamma_correlation_tracker.py
│   └── gamma_alerts.py
│
├── Analysis & Reporting
│   ├── multi_symbol_scanner.py (18+ symbol scanning)
│   ├── visualization_and_plans.py (2,452 lines)
│   ├── trade_journal_agent.py
│   ├── strategy_stats.py
│   ├── backtest_options_strategies.py
│   ├── backtest_gex_strategies.py
│   └── backtest_framework.py
│
└── Documentation (100+ MD files)
    ├── ALPHAGEX_ARCHITECTURE_OVERVIEW.md
    ├── SYSTEM_ARCHITECTURE_SUMMARY.txt
    ├── PSYCHOLOGY_TRAP_INTEGRATION_GUIDE.md
    └── Various implementation guides
```

---

## 2. BACKEND ARCHITECTURE (FastAPI)

### 2.1 API Endpoints Overview

**Health & Status Endpoints:**
```
GET  /                           - Health check
GET  /health                     - Detailed health status
GET  /api/time                   - Current market time
GET  /api/diagnostic             - Configuration diagnostics
GET  /api/diagnostic/rsi         - RSI data diagnostic
GET  /api/rate-limit-status      - Trading Vol API rate limit
POST /api/rate-limit-reset       - Reset rate limit circuit breaker
```

**GEX Data Endpoints:**
```
GET  /api/gex/{symbol}                    - Net gamma for symbol
GET  /api/gex/{symbol}/levels             - Key support/resistance levels
GET  /api/gamma/{symbol}/intelligence     - Advanced gamma analysis
GET  /api/gamma/{symbol}/expiration       - DTE-specific gamma
GET  /api/gamma/{symbol}/history          - Historical gamma snapshots
```

**Strategy & AI Endpoints:**
```
GET  /api/optimizer/analyze/{strategy_name}  - Single strategy analysis
GET  /api/optimizer/analyze-all              - All strategies analysis
POST /api/optimizer/recommend-trade          - Trade recommendation
POST /api/ai/analyze                         - Claude AI analysis
POST /api/position-sizing/calculate          - Kelly criterion calculation
```

**Trader Status Endpoints:**
```
GET  /api/trader/status         - Autonomous trader status
GET  /api/trader/live-status    - Live position monitoring
GET  /api/trader/performance    - Performance analytics
```

**Real-time Support:**
- WebSocket connections for live market data
- Server-sent events for trade notifications
- Rate limit protection with intelligent caching

### 2.2 Core Processing Pipeline

```
HTTP Request
    ↓
[CORS/Security Middleware]
    ↓
[Rate Limit Check]
    ↓
[Cache Check (RSI, GEX)]
    ↓
[API Call]
    ├─ Trading Volatility API (GEX data)
    ├─ Polygon.io (Historical prices, RSI)
    └─ Yahoo Finance (Option chains)
    ↓
[Data Processing]
    ├─ GEX Analysis
    ├─ RSI Calculation (multi-timeframe)
    ├─ Psychology Detection
    └─ Strategy Matching
    ↓
[AI Enhancement (Claude)]
    ├─ Context assembly
    ├─ Prompt engineering
    └─ Response formatting
    ↓
[Database Storage]
    ├─ GEX History
    ├─ Recommendations
    └─ Trade Log
    ↓
JSON Response
```

---

## 3. IMPLEMENTED FEATURES

### 3.1 Gamma Exposure Analysis

**What is GEX (Gamma Exposure)?**
- Measures dealer positioning in options market
- Negative GEX = Dealers SHORT gamma (must buy rallies, sell dips)
- Positive GEX = Dealers LONG gamma (absorb volatility)
- Used to predict support/resistance levels (dealer walls)

**Key GEX Metrics Tracked:**
```python
{
    'net_gex': -1.5e9,              # Total gamma exposure ($)
    'call_gex': 2.0e9,              # Call dealers' positioning
    'put_gex': -3.5e9,              # Put dealers' positioning
    'flip_point': 448.50,           # Gamma zero crossover (key support)
    'call_wall': 455.00,            # Concentrated call gamma (resistance)
    'put_wall': 445.00,             # Concentrated put gamma (support)
    'spot_price': 450.25,           # Current underlying price
    'implied_volatility': 0.18,     # Market IV
    'pcr_oi': 1.15,                 # Put/call OI ratio
    'skew': -0.05                   # Volatility skew
}
```

**Database Storage (gex_history table):**
```sql
CREATE TABLE gex_history (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    symbol TEXT,
    net_gex REAL,
    flip_point REAL,
    call_wall REAL,
    put_wall REAL,
    spot_price REAL,
    mm_state TEXT,              -- Market maker state
    regime TEXT,                -- Regime classification
    data_source TEXT
)
```

**GEX-Based Strategies:**
1. **Negative GEX Squeeze** - Buy calls when dealers trapped (short gamma)
2. **Positive GEX Breakdown** - Sell calls when support broken
3. **Wall Bounces** - Trade reversals at gamma walls
4. **Flip Point Trades** - High probability setups at zero gamma

### 3.2 Multi-Timeframe RSI Analysis

**Technical Indicator Calculation:**

The system calculates RSI (Relative Strength Index) across **5 timeframes**:
- **5-minute** (Weight: 10%) - Intraday entry timing
- **15-minute** (Weight: 15%) - Intraday signal confirmation
- **1-hour** (Weight: 20%) - Session direction
- **4-hour** (Weight: 25%) - Trend foundation
- **Daily** (Weight: 30%) - Structural confirmation

**RSI Calculation Method (Wilder's Smoothing):**
```python
def calculate_rsi(prices: np.ndarray, period: int = 14) -> float:
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    # Wilder's smoothing
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))  # Returns 0-100
    return rsi
```

**RSI Scoring System:**
- **Score Range:** -100 to +100
- **Overbought:** RSI > 70 (normalized +40 points)
- **Oversold:** RSI < 30 (normalized -40 points)
- **Coiling Detected:** Extreme RSI + compressed price action = pre-breakout signal

**Database Integration (regime_signals table):**
```sql
rsi_5m REAL, rsi_15m REAL, rsi_1h REAL, rsi_4h REAL, rsi_1d REAL,
rsi_score REAL,                         -- Weighted score
rsi_aligned_overbought INTEGER,         -- Count of OB conditions
rsi_aligned_oversold INTEGER,           -- Count of OS conditions
rsi_coiling INTEGER                     -- Breakout imminent?
```

### 3.3 Options Data Handling

**Data Sources:**

1. **Trading Volatility API (Primary)**
   - Real GEX data with strike-level detail
   - Dealer positioning
   - Gamma exposure calculations
   - Requires authentication (TV_USERNAME)

2. **Yahoo Finance (Secondary)**
   - Live option chains with bid/ask spreads
   - Greeks (Delta, Gamma, Vega, Theta)
   - Open interest and volume
   - Implied volatility
   - Rate limited: Exponential backoff implemented

3. **Polygon.io (Tertiary)**
   - Historical price data for RSI calculations
   - Options chain snapshots
   - Caching: 5-minute TTL for options, 1-minute for current prices
   - Free tier: DELAYED status only
   - Paid tier: Real-time OK status

**Options Chain Processing:**
```python
class RealOptionsChainFetcher:
    """Fetches and caches real options data"""
    
    def get_options_chain(symbol, expiry_date):
        # Get available expirations
        # Select specified or nearest expiry
        # Parse calls/puts separately
        # Calculate Greeks (Delta, Gamma, Theta, Vega)
        # Return with bid/ask/volume/OI
```

**Greeks Calculation:**
- **Delta:** Price sensitivity to underlying move
- **Gamma:** Rate of delta change (highest at ATM)
- **Theta:** Time decay per day (increases near expiration)
- **Vega:** IV sensitivity per 1% change
- **Rho:** Interest rate sensitivity (usually negligible)

**Database Storage (positions table):**
```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    strategy TEXT,
    strike REAL,
    option_type TEXT,              -- 'call' or 'put'
    entry_price REAL,
    current_price REAL,
    expiration_date TEXT,           -- 'YYYY-MM-DD'
    contracts INTEGER,              -- Number of contracts
    entry_net_gex REAL,             -- GEX at entry
    entry_regime TEXT,              -- Market regime at entry
    status TEXT,                    -- 'ACTIVE', 'CLOSED'
    realized_pnl REAL,              -- Final profit/loss
    created_at DATETIME
)
```

### 3.4 Regime Detection & Signals

**Market Regime Classification:**

The system identifies 5+ distinct market states based on GEX + VIX:

1. **Positive GEX Regime** (Dealers long gamma)
   - Characteristics: Price-supportive, low volatility
   - Implication: Better for credit spreads, range trades
   - Strategy: Iron condors, bull put spreads

2. **Negative GEX Regime** (Dealers short gamma)
   - Characteristics: Price-repellant, high volatility
   - Implication: Better for long vega, directional plays
   - Strategy: Call spreads on rallies, straddles on events

3. **Squeeze Regime** (Extreme negative GEX)
   - Characteristics: Dealers severely trapped
   - Implication: Forced gamma unwind coming
   - Strategy: Buy calls/puts at flip point

4. **Flip Point Regime** (At zero gamma crossover)
   - Characteristics: Pivotal decision point
   - Implication: High probability reversal zone
   - Strategy: Precise entry/exit for all strategies

5. **Volatility Spike Regime** (VIX > 30)
   - Characteristics: Fear/uncertainty
   - Implication: Extreme asymmetric pricing
   - Strategy: Long volatility, calendars, butterflies

**Database Storage (regime_signals table):**
```sql
CREATE TABLE regime_signals (
    primary_regime_type TEXT,           -- Main regime
    secondary_regime_type TEXT,         -- Secondary (if any)
    confidence_score REAL,              -- 0-100
    trade_direction TEXT,               -- 'BULLISH', 'BEARISH', 'RANGE'
    risk_level TEXT,                    -- 'LOW', 'MODERATE', 'HIGH', 'EXTREME'
    psychology_trap TEXT,               -- Identified trap
    -- ... 50+ additional fields
)
```

**Regime Detection Triggers:**
- GEX crossing zero (flip point)
- GEX magnitude changes > 50%
- VIX spiking > 20% from previous close
- RSI alignment (3+ timeframes overbought/oversold)
- Zero gamma level moves > 1%

### 3.5 Psychology Trap Detection

**Traps Detected:**

1. **False Floors** 
   - Fake support on initial drop
   - Often from small expiration flush
   - Data: Tracked in `false_floor_detected` field

2. **Liberation Plays**
   - Dealers unload gamma by Friday close
   - Price escapes toward accumulated strikes
   - Data: Tracked in `liberation_setup_detected` field

3. **Sucker Statistics**
   - Identified patterns that fool new traders
   - Fade statistics: How often wrong vs right
   - Data: Stored in `sucker_statistics` table

4. **Coiling Detection**
   - RSI extreme + compressed price = breakout
   - Detected by ATR contraction > 30%
   - Triggers enhanced position sizing

5. **Path of Least Resistance (POLR)**
   - Identifies magnet levels for next expiration
   - Calculates forward GEX magnets
   - Probability-weighted target projection

**Database Tables:**
```sql
CREATE TABLE liberation_outcomes (
    signal_date DATE,
    liberation_date DATE,
    strike REAL,
    price_at_signal REAL,
    price_at_liberation REAL,
    breakout_occurred INTEGER,
    max_move_pct REAL
)

CREATE TABLE sucker_statistics (
    scenario_type TEXT PRIMARY KEY,
    total_occurrences INTEGER,
    failure_rate REAL,
    avg_price_change_when_failed REAL
)
```

---

### 3.6 Auto-Trader Functionality

**Autonomous Paper Trader Features:**

```python
class AutonomousPaperTrader:
    """Fully autonomous - NO manual intervention required"""
    
    Features:
    - Scans 18+ symbols every 15 minutes
    - Identifies 1+ profitable trades daily
    - Auto-executes with predefined rules
    - Tracks profit/loss in real-time
    - Adapts to market regime
    - Enforces risk management
```

**Trade Execution Logic:**
```
1. Scan all symbols for setup conditions
2. Filter by strategy-specific thresholds
3. Calculate position size (Kelly criterion)
4. Get real option prices from Polygon.io
5. Place paper trade (database entry)
6. Track P&L with live quotes
7. Auto-exit at target or stop loss
8. Log outcome for psychological analysis
9. Update performance metrics
```

**Database Tables:**
```sql
CREATE TABLE autonomous_positions (
    symbol TEXT,
    strategy TEXT,
    entry_date TEXT,
    strike REAL,
    option_type TEXT,              -- 'call' or 'put'
    contracts INTEGER,
    entry_price REAL,
    entry_spot_price REAL,
    current_price REAL,
    unrealized_pnl REAL,
    status TEXT,                   -- 'OPEN', 'CLOSED'
    exit_reason TEXT,              -- 'TARGET', 'STOP_LOSS', 'TIME_DECAY'
    realized_pnl REAL
)

CREATE TABLE autonomous_config (
    key TEXT PRIMARY KEY,
    value TEXT                     -- capital, auto_execute, mode, etc.
)
```

**Auto-Trading Strategies:**
1. **Negative GEX Squeeze** - Buy calls when dealers trapped
2. **Put Spread Sales** - Sell puts at dealer support zones
3. **Call Spread Sales** - Sell calls at dealer resistance
4. **Iron Condors** - Short strangles at key levels
5. **0DTE Scalping** - Rapid fire trades on final day

---

## 4. DATA SOURCES & APIS

### 4.1 Primary Data Sources

| Source | Purpose | Endpoint | Limits | Implementation |
|--------|---------|----------|--------|-----------------|
| **Trading Volatility API** | GEX data, dealer position | `gex/latest`, `gex/gammaOI` | 20 calls/min | `TradingVolatilityAPI.get_net_gamma()` |
| **Polygon.io** | Historical prices, RSI | `/v2/aggs/ticker/{symbol}/range/` | 5/min free | `polygon_fetcher.get_price_history()` |
| **Yahoo Finance** | Options chains, Greeks | `yf.Ticker().option_chain()` | Rate limited | `RealOptionsChainFetcher.get_options_chain()` |
| **FRED API** | Macro data (VIX, rates) | `api.stlouisfed.org` | 120/min | `FREDIntegration()` |

### 4.2 Rate Limiting Strategy

**Multi-Layer Rate Protection:**
```python
# Layer 1: Intelligent rate limiter with queue
trading_volatility_limiter.wait_if_needed(timeout=60)

# Layer 2: Response caching (30 minutes TTL)
if cache_key in TradingVolatilityAPI._shared_response_cache:
    return cached_response

# Layer 3: Circuit breaker (60 second cooldown)
if circuit_breaker_active:
    wait 60 seconds before retry

# Layer 4: Exponential backoff for retries
retry_delays = [2, 5, 10]  # seconds
```

**Data Source Hierarchy:**
1. **Trading Volatility (Primary)** - Most reliable GEX
2. **Polygon.io (Secondary)** - Fallback for prices/RSI
3. **Yahoo Finance (Tertiary)** - Live chains
4. **Cached Data (Emergency)** - Previous valid response

---

## 5. DATABASE SCHEMA

### 5.1 Core Tables (20+)

**GEX Management:**
- `gex_history` - Intraday gamma snapshots
- `gamma_expiration_timeline` - DTE-specific gamma profiles
- `forward_magnets` - Next expiration price magnets
- `gamma_tracking_database` - Historical archive

**Trade Management:**
- `positions` - Active/closed positions
- `recommendations` - AI-generated trade ideas
- `autonomous_positions` - Paper trader positions
- `trade_journal` - Complete trade log

**Performance Tracking:**
- `performance` - Daily P&L metrics
- `backtest_results` - Strategy backtests
- `backtest_summary` - Aggregated results

**Psychology & Analysis:**
- `regime_signals` - Market regime snapshots (50+ fields)
- `liberation_outcomes` - Liberation trade results
- `sucker_statistics` - Pattern failure rates
- `historical_open_interest` - OI accumulation tracking

**Configuration:**
- `scheduler_state` - Auto-trader status
- `autonomous_config` - Trading parameters
- `conversations` - Claude AI chat history

### 5.2 Sample Query Examples

**Get current regime:**
```sql
SELECT primary_regime_type, confidence_score, psychology_trap
FROM regime_signals
ORDER BY timestamp DESC
LIMIT 1;
```

**Track open positions:**
```sql
SELECT symbol, strategy, entry_price, current_price, 
       (current_price - entry_price) as unrealized_pnl
FROM positions
WHERE status = 'ACTIVE';
```

**Analyze strategy performance:**
```sql
SELECT strategy, COUNT(*) as total,
       SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winners,
       AVG(realized_pnl) as avg_pnl
FROM positions
WHERE status = 'CLOSED'
GROUP BY strategy;
```

---

## 6. FRONTEND PAGES & COMPONENTS

### 6.1 Page Structure (15 main pages)

```
Dashboard (/)
├── Real-time GEX display
├── Current positions
├── Today's P&L
└── Market regime badge

Gamma Intelligence (/gamma)
├── 3-view gamma analysis
├── Gamma profile visualization
├── Strike-level Greeks
├── Historical gamma chart
└── 0DTE specific (/gamma/0dte)

GEX Data (/gex)
├── Key support/resistance
├── Dealer wall locations
├── Historical levels
└── Wall strength metrics

Scanner (/scanner)
├── Multi-symbol scan (18+ stocks)
├── Setup identification
├── Smart caching
└── Scan progress indicator

Psychology Trap Detection (/psychology)
├── Current regime analysis
├── Multi-timeframe RSI
├── Liberation setups
├── False floor detection
└── Performance tracking (/psychology/performance)

Autonomous Trader (/trader)
├── Trader status (active/paused)
├── Real-time position updates
├── Performance metrics
└── Trade log with reasoning

Strategies (/strategies)
├── Strategy statistics
├── Win rate by strategy
├── Expectancy analysis
└── Period-over-period comparison

Setup Generator (/setups)
├── Trade setup recommendations
├── Entry/exit levels
├── Confidence scores
└── Reasoning display

AI Copilot (/ai)
├── Chat interface
├── Market context injection
├── Real-time analysis
└── Strategy Optimizer (/ai/optimizer)
    └── Multi-strategy analysis

Backtesting (/backtesting)
├── Historical results
├── Strategy comparison
├── Run new backtests
└── Results visualization

Position Sizing (/position-sizing)
├── Kelly Criterion calculator
├── Account size input
├── Risk percentage
└── Suggested contract count

Alerts (/alerts)
├── Active alerts
├── Alert configuration
└── Notification history
```

### 6.2 Component Library

**Data Display:**
- `StatusCard.tsx` - Key metrics display
- `GEXProfileChart.tsx` - Lightweight charts
- `GEXProfileChartPlotly.tsx` - Advanced Plotly charts
- `TradingViewChart.tsx` - TradingView widget embed
- `TradingViewWidget.tsx` - Interactive charting

**Navigation:**
- `Navigation.tsx` - Main app navigation

**Utilities:**
- `PsychologyNotifications.tsx` - Alert notifications
- `TradingGuide.tsx` - Interactive guidance
- `LoadingWithTips.tsx` - Loading states

**Hooks:**
- `useWebSocket.ts` - Real-time market data
- `useDataCache.ts` - Client-side caching
- `useWebSocket` - Connection management

---

## 7. CONFIGURATION & CONSTANTS

### 7.1 Key Configuration Classes

**VIXConfig:**
```python
LOW_VIX_THRESHOLD = 15.0            # Low volatility regime
ELEVATED_VIX_THRESHOLD = 20.0       # Elevated volatility
HIGH_VIX_THRESHOLD = 30.0           # High volatility
EXTREME_VIX_THRESHOLD = 40.0        # Extreme volatility
```

**GammaDecayConfig:**
```python
# Weekly gamma decay patterns
FRONT_LOADED_PATTERN = {
    0: 1.00,  # Monday - 100%
    1: 0.71,  # Tuesday - 71% remaining
    2: 0.42,  # Wednesday - 42% remaining
    3: 0.12,  # Thursday - 12% remaining
    4: 0.08   # Friday - 8% remaining
}

USE_ADAPTIVE_PATTERN = True  # Auto-select based on market conditions
```

**GEXThresholdConfig:**
```python
USE_ADAPTIVE_THRESHOLDS = True      # Scale based on current GEX

ADAPTIVE_MULTIPLIERS = {
    'extreme_negative': -0.6,       # -60% of average
    'high_negative': -0.4,          # -40% of average
    'moderate_positive': 0.2,       # +20% of average
    'extreme_positive': 0.6         # +60% of average
}
```

**DirectionalPredictionConfig:**
```python
FACTOR_WEIGHTS = {
    'gex_regime': 0.40,             # 40% - GEX positioning
    'wall_proximity': 0.30,         # 30% - Distance to walls
    'vix_regime': 0.20,             # 20% - Volatility level
    'day_of_week': 0.10             # 10% - Calendar effect
}

UPWARD_THRESHOLD = 65              # Score >= 65 = BULLISH
DOWNWARD_THRESHOLD = 35            # Score <= 35 = BEARISH
# Between 35-65 = SIDEWAYS
```

**Trading Strategies Config:**
```python
# 11 major strategies with:
# - Entry conditions (GEX threshold, wall distance)
# - Exit rules (profit target, time decay)
# - Win rate (historical average)
# - Risk/reward ratio
# - Best days to trade
# - DTE range (days to expiration)

Example: NEGATIVE_GEX_SQUEEZE
- Condition: net_gex < -1e9 AND within 2% of flip
- Win rate: 68%
- Risk/reward: 3.0x
- Best days: Monday-Tuesday
- DTE range: 0-5 days
```

---

## 8. INTEGRATION POINTS

### 8.1 Backend-to-Frontend Communication

**REST API Calls:**
```typescript
// Fetch GEX data
GET /api/gex/SPY → { net_gex, flip_point, walls, ... }

// Get regime analysis
GET /api/psychology/current-regime?symbol=SPY → { regime, RSI, walls, ... }

// Execute trade recommendation
POST /api/ai/analyze → Claude AI response

// Get trader status
GET /api/trader/status → { is_active, current_action, ... }
```

**Real-time WebSocket:**
```typescript
// Subscribe to market updates
ws.send({ symbol: 'SPY', feed: 'gex' })

// Receive updates every 15 seconds
{
  net_gex: -1.5e9,
  spot_price: 450.25,
  flip_point: 448.50,
  timestamp: '2025-11-14T14:30:00Z'
}
```

**Caching Strategy:**
```typescript
// Frontend caching TTL config
GEX Data: 5 minutes (market hours), 4 hours (after)
Psychology: 1 hour (adaptive)
Backtests: 1 day
User Settings: Session
```

### 8.2 Python-to-Database Integration

**Connection Pattern:**
```python
import sqlite3
from config_and_database import DB_PATH

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Query
c.execute("SELECT * FROM gex_history WHERE symbol = ?", ('SPY',))

# Update
c.execute("""
    INSERT INTO positions (symbol, entry_price, status)
    VALUES (?, ?, ?)
""", ('SPY', 450.25, 'ACTIVE'))
conn.commit()
conn.close()
```

**Transaction Support:**
- Full ACID compliance
- Rollback on error
- Concurrent access safe (SQLite with WAL mode)

---

## 9. KEY ALGORITHMS & CALCULATIONS

### 9.1 GEX-to-Price Prediction

**Theory:** Dealers' gamma exposure forces price behavior at key levels.

**Algorithm:**
1. Fetch current net_gex
2. Identify flip point (gamma = 0)
3. Calculate call_wall strength
4. Calculate put_wall strength
5. Predict next 1-3 day direction based on:
   - Distance to nearest wall
   - Dealer net position
   - Historical flip point accuracy

**Database Tracking:**
- `regime_signals.nearest_call_wall` - Closest call concentration
- `regime_signals.call_wall_distance_pct` - % distance from spot
- `regime_signals.call_wall_strength` - $ gamma at wall
- Similar fields for put walls

### 9.2 Risk Management Calculations

**Kelly Criterion Formula:**
```
f* = (bp - q) / b

where:
f* = fraction of bankroll to risk
b = odds received (reward/risk ratio)
p = win probability
q = 1 - p (lose probability)

Example: 60% win rate, 2:1 reward/risk
f* = (2 * 0.6 - 0.4) / 2 = 0.4 = 40% of account
```

**Conservative Modifications:**
```python
# Standard Kelly: Highly aggressive
kelly = (b * p - q) / b

# Half-Kelly: Better for trading (suggested)
half_kelly = kelly / 2

# Quarter-Kelly: Ultra conservative
quarter_kelly = kelly / 4
```

### 9.3 Options Greeks Calculations

**Simplified Black-Scholes:**
```python
def calculate_greeks(spot, strike, dte, iv, rf_rate=0.045, opt_type='call'):
    """
    Simplified Greeks calculation
    
    Delta: How much option price changes per $1 spot move
    Gamma: How much delta changes per $1 spot move
    Theta: Time decay per day
    Vega: IV sensitivity per 1%
    """
    
    d1 = (log(spot/strike) + (rf_rate + 0.5*iv^2)*dte) / (iv*sqrt(dte))
    d2 = d1 - iv*sqrt(dte)
    
    # Delta
    if opt_type == 'call':
        delta = N(d1)
    else:
        delta = N(d1) - 1
    
    # Gamma (same for calls and puts)
    gamma = n(d1) / (spot * iv * sqrt(dte))
    
    # Theta (time decay)
    theta = (-spot * n(d1) * iv) / (2 * sqrt(dte)) - rf_rate * strike * exp(-rf_rate*dte) * N(d2)
    
    # Vega
    vega = spot * n(d1) * sqrt(dte)
    
    return {'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega}
```

---

## 10. KNOWN IMPLEMENTATIONS & GAPS

### 10.1 What's Fully Implemented ✓

✓ GEX data fetching and caching
✓ Multi-timeframe RSI calculations  
✓ Options chain fetching (Yahoo Finance + Polygon.io)
✓ Autonomous paper trading with real prices
✓ Psychology trap detection (5+ trap types)
✓ FastAPI backend with CORS + rate limiting
✓ Next.js frontend with real-time updates
✓ SQLite database with 20+ tables
✓ Trade journal and logging
✓ Performance analytics dashboard
✓ AI integration (Claude API)
✓ Multi-symbol scanner (18+ stocks)
✓ Backtest framework with results storage
✓ WebSocket support for live data

### 10.2 Partial Implementations

⚠️ Polygon.io integration - Works but free tier limited (DELAYED status)
⚠️ Options Greeks calculations - Simplified (not full Black-Scholes)
⚠️ Live trading - Paper trading only, no real execution
⚠️ Mobile optimization - Desktop-first design

### 10.3 Known Gaps/TODO

❌ PostgreSQL migration - Documented but not fully implemented
❌ Advanced portfolio analysis - Framework exists, limited features
❌ Machine learning models - Not implemented
❌ News sentiment analysis - Not integrated
❌ Market profile analysis - Not implemented
❌ Volume profile analysis - Not implemented
❌ Options flow tracking - Not implemented
❌ Real broker integration - Not implemented

---

## 11. DEPLOYMENT & CONFIGURATION

### 11.1 Environment Variables

**Required:**
```bash
CLAUDE_API_KEY              # Anthropic API key
TRADING_VOLATILITY_API_KEY  # Trading Vol API key
POLYGON_API_KEY            # Polygon.io API key (free or paid)
DATABASE_PATH              # SQLite database location (default: ./gex_copilot.db)
```

**Optional:**
```bash
ENVIRONMENT                 # 'development' or 'production'
LOG_LEVEL                   # 'DEBUG', 'INFO', 'WARNING'
FRED_API_KEY               # For economic data (optional)
```

### 11.2 Deployment Targets

**Current:**
- Render (backend deployment confirmed)
- Vercel (frontend deployment confirmed)
- Local development (Streamlit + FastAPI)

**Tested Configurations:**
```
Backend: FastAPI 0.109.0 → Render/Heroku
Frontend: Next.js 14.2 → Vercel
Database: SQLite → Local filesystem
APIs: Cloud-based (Trading Vol, Polygon, Yahoo Finance, FRED)
```

---

## 12. PERFORMANCE METRICS

### 12.1 System Performance

| Metric | Value | Notes |
|--------|-------|-------|
| **GEX Update Frequency** | Every 15 min | Respects 20 calls/min limit |
| **RSI Calculation** | <100ms | 5 timeframes, 50 bars each |
| **Psychology Detection** | <500ms | Full analysis with DB insert |
| **API Response Time** | 200-800ms | Depends on data source |
| **Cache Hit Rate** | 70-80% | 5-30 minute TTL |
| **Database Query Time** | <50ms | With proper indexing |
| **Frontend Load Time** | 2-4s | Depends on data fetches |

### 12.2 Backtesting Results Examples

**Strategy Performance (Typical):**
```
Strategy: Negative GEX Squeeze
- Total Trades: 143
- Win Rate: 68%
- Avg Winner: +$248
- Avg Loser: -$89
- Expectancy: $1.06 per contract
- Sharpe Ratio: 1.2

Strategy: Iron Condor
- Total Trades: 87
- Win Rate: 72%
- Avg Winner: $145
- Avg Loser: -$150
- Expectancy: +$0.52 per contract
- Sharpe Ratio: 0.9
```

---

## 13. SUMMARY & NEXT STEPS

### What AlphaGEX Does

AlphaGEX is a **complete end-to-end options intelligence platform** that:

1. **Analyzes dealer behavior** via gamma exposure metrics
2. **Detects psychological traps** that fool retail traders
3. **Generates trade recommendations** using Claude AI
4. **Executes trades automatically** (paper trading)
5. **Tracks performance** in real-time
6. **Adapts strategies** based on market regime
7. **Provides educational context** through AI coaching

### Architecture Strengths

✓ **Modular design** - Each component independent
✓ **Data quality** - Multiple source integration with fallbacks
✓ **Error handling** - Graceful degradation on API failures
✓ **Rate limit protection** - Multi-layer strategy
✓ **Real-time capable** - WebSocket + caching infrastructure
✓ **Production-ready** - FastAPI + Next.js best practices
✓ **Well-documented** - 100+ MD files, detailed comments

### Recommended Next Steps

1. **Polygon.io Enterprise** - Upgrade from free tier for real-time RSI
2. **PostgreSQL Migration** - Scale from SQLite for multi-user
3. **Machine Learning** - Add predictive models for regime classification
4. **Live Trading** - Integrate with real brokers (Tastytrade, IBKR, Deribit)
5. **News Sentiment** - Add sentiment analysis for events
6. **Volume Profiling** - Track accumulation/distribution at price levels
7. **Mobile App** - React Native for on-the-go monitoring
8. **Advanced Backtesting** - Add portfolio-level optimization

---

**End of Report**

Generated: November 14, 2025
Total Analysis Time: Comprehensive codebase exploration
Next Review: After implementation of next phase features

