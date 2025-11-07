# AlphaGEX Architecture & Codebase Overview

## Executive Summary

AlphaGEX is a sophisticated **AI-powered options trading platform** that combines:
- **Gamma Exposure (GEX) Analysis** - Predicts Market Maker behavior
- **Claude AI Integration** - Intelligent trade recommendations and psychological coaching
- **Real-time Market Data** - Trading Volatility API + Yahoo Finance
- **Autonomous Paper Trading** - Full automation with zero manual intervention
- **Professional FastAPI Backend** - Production-ready REST API with WebSocket support

---

## 1. PROJECT STRUCTURE

```
AlphaGEX/
├── backend/
│   └── main.py (2,696 lines - FastAPI application)
│
├── frontend/
│   ├── src/
│   │   ├── app/ (Next.js pages)
│   │   │   ├── page.tsx (Dashboard)
│   │   │   ├── gamma/ (Gamma Intelligence)
│   │   │   ├── gex/ (GEX Data)
│   │   │   ├── trader/ (Autonomous Trader)
│   │   │   ├── scanner/ (Multi-Symbol Scanner)
│   │   │   ├── setups/ (Trade Setups)
│   │   │   ├── strategies/ (Strategy Analysis)
│   │   │   ├── ai/ (AI Copilot Chat)
│   │   │   ├── alerts/ (Alert Management)
│   │   │   └── position-sizing/ (Position Sizing)
│   │   ├── components/ (React Components)
│   │   │   ├── GEXProfileChart.tsx
│   │   │   ├── GEXProfileChartPlotly.tsx
│   │   │   ├── TradingViewChart.tsx
│   │   │   ├── Navigation.tsx
│   │   │   └── StatusCard.tsx
│   │   ├── lib/
│   │   │   ├── api.ts (Axios HTTP client)
│   │   │   └── dataStore.ts
│   │   └── hooks/
│   │       ├── useWebSocket.ts (Real-time market data)
│   │       └── useDataCache.ts (Caching layer)
│   └── package.json (Next.js 14 + React 18 + Recharts + TailwindCSS)
│
├── Core Python Modules (2,842-2,738 lines each)
│   ├── core_classes_and_engines.py
│   │   ├── TradingVolatilityAPI (GEX data fetching)
│   │   ├── OptionsDataFetcher (Yahoo Finance)
│   │   ├── GEXAnalyzer (Gamma calculations)
│   │   ├── TradingStrategy (Strategy selection)
│   │   ├── MarketRegimeAnalyzer (Volatility states)
│   │   ├── RiskManager (Position sizing)
│   │   ├── MonteCarloEngine (Simulations)
│   │   └── BlackScholesPricer (Greeks calculations)
│   │
│   └── intelligence_and_strategies.py
│       ├── ClaudeIntelligence (AI analysis, 1,700+ lines)
│       ├── RealOptionsChainFetcher (Live option prices)
│       ├── GreeksCalculator (Delta, Gamma, Vega, Theta)
│       ├── PositionSizingCalculator (Kelly Criterion)
│       ├── PsychologicalCoach (Red flag detection)
│       ├── PostMortemAnalyzer (Trade review)
│       ├── TradingRAG (Retrieval-Augmented Generation)
│       ├── SmartDTECalculator (DTE optimization)
│       └── Utility functions (Time zones, market hours)
│
├── Database & Configuration
│   ├── config_and_database.py
│   │   ├── MM_STATES (5 market maker states)
│   │   └── STRATEGIES (4 core trading strategies)
│   │
│   ├── gamma_tracking_database.py (GEX history storage)
│   ├── gamma_alerts.py (Alert system)
│   ├── alerts_system.py (Notifications)
│   └── gex_copilot.db (SQLite - main database)
│
├── Autonomous Trading
│   ├── autonomous_paper_trader.py (Full auto-execution)
│   ├── autonomous_trader_dashboard.py (Performance tracking)
│   ├── autonomous_scheduler.py (Cloud task scheduling)
│   ├── paper_trader_v2.py (Paper trading with real prices)
│   └── position_management_agent.py (P&L tracking)
│
├── Analysis & Planning
│   ├── multi_symbol_scanner.py (Scan 18+ symbols)
│   ├── visualization_and_plans.py (Daily game plans)
│   ├── trade_journal_agent.py (Trade logging)
│   ├── position_sizing.py (Kelly Criterion)
│   └── langchain_intelligence.py (LangChain integration)
│
└── Documentation
    ├── ALPHAGEX_COMPREHENSIVE_ANALYSIS.md (Architecture)
    ├── CODEBASE_QUICK_REFERENCE.md (Quick guide)
    └── Various implementation guides
```

