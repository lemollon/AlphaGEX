"""
COUNSELOR Comprehensive Knowledge Base

This module contains ALL knowledge COUNSELOR needs about:
- Database tables (49 tables)
- System architecture
- Trading strategies
- Bot configurations
- Deployment infrastructure
- Economic calendar
"""

# =============================================================================
# DATABASE SCHEMA - ALL 49 TABLES
# =============================================================================

DATABASE_TABLES = """
=== CORE TRADING TABLES ===

fortress_positions:
  - Primary table for FORTRESS Iron Condor positions
  - Columns: position_id, open_date, close_date, expiration, status (open/closed/expired)
  - Columns: put_spread, call_spread, contracts, total_credit, realized_pnl
  - Columns: underlying_at_entry, vix_at_entry, entry_reason
  - Used by: FORTRESS bot, FORTRESS dashboard, P&L calculations

fortress_daily_performance:
  - Daily P&L tracking for FORTRESS
  - Columns: trade_date, daily_pnl, cumulative_pnl, win_count, loss_count
  - Used for: Equity curve, performance metrics

decision_logs:
  - Every trading decision with full reasoning
  - Columns: timestamp, bot_name, decision_type, action, reasoning, market_data
  - Critical for: Audit trail, learning system, debugging

bot_decision_logs:
  - Structured bot decision records
  - Columns: created_at, bot_name, decision, confidence, factors, outcome

autonomous_positions:
  - All autonomous trading positions
  - Columns: position_id, symbol, strategy, entry_price, exit_price, pnl, status

autonomous_trade_log:
  - Execution log for all trades
  - Columns: trade_id, timestamp, action, symbol, quantity, price, fees

wheel_cycles:
  - SPX Wheel strategy cycles
  - Columns: cycle_id, start_date, end_date, status, premium_collected, outcome

=== GEX DATA TABLES ===

gex_snapshots:
  - Point-in-time GEX readings
  - Columns: symbol, timestamp, spot_price, gex_value, call_wall, put_wall
  - Columns: zero_gamma, gex_flip, regime, data_source

gex_history:
  - Historical GEX data for backtesting
  - Columns: timestamp, symbol, net_gex, flip_point, call_wall, put_wall

gex_snapshots_detailed:
  - Strike-by-strike gamma exposure
  - Columns: snapshot_id, strike, call_gamma, put_gamma, net_gamma, open_interest

gamma_levels:
  - Key gamma levels (walls, magnets)
  - Columns: symbol, timestamp, strike, gamma_exposure, level_type

gamma_strike_history:
  - Historical gamma by strike over time
  - Used for: Pattern recognition, strike selection

regime_signals:
  - Market regime classifications over time
  - Columns: timestamp, regime, confidence, factors

=== AI/ML TABLES ===

prophet_predictions:
  - AI trading predictions
  - Columns: created_at, symbol, prediction, confidence, win_probability
  - Columns: suggested_put_strike, suggested_call_strike, reasoning

probability_weights:
  - Calibrated probability system weights
  - Columns: weight_name, gex_wall_strength, volatility_impact
  - Columns: psychology_signal, mm_positioning, historical_pattern
  - Columns: active, calibration_count

ai_predictions:
  - Every AI prediction for learning
  - Columns: prediction_id, timestamp, prediction, confidence, actual_outcome

ai_performance:
  - Daily AI accuracy tracking
  - Columns: date, predictions_made, correct_predictions, accuracy

ml_predictions:
  - ML model predictions
  - Columns: model_name, timestamp, prediction, features, confidence

ml_models:
  - ML model metadata and versioning
  - Columns: model_id, model_type, version, accuracy, trained_at

calibration_history:
  - Probability weight calibration history
  - Columns: calibration_date, old_weights, new_weights, trigger_reason

=== VIX & VOLATILITY TABLES ===

vix_data:
  - VIX snapshots and term structure
  - Columns: timestamp, vix_spot, vix_1m, vix_3m, vvix, term_structure

vix_term_structure:
  - Detailed VIX futures term structure
  - Columns: timestamp, m1, m2, m3, m4, contango_pct

=== CONFIGURATION TABLES ===

autonomous_config:
  - Bot configuration settings
  - Columns: config_name, value, bot_name, last_updated

strategy_config:
  - Strategy parameter settings
  - Columns: strategy_name, parameters (JSON), active

=== MARKET DATA TABLES ===

market_data:
  - General market data snapshots
  - Columns: timestamp, symbol, price, volume, change_pct

market_data_daily:
  - Daily OHLCV data
  - Columns: date, symbol, open, high, low, close, volume

options_chain_snapshots:
  - Full options chain captures
  - Columns: snapshot_time, symbol, expiration, strikes (JSON)

price_history:
  - Historical price data
  - Columns: symbol, date, open, high, low, close, adj_close

=== CONVERSATION & LEARNING TABLES ===

conversation_history:
  - COUNSELOR chat history
  - Columns: session_id, user_message, assistant_response, timestamp

conversations:
  - Conversation metadata
  - Columns: conversation_id, user_id, started_at, last_message_at

=== BACKTEST TABLES ===

backtest_runs:
  - Backtest execution records
  - Columns: run_id, strategy, start_date, end_date, parameters

backtest_results:
  - Aggregated backtest results
  - Columns: run_id, total_return, win_rate, sharpe_ratio, max_drawdown

backtest_trades:
  - Individual trades from backtests
  - Columns: run_id, trade_id, entry_date, exit_date, pnl

=== ALERT TABLES ===

alerts:
  - Active trading alerts
  - Columns: alert_id, type, condition, triggered_at, status

alert_history:
  - Historical alerts
  - Columns: alert_id, created_at, triggered_at, dismissed_at

=== OTHER KEY TABLES ===

account_state:
  - Account balance and equity tracking
  - Columns: timestamp, balance, equity, margin_used

trade_history:
  - Complete trade history across all strategies
  - Columns: trade_id, strategy, symbol, entry, exit, pnl

pattern_learning:
  - Pattern-specific win rates for learning
  - Columns: pattern_name, occurrences, wins, losses, avg_pnl
"""

