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
- [ ] GEX data arrives (check `/api/gex/SPY`)
- [ ] IV Rank calculated (check `/api/vix/current`)
- [ ] Regime classified (check `/api/gex/SPY/regime`)
- [ ] Strategy selected (check `/api/trader/status`)
- [ ] Position sized (check Kelly in trade logs)
- [ ] Trade executed (check `/api/trader/positions`)
- [ ] Exit monitored (check position updates)
- [ ] Stats updated (check `/api/backtests/results`)

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

## 🔧 NEXT STEPS

1. **Run verification script** - Test all endpoints on Render
2. **Review backtest data** - Are there enough real trades?
3. **Check strategy stats** - Do they match reality?
4. **Remove SPX duplicate** - Delete spx_institutional_trader.py
5. **Add critical tests** - Cover the mixins
6. **Clean bare excepts** - Specific exception handling
