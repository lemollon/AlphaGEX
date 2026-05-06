# Bot Registry & ML Systems

All trading bots are advised by PROPHET (Oracle) ML system.
Format: **DISPLAY_NAME (internal_codename)**

## Options Trading Bots

### FORTRESS (ARES) - SPY Iron Condor 0DTE ✓ LIVE
- **Schedule**: 8:30 AM - 3:30 PM CT, every 5 min
- **Strategy**: Iron Condor with dynamic strike selection on SPY
- **Files**: `trading/fortress_v2/`, `backend/api/routes/fortress_routes.py`
- **Trader class**: `FortressTrader`
- **29 API endpoints** - Most mature bot

### SOLOMON (ATHENA) - Directional Spreads ✓ LIVE
- **Schedule**: 8:35 AM - 2:30 PM CT, every 5 min
- **Strategy**: GEX-based directional spreads on SPY
- **Files**: `trading/solomon_v2/`, `backend/api/routes/solomon_routes.py`
- **Trader class**: `SolomonTrader`

### SAMSON (TITAN) - Aggressive SPX Iron Condor ✓ LIVE
- **Schedule**: Multiple trades daily with 30-min cooldown
- **Strategy**: Aggressive Iron Condor on SPX with tighter parameters
- **Parameters**: 15% risk/trade (vs 10%), 40% min win prob (vs 50%), 0.8 SD strikes
- **Files**: `trading/samson/`, `backend/api/routes/samson_routes.py`

### ANCHOR (PEGASUS) - SPX Weekly Iron Condor ✓ LIVE
- **Schedule**: Every 5 min during market hours
- **Strategy**: Standard SPX Iron Condor, more conservative than SAMSON
- **Files**: `trading/anchor/`, `backend/api/routes/anchor_routes.py`

### GIDEON (ICARUS) - Aggressive Directional ✓ LIVE
- **Schedule**: Every 5 min during market hours
- **Strategy**: Aggressive directional variant of SOLOMON on SPY
- **Files**: `trading/gideon/`, `backend/api/routes/gideon_routes.py`

### LAZARUS (PHOENIX) - 0DTE Options ⚠️ PAPER (Partial Implementation)
- **Schedule**: Every 5 min during market hours
- **Strategy**: 0DTE SPY/SPX options via AutonomousPaperTrader
- **Files**: `core/autonomous_paper_trader.py`
- **Note**: No dedicated API routes - uses internal trading logic only

### CORNERSTONE (ATLAS) - SPX Wheel ⚠️ LIVE (Partial Implementation)
- **Schedule**: Daily at 9:05 AM CT
- **Strategy**: SPX Wheel premium collection
- **Files**: `trading/spx_wheel_system.py`, `backend/api/routes/wheel_routes.py`
- **Dashboard**: `/cornerstone`

### SHEPHERD (HERMES) - Manual Wheel Manager (Not Automated)
- **Type**: Manual UI-driven bot, not scheduled
- **Strategy**: Manual wheel strategy management via frontend
- **Dashboard**: `/shepherd`

### FAITH - 2DTE Paper Iron Condor ⚠️ PAPER
- **Strategy**: Paper trading 2DTE Iron Condors for research
- **Files**: `trading/faith/`, `backend/api/routes/faith_routes.py`
- **Dashboard**: `/faith`

### GRACE - 1DTE Paper Iron Condor ⚠️ PAPER
- **Strategy**: Paper trading 1DTE Iron Condors for research
- **Files**: `trading/grace/`, `backend/api/routes/grace_routes.py`
- **Dashboard**: `/grace`

## Futures Trading

### VALOR (HERACLES) - MES Futures Scalping ✓ LIVE
- **Schedule**: During market hours
- **Strategy**: MES (Micro E-mini S&P 500) futures scalping via Tastytrade
- **Files**: `trading/valor/`, `backend/api/routes/valor_routes.py`
- **Trader class**: `ValorTrader`
- **Dashboard**: `/valor`

## Cryptocurrency Trading (AGAPE Family)

### AGAPE - ETH Micro Futures
- **Files**: `trading/agape/`, `backend/api/routes/agape_routes.py`

### AGAPE-SPOT - 24/7 Crypto Spot Trading ✓ LIVE
- **Exchange**: Coinbase Advanced Trade (spot only)
- **Tickers**: ETH-USD, BTC-USD, DOGE-USD, XRP-USD, SHIB-USD
- **Files**: `trading/agape_spot/`, `backend/api/routes/agape_spot_routes.py`
- **Dashboard**: `/agape-spot`
- **See**: `agape-spot.md` rule for full details

### AGAPE Perpetual Contracts (5 bots)
Each perpetual bot has its own directory and route file:
- **AGAPE-ETH-PERP**: `trading/agape_eth_perp/`, `agape_eth_perp_routes.py`
- **AGAPE-BTC-PERP**: `trading/agape_btc_perp/`, `agape_btc_perp_routes.py`
- **AGAPE-XRP-PERP**: `trading/agape_xrp_perp/`, `agape_xrp_perp_routes.py`
- **AGAPE-DOGE-PERP**: `trading/agape_doge_perp/`, `agape_doge_perp_routes.py`
- **AGAPE-SHIB-PERP**: `trading/agape_shib_perp/`, `agape_shib_perp_routes.py`

---

## ML Advisory Systems

### PROPHET (Oracle) - Primary Decision Maker
PROPHET is the central ML advisory system that all trading bots consult before taking positions.

- **Role**: Strategy recommendation (IC vs Directional), win probability estimation
- **Inputs**: WISDOM predictions, market regime, VIX levels, GEX data
- **Staleness Monitoring**: Tracks `hours_since_training`, `is_model_fresh`, `model_trained_at`
- **Training Sources**: Live outcomes → Database backtests → CHRONICLES data
- **Files**: `quant/prophet_advisor.py`, `backend/api/routes/prophet_routes.py`
- **Dashboard**: `/prophet`

