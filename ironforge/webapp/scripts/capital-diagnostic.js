#!/usr/bin/env node
/**
 * IronForge Capital & Sizing Diagnostic
 * =======================================
 * Run BEFORE making any code changes. Shows the full picture:
 * - Where starting_capital comes from
 * - How it flows into paper_account balance
 * - How balance feeds into position sizing
 * - Whether the equity curve and trade history are consistent
 *
 * Run on Render shell:
 *   node scripts/capital-diagnostic.js 2>&1 | tee /tmp/capital-diag.txt
 */

const { Pool } = require('pg')

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
})

async function q(sql) {
  const client = await pool.connect()
  try { return (await client.query(sql)).rows }
  finally { client.release() }
}

function num(v) { const n = Number(v); return isNaN(n) ? 0 : n }

function hr(t) { console.log('\n' + '='.repeat(72)); console.log('  ' + t); console.log('='.repeat(72)) }
function sub(t) { console.log(`\n  --- ${t} ---`) }

function tbl(rows) {
  if (!rows?.length) { console.log('  (no rows)'); return }
  const cols = Object.keys(rows[0])
  const w = cols.map(c => Math.max(c.length, ...rows.map(r => String(r[c] ?? 'NULL').length)))
  console.log('  ' + cols.map((c, i) => c.padEnd(w[i])).join(' | '))
  console.log('  ' + cols.map((_, i) => '-'.repeat(w[i])).join('-+-'))
  for (const row of rows) console.log('  ' + cols.map((c, i) => String(row[c] ?? 'NULL').padEnd(w[i])).join(' | '))
}

const BOTS = [
  { name: 'inferno', dte: '0DTE' },
  { name: 'spark',   dte: '1DTE' },
  { name: 'flame',   dte: '2DTE' },
]

