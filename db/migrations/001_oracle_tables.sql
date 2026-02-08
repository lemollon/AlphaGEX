-- ORACLE Tables Migration
-- Creates tables for Oracle ML Advisor, GEX data, and saved strategies
-- Run: psql $DATABASE_URL -f db/migrations/001_oracle_tables.sql

-- ============================================================================
-- ORACLE PREDICTIONS TABLE
-- Stores predictions made by Oracle for feedback loop and analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS oracle_predictions (
    id SERIAL PRIMARY KEY,

    -- Prediction context
    trade_date DATE NOT NULL,
    bot_name VARCHAR(20) NOT NULL,  -- FORTRESS, ATLAS, PHOENIX
    prediction_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Prediction details
    advice VARCHAR(20) NOT NULL,     -- TRADE_FULL, TRADE_REDUCED, SKIP_TODAY
    win_probability FLOAT NOT NULL,
    confidence FLOAT NOT NULL,
    suggested_risk_pct FLOAT,
    suggested_sd_multiplier FLOAT,

    -- GEX-specific (for FORTRESS)
    use_gex_walls BOOLEAN DEFAULT FALSE,
    suggested_put_strike FLOAT,
    suggested_call_strike FLOAT,

    -- Market context at time of prediction
    spot_price FLOAT NOT NULL,
    vix FLOAT,
    gex_net FLOAT,
    gex_regime VARCHAR(10),  -- POSITIVE, NEGATIVE, NEUTRAL
    gex_call_wall FLOAT,
    gex_put_wall FLOAT,
    gex_flip_point FLOAT,
    day_of_week INTEGER,

    -- Model info
    model_version VARCHAR(20),
    reasoning TEXT,
    top_factors JSONB,

    -- Outcome (updated after trade closes)
    actual_outcome VARCHAR(20),      -- MAX_PROFIT, PUT_BREACHED, CALL_BREACHED, etc.
    actual_pnl FLOAT,
    outcome_date TIMESTAMP WITH TIME ZONE,

    -- Indexes
    CONSTRAINT unique_prediction UNIQUE (trade_date, bot_name)
);

CREATE INDEX IF NOT EXISTS idx_oracle_predictions_date ON oracle_predictions(trade_date);
CREATE INDEX IF NOT EXISTS idx_oracle_predictions_bot ON oracle_predictions(bot_name);
CREATE INDEX IF NOT EXISTS idx_oracle_predictions_outcome ON oracle_predictions(actual_outcome);