### WISDOM (SAGE) - Strategic Algorithmic Guidance Engine
XGBoost-based ML system that feeds probability predictions into PROPHET.

- **Model**: XGBoost classifier for trade outcome prediction
- **Training Data**: CHRONICLES backtests, live trade outcomes
- **Features Used**:
  - Volatility: VIX, VIX percentile, VIX change, expected move
  - GEX: Regime, normalized value, distance to flip point
  - Timing: Day of week, price change, 30-day win rate
- **Capabilities**: Favorable condition identification, position sizing adjustment, calibrated probabilities
- **Limitations**: Cannot predict black swans, does not replace risk management
- **Files**: `backend/api/routes/ml_routes.py` (WISDOM endpoints)
- **Dashboard**: `/wisdom` page with 6 tabs

### STARS (ORION) - GEX Probability Models for WATCHTOWER/GLORY
STARS provides ML-powered probability predictions that guide WATCHTOWER (0DTE) and GLORY (Weekly) gamma visualizations.

- **Model**: 5 XGBoost sub-models (classifiers and regressors)
- **Sub-Models**:
  1. **Direction Probability** - UP/DOWN/FLAT classification
  2. **Flip Gravity** - Probability price moves toward flip point
  3. **Magnet Attraction** - Probability price reaches nearest magnet
  4. **Volatility Estimate** - Expected price range prediction
  5. **Pin Zone Behavior** - Probability of staying pinned between magnets
- **Integration**: Hybrid probability: `combined = (0.6 × ML_prob) + (0.4 × distance_prob)`
- **Auto-Training**: Every Sunday at 6:00 PM CT (after QUANT training at 5 PM)
- **Fallback**: When models not trained, uses 100% distance-based probability
- **Files**:
  - Core: `quant/gex_probability_models.py`
  - Shared Engine: `core/shared_gamma_engine.py`
  - WATCHTOWER Engine: `core/watchtower_engine.py`
  - Scheduler: `scheduler/trader_scheduler.py`
- **API Endpoints**:
  ```
  GET  /api/ml/gex-models/status
  POST /api/ml/gex-models/train
  POST /api/ml/gex-models/predict
  GET  /api/ml/gex-models/data-status
  ```
- **Dashboard**: `/gex-ml`

### COUNSELOR (GEXIS) - AI Trading Assistant
J.A.R.V.I.S.-style AI chatbot providing decision support throughout the platform.

- **Personality**: Time-aware greetings, Central Time, professional demeanor, "Optionist Prime" user
- **Files** (11+ modules in `ai/`):
  - `counselor_personality.py` - Core identity and prompts
  - `counselor_tools.py` - 17 agentic tools (database, market data, bot control)
  - `counselor_knowledge.py` - Knowledge base (285+ database tables documented)
  - `counselor_commands.py` - Slash commands (`/market-hours`, `/suggestion`, `/risk`)
  - `counselor_learning_memory.py` - Self-improving prediction accuracy tracking
  - `counselor_extended_thinking.py` - Claude Extended Thinking for complex analysis
  - `counselor_cache.py` - TTL-based caching (60s market, 30s positions)
  - `counselor_rate_limiter.py` - Token bucket rate limiting
  - `counselor_tracing.py` - Request tracing and telemetry
- **Frontend**: `FloatingChatbot.tsx` - Streaming chat widget
- **API Routes**: `backend/api/routes/ai_routes.py` - 35+ endpoints
- **Dashboard**: `/counselor-commands`

### DISCERNMENT (APOLLO) - ML Scanner
- **Files**: `core/discernment_ml_engine.py`, `core/discernment_outcome_tracker.py`
- **Routes**: `backend/api/routes/discernment_routes.py`
- **Dashboard**: `/discernment`

### PROVERBS - Feedback Loop Intelligence
- **Files**: `quant/proverbs_feedback_loop.py`, `proverbs_ai_analyst.py`, `proverbs_enhancements.py`, `proverbs_notifications.py`
- **Routes**: `backend/api/routes/proverbs_routes.py`
- **Dashboard**: `/proverbs`

### CHRONICLES (KRONOS) - Backtesting Engine
- **Files**: `quant/chronicles_gex_calculator.py`, `backend/services/`
- **Routes**: `backend/api/routes/spx_backtest_routes.py`

### GLORY (HYPERION) - Weekly Gamma Analysis
- **Routes**: `backend/api/routes/glory_routes.py`
- **Dashboard**: `/glory`

### COVENANT (NEXUS) - Neural Network Visualization
- **Dashboard**: `/covenant`, `/covenant-demo`

---

## Removed Legacy Systems (January 2025)

Removed in favor of **PROPHET (Oracle) as the sole decision authority**:

- **Circuit Breaker**: `trading/circuit_breaker.py` - DELETED. PROPHET provides all risk management.
- **Ensemble Strategy**: `quant/ensemble_strategy.py` - DELETED. "PROPHET is god." API returns unavailable.
- **ML Regime Classifier**: `quant/ml_regime_classifier.py` - DELETED. Routes handle module absence.
- **GEX Directional ML**: Removed from all bot signal files. Redundant with PROPHET.
- **Kill Switch**: Removed. "Always allow trading" - PROPHET controls trade frequency.
- **Daily Trade Limits**: Removed from FORTRESS, GIDEON. PROPHET decides frequency.
- **LangChain AI System**: All `ai/langchain_*.py` files deleted. COUNSELOR replaces via direct Anthropic SDK. API endpoints return 503 with redirect.
- **Solomon Enhancements**: `quant/solomon_enhancements.py` - DELETED. PROPHET absorbed functionality.
