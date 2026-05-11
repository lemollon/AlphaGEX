-- JOSHUA — per-day setup armed/fired tracking.
-- One row per trading day. Each setup arms at market open and locks after firing.

CREATE TABLE IF NOT EXISTS helios_daily_state (
    trade_date          DATE         PRIMARY KEY,
    wall_fade_fired     BOOLEAN      NOT NULL DEFAULT FALSE,
    wall_break_fired    BOOLEAN      NOT NULL DEFAULT FALSE,
    flip_cross_fired    BOOLEAN      NOT NULL DEFAULT FALSE,
    last_signal_minute  INTEGER,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_helios_daily_state_date
    ON helios_daily_state(trade_date DESC);
