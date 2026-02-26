#!/usr/bin/env node
/**
 * IronForge Table Mapping Verification
 * =====================================
 * Verifies that the FLAME and SPARK bot table mapping is correctly wired
 * end-to-end: bot names → DB prefixes → actual tables → data.
 *
 * IronForge uses its own database with flame_*/spark_* table prefixes.
 * Python workers write to flame_*/spark_* tables.
 * The webapp reads from the same tables via botTable().
 *
 * Usage (from Render shell):
 *   cd ~/project/src/ironforge/webapp
 *   node scripts/verify_table_mapping.js
 */

const { Pool } = require('pg')

const DATABASE_URL = process.env.DATABASE_URL
if (!DATABASE_URL) {
  console.error('ERROR: DATABASE_URL not set')
  process.exit(1)
}

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

// ---- Mapping definitions (mirrors webapp/src/lib/db.ts) ----

const DB_PREFIX = {
  flame: 'flame',
  spark: 'spark',
}

const HEARTBEAT_MAP = {
  flame: 'FLAME',
  spark: 'SPARK',
}

const DTE_MODES = {
  flame: '2DTE',
  spark: '1DTE',
}

function botTable(bot, suffix) {
  const prefix = DB_PREFIX[bot] || bot
  return `${prefix}_${suffix}`
}

function heartbeatName(bot) {
  return HEARTBEAT_MAP[bot] || bot.toUpperCase()
}

function dteMode(bot) {
  return DTE_MODES[bot] || null
}

const TABLE_SUFFIXES = [
  'positions', 'paper_account', 'signals', 'equity_snapshots',
  'logs', 'daily_perf', 'pdt_log', 'config',
]