---

## 2. CURRENT GAMMA EXPOSURE IMPLEMENTATION

### Data Sources

| Source | Purpose | Implementation |
|--------|---------|-----------------|
| **Trading Volatility API** | GEX data (net_gex, flip_point, walls) | `TradingVolatilityAPI` class |
| **Yahoo Finance** | Real-time option prices, Greeks, IV | `RealOptionsChainFetcher` class |
| **FRED API** | Macro context (VIX, yields, rates) | `FREDIntegration` in intelligence_and_strategies.py |
| **SQLite Database** | Historical GEX, trades, alerts | `gamma_tracking_database.py` |

### GEX Data Model

**Trading Volatility API Response** (HTTP GET `/api/gex/{symbol}`):
```python
{
    'symbol': 'SPY',
    'spot_price': 450.25,
    'net_gex': -1.5e9,              # Negative = dealers SHORT gamma
    'flip_point': 448.50,           # Gamma zero crossover
    'call_wall': 455.00,            # Call concentration
    'put_wall': 445.00,             # Put concentration
    'call_gex': 2.0e9,              # Call dealer positioning
    'put_gex': -3.5e9,              # Put dealer positioning
    'implied_volatility': 0.18,
    'pcr_oi': 1.15,                 # Put/Call OI ratio
    'skew': -0.05
}
```

### GEX Database Schema (SQLite)

**Table: `gamma_history`** - Intraday gamma snapshots
```sql
CREATE TABLE gamma_history (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    timestamp TEXT,              -- YYYY-MM-DD HH:MM:SS
    date TEXT,                   -- YYYY-MM-DD
    time_of_day TEXT,            -- HH:MM
    spot_price REAL,
    net_gex REAL,
    flip_point REAL,
    call_wall REAL,
    put_wall REAL,
    implied_volatility REAL,
    put_call_ratio REAL,
    distance_to_flip_pct REAL,
    regime TEXT,                 -- "Positive GEX", "Negative GEX", etc.
    UNIQUE(symbol, timestamp)
);
```

**Table: `gamma_daily_summary`** - Daily aggregates
```sql
CREATE TABLE gamma_daily_summary (
    symbol TEXT,
    date TEXT,
    open_gex REAL,
    close_gex REAL,
    high_gex REAL,
    low_gex REAL,
    gex_change REAL,
    gex_change_pct REAL,
    open_flip REAL,
    close_flip REAL,
    open_price REAL,
    close_price REAL,
    price_change_pct REAL,
    avg_iv REAL,
    snapshots_count INTEGER,
    UNIQUE(symbol, date)
);
```

### GEX Calculation Logic

**Core Formula** (in `core_classes_and_engines.py`):
```python
Net GEX = Sum across all strikes:
    Delta_adjusted_gamma × Open_Interest × 100 × Spot_Price
    
Where:
- Delta-adjusted means: Gamma is weighted by dealer delta hedging behavior
- Open Interest: Volume of contracts at each strike
- Multiplier (100): Standard option contract size
- Spot Price: Current underlying price
```

**Interpretation**:
- **Negative GEX (< -$1B)**: Dealers SHORT gamma → Forced to BUY on rallies, SELL on dips
- **Positive GEX (> +$1B)**: Dealers LONG gamma → Sell rallies, buy dips (support)
- **Flip Point**: Where gamma crosses zero (regime change point)

---

## 3. OPTIONS DATA FETCHING & STORAGE

### Real-Time Data Pipeline

