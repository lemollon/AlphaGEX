-- QUICK DATABASE CHECK
-- Copy and paste this into Render's PostgreSQL shell or psql

-- 1. Count all tables
SELECT 'TOTAL TABLES' as metric, COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public';

-- 2. Row counts for all tables
SELECT
    table_name,
    (xpath('/row/cnt/text()', xml_count))[1]::text::int as row_count
FROM (
    SELECT table_name,
           query_to_xml(format('SELECT COUNT(*) as cnt FROM %I.%I', table_schema, table_name), false, true, '') as xml_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
) t
ORDER BY row_count DESC;

-- 3. Check GEX history
SELECT 'GEX_HISTORY' as table_name, COUNT(*) as rows, MAX(timestamp) as latest FROM gex_history;

-- 4. Check regime signals
SELECT 'REGIME_SIGNALS' as table_name, COUNT(*) as rows, MAX(timestamp) as latest FROM regime_signals;

-- 5. Check backtest results
SELECT 'BACKTEST_RESULTS' as table_name, COUNT(*) as rows, MAX(timestamp) as latest FROM backtest_results;

-- 6. Check closed trades
SELECT 'CLOSED_TRADES' as table_name, COUNT(*) as rows, MAX(created_at) as latest FROM autonomous_closed_trades;

-- 7. Sample of latest GEX data
SELECT symbol, net_gex, flip_point, spot_price, timestamp
FROM gex_history
ORDER BY timestamp DESC
LIMIT 5;

-- 8. Sample of latest backtest results
SELECT strategy_name, win_rate, total_trades, timestamp
FROM backtest_results
ORDER BY timestamp DESC
LIMIT 5;

-- 9. Check if new ML tables exist
SELECT table_name,
       CASE WHEN table_name IS NOT NULL THEN 'EXISTS' ELSE 'MISSING' END as status
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN (
    'price_history',
    'greeks_snapshots',
    'vix_term_structure',
    'options_flow',
    'ai_analysis_history',
    'backtest_trades',
    'market_snapshots'
);
