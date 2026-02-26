#!/usr/bin/env node
/**
 * IronForge Render Shell Diagnostic
 * ==================================
 * Uses Node.js + pg (already installed in webapp's node_modules).
 * No Python, no venv, no pip install.
 *
 * Usage (from Render shell):
 *   cd ~/project/src/ironforge/webapp
 *   node scripts/diag.js
 */

const { Pool } = require('pg')

const DATABASE_URL = process.env.DATABASE_URL
if (!DATABASE_URL) {
  console.error('ERROR: DATABASE_URL not set')
  process.exit(1)
}

const TRADIER_API_KEY = process.env.TRADIER_API_KEY || ''
const TRADIER_BASE_URL = process.env.TRADIER_BASE_URL || 'https://sandbox.tradier.com/v1'

const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  max: 3,
})

let passed = 0
let failed = 0
let warnings = 0

function pass(label, detail) {
  passed++
  console.log(`  [+] PASS ${label}${detail ? ': ' + detail : ''}`)
}

function fail(label, detail) {
  failed++
  console.log(`  [X] FAIL ${label}${detail ? ': ' + detail : ''}`)
}

function warn(label, detail) {
  warnings++
  console.log(`  [!] WARN ${label}${detail ? ': ' + detail : ''}`)
}

function section(num, title) {
  console.log(`\n${'='.repeat(60)}`)
  console.log(`  ${num}. ${title}`)
  console.log('='.repeat(60))
}

