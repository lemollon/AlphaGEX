/**
 * PostgreSQL client for IronForge on Render.
 *
 * Replaces the Databricks REST API client. Uses node-postgres (pg) directly.
 * Auto-creates tables on first use so the dashboard works before workers start.
 */

import { Pool } from 'pg'

let _pool: Pool | null = null

function getPool(): Pool {
  if (!_pool) {
    _pool = new Pool({
      connectionString: process.env.DATABASE_URL,
      ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
      max: 5,
    })
  }
  return _pool
}

/**
 * Map Iron Forge bot names to database table prefixes.
 * IronForge has its own database — tables use flame_*/spark_* prefixes.
 */
const DB_PREFIX: Record<string, string> = {
  flame: 'flame',
  spark: 'spark',
}

/** Map display names to heartbeat bot_name values in bot_heartbeats table. */
const HEARTBEAT_MAP: Record<string, string> = {
  flame: 'FLAME',
  spark: 'SPARK',
}

/** Bot-specific table name, mapped to AlphaGEX table prefix. */
export function botTable(bot: string, suffix: string): string {
  const prefix = DB_PREFIX[bot] || bot
  return `${prefix}_${suffix}`
}

/** Get the heartbeat bot_name for this display bot. */
export function heartbeatName(bot: string): string {
  return HEARTBEAT_MAP[bot] || bot.toUpperCase()
}

/**
 * Returns the dte_mode value for this bot.
 * Both flame and spark tables have a dte_mode column.
 */
export function dteMode(bot: string): string | null {
  if (bot === 'flame') return '2DTE'
  if (bot === 'spark') return '1DTE'
  return null
}

// ---- Auto-create tables on first use ----

let tablesReady = false

const INIT_DDL = `
CREATE TABLE IF NOT EXISTS bot_heartbeats (
  bot_name TEXT NOT NULL PRIMARY KEY,
  last_heartbeat TIMESTAMPTZ,
  status TEXT,
  scan_count BIGINT DEFAULT 0,
  details TEXT
);
` + ['flame', 'spark'].map(bot => `
CREATE TABLE IF NOT EXISTS ${bot}_paper_account (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  starting_capital NUMERIC(12,2) NOT NULL,
  current_balance NUMERIC(12,2) NOT NULL,
  cumulative_pnl NUMERIC(12,2) DEFAULT 0,
  total_trades INT DEFAULT 0,
  collateral_in_use NUMERIC(12,2) DEFAULT 0,
  buying_power NUMERIC(12,2) NOT NULL,
  high_water_mark NUMERIC(12,2) NOT NULL,
  max_drawdown NUMERIC(12,2) DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  dte_mode TEXT DEFAULT '2DTE',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ${bot}_positions (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  position_id TEXT NOT NULL,
  ticker TEXT NOT NULL,
  expiration DATE NOT NULL,
  put_short_strike NUMERIC(10,2) NOT NULL,
  put_long_strike NUMERIC(10,2) NOT NULL,
  put_credit NUMERIC(10,4) NOT NULL,
  call_short_strike NUMERIC(10,2) NOT NULL,
  call_long_strike NUMERIC(10,2) NOT NULL,
  call_credit NUMERIC(10,4) NOT NULL,
  contracts INT NOT NULL,
  spread_width NUMERIC(10,2) NOT NULL,
  total_credit NUMERIC(10,4) NOT NULL,
  max_loss NUMERIC(10,2) NOT NULL,
  max_profit NUMERIC(10,2) NOT NULL,
  collateral_required NUMERIC(10,2) DEFAULT 0,
  underlying_at_entry NUMERIC(10,2) NOT NULL,
  vix_at_entry NUMERIC(6,2),
  expected_move NUMERIC(10,2),
  call_wall NUMERIC(10,2),
  put_wall NUMERIC(10,2),
  gex_regime TEXT,
  flip_point NUMERIC(10,2),
  net_gex NUMERIC(15,2),
  oracle_confidence NUMERIC(5,4),
  oracle_win_probability NUMERIC(8,4),
  oracle_advice TEXT,
  oracle_reasoning TEXT,
  oracle_top_factors TEXT,
  oracle_use_gex_walls BOOLEAN DEFAULT FALSE,
  wings_adjusted BOOLEAN DEFAULT FALSE,
  original_put_width NUMERIC(10,2),
  original_call_width NUMERIC(10,2),
  put_order_id TEXT DEFAULT 'PAPER',
  call_order_id TEXT DEFAULT 'PAPER',
  status TEXT NOT NULL DEFAULT 'open',
  open_time TIMESTAMPTZ NOT NULL,
  open_date DATE,
  close_time TIMESTAMPTZ,
  close_price NUMERIC(10,4),
  close_reason TEXT,
  realized_pnl NUMERIC(10,2),
  dte_mode TEXT DEFAULT '2DTE',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ${bot}_signals (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  signal_time TIMESTAMPTZ DEFAULT NOW(),
  spot_price NUMERIC(10,2),
  vix NUMERIC(6,2),
  expected_move NUMERIC(10,2),
  call_wall NUMERIC(10,2),
  put_wall NUMERIC(10,2),
  gex_regime TEXT,
  put_short NUMERIC(10,2),
  put_long NUMERIC(10,2),
  call_short NUMERIC(10,2),
  call_long NUMERIC(10,2),
  total_credit NUMERIC(10,4),
  confidence NUMERIC(5,4),
  was_executed BOOLEAN DEFAULT FALSE,
  skip_reason TEXT,
  reasoning TEXT,
  wings_adjusted BOOLEAN DEFAULT FALSE,
  dte_mode TEXT DEFAULT '2DTE'
);
CREATE TABLE IF NOT EXISTS ${bot}_equity_snapshots (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  snapshot_time TIMESTAMPTZ DEFAULT NOW(),
  balance NUMERIC(12,2) NOT NULL,
  unrealized_pnl NUMERIC(12,2) DEFAULT 0,
  realized_pnl NUMERIC(12,2) DEFAULT 0,
  open_positions INT DEFAULT 0,
  note TEXT,
  dte_mode TEXT DEFAULT '2DTE',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ${bot}_logs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  log_time TIMESTAMPTZ DEFAULT NOW(),
  level TEXT,
  message TEXT,
  details TEXT,
  dte_mode TEXT DEFAULT '2DTE'
);
CREATE TABLE IF NOT EXISTS ${bot}_daily_perf (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  trade_date DATE NOT NULL UNIQUE,
  trades_executed INT DEFAULT 0,
  positions_closed INT DEFAULT 0,
  realized_pnl NUMERIC(10,2) DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ${bot}_pdt_log (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  trade_date DATE NOT NULL,
  symbol TEXT NOT NULL,
  position_id TEXT NOT NULL,
  opened_at TIMESTAMPTZ NOT NULL,
  closed_at TIMESTAMPTZ,
  is_day_trade BOOLEAN DEFAULT FALSE,
  contracts INT NOT NULL,
  entry_credit NUMERIC(10,4),
  exit_cost NUMERIC(10,4),
  pnl NUMERIC(10,2),
  close_reason TEXT,
  dte_mode TEXT DEFAULT '2DTE',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ${bot}_config (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dte_mode TEXT NOT NULL UNIQUE,
  sd_multiplier NUMERIC(5,2) DEFAULT 1.2,
  spread_width NUMERIC(5,2) DEFAULT 5.0,
  min_credit NUMERIC(5,4) DEFAULT 0.05,
  profit_target_pct NUMERIC(5,2) DEFAULT 30.0,
  stop_loss_pct NUMERIC(5,2) DEFAULT 100.0,
  vix_skip NUMERIC(5,2) DEFAULT 32.0,
  max_contracts INT DEFAULT 10,
  max_trades_per_day INT DEFAULT 1,
  buying_power_usage_pct NUMERIC(5,4) DEFAULT 0.85,
  risk_per_trade_pct NUMERIC(5,4) DEFAULT 0.15,
  min_win_probability NUMERIC(5,4) DEFAULT 0.42,
  entry_start TEXT DEFAULT '08:30',
  entry_end TEXT DEFAULT '14:00',
  eod_cutoff_et TEXT DEFAULT '15:45',
  pdt_max_day_trades INT DEFAULT 3,
  starting_capital NUMERIC(12,2) DEFAULT 10000.0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
`).join('')