```
┌──────────────────────────────────────────────────────┐
│ FRONTEND REQUEST                                      │
│ GET /api/gamma/{symbol}/intelligence?vix=20         │
└────────────────┬─────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│ BACKEND (FastAPI - backend/main.py)                  │
│ @app.get("/api/gamma/{symbol}/intelligence")        │
└────────────────┬─────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────────┐  ┌──────────────────────────────┐
│ Trading Vol API  │  │ Yahoo Finance Option Chain   │
│ get_net_gamma()  │  │ RealOptionsChainFetcher      │
│ get_gex_profile()│  │ - Fetches all strikes        │
│                  │  │ - Gets bid/ask/last prices   │
│                  │  │ - Calculates Greeks          │
│                  │  │ - IV per strike              │
└────────┬─────────┘  └────────────┬─────────────────┘
         │                         │
         └────────────┬────────────┘
                      ▼
        ┌─────────────────────────┐
        │ ClaudeIntelligence.     │
        │ analyze_market()        │
        │ (1700+ lines)           │
        │ - Analyzes GEX          │
        │ - Detects MM state      │
        │ - Strategy selection    │
        │ - Sizing calculation    │
        └────────────┬────────────┘
                     ▼
        ┌────────────────────────┐
        │ SQL: Store in Database │
        │ gamma_history table    │
        │ gamma_daily_summary    │
        └────────────┬───────────┘
                     ▼
        ┌────────────────────────┐
        │ JSON Response          │
        │ (Frontend displays)    │
        └────────────────────────┘
```

### Options Data Fetcher Implementation

**Class: `RealOptionsChainFetcher`** (in `intelligence_and_strategies.py`):
```python
def get_options_chain(symbol: str, expiry_date: str):
    """Fetch REAL options chain from Yahoo Finance"""
    # Returns: DataFrame with:
    # - strike, bid, ask, lastPrice
    # - openInterest, volume
    # - impliedVolatility
    # - delta, gamma, theta, vega
    # - contractSymbol
    
def find_best_strike(symbol: str, option_type: str, delta_target: float):
    """Find strike matching target delta (e.g., 0.50 for ATM)"""
```

**Class: `GreeksCalculator`** - Black-Scholes implementation:
```python
def calculate_greeks(spot, strike, time_to_expiry, volatility, rate):
    # Returns: delta, gamma, vega, theta, charm, vanna
    # Uses scipy.stats.norm for CDF calculations
```

---

## 4. DATABASE SCHEMA & ORM

### Current Setup

**Database Type**: SQLite (file-based)
**Path**: `gex_copilot.db` (in project root)
**ORM**: Direct SQL (no ORM currently - using sqlite3 library)
**Backend ORM**: SQLAlchemy (installed in `requirements.txt` but not yet fully integrated)

### Main Tables

| Table | Purpose | Records |
|-------|---------|---------|
| `gamma_history` | Intraday GEX snapshots | 1000s/day |
| `gamma_daily_summary` | Daily GEX aggregates | 365+ |
| `spy_correlation` | Multi-symbol correlation | 365+ |
| `autonomous_positions` | Open trades | 10-50 |
| `autonomous_trade_log` | Completed trades | 1000+ |
| `autonomous_config` | Trader settings | 10 |
| `autonomous_live_status` | Current trader state | 1 |
| `scanner_history` | Multi-symbol scans | 100s |
| `trade_setups` | Generated setups | 1000s |
| `alerts` | User alerts | 50-200 |

### Data Access Pattern

```python
# Current: Direct SQL
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT * FROM gamma_history WHERE symbol=? AND date>=?", (symbol, date))
df = pd.read_sql_query(query, conn)

# Future: SQLAlchemy (ready in requirements.txt)
from sqlalchemy import create_engine
engine = create_engine(f'sqlite:///{DB_PATH}')
```

---

## 5. API ENDPOINTS STRUCTURE

### Backend FastAPI Routes (main.py - 2,696 lines)

#### Health & Diagnostics
- `GET /` - Root (API info)
- `GET /health` - Health check
- `GET /api/time` - Market time status
- `GET /api/diagnostic` - Configuration check

#### Gamma Exposure Data
- `GET /api/gex/{symbol}` - Get GEX data
- `GET /api/gex/{symbol}/levels` - Strike-by-strike GEX detail

#### Gamma Intelligence
- `GET /api/gamma/{symbol}/intelligence?vix=20` - AI-powered analysis (1,700+ lines)
- `GET /api/gamma/{symbol}/expiration` - Weekly expiration breakdown
- `GET /api/gamma/{symbol}/history?days=30` - Historical GEX data