async function run() {
  console.log('============================================================')
  console.log('  IRONFORGE RENDER DIAGNOSTIC')
  console.log(`  ${new Date().toISOString()}`)
  console.log('============================================================')

  // ── 1. DATABASE CONNECTION ─────────────────────────────────────
  section(1, 'DATABASE CONNECTION')
  let client
  try {
    client = await pool.connect()
    const vr = await client.query('SELECT version()')
    const pgVer = vr.rows[0].version.split(',')[0]
    pass('PostgreSQL', pgVer)

    const tr = await client.query("SELECT NOW() AT TIME ZONE 'America/Chicago' as ct")
    console.log(`  DB time (CT): ${tr.rows[0].ct}`)
    client.release()
  } catch (err) {
    fail('PostgreSQL', err.message)
    console.error('\n  FATAL: Cannot connect to database. Exiting.')
    process.exit(1)
  }

  // ── 2. TABLES ──────────────────────────────────────────────────
  section(2, 'TABLE VERIFICATION')
  try {
    const res = await pool.query(`
      SELECT tablename FROM pg_tables
      WHERE schemaname = 'public'
      AND (tablename LIKE 'flame_%' OR tablename LIKE 'spark_%'
           OR tablename = 'bot_heartbeats' OR tablename = 'bot_active')
      ORDER BY tablename
    `)
    const tables = res.rows.map(r => r.tablename)
    const expected = [
      'flame_positions', 'flame_paper_account', 'flame_signals',
      'flame_logs', 'flame_equity_snapshots', 'flame_pdt_log',
      'flame_daily_perf', 'flame_config',
      'spark_positions', 'spark_paper_account', 'spark_signals',
      'spark_logs', 'spark_equity_snapshots', 'spark_pdt_log',
      'spark_daily_perf', 'spark_config',
      'bot_heartbeats',
    ]
    const missing = expected.filter(t => !tables.includes(t))
    if (missing.length === 0) {
      pass('All expected tables', `${tables.length} found`)
    } else {
      fail('Missing tables', missing.join(', '))
    }
  } catch (err) {
    fail('Table check', err.message)
  }

  // ── 3. PAPER ACCOUNTS ─────────────────────────────────────────
  section(3, 'PAPER ACCOUNTS')
  for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']]) {
    try {
      const res = await pool.query(
        `SELECT current_balance, cumulative_pnl, total_trades,
                collateral_in_use, buying_power, is_active, starting_capital
         FROM ${bot}_paper_account
         WHERE dte_mode = $1
         ORDER BY id DESC LIMIT 1`,
        [dte]
      )
      if (res.rows.length === 0) {
        fail(`${bot.toUpperCase()} account`, 'No account found')
      } else {
        const r = res.rows[0]
        pass(`${bot.toUpperCase()} account`,
          `balance=$${pf(r.current_balance)} ` +
          `P&L=$${pf(r.cumulative_pnl)} ` +
          `BP=$${pf(r.buying_power)} ` +
          `trades=${r.total_trades} ` +
          `collateral=$${pf(r.collateral_in_use)} ` +
          `active=${r.is_active}`
        )
        if (parseFloat(r.buying_power) < 200) {
          warn(`${bot.toUpperCase()} low buying power`, `$${pf(r.buying_power)} < $200`)
        }
      }
    } catch (err) {
      fail(`${bot.toUpperCase()} account`, err.message)
    }
  }

  // ── 4. OPEN POSITIONS ─────────────────────────────────────────
  section(4, 'OPEN POSITIONS')
  for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']]) {
    try {
      const res = await pool.query(
        `SELECT position_id, ticker, expiration,
                put_short_strike, put_long_strike,
                call_short_strike, call_long_strike,
                total_credit, contracts, open_time
         FROM ${bot}_positions
         WHERE status = 'open' AND dte_mode = $1
         ORDER BY open_time DESC`,
        [dte]
      )
      if (res.rows.length === 0) {
        pass(`${bot.toUpperCase()} positions`, '0 open (ready to trade)')
      } else {
        for (const p of res.rows) {
          console.log(`  [${bot.toUpperCase()}] ${p.position_id}: ` +
            `${p.put_long_strike}/${p.put_short_strike}P-` +
            `${p.call_short_strike}/${p.call_long_strike}C ` +
            `x${p.contracts} @ $${pf(p.total_credit)} ` +
            `exp=${str(p.expiration)} opened=${str(p.open_time)}`)
        }
        pass(`${bot.toUpperCase()} positions`, `${res.rows.length} open`)
      }
    } catch (err) {
      fail(`${bot.toUpperCase()} positions`, err.message)
    }
  }

  // ── 5. RECENT CLOSED TRADES ────────────────────────────────────
  section(5, 'RECENT CLOSED TRADES (last 5)')
  for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']]) {
    try {
      const res = await pool.query(
        `SELECT position_id, close_time, realized_pnl, close_reason,
                put_long_strike, put_short_strike,
                call_short_strike, call_long_strike, contracts
         FROM ${bot}_positions
         WHERE status != 'open' AND dte_mode = $1
         ORDER BY close_time DESC NULLS LAST
         LIMIT 5`,
        [dte]
      )
      if (res.rows.length === 0) {
        console.log(`  [${bot.toUpperCase()}] No closed trades yet`)
      } else {
        for (const t of res.rows) {
          const pnl = t.realized_pnl != null ? `$${pf(t.realized_pnl)}` : 'N/A'
          console.log(`  [${bot.toUpperCase()}] ${str(t.close_time).slice(0,16)} ` +
            `${t.put_long_strike}/${t.put_short_strike}P-` +
            `${t.call_short_strike}/${t.call_long_strike}C ` +
            `x${t.contracts} P&L=${pnl} [${t.close_reason}]`)
        }
      }

      // Performance summary
      const stats = await pool.query(
        `SELECT COUNT(*) as total,
                COUNT(*) FILTER (WHERE realized_pnl > 0) as wins,
                COALESCE(SUM(realized_pnl), 0) as total_pnl,
                COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) as avg_win,
                COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl <= 0), 0) as avg_loss
         FROM ${bot}_positions
         WHERE status != 'open' AND dte_mode = $1 AND realized_pnl IS NOT NULL`,
        [dte]
      )
      const s = stats.rows[0]
      const wr = parseInt(s.total) > 0
        ? ((parseInt(s.wins) / parseInt(s.total)) * 100).toFixed(1)
        : '0.0'
      pass(`${bot.toUpperCase()} performance`,
        `${s.total} trades, WR=${wr}%, P&L=$${pf(s.total_pnl)}, ` +
        `avg_win=$${pf(s.avg_win)}, avg_loss=$${pf(s.avg_loss)}`)
    } catch (err) {
      fail(`${bot.toUpperCase()} trades`, err.message)
    }
  }

  // ── 6. HEARTBEATS ─────────────────────────────────────────────
  section(6, 'BOT HEARTBEATS')
  try {
    const res = await pool.query(`
      SELECT bot_name, last_heartbeat, status, scan_count,
             EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_ago
      FROM bot_heartbeats ORDER BY bot_name
    `)
    if (res.rows.length === 0) {
      warn('No heartbeats', 'Bots may not have run since deploy')
    } else {
      for (const r of res.rows) {
        const ago = r.seconds_ago != null ? `${Math.round(r.seconds_ago)}s ago` : 'never'
        const stale = r.seconds_ago != null && r.seconds_ago > 600
        const tag = stale ? '[STALE]' : '[OK]'
        console.log(`  ${tag} ${r.bot_name}: status=${r.status} scans=${r.scan_count} last=${ago}`)
        if (stale) warn(`${r.bot_name} stale`, `${Math.round(r.seconds_ago)}s since last heartbeat`)
      }
    }
  } catch (err) {
    fail('Heartbeats', err.message)
  }

  // ── 7. BOT ACTIVE STATUS ──────────────────────────────────────
  section(7, 'BOT ACTIVE STATUS')
  try {
    const res = await pool.query('SELECT bot_name, is_active FROM bot_active ORDER BY bot_name')
    if (res.rows.length === 0) {
      // Check paper_account for active state
      for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']]) {
        const ar = await pool.query(
          `SELECT is_active FROM ${bot}_paper_account WHERE dte_mode = $1 ORDER BY id DESC LIMIT 1`,
          [dte]
        )
        if (ar.rows.length > 0) {
          const active = ar.rows[0].is_active
          if (active) pass(`${bot.toUpperCase()} active`, 'ENABLED')
          else warn(`${bot.toUpperCase()} inactive`, 'DISABLED — toggle on to trade')
        }
      }
    } else {
      for (const r of res.rows) {
        if (r.is_active) pass(`${r.bot_name} active`, 'ENABLED')
        else warn(`${r.bot_name} inactive`, 'DISABLED')
      }
    }
  } catch (err) {
    // bot_active table may not exist — check paper_account instead
    for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']]) {
      try {
        const ar = await pool.query(
          `SELECT is_active FROM ${bot}_paper_account WHERE dte_mode = $1 ORDER BY id DESC LIMIT 1`,
          [dte]
        )
        if (ar.rows.length > 0) {
          const active = ar.rows[0].is_active
          if (active) pass(`${bot.toUpperCase()} active`, 'ENABLED (from paper_account)')
          else warn(`${bot.toUpperCase()} inactive`, 'DISABLED')
        }
      } catch (e2) {
        fail(`${bot.toUpperCase()} active check`, e2.message)
      }
    }
  }

  // ── 8. EQUITY SNAPSHOTS TODAY ──────────────────────────────────
  section(8, 'EQUITY SNAPSHOTS (today)')
  for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']]) {
    try {
      const res = await pool.query(
        `SELECT COUNT(*) as cnt,
                MIN(snapshot_time) as first_snap,
                MAX(snapshot_time) as last_snap
         FROM ${bot}_equity_snapshots
         WHERE snapshot_time::date = CURRENT_DATE AND dte_mode = $1`,
        [dte]
      )
      const r = res.rows[0]
      const cnt = parseInt(r.cnt)
      if (cnt > 0) {
        pass(`${bot.toUpperCase()} snapshots`, `${cnt} today (first: ${str(r.first_snap)}, last: ${str(r.last_snap)})`)
      } else {
        warn(`${bot.toUpperCase()} snapshots`, 'None today — intraday chart will be empty')
      }
    } catch (err) {
      fail(`${bot.toUpperCase()} snapshots`, err.message)
    }
  }

  // ── 9. TRADE GATES ─────────────────────────────────────────────
  section(9, 'TRADE GATES')
  for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']]) {
    try {
      // Traded today?
      const today = await pool.query(
        `SELECT COUNT(*) as cnt FROM ${bot}_positions
         WHERE open_date = CURRENT_DATE AND dte_mode = $1`,
        [dte]
      )
      const tradedToday = parseInt(today.rows[0].cnt) > 0
      if (!tradedToday) {
        pass(`${bot.toUpperCase()} hasn't traded today`, 'eligible')
      } else {
        warn(`${bot.toUpperCase()} already traded today`, 'will skip')
      }

      // PDT
      const pdt = await pool.query(
        `SELECT COUNT(*) as cnt FROM ${bot}_pdt_log
         WHERE closed_at IS NOT NULL
         AND closed_at >= NOW() - INTERVAL '5 days'
         AND is_day_trade = TRUE
         AND dte_mode = $1`,
        [dte]
      )
      const pdtCount = parseInt(pdt.rows[0].cnt)
      if (pdtCount < 3) {
        pass(`${bot.toUpperCase()} PDT room`, `${pdtCount}/3 day trades`)
      } else {
        warn(`${bot.toUpperCase()} PDT limit`, `${pdtCount}/3 — paper blocked, sandbox only`)
      }
    } catch (err) {
      fail(`${bot.toUpperCase()} gates`, err.message)
    }
  }

  // ── 10. TRADING WINDOW ─────────────────────────────────────────
  section(10, 'TRADING WINDOW')
  try {
    const tr = await pool.query("SELECT NOW() AT TIME ZONE 'America/Chicago' as ct")
    const ct = new Date(tr.rows[0].ct)
    const hour = ct.getHours()
    const min = ct.getMinutes()
    const dow = ct.getDay()
    const timeStr = `${String(hour).padStart(2,'0')}:${String(min).padStart(2,'0')}`
    const isWeekday = dow >= 1 && dow <= 5
    const inWindow = isWeekday && (hour > 8 || (hour === 8 && min >= 30)) && (hour < 14 || (hour === 14 && min <= 45))

    console.log(`  Time (CT): ${timeStr} (${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][dow]})`)
    if (inWindow) {
      pass('Trading window', `${timeStr} CT is within 08:30-14:45 CT`)
    } else if (!isWeekday) {
      warn('Weekend', 'Market closed')
    } else {
      warn('Outside trading window', `${timeStr} CT — window is 08:30-14:45 CT`)
    }
  } catch (err) {
    fail('Trading window', err.message)
  }

  // ── 11. TRADIER API ────────────────────────────────────────────
  section(11, 'TRADIER API')
  if (!TRADIER_API_KEY) {
    fail('TRADIER_API_KEY', 'Not set — bots cannot get quotes or place orders')
  } else {
    pass('TRADIER_API_KEY', `${TRADIER_API_KEY.slice(0, 10)}...`)
    console.log(`  Base URL: ${TRADIER_BASE_URL}`)

    try {
      const resp = await fetch(`${TRADIER_BASE_URL}/markets/quotes?symbols=SPY,VIX`, {
        headers: {
          'Authorization': `Bearer ${TRADIER_API_KEY}`,
          'Accept': 'application/json',
        },
      })
      if (!resp.ok) {
        fail('Tradier HTTP', `status ${resp.status}`)
      } else {
        const data = await resp.json()
        let quotes = data.quotes?.quote
        if (!Array.isArray(quotes)) quotes = quotes ? [quotes] : []

        for (const q of quotes) {
          console.log(`  ${q.symbol}: last=$${q.last} bid=$${q.bid} ask=$${q.ask}`)
        }

        const spy = quotes.find(q => q.symbol === 'SPY')
        if (spy && parseFloat(spy.last) > 0) {
          pass('SPY quote', `$${spy.last}`)
        } else {
          fail('SPY quote', 'No valid quote')
        }
      }
    } catch (err) {
      fail('Tradier API', err.message)
    }

    // Expirations
    try {
      const resp = await fetch(
        `${TRADIER_BASE_URL}/markets/options/expirations?symbol=SPY&includeAllRoots=true`,
        {
          headers: {
            'Authorization': `Bearer ${TRADIER_API_KEY}`,
            'Accept': 'application/json',
          },
        }
      )
      if (resp.ok) {
        const data = await resp.json()
        let dates = data.expirations?.date || []
        if (!Array.isArray(dates)) dates = [dates]
        pass('SPY expirations', `${dates.length} dates, nearest=${dates[0] || 'none'}`)
      }
    } catch (err) {
      fail('Expirations', err.message)
    }
  }

  // ── 12. RECENT LOGS ────────────────────────────────────────────
  section(12, 'RECENT LOGS (last 5 each)')
  for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']]) {
    try {
      const res = await pool.query(
        `SELECT log_time, level, message FROM ${bot}_logs
         WHERE dte_mode = $1
         ORDER BY log_time DESC LIMIT 5`,
        [dte]
      )
      if (res.rows.length === 0) {
        console.log(`  [${bot.toUpperCase()}] No logs yet`)
      } else {
        for (const r of res.rows) {
          const ts = str(r.log_time).slice(0, 19)
          console.log(`  [${bot.toUpperCase()}] ${ts} [${r.level}] ${(r.message || '').slice(0, 80)}`)
        }
      }
    } catch (err) {
      console.log(`  [${bot.toUpperCase()}] Log error: ${err.message}`)
    }
  }

  // ── SUMMARY ────────────────────────────────────────────────────
  console.log(`\n${'='.repeat(60)}`)
  console.log(`  SUMMARY: ${passed} passed, ${failed} failed, ${warnings} warnings`)
  console.log('='.repeat(60))
  if (failed === 0) {
    console.log('  ALL CHECKS PASSED')
    if (warnings > 0) console.log(`  ${warnings} warning(s) — review above`)
  } else {
    console.log('  SOME CHECKS FAILED — fix the [X] items above')
  }

  await pool.end()
}

// Helpers
function pf(val) {
  if (val == null) return '0.00'
  return parseFloat(val).toFixed(2)
}
function str(val) {
  if (val == null) return '?'
  if (val instanceof Date) return val.toISOString()
  return String(val)
}

run().catch(err => {
  console.error('FATAL:', err)
  process.exit(1)
})
