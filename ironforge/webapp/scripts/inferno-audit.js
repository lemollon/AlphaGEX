#!/usr/bin/env node
/**
 * INFERNO Full Audit Script
 * ==========================
 * Run on Render shell: cd ironforge/webapp && node scripts/inferno-audit.js
 *
 * Connects to PostgreSQL via DATABASE_URL and runs all 10 audit queries.
 * Outputs formatted results for each query with PASS/FAIL/INVESTIGATE verdicts.
 */

const { Pool } = require('pg')

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
})

const CT_TODAY = "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date"

async function query(sql) {
  const client = await pool.connect()
  try {
    const result = await client.query(sql)
    return result.rows
  } finally {
    client.release()
  }
}

function hr(title) {
  console.log('\n' + '='.repeat(70))
  console.log(`  ${title}`)
  console.log('='.repeat(70))
}

function table(rows, columns) {
  if (!rows || rows.length === 0) {
    console.log('  (no rows)')
    return
  }
  const cols = columns || Object.keys(rows[0])
  // Header
  const widths = cols.map(c => Math.max(c.length, ...rows.map(r => String(r[c] ?? 'NULL').length)))
  const header = cols.map((c, i) => c.padEnd(widths[i])).join(' | ')
  console.log('  ' + header)
  console.log('  ' + cols.map((_, i) => '-'.repeat(widths[i])).join('-+-'))
  for (const row of rows) {
    const line = cols.map((c, i) => String(row[c] ?? 'NULL').padEnd(widths[i])).join(' | ')
    console.log('  ' + line)
  }
}