#### AI Copilot
- `POST /api/ai/analyze` - Market analysis with Claude

#### Autonomous Trader
- `GET /api/trader/status` - Current trader state
- `GET /api/trader/live-status` - Real-time status
- `GET /api/trader/performance` - P&L metrics
- `GET /api/trader/trades?limit=10` - Trade history
- `GET /api/trader/positions` - Open positions
- `GET /api/trader/trade-log` - Activity log
- `POST /api/trader/execute` - Manual execution trigger

#### Market Data
- `GET /api/market/price-history/{symbol}?days=90` - Historical prices

#### Multi-Symbol Scanner
- `POST /api/scanner/scan` - Scan 18+ symbols
- `GET /api/scanner/history?limit=10` - Previous scans
- `GET /api/scanner/results/{scan_id}` - Scan results

#### Trade Setups
- `POST /api/setups/generate` - Generate trade setups
- `POST /api/setups/save` - Save setup
- `GET /api/setups/list?limit=20` - List setups
- `PUT /api/setups/{setup_id}` - Update setup

#### Alerts
- `POST /api/alerts/create` - Create alert
- `GET /api/alerts/list` - Get active alerts
- `DELETE /api/alerts/{alert_id}` - Delete alert
- `GET /api/alerts/check` - Check triggered alerts
- `GET /api/alerts/history` - Alert history

#### Position Sizing
- `POST /api/position-sizing/calculate` - Calculate sizing

#### WebSocket (Real-time)
- `WS /ws/market-data?symbol=SPY` - Real-time market data stream

---

## 6. FRONTEND FRAMEWORK & COMPONENTS

### Tech Stack
- **Framework**: Next.js 14 (App Router)
- **UI Library**: React 18
- **Charts**: Lightweight Charts + Recharts + Plotly
- **HTTP Client**: Axios
- **Styling**: TailwindCSS 3.4 + PostCSS
- **Icons**: Lucide React
- **Utilities**: date-fns

### Page Structure

| Page | Route | Purpose |
|------|-------|---------|
| Dashboard | `/` | Overview, positions, P&L |
| Gamma Intelligence | `/gamma` | GEX analysis with 3-view breakdown |
| GEX Data | `/gex` | Detailed GEX levels by strike |
| Trader | `/trader` | Autonomous trader status |
| Scanner | `/scanner` | Multi-symbol scan results |
| Setups | `/setups` | Trade setup generation/management |
| Strategies | `/strategies` | Strategy comparison |
| AI Chat | `/ai` | Claude AI copilot |
| Alerts | `/alerts` | Alert management |
| Position Sizing | `/position-sizing` | Kelly criterion calculator |

### Key Components

```
Navigation.tsx
  ├─ Sidebar navigation
  └─ Dark mode toggle

StatusCard.tsx
  └─ Key metrics display

GEXProfileChart.tsx / GEXProfileChartPlotly.tsx
  ├─ Gamma profile visualization
  ├─ Call/put walls
  └─ Flip point overlay

TradingViewChart.tsx
  └─ TradingView embedded widget

API Client (lib/api.ts)
  └─ Axios instance with all endpoints
```

### Data Flow

```
User Action (Click)
    ↓
Page Component State Update (useState)
    ↓
API Call (apiClient.getGEX(), etc.)
    ↓
Axios HTTP Request
    ↓
Backend FastAPI Processing
    ↓
JSON Response
    ↓
Component Re-render with New Data
    ↓
Chart/UI Update (using Recharts/Plotly)
```

### Hooks

- **`useWebSocket`**: Real-time market data connection
- **`useDataCache`**: 5-minute cache for API responses
- **`useRouter`**: Next.js navigation
- **`useState`, `useEffect`**: Standard React state management

---

## 7. EXISTING TECHNICAL INDICATORS & RSI

### Current Implementations

**Found in `intelligence_and_strategies.py`:**

1. **Greeks Calculation** (Black-Scholes)
   - Delta (directional sensitivity)
   - Gamma (delta sensitivity)
   - Vega (volatility sensitivity)
   - Theta (time decay)
   - Charm (delta decay over time)
   - Vanna (volatility/delta interaction)

2. **Volatility Regime** Classification
   - IV Rank calculation
   - VIX ranges: LOW (<15), NORMAL (15-20), HIGH (20-30), EXTREME (>30)
   - Skew analysis (put vs call IV)

