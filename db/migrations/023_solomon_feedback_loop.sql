-- Migration 023: Solomon Feedback Loop Enhancements
-- Adds prediction linking, strategy tracking, and direction accuracy
-- Supports the complete feedback loop: Oracle -> Bots -> Solomon -> Oracle

-- ============================================================================
-- 1. ORACLE PREDICTIONS - Add strategy recommendation and position linking
-- ============================================================================

-- Add strategy recommendation column (IRON_CONDOR or DIRECTIONAL)
ALTER TABLE oracle_predictions ADD COLUMN IF NOT EXISTS strategy_recommendation VARCHAR(20);

-- Add position_id for 1:1 prediction-to-position linking (Option C)
ALTER TABLE oracle_predictions ADD COLUMN IF NOT EXISTS position_id VARCHAR(100);

-- Add direction tracking for directional strategies
ALTER TABLE oracle_predictions ADD COLUMN IF NOT EXISTS direction_predicted VARCHAR(10);  -- BULLISH/BEARISH
ALTER TABLE oracle_predictions ADD COLUMN IF NOT EXISTS direction_correct BOOLEAN;

-- Drop old unique constraint and create new one with position_id
-- Note: This allows multiple predictions per bot per day (one per position)
DROP INDEX IF EXISTS oracle_predictions_trade_date_bot_name_key;
CREATE UNIQUE INDEX IF NOT EXISTS oracle_predictions_position_unique
    ON oracle_predictions(trade_date, bot_name, position_id)
    WHERE position_id IS NOT NULL;

-- Index for strategy analysis
CREATE INDEX IF NOT EXISTS idx_oracle_predictions_strategy ON oracle_predictions(strategy_recommendation);
CREATE INDEX IF NOT EXISTS idx_oracle_predictions_position ON oracle_predictions(position_id);
CREATE INDEX IF NOT EXISTS idx_oracle_predictions_direction ON oracle_predictions(direction_predicted);

-- ============================================================================
-- 2. BOT POSITION TABLES - Add oracle_prediction_id column
-- ============================================================================

-- ARES positions
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_prediction_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_ares_positions_oracle_pred ON ares_positions(oracle_prediction_id);

-- ATHENA positions
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS oracle_prediction_id INTEGER;
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS direction_taken VARCHAR(10);  -- BULLISH/BEARISH
CREATE INDEX IF NOT EXISTS idx_athena_positions_oracle_pred ON athena_positions(oracle_prediction_id);

-- TITAN positions
ALTER TABLE titan_positions ADD COLUMN IF NOT EXISTS oracle_prediction_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_titan_positions_oracle_pred ON titan_positions(oracle_prediction_id);

-- PEGASUS positions
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS oracle_prediction_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_pegasus_positions_oracle_pred ON pegasus_positions(oracle_prediction_id);

-- ICARUS positions
ALTER TABLE icarus_positions ADD COLUMN IF NOT EXISTS oracle_prediction_id INTEGER;
ALTER TABLE icarus_positions ADD COLUMN IF NOT EXISTS direction_taken VARCHAR(10);  -- BULLISH/BEARISH
CREATE INDEX IF NOT EXISTS idx_icarus_positions_oracle_pred ON icarus_positions(oracle_prediction_id);

-- ============================================================================
-- 3. SOLOMON PERFORMANCE - Add strategy-level tracking
-- ============================================================================

-- Add trade-level tracking columns (needed for per-trade analysis)
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS trade_date DATE;
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS pnl DECIMAL(12,2);
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS is_win BOOLEAN;
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Add strategy and outcome tracking to solomon_performance
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(20);  -- IRON_CONDOR/DIRECTIONAL
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS oracle_advice VARCHAR(20);   -- TRADE_FULL/REDUCED/SKIP
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS oracle_strategy_recommendation VARCHAR(20);
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS oracle_prediction_id INTEGER;

