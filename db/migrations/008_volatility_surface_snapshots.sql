-- Volatility Surface Snapshots Migration
-- Stores periodic volatility surface analysis for historical tracking and ML training
-- Run: psql $DATABASE_URL -f db/migrations/008_volatility_surface_snapshots.sql

-- ============================================================================
-- VOLATILITY SURFACE SNAPSHOTS TABLE
-- Stores complete volatility surface analysis at regular intervals
-- ============================================================================
CREATE TABLE IF NOT EXISTS volatility_surface_snapshots (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
    snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Price context
    spot_price DECIMAL(10,2) NOT NULL,

    -- ATM IV metrics
    atm_iv DECIMAL(6,4),                -- ATM implied volatility
    iv_rank DECIMAL(5,2),               -- IV rank (0-100)
    iv_percentile DECIMAL(5,2),         -- IV percentile (0-100)

    -- Skew metrics
    skew_25d DECIMAL(6,4),              -- 25-delta put IV - 25-delta call IV
    skew_10d DECIMAL(6,4),              -- 10-delta skew
    risk_reversal DECIMAL(6,4),         -- 25-delta risk reversal
    butterfly DECIMAL(6,4),             -- Butterfly (smile curvature)
    put_skew_slope DECIMAL(8,6),        -- Put skew slope
    call_skew_slope DECIMAL(8,6),       -- Call skew slope
    skew_ratio DECIMAL(6,4),            -- Put/call skew ratio

    -- Skew regime classification
    skew_regime VARCHAR(30),            -- EXTREME_PUT_SKEW, HIGH_PUT_SKEW, NORMAL_SKEW, FLAT_SKEW, CALL_SKEW

    -- Term structure
    term_slope DECIMAL(8,6),            -- IV change per day
    term_regime VARCHAR(30),            -- STEEP_CONTANGO, NORMAL_CONTANGO, FLAT, BACKWARDATION, STEEP_BACKWARDATION
    front_month_iv DECIMAL(6,4),        -- Front month ATM IV
    back_month_iv DECIMAL(6,4),         -- Back month ATM IV
    is_inverted BOOLEAN DEFAULT FALSE,  -- Term structure inversion

    -- IV by DTE
    iv_7dte DECIMAL(6,4),
    iv_14dte DECIMAL(6,4),
    iv_30dte DECIMAL(6,4),
    iv_45dte DECIMAL(6,4),
    iv_60dte DECIMAL(6,4),

    -- Trading recommendations
    recommended_dte INTEGER,            -- Best DTE given term structure
    directional_bias VARCHAR(10),       -- bullish, neutral, bearish
    should_sell_premium BOOLEAN,        -- Premium selling favorable?
    optimal_strategy VARCHAR(50),       -- Recommended strategy type
    strategy_reasoning TEXT,            -- Why this strategy

    -- SVI parameters (for advanced surface modeling)
    svi_params JSONB,                   -- {a, b, rho, m, sigma} per expiration

    -- Fit quality
    fit_quality_mae DECIMAL(8,6),       -- Mean absolute error
    fit_quality_n_points INTEGER,       -- Number of data points
    fit_quality_n_expirations INTEGER,  -- Number of expirations fitted

    -- Source
    data_source VARCHAR(50) DEFAULT 'TRADIER',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_vol_surface_symbol_time ON volatility_surface_snapshots(symbol, snapshot_time);
CREATE INDEX IF NOT EXISTS idx_vol_surface_skew_regime ON volatility_surface_snapshots(skew_regime);
CREATE INDEX IF NOT EXISTS idx_vol_surface_term_regime ON volatility_surface_snapshots(term_regime);
CREATE INDEX IF NOT EXISTS idx_vol_surface_iv_rank ON volatility_surface_snapshots(iv_rank);

-- ============================================================================
-- VOLATILITY SURFACE ALERTS TABLE
-- Stores alerts when surface conditions change significantly
-- ============================================================================
CREATE TABLE IF NOT EXISTS volatility_surface_alerts (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
    alert_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Alert type
    alert_type VARCHAR(50) NOT NULL,    -- SKEW_REGIME_CHANGE, TERM_INVERSION, IV_SPIKE, IV_CRUSH
    severity VARCHAR(10) NOT NULL,      -- LOW, MEDIUM, HIGH, CRITICAL

    -- Alert details
    message TEXT NOT NULL,
    previous_value TEXT,
    new_value TEXT,

    -- Context
    spot_price DECIMAL(10,2),
    iv_rank DECIMAL(5,2),

    -- Status
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vol_alerts_symbol_time ON volatility_surface_alerts(symbol, alert_time);
CREATE INDEX IF NOT EXISTS idx_vol_alerts_type ON volatility_surface_alerts(alert_type);

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'Volatility surface tables created successfully' as status;