async function run() {
  console.log('INFERNO FULL AUDIT — ' + new Date().toISOString())
  console.log('Database: ' + (process.env.DATABASE_URL ? 'connected' : 'MISSING DATABASE_URL'))

  // ── Q1: CONFIG STATE ──
  hr('Q1: INFERNO CONFIG STATE')
  try {
    const rows = await query(`SELECT * FROM inferno_config WHERE dte_mode = '0DTE'`)
    if (rows.length === 0) {
      console.log('  ❌ NO CONFIG ROW — INFERNO is using hardcoded defaults only!')
    } else {
      for (const row of rows) {
        for (const [k, v] of Object.entries(row)) {
          console.log(`  ${k}: ${v}`)
        }
      }
      const r = rows[0]
      // Validation
      const checks = [
        ['max_contracts', r.max_contracts, v => Number(v) <= 5, 'should be <= 5 (was 20 default)'],
        ['stop_loss_pct', r.stop_loss_pct, v => Number(v) <= 200, 'should be <= 200 (code default is 300)'],
        ['profit_target_pct', r.profit_target_pct, v => Number(v) >= 30 && Number(v) <= 50, 'expected 30-50'],
        ['max_trades_per_day', r.max_trades_per_day, v => Number(v) === 0, 'should be 0 (unlimited)'],
        ['buying_power_usage_pct', r.buying_power_usage_pct, v => Number(v) > 0 && Number(v) <= 1, 'expected 0-1 range'],
      ]
      console.log('\n  Validation:')
      for (const [name, val, check, msg] of checks) {
        const ok = val != null && check(val)
        console.log(`  ${ok ? '✅' : '⚠️ '} ${name} = ${val} ${ok ? '' : '— ' + msg}`)
      }
    }
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q2: PAPER ACCOUNT INTEGRITY ──
  hr('Q2: PAPER ACCOUNT INTEGRITY')
  try {
    const rows = await query(`
      SELECT
        id, current_balance, starting_capital, cumulative_pnl,
        buying_power, collateral_in_use, account_type, is_active, dte_mode, person,
        ROUND((current_balance - starting_capital - cumulative_pnl)::numeric, 2) as balance_drift,
        ROUND((current_balance - buying_power - collateral_in_use)::numeric, 2) as bp_drift
      FROM inferno_paper_account
      WHERE is_active = true
      ORDER BY id
    `)
    table(rows)
    for (const r of rows) {
      const bd = Number(r.balance_drift)
      const bpd = Number(r.bp_drift)
      if (Math.abs(bd) > 0.01) console.log(`  ❌ BALANCE DRIFT: $${bd} on account id=${r.id}`)
      if (Math.abs(bpd) > 0.01) console.log(`  ❌ BP DRIFT: $${bpd} on account id=${r.id}`)
    }
    if (rows.length === 0) console.log('  ❌ NO ACTIVE PAPER ACCOUNT')
    else if (rows.every(r => Math.abs(Number(r.balance_drift)) < 0.01 && Math.abs(Number(r.bp_drift)) < 0.01)) {
      console.log('  ✅ PASS — no drift detected')
    }
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q3: ALL TRADES (summary + recent 30) ──
  hr('Q3: ALL TRADES — SUMMARY')
  try {
    const summary = await query(`
      SELECT
        COUNT(*) as total_trades,
        COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed,
        COUNT(CASE WHEN status = 'open' THEN 1 END) as open,
        MIN(open_time AT TIME ZONE 'America/Chicago') as first_trade,
        MAX(open_time AT TIME ZONE 'America/Chicago') as last_trade
      FROM inferno_positions
    `)
    table(summary)

    console.log('\n  Last 30 closed trades:')
    const recent = await query(`
      SELECT
        position_id,
        to_char(open_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as open_ct,
        to_char(close_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as close_ct,
        contracts,
        ROUND(total_credit::numeric, 4) as credit,
        ROUND(close_price::numeric, 4) as close_px,
        close_reason,
        ROUND(realized_pnl::numeric, 2) as pnl,
        ROUND(EXTRACT(EPOCH FROM (close_time - open_time))/60) as hold_min,
        ROUND(vix_at_entry::numeric, 1) as vix,
        ROUND(oracle_win_probability::numeric, 2) as wp
      FROM inferno_positions
      WHERE status = 'closed'
      ORDER BY close_time DESC
      LIMIT 30
    `)
    table(recent)

    // Check for 10x bug (contracts > 3)
    const oversized = await query(`
      SELECT position_id, contracts, collateral_required,
        to_char(open_time AT TIME ZONE 'America/Chicago', 'YYYY-MM-DD HH24:MI') as open_ct
      FROM inferno_positions WHERE contracts > 3 ORDER BY contracts DESC LIMIT 10
    `)
    if (oversized.length > 0) {
      console.log(`\n  ⚠️  ${oversized.length} OVERSIZED TRADES (contracts > 3):`)
      table(oversized)
    } else {
      console.log('\n  ✅ No oversized trades (all <= 3 contracts)')
    }

    // Check entry window violations
    const windowViolations = await query(`
      SELECT position_id, contracts,
        to_char(open_time AT TIME ZONE 'America/Chicago', 'YYYY-MM-DD HH24:MI') as open_ct,
        EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') * 100 +
        EXTRACT(MINUTE FROM open_time AT TIME ZONE 'America/Chicago') as hhmm
      FROM inferno_positions
      WHERE EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') * 100 +
            EXTRACT(MINUTE FROM open_time AT TIME ZONE 'America/Chicago') > 1430
         OR EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') * 100 +
            EXTRACT(MINUTE FROM open_time AT TIME ZONE 'America/Chicago') < 830
      ORDER BY open_time DESC LIMIT 10
    `)
    if (windowViolations.length > 0) {
      console.log(`\n  ⚠️  ${windowViolations.length} ENTRY WINDOW VIOLATIONS (outside 8:30-14:30):`)
      table(windowViolations)
    } else {
      console.log('  ✅ All trades within entry window')
    }
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q4: LOSS BREAKDOWN BY CLOSE REASON ──
  hr('Q4: LOSS BREAKDOWN BY CLOSE REASON')
  try {
    const rows = await query(`
      SELECT
        close_reason,
        COUNT(*) as trades,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(MIN(realized_pnl)::numeric, 2) as worst,
        ROUND(MAX(realized_pnl)::numeric, 2) as best,
        COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
        COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) as losses,
        ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct
      FROM inferno_positions
      WHERE status = 'closed'
      GROUP BY close_reason
      ORDER BY total_pnl ASC
    `)
    table(rows)
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q5: P&L BY VIX REGIME ──
  hr('Q5: P&L BY VIX REGIME')
  try {
    const rows = await query(`
      SELECT
        CASE
          WHEN vix_at_entry < 15 THEN '1_LOW(<15)'
          WHEN vix_at_entry < 20 THEN '2_NORMAL(15-20)'
          WHEN vix_at_entry < 25 THEN '3_ELEVATED(20-25)'
          WHEN vix_at_entry < 35 THEN '4_HIGH(25-35)'
          ELSE '5_EXTREME(35+)'
        END as vix_bucket,
        COUNT(*) as trades,
        ROUND(AVG(vix_at_entry)::numeric, 1) as avg_vix,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct
      FROM inferno_positions WHERE status = 'closed'
      GROUP BY vix_bucket ORDER BY vix_bucket
    `)
    table(rows)
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q6: P&L BY HOUR OF DAY ──
  hr('Q6: P&L BY HOUR OPENED (CT)')
  try {
    const rows = await query(`
      SELECT
        EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') as hour_ct,
        COUNT(*) as trades,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct
      FROM inferno_positions WHERE status = 'closed'
      GROUP BY hour_ct ORDER BY hour_ct
    `)
    table(rows)
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q7: P&L BY DAY OF WEEK ──
  hr('Q7: P&L BY DAY OF WEEK')
  try {
    const rows = await query(`
      SELECT
        TO_CHAR(open_time AT TIME ZONE 'America/Chicago', 'Day') as day,
        EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') as dow,
        COUNT(*) as trades,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct
      FROM inferno_positions WHERE status = 'closed'
      GROUP BY day, dow ORDER BY dow
    `)
    table(rows)
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q8: ORACLE SIGNAL QUALITY ──
  hr('Q8: ORACLE SIGNAL QUALITY (WP vs actual win rate)')
  try {
    const rows = await query(`
      SELECT
        ROUND(oracle_win_probability::numeric, 2) as wp,
        COUNT(*) as trades,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as actual_wr
      FROM inferno_positions
      WHERE status = 'closed' AND oracle_win_probability IS NOT NULL
      GROUP BY wp ORDER BY wp
    `)
    table(rows)
    if (rows.length > 0) {
      // Check if higher WP correlates with higher win rate
      const sorted = rows.filter(r => Number(r.trades) >= 5).sort((a, b) => Number(a.wp) - Number(b.wp))
      if (sorted.length >= 2) {
        const low = sorted[0]
        const high = sorted[sorted.length - 1]
        const lowWr = Number(low.actual_wr)
        const highWr = Number(high.actual_wr)
        if (highWr > lowWr + 5) {
          console.log(`  ✅ Oracle has predictive value: WP=${low.wp} → ${lowWr}% vs WP=${high.wp} → ${highWr}%`)
        } else {
          console.log(`  ⚠️  Oracle may lack predictive value: WP=${low.wp} → ${lowWr}% vs WP=${high.wp} → ${highWr}%`)
        }
      }
    }
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q9: SIZING VALIDATION ──
  hr('Q9: SIZING VALIDATION (top 20 by contracts)')
  try {
    const rows = await query(`
      SELECT
        position_id,
        contracts,
        ROUND(collateral_required::numeric, 2) as collateral,
        spread_width,
        ROUND(total_credit::numeric, 4) as credit,
        ROUND(((spread_width * 100 - total_credit * 100) * contracts)::numeric, 2) as expected_coll,
        ROUND((collateral_required - ((spread_width * 100 - total_credit * 100) * contracts))::numeric, 2) as diff
      FROM inferno_positions
      ORDER BY contracts DESC
      LIMIT 20
    `)
    table(rows)
    const badColl = rows.filter(r => Math.abs(Number(r.diff)) > 1)
    if (badColl.length > 0) {
      console.log(`  ⚠️  ${badColl.length} positions with collateral mismatch > $1`)
    } else {
      console.log('  ✅ All collateral calculations correct')
    }
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── Q10: ORPHAN POSITION CHECK ──
  hr('Q10: ORPHAN POSITION CHECK')
  try {
    const openRows = await query(`
      SELECT
        position_id, status, contracts,
        ROUND(collateral_required::numeric, 2) as collateral,
        to_char(open_time AT TIME ZONE 'America/Chicago', 'YYYY-MM-DD HH24:MI') as open_ct,
        CASE WHEN (open_time AT TIME ZONE 'America/Chicago')::date < ${CT_TODAY}
             THEN 'ORPHAN' ELSE 'OK' END as status_check
      FROM inferno_positions WHERE status = 'open'
    `)
    if (openRows.length === 0) {
      console.log('  ✅ No open positions')
    } else {
      table(openRows)
      const orphans = openRows.filter(r => r.status_check === 'ORPHAN')
      if (orphans.length > 0) {
        console.log(`  ❌ ${orphans.length} ORPHAN POSITIONS from prior days!`)
      }
    }

    // Cross-check collateral
    const collCheck = await query(`
      SELECT
        COALESCE(SUM(collateral_required), 0) as open_collateral
      FROM inferno_positions WHERE status = 'open'
    `)
    const acctCheck = await query(`
      SELECT collateral_in_use
      FROM inferno_paper_account
      WHERE is_active = true AND COALESCE(account_type, 'sandbox') = 'sandbox'
      LIMIT 1
    `)
    const openColl = Number(collCheck[0]?.open_collateral || 0)
    const acctColl = Number(acctCheck[0]?.collateral_in_use || 0)
    const collDiff = Math.abs(openColl - acctColl)
    console.log(`\n  Open position collateral: $${openColl.toFixed(2)}`)
    console.log(`  Paper account collateral_in_use: $${acctColl.toFixed(2)}`)
    if (collDiff > 0.01) {
      console.log(`  ❌ COLLATERAL MISMATCH: $${collDiff.toFixed(2)}`)
    } else {
      console.log('  ✅ Collateral matches')
    }
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  // ── SUMMARY: OVERALL PERFORMANCE ──
  hr('SUMMARY: OVERALL PERFORMANCE')
  try {
    const perf = await query(`
      SELECT
        COUNT(*) as total_trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
        ROUND(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END)::numeric, 2) as avg_loss,
        ROUND(MAX(realized_pnl)::numeric, 2) as best,
        ROUND(MIN(realized_pnl)::numeric, 2) as worst,
        ROUND(
          (SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 1
        ) as win_rate_pct
      FROM inferno_positions
      WHERE status = 'closed'
    `)
    const r = perf[0]
    console.log(`  Total trades:  ${r.total_trades}`)
    console.log(`  Win rate:      ${r.win_rate_pct}% (${r.wins}W / ${r.losses}L)`)
    console.log(`  Total P&L:     $${r.total_pnl}`)
    console.log(`  Avg P&L/trade: $${r.avg_pnl}`)
    console.log(`  Avg winner:    $${r.avg_win}`)
    console.log(`  Avg loser:     $${r.avg_loss}`)
    console.log(`  Best trade:    $${r.best}`)
    console.log(`  Worst trade:   $${r.worst}`)

    // Expected value
    const wr = Number(r.win_rate_pct) / 100
    const avgWin = Number(r.avg_win)
    const avgLoss = Math.abs(Number(r.avg_loss))
    const ev = (wr * avgWin) - ((1 - wr) * avgLoss)
    console.log(`  Expected Value: $${ev.toFixed(2)}/trade ${ev > 0 ? '✅ POSITIVE' : '❌ NEGATIVE'}`)

    // Profit factor
    const pfRows = await query(`
      SELECT
        COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 0) as gross_wins,
        ABS(COALESCE(SUM(CASE WHEN realized_pnl < 0 THEN realized_pnl END), 0)) as gross_losses
      FROM inferno_positions WHERE status = 'closed'
    `)
    const gw = Number(pfRows[0].gross_wins)
    const gl = Number(pfRows[0].gross_losses)
    const pf = gl > 0 ? (gw / gl).toFixed(2) : 'INF'
    console.log(`  Profit factor: ${pf} (gross wins $${gw.toFixed(2)} / gross losses $${gl.toFixed(2)})`)

    // Account state
    const acct = await query(`
      SELECT current_balance, starting_capital, cumulative_pnl, buying_power, collateral_in_use
      FROM inferno_paper_account
      WHERE is_active = true AND COALESCE(account_type, 'sandbox') = 'sandbox'
      LIMIT 1
    `)
    if (acct[0]) {
      const a = acct[0]
      console.log(`\n  Account State:`)
      console.log(`    Balance:     $${Number(a.current_balance).toFixed(2)}`)
      console.log(`    Starting:    $${Number(a.starting_capital).toFixed(2)}`)
      console.log(`    Cum P&L:     $${Number(a.cumulative_pnl).toFixed(2)}`)
      console.log(`    Buying Power: $${Number(a.buying_power).toFixed(2)}`)
      console.log(`    Collateral:  $${Number(a.collateral_in_use).toFixed(2)}`)
    }
  } catch (e) {
    console.log(`  ERROR: ${e.message}`)
  }

  console.log('\n' + '='.repeat(70))
  console.log('  AUDIT COMPLETE — ' + new Date().toISOString())
  console.log('='.repeat(70))

  await pool.end()
}

run().catch(e => {
  console.error('Fatal error:', e.message)
  process.exit(1)
})
