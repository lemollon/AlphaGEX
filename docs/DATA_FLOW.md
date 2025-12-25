# AlphaGEX Data Flow

## How Data Moves Through the System

This document describes the complete data flow from external APIs through processing to storage and display.

---

## High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                               EXTERNAL DATA SOURCES                                       │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐                  │
│   │ TRADING VOL API  │    │   POLYGON API    │    │   TRADIER API    │                  │
│   │                  │    │                  │    │                  │                  │
│   │ • Net GEX        │    │ • VIX Level      │    │ • Real-time      │                  │
│   │ • Call Wall      │    │ • Option Prices  │    │   Quotes         │                  │
│   │ • Put Wall       │    │ • Historical     │    │ • Order          │                  │
│   │ • Flip Point     │    │   Data           │    │   Execution      │                  │
│   │ • Strike GEX     │    │ • Greeks         │    │ • Account        │                  │
│   └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘                  │
│            │                       │                       │                            │
└────────────┼───────────────────────┼───────────────────────┼────────────────────────────┘
             │                       │                       │
             ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              UNIFIED DATA PROVIDER                                        │
│                         (data/unified_data_provider.py)                                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌────────────────────────────────────────────────────────────────────────────────┐    │
│   │                           DATA AGGREGATION                                      │    │
│   │                                                                                 │    │
│   │   fetch_gex()  ───┐                                                             │    │
│   │                   │                                                             │    │
│   │   fetch_vix()  ───┼───▶  MarketData Object  ───▶  Cache (60s)                   │    │
│   │                   │      {                                                      │    │
│   │   fetch_quote() ──┘        symbol,                                              │    │
│   │                            spot_price,                                          │    │
│   │                            net_gex,                                             │    │
│   │                            vix,                                                 │    │
│   │                            iv_rank,                                             │    │
│   │                            call_wall,                                           │    │
│   │                            put_wall,                                            │    │
│   │                            flip_point,                                          │    │
│   │                            timestamp                                            │    │
│   │                          }                                                      │    │
│   └────────────────────────────────────────────────────────────────────────────────┘    │
│                                          │                                               │
└──────────────────────────────────────────┼───────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              PROCESSING LAYER                                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐                     │
│   │ REGIME          │    │ STRATEGY        │    │ POSITION        │                     │
│   │ CLASSIFIER      │───▶│ SELECTOR        │───▶│ SIZER           │                     │
│   │                 │    │                 │    │                 │                     │
│   │ Input:          │    │ Input:          │    │ Input:          │                     │
│   │ • MarketData    │    │ • Regime        │    │ • Strategy      │                     │
│   │                 │    │ • IV Rank       │    │ • Stats         │                     │
│   │ Output:         │    │                 │    │ • Confidence    │                     │
│   │ • Regime        │    │ Output:         │    │                 │                     │
│   │ • Confidence    │    │ • Strategy      │    │ Output:         │                     │
│   │ • Action        │    │ • Parameters    │    │ • Contracts     │                     │
│   └─────────────────┘    └─────────────────┘    │ • Kelly %       │                     │
│                                                 └─────────────────┘                     │
│                                                          │                               │
└──────────────────────────────────────────────────────────┼───────────────────────────────┘
                                                           │
                                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              STORAGE LAYER (PostgreSQL)                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐                  │