3. **Market Maker State Detection**
   - GEX-based regime classification (5 states)
   - Distance to flip point calculation
   - Wall proximity analysis

### NOT YET IMPLEMENTED

- **RSI (Relative Strength Index)** - No existing implementation
- **Moving Averages** - No existing implementation
- **Bollinger Bands** - No existing implementation
- **MACD** - No existing implementation
- **Stochastic Oscillator** - No existing implementation

**Note**: The system focuses on **GEX-based analysis** rather than traditional technical indicators. Price action, Greeks, and market maker behavior provide the primary signals.

---

## 8. AUTONOMOUS TRADER IMPLEMENTATION

### Architecture

**File**: `autonomous_paper_trader.py` (1,237 lines)

```python
class AutonomousPaperTrader:
    """
    Fully autonomous paper trader - NO manual intervention required
    - Starting Capital: $5,000
    - Auto-execution: Every market day
    - Position Sizing: 25% max per trade
    - Exit Conditions: +50% profit, -30% loss, 1 DTE, GEX change
    """
    
    def __init__(self, db_path: DB_PATH):
        self._ensure_tables()        # Create DB tables
        self.starting_capital = 5000
        self.capital = get_current_capital()  # From DB
        
    def find_daily_trade(self) -> TradeSetup:
        """Find ONE trade per day based on GEX analysis"""
        # 1. Get GEX data from Trading Volatility API
        # 2. Analyze market regime
        # 3. Get real option prices from Yahoo Finance
        # 4. Claude AI selects strategy
        # 5. Calculate position size
        # 6. Check psychological factors
        # 7. Return trade setup (or None)
        
    def execute_trade(self, setup: TradeSetup):
        """Execute the trade"""
        # 1. Submit order at current prices
        # 2. Record entry price/spread
        # 3. Store in DB with reasoning
        
    def manage_positions(self):
        """Run every hour - check exit conditions"""
        # 1. Get current option prices
        # 2. Calculate unrealized P&L
        # 3. Check exit conditions:
        #    - +50% profit → CLOSE
        #    - -30% loss → CLOSE
        #    - 1 DTE remaining → CLOSE
        #    - GEX regime changed → REASSESS
        # 4. Update DB
        # 5. Log to trade_log
```

### Trading Decision Flow

```
9:00 AM ET (Market Open -30 min)
├─ Check if already traded today
├─ Fetch SPY GEX from Trading Volatility API
├─ Determine Market Maker state (5 types)
├─ Classify volatility regime (VIX-based)
├─ Get real option prices from Yahoo Finance
├─ Calculate Greeks for all strikes
├─ Claude AI analyzes setup:
│  ├─ Selects strategy (Iron Condor, Spread, etc.)
│  ├─ Identifies entry/exit levels
│  ├─ Calculates risk/reward ratio
│  └─ Scores confidence (0-100)
├─ PsychologicalCoach checks for red flags
├─ PositionSizingCalculator determines size (Kelly)
└─ EXECUTE or PASS

9:30 AM - 4:00 PM ET (Every Hour)
├─ Check open positions
├─ Get current option prices
├─ Calculate unrealized P&L
├─ Monitor exit conditions:
│  ├─ +50% profit → CLOSE for max profit
│  ├─ -30% loss → CLOSE to limit loss
│  ├─ 1 DTE or less → CLOSE before expiration
│  └─ GEX regime change → REASSESS strategy
└─ Update database

4:00 PM ET (Market Close)
└─ Update daily summary
```

### Database Tables

**Table: `autonomous_positions`** - Open trades
```sql
CREATE TABLE autonomous_positions (
    id INTEGER PRIMARY KEY,
    symbol TEXT,                    -- "SPY"
    strategy TEXT,                  -- "IRON_CONDOR"
    action TEXT,                    -- "BUY" / "SELL"
    entry_date TEXT,               -- YYYY-MM-DD
    entry_time TEXT,               -- HH:MM:SS
    strike REAL,
    option_type TEXT,              -- "CALL" / "PUT"
    expiration_date TEXT,           -- YYYY-MM-DD (DTE)
    contracts INTEGER,
    entry_price REAL,
    entry_bid REAL,
    entry_ask REAL,
    entry_spot_price REAL,
    current_price REAL,
    current_spot_price REAL,
    unrealized_pnl REAL,
    status TEXT,                   -- "OPEN" / "CLOSED"
    closed_date TEXT,
    exit_price REAL,
    realized_pnl REAL,
    exit_reason TEXT,              -- "+50%", "-30%", "1 DTE", "GEX change"
    confidence INTEGER,             -- 0-100
    gex_regime TEXT,               -- "TRAPPED", "DEFENDING", etc.
    entry_net_gex REAL,
    trade_reasoning TEXT
);
```