# =============================================================================
# SYSTEM ARCHITECTURE
# =============================================================================

SYSTEM_ARCHITECTURE = """
=== ALPHAGEX ARCHITECTURE ===

DEPLOYMENT INFRASTRUCTURE:

1. Render Services:
   - alphagex-api (Web Service)
     * FastAPI backend
     * Port 8000
     * Health check: /health
     * Auto-deploy from main branch

   - alphagex-trader (Background Worker)
     * Runs FORTRESS bot scheduler
     * Checks trading windows
     * Executes trades via Tradier

   - alphagex-collector (Background Worker)
     * Collects GEX data
     * Updates market snapshots
     * Runs every 15 minutes during market hours

   - alphagex-db (PostgreSQL)
     * 127 tables
     * Persistent storage

2. Vercel Frontend:
   - Next.js 14 with App Router
   - React Server Components
   - Tailwind CSS
   - Real-time updates via polling

=== SIGNAL FLOW ===

Data Collection:
```
Trading Volatility API → alphagex-collector → gex_snapshots table
Tradier API → alphagex-collector → market_data table
```

Signal Generation:
```
gex_snapshots → CHRONICLES (GEX Calculator) → regime_signals
regime_signals → PROPHET (AI Advisor) → prophet_predictions
prophet_predictions → Bots (FORTRESS/SOLOMON) → decision_logs
```

Trade Execution:
```
Bot Decision → Tradier API → Order Placed → fortress_positions updated
Position Monitor → Check Greeks → Alert if needed
Expiration/Exit → realized_pnl calculated → performance updated
```

=== API ARCHITECTURE ===

Backend Routes:
- /api/ai/* - COUNSELOR chat, analysis, learning
- /api/fortress/* - FORTRESS bot control and status
- /api/solomon/* - SOLOMON bot control
- /api/gex/* - GEX data endpoints
- /api/vix/* - VIX data endpoints
- /api/autonomous/* - Bot orchestration
- /api/probability/* - Probability system

Key Files:
- backend/main.py - FastAPI app, CORS, startup
- backend/api/routes/ai_routes.py - COUNSELOR endpoints (1,700+ lines)
- backend/api/routes/fortress_routes.py - FORTRESS endpoints
- backend/api/dependencies.py - Shared instances

=== FRONTEND ARCHITECTURE ===

Pages by Category:

MAIN:
- /dashboard - Main dashboard with system overview
- /daily-manna - Daily market insights and trading guidance
- /covenant - COVENANT Neural Network visualization (3D interactive)

ANALYSIS:
- /gex - GEX Analysis multi-ticker view
- /gex/history - Historical GEX data and trends
- /watchtower - WATCHTOWER 0DTE Gamma real-time visualization

TRADING:
- /discernment - DISCERNMENT ML-powered options scanner

AI & TESTING:
- /zero-dte-backtest - CHRONICLES 0DTE Condor backtester
- /prophet - PROPHET AI Trading Advisor
- /proverbs - PROVERBS Feedback Loop and learning system

LIVE TRADING:
- /fortress - FORTRESS Iron Condor dashboard (SPX live/SPY sandbox)
- /solomon - SOLOMON Directional Spreads dashboard

VOLATILITY:
- /vix - VIX Dashboard with term structure
- /volatility-comparison - IV vs HV comparison
- /alerts - Trading alerts management

BETA FEATURES:
- /jubilee - JUBILEE ML prediction system
- /trader - LAZARUS SPY 0DTE trading
- /wheel - SHEPHERD Manual Wheel strategy
- /spx-wheel - CORNERSTONE SPX Wheel automation
- /spx - SPX Institutional flow analysis

SYSTEM:
- /counselor-commands - COUNSELOR command reference
- /settings/system - System configuration
- /settings/notifications - Alert preferences
- /database - Database admin panel
- /logs - Decision logs and audit trail
- /data-transparency - Data source transparency
- /system/processes - Background process monitoring
- /feature-docs - Feature documentation

Components:
- FloatingChatbot.tsx - COUNSELOR chat widget (always visible, supports markdown)
- Covenant3D.tsx - 3D neural network visualization
- Navigation.tsx - Sidebar navigation with market status
- DecisionLogViewer.tsx - Trade decision audit trail
- EquityCurveChart.tsx - Live equity tracking
"""

