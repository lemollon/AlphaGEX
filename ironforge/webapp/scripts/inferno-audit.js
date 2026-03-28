#!/usr/bin/env node
/**
 * IronForge Full Audit Script — FLAME, SPARK, INFERNO
 * =====================================================
 * Run on Render shell:
 *   cd ironforge/webapp && node scripts/inferno-audit.js
 *   cd ironforge/webapp && node scripts/inferno-audit.js 2>&1 | tee /tmp/audit.txt
 *
 * Runs all audit queries for ALL THREE bots + Kelly criterion diagnostics.
 */

const { Pool } = require('pg')

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
})

const CT_TODAY = "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date"

const BOTS = [
  { name: 'inferno', dte: '0DTE', label: 'INFERNO', kelly: true },
  { name: 'spark',   dte: '1DTE', label: 'SPARK',   kelly: true },
  { name: 'flame',   dte: '2DTE', label: 'FLAME',   kelly: false },
]

async function q(sql) {
  const client = await pool.connect()
  try {
    return (await client.query(sql)).rows
  } finally {
    client.release()
  }
}

function hr(title) {
  console.log('\n' + '='.repeat(72))
  console.log(`  ${title}`)
  console.log('='.repeat(72))
}

function subhr(title) {
  console.log(`\n  --- ${title} ---`)
}

function tbl(rows, columns) {
  if (!rows || rows.length === 0) { console.log('  (no rows)'); return }
  const cols = columns || Object.keys(rows[0])
  const widths = cols.map(c => Math.max(c.length, ...rows.map(r => String(r[c] ?? 'NULL').length)))
  console.log('  ' + cols.map((c, i) => c.padEnd(widths[i])).join(' | '))
  console.log('  ' + cols.map((_, i) => '-'.repeat(widths[i])).join('-+-'))
  for (const row of rows) {
    console.log('  ' + cols.map((c, i) => String(row[c] ?? 'NULL').padEnd(widths[i])).join(' | '))
  }
}

function num(v) { const n = Number(v); return isNaN(n) ? 0 : n }

