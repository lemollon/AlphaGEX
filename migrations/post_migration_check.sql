-- =============================================================================
-- POST-MIGRATION CHECK: AlphaGEX Bot Rename
-- =============================================================================
-- READ-ONLY script. Run this AFTER bot_rename_migration_v2.sql to verify
-- the migration succeeded. Compare output with pre_migration_check.sql.
--
-- What it checks:
--   1. All new-name tables exist with row counts
--   2. Zero old-name tables remain
--   3. bot_name column values are all updated
--   4. Config keys are updated
--   5. ml_models model_name values are updated
--
-- Usage:
--   psql "YOUR_CONNECTION_STRING" -f migrations/post_migration_check.sql
--
-- Date: 2026-02-09
-- =============================================================================

\echo ''
\echo '============================================='
\echo '  POST-MIGRATION CHECK: Bot Rename'
\echo '============================================='
\echo ''

-- =============================================================================
-- 1. NEW-NAME TABLES (should all exist after migration)
-- =============================================================================
\echo '--- NEW-NAME TABLES AND ROW COUNTS ---'
\echo ''

SELECT
    'NEW' AS status,
    t.table_name,
    (xpath('/row/cnt/text()',
        query_to_xml(format('SELECT COUNT(*) AS cnt FROM %I', t.table_name), false, true, '')
    ))[1]::text::bigint AS row_count
FROM information_schema.tables t
WHERE t.table_schema = 'public'
AND t.table_name LIKE ANY(ARRAY[
    'fortress_%', 'samson_%', 'anchor_%', 'gideon_%',
    'valor_%', 'jubilee_%',
    'proverbs_%',
    'prophet_%', 'discernment_%', 'watchtower_%',
    'chronicles_%', 'glory_%'
])
ORDER BY t.table_name;

-- NOTE: solomon_* tables are the ATHENA bot tables (renamed athena→solomon).
-- They are listed separately because solomon_* also existed before as advisory tables.
\echo ''
\echo '--- SOLOMON (bot) TABLES (renamed from athena_*) ---'

SELECT
    'SOLOMON_BOT' AS status,
    t.table_name,
    (xpath('/row/cnt/text()',
        query_to_xml(format('SELECT COUNT(*) AS cnt FROM %I', t.table_name), false, true, '')
    ))[1]::text::bigint AS row_count
FROM information_schema.tables t
WHERE t.table_schema = 'public'
AND t.table_name LIKE 'solomon_%'
ORDER BY t.table_name;

\echo ''
\echo '--- TOTAL NEW-NAME TABLES ---'
SELECT COUNT(*) AS new_table_count
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE ANY(ARRAY[
    'fortress_%', 'solomon_%', 'samson_%', 'anchor_%', 'gideon_%',
    'valor_%', 'jubilee_%',
    'proverbs_%',
    'prophet_%', 'discernment_%', 'watchtower_%',
    'chronicles_%', 'glory_%'
]);

-- =============================================================================
-- 2. OLD-NAME TABLES (should be ZERO after migration)
-- =============================================================================
\echo ''
\echo '--- OLD-NAME TABLES REMAINING (should be empty!) ---'

SELECT
    'STILL_OLD' AS status,
    table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE ANY(ARRAY[
    'ares_%', 'athena_%', 'titan_%', 'pegasus_%', 'icarus_%',
    'heracles_%', 'prometheus_%',
    'oracle_%', 'apollo_%', 'argus_%',
    'kronos_%', 'hyperion_%'
])
ORDER BY table_name;

\echo ''
SELECT
    CASE WHEN COUNT(*) = 0
        THEN 'PASS: Zero old-name tables remain'
        ELSE 'FAIL: ' || COUNT(*) || ' old-name tables still exist!'
    END AS table_rename_result
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE ANY(ARRAY[
    'ares_%', 'athena_%', 'titan_%', 'pegasus_%', 'icarus_%',
    'heracles_%', 'prometheus_%',
    'oracle_%', 'apollo_%', 'argus_%',
    'kronos_%', 'hyperion_%'
]);

