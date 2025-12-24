-- ============================================================================
-- Migration 010: Add Entry Context to apache_positions
-- ============================================================================
-- Adds columns to store market conditions, Greeks, and ML signals at entry
-- so we don't need to join with trading_decisions for detailed position data.
-- ============================================================================

-- Add VIX at entry
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS vix_at_entry FLOAT;

-- Add GEX wall levels at entry
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS put_wall_at_entry FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS call_wall_at_entry FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS flip_point_at_entry FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS net_gex_at_entry FLOAT;

-- Add Greeks at entry (net values for the spread)
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS entry_delta FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS entry_gamma FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS entry_theta FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS entry_vega FLOAT;

-- Add ML signal data at entry
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS ml_direction VARCHAR(20);
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS ml_confidence FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS ml_win_probability FLOAT;

-- Add computed fields for convenience
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS breakeven FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS rr_ratio FLOAT;

-- Create index for querying by VIX regime
CREATE INDEX IF NOT EXISTS idx_apache_positions_vix ON apache_positions(vix_at_entry);

-- Add comments
COMMENT ON COLUMN apache_positions.vix_at_entry IS 'VIX level at time of entry';
COMMENT ON COLUMN apache_positions.put_wall_at_entry IS 'GEX put wall strike at entry';
COMMENT ON COLUMN apache_positions.call_wall_at_entry IS 'GEX call wall strike at entry';
COMMENT ON COLUMN apache_positions.flip_point_at_entry IS 'GEX gamma flip point at entry';
COMMENT ON COLUMN apache_positions.net_gex_at_entry IS 'Net GEX value at entry';
COMMENT ON COLUMN apache_positions.entry_delta IS 'Net delta of spread at entry';
COMMENT ON COLUMN apache_positions.entry_gamma IS 'Net gamma of spread at entry';
COMMENT ON COLUMN apache_positions.entry_theta IS 'Net theta of spread at entry';
COMMENT ON COLUMN apache_positions.entry_vega IS 'Net vega of spread at entry';
COMMENT ON COLUMN apache_positions.ml_direction IS 'ML model predicted direction (UP/DOWN/FLAT)';
COMMENT ON COLUMN apache_positions.ml_confidence IS 'ML model confidence (0-1)';
COMMENT ON COLUMN apache_positions.ml_win_probability IS 'ML predicted win probability (0-1)';
COMMENT ON COLUMN apache_positions.breakeven IS 'Breakeven price for the spread';
COMMENT ON COLUMN apache_positions.rr_ratio IS 'Risk/Reward ratio at entry';
