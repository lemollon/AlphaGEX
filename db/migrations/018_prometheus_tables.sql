-- Migration 018: Create Prometheus ML Tables
-- Creates all tables required for the Prometheus ML system
-- Run: psql $DATABASE_URL -f db/migrations/018_prometheus_tables.sql

-- 1. prometheus_predictions - Stores ML predictions for trades
CREATE TABLE IF NOT EXISTS prometheus_predictions (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(50) UNIQUE NOT NULL,
    trade_date VARCHAR(20),
    strike DECIMAL(10,2),
    underlying_price DECIMAL(10,2),
    dte INTEGER,
    delta DECIMAL(6,4),
    premium DECIMAL(10,4),
    win_probability DECIMAL(5,4),
    recommendation VARCHAR(20),
    confidence DECIMAL(5,4),
    reasoning TEXT,
    key_factors JSONB,
    feature_values JSONB,
    vix DECIMAL(6,2),
    iv_rank DECIMAL(5,2),
    model_version VARCHAR(50),
    session_id VARCHAR(50),
    actual_outcome VARCHAR(10),
    actual_pnl DECIMAL(12,2),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for trade lookups
CREATE INDEX IF NOT EXISTS idx_prometheus_predictions_trade_id ON prometheus_predictions(trade_id);
CREATE INDEX IF NOT EXISTS idx_prometheus_predictions_created_at ON prometheus_predictions(created_at);

-- 2. prometheus_live_model - Stores the active ML model binary
CREATE TABLE IF NOT EXISTS prometheus_live_model (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(50) NOT NULL,
    model_binary BYTEA,
    scaler_binary BYTEA,
    model_type VARCHAR(50),
    feature_names JSONB,
    accuracy DECIMAL(5,4),
    calibration_error DECIMAL(5,4),
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for active model lookup
CREATE INDEX IF NOT EXISTS idx_prometheus_live_model_active ON prometheus_live_model(is_active) WHERE is_active = TRUE;

-- 3. prometheus_training_history - Stores training run history
CREATE TABLE IF NOT EXISTS prometheus_training_history (
    id SERIAL PRIMARY KEY,
    training_id VARCHAR(50) UNIQUE NOT NULL,
    total_samples INTEGER,
    train_samples INTEGER,
    test_samples INTEGER,
    win_count INTEGER,
    loss_count INTEGER,
    baseline_win_rate DECIMAL(5,4),
    accuracy DECIMAL(5,4),
    precision_score DECIMAL(5,4),
    recall DECIMAL(5,4),
    f1_score DECIMAL(5,4),
    auc_roc DECIMAL(5,4),
    brier_score DECIMAL(5,4),
    cv_accuracy_mean DECIMAL(5,4),
    cv_accuracy_std DECIMAL(5,4),
    cv_scores JSONB,
    calibration_error DECIMAL(5,4),
    is_calibrated BOOLEAN DEFAULT FALSE,
    feature_importance JSONB,
    model_type VARCHAR(50),
    model_version VARCHAR(50),
    interpretation TEXT,
    honest_assessment TEXT,
    recommendation TEXT,
    model_path VARCHAR(255),
    model_saved_to_db BOOLEAN DEFAULT FALSE,
    model_binary BYTEA,
    scaler_binary BYTEA,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for version lookup
CREATE INDEX IF NOT EXISTS idx_prometheus_training_history_version ON prometheus_training_history(model_version);
CREATE INDEX IF NOT EXISTS idx_prometheus_training_history_created ON prometheus_training_history(created_at DESC);

-- 4. prometheus_logs - Stores ML decision logs
CREATE TABLE IF NOT EXISTS prometheus_logs (
    id SERIAL PRIMARY KEY,
    log_type VARCHAR(30) NOT NULL,
    action VARCHAR(100),
    ml_score DECIMAL(5,4),
    recommendation VARCHAR(20),
    trade_id VARCHAR(50),
    reasoning TEXT,
    details JSONB,
    features JSONB,
    execution_time_ms INTEGER,
    session_id VARCHAR(50),
    trace_id VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for log queries
CREATE INDEX IF NOT EXISTS idx_prometheus_logs_type ON prometheus_logs(log_type);
CREATE INDEX IF NOT EXISTS idx_prometheus_logs_created ON prometheus_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_prometheus_logs_trade_id ON prometheus_logs(trade_id) WHERE trade_id IS NOT NULL;

-- 5. prometheus_models - Alternative model storage (for backup/versioning)
CREATE TABLE IF NOT EXISTS prometheus_models (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(50) NOT NULL,
    model_name VARCHAR(100),
    model_binary BYTEA,
    scaler_binary BYTEA,
    config JSONB,
    metrics JSONB,
    is_production BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for model lookup
CREATE INDEX IF NOT EXISTS idx_prometheus_models_version ON prometheus_models(model_version);
CREATE INDEX IF NOT EXISTS idx_prometheus_models_production ON prometheus_models(is_production) WHERE is_production = TRUE;

-- Verify tables created
SELECT 'prometheus_predictions' as table_name, COUNT(*) as row_count FROM prometheus_predictions
UNION ALL
SELECT 'prometheus_live_model', COUNT(*) FROM prometheus_live_model
UNION ALL
SELECT 'prometheus_training_history', COUNT(*) FROM prometheus_training_history
UNION ALL
SELECT 'prometheus_logs', COUNT(*) FROM prometheus_logs
UNION ALL
SELECT 'prometheus_models', COUNT(*) FROM prometheus_models;