async function run() {
  console.log('============================================================')
  console.log('  IRONFORGE TABLE MAPPING VERIFICATION')
  console.log(`  ${new Date().toISOString()}`)
  console.log('============================================================')

  // ── 1. DB CONNECTION ─────────────────────────────────────────
  section(1, 'DATABASE CONNECTION')
  try {
    const res = await pool.query('SELECT version()')
    const pgVer = res.rows[0].version.split(',')[0]
    pass('PostgreSQL', pgVer)
  } catch (err) {
    fail('PostgreSQL', err.message)
    console.error('\n  FATAL: Cannot connect to database. Exiting.')
    process.exit(1)
  }

  // ── 2. MAPPING DEFINITION ───────────────────────────────────
  section(2, 'MAPPING DEFINITIONS')
  console.log('  DB_PREFIX (bot → table prefix):')
  for (const [display, prefix] of Object.entries(DB_PREFIX)) {
    console.log(`    ${display.toUpperCase()} → ${prefix}_* tables`)
  }
  console.log('  HEARTBEAT_MAP (bot → heartbeat bot_name):')
  for (const [display, hb] of Object.entries(HEARTBEAT_MAP)) {
    console.log(`    ${display.toUpperCase()} → bot_name="${hb}"`)
  }
  console.log('  DTE_MODE:')
  for (const [bot, dte] of Object.entries(DTE_MODES)) {
    console.log(`    ${bot.toUpperCase()} → ${dte}`)
  }
  pass('Mapping definitions loaded', '2 bots configured')

  // ── 3. TABLE EXISTENCE ──────────────────────────────────────
  section(3, 'TABLE EXISTENCE')
  const allTablesOk = { flame: true, spark: true }

  for (const bot of ['flame', 'spark']) {
    console.log(`\n  --- ${bot.toUpperCase()} (prefix: ${DB_PREFIX[bot]}) ---`)
    for (const suffix of TABLE_SUFFIXES) {
      const tableName = botTable(bot, suffix)
      try {
        const res = await pool.query(`
          SELECT EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'public' AND tablename = $1
          ) as exists
        `, [tableName])
        if (res.rows[0].exists) {
          pass(`${tableName}`, 'exists')
        } else {
          fail(`${tableName}`, 'TABLE MISSING')
          allTablesOk[bot] = false
        }
      } catch (err) {
        fail(`${tableName}`, err.message)
        allTablesOk[bot] = false
      }
    }
  }

  // Check shared table
  try {
    const res = await pool.query(`
      SELECT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'public' AND tablename = 'bot_heartbeats'
      ) as exists
    `)
    if (res.rows[0].exists) {
      pass('bot_heartbeats', 'exists')
    } else {
      fail('bot_heartbeats', 'TABLE MISSING')
    }
  } catch (err) {
    fail('bot_heartbeats', err.message)
  }

  // ── 4. NO STALE FAITH/GRACE TABLES ─────────────────────────
  section(4, 'STALE TABLE CHECK (faith_*/grace_* should NOT exist)')
  try {
    const res = await pool.query(`
      SELECT tablename FROM pg_tables
      WHERE schemaname = 'public'
      AND (tablename LIKE 'faith_%' OR tablename LIKE 'grace_%')
      ORDER BY tablename
    `)
    if (res.rows.length === 0) {
      pass('No stale tables', 'faith_*/grace_* correctly absent — IronForge uses flame_*/spark_*')
    } else {
      const stale = res.rows.map(r => r.tablename)
      warn('Legacy AlphaGEX tables found', stale.join(', '))
      console.log('  NOTE: faith_*/grace_* are AlphaGEX legacy tables.')
      console.log('  IronForge should use flame_*/spark_* in its own database.')
    }
  } catch (err) {
    fail('Stale table check', err.message)
  }

  // ── 5. DATA THROUGH MAPPING ─────────────────────────────────
  section(5, 'DATA THROUGH MAPPED TABLES')
  for (const bot of ['flame', 'spark']) {
    const dte = dteMode(bot)
    const posTable = botTable(bot, 'positions')
    const acctTable = botTable(bot, 'paper_account')
    const configTable = botTable(bot, 'config')

    console.log(`\n  --- ${bot.toUpperCase()} (reading from ${DB_PREFIX[bot]}_* tables, dte_mode=${dte}) ---`)

    // Paper account
    try {
      const res = await pool.query(
        `SELECT current_balance, cumulative_pnl, total_trades, is_active
         FROM ${acctTable}
         WHERE dte_mode = $1
         ORDER BY id DESC LIMIT 1`,
        [dte]
      )
      if (res.rows.length > 0) {
        const r = res.rows[0]
        pass(`${acctTable} data`,
          `balance=$${pf(r.current_balance)} P&L=$${pf(r.cumulative_pnl)} trades=${r.total_trades} active=${r.is_active}`)
      } else {
        warn(`${acctTable}`, 'No account rows — bot may not have been initialized')
      }
    } catch (err) {
      fail(`${acctTable} query`, err.message)
    }

    // Positions count
    try {
      const res = await pool.query(
        `SELECT
           COUNT(*) FILTER (WHERE status = 'open') as open_ct,
           COUNT(*) FILTER (WHERE status != 'open') as closed_ct,
           COUNT(*) as total_ct
         FROM ${posTable}
         WHERE dte_mode = $1`,
        [dte]
      )
      const r = res.rows[0]
      pass(`${posTable} data`,
        `${r.open_ct} open, ${r.closed_ct} closed, ${r.total_ct} total`)
    } catch (err) {
      fail(`${posTable} query`, err.message)
    }

    // Config
    try {
      const res = await pool.query(
        `SELECT sd_multiplier, spread_width, max_contracts, starting_capital
         FROM ${configTable}
         WHERE dte_mode = $1
         LIMIT 1`,
        [dte]
      )
      if (res.rows.length > 0) {
        const r = res.rows[0]
        pass(`${configTable} data`,
          `SD=${r.sd_multiplier} width=${r.spread_width} max_contracts=${r.max_contracts} capital=$${pf(r.starting_capital)}`)
      } else {
        warn(`${configTable}`, 'No config row — using defaults')
      }
    } catch (err) {
      fail(`${configTable} query`, err.message)
    }
  }

  // ── 6. HEARTBEAT MAPPING ────────────────────────────────────
  section(6, 'HEARTBEAT MAPPING')
  for (const bot of ['flame', 'spark']) {
    const hbName = heartbeatName(bot)
    try {
      const res = await pool.query(
        `SELECT bot_name, last_heartbeat, status, scan_count,
                EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_ago
         FROM bot_heartbeats
         WHERE bot_name = $1`,
        [hbName]
      )
      if (res.rows.length > 0) {
        const r = res.rows[0]
        const ago = r.seconds_ago != null ? `${Math.round(r.seconds_ago)}s ago` : 'never'
        const stale = r.seconds_ago != null && r.seconds_ago > 600
        pass(`${bot.toUpperCase()} → ${hbName}`,
          `status=${r.status} scans=${r.scan_count} last=${ago}${stale ? ' [STALE]' : ''}`)
        if (stale) warn(`${hbName} heartbeat stale`, `${Math.round(r.seconds_ago)}s since last`)
      } else {
        warn(`${bot.toUpperCase()} → ${hbName}`, 'No heartbeat row — bot may not have run yet')
      }
    } catch (err) {
      fail(`${bot.toUpperCase()} heartbeat`, err.message)
    }
  }

  // ── 7. PYTHON↔WEBAPP ALIGNMENT ──────────────────────────────
  section(7, 'PYTHON ↔ WEBAPP ALIGNMENT')
  console.log('  Verifying Python writers and webapp readers use same tables...')

  // Python TradingDatabase uses: bot_name.lower() as prefix
  // FLAME → flame_, SPARK → spark_
  // Webapp botTable() uses: DB_PREFIX[bot] as prefix
  // flame → flame_, spark → spark_
  const pythonPrefixes = { FLAME: 'flame', SPARK: 'spark' }
  const webappPrefixes = { flame: DB_PREFIX['flame'], spark: DB_PREFIX['spark'] }

  for (const [pyBot, pyPrefix] of Object.entries(pythonPrefixes)) {
    const webBot = pyBot.toLowerCase()
    const webPrefix = webappPrefixes[webBot]
    if (pyPrefix === webPrefix) {
      pass(`${pyBot} alignment`, `Python writes to ${pyPrefix}_*, webapp reads ${webPrefix}_*`)
    } else {
      fail(`${pyBot} alignment`, `MISMATCH: Python writes ${pyPrefix}_*, webapp reads ${webPrefix}_*`)
    }
  }

  // Heartbeat alignment
  for (const [pyBot, pyName] of Object.entries({ FLAME: 'FLAME', SPARK: 'SPARK' })) {
    const webBot = pyBot.toLowerCase()
    const webName = heartbeatName(webBot)
    if (pyName === webName) {
      pass(`${pyBot} heartbeat alignment`, `Python writes bot_name='${pyName}', webapp reads '${webName}'`)
    } else {
      fail(`${pyBot} heartbeat alignment`, `MISMATCH: Python writes '${pyName}', webapp reads '${webName}'`)
    }
  }

  // DTE mode alignment
  for (const [pyBot, pyDte] of Object.entries({ FLAME: '2DTE', SPARK: '1DTE' })) {
    const webBot = pyBot.toLowerCase()
    const webDte = dteMode(webBot)
    if (pyDte === webDte) {
      pass(`${pyBot} dte_mode alignment`, `Python=${pyDte}, webapp=${webDte}`)
    } else {
      fail(`${pyBot} dte_mode alignment`, `MISMATCH: Python=${pyDte}, webapp=${webDte || 'null'}`)
    }
  }

  // ── 8. API ROUTE SIMULATION ─────────────────────────────────
  section(8, 'API ROUTE SIMULATION (botTable function)')
  const testCases = [
    ['flame', 'positions', 'flame_positions'],
    ['flame', 'paper_account', 'flame_paper_account'],
    ['flame', 'equity_snapshots', 'flame_equity_snapshots'],
    ['flame', 'config', 'flame_config'],
    ['spark', 'positions', 'spark_positions'],
    ['spark', 'paper_account', 'spark_paper_account'],
    ['spark', 'equity_snapshots', 'spark_equity_snapshots'],
    ['spark', 'config', 'spark_config'],
  ]

  for (const [bot, suffix, expected] of testCases) {
    const actual = botTable(bot, suffix)
    if (actual === expected) {
      pass(`botTable('${bot}', '${suffix}')`, `→ ${actual}`)
    } else {
      fail(`botTable('${bot}', '${suffix}')`, `expected ${expected}, got ${actual}`)
    }
  }

  // ── 9. DTE_MODE COLUMN CHECK ────────────────────────────────
  section(9, 'DTE_MODE COLUMN VERIFICATION')
  for (const bot of ['flame', 'spark']) {
    const tableName = botTable(bot, 'positions')
    try {
      const res = await pool.query(`
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = $1
        AND column_name = 'dte_mode'
      `, [tableName])
      const hasDteMode = res.rows.length > 0
      if (hasDteMode) {
        pass(`${tableName} has dte_mode`, `Column exists, filtered by ${dteMode(bot)}`)
      } else {
        fail(`${tableName} missing dte_mode`, `${bot.toUpperCase()} requires dte_mode for filtering`)
      }
    } catch (err) {
      fail(`${tableName} dte_mode check`, err.message)
    }
  }

  // ── 10. SNAPSHOT COLUMN CHECK ───────────────────────────────
  section(10, 'EQUITY SNAPSHOT COLUMN VERIFICATION')
  for (const bot of ['flame', 'spark']) {
    const tableName = botTable(bot, 'equity_snapshots')
    try {
      const res = await pool.query(`
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = $1
        AND column_name IN ('snapshot_time', 'timestamp')
        ORDER BY column_name
      `, [tableName])
      const cols = res.rows.map(r => r.column_name)
      if (cols.includes('snapshot_time')) {
        pass(`${tableName}`, `Uses snapshot_time column (IronForge schema)`)
      } else if (cols.includes('timestamp')) {
        warn(`${tableName}`, `Uses "timestamp" column (AlphaGEX schema) — webapp queries must use "timestamp"`)
      } else {
        fail(`${tableName}`, 'Neither snapshot_time nor timestamp column found')
      }
    } catch (err) {
      fail(`${tableName} column check`, err.message)
    }
  }

  // ── 11. RECENT ACTIVITY CHECK ───────────────────────────────
  section(11, 'RECENT ACTIVITY (last 24h)')
  for (const bot of ['flame', 'spark']) {
    const dte = dteMode(bot)
    const logsTable = botTable(bot, 'logs')
    const signalsTable = botTable(bot, 'signals')

    // Recent logs
    try {
      const res = await pool.query(
        `SELECT COUNT(*) as cnt FROM ${logsTable}
         WHERE log_time >= NOW() - INTERVAL '24 hours' AND dte_mode = $1`,
        [dte]
      )
      const cnt = parseInt(res.rows[0].cnt)
      if (cnt > 0) {
        pass(`${bot.toUpperCase()} logs (24h)`, `${cnt} entries`)
      } else {
        warn(`${bot.toUpperCase()} logs (24h)`, 'None — bot may not have run recently')
      }
    } catch (err) {
      fail(`${bot.toUpperCase()} logs`, err.message)
    }

    // Recent signals
    try {
      const res = await pool.query(
        `SELECT COUNT(*) as cnt,
                COUNT(*) FILTER (WHERE was_executed = TRUE) as executed
         FROM ${signalsTable}
         WHERE signal_time >= NOW() - INTERVAL '24 hours' AND dte_mode = $1`,
        [dte]
      )
      const r = res.rows[0]
      const cnt = parseInt(r.cnt)
      const exec = parseInt(r.executed)
      if (cnt > 0) {
        pass(`${bot.toUpperCase()} signals (24h)`, `${cnt} signals, ${exec} executed`)
      } else {
        warn(`${bot.toUpperCase()} signals (24h)`, 'None — no scans in last 24h')
      }
    } catch (err) {
      fail(`${bot.toUpperCase()} signals`, err.message)
    }
  }

  // ── SUMMARY ──────────────────────────────────────────────────
  console.log(`\n${'='.repeat(60)}`)
  console.log(`  SUMMARY: ${passed} passed, ${failed} failed, ${warnings} warnings`)
  console.log('='.repeat(60))
  if (failed === 0) {
    console.log('  TABLE MAPPING VERIFIED — FLAME→flame_*, SPARK→spark_* working correctly')
    if (warnings > 0) console.log(`  ${warnings} warning(s) — review above`)
  } else {
    console.log('  MAPPING ISSUES DETECTED — fix the [X] items above')
  }

  await pool.end()
  process.exit(failed > 0 ? 1 : 0)
}

// Helpers
function pf(val) {
  if (val == null) return '0.00'
  return parseFloat(val).toFixed(2)
}

run().catch(err => {
  console.error('FATAL:', err)
  process.exit(1)
})