# =============================================================================
# TRADING STRATEGIES
# =============================================================================

TRADING_STRATEGIES = """
=== FORTRESS STRATEGY (0DTE Iron Condor) ===

Overview:
- Trades 0DTE (same-day expiry) Iron Condors on SPX
- Uses SPY in sandbox mode (Tradier doesn't support SPX options in sandbox)
- Target: 10% monthly returns via daily compounding

Configuration:
- Entry Time: 10:15 AM ET (after morning volatility settles)
- Exit: Let expire worthless OR stop loss at 200% of credit
- Spread Width: $10 for SPX, $2 for SPY
- Strike Distance: 1 Standard Deviation from current price
- Risk Per Trade: 10% of capital (aggressive Kelly)
- Contracts: Calculated based on risk and max loss

Entry Criteria:
1. Trading window open (10:00 AM - 3:00 PM ET)
2. VIX within acceptable range (12-35)
3. Not within 30 min of major news event
4. Sufficient premium available (min $1.50 SPX / $0.15 SPY)

Position Sizing:
- Max Loss = Spread Width - Credit Received
- Position Size = (Capital × Risk%) / Max Loss
- Round down to nearest contract

P&L Tracking:
- Daily P&L recorded in fortress_daily_performance
- Position details in fortress_positions
- All decisions logged in decision_logs

=== SOLOMON STRATEGY (Directional Spreads) ===

Overview:
- GEX-based directional credit spreads
- Uses wall proximity for edge
- Trades bull call spreads or bear put spreads

Signal Sources:
1. PRIMARY: GEX ML Signal (trained classifier)
2. FALLBACK: Prophet AI Advisor

Entry Criteria:
- Price within 0.5-1% of gamma wall
- Clear directional signal (bullish/bearish)
- Confidence > 60%
- VIX regime favorable

Wall Filter Logic:
- Near Call Wall → Bearish bias → Bear Call Spread
- Near Put Wall → Bullish bias → Bull Put Spread
- Backtest shows 90-98% win rate with wall filter

=== CORNERSTONE STRATEGY (SPX Wheel) ===

Overview:
- Cash-secured put selling on SPX
- 45 DTE, 20-delta puts
- Roll or take assignment if ITM

Three Edges:
1. Volatility Risk Premium (IV > RV)
2. Theta Decay (time value erosion)
3. Probability (80%+ OTM expiry rate)

=== PROBABILITY SYSTEM ===

Factors (weights calibrated from outcomes):
- gex_wall_strength: 0.25 (proximity to gamma walls)
- volatility_impact: 0.20 (VIX regime effect)
- psychology_signal: 0.15 (sentiment/traps)
- mm_positioning: 0.20 (market maker state)
- historical_pattern: 0.20 (pattern recognition)

Win Probability Calculation:
probability = Σ (factor_value × factor_weight)
Adjusted for regime and recent accuracy
"""