│   │ gex_data         │    │ autonomous_      │    │ bot_decision_    │                  │
│   │                  │    │ positions        │    │ logs             │                  │
│   │ • symbol         │    │                  │    │                  │                  │
│   │ • net_gex        │    │ • symbol         │    │ • decision_id    │                  │
│   │ • spot_price     │    │ • strategy       │    │ • what           │                  │
│   │ • call_wall      │    │ • entry_price    │    │ • why            │                  │
│   │ • put_wall       │    │ • contracts      │    │ • how            │                  │
│   │ • timestamp      │    │ • status         │    │ • market_context │                  │
│   └──────────────────┘    └──────────────────┘    └──────────────────┘                  │
│                                                                                          │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐                  │
│   │ autonomous_      │    │ strategy_stats   │    │ spx_wheel_       │                  │
│   │ closed_trades    │    │                  │    │ positions        │                  │
│   │                  │    │ • strategy_name  │    │                  │                  │
│   │ • realized_pnl   │    │ • win_rate       │    │ • strike         │                  │
│   │ • exit_reason    │    │ • avg_win        │    │ • expiration     │                  │
│   │ • entry_regime   │    │ • expectancy     │    │ • premium        │                  │
│   └──────────────────┘    └──────────────────┘    └──────────────────┘                  │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER (FastAPI)                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   /api/gex/{symbol}          → GEX data + regime                                        │
│   /api/vix/current           → VIX level + IV rank                                      │
│   /api/trader/status         → Current trader state                                     │
│   /api/trader/positions      → Open positions                                           │
│   /api/trader/performance    → P&L history                                              │
│   /api/backtests/results     → Backtest data                                            │
│   /api/gamma/intelligence    → AI analysis                                              │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (Next.js React)                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐                  │
│   │ /trader          │    │ /gex             │    │ /gamma           │                  │
│   │                  │    │                  │    │                  │                  │
│   │ Position list    │    │ GEX bar chart    │    │ Gamma analysis   │                  │
│   │ P&L summary      │    │ Call/Put walls   │    │ Probabilities    │                  │
│   │ Trade history    │    │ Regime indicator │    │ AI insights      │                  │
│   └──────────────────┘    └──────────────────┘    └──────────────────┘                  │
│                                                                                          │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐                  │
│   │ /psychology      │    │ /backtesting     │    │ /scanner         │                  │
│   │                  │    │                  │    │                  │                  │
│   │ Trap detection   │    │ Strategy perf    │    │ Market scanner   │                  │
│   │ FOMO/Fear alerts │    │ Win rates        │    │ Opportunity list │                  │
│   └──────────────────┘    └──────────────────┘    └──────────────────┘                  │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Data Flows

### 1. GEX Data Flow

```
Trading Volatility API
        │
        │  HTTP GET /gex/{symbol}
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  data/trading_vol_fetcher.py                                    │
│                                                                 │
│  def fetch_gex(symbol: str) -> dict:                           │
│      response = requests.get(                                   │
│          f"{BASE_URL}/api/gex/{symbol}",                       │
│          headers={"Authorization": f"Bearer {API_KEY}"}        │
│      )                                                          │
│      return response.json()                                     │
│                                                                 │
│  Returns:                                                       │
│  {                                                              │
│      "SPY": {                                                   │
│          "net_gex": 2450000000,                                │
│          "spot_price": 585.42,                                  │
│          "call_wall": 590,                                      │
│          "put_wall": 575,                                       │
│          "gex_flip_point": 580,                                │
│          "strikes": [                                           │
│              {"strike": 580, "gamma": 1250000, ...},           │
│              {"strike": 585, "gamma": 980000, ...}             │
│          ]                                                      │
│      }                                                          │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
        │
        │  Parsed and cached
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Cache Layer (60 seconds TTL)                                   │
│                                                                 │
│  gex_cache = {                                                  │
│      "SPY": {                                                   │
│          "data": {...},                                         │
│          "timestamp": "2025-12-25T14:30:00",                   │
│          "ttl": 60                                              │
│      }                                                          │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
        │
        │  Stored for historical analysis
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL: gex_data table                                     │
│                                                                 │
│  INSERT INTO gex_data (                                         │
│      symbol, net_gex, spot_price, call_wall, put_wall,         │
│      gex_flip_point, strikes, timestamp                         │
│  ) VALUES (                                                     │
│      'SPY', 2450000000, 585.42, 590, 575, 580,                 │
│      '[{"strike": 580, ...}]', NOW()                           │
│  )                                                              │
└─────────────────────────────────────────────────────────────────┘
        │
        │  Exposed via API
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI: /api/gex/{symbol}                                     │
│                                                                 │
│  @router.get("/gex/{symbol}")                                   │
│  async def get_gex(symbol: str):                               │
│      # Try cache first                                          │
│      cached = gex_cache.get(symbol)                            │
│      if cached and not is_stale(cached):                       │
│          return cached["data"]                                  │
│                                                                 │
│      # Fetch fresh data                                         │
│      data = fetch_gex(symbol)                                  │
│      gex_cache[symbol] = {"data": data, "timestamp": now()}    │
│      store_to_db(data)                                          │
│      return data                                                │
└─────────────────────────────────────────────────────────────────┘
        │
        │  Consumed by frontend
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  React Component: GEXChart.tsx                                  │
│                                                                 │
│  const { data, isLoading } = useSWR(                           │
│      `/api/gex/${symbol}`,                                      │
│      fetcher,                                                   │
│      { refreshInterval: 60000 }                                 │
│  )                                                              │
│                                                                 │
│  // Render bar chart with GEX by strike                         │
│  <BarChart data={data.strikes} />                              │
│  <LevelIndicator level={data.call_wall} label="Call Wall" />   │
│  <LevelIndicator level={data.put_wall} label="Put Wall" />     │
└─────────────────────────────────────────────────────────────────┘
```

