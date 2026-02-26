#!/usr/bin/env node
/**
 * Verify Iron Forge → AlphaGEX table mapping
 *
 * Run on Render shell:
 *   node ironforge/scripts/verify_table_mapping.js
 *
 * Tests every SQL query the Iron Forge routes will execute after the
 * flame→faith / spark→grace table mapping fix.
 */

const { Pool } = require('pg')

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
})

const PASS = '\x1b[32m✓\x1b[0m'
const FAIL = '\x1b[31m✗\x1b[0m'
const WARN = '\x1b[33m!\x1b[0m'

let passed = 0
let failed = 0
let warnings = 0

async function test(name, sql, params, check) {
  try {
    const res = await pool.query(sql, params || [])
    const result = check(res.rows)
    if (result === true) {
      console.log(`  ${PASS} ${name}`)
      passed++
    } else if (result === 'warn') {
      console.log(`  ${WARN} ${name} (empty but query succeeded)`)
      warnings++
    } else {
      console.log(`  ${FAIL} ${name}: ${result}`)
      failed++
    }
  } catch (err) {
    console.log(`  ${FAIL} ${name}: ${err.message}`)
    failed++
  }
}

async function main() {
  console.log('\n=== Iron Forge Table Mapping Verification ===\n')

  // ---------- FLAME (faith) ----------
  console.log('FLAME → faith_* tables (2DTE):')

  await test(
    'status: paper_account with dte_mode',
    `SELECT starting_capital, current_balance, cumulative_pnl, is_active
     FROM faith_paper_account
     WHERE is_active = TRUE AND dte_mode = $1
     ORDER BY id DESC LIMIT 1`,
    ['2DTE'],
    (rows) => rows.length > 0 ? true : 'warn'
  )

  await test(
    'status: position count with dte_mode',
    `SELECT COUNT(*) as cnt FROM faith_positions
     WHERE status = 'open' AND dte_mode = $1`,
    ['2DTE'],
    () => true
  )

  await test(
    'status: heartbeat as FAITH',
    `SELECT scan_count, last_heartbeat, status FROM bot_heartbeats
     WHERE bot_name = $1`,
    ['FAITH'],
    (rows) => rows.length > 0 ? true : 'No FAITH heartbeat found'
  )

  await test(
    'status: equity_snapshots with "timestamp" column',
    `SELECT unrealized_pnl, open_positions, "timestamp" as snapshot_time
     FROM faith_equity_snapshots
     WHERE dte_mode = $1
     ORDER BY "timestamp" DESC LIMIT 1`,
    ['2DTE'],
    () => true  // OK even if empty
  )

  await test(
    'equity-curve: closed trades with dte_mode',
    `SELECT close_time, realized_pnl,
            SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl
     FROM faith_positions
     WHERE status IN ('closed', 'expired')
       AND realized_pnl IS NOT NULL AND close_time IS NOT NULL
       AND dte_mode = $1
     ORDER BY close_time`,
    ['2DTE'],
    (rows) => {
      if (rows.length === 0) return 'No closed trades found'
      const total = rows[rows.length - 1].cumulative_pnl
      console.log(`       → ${rows.length} trades, cumulative P&L = $${parseFloat(total).toFixed(2)}`)
      return true
    }
  )

  await test(
    'trades: closed positions (no sandbox_order_id)',
    `SELECT position_id, ticker, realized_pnl, close_reason, close_time,
            wings_adjusted
     FROM faith_positions
     WHERE status IN ('closed', 'expired') AND dte_mode = $1
     ORDER BY close_time DESC LIMIT 5`,
    ['2DTE'],
    (rows) => {
      if (rows.length === 0) return 'No trades found'
      rows.forEach(r => console.log(`       → ${r.position_id}: $${parseFloat(r.realized_pnl).toFixed(2)} (${r.close_reason})`))
      return true
    }
  )

  await test(
    'performance: aggregate stats with dte_mode',
    `SELECT COUNT(*) as total,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as total_pnl
     FROM faith_positions
     WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
       AND dte_mode = $1`,
    ['2DTE'],
    (rows) => {
      const r = rows[0]
      if (parseInt(r.total) === 0) return 'No trades for stats'
      const wr = (parseInt(r.wins) / parseInt(r.total) * 100).toFixed(1)
      console.log(`       → ${r.total} trades, ${wr}% WR, $${parseFloat(r.total_pnl).toFixed(2)} P&L`)
      return true
    }
  )

  await test(
    'logs: faith_logs with dte_mode',
    `SELECT log_time, level, message FROM faith_logs
     WHERE dte_mode = $1 ORDER BY log_time DESC LIMIT 3`,
    ['2DTE'],
    () => true
  )

  // ---------- SPARK (grace) ----------
  console.log('\nSPARK → grace_* tables (NO dte_mode):')

  await test(
    'status: paper_account WITHOUT dte_mode',
    `SELECT starting_capital, current_balance, cumulative_pnl, is_active
     FROM grace_paper_account
     WHERE is_active = TRUE
     ORDER BY id DESC LIMIT 1`,
    [],
    (rows) => rows.length > 0 ? true : 'warn'
  )

  await test(
    'status: position count WITHOUT dte_mode',
    `SELECT COUNT(*) as cnt FROM grace_positions WHERE status = 'open'`,
    [],
    () => true
  )

  await test(
    'status: heartbeat as GRACE',
    `SELECT scan_count, last_heartbeat, status FROM bot_heartbeats
     WHERE bot_name = $1`,
    ['GRACE'],
    (rows) => rows.length > 0 ? true : 'No GRACE heartbeat found'
  )

  await test(
    'status: equity_snapshots with "timestamp" column (no dte_mode)',
    `SELECT unrealized_pnl, open_positions, "timestamp" as snapshot_time
     FROM grace_equity_snapshots
     ORDER BY "timestamp" DESC LIMIT 1`,
    [],
    () => true
  )

  await test(
    'equity-curve: closed trades WITHOUT dte_mode',
    `SELECT close_time, realized_pnl,
            SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl
     FROM grace_positions
     WHERE status IN ('closed', 'expired')
       AND realized_pnl IS NOT NULL AND close_time IS NOT NULL
     ORDER BY close_time`,
    [],
    (rows) => {
      if (rows.length === 0) return 'No closed trades found'
      const total = rows[rows.length - 1].cumulative_pnl
      console.log(`       → ${rows.length} trades, cumulative P&L = $${parseFloat(total).toFixed(2)}`)
      return true
    }
  )

  await test(
    'trades: closed positions (no sandbox_order_id, no dte_mode)',
    `SELECT position_id, ticker, realized_pnl, close_reason, close_time,
            wings_adjusted
     FROM grace_positions
     WHERE status IN ('closed', 'expired')
     ORDER BY close_time DESC LIMIT 5`,
    [],
    (rows) => {
      if (rows.length === 0) return 'No trades found'
      rows.forEach(r => console.log(`       → ${r.position_id}: $${parseFloat(r.realized_pnl).toFixed(2)} (${r.close_reason})`))
      return true
    }
  )

  await test(
    'performance: aggregate stats WITHOUT dte_mode',
    `SELECT COUNT(*) as total,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as total_pnl
     FROM grace_positions
     WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL`,
    [],
    (rows) => {
      const r = rows[0]
      if (parseInt(r.total) === 0) return 'No trades for stats'
      const wr = (parseInt(r.wins) / parseInt(r.total) * 100).toFixed(1)
      console.log(`       → ${r.total} trades, ${wr}% WR, $${parseFloat(r.total_pnl).toFixed(2)} P&L`)
      return true
    }
  )

  await test(
    'logs: grace_logs WITHOUT dte_mode',
    `SELECT log_time, level, message FROM grace_logs
     ORDER BY log_time DESC LIMIT 3`,
    [],
    () => true
  )

  // ---------- Negative tests (old tables should be empty) ----------
  console.log('\nOld flame_*/spark_* tables (should be empty or missing):')

  await test(
    'flame_positions should have 0 trades',
    `SELECT COUNT(*) as cnt FROM flame_positions`,
    [],
    (rows) => {
      const cnt = parseInt(rows[0].cnt)
      if (cnt === 0) return true
      return `Has ${cnt} rows (unexpected — old table has data?)`
    }
  )

  await test(
    'spark_positions should have 0 trades',
    `SELECT COUNT(*) as cnt FROM spark_positions`,
    [],
    (rows) => {
      const cnt = parseInt(rows[0].cnt)
      if (cnt === 0) return true
      return `Has ${cnt} rows (unexpected — old table has data?)`
    }
  )

  // ---------- Summary ----------
  console.log(`\n=== Results: ${passed} passed, ${failed} failed, ${warnings} warnings ===`)
  if (failed > 0) {
    console.log('\n\x1b[31mSome queries will fail after deploy. Fix before merging.\x1b[0m')
    process.exit(1)
  } else {
    console.log('\n\x1b[32mAll queries pass. Safe to deploy.\x1b[0m')
  }

  await pool.end()
}

main().catch(err => {
  console.error('Fatal error:', err)
  process.exit(1)
})
