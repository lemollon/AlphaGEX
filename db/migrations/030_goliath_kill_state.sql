-- Migration 030: GOLIATH kill-switch state
--
-- Per master spec section 6 + Phase 5 acceptance criteria:
-- kill state must persist across process restarts. One active row per
-- (scope, instance_name); manual override clears active flag.
--
-- scope = 'INSTANCE'  -> instance_name is one of MSTU/TSLL/NVDL/CONL/AMDL
-- scope = 'PLATFORM'  -> instance_name is NULL (kill applies to all instances)

CREATE TABLE IF NOT EXISTS goliath_kill_state (
    id              BIGSERIAL PRIMARY KEY,
    scope           VARCHAR(10) NOT NULL CHECK (scope IN ('INSTANCE', 'PLATFORM')),
    instance_name   VARCHAR(20),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_id      VARCHAR(8) NOT NULL,
    reason          TEXT NOT NULL DEFAULT '',
    context         JSONB NOT NULL DEFAULT '{}'::JSONB,
    killed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cleared_at      TIMESTAMPTZ,
    cleared_by      TEXT,
    CONSTRAINT goliath_kill_scope_consistency
        CHECK ((scope = 'PLATFORM' AND instance_name IS NULL)
            OR (scope = 'INSTANCE' AND instance_name IS NOT NULL))
);

-- Fast lookup: "is this scope currently killed?"
CREATE INDEX IF NOT EXISTS idx_goliath_kill_state_active
    ON goliath_kill_state (scope, instance_name)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_goliath_kill_state_killed_at
    ON goliath_kill_state (killed_at DESC);

COMMENT ON TABLE goliath_kill_state IS
    'Persistent kill-switch state per master spec section 6. '
    'One active row per (scope, instance_name); manual override '
    'sets active=FALSE + cleared_at/cleared_by.';
