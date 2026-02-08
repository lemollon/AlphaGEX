-- WATCHTOWER Performance Indexes Migration
-- Adds indexes to optimize common WATCHTOWER queries for better load times
-- Run: psql $DATABASE_URL -f db/migrations/006_argus_performance_indexes.sql

-- ============================================================================
-- EXPECTED MOVE CHANGE QUERIES OPTIMIZATION
-- The get_expected_move_change() function queries for prior day and today's
-- opening expected move - these queries need optimized indexes
-- ============================================================================

-- Index for querying yesterday's last snapshot (prior day's close)
-- Query: SELECT ... WHERE DATE(snapshot_time) < CURRENT_DATE ORDER BY snapshot_time DESC LIMIT 1
CREATE INDEX IF NOT EXISTS idx_watchtower_snapshots_snapshot_time_desc
ON watchtower_snapshots(snapshot_time DESC);

-- Index for querying today's first snapshot (open)
-- Query: SELECT ... WHERE DATE(snapshot_time) = CURRENT_DATE ORDER BY snapshot_time ASC LIMIT 1
CREATE INDEX IF NOT EXISTS idx_watchtower_snapshots_snapshot_time_asc
ON watchtower_snapshots(snapshot_time ASC);

-- Composite index for date-based filtering with time ordering
-- This helps with both DATE(snapshot_time) comparisons
CREATE INDEX IF NOT EXISTS idx_watchtower_snapshots_date_time
ON watchtower_snapshots((snapshot_time::date), snapshot_time);

-- ============================================================================
-- REPLAY DATA QUERIES OPTIMIZATION
-- Historical replay needs fast access to snapshots by date
-- ============================================================================

-- Index for replay queries that filter by date and need the latest/earliest time
CREATE INDEX IF NOT EXISTS idx_watchtower_snapshots_replay
ON watchtower_snapshots((snapshot_time::date), snapshot_time DESC);

-- ============================================================================
-- COMMENTARY QUERIES OPTIMIZATION
-- Commentary is frequently queried for display
-- ============================================================================

-- Index for recent commentary lookup
CREATE INDEX IF NOT EXISTS idx_watchtower_commentary_created_desc
ON watchtower_commentary(created_at DESC);

-- ============================================================================
-- STRIKES QUERIES OPTIMIZATION
-- Strike data is frequently joined with snapshots
-- ============================================================================

-- Composite index for strike queries that filter by snapshot and order by strike
CREATE INDEX IF NOT EXISTS idx_argus_strikes_snapshot_strike
ON argus_strikes(snapshot_id, strike);

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'WATCHTOWER performance indexes created successfully' as status;
SELECT indexname, tablename FROM pg_indexes
WHERE tablename LIKE 'argus_%'
ORDER BY tablename, indexname;
