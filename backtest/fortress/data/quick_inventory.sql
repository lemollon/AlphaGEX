-- FORTRESS Backtest - Quick Data Inventory
-- Run this FIRST on Render to see what data is available
-- Usage: psql $DATABASE_URL -f quick_inventory.sql

\echo '============================================'
\echo '  FORTRESS Backtest Data Inventory'
\echo '============================================'

\echo ''
\echo '--- CORE OPTIONS DATA ---'
SELECT 'orat_options_eod (SPY 0-7DTE)' as table_name, COUNT(*) as rows, MIN(trade_date)::text as from_date, MAX(trade_date)::text as to_date FROM orat_options_eod WHERE ticker='SPY' AND dte BETWEEN 0 AND 7;
SELECT 'orat_options_eod (SPX 0-7DTE)' as table_name, COUNT(*) as rows, MIN(trade_date)::text as from_date, MAX(trade_date)::text as to_date FROM orat_options_eod WHERE ticker='SPX' AND dte BETWEEN 0 AND 7;
SELECT 'options_chain_snapshots (SPY)' as table_name, COUNT(*) as rows, MIN(timestamp::date)::text as from_date, MAX(timestamp::date)::text as to_date FROM options_chain_snapshots WHERE symbol='SPY';

\echo ''
\echo '--- PRICE & VIX ---'
SELECT 'price_history (SPY daily)' as table_name, COUNT(*) as rows, MIN(timestamp::date)::text as from_date, MAX(timestamp::date)::text as to_date FROM price_history WHERE symbol='SPY' AND timeframe='1d';
SELECT 'price_history (SPY 1min)' as table_name, COUNT(*) as rows, MIN(timestamp::date)::text as from_date, MAX(timestamp::date)::text as to_date FROM price_history WHERE symbol='SPY' AND timeframe='1min';
SELECT 'price_history (SPY ALL)' as table_name, COUNT(*) as rows, MIN(timestamp::date)::text as from_date, MAX(timestamp::date)::text as to_date FROM price_history WHERE symbol='SPY';
SELECT 'vix_term_structure' as table_name, COUNT(*) as rows, MIN(timestamp::date)::text as from_date, MAX(timestamp::date)::text as to_date FROM vix_term_structure;

\echo ''
\echo '--- GEX DATA ---'
SELECT 'gex_structure_daily (SPY)' as table_name, COUNT(*) as rows, MIN(trade_date)::text as from_date, MAX(trade_date)::text as to_date FROM gex_structure_daily WHERE symbol='SPY';
SELECT 'gex_structure_daily (SPX)' as table_name, COUNT(*) as rows, MIN(trade_date)::text as from_date, MAX(trade_date)::text as to_date FROM gex_structure_daily WHERE symbol='SPX';
SELECT 'gex_daily' as table_name, COUNT(*) as rows, MIN(trade_date)::text as from_date, MAX(trade_date)::text as to_date FROM gex_daily;
SELECT 'gamma_history (SPY)' as table_name, COUNT(*) as rows, MIN(date)::text as from_date, MAX(date)::text as to_date FROM gamma_history WHERE symbol='SPY';

\echo ''
\echo '--- WATCHTOWER DATA ---'
SELECT 'watchtower_snapshots (SPY)' as table_name, COUNT(*) as rows, MIN(snapshot_time::date)::text as from_date, MAX(snapshot_time::date)::text as to_date FROM watchtower_snapshots WHERE symbol='SPY';
SELECT 'argus_strikes' as table_name, COUNT(*) as rows, MIN(created_at::date)::text as from_date, MAX(created_at::date)::text as to_date FROM argus_strikes;
SELECT 'argus_gamma_flips' as table_name, COUNT(*) as rows, MIN(flip_time::date)::text as from_date, MAX(flip_time::date)::text as to_date FROM argus_gamma_flips;
SELECT 'argus_predictions' as table_name, COUNT(*) as rows, MIN(prediction_date)::text as from_date, MAX(prediction_date)::text as to_date FROM argus_predictions;

\echo ''
\echo '--- REGIME & VOLATILITY ---'
SELECT 'regime_signals' as table_name, COUNT(*) as rows, MIN(timestamp::date)::text as from_date, MAX(timestamp::date)::text as to_date FROM regime_signals;
SELECT 'volatility_surface_snapshots' as table_name, COUNT(*) as rows, MIN(snapshot_time::date)::text as from_date, MAX(snapshot_time::date)::text as to_date FROM volatility_surface_snapshots;

\echo ''
\echo '--- FORTRESS BOT DATA ---'
SELECT 'scan_activity (FORTRESS)' as table_name, COUNT(*) as rows, MIN(date)::text as from_date, MAX(date)::text as to_date FROM scan_activity WHERE bot_name='FORTRESS';
SELECT 'scan_activity (ALL)' as table_name, COUNT(*) as rows, MIN(date)::text as from_date, MAX(date)::text as to_date FROM scan_activity;
SELECT 'prophet_predictions (FORTRESS)' as table_name, COUNT(*) as rows, MIN(trade_date)::text as from_date, MAX(trade_date)::text as to_date FROM prophet_predictions WHERE bot_name='FORTRESS';
SELECT 'prophet_training_outcomes' as table_name, COUNT(*) as rows, MIN(trade_date)::text as from_date, MAX(trade_date)::text as to_date FROM prophet_training_outcomes WHERE bot_name='FORTRESS';
SELECT 'fortress_positions' as table_name, COUNT(*) as rows, MIN(created_at::date)::text as from_date, MAX(created_at::date)::text as to_date FROM fortress_positions;
SELECT 'fortress_daily_performance' as table_name, COUNT(*) as rows, MIN(date)::text as from_date, MAX(date)::text as to_date FROM fortress_daily_performance;

\echo ''
\echo '--- OPTIONS CHAIN SNAPSHOTS BY MONTH ---'
SELECT DATE_TRUNC('month', timestamp)::date as month, COUNT(*) as snapshots, COUNT(DISTINCT timestamp::date) as days
FROM options_chain_snapshots WHERE symbol='SPY'
GROUP BY 1 ORDER BY 1;

\echo ''
\echo '--- WATCHTOWER SNAPSHOTS BY MONTH ---'
SELECT DATE_TRUNC('month', snapshot_time)::date as month, COUNT(*) as snapshots, COUNT(DISTINCT snapshot_time::date) as days
FROM watchtower_snapshots WHERE symbol='SPY'
GROUP BY 1 ORDER BY 1;

\echo ''
\echo '============================================'
\echo '  DONE - Copy this output and paste it back!'
\echo '============================================'
