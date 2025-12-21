-- PROMETHEUS Tables Migration
-- Creates tables for Prometheus ML System (SPX Wheel ML)
-- Prometheus: Predictive Risk Optimization Through Machine Evaluation & Training for Honest Earnings Utility System
-- Run: psql $DATABASE_URL -f db/migrations/004_prometheus_tables.sql

-- ============================================================================
-- PROMETHEUS PREDICTIONS TABLE
-- Stores predictions made by Prometheus ML for feedback loop and analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS prometheus_predictions (
    id SERIAL PRIMARY KEY,

    -- Prediction context
    trade_date DATE NOT NULL,
    prediction_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    session_id VARCHAR(50),  -- For session tracking

    -- Trade details
    trade_id VARCHAR(100),
    strike FLOAT NOT NULL,
    underlying_price FLOAT NOT NULL,
    dte INTEGER NOT NULL,
    delta FLOAT,
    premium FLOAT,

    -- Prediction details
    win_probability FLOAT NOT NULL,
    recommendation VARCHAR(20) NOT NULL,  -- STRONG_TRADE, TRADE, NEUTRAL, CAUTION, SKIP
    confidence FLOAT,
    reasoning TEXT,

    -- Key factors (stored as JSONB for flexibility)
    key_factors JSONB,
    feature_values JSONB,

    -- Market context at time of prediction
    vix FLOAT,
    iv_rank FLOAT,
    gex_regime VARCHAR(10),  -- POSITIVE, NEGATIVE, NEUTRAL
    put_wall_distance_pct FLOAT,

    -- Model info
    model_version VARCHAR(20),
    model_accuracy FLOAT,

    -- Outcome (updated after trade closes)
    actual_outcome VARCHAR(10),  -- WIN, LOSS, NULL if pending
    actual_pnl FLOAT,
    outcome_date TIMESTAMP WITH TIME ZONE,
    was_traded BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prometheus_predictions_date ON prometheus_predictions(trade_date);
CREATE INDEX IF NOT EXISTS idx_prometheus_predictions_outcome ON prometheus_predictions(actual_outcome);
CREATE INDEX IF NOT EXISTS idx_prometheus_predictions_session ON prometheus_predictions(session_id);
CREATE INDEX IF NOT EXISTS idx_prometheus_predictions_trade ON prometheus_predictions(trade_id);

-- ============================================================================
-- PROMETHEUS DECISION LOGS TABLE
-- Comprehensive logging for all Prometheus ML decisions and actions
-- ============================================================================
CREATE TABLE IF NOT EXISTS prometheus_decision_logs (
    id SERIAL PRIMARY KEY,

    -- Log identification
    session_id VARCHAR(50),
    trace_id VARCHAR(100),  -- For tracing across systems

    -- Log details
    log_type VARCHAR(30) NOT NULL,  -- PREDICTION, TRAINING, OUTCOME, FEATURE_ANALYSIS, ERROR
    action VARCHAR(50) NOT NULL,

    -- Context
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    trade_id VARCHAR(100),

    -- Prediction specific
    ml_score FLOAT,
    recommendation VARCHAR(20),

    -- Details as JSONB for flexibility
    details JSONB,
    reasoning TEXT,

    -- Feature values at time of decision
    features JSONB,

    -- Error tracking
    error_message TEXT,
    error_stack TEXT,

    -- Performance metrics
    execution_time_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_prometheus_logs_type ON prometheus_decision_logs(log_type);
CREATE INDEX IF NOT EXISTS idx_prometheus_logs_session ON prometheus_decision_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_prometheus_logs_trace ON prometheus_decision_logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_prometheus_logs_time ON prometheus_decision_logs(timestamp);

-- ============================================================================
-- PROMETHEUS TRAINING HISTORY TABLE
-- Tracks model training runs and performance evolution
-- ============================================================================
CREATE TABLE IF NOT EXISTS prometheus_training_history (
    id SERIAL PRIMARY KEY,

    -- Training run identification
    training_id VARCHAR(50) NOT NULL UNIQUE,
    training_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Training data stats
    total_samples INTEGER NOT NULL,
    train_samples INTEGER NOT NULL,
    test_samples INTEGER NOT NULL,
    win_count INTEGER,
    loss_count INTEGER,
    baseline_win_rate FLOAT,

    -- Model performance metrics
    accuracy FLOAT,
    precision_score FLOAT,
    recall FLOAT,
    f1_score FLOAT,
    auc_roc FLOAT,
    brier_score FLOAT,

    -- Cross-validation results
    cv_accuracy_mean FLOAT,
    cv_accuracy_std FLOAT,
    cv_scores JSONB,  -- All CV fold scores

    -- Calibration metrics
    calibration_error FLOAT,
    is_calibrated BOOLEAN DEFAULT FALSE,

    -- Feature importance (top features)
    feature_importance JSONB,

    -- Model configuration
    model_type VARCHAR(50),  -- RandomForest, GradientBoosting, etc.
    model_params JSONB,
    model_version VARCHAR(20),

    -- Persistence
    model_path VARCHAR(255),
    model_saved_to_db BOOLEAN DEFAULT FALSE,
    model_binary BYTEA,  -- Store model in DB for persistence
    scaler_binary BYTEA,  -- Store scaler too

    -- Interpretation
    interpretation JSONB,
    honest_assessment TEXT,
    recommendation TEXT,

    -- Status
    status VARCHAR(20) DEFAULT 'COMPLETED',  -- COMPLETED, FAILED, IN_PROGRESS
    error_message TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prometheus_training_date ON prometheus_training_history(training_date);
CREATE INDEX IF NOT EXISTS idx_prometheus_training_version ON prometheus_training_history(model_version);

-- ============================================================================
-- PROMETHEUS FEATURE ANALYSIS TABLE
-- Stores feature importance analysis and trends
-- ============================================================================
CREATE TABLE IF NOT EXISTS prometheus_feature_analysis (
    id SERIAL PRIMARY KEY,

    analysis_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    training_id VARCHAR(50) REFERENCES prometheus_training_history(training_id),

    -- Feature details
    feature_name VARCHAR(50) NOT NULL,
    importance FLOAT NOT NULL,
    importance_rank INTEGER,

    -- Feature statistics
    mean_value FLOAT,
    std_value FLOAT,
    min_value FLOAT,
    max_value FLOAT,

    -- Feature correlation with outcome
    correlation_with_win FLOAT,

    -- Trend (compared to previous training)
    importance_change FLOAT,
    importance_trend VARCHAR(10),  -- UP, DOWN, STABLE

    -- Feature meaning/interpretation
    interpretation TEXT
);

CREATE INDEX IF NOT EXISTS idx_prometheus_features_training ON prometheus_feature_analysis(training_id);
CREATE INDEX IF NOT EXISTS idx_prometheus_features_name ON prometheus_feature_analysis(feature_name);

-- ============================================================================
-- PROMETHEUS LIVE MODEL TABLE
-- Stores the current production model for persistence across restarts
-- ============================================================================
CREATE TABLE IF NOT EXISTS prometheus_live_model (
    id SERIAL PRIMARY KEY,

    -- Model identification
    model_version VARCHAR(20) NOT NULL,
    training_id VARCHAR(50) REFERENCES prometheus_training_history(training_id),

    -- Model binary (pickle serialized)
    model_binary BYTEA NOT NULL,
    scaler_binary BYTEA,

    -- Model metadata
    model_type VARCHAR(50),
    feature_names JSONB,

    -- Performance at time of deployment
    accuracy FLOAT,
    calibration_error FLOAT,

    -- Deployment info
    is_active BOOLEAN DEFAULT TRUE,
    deployed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deployed_by VARCHAR(100),

    -- Usage stats
    predictions_made INTEGER DEFAULT 0,
    last_prediction_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prometheus_live_model_active ON prometheus_live_model(is_active);
CREATE INDEX IF NOT EXISTS idx_prometheus_live_model_version ON prometheus_live_model(model_version);

-- ============================================================================
-- PROMETHEUS PERFORMANCE TRACKING TABLE
-- Tracks prediction accuracy and model performance over time
-- ============================================================================
CREATE TABLE IF NOT EXISTS prometheus_performance (
    id SERIAL PRIMARY KEY,

    -- Time period
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    period_type VARCHAR(10) NOT NULL,  -- DAILY, WEEKLY, MONTHLY

    -- Prediction stats
    total_predictions INTEGER DEFAULT 0,
    predictions_followed INTEGER DEFAULT 0,  -- How many predictions were actually traded

    -- Outcome stats
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    win_rate FLOAT,

    -- Accuracy metrics
    predictions_correct INTEGER DEFAULT 0,
    prediction_accuracy FLOAT,
    brier_score FLOAT,

    -- P&L attribution to ML
    total_pnl FLOAT,
    avg_pnl_per_trade FLOAT,

    -- Calibration metrics
    avg_predicted_win_prob FLOAT,
    actual_win_rate FLOAT,
    calibration_error FLOAT,

    -- Model version used
    model_version VARCHAR(20),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_prometheus_perf UNIQUE (period_start, period_end, period_type)
);

CREATE INDEX IF NOT EXISTS idx_prometheus_perf_period ON prometheus_performance(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_prometheus_perf_type ON prometheus_performance(period_type);

-- ============================================================================
-- PROMETHEUS ALERTS TABLE
-- Stores alerts and anomalies detected by Prometheus
-- ============================================================================
CREATE TABLE IF NOT EXISTS prometheus_alerts (
    id SERIAL PRIMARY KEY,

    -- Alert details
    alert_type VARCHAR(30) NOT NULL,  -- PERFORMANCE_DROP, CALIBRATION_DRIFT, DATA_QUALITY, FEATURE_DRIFT
    severity VARCHAR(10) NOT NULL,    -- INFO, WARNING, CRITICAL

    -- Alert context
    title VARCHAR(200) NOT NULL,
    description TEXT,

    -- Metrics that triggered alert
    metric_name VARCHAR(50),
    metric_value FLOAT,
    threshold_value FLOAT,

    -- Status
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prometheus_alerts_type ON prometheus_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_prometheus_alerts_severity ON prometheus_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_prometheus_alerts_resolved ON prometheus_alerts(is_resolved);

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'Prometheus tables created successfully' as status;
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE 'prometheus_%'
ORDER BY table_name;