-- ============================================================================
-- GEX DAILY DATA TABLE
-- Stores daily GEX calculations for ML training and historical analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS gex_daily (
    id SERIAL PRIMARY KEY,

    -- Date and symbol
    trade_date DATE NOT NULL,
    symbol VARCHAR(10) NOT NULL DEFAULT 'SPX',

    -- Price context
    spot_price FLOAT NOT NULL,

    -- Core GEX metrics
    net_gex FLOAT NOT NULL,           -- Total net gamma exposure
    call_gex FLOAT,                    -- Total call gamma
    put_gex FLOAT,                     -- Total put gamma (negative)

    -- Key levels
    call_wall FLOAT,                   -- Strike with highest call GEX
    put_wall FLOAT,                    -- Strike with highest put GEX
    flip_point FLOAT,                  -- Where GEX crosses zero

    -- Normalized metrics
    gex_normalized FLOAT,              -- GEX / spot^2
    gex_regime VARCHAR(10),            -- POSITIVE, NEGATIVE, NEUTRAL
    distance_to_flip_pct FLOAT,        -- (spot - flip) / spot * 100

    -- Position relative to walls
    above_call_wall BOOLEAN,
    below_put_wall BOOLEAN,
    between_walls BOOLEAN,

    -- DTE used for calculation
    dte_max_used INTEGER DEFAULT 7,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_gex_daily UNIQUE (trade_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_gex_daily_date ON gex_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_gex_daily_symbol ON gex_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_gex_daily_regime ON gex_daily(gex_regime);

-- ============================================================================
-- SAVED STRATEGIES TABLE
-- Stores custom backtesting strategies saved by users
-- ============================================================================
CREATE TABLE IF NOT EXISTS saved_strategies (
    id SERIAL PRIMARY KEY,

    -- Strategy identity
    name VARCHAR(100) NOT NULL,
    description TEXT,
    user_id VARCHAR(100),  -- For multi-user support

    -- Strategy type
    strategy_type VARCHAR(50) NOT NULL,  -- iron_condor, gex_protected_iron_condor, etc.

    -- Parameters (JSONB for flexibility)
    parameters JSONB NOT NULL,
    /*
    Expected parameters structure:
    {
        "initial_capital": 1000000,
        "spread_width": 10.0,
        "sd_multiplier": 1.0,
        "risk_per_trade_pct": 5.0,
        "ticker": "SPX",
        "strategy_type": "iron_condor",
        "min_vix": null,
        "max_vix": 35,
        "stop_loss_pct": null,
        "profit_target_pct": 50,
        "trade_days": [0, 1, 2, 3, 4],
        "strike_selection": "sd",
        "fixed_strike_distance": 50,
        "target_delta": 0.16
    }
    */

    -- Backtest results (cached)
    last_backtest_date TIMESTAMP WITH TIME ZONE,
    backtest_results JSONB,
    /*
    Cached backtest summary:
    {
        "win_rate": 68.5,
        "total_return_pct": 45.2,
        "max_drawdown_pct": 12.3,
        "sharpe_ratio": 1.85,
        "total_trades": 250
    }
    */

    -- Metadata
    is_preset BOOLEAN DEFAULT FALSE,  -- System presets vs user saved
    is_public BOOLEAN DEFAULT FALSE,  -- Share with other users
    tags VARCHAR(255)[],              -- For filtering

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_strategy_name UNIQUE (name, user_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_strategies_type ON saved_strategies(strategy_type);
CREATE INDEX IF NOT EXISTS idx_saved_strategies_preset ON saved_strategies(is_preset);
CREATE INDEX IF NOT EXISTS idx_saved_strategies_user ON saved_strategies(user_id);

-- ============================================================================
-- ML TRAINING OUTCOMES TABLE
-- Stores trade outcomes for continuous learning
-- ============================================================================
CREATE TABLE IF NOT EXISTS oracle_training_outcomes (
    id SERIAL PRIMARY KEY,

    -- Trade identification
    trade_date DATE NOT NULL,
    bot_name VARCHAR(20) NOT NULL,

    -- Features at time of trade (for model training)
    features JSONB NOT NULL,
    /*
    {
        "vix": 18.5,
        "vix_percentile_30d": 45,
        "vix_change_1d": -2.1,
        "day_of_week": 2,
        "price_change_1d": 0.5,
        "expected_move_pct": 1.2,
        "win_rate_30d": 0.68,
        "gex_normalized": 0.0015,
        "gex_regime_positive": 1,
        "gex_distance_to_flip_pct": 1.5,
        "gex_between_walls": 1
    }
    */

    -- Outcome
    outcome VARCHAR(20) NOT NULL,  -- MAX_PROFIT, PUT_BREACHED, etc.
    is_win BOOLEAN NOT NULL,       -- Simplified win/loss
    net_pnl FLOAT,

    -- Trade details
    put_strike FLOAT,
    call_strike FLOAT,
    spot_at_entry FLOAT,
    spot_at_exit FLOAT,

    -- Used in training
    used_in_model_version VARCHAR(20),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_training_outcomes_date ON oracle_training_outcomes(trade_date);
CREATE INDEX IF NOT EXISTS idx_training_outcomes_bot ON oracle_training_outcomes(bot_name);
CREATE INDEX IF NOT EXISTS idx_training_outcomes_win ON oracle_training_outcomes(is_win);

-- ============================================================================
-- INSERT DEFAULT STRATEGY PRESETS
-- ============================================================================
INSERT INTO saved_strategies (name, description, strategy_type, parameters, is_preset, tags)
VALUES
    (
        'Conservative IC',
        'Standard Iron Condor with 1.5 SD multiplier for wider strikes and lower risk',
        'iron_condor',
        '{"initial_capital": 1000000, "spread_width": 10.0, "sd_multiplier": 1.5, "risk_per_trade_pct": 3.0, "ticker": "SPX", "max_vix": 30, "trade_days": [0, 1, 2, 3, 4], "strike_selection": "sd"}'::jsonb,
        TRUE,
        ARRAY['conservative', 'iron_condor', 'low_risk']
    ),
    (
        'Aggressive IC',
        'Aggressive Iron Condor with 0.8 SD multiplier for tighter strikes and higher premium',
        'iron_condor',
        '{"initial_capital": 1000000, "spread_width": 10.0, "sd_multiplier": 0.8, "risk_per_trade_pct": 8.0, "ticker": "SPX", "min_vix": 15, "trade_days": [0, 1, 2, 3, 4], "strike_selection": "sd"}'::jsonb,
        TRUE,
        ARRAY['aggressive', 'iron_condor', 'high_premium']
    ),
    (
        'GEX-Protected IC',
        'Iron Condor using GEX walls for strike selection with SD fallback',
        'gex_protected_iron_condor',
        '{"initial_capital": 1000000, "spread_width": 10.0, "sd_multiplier": 1.0, "risk_per_trade_pct": 5.0, "ticker": "SPX", "trade_days": [0, 1, 2, 3, 4], "strike_selection": "sd"}'::jsonb,
        TRUE,
        ARRAY['gex', 'iron_condor', 'protected']
    ),
    (
        'VIX Filter IC',
        'Iron Condor only trading in elevated volatility (VIX 18-35)',
        'iron_condor',
        '{"initial_capital": 1000000, "spread_width": 10.0, "sd_multiplier": 1.0, "risk_per_trade_pct": 5.0, "ticker": "SPX", "min_vix": 18, "max_vix": 35, "trade_days": [0, 1, 2, 3, 4], "strike_selection": "sd"}'::jsonb,
        TRUE,
        ARRAY['vix_filter', 'iron_condor', 'volatility']
    ),
    (
        'Monday-Wednesday IC',
        'Iron Condor trading only on Mon/Wed for lower theta decay competition',
        'iron_condor',
        '{"initial_capital": 1000000, "spread_width": 10.0, "sd_multiplier": 1.0, "risk_per_trade_pct": 5.0, "ticker": "SPX", "trade_days": [0, 2], "strike_selection": "sd"}'::jsonb,
        TRUE,
        ARRAY['day_filter', 'iron_condor']
    )
ON CONFLICT (name, user_id) DO NOTHING;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'Oracle tables created successfully' as status;
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('oracle_predictions', 'gex_daily', 'saved_strategies', 'oracle_training_outcomes')
ORDER BY table_name;