-- Add outcome details
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS outcome_type VARCHAR(30);  -- MAX_PROFIT/PUT_BREACHED/CALL_BREACHED/LOSS
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS direction_taken VARCHAR(10);  -- BULLISH/BEARISH (for directional bots)
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS direction_correct BOOLEAN;

-- Add market context at trade time
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS vix_at_trade DECIMAL(5,2);
ALTER TABLE solomon_performance ADD COLUMN IF NOT EXISTS gex_regime_at_trade VARCHAR(20);

-- Create unique constraint for per-bot per-day tracking (for ON CONFLICT)
CREATE UNIQUE INDEX IF NOT EXISTS idx_solomon_perf_bot_date ON solomon_performance(bot_name, trade_date)
    WHERE trade_date IS NOT NULL;

-- Indexes for strategy analysis
CREATE INDEX IF NOT EXISTS idx_solomon_perf_strategy ON solomon_performance(strategy_type);
CREATE INDEX IF NOT EXISTS idx_solomon_perf_oracle_advice ON solomon_performance(oracle_advice);
CREATE INDEX IF NOT EXISTS idx_solomon_perf_outcome ON solomon_performance(outcome_type);
CREATE INDEX IF NOT EXISTS idx_solomon_perf_direction ON solomon_performance(direction_correct);
CREATE INDEX IF NOT EXISTS idx_solomon_perf_trade_date ON solomon_performance(trade_date);

-- ============================================================================
-- 4. SOLOMON STRATEGY ANALYSIS TABLE (New)
-- ============================================================================

CREATE TABLE IF NOT EXISTS solomon_strategy_analysis (
    id SERIAL PRIMARY KEY,
    analysis_date DATE NOT NULL,
    analysis_time TIMESTAMPTZ DEFAULT NOW(),

    -- Strategy-level metrics
    strategy_type VARCHAR(20) NOT NULL,  -- IRON_CONDOR or DIRECTIONAL

    -- Aggregated performance
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate DECIMAL(5,4),
    total_pnl DECIMAL(12,2),
    avg_pnl DECIMAL(10,2),

    -- Oracle accuracy for this strategy
    oracle_recommended_count INTEGER DEFAULT 0,  -- Times Oracle said use this strategy
    oracle_correct_count INTEGER DEFAULT 0,      -- Times Oracle was right
    oracle_accuracy DECIMAL(5,4),

    -- By bot breakdown (JSONB for flexibility)
    bot_breakdown JSONB,  -- {"ARES": {"trades": 5, "wins": 4}, "PEGASUS": {...}}

    -- Market conditions summary
    avg_vix DECIMAL(5,2),
    dominant_gex_regime VARCHAR(20),

    -- Insights
    insights JSONB,  -- AI-generated insights about this strategy's performance

    UNIQUE(analysis_date, strategy_type)
);

CREATE INDEX IF NOT EXISTS idx_solomon_strategy_date ON solomon_strategy_analysis(analysis_date);
CREATE INDEX IF NOT EXISTS idx_solomon_strategy_type ON solomon_strategy_analysis(strategy_type);

-- ============================================================================
-- 5. BOT STRATEGY CONFIGURATION TABLE (New)
-- ============================================================================

