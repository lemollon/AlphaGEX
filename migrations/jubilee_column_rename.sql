-- JUBILEE Column Rename Migration
-- Renames legacy bot name columns to match the new bot names:
--   ARES → FORTRESS, TITAN → SAMSON, PEGASUS → ANCHOR
--
-- Run BEFORE deploying the code update.
-- Idempotent: safe to run multiple times.
--
-- Usage in Render shell:
--   psql $DATABASE_URL -f migrations/jubilee_column_rename.sql

BEGIN;

-- Detect which column names currently exist and rename accordingly.
-- The production DB may have the original PROMETHEUS-era names (_ares, _titan, _pegasus)
-- or partially renamed names. This handles all cases.

-- cash_deployed_to_ares → cash_deployed_to_fortress
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'cash_deployed_to_ares') THEN
        ALTER TABLE jubilee_positions RENAME COLUMN cash_deployed_to_ares TO cash_deployed_to_fortress;
        RAISE NOTICE 'Renamed cash_deployed_to_ares → cash_deployed_to_fortress';
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'cash_deployed_to_fortress') THEN
        ALTER TABLE jubilee_positions ADD COLUMN cash_deployed_to_fortress DECIMAL(15, 2) DEFAULT 0;
        RAISE NOTICE 'Added missing column cash_deployed_to_fortress';
    ELSE
        RAISE NOTICE 'cash_deployed_to_fortress already exists - no action';
    END IF;
END $$;

-- cash_deployed_to_titan → cash_deployed_to_samson
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'cash_deployed_to_titan') THEN
        ALTER TABLE jubilee_positions RENAME COLUMN cash_deployed_to_titan TO cash_deployed_to_samson;
        RAISE NOTICE 'Renamed cash_deployed_to_titan → cash_deployed_to_samson';
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'cash_deployed_to_samson') THEN
        ALTER TABLE jubilee_positions ADD COLUMN cash_deployed_to_samson DECIMAL(15, 2) DEFAULT 0;
        RAISE NOTICE 'Added missing column cash_deployed_to_samson';
    ELSE
        RAISE NOTICE 'cash_deployed_to_samson already exists - no action';
    END IF;
END $$;

-- cash_deployed_to_pegasus → cash_deployed_to_anchor
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'cash_deployed_to_pegasus') THEN
        ALTER TABLE jubilee_positions RENAME COLUMN cash_deployed_to_pegasus TO cash_deployed_to_anchor;
        RAISE NOTICE 'Renamed cash_deployed_to_pegasus → cash_deployed_to_anchor';
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'cash_deployed_to_anchor') THEN
        ALTER TABLE jubilee_positions ADD COLUMN cash_deployed_to_anchor DECIMAL(15, 2) DEFAULT 0;
        RAISE NOTICE 'Added missing column cash_deployed_to_anchor';
    ELSE
        RAISE NOTICE 'cash_deployed_to_anchor already exists - no action';
    END IF;
END $$;

-- returns_from_ares → returns_from_fortress
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'returns_from_ares') THEN
        ALTER TABLE jubilee_positions RENAME COLUMN returns_from_ares TO returns_from_fortress;
        RAISE NOTICE 'Renamed returns_from_ares → returns_from_fortress';
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'returns_from_fortress') THEN
        ALTER TABLE jubilee_positions ADD COLUMN returns_from_fortress DECIMAL(15, 2) DEFAULT 0;
        RAISE NOTICE 'Added missing column returns_from_fortress';
    ELSE
        RAISE NOTICE 'returns_from_fortress already exists - no action';
    END IF;
END $$;

-- returns_from_titan → returns_from_samson
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'returns_from_titan') THEN
        ALTER TABLE jubilee_positions RENAME COLUMN returns_from_titan TO returns_from_samson;
        RAISE NOTICE 'Renamed returns_from_titan → returns_from_samson';
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'returns_from_samson') THEN
        ALTER TABLE jubilee_positions ADD COLUMN returns_from_samson DECIMAL(15, 2) DEFAULT 0;
        RAISE NOTICE 'Added missing column returns_from_samson';
    ELSE
        RAISE NOTICE 'returns_from_samson already exists - no action';
    END IF;
END $$;

-- returns_from_pegasus → returns_from_anchor
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'returns_from_pegasus') THEN
        ALTER TABLE jubilee_positions RENAME COLUMN returns_from_pegasus TO returns_from_anchor;
        RAISE NOTICE 'Renamed returns_from_pegasus → returns_from_anchor';
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'jubilee_positions' AND column_name = 'returns_from_anchor') THEN
        ALTER TABLE jubilee_positions ADD COLUMN returns_from_anchor DECIMAL(15, 2) DEFAULT 0;
        RAISE NOTICE 'Added missing column returns_from_anchor';
    ELSE
        RAISE NOTICE 'returns_from_anchor already exists - no action';
    END IF;
END $$;

-- Verify final state
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'jubilee_positions'
    AND column_name IN (
        'cash_deployed_to_fortress', 'cash_deployed_to_samson', 'cash_deployed_to_anchor',
        'returns_from_fortress', 'returns_from_samson', 'returns_from_anchor'
    );
    IF col_count = 6 THEN
        RAISE NOTICE 'SUCCESS: All 6 columns verified (fortress, samson, anchor)';
    ELSE
        RAISE WARNING 'ISSUE: Only % of 6 expected columns found', col_count;
    END IF;
END $$;

COMMIT;