**Table: `autonomous_config`** - Settings
```sql
CREATE TABLE autonomous_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Example rows:
-- ('capital', '5000')
-- ('auto_execute', 'true')
-- ('initialized', 'true')
-- ('mode', 'paper')
-- ('last_trade_date', '2024-01-15')
```

### Performance Tracking

**Dashboard: `/trader`** displays:
- Total account balance
- Today's P&L
- Week's P&L
- Monthly win rate
- Open positions with unrealized P&L
- Recent trade log
- Strategy performance breakdown

---

## 9. PSYCHOLOGICAL TRAP DETECTION (Existing)

### Current Implementation

**Class: `PsychologicalCoach`** (in `intelligence_and_strategies.py`, Line 312):

```python
def analyze_behavior(conversation_history, current_request) -> Dict:
    """Detect psychological red flags"""
    
    red_flags = []
    
    # RED FLAG 1: OVERTRADING
    if trade_request_count >= 4:
        → Alert: Too many trade requests recently
        
    # RED FLAG 2: REVENGE TRADING
    if (loss_mentioned) AND (new_trade_requested):
        → CRITICAL: Just lost and already wants another trade
        
    # RED FLAG 3: IGNORING ADVICE
    if (AI warned "risky/terrible") AND (user still pushing):
        → Alert: Overconfidence after warning
        
    # RED FLAG 4: AFTER HOURS TRADING
    if (market_closed) AND (trade_request):
        → Alert: Emotional planning outside market hours
        
    # RED FLAG 5: TIMING VIOLATION
    if (Wednesday after 3PM OR Thursday/Friday afternoon):
        → CRITICAL: Theta trap - don't hold directional into weekend
```

### Integration Points

1. **In `ClaudeIntelligence.analyze_market()`** - Claude checks psychology before recommending
2. **In Backend API** - Psychology check happens server-side
3. **Not yet in Frontend** - UI doesn't display psychology warnings

---

## 10. INTEGRATION ARCHITECTURE FOR PSYCHOLOGY TRAP DETECTION SYSTEM

### Current State
- ✅ Basic psychology detection (5 red flags)
- ✅ SQLite database setup
- ✅ Backend API endpoints ready
- ✅ Frontend pages ready to display
- ✅ Claude AI integration ready
- ❌ **Comprehensive trap detection system NOT implemented**

### What's Missing for New System
1. **Trap Pattern Recognition** - Identify common psychology traps
2. **Behavioral Scoring** - Quantify trader psychology state
3. **Trap-Specific Recommendations** - Give actionable advice for each trap
4. **ML/AI Analysis** - Use Claude to detect subtle patterns
5. **Frontend Dashboard** - Visualize psychology metrics
6. **Historical Tracking** - Learn from past behavioral mistakes

### Integration Points Ready

**Backend** (FastAPI):
```python
# Can add to /api/ai/analyze or new endpoint
@app.post("/api/psychology/analyze")
async def analyze_psychology_trap(request: dict):
    # Receives: conversation history, market data, current trades
    # Returns: Psychology trap classification + recommendations
```

**Database** (SQLite):
```python
# Can add new tables
CREATE TABLE psychology_history (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    trap_type TEXT,              -- "REVENGE", "OVERCONFIDENCE", etc.
    severity TEXT,               -- "LOW", "MEDIUM", "HIGH", "CRITICAL"
    description TEXT,
    recommendation TEXT
);
```

**Frontend** (Next.js):
```tsx
// Can add new page or component
<PsychologyDashboard />
  ├─ Current Psychology State
  ├─ Active Traps
  ├─ Trap History
  └─ Recommendations
```

---

## 11. DATA FLOW SUMMARY

### Complete Request Flow