async function run() {
  console.log('IRONFORGE CAPITAL & SIZING DIAGNOSTIC — ' + new Date().toISOString())

  for (const bot of BOTS) {
    hr(`${bot.name.toUpperCase()} (${bot.dte})`)

    // 1. Config starting_capital
    sub('1. Config Table (source of truth for starting_capital)')
    try {
      const cfg = await q(`SELECT starting_capital, max_contracts, buying_power_usage_pct, stop_loss_pct, profit_target_pct, min_credit
        FROM ${bot.name}_config WHERE dte_mode = '${bot.dte}' LIMIT 1`)
      tbl(cfg)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 2. Paper account state
    sub('2. Paper Account (all rows, active and inactive)')
    try {
      const accts = await q(`SELECT id, starting_capital, current_balance, cumulative_pnl,
        buying_power, collateral_in_use, total_trades, account_type, person, is_active,
        ROUND((current_balance - starting_capital - cumulative_pnl)::numeric, 2) as balance_drift,
        ROUND((current_balance - buying_power - collateral_in_use)::numeric, 2) as bp_drift
        FROM ${bot.name}_paper_account ORDER BY id`)
      tbl(accts)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 3. Verify: sum of all closed trade P&L = cumulative_pnl
    sub('3. P&L Reconciliation (closed trades sum vs paper_account.cumulative_pnl)')
    try {
      const tradePnl = await q(`SELECT
        COUNT(*) as closed_trades,
        ROUND(COALESCE(SUM(realized_pnl), 0)::numeric, 2) as sum_realized_pnl
        FROM ${bot.name}_positions WHERE status = 'closed' AND COALESCE(account_type, 'sandbox') = 'sandbox'`)
      const acctPnl = await q(`SELECT cumulative_pnl
        FROM ${bot.name}_paper_account WHERE is_active = true AND COALESCE(account_type, 'sandbox') = 'sandbox' LIMIT 1`)
      const sumPnl = num(tradePnl[0]?.sum_realized_pnl)
      const cumPnl = num(acctPnl[0]?.cumulative_pnl)
      const drift = Math.abs(sumPnl - cumPnl)
      console.log(`  Closed trades sum(realized_pnl): $${sumPnl.toFixed(2)}`)
      console.log(`  Paper account cumulative_pnl:    $${cumPnl.toFixed(2)}`)
      console.log(`  Drift: $${drift.toFixed(2)} ${drift < 0.01 ? '(MATCH)' : '*** MISMATCH ***'}`)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 4. Starting capital history — did it change over time?
    sub('4. Starting Capital History (from equity snapshots)')
    try {
      const snaps = await q(`SELECT
        (snapshot_time AT TIME ZONE 'America/Chicago')::date as day,
        MIN(starting_capital) as min_cap,
        MAX(starting_capital) as max_cap,
        COUNT(*) as snapshots
        FROM ${bot.name}_equity_snapshots
        WHERE COALESCE(account_type, 'sandbox') = 'sandbox'
        GROUP BY day ORDER BY day`)
      if (snaps.length > 0) {
        tbl(snaps)
        const caps = snaps.map(s => num(s.max_cap))
        const minCap = Math.min(...caps)
        const maxCap = Math.max(...caps)
        if (maxCap - minCap > 1) {
          console.log(`  *** CAPITAL CHANGED: ranged from $${minCap.toFixed(0)} to $${maxCap.toFixed(0)}`)
        }
      }
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 5. Trade sizing analysis — contracts vs account size at time of trade
    sub('5. Sizing Analysis (contracts × collateral vs balance at time)')
    try {
      const trades = await q(`SELECT
        p.position_id,
        p.contracts,
        ROUND(p.collateral_required::numeric, 0) as collateral,
        ROUND(p.total_credit::numeric, 4) as credit,
        ROUND(p.realized_pnl::numeric, 2) as pnl,
        to_char(p.open_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as opened,
        p.close_reason
        FROM ${bot.name}_positions p
        WHERE p.status = 'closed' AND COALESCE(p.account_type, 'sandbox') = 'sandbox'
        ORDER BY p.open_time DESC LIMIT 20`)
      tbl(trades)

      // Summary: contract distribution
      const dist = await q(`SELECT
        contracts, COUNT(*) as trades,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl
        FROM ${bot.name}_positions
        WHERE status = 'closed' AND COALESCE(account_type, 'sandbox') = 'sandbox'
        GROUP BY contracts ORDER BY contracts`)
      console.log('\n  Contract size distribution:')
      tbl(dist)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 6. What % of balance was each trade?
    sub('6. Position Size as % of Balance (collateral / paper_account balance)')
    try {
      const acct = await q(`SELECT current_balance, starting_capital
        FROM ${bot.name}_paper_account WHERE is_active = true AND COALESCE(account_type, 'sandbox') = 'sandbox' LIMIT 1`)
      const bal = num(acct[0]?.current_balance)
      const start = num(acct[0]?.starting_capital)

      if (bal > 0) {
        const pctTrades = await q(`SELECT
          position_id, contracts,
          ROUND(collateral_required::numeric, 0) as collateral,
          ROUND((collateral_required / ${bal} * 100)::numeric, 1) as pct_of_current_bal,
          ROUND((collateral_required / ${start} * 100)::numeric, 1) as pct_of_starting_cap,
          to_char(open_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as opened
          FROM ${bot.name}_positions
          WHERE COALESCE(account_type, 'sandbox') = 'sandbox'
          ORDER BY collateral_required DESC LIMIT 10`)
        console.log(`  Current balance: $${bal.toFixed(2)}, Starting capital: $${start.toFixed(2)}`)
        tbl(pctTrades)
      }
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 7. Equity curve endpoints — first and last snapshots
    sub('7. Equity Curve Range')
    try {
      const first = await q(`SELECT
        snapshot_time AT TIME ZONE 'America/Chicago' as time,
        equity, starting_capital, cumulative_pnl, unrealized_pnl
        FROM ${bot.name}_equity_snapshots
        WHERE COALESCE(account_type, 'sandbox') = 'sandbox'
        ORDER BY snapshot_time ASC LIMIT 1`)
      const last = await q(`SELECT
        snapshot_time AT TIME ZONE 'America/Chicago' as time,
        equity, starting_capital, cumulative_pnl, unrealized_pnl
        FROM ${bot.name}_equity_snapshots
        WHERE COALESCE(account_type, 'sandbox') = 'sandbox'
        ORDER BY snapshot_time DESC LIMIT 1`)
      console.log('  First snapshot:')
      tbl(first)
      console.log('  Latest snapshot:')
      tbl(last)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 8. Daily P&L from daily_perf table
    sub('8. Daily Performance')
    try {
      const daily = await q(`SELECT
        trade_date, trades_executed, positions_closed,
        ROUND(realized_pnl::numeric, 2) as pnl
        FROM ${bot.name}_daily_perf
        WHERE COALESCE(person, '') != 'Logan'
        ORDER BY trade_date DESC LIMIT 15`)
      tbl(daily)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 9. Kelly inputs from actual data (what Kelly WOULD compute)
    sub('9. Kelly Inputs (from ALL closed trades)')
    try {
      const kelly = await q(`SELECT
        COUNT(*) as total_trades,
        COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
        COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) as losses,
        ROUND((COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 1) as win_rate,
        ROUND(AVG(CASE WHEN realized_pnl > 0 AND contracts > 0 THEN realized_pnl / contracts END)::numeric, 2) as avg_win_per_contract,
        ROUND(AVG(CASE WHEN realized_pnl < 0 AND contracts > 0 THEN ABS(realized_pnl) / contracts END)::numeric, 2) as avg_loss_per_contract,
        ROUND(AVG(total_credit)::numeric, 4) as avg_credit,
        ROUND(AVG(spread_width)::numeric, 2) as avg_spread,
        ROUND(AVG(CASE WHEN total_credit > 0 AND spread_width > 0
          THEN total_credit / (spread_width - total_credit) END)::numeric, 4) as avg_rr_ratio
        FROM ${bot.name}_positions
        WHERE status = 'closed' AND COALESCE(account_type, 'sandbox') = 'sandbox'`)
      tbl(kelly)

      const r = kelly[0]
      if (r && num(r.total_trades) > 0) {
        const wr = num(r.win_rate) / 100
        const avgRR = num(r.avg_rr_ratio)
        const avgCredit = num(r.avg_credit)
        const avgSpread = num(r.avg_spread)

        if (avgRR > 0) {
          const kellyRaw = wr - ((1 - wr) / avgRR)
          const kellyHalf = kellyRaw * 0.5
          console.log(`\n  Per-trade Kelly (using avg RR=${avgRR.toFixed(4)}, WR=${(wr*100).toFixed(1)}%):`)
          console.log(`    Raw Kelly: ${(kellyRaw * 100).toFixed(2)}%`)
          console.log(`    Half Kelly: ${(kellyHalf * 100).toFixed(2)}%`)
          console.log(`    Kelly says: ${kellyRaw > 0 ? 'POSITIVE EDGE' : '*** NEGATIVE EDGE — SHOULD NOT TRADE AT THIS R/R ***'}`)
        }
        console.log(`\n  Avg credit: $${avgCredit.toFixed(4)} on $${avgSpread.toFixed(0)} spread`)
        console.log(`  Avg R/R: ${avgRR.toFixed(4)} (1:${avgRR > 0 ? Math.round(1/avgRR) : 'INF'})`)
        console.log(`  Min credit for RR>=0.05: $${(0.05 * avgSpread / (1 + 0.05)).toFixed(2)}`)
      }
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // 10. Credit distribution — how many trades would be blocked by min_credit / min_rr
    sub('10. Credit Distribution (would R/R gate block trades?)')
    try {
      const dist = await q(`SELECT
        CASE
          WHEN total_credit < 0.05 THEN 'a_under_0.05'
          WHEN total_credit < 0.10 THEN 'b_0.05-0.10'
          WHEN total_credit < 0.15 THEN 'c_0.10-0.15'
          WHEN total_credit < 0.25 THEN 'd_0.15-0.25'
          WHEN total_credit < 0.50 THEN 'e_0.25-0.50'
          ELSE 'f_0.50+'
        END as credit_bucket,
        COUNT(*) as trades,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct
        FROM ${bot.name}_positions
        WHERE status = 'closed' AND COALESCE(account_type, 'sandbox') = 'sandbox'
        GROUP BY credit_bucket ORDER BY credit_bucket`)
      tbl(dist)
      console.log('\n  If R/R gate blocks credit < $0.25 (RR < 0.05 on $5 spread):')
      const blocked = dist.filter(r => ['a_under_0.05', 'b_0.05-0.10', 'c_0.10-0.15', 'd_0.15-0.25'].includes(r.credit_bucket))
      const blockedTrades = blocked.reduce((s, r) => s + num(r.trades), 0)
      const blockedPnl = blocked.reduce((s, r) => s + num(r.total_pnl), 0)
      const totalTrades = dist.reduce((s, r) => s + num(r.trades), 0)
      console.log(`  Would block: ${blockedTrades}/${totalTrades} trades (${(blockedTrades/totalTrades*100).toFixed(0)}%), P&L of blocked: $${blockedPnl.toFixed(2)}`)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }
  }

  console.log('\n' + '='.repeat(72))
  console.log('  DIAGNOSTIC COMPLETE — ' + new Date().toISOString())
  console.log('  Paste this output before making any code changes.')
  console.log('='.repeat(72))

  await pool.end()
}

run().catch(e => { console.error('Fatal:', e.message); process.exit(1) })
