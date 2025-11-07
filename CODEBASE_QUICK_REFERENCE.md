# AlphaGEX Codebase - Quick Reference Guide

## Project Overview

**What it does**: Options trading intelligence platform using Gamma Exposure (GEX) analysis and Claude AI to generate profitable trade signals.

**Core Edge**: Predicts Market Maker behavior by analyzing dealer gamma positioning to identify forced buying/selling situations.

**Data**: Real market data from Trading Volatility API (GEX) + Yahoo Finance (options prices).

**AI**: Claude 3.5 Sonnet for intelligent analysis, recommendations, and psychological coaching.

---

## File Organization

### Core Analysis (Primary - START HERE)

| File | Lines | Purpose | Key Classes |
|------|-------|---------|-------------|
| `core_classes_and_engines.py` | 2,842 | GEX analysis & trading logic | `TradingVolatilityAPI`, `GEXAnalyzer`, `TradingStrategy`, `MarketRegimeAnalyzer` |
| `intelligence_and_strategies.py` | 2,738 | Claude AI & advanced analysis | `ClaudeIntelligence`, `TradingRAG`, `FREDIntegration` |
| `config_and_database.py` | ~200 | Constants, MM states, strategies | `MM_STATES`, `STRATEGIES` (5 MM states, 4 trading strategies) |

### User Interface

| File | Lines | Purpose | Components |
|------|-------|---------|------------|
| `gex_copilot.py` | 3,260 | Main Streamlit app | Dashboard, AI Chat, Trade Journal, Position Management |
| `visualization_and_plans.py` | 2,452 | Charts & visualizations | Gamma plots, GEX history, Greeks displays |

### Backend API

| File | Lines | Purpose | Key Endpoints |
|------|-------|---------|---------------|
| `backend/main.py` | 2,696 | FastAPI REST API | `/api/gex/{symbol}`, `/api/gamma/{symbol}/intelligence`, `/api/ai/analyze`, `/ws/market-data` |

### Autonomous Trading

| File | Lines | Purpose | Functionality |
|------|-------|---------|---------------|
| `autonomous_paper_trader.py` | 1,237 | Auto-execution engine | Finds daily trade, executes, manages positions |
| `autonomous_trader_dashboard.py` | 1,073 | Performance tracking | Shows positions, P&L, activity log |
| `autonomous_scheduler.py` | ~300 | Task scheduling | Cron-style execution for cloud deployment |

### Supporting Systems

| File | Lines | Purpose | Notes |
|------|-------|---------|-------|
| `paper_trader_v2.py` | 617 | Paper trading with real prices | Uses Yahoo Finance for option prices |
| `gamma_tracking_database.py` | 574 | GEX history management | Stores daily GEX snapshots |
| `position_sizing.py` | ~280 | Kelly criterion calculator | Full, half, quarter Kelly sizing |
| `trade_journal_agent.py` | 460 | Trade logging & analysis | Post-trade review system |
| `position_management_agent.py` | 416 | Position monitoring | P&L tracking, exit condition checks |
| `alerts_system.py` | 378 | Alert notifications | Twilio SMS, price alerts |
| `multi_symbol_scanner.py` | 493 | Multi-symbol analysis | Extends beyond SPY |

---

## Key Concepts

### 1. Market Maker States (5 Types)

```python
PANICKING (GEX < -$3B)    → Dealers SHORT gamma, forced buyers → Win: 90%
TRAPPED   (GEX -$3B to -$2B) → Forced buying on rallies → Win: 85%
HUNTING   (GEX -$2B to -$1B) → Aggressive positioning → Win: 60%
DEFENDING (GEX > +$1B)    → Selling rallies, buying dips → Win: 72%
NEUTRAL   (GEX -$1B to +$1B) → Balanced → Win: 50%
```

### 2. Core Trading Strategies

**Directional** (Long Volatility)
- Negative GEX Squeeze: Buy calls when dealers SHORT gamma
- Positive GEX Breakdown: Buy puts when dealers LONG gamma
- Flip Point Explosion: Enter when regime about to change

**Range-Bound** (Short Volatility)
- Iron Condor: Sell premium between walls (72% win rate)
- Premium Selling: Fade extreme moves at walls

### 3. Gamma Intelligence (3-View Analysis)

**View 1 - Daily Impact**: Today's gamma expiring %
**View 2 - Weekly Evolution**: Monday baseline vs current vs Friday
**View 3 - Volatility Potential**: Daily expiration breakdown, highest risk day

### 4. Greeks Calculation

```python
Delta        → Directional sensitivity (0 = neutral, 1 = pure directional)
Gamma        → Delta sensitivity (drives position sizing)
Vega         → Volatility impact
Theta        → Time decay
Charm        → Delta decay over time
Vanna        → Volatility/delta interaction
```

### 5. Position Sizing Methods

```python
Full Kelly    → Maximum growth (20%+ positions)
Half Kelly    → Balanced growth (10-15% positions) ← RECOMMENDED
Quarter Kelly → Conservative (5-8% positions)
```

---

## Understanding the Data Flow

### 1. Data Sources (Real Market Only)