async function run() {
  console.log('IRONFORGE FULL AUDIT — ' + new Date().toISOString())
  console.log('Database: ' + (process.env.DATABASE_URL ? 'connected' : '*** MISSING DATABASE_URL ***'))
  if (!process.env.DATABASE_URL) { console.error('Set DATABASE_URL and retry.'); process.exit(1) }

  for (const bot of BOTS) {
    hr(`${bot.label} (${bot.dte}) — FULL AUDIT`)

    // ── Q1: CONFIG ──
    subhr('Q1: Config')
    try {
      const rows = await q(`SELECT * FROM ${bot.name}_config WHERE dte_mode = '${bot.dte}'`)
      if (rows.length === 0) {
        console.log(`  (no config row — using hardcoded defaults)`)
      } else {
        for (const [k, v] of Object.entries(rows[0])) console.log(`  ${k}: ${v}`)
      }
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q2: PAPER ACCOUNT ──
    subhr('Q2: Paper Account Integrity')
    try {
      const rows = await q(`
        SELECT
          id, current_balance, starting_capital, cumulative_pnl,
          buying_power, collateral_in_use, account_type, person,
          ROUND((current_balance - starting_capital - cumulative_pnl)::numeric, 2) as balance_drift,
          ROUND((current_balance - buying_power - collateral_in_use)::numeric, 2) as bp_drift
        FROM ${bot.name}_paper_account
        WHERE is_active = true ORDER BY id`)
      tbl(rows)
      for (const r of rows) {
        if (Math.abs(num(r.balance_drift)) > 0.01) console.log(`  *** BALANCE DRIFT: $${r.balance_drift} id=${r.id}`)
        if (Math.abs(num(r.bp_drift)) > 0.01) console.log(`  *** BP DRIFT: $${r.bp_drift} id=${r.id}`)
      }
      if (rows.length > 0 && rows.every(r => Math.abs(num(r.balance_drift)) < 0.01 && Math.abs(num(r.bp_drift)) < 0.01))
        console.log('  PASS — no drift')
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q3: TRADE SUMMARY + RECENT ──
    subhr('Q3: Trade Summary')
    try {
      const summary = await q(`
        SELECT COUNT(*) as total,
          COUNT(CASE WHEN status='closed' THEN 1 END) as closed,
          COUNT(CASE WHEN status='open' THEN 1 END) as open,
          to_char(MIN(open_time AT TIME ZONE 'America/Chicago'), 'YYYY-MM-DD HH24:MI') as first_trade,
          to_char(MAX(open_time AT TIME ZONE 'America/Chicago'), 'YYYY-MM-DD HH24:MI') as last_trade
        FROM ${bot.name}_positions`)
      tbl(summary)

      console.log('\n  Last 20 closed:')
      const recent = await q(`
        SELECT position_id,
          to_char(open_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as open_ct,
          to_char(close_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as close_ct,
          contracts, ROUND(total_credit::numeric, 4) as credit,
          ROUND(close_price::numeric, 4) as close_px, close_reason,
          ROUND(realized_pnl::numeric, 2) as pnl,
          ROUND(EXTRACT(EPOCH FROM (close_time - open_time))/60) as hold_min,
          ROUND(vix_at_entry::numeric, 1) as vix,
          ROUND(oracle_win_probability::numeric, 2) as wp
        FROM ${bot.name}_positions WHERE status = 'closed'
        ORDER BY close_time DESC LIMIT 20`)
      tbl(recent)

      // Oversized trades
      const big = await q(`
        SELECT position_id, contracts, ROUND(collateral_required::numeric, 0) as coll,
          to_char(open_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as open_ct
        FROM ${bot.name}_positions WHERE contracts > 5 ORDER BY contracts DESC LIMIT 10`)
      if (big.length > 0) { console.log(`\n  WARNING: ${big.length} trades with contracts > 5:`); tbl(big) }

      // Entry window violations
      const windowV = await q(`
        SELECT position_id,
          to_char(open_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as open_ct,
          EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') * 100 +
          EXTRACT(MINUTE FROM open_time AT TIME ZONE 'America/Chicago') as hhmm
        FROM ${bot.name}_positions
        WHERE EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') * 100 +
              EXTRACT(MINUTE FROM open_time AT TIME ZONE 'America/Chicago') > 1430
           OR EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') * 100 +
              EXTRACT(MINUTE FROM open_time AT TIME ZONE 'America/Chicago') < 830
        LIMIT 10`)
      if (windowV.length > 0) { console.log(`\n  WARNING: ${windowV.length} entry window violations:`); tbl(windowV) }
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q4: LOSS BREAKDOWN ──
    subhr('Q4: P&L by Close Reason')
    try {
      const rows = await q(`
        SELECT close_reason, COUNT(*) as trades,
          ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
          ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
          ROUND(MIN(realized_pnl)::numeric, 2) as worst,
          ROUND(MAX(realized_pnl)::numeric, 2) as best,
          COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
          COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) as losses,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)*100.0/NULLIF(COUNT(*),0), 1) as win_pct
        FROM ${bot.name}_positions WHERE status = 'closed'
        GROUP BY close_reason ORDER BY total_pnl ASC`)
      tbl(rows)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q5: VIX REGIME ──
    subhr('Q5: P&L by VIX Regime')
    try {
      const rows = await q(`
        SELECT CASE
            WHEN vix_at_entry < 15 THEN '1_LOW(<15)'
            WHEN vix_at_entry < 20 THEN '2_NORM(15-20)'
            WHEN vix_at_entry < 25 THEN '3_ELEV(20-25)'
            WHEN vix_at_entry < 35 THEN '4_HIGH(25-35)'
            ELSE '5_EXTREME(35+)' END as vix,
          COUNT(*) as trades, ROUND(AVG(vix_at_entry)::numeric, 1) as avg_vix,
          ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
          ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)*100.0/NULLIF(COUNT(*),0), 1) as win_pct
        FROM ${bot.name}_positions WHERE status = 'closed'
        GROUP BY vix ORDER BY vix`)
      tbl(rows)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q6: HOUR OF DAY ──
    subhr('Q6: P&L by Hour Opened (CT)')
    try {
      const rows = await q(`
        SELECT EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') as hour_ct,
          COUNT(*) as trades, ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
          ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)*100.0/NULLIF(COUNT(*),0), 1) as win_pct
        FROM ${bot.name}_positions WHERE status = 'closed'
        GROUP BY hour_ct ORDER BY hour_ct`)
      tbl(rows)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q7: DAY OF WEEK ──
    subhr('Q7: P&L by Day of Week')
    try {
      const rows = await q(`
        SELECT TRIM(TO_CHAR(open_time AT TIME ZONE 'America/Chicago', 'Day')) as day,
          EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') as dow,
          COUNT(*) as trades, ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
          ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)*100.0/NULLIF(COUNT(*),0), 1) as win_pct
        FROM ${bot.name}_positions WHERE status = 'closed'
        GROUP BY day, dow ORDER BY dow`)
      tbl(rows)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q8: ORACLE SIGNAL QUALITY ──
    subhr('Q8: Oracle Signal Quality (WP vs actual win rate)')
    try {
      const rows = await q(`
        SELECT ROUND(oracle_win_probability::numeric, 2) as wp,
          COUNT(*) as trades, ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
          ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)*100.0/NULLIF(COUNT(*),0), 1) as actual_wr
        FROM ${bot.name}_positions
        WHERE status = 'closed' AND oracle_win_probability IS NOT NULL
        GROUP BY wp ORDER BY wp`)
      tbl(rows)
      const sig = rows.filter(r => num(r.trades) >= 5).sort((a, b) => num(a.wp) - num(b.wp))
      if (sig.length >= 2) {
        const lo = sig[0], hi = sig[sig.length - 1]
        const diff = num(hi.actual_wr) - num(lo.actual_wr)
        console.log(`  Oracle spread: WP=${lo.wp} -> ${lo.actual_wr}% vs WP=${hi.wp} -> ${hi.actual_wr}% (${diff > 5 ? 'predictive' : 'WEAK'})`)
      }
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q9: SIZING VALIDATION ──
    subhr('Q9: Sizing Validation (top 15 by contracts)')
    try {
      const rows = await q(`
        SELECT position_id, contracts,
          ROUND(collateral_required::numeric, 2) as collateral, spread_width,
          ROUND(total_credit::numeric, 4) as credit,
          ROUND(((spread_width*100 - total_credit*100)*contracts)::numeric, 2) as expected_coll,
          ROUND((collateral_required - ((spread_width*100 - total_credit*100)*contracts))::numeric, 2) as diff
        FROM ${bot.name}_positions ORDER BY contracts DESC LIMIT 15`)
      tbl(rows)
      const bad = rows.filter(r => Math.abs(num(r.diff)) > 1)
      if (bad.length > 0) console.log(`  WARNING: ${bad.length} positions with collateral mismatch > $1`)
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── Q10: ORPHAN CHECK ──
    subhr('Q10: Orphan Positions')
    try {
      const openR = await q(`
        SELECT position_id, contracts, ROUND(collateral_required::numeric, 2) as coll,
          to_char(open_time AT TIME ZONE 'America/Chicago', 'YYYY-MM-DD HH24:MI') as open_ct,
          CASE WHEN (open_time AT TIME ZONE 'America/Chicago')::date < ${CT_TODAY}
               THEN 'ORPHAN' ELSE 'OK' END as check
        FROM ${bot.name}_positions WHERE status = 'open'`)
      if (openR.length === 0) { console.log('  No open positions') }
      else {
        tbl(openR)
        const orphans = openR.filter(r => r.check === 'ORPHAN')
        if (orphans.length > 0) console.log(`  *** ${orphans.length} ORPHAN(S) from prior days!`)
      }
      // Cross-check collateral
      const oc = await q(`SELECT COALESCE(SUM(collateral_required),0) as open_coll FROM ${bot.name}_positions WHERE status='open'`)
      const ac = await q(`SELECT collateral_in_use FROM ${bot.name}_paper_account WHERE is_active=true AND COALESCE(account_type,'sandbox')='sandbox' LIMIT 1`)
      const openC = num(oc[0]?.open_coll), acctC = num(ac[0]?.collateral_in_use)
      console.log(`  Open collateral: $${openC.toFixed(2)}, Account collateral_in_use: $${acctC.toFixed(2)}` +
        (Math.abs(openC - acctC) > 0.01 ? ` *** MISMATCH $${Math.abs(openC - acctC).toFixed(2)}` : ' — match'))
    } catch (e) { console.log(`  ERROR: ${e.message}`) }

    // ── KELLY CRITERION DIAGNOSTIC (INFERNO + SPARK) ──
    if (bot.kelly) {
      subhr(`Q11: Kelly Criterion Diagnostic (${bot.label})`)
      try {
        // Get ALL closed trades (same query Kelly uses in scanner.ts)
        const trades = await q(`
          SELECT realized_pnl, contracts
          FROM ${bot.name}_positions
          WHERE status = 'closed' AND dte_mode = '${bot.dte}'
            AND COALESCE(account_type, 'sandbox') = 'sandbox'
            AND realized_pnl IS NOT NULL`)

        console.log(`  Total closed trades: ${trades.length}`)
        console.log(`  Kelly minimum: 10 trades (quarter-Kelly), 20 trades (half-Kelly)`)

        if (trades.length < 10) {
          console.log(`  STATUS: FALLBACK TO BP SIZING (need ${10 - trades.length} more trades)`)
        } else {
          let wins = 0, losses = 0, totalWinPc = 0, totalLossPc = 0

          for (const t of trades) {
            const pnl = num(t.realized_pnl)
            const c = Math.max(1, num(t.contracts))
            const ppc = pnl / c
            if (pnl > 0) { wins++; totalWinPc += ppc }
            else { losses++; totalLossPc += Math.abs(ppc) }
          }

          const winRate = wins / trades.length
          const avgWin = wins > 0 ? totalWinPc / wins : 0
          const avgLoss = losses > 0 ? totalLossPc / losses : 1

          // Kelly: f* = (b*p - q) / b
          const b = avgLoss > 0 ? avgWin / avgLoss : 0
          const kellyOpt = b > 0 ? (b * winRate - (1 - winRate)) / b : 0
          const fraction = trades.length >= 20 ? 0.5 : 0.25
          const fractionLabel = trades.length >= 20 ? 'HALF' : 'QUARTER'
          const kellyFrac = Math.max(0, kellyOpt * fraction)

          console.log(``)
          console.log(`  Sample size:     ${trades.length} trades`)
          console.log(`  Win rate:        ${(winRate * 100).toFixed(1)}% (${wins}W / ${losses}L)`)
          console.log(`  Avg win/contract:  $${avgWin.toFixed(2)}`)
          console.log(`  Avg loss/contract: $${avgLoss.toFixed(2)}`)
          console.log(`  Payoff ratio (b):  ${b.toFixed(3)}`)
          console.log(``)
          console.log(`  Kelly optimal:   ${(kellyOpt * 100).toFixed(2)}%`)
          console.log(`  Fraction used:   ${fractionLabel} (${(fraction * 100).toFixed(0)}%)`)
          console.log(`  Kelly applied:   ${(kellyFrac * 100).toFixed(2)}%`)
          console.log(``)

          if (kellyOpt <= 0) {
            console.log(`  *** NEGATIVE EDGE — Kelly says size at minimum (1 contract)`)
            console.log(`  *** This means avg losses exceed avg wins adjusted for win rate`)
          } else {
            // Simulate at different account balances
            for (const balance of [5000, 10000, 15000, 20000]) {
              // Assume $5 spread width, $0.40 credit -> collateral = ($5-$0.40)*100 = $460/contract
              const collateralPer = 460
              const maxRisk = balance * kellyFrac
              const contracts = Math.max(1, Math.floor(maxRisk / collateralPer))
              console.log(`  At $${balance.toLocaleString()} balance: ${contracts} contracts (max risk $${maxRisk.toFixed(0)}, $${collateralPer}/contract)`)
            }
          }

          console.log(``)
          console.log(`  STATUS: ${trades.length >= 20 ? 'HALF-KELLY ACTIVE' : trades.length >= 10 ? 'QUARTER-KELLY ACTIVE' : 'FALLBACK'} (${trades.length} trades)`)

          // Show what Kelly would have recommended for last 5 trades
          console.log(`\n  Last 5 trades — what Kelly would size:`)
          const last5 = await q(`
            SELECT position_id, contracts,
              ROUND(realized_pnl::numeric, 2) as pnl,
              ROUND(collateral_required::numeric, 0) as coll,
              to_char(open_time AT TIME ZONE 'America/Chicago', 'MM/DD HH24:MI') as open_ct
            FROM ${bot.name}_positions
            WHERE status = 'closed' AND dte_mode = '${bot.dte}'
              AND COALESCE(account_type, 'sandbox') = 'sandbox'
            ORDER BY close_time DESC LIMIT 5`)

          // Get current balance for Kelly sizing
          const acctRow = await q(`
            SELECT current_balance FROM ${bot.name}_paper_account
            WHERE is_active = true AND COALESCE(account_type, 'sandbox') = 'sandbox' LIMIT 1`)
          const currentBal = num(acctRow[0]?.current_balance)

          for (const t of last5) {
            const actualContracts = num(t.contracts)
            const collPer = actualContracts > 0 ? num(t.coll) / actualContracts : 460
            const kellyContracts = kellyOpt > 0
              ? Math.max(1, Math.floor(currentBal * kellyFrac / collPer))
              : 1
            const flag = actualContracts > kellyContracts * 1.5 ? ' << OVERSIZED'
              : actualContracts < kellyContracts * 0.5 ? ' << UNDERSIZED'
              : ''
            console.log(`  ${t.position_id}: actual=${actualContracts} kelly=${kellyContracts} pnl=$${t.pnl} ${t.open_ct}${flag}`)
          }
        }
      } catch (e) { console.log(`  ERROR: ${e.message}`) }
    }

    // ── OVERALL PERFORMANCE ──
    subhr('Performance Summary')
    try {
      const p = await q(`
        SELECT COUNT(*) as total,
          SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
          SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
          ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
          ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
          ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
          ROUND(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END)::numeric, 2) as avg_loss,
          ROUND(MAX(realized_pnl)::numeric, 2) as best,
          ROUND(MIN(realized_pnl)::numeric, 2) as worst,
          ROUND((SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(*),0))::numeric, 1) as win_pct
        FROM ${bot.name}_positions WHERE status = 'closed'`)
      const r = p[0]
      if (num(r.total) === 0) { console.log('  No closed trades yet'); continue }

      console.log(`  Trades: ${r.total} (${r.wins}W / ${r.losses}L)`)
      console.log(`  Win rate: ${r.win_pct}%`)
      console.log(`  Total P&L: $${r.total_pnl}`)
      console.log(`  Avg P&L/trade: $${r.avg_pnl}`)
      console.log(`  Avg win: $${r.avg_win}  |  Avg loss: $${r.avg_loss}`)
      console.log(`  Best: $${r.best}  |  Worst: $${r.worst}`)

      const wr = num(r.win_pct) / 100, aw = num(r.avg_win), al = Math.abs(num(r.avg_loss))
      const ev = (wr * aw) - ((1 - wr) * al)
      console.log(`  EV/trade: $${ev.toFixed(2)} ${ev > 0 ? '(POSITIVE)' : '*** NEGATIVE ***'}`)

      const gf = await q(`
        SELECT COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl END),0) as gw,
          ABS(COALESCE(SUM(CASE WHEN realized_pnl < 0 THEN realized_pnl END),0)) as gl
        FROM ${bot.name}_positions WHERE status = 'closed'`)
      const gw = num(gf[0].gw), gl = num(gf[0].gl)
      console.log(`  Profit factor: ${gl > 0 ? (gw / gl).toFixed(2) : 'INF'} ($${gw.toFixed(0)} / $${gl.toFixed(0)})`)

      const acct = await q(`
        SELECT current_balance, starting_capital, cumulative_pnl, buying_power, collateral_in_use
        FROM ${bot.name}_paper_account
        WHERE is_active = true AND COALESCE(account_type, 'sandbox') = 'sandbox' LIMIT 1`)
      if (acct[0]) {
        const a = acct[0]
        console.log(`  Account: bal=$${num(a.current_balance).toFixed(2)} start=$${num(a.starting_capital).toFixed(2)} cum=$${num(a.cumulative_pnl).toFixed(2)} bp=$${num(a.buying_power).toFixed(2)} coll=$${num(a.collateral_in_use).toFixed(2)}`)
      }
    } catch (e) { console.log(`  ERROR: ${e.message}`) }
  }

  console.log('\n' + '='.repeat(72))
  console.log('  AUDIT COMPLETE — ' + new Date().toISOString())
  console.log('='.repeat(72))

  await pool.end()
}

run().catch(e => { console.error('Fatal:', e.message); process.exit(1) })
