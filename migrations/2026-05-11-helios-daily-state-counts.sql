-- JOSHUA — extend helios_daily_state with per-setup fire counts.
-- Replaces the boolean _fired flags with INT counters so each setup can fire
-- up to max_trades_per_setup_per_day times. Booleans stay for backward compat
-- and are kept in sync.

ALTER TABLE helios_daily_state
    ADD COLUMN IF NOT EXISTS wall_fade_count   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS wall_break_count  INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS flip_cross_count  INTEGER NOT NULL DEFAULT 0;

-- Backfill counts from existing booleans so historical rows aren't reset.
UPDATE helios_daily_state SET wall_fade_count = 1
    WHERE wall_fade_fired AND wall_fade_count = 0;
UPDATE helios_daily_state SET wall_break_count = 1
    WHERE wall_break_fired AND wall_break_count = 0;
UPDATE helios_daily_state SET flip_cross_count = 1
    WHERE flip_cross_fired AND flip_cross_count = 0;
