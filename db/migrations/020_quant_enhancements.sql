-- Migration 020: QUANT Enhancements
-- Adds outcome tracking, bot integration, alerts, and performance tables

-- ============================================================================
-- 1. ENHANCE ml_predictions with outcome tracking and bot integration
-- ============================================================================

-- Add outcome tracking columns
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS outcome_correct BOOLEAN;
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS outcome_pnl DECIMAL(10,2);
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS outcome_notes TEXT;
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS outcome_recorded_at TIMESTAMPTZ;

-- Add bot integration columns
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS used_by_bot VARCHAR(20);  -- FORTRESS, SOLOMON, GIDEON, TITAN, ANCHOR
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS trade_id VARCHAR(100);     -- Link to actual trade
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS session_id VARCHAR(50);    -- Trading session

-- Add market context at prediction time
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS spot_price DECIMAL(10,2);
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS vix DECIMAL(5,2);
ALTER TABLE ml_predictions ADD COLUMN IF NOT EXISTS gex_regime VARCHAR(20);

-- Indexes for new columns
CREATE INDEX IF NOT EXISTS idx_ml_predictions_outcome ON ml_predictions(outcome_correct);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_bot ON ml_predictions(used_by_bot);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_trade ON ml_predictions(trade_id);

-- ============================================================================
-- 2. QUANT ALERTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS quant_alerts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    alert_type VARCHAR(50) NOT NULL,      -- REGIME_CHANGE, HIGH_CONFIDENCE, MODEL_DISAGREE, STREAK
    severity VARCHAR(20) DEFAULT 'INFO',  -- INFO, WARNING, CRITICAL
    title VARCHAR(200) NOT NULL,
    message TEXT,

    -- Context
    symbol VARCHAR(10) DEFAULT 'SPY',
    previous_value VARCHAR(50),           -- Previous prediction
    current_value VARCHAR(50),            -- New prediction
    confidence DECIMAL(5,2),

    -- Model info
    model_name VARCHAR(50),               -- Which model triggered
    models_involved JSONB,                -- For MODEL_DISAGREE: all model predictions

    -- Status
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quant_alerts_timestamp ON quant_alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_quant_alerts_type ON quant_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_quant_alerts_severity ON quant_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_quant_alerts_unacked ON quant_alerts(acknowledged) WHERE acknowledged = FALSE;

-- ============================================================================
-- 3. MODEL PERFORMANCE TRACKING TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS quant_model_performance (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    model_name VARCHAR(50) NOT NULL,      -- REGIME_CLASSIFIER, GEX_DIRECTIONAL, ENSEMBLE
    symbol VARCHAR(10) DEFAULT 'SPY',

    -- Daily stats
    total_predictions INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    incorrect_predictions INTEGER DEFAULT 0,
    pending_predictions INTEGER DEFAULT 0,

    -- Performance metrics
    accuracy DECIMAL(5,2),                -- Correct / Total
    avg_confidence DECIMAL(5,2),
    total_pnl DECIMAL(10,2),

    -- By prediction value
    predictions_by_value JSONB,           -- {SELL_PREMIUM: {total: 5, correct: 4}, ...}

    -- Market context
    avg_vix DECIMAL(5,2),
    dominant_regime VARCHAR(20),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(date, model_name, symbol)
);

CREATE INDEX IF NOT EXISTS idx_quant_perf_date ON quant_model_performance(date DESC);
CREATE INDEX IF NOT EXISTS idx_quant_perf_model ON quant_model_performance(model_name);

-- ============================================================================
-- 4. MODEL TRAINING HISTORY TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS quant_training_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    model_name VARCHAR(50) NOT NULL,

    -- Training info
    training_samples INTEGER,
    validation_samples INTEGER,

    -- Metrics before/after
    accuracy_before DECIMAL(5,2),
    accuracy_after DECIMAL(5,2),

    -- Model details
    model_version VARCHAR(50),
    feature_importance JSONB,
    hyperparameters JSONB,

    -- Status
    status VARCHAR(20) DEFAULT 'COMPLETED',  -- STARTED, COMPLETED, FAILED
    error_message TEXT,
    duration_seconds INTEGER,

    triggered_by VARCHAR(50),             -- AUTO, MANUAL, SCHEDULED

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quant_training_model ON quant_training_history(model_name);
CREATE INDEX IF NOT EXISTS idx_quant_training_timestamp ON quant_training_history(timestamp DESC);

-- ============================================================================
-- 5. LAST PREDICTIONS CACHE (for change detection)
-- ============================================================================

CREATE TABLE IF NOT EXISTS quant_last_predictions (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(50) NOT NULL UNIQUE,
    symbol VARCHAR(10) DEFAULT 'SPY',
    predicted_value VARCHAR(50),
    confidence DECIMAL(5,2),
    timestamp TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert initial rows for each model
INSERT INTO quant_last_predictions (model_name, symbol) VALUES
    ('REGIME_CLASSIFIER', 'SPY'),
    ('GEX_DIRECTIONAL', 'SPY'),
    ('ENSEMBLE', 'SPY')
ON CONFLICT (model_name) DO NOTHING;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE quant_alerts IS 'Alerts generated by QUANT models (regime changes, disagreements)';
COMMENT ON TABLE quant_model_performance IS 'Daily performance metrics for each ML model';
COMMENT ON TABLE quant_training_history IS 'History of model training runs';
COMMENT ON TABLE quant_last_predictions IS 'Cache of last prediction for change detection';
