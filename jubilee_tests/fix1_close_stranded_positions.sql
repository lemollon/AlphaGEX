-- ═══════════════════════════════════════════════════════════════════
-- FIX 1: Close the 5 stranded JUBILEE IC positions
-- ═══════════════════════════════════════════════════════════════════
-- These 5 positions were opened on Feb 13 as 7DTE Iron Condors
-- but the monitoring loop died (jubilee_ic_trader failed to init).
-- current_dte is stuck at 7 because check_exit_conditions() was
-- never called to update it.
--
-- All 5 expired OTM on Feb 20, 2026:
--   SPX closed at ~6889.5
--   All put spreads: 6710-6745 range (well below 6889) ✅
--   All call spreads: 6925-6955 range (well above 6889) ✅
--   FULL CREDIT KEPT — expired worthless.
--
-- ⚠️ CONFIRM WITH LERON BEFORE RUNNING ⚠️
-- ═══════════════════════════════════════════════════════════════════

-- STEP 0: VERIFY — Show the 5 stranded positions
SELECT
    position_id,
    put_short_strike || '/' || put_long_strike AS put_spread,
    call_short_strike || '/' || call_long_strike AS call_spread,
    expiration,
    current_dte AS stuck_dte,
    entry_credit,
    contracts,
    entry_credit * contracts * 100 AS full_credit_pnl,
    status,
    open_time
FROM jubilee_ic_positions
WHERE status IN ('open', 'OPEN', 'pending')
ORDER BY open_time;

-- STEP 1: Update positions to closed with correct P&L
-- All expired OTM → exit_price = 0 (worthless), realized_pnl = full credit
UPDATE jubilee_ic_positions
SET
    status = 'closed',
    close_reason = 'EXPIRED_OTM_MANUAL',
    close_time = '2026-02-20 15:00:00-06',  -- 3:00 PM CT market close
    exit_price = 0,                          -- expired worthless
    realized_pnl = entry_credit * contracts * 100,  -- full credit kept as profit
    current_dte = 0,                         -- fix the stuck DTE
    updated_at = NOW()
WHERE status IN ('open', 'OPEN', 'pending')
  AND expiration <= '2026-02-20';

-- STEP 2: Copy to closed trades table for historical record
INSERT INTO jubilee_ic_closed_trades (
    position_id, source_box_position_id, ticker,
    put_short_strike, put_long_strike, call_short_strike, call_long_strike,
    spread_width, expiration, dte_at_entry,
    contracts, entry_credit, exit_price, realized_pnl,
    spot_at_entry, vix_at_entry, gamma_regime, oracle_confidence,
    open_time, close_time, close_reason, hold_duration_minutes
)
SELECT
    position_id, source_box_position_id, ticker,
    put_short_strike, put_long_strike, call_short_strike, call_long_strike,
    spread_width, expiration, dte_at_entry,
    contracts, entry_credit, exit_price, realized_pnl,
    spot_at_entry, vix_at_entry, gamma_regime_at_entry, oracle_confidence,
    open_time, close_time, close_reason,
    EXTRACT(EPOCH FROM (close_time - open_time))::int / 60 AS hold_duration_minutes
FROM jubilee_ic_positions
WHERE close_reason = 'EXPIRED_OTM_MANUAL'
ON CONFLICT (position_id) DO NOTHING;

-- STEP 3: Verify — Should show 0 open positions
SELECT COUNT(*) AS remaining_open
FROM jubilee_ic_positions
WHERE status IN ('open', 'OPEN', 'pending');

-- STEP 4: Verify — Show the closed trades
SELECT
    position_id,
    entry_credit,
    exit_price,
    realized_pnl,
    close_reason,
    close_time
FROM jubilee_ic_closed_trades
WHERE close_reason = 'EXPIRED_OTM_MANUAL'
ORDER BY close_time DESC;

-- STEP 5: Summary
SELECT
    COUNT(*) AS total_closed,
    SUM(realized_pnl) AS total_pnl,
    AVG(entry_credit) AS avg_entry_credit,
    AVG(contracts) AS avg_contracts
FROM jubilee_ic_closed_trades
WHERE close_reason = 'EXPIRED_OTM_MANUAL';
