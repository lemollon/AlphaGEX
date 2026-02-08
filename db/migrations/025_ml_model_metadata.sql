-- ============================================================================
-- Migration 025: ML Model Metadata Table
-- Created: January 2026
-- Purpose: Track currently deployed ML models with their metadata
-- ============================================================================

-- ============================================================================
-- 1. ML_MODEL_METADATA TABLE
-- Stores metadata about currently deployed/active ML models
-- Different from quant_training_history which stores all training runs
-- ============================================================================

CREATE TABLE IF NOT EXISTS ml_model_metadata (
    id SERIAL PRIMARY KEY,

    -- Model identification
    model_name VARCHAR(50) NOT NULL,          -- WISDOM, PROPHET, GEX_PROBABILITY, GEX_DIRECTIONAL
    model_version VARCHAR(50),                -- e.g., 'v1.0.0', '2026-01-26'

    -- Training info
    trained_at TIMESTAMPTZ NOT NULL,          -- When this model was trained
    training_samples INTEGER,                 -- Number of samples used

    -- Performance metrics
    accuracy DECIMAL(5,4),                    -- Model accuracy (0.0000 to 1.0000)
    precision_score DECIMAL(5,4),             -- Precision metric
    recall_score DECIMAL(5,4),                -- Recall metric
    f1_score DECIMAL(5,4),                    -- F1 score

    -- Feature information
    feature_count INTEGER,                    -- Number of features used
    feature_importance JSONB,                 -- {"feature_name": importance_score}

    -- Model configuration
    hyperparameters JSONB,                    -- {"n_estimators": 100, "max_depth": 5}
    model_type VARCHAR(50),                   -- XGBoost, RandomForest, etc.

    -- Deployment tracking
    is_active BOOLEAN DEFAULT TRUE,           -- Is this the currently deployed model?
    deployed_at TIMESTAMPTZ DEFAULT NOW(),    -- When deployed to production

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT,

    -- Ensure only one active model per model_name
    CONSTRAINT unique_active_model UNIQUE (model_name, is_active)
        DEFERRABLE INITIALLY DEFERRED
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ml_model_metadata_name
    ON ml_model_metadata(model_name);
CREATE INDEX IF NOT EXISTS idx_ml_model_metadata_active
    ON ml_model_metadata(model_name, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_ml_model_metadata_trained
    ON ml_model_metadata(trained_at DESC);

-- Insert initial placeholder rows for each model type
-- These will be updated when models are first trained
INSERT INTO ml_model_metadata (model_name, model_version, trained_at, is_active, notes)
VALUES
    ('WISDOM', 'not_trained', NOW() - INTERVAL '1 year', TRUE, 'Placeholder - will be updated on first training'),
    ('PROPHET', 'not_trained', NOW() - INTERVAL '1 year', TRUE, 'Placeholder - will be updated on first training'),
    ('GEX_PROBABILITY', 'not_trained', NOW() - INTERVAL '1 year', TRUE, 'Placeholder - will be updated on first training'),
    ('GEX_DIRECTIONAL', 'not_trained', NOW() - INTERVAL '1 year', TRUE, 'Placeholder - will be updated on first training')
ON CONFLICT DO NOTHING;

-- Documentation
COMMENT ON TABLE ml_model_metadata IS 'Metadata for currently deployed ML models (WISDOM, Prophet, GEX models)';
COMMENT ON COLUMN ml_model_metadata.model_name IS 'Model identifier: WISDOM, PROPHET, GEX_PROBABILITY, GEX_DIRECTIONAL';
COMMENT ON COLUMN ml_model_metadata.is_active IS 'TRUE if this is the currently deployed version of the model';
COMMENT ON COLUMN ml_model_metadata.feature_importance IS 'JSON object mapping feature names to importance scores';

-- ============================================================================
-- 2. HELPER FUNCTION: Update model metadata after training
-- ============================================================================

CREATE OR REPLACE FUNCTION update_ml_model_metadata(
    p_model_name VARCHAR(50),
    p_model_version VARCHAR(50),
    p_accuracy DECIMAL(5,4) DEFAULT NULL,
    p_training_samples INTEGER DEFAULT NULL,
    p_feature_importance JSONB DEFAULT NULL,
    p_hyperparameters JSONB DEFAULT NULL,
    p_model_type VARCHAR(50) DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    result_id INTEGER;
BEGIN
    -- Deactivate any existing active model for this name
    UPDATE ml_model_metadata
    SET is_active = FALSE
    WHERE model_name = p_model_name AND is_active = TRUE;

    -- Insert new active model
    INSERT INTO ml_model_metadata (
        model_name, model_version, trained_at, training_samples,
        accuracy, feature_importance, hyperparameters, model_type,
        is_active, deployed_at
    ) VALUES (
        p_model_name, p_model_version, NOW(), p_training_samples,
        p_accuracy, p_feature_importance, p_hyperparameters, p_model_type,
        TRUE, NOW()
    )
    RETURNING id INTO result_id;

    RETURN result_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Verification query
-- ============================================================================
SELECT 'ml_model_metadata table created' AS status, COUNT(*) AS initial_rows FROM ml_model_metadata;