```
Trading Volatility API
  → GEX Data (net_gex, flip_point, call_wall, put_wall)
  → Dealer positioning insight

Yahoo Finance
  → Option chains (all strikes, expirations)
  → Bid/Ask prices (entry/exit)
  → Implied volatility (regime)
  → Volume & open interest (liquidity)

FRED API (Macro Context)
  → VIX (volatility regime)
  → Treasury yields (rate expectations)
  → Fed Funds rate (monetary policy)

Internal Database
  → Historical GEX data
  → Trade history (2000+ trades)
  → Performance metrics
```

### 2. Analysis Pipeline

```
Get GEX Data
  → Determine MM State (5 types)
  → Classify Volatility Regime
  → Calculate Gamma Expiration Risk
  → Fetch Real Option Prices
  → Calculate Greeks
  → Identify Strategy
  → Size Position (Kelly criterion)
  → Check Psychological Factors
  → Generate Recommendation
```

### 3. Claude AI Integration

**Location**: `intelligence_and_strategies.py` Line 1328

```python
class ClaudeIntelligence:
    def analyze_market(market_data, user_query, gamma_intel)
        # 1700+ lines of sophisticated analysis
        # Returns: Full recommendation with reasoning

    def teach_concept(market_data, topic)
        # Educational explanations

    def challenge_trade_idea(idea, market_data)
        # Risk assessment & pushback

    def _call_claude_api(messages)
        # Direct Anthropic API call
        # Uses Claude 3.5 Sonnet
        # System prompt: 2000+ lines with market context
```

**System Prompt Includes**:
- Real-time market regime (VIX, yields, Fed rates)
- Day-of-week trading rules
- GEX-specific trading guidance
- Risk management protocols
- Psychological coaching

---

## Trading Workflow

### Daily Process

```
9:00 AM ET
├─ Check if already traded today
├─ Fetch SPY GEX from Trading Volatility API
├─ Analyze market regime
├─ Get real option prices from Yahoo Finance
├─ Calculate Greeks
├─ Claude AI analyzes setup
├─ Check psychological factors
└─ Execute or pass

9:30 AM - 4:00 PM ET (Every Hour)
├─ Check open position P&L
├─ Monitor GEX regime changes
├─ Check exit conditions:
│  ├─ +50% profit → AUTO CLOSE
│  ├─ -30% loss → AUTO CLOSE
│  ├─ 1 DTE or less → AUTO CLOSE
│  └─ GEX state flip → REASSESS
└─ Update database

4:00 PM ET
├─ Close any remaining positions
├─ Calculate daily P&L
├─ Log full trade details
├─ Optional: Claude post-mortem analysis
└─ Update RAG system with new trade
```

---

## Important Classes to Understand

### ClaudeIntelligence (Core AI)
- **File**: `intelligence_and_strategies.py:1328`
- **Methods**:
  - `analyze_market()` - Main recommendation engine
  - `teach_concept()` - Educational mode
  - `challenge_trade_idea()` - Risk assessment
  - `_call_claude_api()` - API interaction
- **Supports**:
  - Psychological coaching (red flag detection)
  - Trade post-mortem analysis
  - Portfolio analysis
  - Scenario planning

### TradingVolatilityAPI (GEX Data)
- **File**: `core_classes_and_engines.py`
- **Methods**:
  - `get_net_gamma(symbol)` - Fetches GEX + flip + walls + spot price
  - `get_gex_profile(symbol)` - Detailed GEX profile with strike-level data
  - `get_historical_gamma(symbol, days_back)` - Historical gamma data
- **Returns**: Real dealer gamma positioning

### GEXAnalyzer (Gamma Calculations)
- **File**: `core_classes_and_engines.py`
- **Methods**:
  - `calculate_gex()` - Gamma at each strike
  - `find_gamma_flip()` - Zero crossing point
  - `identify_key_levels()` - Support/resistance
  - `calculate_charm()` - Delta decay

### TradingStrategy (Setup Identification)
- **File**: `core_classes_and_engines.py`
- **Methods**:
  - `identify_squeeze_setups()` - Negative GEX
  - `identify_iron_condors()` - Range-bound
  - `identify_premium_selling()` - Wall setups
  - `calculate_position_size()` - Kelly sizing

### TradingRAG (Trade History Retrieval)
- **File**: `intelligence_and_strategies.py:715`
- **Methods**:
  - `get_similar_trades()` - Pattern matching
  - `get_personal_stats()` - Win/loss tracking
  - `get_pattern_success_rate()` - Historical performance
  - `build_context_for_claude()` - RAG context
- **Purpose**: Memory for similar setups

---

## Database Schema

### Core Tables

**gex_history**
```
id, timestamp, symbol, net_gex, flip_point, 
call_wall, put_wall, spot_price, mm_state, regime
```

**recommendations**
```
id, timestamp, symbol, strategy, confidence,
entry_price, target_price, stop_price,
option_strike, option_type, dte, reasoning
```

**autonomous_positions**
```
id, entry_time, exit_time, symbol, 
entry_price, exit_price, quantity, p_l,
strategy, gex_at_entry, reasoning
```

