-- Migration 021: Auto-Validation System Tables
-- Thompson Sampling for capital allocation and ML model validation results
-- Created: 2025-01

-- ============================================================================
-- THOMPSON SAMPLING PARAMETERS
-- Stores the alpha/beta parameters for each bot's Beta distribution
-- ============================================================================

CREATE TABLE IF NOT EXISTS thompson_parameters (
    id SERIAL PRIMARY KEY,
    bot_name VARCHAR(50) NOT NULL,
    alpha DECIMAL(10,4) NOT NULL DEFAULT 1.0,  -- Beta distribution alpha (successes + 1)
    beta DECIMAL(10,4) NOT NULL DEFAULT 1.0,   -- Beta distribution beta (failures + 1)
    total_trades INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_pnl DECIMAL(15,2) DEFAULT 0.0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(bot_name)
);

-- Index for bot lookups
CREATE INDEX IF NOT EXISTS idx_thompson_bot_name ON thompson_parameters(bot_name);

-- Comments
COMMENT ON TABLE thompson_parameters IS 'Thompson Sampling parameters for bot capital allocation';
COMMENT ON COLUMN thompson_parameters.alpha IS 'Beta distribution alpha parameter (prior + wins)';
COMMENT ON COLUMN thompson_parameters.beta IS 'Beta distribution beta parameter (prior + losses)';

-- ============================================================================
-- ML VALIDATION RESULTS
-- Logs validation results for each ML model over time
-- ============================================================================

CREATE TABLE IF NOT EXISTS ml_validation_results (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    validation_time TIMESTAMPTZ DEFAULT NOW(),

    -- Accuracy metrics
    in_sample_accuracy DECIMAL(5,4),      -- 0.0000 to 1.0000
    out_of_sample_accuracy DECIMAL(5,4),  -- 0.0000 to 1.0000
    degradation_pct DECIMAL(5,2),         -- Percentage degradation

    -- Status and recommendations
    status VARCHAR(20) NOT NULL,          -- healthy, degraded, failed
    recommendation VARCHAR(50),           -- KEEP, RETRAIN, INVESTIGATE
    is_robust BOOLEAN DEFAULT TRUE,

    -- Additional metrics
    degradation_threshold DECIMAL(5,2),   -- Threshold used
    samples_tested INTEGER,

    -- Metadata
    details JSONB,                        -- Full validation details
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for querying
CREATE INDEX IF NOT EXISTS idx_ml_validation_model ON ml_validation_results(model_name);
CREATE INDEX IF NOT EXISTS idx_ml_validation_time ON ml_validation_results(validation_time DESC);
CREATE INDEX IF NOT EXISTS idx_ml_validation_status ON ml_validation_results(status);

-- Comments
COMMENT ON TABLE ml_validation_results IS 'Historical ML model validation results for monitoring degradation';
COMMENT ON COLUMN ml_validation_results.in_sample_accuracy IS 'Accuracy on training data';
COMMENT ON COLUMN ml_validation_results.out_of_sample_accuracy IS 'Accuracy on holdout/recent data';
COMMENT ON COLUMN ml_validation_results.degradation_pct IS 'Percentage drop between IS and OOS accuracy';

-- ============================================================================
-- THOMPSON ALLOCATION HISTORY
-- Logs capital allocation decisions over time
-- ============================================================================

CREATE TABLE IF NOT EXISTS thompson_allocation_history (
    id SERIAL PRIMARY KEY,
    allocation_time TIMESTAMPTZ DEFAULT NOW(),
    total_capital DECIMAL(15,2) NOT NULL,
    method VARCHAR(20) NOT NULL DEFAULT 'thompson',  -- thompson, equal
    allocations JSONB NOT NULL,                      -- {bot_name: amount}
    allocation_pcts JSONB NOT NULL,                  -- {bot_name: percentage}
    confidence JSONB,                                -- {bot_name: confidence_score}
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_thompson_alloc_time ON thompson_allocation_history(allocation_time DESC);

-- Comments
COMMENT ON TABLE thompson_allocation_history IS 'Historical capital allocation decisions from Thompson Sampling';

-- ============================================================================
-- BOT TRADE OUTCOMES
-- Logs individual trade outcomes for Thompson Sampling updates
-- ============================================================================

CREATE TABLE IF NOT EXISTS thompson_trade_outcomes (
    id SERIAL PRIMARY KEY,
    bot_name VARCHAR(50) NOT NULL,
    trade_time TIMESTAMPTZ DEFAULT NOW(),
    win BOOLEAN NOT NULL,
    pnl DECIMAL(15,2) DEFAULT 0.0,

    -- Context
    trade_type VARCHAR(50),               -- IRON_CONDOR, VERTICAL_SPREAD, etc.
    symbol VARCHAR(10) DEFAULT 'SPY',

    -- Pre/Post Thompson state
    alpha_before DECIMAL(10,4),
    beta_before DECIMAL(10,4),
    alpha_after DECIMAL(10,4),
    beta_after DECIMAL(10,4),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_thompson_outcomes_bot ON thompson_trade_outcomes(bot_name);
CREATE INDEX IF NOT EXISTS idx_thompson_outcomes_time ON thompson_trade_outcomes(trade_time DESC);
CREATE INDEX IF NOT EXISTS idx_thompson_outcomes_win ON thompson_trade_outcomes(win);

-- Comments
COMMENT ON TABLE thompson_trade_outcomes IS 'Individual trade outcomes for Thompson Sampling parameter updates';

-- ============================================================================
-- INITIALIZE DEFAULT THOMPSON PARAMETERS FOR ALL BOTS
-- Using uninformative prior (1, 1) = uniform distribution
-- ============================================================================

INSERT INTO thompson_parameters (bot_name, alpha, beta, total_trades, total_wins, total_pnl)
VALUES
    ('FORTRESS', 1.0, 1.0, 0, 0, 0.0),
    ('SOLOMON', 1.0, 1.0, 0, 0, 0.0),
    ('LAZARUS', 1.0, 1.0, 0, 0, 0.0),
    ('CORNERSTONE', 1.0, 1.0, 0, 0, 0.0),
    ('GIDEON', 1.0, 1.0, 0, 0, 0.0),
    ('ANCHOR', 1.0, 1.0, 0, 0, 0.0),
    ('TITAN', 1.0, 1.0, 0, 0, 0.0)
ON CONFLICT (bot_name) DO NOTHING;