---

### 2. Trade Decision Flow

```
Market Data
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Regime Classifier (core/market_regime_classifier.py)          │
│                                                                 │
│  Input:                              Output:                    │
│  • spot_price: 585.42               • regime: POSITIVE_GAMMA   │
│  • net_gex: +2.45B                  • confidence: 85           │
│  • vix: 18.5                        • action: SELL_PREMIUM     │
│  • iv_rank: 45                      • trend: UPTREND           │
│  • ma20: 582, ma50: 578                                        │
│                                                                 │
│  Logic:                                                         │
│  if net_gex > 500M and iv_rank > 40:                           │
│      action = "SELL_PREMIUM"                                    │
│      confidence = base_confidence + gex_score + iv_score       │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Selector                                              │
│                                                                 │
│  Input:                              Output:                    │
│  • action: SELL_PREMIUM             • strategy: BULL_PUT_SPREAD│
│  • trend: UPTREND                   • short_delta: 0.30        │
│  • iv_rank: 45                      • long_delta: 0.15         │
│                                     • dte: 45                   │
│  Logic:                             • width: 5                  │
│  if action == SELL_PREMIUM:                                     │
│      if trend == UPTREND:                                       │
│          return BULL_PUT_SPREAD                                 │
│      elif trend == DOWNTREND:                                   │
│          return BEAR_CALL_SPREAD                                │
│      else:                                                      │
│          return IRON_CONDOR                                     │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Position Sizer (trading/mixins/position_sizer.py)             │
│                                                                 │
│  Input:                              Output:                    │
│  • strategy: BULL_PUT_SPREAD        • kelly_pct: 4.4%          │
│  • win_rate: 68%                    • contracts: 5             │
│  • avg_win: 15%                     • max_loss: $2,500         │
│  • avg_loss: 25%                                               │
│  • confidence: 85                                               │
│  • account: $50,000                                             │
│                                                                 │
│  Kelly = (0.68 × 15 - 0.32 × 25) / 25 = 8.8%                   │
│  Half Kelly = 4.4%                                              │
│  Position = $50,000 × 0.044 = $2,200                           │
│  Contracts = $2,200 / $500 per contract = 4.4 → 5 contracts    │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Decision Logger (trading/decision_logger.py)                   │
│                                                                 │
│  TradeDecision {                                                │
│      decision_id: "DEC-2025122514300001",                      │
│      timestamp: "2025-12-25T14:30:00",                         │
│      bot_name: "PROMETHEUS",                                    │
│      decision_type: "ENTRY",                                    │
│                                                                 │
│      what: "SELL 5x SPY Bull Put Spread 580/575 Jan 45DTE",    │
│      why: "Positive GEX +2.45B with 45% IV Rank. Uptrend       │
│            confirmed by price > MA20 > MA50. Backtest          │
│            win rate 68%.",                                      │
│      how: "Kelly sizing at 4.4% ($2,200). Credit: $1.25       │
│            per spread. Max loss: $3.75/spread.",               │
│                                                                 │
│      market_context: {                                          │
│          spot_price: 585.42,                                    │
│          vix: 18.5,                                             │
│          regime: "POSITIVE_GAMMA"                               │
│      },                                                         │
│                                                                 │
│      legs: [                                                    │
│          {strike: 580, type: PUT, action: SELL, delta: -0.30}, │
│          {strike: 575, type: PUT, action: BUY, delta: -0.15}   │
│      ]                                                          │
│  }                                                              │
│                                                                 │
│  → Stored in: bot_decision_logs table                          │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Trade Executor                                                 │
│                                                                 │
│  PAPER MODE:                                                    │
│  • Simulate fill at mid price                                   │
│  • Record to autonomous_positions                               │
│  • Generate paper order_id                                      │
│                                                                 │
│  LIVE MODE:                                                     │
│  • Place order via Tradier API                                  │
│  • Wait for fill confirmation                                   │
│  • Record actual fill price                                     │
│  • Store broker order_id                                        │
│                                                                 │
│  → Stored in: autonomous_positions table                        │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3. Position Update Flow

```
Position Monitor (runs every 60 seconds)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Query Open Positions                                           │
│                                                                 │
│  SELECT * FROM autonomous_positions                             │
│  WHERE status = 'OPEN'                                          │
│                                                                 │
│  Returns:                                                       │
│  [                                                              │
│      {id: 123, symbol: SPY, strategy: BULL_PUT_SPREAD,         │
│       entry_price: 1.25, contracts: 5, expiration: 2025-02-07} │
│  ]                                                              │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Get Current Prices (for each position)                        │
│                                                                 │
│  current_price = get_spread_value(position)                     │
│  • Fetch option quotes from Polygon/Tradier                     │
│  • Calculate spread value                                       │
│  • current_price = 0.65 (was 1.25 at entry)                    │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Calculate P&L                                                  │
│                                                                 │
│  entry_credit = 1.25 × 100 × 5 = $625                          │
│  current_cost = 0.65 × 100 × 5 = $325 (to close)               │
│  unrealized_pnl = $625 - $325 = $300                           │
│  pnl_pct = ($300 / $625) × 100 = 48%                           │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Check Exit Conditions                                          │
│                                                                 │
│  ✓ profit_target (50%): pnl_pct (48%) < 50% → NOT MET          │
│  ✓ stop_loss (200%): pnl_pct (48%) > -200% → NOT MET           │
│  ✓ time_exit (7 DTE): dte (43) > 7 → NOT MET                   │
│                                                                 │
│  → No exit triggered, continue monitoring                       │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Update Position in Database                                    │
│                                                                 │
│  UPDATE autonomous_positions SET                                │
│      current_price = 0.65,                                      │
│      unrealized_pnl = 300,                                      │
│      updated_at = NOW()                                         │
│  WHERE id = 123                                                 │
└─────────────────────────────────────────────────────────────────┘
    │
    │  When exit condition met (e.g., pnl_pct >= 50%)
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Execute Exit                                                   │
│                                                                 │
│  1. Close position (buy back spread)                            │
│  2. Update autonomous_positions: status = 'CLOSED'              │
│  3. Insert into autonomous_closed_trades                        │
│  4. Update strategy_stats                                       │
│  5. Log exit decision to bot_decision_logs                      │
└─────────────────────────────────────────────────────────────────┘
```

---

### 4. Frontend Data Consumption

```
React App Initialization
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  SWR Data Fetching (lib/api.ts)                                │
│                                                                 │
│  // Configured with base URL and interceptors                   │
│  const api = axios.create({                                     │
│      baseURL: process.env.NEXT_PUBLIC_API_URL,                 │
│      timeout: 10000                                             │
│  })                                                             │
│                                                                 │
│  // SWR fetcher function                                        │
│  export const fetcher = (url: string) =>                       │
│      api.get(url).then(res => res.data)                        │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Page Component (e.g., /trader page)                           │
│                                                                 │
│  function TraderPage() {                                        │
│      // Fetch trader status (refreshes every 30s)              │
│      const { data: status } = useSWR(                          │
│          '/api/trader/status',                                  │
│          fetcher,                                               │
│          { refreshInterval: 30000 }                             │
│      )                                                          │
│                                                                 │
│      // Fetch positions (refreshes every 60s)                   │
│      const { data: positions } = useSWR(                       │
│          '/api/trader/positions',                               │
│          fetcher,                                               │
│          { refreshInterval: 60000 }                             │
│      )                                                          │
│                                                                 │
│      // Fetch performance (refreshes every 5min)                │
│      const { data: performance } = useSWR(                     │
│          '/api/trader/performance',                             │
│          fetcher,                                               │
│          { refreshInterval: 300000 }                            │
│      )                                                          │
│                                                                 │
│      return (                                                   │
│          <TraderDashboard                                       │
│              status={status}                                    │
│              positions={positions}                              │
│              performance={performance}                          │
│          />                                                     │
│      )                                                          │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Component Rendering                                            │
│                                                                 │
│  <TraderDashboard>                                             │
│      │                                                          │
│      ├── <StatusCard>                                          │
│      │       Current: ACTIVE                                    │
│      │       Strategy: BULL_PUT_SPREAD                         │
│      │       Regime: POSITIVE_GAMMA                            │
│      │                                                          │
│      ├── <PositionsTable>                                      │
│      │       | Symbol | Strategy | Entry | Current | P&L |     │
│      │       | SPY    | BPS      | $1.25 | $0.65   | +$300|    │
│      │                                                          │
│      └── <PerformanceChart>                                    │
│              Daily P&L over time                                │
│              Win rate: 68%                                      │
│              Total P&L: +$2,450                                 │
│  </TraderDashboard>                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Transformation Summary

| Stage | Input | Transformation | Output |
|-------|-------|----------------|--------|
| **API Fetch** | HTTP Response | Parse JSON | Raw data dict |
| **Validation** | Raw data | Schema validation | Validated data |
| **Caching** | Validated data | Add timestamp, TTL | Cached entry |
| **Storage** | Validated data | SQL insert | Database row |
| **Regime** | Market data | Classification logic | Regime + confidence |
| **Strategy** | Regime + action | Strategy mapping | Strategy config |
| **Sizing** | Strategy + stats | Kelly calculation | Position size |
| **Decision** | All context | Aggregation | Decision log entry |
| **API Response** | Database query | JSON serialization | API response |
| **Frontend** | API response | React state | UI components |

---

## Error Handling at Each Stage

| Stage | Error Type | Handling | Fallback |
|-------|------------|----------|----------|
| API Fetch | Network timeout | Retry 3x | Use cached data |
| API Fetch | 429 Rate limit | Wait + retry | Use cached data |
| Validation | Invalid data | Log + reject | Skip processing |
| Caching | Cache miss | Fetch fresh | Direct API call |
| Storage | DB error | Log + continue | In-memory only |
| Regime | Missing data | Log + default | NEUTRAL regime |
| Strategy | No valid strategy | Log + skip | No trade |
| Sizing | Negative Kelly | Block strategy | Zero size |
| Execution | Order rejected | Log + alert | No position |
| Frontend | API error | Show error UI | Cached data |