```
USER
  ↓
FRONTEND (Next.js)
  ├─ Component render
  ├─ User interaction (button click)
  └─ Call apiClient method
       ↓
    AXIOS HTTP REQUEST
       ↓
BACKEND (FastAPI - main.py)
  ├─ Route matching
  ├─ Fetch GEX data (TradingVolatilityAPI)
  ├─ Fetch option prices (Yahoo Finance)
  ├─ Run analysis (ClaudeIntelligence)
  ├─ Store in database (SQLite)
  └─ Return JSON response
       ↓
    RESPONSE (JSON)
       ↓
FRONTEND
  ├─ Update state (useState)
  ├─ Update cache (useDataCache)
  ├─ Re-render component
  └─ Display to user
```

### Autonomous Trading Loop

```
SCHEDULE (APScheduler - every market day)
  ↓
AUTONOMOUS TRADER (autonomous_paper_trader.py)
  ├─ 9:00 AM: Find daily trade
  │   ├─ Get GEX data
  │   ├─ Analyze with Claude
  │   └─ Get position size
  │       ↓
  │   EXECUTE TRADE
  │       ↓
  │   STORE IN DATABASE
  │
  ├─ Every hour: Check positions
  │   ├─ Get current prices
  │   ├─ Calculate P&L
  │   └─ Check exit conditions
  │
  └─ 4:00 PM: Close everything / Summary
```

---

## 12. KEY FILES TO MODIFY FOR PSYCHOLOGY SYSTEM

### Essential Files

1. **`intelligence_and_strategies.py`** (2,738 lines)
   - Location: Line 312 (PsychologicalCoach class)
   - Action: **Extend** current psychology detection
   - Add: Comprehensive trap detection methods

2. **`backend/main.py`** (2,696 lines)
   - Location: Line 717+ (AI endpoints)
   - Action: **Add** new psychology endpoint
   - Route: `POST /api/psychology/analyze`

3. **`config_and_database.py`** (~200 lines)
   - Location: Currently holds MM_STATES and STRATEGIES
   - Action: **Add** Psychology Trap definitions and thresholds

4. **`gamma_tracking_database.py`** (574 lines)
   - Location: Line 19 (GammaTrackingDB class)
   - Action: **Add** psychology history table

5. **Frontend** (Create new page)
   - Location: `frontend/src/app/psychology/page.tsx` (NEW)
   - Action: **Create** Psychology dashboard

6. **Frontend API** (`frontend/src/lib/api.ts`)
   - Action: **Add** psychology endpoints to apiClient

---

## 13. SUMMARY TABLE: Architecture Components

| Component | Type | Framework | Status |
|-----------|------|-----------|--------|
| **Backend API** | FastAPI | Python 3.x | ✅ Operational |
| **Frontend** | Next.js 14 | React 18 | ✅ Operational |
| **Database** | SQLite | SQL | ✅ Operational |
| **GEX Data** | API Integration | Trading Volatility | ✅ Operational |
| **Options Data** | Web Scraping | Yahoo Finance | ✅ Operational |
| **AI Integration** | Claude API | Anthropic | ✅ Operational |
| **LangChain** | Agent Framework | Python | ✅ Installed |
| **WebSockets** | Real-time | FastAPI | ✅ Ready |
| **Paper Trading** | Autonomous | Python | ✅ Operational |
| **Psychology Detection** | Basic | Python | ⚠️ Partial (5 flags) |
| **Psychology Dashboard** | Frontend | React | ❌ Not implemented |
| **Trap Detection System** | AI | Claude | ❌ Not implemented |

---

## 14. DEPLOYMENT & CONFIGURATION

### Environment Variables

**Backend** (`.env` file):
```
ANTHROPIC_API_KEY=sk-ant-...
TRADING_VOLATILITY_API_KEY=...
TV_USERNAME=...
DATABASE_PATH=/path/to/gex_copilot.db
```

**Frontend** (`.env.local` file):
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

### Running Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### Production Deployment

- **Backend**: Render, Railway, or Digital Ocean (configured in `render.yaml`)
- **Frontend**: Vercel (configured in `frontend/vercel.json`)
- **Database**: SQLite (file-based) or migrate to PostgreSQL

---

**END OF ARCHITECTURE OVERVIEW**
