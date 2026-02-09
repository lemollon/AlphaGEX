-- =============================================================================
-- PRE-MIGRATION CHECK: AlphaGEX Bot Rename
-- =============================================================================
-- READ-ONLY script. Run this BEFORE bot_rename_migration_v2.sql to capture
-- the current state of your database.
--
-- What it checks:
--   1. Which old-name tables exist (and their row counts)
--   2. Which new-name tables already exist (conflict detection)
--   3. Current bot_name values in bot_decision_logs
--   4. Current config keys in autonomous_config
--   5. Current model_name values in ml_models
--
-- Usage:
--   psql "YOUR_CONNECTION_STRING" -f migrations/pre_migration_check.sql
--
-- Date: 2026-02-09
-- =============================================================================

\echo ''
\echo '============================================='
\echo '  PRE-MIGRATION CHECK: Bot Rename'
\echo '============================================='
\echo ''

-- =============================================================================
-- 1. OLD-NAME TABLES (should exist before migration)
-- =============================================================================
\echo '--- OLD-NAME TABLES AND ROW COUNTS ---'
\echo ''

SELECT
    'OLD' AS status,
    t.table_name,
    (xpath('/row/cnt/text()',
        query_to_xml(format('SELECT COUNT(*) AS cnt FROM %I', t.table_name), false, true, '')
    ))[1]::text::bigint AS row_count
FROM information_schema.tables t
WHERE t.table_schema = 'public'
AND t.table_name LIKE ANY(ARRAY[
    'ares_%', 'athena_%', 'titan_%', 'pegasus_%', 'icarus_%',
    'heracles_%', 'prometheus_%',
    'solomon_%',
    'oracle_%', 'apollo_%', 'argus_%',
    'kronos_%', 'hyperion_%'
])
ORDER BY t.table_name;

\echo ''
\echo '--- TOTAL OLD-NAME TABLES ---'
SELECT COUNT(*) AS old_table_count
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE ANY(ARRAY[
    'ares_%', 'athena_%', 'titan_%', 'pegasus_%', 'icarus_%',
    'heracles_%', 'prometheus_%',
    'solomon_%',
    'oracle_%', 'apollo_%', 'argus_%',
    'kronos_%', 'hyperion_%'
]);

-- =============================================================================
-- 2. NEW-NAME TABLES (should NOT exist yet — conflicts)
-- =============================================================================
\echo ''
\echo '--- NEW-NAME TABLES ALREADY EXISTING (conflicts!) ---'

SELECT
    'CONFLICT' AS status,
    table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE ANY(ARRAY[
    'fortress_%', 'solomon_%', 'samson_%', 'anchor_%', 'gideon_%',
    'valor_%', 'jubilee_%',
    'proverbs_%',
    'prophet_%', 'discernment_%', 'watchtower_%',
    'chronicles_%', 'glory_%'
])
ORDER BY table_name;

\echo ''
\echo '  NOTE: solomon_* tables above are EXPECTED — they are the advisory'
\echo '  tables that will be renamed to proverbs_* BEFORE athena→solomon.'
\echo '  proverbs_* tables may also exist if code already created them.'
\echo ''

-- =============================================================================
-- 3. BOT_NAME VALUES IN bot_decision_logs
-- =============================================================================
\echo '--- bot_decision_logs: DISTINCT bot_name VALUES ---'

SELECT bot_name, COUNT(*) AS row_count
FROM bot_decision_logs
GROUP BY bot_name
ORDER BY bot_name;

-- =============================================================================
-- 4. AUTONOMOUS_CONFIG KEYS (bot-specific)
-- =============================================================================
\echo ''
\echo '--- autonomous_config: BOT-SPECIFIC KEYS ---'

SELECT key, LEFT(value, 50) AS value_preview
FROM autonomous_config
WHERE key LIKE ANY(ARRAY[
    'ares_%', 'athena_%', 'titan_%', 'pegasus_%', 'icarus_%',
    'heracles_%', 'fortress_%', 'solomon_%', 'samson_%',
    'anchor_%', 'gideon_%', 'valor_%'
])
ORDER BY key;

-- =============================================================================
-- 5. ML_MODELS MODEL_NAME VALUES
-- =============================================================================
\echo ''
\echo '--- ml_models: DISTINCT model_name VALUES ---'

SELECT model_name, COUNT(*) AS row_count
FROM ml_models
GROUP BY model_name
ORDER BY model_name;

-- =============================================================================
-- 6. TRADING_DECISIONS STRATEGY VALUES (bot references)
-- =============================================================================
\echo ''
\echo '--- trading_decisions: DISTINCT strategy VALUES ---'

SELECT strategy, COUNT(*) AS row_count
FROM trading_decisions
WHERE strategy IS NOT NULL
GROUP BY strategy
ORDER BY strategy;

-- =============================================================================
-- SUMMARY
-- =============================================================================
\echo ''
\echo '============================================='
\echo '  PRE-MIGRATION CHECK COMPLETE'
\echo '============================================='
\echo '  Save this output! Compare with post-migration check'
\echo '  to verify row counts match after rename.'
\echo '============================================='
\echo ''