-- =============================================================================
-- 3. BOT_NAME VALUES IN bot_decision_logs (should be all Biblical)
-- =============================================================================
\echo ''
\echo '--- bot_decision_logs: DISTINCT bot_name VALUES ---'

SELECT bot_name, COUNT(*) AS row_count
FROM bot_decision_logs
GROUP BY bot_name
ORDER BY bot_name;

\echo ''
SELECT
    CASE WHEN COUNT(*) = 0
        THEN 'PASS: Zero old Greek names in bot_decision_logs'
        ELSE 'FAIL: ' || COUNT(*) || ' rows still have old Greek names!'
    END AS bot_name_result
FROM bot_decision_logs
WHERE bot_name IN (
    'ARES', 'ATHENA', 'TITAN', 'PEGASUS', 'ICARUS',
    'PHOENIX', 'ATLAS', 'HERMES', 'PROMETHEUS', 'HERACLES',
    'ORACLE', 'SAGE', 'ARGUS', 'GEXIS', 'KRONOS',
    'HYPERION', 'APOLLO', 'ORION', 'NEXUS', 'SOLOMON'
);

-- =============================================================================
-- 4. CONFIG KEYS (should all be new names)
-- =============================================================================
\echo ''
\echo '--- autonomous_config: BOT-SPECIFIC KEYS ---'

SELECT key, LEFT(value, 50) AS value_preview
FROM autonomous_config
WHERE key LIKE ANY(ARRAY[
    'fortress_%', 'solomon_%', 'samson_%', 'anchor_%', 'gideon_%', 'valor_%',
    'ares_%', 'athena_%', 'titan_%', 'pegasus_%', 'icarus_%', 'heracles_%'
])
ORDER BY key;

\echo ''
SELECT
    CASE WHEN COUNT(*) = 0
        THEN 'PASS: Zero old config keys remain'
        ELSE 'FAIL: ' || COUNT(*) || ' old config keys still exist!'
    END AS config_key_result
FROM autonomous_config
WHERE key IN (
    'ares_starting_capital', 'athena_starting_capital',
    'titan_starting_capital', 'pegasus_starting_capital',
    'icarus_starting_capital', 'heracles_starting_capital',
    'ares_mode', 'ares_ticker'
);

-- =============================================================================
-- 5. ML_MODELS MODEL_NAME VALUES
-- =============================================================================
\echo ''
\echo '--- ml_models: DISTINCT model_name VALUES ---'

SELECT model_name, COUNT(*) AS row_count
FROM ml_models
GROUP BY model_name
ORDER BY model_name;

\echo ''
SELECT
    CASE WHEN COUNT(*) = 0
        THEN 'PASS: Zero old ML model names remain'
        ELSE 'FAIL: ' || COUNT(*) || ' old ML model names still exist!'
    END AS ml_model_result
FROM ml_models
WHERE model_name IN ('ares_ml', 'heracles_ml');

-- =============================================================================
-- 6. TRADING_DECISIONS STRATEGY VALUES
-- =============================================================================
\echo ''
\echo '--- trading_decisions: DISTINCT strategy VALUES ---'

SELECT strategy, COUNT(*) AS row_count
FROM trading_decisions
WHERE strategy IS NOT NULL
GROUP BY strategy
ORDER BY strategy;

\echo ''
SELECT
    CASE WHEN COUNT(*) = 0
        THEN 'PASS: Zero old Greek names in trading_decisions.strategy'
        ELSE 'FAIL: ' || COUNT(*) || ' rows still have old Greek names in strategy!'
    END AS strategy_result
FROM trading_decisions
WHERE strategy LIKE ANY(ARRAY[
    '%ARES%', '%ATHENA%', '%TITAN%', '%PEGASUS%', '%ICARUS%',
    '%PHOENIX%', '%HERACLES%'
]);

-- =============================================================================
-- SUMMARY
-- =============================================================================
\echo ''
\echo '============================================='
\echo '  POST-MIGRATION CHECK COMPLETE'
\echo '============================================='
\echo '  Compare row counts with pre-migration output.'
\echo '  All checks should show PASS.'
\echo '============================================='
\echo ''