CREATE TABLE IF NOT EXISTS solomon_bot_configs (
    id SERIAL PRIMARY KEY,
    bot_name VARCHAR(20) NOT NULL UNIQUE,

    -- Strategy classification
    strategy_type VARCHAR(20) NOT NULL,  -- IRON_CONDOR or DIRECTIONAL

    -- Success metrics and targets
    primary_success_metric VARCHAR(50) NOT NULL,  -- win_rate, direction_accuracy, etc.
    target_value DECIMAL(5,4),  -- e.g., 0.70 for 70% win rate

    -- Degradation thresholds (bot-specific)
    degradation_threshold DECIMAL(5,4) DEFAULT 0.15,  -- Alert if drops 15%
    min_sample_size INTEGER DEFAULT 20,  -- Min trades before analysis

    -- Bot personality (aggressive vs conservative)
    risk_tolerance VARCHAR(20) DEFAULT 'NORMAL',  -- AGGRESSIVE, NORMAL, CONSERVATIVE

    -- What to track for this bot
    track_metrics JSONB,  -- ["win_rate", "put_breach_rate", "call_breach_rate"]

    -- Optimization parameters (what Solomon can propose changes to)
    optimizable_params JSONB,  -- ["sd_multiplier", "spread_width", "wall_filter"]

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default configurations for the 5 bots
INSERT INTO solomon_bot_configs (bot_name, strategy_type, primary_success_metric, target_value, risk_tolerance, track_metrics, optimizable_params)
VALUES
    ('ARES', 'IRON_CONDOR', 'win_rate', 0.70, 'NORMAL',
     '["win_rate", "put_breach_rate", "call_breach_rate", "max_profit_rate"]',
     '["sd_multiplier", "spread_width", "profit_target_pct"]'),
    ('PEGASUS', 'IRON_CONDOR', 'win_rate', 0.70, 'CONSERVATIVE',
     '["win_rate", "put_breach_rate", "call_breach_rate", "max_profit_rate"]',
     '["sd_multiplier", "spread_width", "profit_target_pct"]'),
    ('TITAN', 'IRON_CONDOR', 'win_rate', 0.60, 'AGGRESSIVE',
     '["win_rate", "put_breach_rate", "call_breach_rate", "max_profit_rate", "trade_frequency"]',
     '["sd_multiplier", "spread_width", "profit_target_pct", "min_win_probability"]'),
    ('ATHENA', 'DIRECTIONAL', 'direction_accuracy', 0.55, 'CONSERVATIVE',
     '["direction_accuracy", "avg_rr_achieved", "wall_proximity_at_entry"]',
     '["wall_filter_pct", "profit_target_pct", "stop_loss_pct", "min_rr_ratio"]'),
    ('ICARUS', 'DIRECTIONAL', 'direction_accuracy', 0.50, 'AGGRESSIVE',
     '["direction_accuracy", "avg_rr_achieved", "trade_frequency"]',
     '["wall_filter_pct", "profit_target_pct", "stop_loss_pct", "min_win_probability"]')
ON CONFLICT (bot_name) DO UPDATE SET
    strategy_type = EXCLUDED.strategy_type,
    primary_success_metric = EXCLUDED.primary_success_metric,
    target_value = EXCLUDED.target_value,
    risk_tolerance = EXCLUDED.risk_tolerance,
    track_metrics = EXCLUDED.track_metrics,
    optimizable_params = EXCLUDED.optimizable_params,
    updated_at = NOW();

-- ============================================================================
-- 6. ORACLE STRATEGY ACCURACY TABLE (New)
-- ============================================================================

CREATE TABLE IF NOT EXISTS oracle_strategy_accuracy (
    id SERIAL PRIMARY KEY,
    analysis_date DATE NOT NULL,

    -- What Oracle recommended
    strategy_recommended VARCHAR(20) NOT NULL,  -- IRON_CONDOR, DIRECTIONAL, SKIP

    -- Market conditions when recommended
    vix_regime VARCHAR(20),
    gex_regime VARCHAR(20),

    -- Outcome tracking
    times_recommended INTEGER DEFAULT 0,
    times_followed INTEGER DEFAULT 0,      -- How often bots actually used this strategy
    times_successful INTEGER DEFAULT 0,    -- How often it was profitable
    total_pnl DECIMAL(12,2) DEFAULT 0,

    -- Accuracy metrics
    recommendation_accuracy DECIMAL(5,4),  -- times_successful / times_followed

    UNIQUE(analysis_date, strategy_recommended, vix_regime, gex_regime)
);

CREATE INDEX IF NOT EXISTS idx_oracle_strategy_acc_date ON oracle_strategy_accuracy(analysis_date);
CREATE INDEX IF NOT EXISTS idx_oracle_strategy_acc_rec ON oracle_strategy_accuracy(strategy_recommended);