**autonomous_trade_log**
```
id, timestamp, action, details, success, error_msg
```

---

## FastAPI Endpoints

```python
GET  /              → Root/health check
GET  /health        → Health status
GET  /api/time      → Current time in ET/UTC
GET  /api/diagnostic → System diagnostics

GET  /api/gex/{symbol}                  → GEX data
GET  /api/gex/{symbol}/levels           → Key levels (walls, flip)
GET  /api/gamma/{symbol}/intelligence   → 3-view gamma analysis
GET  /api/gamma/{symbol}/expiration     → Gamma expiration risk
GET  /api/gamma/{symbol}/history?days=  → Historical GEX data

POST /api/ai/analyze       → Claude analysis
POST /api/position-sizing/calculate → Kelly sizing

WS   /ws/market-data?symbol=SPY → Real-time updates
```

---

## Configuration Files

**`.env` or Streamlit Secrets**
```
CLAUDE_API_KEY=sk-ant-...
TRADING_VOLATILITY_API_KEY=your_key
FRED_API_KEY=your_key (optional)
```

**`config_and_database.py`**
- MM_STATES: 5 behavioral states
- STRATEGIES: 4 trading strategies
- Win rates, R/R ratios, conditions

---

## Key Metrics & Performance

**Strategy Win Rates** (Historical)
- Negative GEX Squeeze: 68% | R/R 3.0:1
- Positive GEX Breakdown: 62% | R/R 2.5:1
- Iron Condor: 72% | R/R 0.3:1
- Premium Selling: 65% | R/R 0.5:1
- Flip Point Explosion: 75% | R/R 2.0:1

**Expected Returns** (With proper sizing)
- Conservative (Quarter Kelly): +5-8% monthly
- Balanced (Half Kelly): +10-15% monthly
- Aggressive (Full Kelly): +20-30% monthly

**Autonomous Trader** (Paper Trading)
- Starting capital: $5,000
- Max position: 25% = $1,250
- Profit target: +50%
- Stop loss: -30%
- Trades/month: ~20 (1 per market day)

---

## Common Tasks

### Check MM State
```python
from intelligence_and_strategies import ClaudeIntelligence
from core_classes_and_engines import TradingVolatilityAPI

api = TradingVolatilityAPI()
gex_data = api.get_net_gamma('SPY')
net_gex = gex_data['net_gex']

# net_gex < -$3B → PANICKING
# net_gex < -$2B → TRAPPED
# etc.
```

### Get Real Option Price
```python
from intelligence_and_strategies import RealOptionsChainFetcher

fetcher = RealOptionsChainFetcher()
option = fetcher.find_best_strike('SPY', 'call', delta_target=0.50)
# Returns: bid, ask, last, iv, volume, open_interest
```

### Calculate Position Size
```python
from intelligence_and_strategies import PositionSizingCalculator

calculator = PositionSizingCalculator()
contracts = calculator.calculate_contracts(
    account_size=50000,
    risk_pct=2.0,
    entry_price=4.50,
    stop_price=3.15  # 30% stop
)
```

### Analyze Market
```python
from intelligence_and_strategies import ClaudeIntelligence

claude = ClaudeIntelligence()
response = claude.analyze_market(
    market_data={'net_gex': -2.1e9, 'flip_point': 580, 'spot': 576},
    user_query="Should I buy calls?",
    gamma_intel=gamma_intelligence
)
```

---

## Next Steps for LangChain Integration

### High-Priority Items

1. **Agent Framework**
   - Replace direct API calls with LangChain agents
   - Add tool definitions for GEX fetching, options analysis, sizing
   - Multi-step workflow with reflection

2. **Memory Management**
   - Migrate from manual conversation tracking to LangChain memory
   - ConversationBufferMemory for short-term
   - Persistent memory for trade history

3. **Prompt Engineering**
   - Break 2000+ line system prompt into composable templates
   - Dynamic prompt selection based on context
   - Personalization based on user profile

4. **Output Parsing**
   - Structure Claude's responses with Pydantic models
   - Validate all required fields
   - Handle errors gracefully

5. **RAG Enhancement**
   - Upgrade TradingRAG to use vector stores
   - Semantic search over 2000+ historical trades
   - Better pattern matching

---

## Files to Read First

1. **ALPHAGEX_COMPREHENSIVE_ANALYSIS.md** (This detailed breakdown)
2. **SYSTEM_ARCHITECTURE_SUMMARY.txt** (Visual diagrams)
3. **core_classes_and_engines.py** (Core logic)
4. **intelligence_and_strategies.py** (Claude integration)
5. **gex_copilot.py** (How it all comes together)

---

## Resources

- **Trading Volatility API**: https://stocks.tradingvolatility.net/
- **Claude API Docs**: https://docs.anthropic.com/
- **Yahoo Finance**: https://yfinance.readthedocs.io/
- **FRED API**: https://fred.stlouisfed.org/
- **FastAPI**: https://fastapi.tiangolo.com/
- **Streamlit**: https://docs.streamlit.io/

---

**Last Updated**: 2025-11-07
**Status**: Production Ready
**Version**: 2.0.0