/**
 * Ensure all tables exist. Runs once per server cold start.
 * Uses CREATE TABLE IF NOT EXISTS so it's safe to call repeatedly.
 */
async function ensureTables(): Promise<void> {
  if (tablesReady) return
  const client = await getPool().connect()
  try {
    await client.query(INIT_DDL)
    // Seed paper accounts if empty
    for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']] as const) {
      const res = await client.query(
        `SELECT id FROM ${bot}_paper_account WHERE is_active = TRUE AND dte_mode = $1 LIMIT 1`,
        [dte],
      )
      if (res.rows.length === 0) {
        await client.query(
          `INSERT INTO ${bot}_paper_account
            (starting_capital, current_balance, cumulative_pnl, buying_power, high_water_mark, dte_mode)
           VALUES (10000, 10000, 0, 10000, 10000, $1)`,
          [dte],
        )
      }
    }
    tablesReady = true
  } catch (err) {
    console.error('ensureTables failed:', err)
  } finally {
    client.release()
  }
}

/**
 * Execute a SQL query and return rows as objects.
 * Auto-creates tables on first call.
 */
export async function query<T = Record<string, any>>(
  sql: string,
  params?: any[],
): Promise<T[]> {
  await ensureTables()
  const client = await getPool().connect()
  try {
    const result = await client.query(sql, params)
    return result.rows as T[]
  } finally {
    client.release()
  }
}

/** Parse a value as a float, defaulting to 0. */
export function num(val: any): number {
  if (val == null || val === '') return 0
  const n = parseFloat(val)
  return isNaN(n) ? 0 : n
}

/** Parse a value as an int, defaulting to 0. */
export function int(val: any): number {
  if (val == null || val === '') return 0
  const n = parseInt(val, 10)
  return isNaN(n) ? 0 : n
}

/** Validate bot name parameter — only flame or spark allowed. */
export function validateBot(bot: string): string | null {
  const b = bot.toLowerCase()
  if (b !== 'flame' && b !== 'spark') return null
  return b
}
