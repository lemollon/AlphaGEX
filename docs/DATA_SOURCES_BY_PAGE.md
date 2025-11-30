# AlphaGEX Data Sources by Page

## Complete Data Flow Documentation

This document shows exactly where each page gets its data, how often it updates, and whether it's stored for ML/AI analysis.

---

## Dashboard (/)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| GEX Summary | Net GEX, Flip Point | `/api/gex/SPY` | TradingVolatility API | On load | YES - `gex_history` |
| Price Chart | SPY Price | `/api/market/price-history/SPY` | Polygon.io | On load | **NOW YES** - `price_history` |
| Trader Status | P&L, Positions | `/api/trader/status` | Database | 10 sec | YES - `autonomous_*` |
| Psychology | Regime | `/api/psychology/current-regime` | Calculated | On load | YES - `regime_signals` |

---

## GEX Page (/gex)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Net GEX | Total GEX value | `/api/gex/{symbol}` | TradingVolatility → Tradier → DB | On load | YES - `gex_history` |
| Flip Point | Gamma flip level | `/api/gex/{symbol}` | Same as above | On load | YES |
| Call Wall | Call resistance | `/api/gex/{symbol}` | Same as above | On load | YES |
| Put Wall | Put support | `/api/gex/{symbol}` | Same as above | On load | YES |
| GEX Chart | Historical GEX | `/api/gex/history` | Database | On load | YES |

**Data Flow:**
```
TradingVolatility API (primary)
    ↓ (if fails)
Tradier Options Chain → Calculate GEX
    ↓ (if fails)
gex_history table (last 7 days)
```

---

## Gamma Analysis (/gamma)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| 3-View Analysis | Primary/Secondary/Tertiary | `/api/gamma/{symbol}/intelligence` | TradingVolatility | On load | Partial |
| Gamma Levels | Support/Resistance | `/api/gamma/{symbol}/levels` | TradingVolatility | On load | YES - `gex_history` |
| Probabilities | Move probabilities | `/api/gamma/{symbol}/probabilities` | Calculated | On load | YES - `probability_*` |
| Waterfall | Expiration risk | `/api/gamma/{symbol}/expiration-waterfall` | Calculated | On load | YES - `gamma_expiration_timeline` |

---

## Trader Page (/trader)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Open Positions | Active trades | `/api/trader/positions` | Database | 10 sec WebSocket | YES - `autonomous_open_positions` |
| Closed Trades | Trade history | `/api/trader/closed-trades` | Database | On load | YES - `autonomous_closed_trades` |
| Equity Curve | Account value over time | `/api/trader/equity-curve` | Database | 5 min | YES - `autonomous_equity_snapshots` |
| Performance | Win rate, P&L | `/api/trader/performance` | Database | On load | YES - Calculated from trades |

**WebSocket Updates:**
- `/ws/trader` - Updates every 10 seconds during market hours
- `/ws/positions` - Updates every 5 seconds

---

## VIX Page (/vix)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| VIX Spot | Current VIX | `/api/vix/current` | Polygon.io | On load | Partial - `regime_signals.vix_current` |
| Hedge Signal | Buy/Sell signal | `/api/vix/hedge-signal` | Calculated | On load | YES - `vix_hedge_signals` |
| Term Structure | VIX futures | `/api/vix/current` | Polygon.io | On load | **NOW YES** - `vix_term_structure` |

---

## Psychology (/psychology)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Current Regime | Regime type | `/api/psychology/current-regime` | Analysis engine | On load | YES - `regime_signals` |
| RSI Multi-TF | 5m/15m/1h/4h/1d RSI | `/api/psychology/current-regime` | Polygon.io + Calc | On load | YES - in `regime_signals` |
| Trap Detection | Psychology traps | `/api/psychology/current-regime` | Analysis engine | On load | YES |
| Liberation Setups | Breakout signals | `/api/psychology/liberation-setups` | Analysis engine | On load | YES - `liberation_outcomes` |
| False Floors | False support | `/api/psychology/false-floors` | Analysis engine | On load | YES |

---

## Scanner (/scanner)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Multi-Symbol | GEX for 20+ symbols | `/api/scanner/scan` | TradingVolatility | Manual | YES - `scanner_history` |
| Opportunities | Best setups | `/api/scanner/scan` | Calculated | Manual | YES |

---