# =============================================================================
# ECONOMIC CALENDAR KNOWLEDGE
# =============================================================================

ECONOMIC_CALENDAR_KNOWLEDGE = """
=== ECONOMIC EVENTS COUNSELOR MUST KNOW ===

HIGH IMPACT EVENTS (Avoid 0DTE on these days):

1. FOMC (Federal Reserve)
   - 8 meetings per year
   - 2:00 PM ET announcement
   - Can move SPX 50-100 points
   - AVOID Iron Condors on FOMC days

2. CPI (Consumer Price Index)
   - Monthly, 8:30 AM ET
   - Key inflation measure
   - Higher = hawkish Fed = bearish
   - Major volatility for 2-4 hours after

3. NFP (Non-Farm Payrolls)
   - First Friday of month, 8:30 AM ET
   - Employment data
   - AVOID morning 0DTE trades on NFP Friday

4. PCE (Personal Consumption Expenditures)
   - Fed's preferred inflation measure
   - Monthly, last week
   - Less volatile than CPI but still significant

MEDIUM IMPACT EVENTS:

5. PPI (Producer Price Index)
   - Usually day before/after CPI
   - Leading indicator for CPI
   - Reduced position size recommended

6. GDP
   - Quarterly readings
   - Less volatile unless big surprise
   - Trade normally with caution

7. Retail Sales
   - Monthly consumer spending
   - Can move markets on surprises

OPTIONS EXPIRATION EVENTS:

8. Monthly OPEX
   - Third Friday of each month
   - Increased gamma effects
   - Pin risk around strikes

9. Quad Witching
   - March, June, September, December
   - Extreme volume
   - Consider closing positions Thursday

10. VIX Expiration
    - Wednesday before OPEX
    - VIX mean reversion common

COUNSELOR TRADING RULES FOR EVENTS:

Pre-CPI/FOMC/NFP:
- Widen Iron Condor strikes by 0.5 SD
- Reduce position size by 50%
- Or skip trading entirely

Day of Event:
- Wait 30-60 minutes after release
- Confirm direction before entering
- Use tighter stops

Post-Event:
- Return to normal sizing after volatility settles
- Usually takes 2-4 hours
"""

# =============================================================================
# COUNSELOR COMMANDS REFERENCE
# =============================================================================

COUNSELOR_COMMANDS = """
=== COUNSELOR SLASH COMMANDS ===

INFORMATION COMMANDS:
/help          - Show all available commands
/status        - Full system status (bots, positions, P&L)
/briefing      - Morning market briefing with all data
/calendar      - Upcoming economic events (7 days)

MARKET DATA COMMANDS:
/gex [SYMBOL]  - GEX data for symbol (default: SPY)
/vix           - Current VIX data and term structure
/market        - SPX, SPY, VIX prices with expected moves
/regime        - Current market regime classification

POSITION COMMANDS:
/positions     - All open positions with Greeks
/pnl           - P&L summary across all strategies
/history [N]   - Last N trades (default: 10)

ANALYSIS COMMANDS:
/analyze [SYM] - Full trade opportunity analysis
/risk          - Current portfolio risk assessment
/weights       - Probability system weights
/backtest      - Recent backtest performance

BOT CONTROL COMMANDS (Requires Confirmation):
/start fortress    - Start FORTRESS bot
/stop fortress     - Stop FORTRESS bot
/cycle solomon  - Run one SOLOMON trading cycle
/calibrate     - Recalibrate probability weights

LEARNING COMMANDS:
/accuracy      - AI prediction accuracy stats
/patterns      - Pattern recognition insights
/improve       - Suggested improvements from trade journal

NATURAL LANGUAGE QUERIES:
- "What's the GEX looking like today?"
- "Should I trade today?"
- "Explain my last trade"
- "What economic events are coming up?"
- "How is FORTRESS performing?"
- "What's my win rate this month?"
"""

# =============================================================================
# COMBINE ALL KNOWLEDGE
# =============================================================================

def get_full_knowledge() -> str:
    """Get the complete COUNSELOR knowledge base"""
    return f"""
{DATABASE_TABLES}

{SYSTEM_ARCHITECTURE}

{TRADING_STRATEGIES}

{ECONOMIC_CALENDAR_KNOWLEDGE}

{COUNSELOR_COMMANDS}
"""
