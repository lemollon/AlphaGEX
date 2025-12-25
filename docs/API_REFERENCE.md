# AlphaGEX API Reference

## Base URL

| Environment | URL |
|-------------|-----|
| Production | `https://your-app.onrender.com` |
| Local | `http://localhost:8000` |

---

## Authentication

Currently, the API does not require authentication. Future versions will support API key authentication.

---

## Health & Status

### GET /health

Check if the server and database are operational.

**Request:**
```bash
curl https://your-app.onrender.com/health
```

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0",
  "timestamp": "2025-12-25T14:30:00Z"
}
```

**Status Codes:**
| Code | Description |
|------|-------------|
| 200 | Server healthy |
| 503 | Database connection failed |

---

## GEX (Gamma Exposure) Endpoints

### GET /api/gex/{symbol}

Fetch current GEX data for a symbol.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | path | Yes | Stock symbol (SPY, QQQ, SPX) |

**Request:**
```bash
curl https://your-app.onrender.com/api/gex/SPY
```

**Response:**
```json
{
  "symbol": "SPY",
  "spot_price": 585.42,
  "net_gex": 2450000000,
  "call_wall": 590,
  "put_wall": 575,
  "gex_flip_point": 580,
  "gamma_tilt": "bullish",
  "timestamp": "2025-12-25T14:30:00Z",
  "strikes": [
    {
      "strike": 580,
      "call_gamma": 1250000,
      "put_gamma": -850000,
      "net_gamma": 400000
    }
  ]
}
```

**Status Codes:**
| Code | Description |
|------|-------------|
| 200 | Success |
| 404 | Symbol not found |
| 502 | External API error |

---

### GET /api/gex/{symbol}/regime

Get market regime classification.

**Request:**
```bash
curl https://your-app.onrender.com/api/gex/SPY/regime
```

**Response:**
```json
{
  "regime": "POSITIVE_GAMMA",
  "confidence": 85,
  "recommended_action": "SELL_PREMIUM",
  "indicators": {
    "gex_signal": "BULLISH",
    "vix_signal": "LOW_VOL",
    "trend_signal": "UPTREND",
    "momentum": "STRONG"
  },
  "analysis": "Positive GEX with uptrend suggests mean reversion environment. Sell premium strategies favored."
}
```

**Regime Values:**
| Regime | Description |
|--------|-------------|
| POSITIVE_GAMMA | Dealers hedge by selling rallies, buying dips |
| NEGATIVE_GAMMA | Dealers amplify moves, momentum environment |
| NEUTRAL | Low conviction, choppy conditions |

---

### GET /api/gex/{symbol}/profile

Get detailed GEX profile with all strikes.

**Request:**
```bash
curl https://your-app.onrender.com/api/gex/SPY/profile
```

**Response:**
```json
{
  "symbol": "SPY",
  "spot_price": 585.42,
  "expiration": "2025-01-17",
  "profile": {
    "net_gex": 2450000000,
    "call_wall": 590,
    "put_wall": 575,
    "flip_point": 580,
    "hvm_level": 585,
    "charm_flow": "positive"
  },
  "strikes": [
    {
      "strike": 575,
      "call_oi": 15000,
      "put_oi": 45000,
      "call_gamma": 500000,
      "put_gamma": -2100000,
      "net_gamma": -1600000,
      "delta_dollars": -125000000
    }
  ]
}
```

---

## VIX Endpoints

### GET /api/vix/current

Get current VIX level and IV metrics.

**Request:**
```bash
curl https://your-app.onrender.com/api/vix/current
```

**Response:**
```json
{
  "vix": 18.5,
  "iv_rank": 45,
  "iv_percentile": 42,
  "vix_term_structure": "contango",
  "vix_1m": 17.2,
  "vix_3m": 19.8,
  "is_live": true,
  "source": "polygon",
  "timestamp": "2025-12-25T14:30:00Z"
}
```

**IV Rank Interpretation:**
| Range | Meaning |
|-------|---------|
| 0-20 | Very low IV, buy premium |
| 20-40 | Low IV |
| 40-60 | Normal IV |
| 60-80 | High IV, sell premium |
| 80-100 | Very high IV |

---

## Trader Endpoints

### GET /api/trader/status

Get current autonomous trader status.

**Request:**
```bash
curl https://your-app.onrender.com/api/trader/status
```

**Response:**
```json
{
  "status": "ACTIVE",
  "mode": "PAPER",
  "current_strategy": "BULL_PUT_SPREAD",
  "regime": "POSITIVE_GAMMA",
  "confidence": 85,
  "last_signal_time": "2025-12-25T14:30:00Z",
  "next_evaluation": "2025-12-25T15:00:00Z",
  "open_positions": 2,
  "daily_pnl": 350.00,
  "circuit_breaker": {
    "status": "OK",
    "daily_loss": 150.00,
    "max_daily_loss": 500.00
  }
}
```

**Status Values:**
| Status | Description |
|--------|-------------|
| ACTIVE | Trading normally |
| PAUSED | Manually paused |
| CIRCUIT_BREAKER | Halted due to losses |
| MARKET_CLOSED | Outside trading hours |
| ERROR | System error |

---

### GET /api/trader/positions

Get all open positions.

**Request:**
```bash
curl https://your-app.onrender.com/api/trader/positions
```

**Response:**
```json
{
  "positions": [
    {
      "id": 123,
      "symbol": "SPY",
      "strategy": "BULL_PUT_SPREAD",
      "direction": "BULLISH",
      "legs": [
        {
          "strike": 580,
          "type": "PUT",
          "action": "SELL",
          "contracts": 5,
          "entry_price": 2.50
        },
        {
          "strike": 575,
          "type": "PUT",
          "action": "BUY",
          "contracts": 5,
          "entry_price": 1.25
        }
      ],
      "entry_price": 1.25,
      "current_price": 0.85,
      "entry_time": "2025-12-25T10:30:00Z",
      "expiration": "2025-01-17",
      "dte": 23,
      "unrealized_pnl": 200.00,
      "unrealized_pnl_pct": 32.0,
      "status": "OPEN",
      "profit_target_pct": 50,
      "stop_loss_pct": 200
    }
  ],
  "total_unrealized_pnl": 200.00,
  "total_positions": 1
}
```

---

### GET /api/trader/performance

Get trading performance metrics.

**Request:**
```bash
curl https://your-app.onrender.com/api/trader/performance
```

**Query Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| days | int | 30 | Lookback period |

**Response:**
```json
{
  "period_days": 30,
  "total_trades": 47,
  "winning_trades": 32,
  "losing_trades": 15,
  "win_rate": 68.1,
  "total_pnl": 2450.00,
  "avg_win": 125.50,
  "avg_loss": -85.30,
  "profit_factor": 2.94,
  "max_drawdown": -450.00,
  "max_drawdown_pct": 0.9,
  "sharpe_ratio": 1.85,
  "best_trade": 450.00,
  "worst_trade": -225.00,
  "by_strategy": {
    "BULL_PUT_SPREAD": {
      "trades": 25,
      "win_rate": 72.0,
      "pnl": 1850.00
    },
    "IRON_CONDOR": {
      "trades": 15,
      "win_rate": 60.0,
      "pnl": 450.00
    }
  },
  "daily_pnl": [
    {"date": "2025-12-24", "pnl": 150.00},
    {"date": "2025-12-23", "pnl": -50.00}
  ]
}
```

---

### POST /api/trader/pause

Pause autonomous trading.

**Request:**
```bash
curl -X POST https://your-app.onrender.com/api/trader/pause \
  -H "Content-Type: application/json" \
  -d '{"reason": "Manual pause for review"}'