## Backtesting (/backtesting)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Results | Win rate, Sharpe | `/api/backtest/results` | Database | On load | YES - `backtest_results` |
| Summary | Aggregate stats | `/api/backtest/summary` | Database | On load | YES - `backtest_summary` |
| Best Strategies | Ranked strategies | `/api/backtest/best-strategies` | Database | On load | YES |
| **Individual Trades** | Trade-by-trade | NEW | Database | On load | **NOW YES** - `backtest_trades` |

**VERIFICATION:** You can now see every individual trade that makes up the backtest results.

---

## Charts (/charts)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Price History | OHLCV bars | `/api/market/price-history/{symbol}` | Polygon.io | On load | **NOW YES** - `price_history` |
| Technical Indicators | RSI, MACD, etc | Client-side | Calculated from price | Real-time | NO - Calculated |

---

## AI Copilot (/ai-copilot)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Chat History | Past conversations | Database | Local | On load | YES - `conversations` |
| AI Response | Analysis | `/api/ai/analyze` | Claude API | On request | **NOW YES** - `ai_analysis_history` |
| Market Context | Used for analysis | Multiple | All APIs | Per request | **NOW YES** |

---

## Position Sizing (/position-sizing)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Kelly Sizing | Full/Half/Quarter | `/api/position-sizing/calculate` | Calculated | On request | **NOW YES** - `position_sizing_history` |
| Risk Metrics | VaR, RoR | Calculated | Local | On request | **NOW YES** |

---

## Probability (/probability)

| Component | Data Displayed | API Endpoint | External Source | Update Freq | Stored? |
|-----------|---------------|--------------|-----------------|-------------|---------|
| Predictions | ML predictions | `/api/probability/predictions` | ML Model | On request | YES - `probability_predictions` |
| Outcomes | Actual results | `/api/probability/outcomes` | Trade results | On trade close | YES - `probability_outcomes` |
| Calibration | Model accuracy | `/api/probability/accuracy` | Calculated | On load | YES - `calibration_history` |
| Weights | Feature importance | `/api/probability/weights` | ML Model | On calibration | YES - `probability_weights` |

---

## NEW TABLES ADDED FOR ML/AI (November 2024)

These tables are NOW being populated when data flows through the system:

| Table | Purpose | Data Stored |
|-------|---------|-------------|
| `price_history` | Historical OHLCV | All price bars from Polygon |
| `greeks_snapshots` | Greeks at trade time | Delta, Gamma, Theta, Vega, IV |
| `vix_term_structure` | Full VIX curve | Spot, futures, contango |
| `options_flow` | Options activity | Volume, OI, unusual activity |
| `ai_analysis_history` | AI insights | All Claude analyses |
| `position_sizing_history` | Sizing decisions | Kelly calculations |
| `strategy_comparison_history` | Strategy picks | Comparison results |
| `market_snapshots` | Minute-by-minute | Complete market state |
| `backtest_trades` | Individual trades | Every backtest trade for verification |
| `backtest_runs` | Backtest metadata | Run configuration |
| `data_collection_log` | Collection tracking | When/what was collected |

---

## WebSocket Real-Time Updates

| Endpoint | Data | Update Frequency | Used By |
|----------|------|------------------|---------|
| `/ws/market-data` | Price, GEX summary | 30 seconds | Dashboard |
| `/ws/trader` | Trader status, positions | 10 seconds | Trader page |
| `/ws/positions` | Position updates | 5 seconds | Trader page |

---

## Data Collection Schedule

| Data Type | Collection Trigger | Frequency |
|-----------|-------------------|-----------|
| GEX Data | API request | Every GEX page load |
| Price History | Chart request | Every chart load |
| Greeks | Trade entry/exit | Per trade |
| VIX | VIX page load | On demand |
| Regime Signals | Psychology page | On demand |
| Market Snapshots | Background job | Every minute (market hours) |

---

## How to Verify Data is Real

Run the verification script:
```bash
cd /home/user/AlphaGEX
python scripts/verify_data_flow.py
```

This will:
1. Check every database table for data
2. Test every API endpoint
3. Verify timestamps are recent
4. Report what's working and what's not

---

## Summary

**BEFORE (Problems):**
- Price data fetched but NOT stored
- Greeks calculated but NOT stored
- AI analysis displayed but NOT stored
- Backtest trades NOT verifiable (only summaries)
- VIX term structure NOT stored

**AFTER (Fixed):**
- All external data is now stored when fetched
- Individual backtest trades are recorded
- AI analyses are logged for feedback loops
- Complete market snapshots every minute
- Full audit trail for verification

---

Last Updated: 2024-11-30
