# API Structure & Database Schema

## Route Naming Convention
- All routes in `backend/api/routes/`, pattern: `*_routes.py`
- Router prefix matches domain (e.g., `/api/gex/`, `/api/fortress/`)
- Bot routes use biblical display names in URLs (`/api/fortress/` not `/api/ares/`)

## Key API Endpoints

```
# Health & System
GET  /health                    # System health check
GET  /api/system-health         # Comprehensive health (includes PROPHET staleness)
GET  /ready                     # Readiness probe

# GEX Data
GET  /api/gex/{symbol}          # GEX data for symbol
GET  /api/gex/{symbol}/levels   # Support/resistance levels
GET  /api/gamma/0dte            # 0DTE gamma expiration data

# WATCHTOWER (Real-time 0DTE Gamma)
GET  /api/watchtower/snapshot        # Full gamma snapshot with market structure
GET  /api/watchtower/history         # Historical gamma for sparklines
GET  /api/watchtower/danger-zones    # Active danger zone alerts
GET  /api/watchtower/trade-action    # Actionable trade recommendation
POST /api/watchtower/signals/log     # Log signal for tracking
GET  /api/watchtower/signals/recent  # Recent signals with outcomes
GET  /api/watchtower/signals/performance # Win rate, P&L, stats

# Trading Bots (20+ bots, 200+ endpoints total)
GET  /api/fortress/status       # FORTRESS bot status
POST /api/fortress/analyze      # Analyze IC opportunity
GET  /api/solomon/status        # SOLOMON bot status
GET  /api/samson/status         # SAMSON bot status
GET  /api/samson/positions      # SAMSON open positions
GET  /api/samson/equity-curve   # SAMSON equity curve
GET  /api/anchor/status         # ANCHOR bot status
GET  /api/gideon/status         # GIDEON bot status
GET  /api/valor/status          # VALOR bot status
GET  /api/trader/performance    # Unified trading performance

# PROPHET (ML Advisory)
GET  /api/prophet/health        # PROPHET health with staleness
GET  /api/prophet/status        # Detailed status
POST /api/prophet/strategy-recommendation  # IC vs Directional
GET  /api/prophet/vix-regimes   # VIX regime definitions

# WISDOM (ML Predictions)
GET  /api/ml/sage/status        # WISDOM model status
POST /api/ml/sage/predict       # Run prediction
POST /api/ml/sage/train         # Trigger training

# AI & COUNSELOR (35+ endpoints)
POST /api/ai/analyze            # AI market analysis
POST /api/ai/gexis/agentic-chat # Full agentic chat with tools
POST /api/ai/gexis/agentic-chat/stream  # Streaming responses
POST /api/ai/gexis/extended-thinking    # Deep analysis mode

# Transparency & Logging
GET  /api/logs/summary          # Summary of all 22+ log tables
GET  /api/logs/bot-decisions    # All bot trading decisions
GET  /api/data-transparency/regime-signals  # All 80+ regime signals
```

---

## Database Schema (285+ tables)

### Core Trading Tables
- `autonomous_open_positions`, `autonomous_closed_trades`, `autonomous_trade_log`
- `unified_trades`, `trading_decisions`

### Bot-Specific Tables (pattern: `{bot}_*`)
Each bot (FORTRESS, SOLOMON, SAMSON, ANCHOR, GIDEON, VALOR, FAITH, GRACE) has:
- `{bot}_positions`, `{bot}_closed_trades`, `{bot}_equity_snapshots`, `{bot}_scan_activity`, `{bot}_config`

### Crypto Tables (AGAPE family)
- `agape_spot_positions`, `agape_spot_scan_activity`, `agape_spot_win_tracker`, `agape_spot_equity_snapshots`, `agape_spot_ml_shadow`

### ML & PROPHET Tables
- `prophet_predictions`, `ml_decision_logs`, `sage_training_history`, `ml_model_metadata`, `proverbs_*` (12+)

### Analytics Tables
- `gex_history`, `gamma_history`, `regime_classifications` (80+ columns), `backtest_results`, `drift_analysis`

### Logging Tables (22+)
- `ai_analysis_history`, `psychology_analysis`, `wheel_activity_log`, `gex_change_log`, `fortress_ml_outcomes`

### Configuration Tables
- `autonomous_config`, `alerts`, `push_subscriptions`
