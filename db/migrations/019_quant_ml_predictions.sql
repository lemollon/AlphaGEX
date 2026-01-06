-- Migration 019: QUANT ML Predictions Logging Table
-- Logs all ML model predictions for analysis and debugging

CREATE TABLE IF NOT EXISTS ml_predictions (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    symbol VARCHAR(10) DEFAULT 'SPY',
    prediction_type VARCHAR(50) NOT NULL,  -- REGIME_CLASSIFIER, GEX_DIRECTIONAL, ENSEMBLE
    predicted_value VARCHAR(50),           -- SELL_PREMIUM, BUY_CALLS, BULLISH, etc.
    confidence DECIMAL(5,2),               -- 0-100
    features_used JSONB,                   -- Input features and full output
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast querying
CREATE INDEX IF NOT EXISTS idx_ml_predictions_timestamp ON ml_predictions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_type ON ml_predictions(prediction_type);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_symbol ON ml_predictions(symbol);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_value ON ml_predictions(predicted_value);

-- Add comments
COMMENT ON TABLE ml_predictions IS 'Logs all QUANT ML model predictions for analysis';
COMMENT ON COLUMN ml_predictions.prediction_type IS 'Model type: REGIME_CLASSIFIER, GEX_DIRECTIONAL, ENSEMBLE';
COMMENT ON COLUMN ml_predictions.predicted_value IS 'Predicted action/direction';
COMMENT ON COLUMN ml_predictions.features_used IS 'JSON containing input features and full output';