```

**Response:**
```json
{
  "success": true,
  "status": "PAUSED",
  "paused_at": "2025-12-25T14:30:00Z",
  "reason": "Manual pause for review"
}
```

---

### POST /api/trader/resume

Resume autonomous trading.

**Request:**
```bash
curl -X POST https://your-app.onrender.com/api/trader/resume
```

**Response:**
```json
{
  "success": true,
  "status": "ACTIVE",
  "resumed_at": "2025-12-25T14:30:00Z"
}
```

---

## Backtest Endpoints

### GET /api/backtests/results

Get backtest and live trade results.

**Query Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| limit | int | 10 | Number of results |
| strategy | string | null | Filter by strategy |

**Request:**
```bash
curl "https://your-app.onrender.com/api/backtests/results?limit=5&strategy=BULL_PUT_SPREAD"
```

**Response:**
```json
{
  "recent_trades": [
    {
      "id": 456,
      "symbol": "SPY",
      "strategy": "BULL_PUT_SPREAD",
      "entry_time": "2025-12-20T10:30:00Z",
      "exit_time": "2025-12-24T14:00:00Z",
      "entry_price": 1.25,
      "exit_price": 0.50,
      "pnl": 375.00,
      "pnl_pct": 60.0,
      "exit_reason": "PROFIT_TARGET"
    }
  ],
  "strategy_stats": {
    "BULL_PUT_SPREAD": {
      "total_trades": 47,
      "win_rate": 68.1,
      "avg_win_pct": 12.5,
      "avg_loss_pct": 22.3,
      "expectancy": 3.42,
      "profit_factor": 2.15,
      "last_updated": "2025-12-25T16:00:00Z"
    }
  }
}
```

---

### GET /api/backtests/smart-recommendations

Get AI-powered trade recommendations.

**Request:**
```bash
curl https://your-app.onrender.com/api/backtests/smart-recommendations
```

**Response:**
```json
{
  "recommendations": [
    {
      "strategy": "BULL_PUT_SPREAD",
      "symbol": "SPY",
      "confidence": 85,
      "reasoning": "Positive GEX environment with high IV rank (65%). Historical win rate 68% in similar conditions.",
      "suggested_strikes": {
        "short_put": 580,
        "long_put": 575
      },
      "suggested_expiration": "2025-01-17",
      "suggested_size": 5,
      "expected_credit": 1.25,
      "max_loss": 375.00,
      "risk_reward": "3.3:1"
    }
  ],
  "market_context": {
    "regime": "POSITIVE_GAMMA",
    "vix": 18.5,
    "iv_rank": 65,
    "trend": "UPTREND"
  }
}
```

---

## Gamma Intelligence Endpoints

### GET /api/gamma/intelligence

Get comprehensive gamma analysis.

**Query Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Stock symbol |
| vix | float | No | Override VIX value |

**Request:**
```bash
curl "https://your-app.onrender.com/api/gamma/intelligence?symbol=SPY"
```

**Response:**
```json
{
  "symbol": "SPY",
  "analysis": {
    "regime": "POSITIVE_GAMMA",
    "conviction": "HIGH",
    "bias": "BULLISH",
    "key_levels": {
      "call_wall": 590,
      "put_wall": 575,
      "flip_point": 580,
      "hvm": 585
    },
    "expected_range": {
      "low": 578,
      "high": 592,
      "confidence": 68
    }
  },
  "trade_setup": {
    "strategy": "BULL_PUT_SPREAD",
    "short_strike": 580,
    "long_strike": 575,
    "credit": 1.25,
    "pop": 72,
    "expected_value": 45.00
  },
  "risk_factors": [
    "FOMC meeting in 3 days",
    "VIX near support at 18"
  ]
}
```

---

### GET /api/gamma/probabilities

Get strike probability analysis.

**Request:**
```bash
curl "https://your-app.onrender.com/api/gamma/probabilities?symbol=SPY&vix=18.5"
```

**Response:**
```json
{
  "symbol": "SPY",
  "spot_price": 585.42,
  "probabilities": [
    {
      "strike": 575,
      "prob_below": 15.2,
      "prob_at": 3.1,
      "prob_above": 81.7
    },
    {
      "strike": 580,
      "prob_below": 28.5,
      "prob_at": 4.2,
      "prob_above": 67.3
    },
    {
      "strike": 585,
      "prob_below": 48.2,
      "prob_at": 5.1,
      "prob_above": 46.7
    }
  ],
  "expected_move": {
    "1_day": 1.2,
    "7_day": 3.5,
    "30_day": 7.2
  }
}
```

---

## Psychology Endpoints

### GET /api/psychology/alerts

Get psychological trap detection alerts.

**Request:**
```bash
curl https://your-app.onrender.com/api/psychology/alerts
```

**Response:**
```json
{
  "alerts": [
    {
      "type": "FOMO_WARNING",
      "severity": "MEDIUM",
      "message": "Market up 3 days in a row. Avoid chasing momentum.",
      "recommendation": "Wait for pullback to key support at 580"
    },
    {
      "type": "FALSE_FLOOR",
      "severity": "HIGH",
      "message": "Put wall at 575 may not hold if GEX turns negative",
      "recommendation": "Reduce position size below flip point"
    }
  ],
  "liberation_setups": [
    {
      "type": "GAMMA_SQUEEZE",
      "probability": 35,
      "trigger_level": 592,
      "target": 600
    }
  ]
}
```

---

## Price History Endpoints

### GET /api/price-history

Get historical price data.

**Query Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Stock symbol |
| range | string | No | Time range (1d, 5d, 1mo, 3mo, 1y) |
| interval | string | No | Bar interval (1m, 5m, 15m, 1h, 1d) |

**Request:**
```bash
curl "https://your-app.onrender.com/api/price-history?symbol=SPY&range=1d&interval=5m"
```

**Response:**
```json
{
  "symbol": "SPY",
  "bars": [
    {
      "timestamp": "2025-12-25T09:30:00Z",
      "open": 584.50,
      "high": 585.20,
      "low": 584.30,
      "close": 585.00,
      "volume": 1250000
    }
  ],
  "metadata": {
    "range": "1d",
    "interval": "5m",
    "bar_count": 78
  }
}
```

---

## SPX Wheel Endpoints

### GET /api/wheel/positions

Get SPX wheel strategy positions.

**Request:**
```bash
curl https://your-app.onrender.com/api/wheel/positions
```

**Response:**
```json
{
  "positions": [
    {
      "id": 789,
      "option_ticker": "SPXW250117P05800",
      "strike": 5800,
      "expiration": "2025-01-17",
      "contracts": 1,
      "entry_price": 12.50,
      "current_price": 8.25,
      "premium_received": 1250.00,
      "unrealized_pnl": 425.00,
      "status": "OPEN",
      "dte": 23
    }
  ],
  "summary": {
    "total_premium_collected": 15750.00,
    "total_realized_pnl": 12500.00,
    "total_unrealized_pnl": 425.00,
    "open_positions": 1,
    "win_rate": 82.5
  }
}
```

---

### GET /api/wheel/parameters

Get current wheel strategy parameters.

**Request:**
```bash
curl https://your-app.onrender.com/api/wheel/parameters
```

**Response:**
```json
{
  "parameters": {
    "target_delta": 0.15,
    "target_dte": 45,
    "min_premium": 500,
    "max_contracts": 2,
    "profit_target_pct": 50,
    "stop_loss_pct": 200,
    "roll_at_dte": 7
  },
  "last_optimized": "2025-12-20T00:00:00Z",
  "optimization_source": "backtest"
}
```

---

## Error Responses

All endpoints return errors in a consistent format:

```json
{
  "error": true,
  "code": "SYMBOL_NOT_FOUND",
  "message": "Symbol 'INVALID' not found in our database",
  "details": {
    "requested_symbol": "INVALID",
    "valid_symbols": ["SPY", "QQQ", "SPX", "IWM"]
  }
}
```

**Common Error Codes:**
| Code | HTTP Status | Description |
|------|-------------|-------------|
| SYMBOL_NOT_FOUND | 404 | Invalid symbol |
| RATE_LIMITED | 429 | Too many requests |
| EXTERNAL_API_ERROR | 502 | Upstream API failed |
| DATABASE_ERROR | 500 | Database query failed |
| VALIDATION_ERROR | 422 | Invalid request parameters |
| UNAUTHORIZED | 401 | Missing/invalid auth |

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| /api/gex/* | 60 requests | Per minute |
| /api/trader/* | 30 requests | Per minute |
| /api/gamma/* | 30 requests | Per minute |
| All others | 120 requests | Per minute |

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1703515200
```

---

## WebSocket Endpoints

### WS /ws/gex/{symbol}

Real-time GEX updates.

**Connect:**
```javascript
const ws = new WebSocket('wss://your-app.onrender.com/ws/gex/SPY');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('GEX update:', data);
};
```

**Message Format:**
```json
{
  "type": "GEX_UPDATE",
  "symbol": "SPY",
  "net_gex": 2450000000,
  "spot_price": 585.42,
  "timestamp": "2025-12-25T14:30:00Z"
}
```

### WS /ws/trades

Real-time trade notifications.

**Message Types:**
```json
{
  "type": "TRADE_OPENED",
  "position_id": 123,
  "strategy": "BULL_PUT_SPREAD",
  "symbol": "SPY"
}
```

```json
{
  "type": "TRADE_CLOSED",
  "position_id": 123,
  "pnl": 375.00,
  "exit_reason": "PROFIT_TARGET"
}
```
