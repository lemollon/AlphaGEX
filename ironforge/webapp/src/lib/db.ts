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

// Map Iron Forge bot names to database table prefixes.
// IronForge has its own database — tables use flame_/spark_ prefixes.
const DB_PREFIX: Record<string, string> = {
  flame: 'flame',
  spark: 'spark',
  inferno: 'inferno',
}

/** Map display names to heartbeat bot_name values in bot_heartbeats table. */
const HEARTBEAT_MAP: Record<string, string> = {
  flame: 'FLAME',
  spark: 'SPARK',
  inferno: 'INFERNO',
}

/**
 * SQL expression for "today" in Central Time.
 * PostgreSQL on Render runs UTC — CURRENT_DATE returns the UTC date, which
 * is wrong after 7 PM CT (midnight UTC).  This converts the server timestamp
 * to America/Chicago before extracting the date.
 */
export const CT_TODAY = "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date"

/** Bot-specific table name: {prefix}_{suffix}. */
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
  if (bot === 'inferno') return '0DTE'
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
` + `
CREATE TABLE IF NOT EXISTS ironforge_accounts (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  person TEXT NOT NULL,
  account_id TEXT NOT NULL,
  api_key TEXT NOT NULL,
  bot TEXT NOT NULL,
  type TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
` + `
CREATE TABLE IF NOT EXISTS ironforge_person_aliases (
  person TEXT NOT NULL PRIMARY KEY,
  alias TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
` + `
CREATE TABLE IF NOT EXISTS ironforge_pdt_config (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bot_name TEXT NOT NULL UNIQUE,
  pdt_enabled BOOLEAN DEFAULT TRUE,
  day_trade_count INT DEFAULT 0,
  max_day_trades INT DEFAULT 4,
  window_days INT DEFAULT 5,
  max_trades_per_day INT DEFAULT 1,
  last_reset_at TIMESTAMPTZ,
  last_reset_by TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ironforge_production_pause (
  bot_name TEXT PRIMARY KEY,
  paused BOOLEAN NOT NULL DEFAULT FALSE,
  paused_at TIMESTAMPTZ,
  paused_by TEXT,
  paused_reason TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
` + ['flame', 'spark', 'inferno'].map(bot => `
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
  kelly_raw NUMERIC(8,4),
  kelly_half NUMERIC(8,4),
  kelly_size_pct NUMERIC(6,4),
  sandbox_order_id TEXT,
  sandbox_close_order_id TEXT,
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
  person TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ${bot}_pdt_config (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bot_name TEXT NOT NULL,
  pdt_enabled BOOLEAN DEFAULT TRUE,
  day_trade_count INT DEFAULT 0,
  max_day_trades INT DEFAULT 4,
  window_days INT DEFAULT 5,
  max_trades_per_day INT DEFAULT 1,
  last_reset_at TIMESTAMPTZ,
  last_reset_by TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ${bot}_pdt_audit_log (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bot_name TEXT NOT NULL,
  action TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  reason TEXT,
  performed_by TEXT DEFAULT 'user',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ${bot}_pending_orders (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  position_id TEXT NOT NULL,
  ticker TEXT NOT NULL,
  expiration DATE NOT NULL,
  put_short_strike NUMERIC(10,2),
  put_long_strike NUMERIC(10,2),
  call_short_strike NUMERIC(10,2),
  call_long_strike NUMERIC(10,2),
  contracts INT NOT NULL,
  total_credit NUMERIC(10,4),
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  dte_mode TEXT
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
  max_contracts INT DEFAULT 0,
  max_trades_per_day INT DEFAULT 1,
  buying_power_usage_pct NUMERIC(5,4) DEFAULT 0.85,
  risk_per_trade_pct NUMERIC(5,4) DEFAULT 0.15,
  min_win_probability NUMERIC(5,4) DEFAULT 0.42,
  entry_start TEXT DEFAULT '08:30',
  entry_end TEXT DEFAULT '14:00',
  eod_cutoff_et TEXT DEFAULT '15:45',
  pdt_max_day_trades INT DEFAULT 4,
  starting_capital NUMERIC(12,2) DEFAULT 10000.0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
`).join('') + `
CREATE TABLE IF NOT EXISTS production_equity_snapshots (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  snapshot_time TIMESTAMPTZ DEFAULT NOW(),
  person TEXT NOT NULL,
  account_id TEXT,
  total_equity NUMERIC(12,2),
  option_buying_power NUMERIC(12,2),
  day_pnl NUMERIC(12,2),
  unrealized_pnl NUMERIC(12,2),
  open_positions INT DEFAULT 0,
  note TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
`

/**
 * Ensure all tables exist. Runs once per server cold start.
 * Uses CREATE TABLE IF NOT EXISTS so it's safe to call repeatedly.
 */
async function ensureTables(): Promise<void> {
  if (tablesReady) return
  const client = await getPool().connect()
  try {
    await client.query(INIT_DDL)

    // Add missing columns to existing positions tables (safe to run repeatedly)
    for (const bot of ['flame', 'spark', 'inferno']) {
      for (const col of ['sandbox_order_id TEXT', 'sandbox_close_order_id TEXT', 'person TEXT',
                          'kelly_raw NUMERIC(8,4)', 'kelly_half NUMERIC(8,4)', 'kelly_size_pct NUMERIC(6,4)']) {
        try {
          await client.query(`ALTER TABLE ${bot}_positions ADD COLUMN IF NOT EXISTS ${col}`)
        } catch { /* column already exists or table doesn't exist yet */ }
      }
      // Add person column to equity_snapshots, daily_perf, logs, signals, and pdt_log for per-person filtering
      for (const tbl of [`${bot}_equity_snapshots`, `${bot}_daily_perf`, `${bot}_logs`, `${bot}_signals`, `${bot}_pdt_log`]) {
        try {
          await client.query(`ALTER TABLE ${tbl} ADD COLUMN IF NOT EXISTS person TEXT`)
        } catch { /* column already exists or table doesn't exist yet */ }
      }
      // Add account_type column for production vs sandbox position tracking
      for (const tbl of [`${bot}_positions`, `${bot}_paper_account`, `${bot}_equity_snapshots`, `${bot}_daily_perf`, `${bot}_pdt_log`, `${bot}_signals`, `${bot}_logs`]) {
        try {
          await client.query(`ALTER TABLE ${tbl} ADD COLUMN IF NOT EXISTS account_type TEXT DEFAULT 'sandbox'`)
        } catch { /* column already exists or table doesn't exist yet */ }
      }
      // Add person column to paper_account for per-person production tracking
      try {
        await client.query(`ALTER TABLE ${bot}_paper_account ADD COLUMN IF NOT EXISTS person TEXT`)
      } catch { /* column already exists or table doesn't exist yet */ }
      // Backfill NULL person values to 'User' so existing data matches person filter
      for (const tbl of [`${bot}_positions`, `${bot}_equity_snapshots`, `${bot}_daily_perf`]) {
        try {
          await client.query(`UPDATE ${tbl} SET person = 'User' WHERE person IS NULL`)
        } catch { /* table may not exist yet */ }
      }
      // Backfill NULL account_type to 'sandbox' for existing rows
      for (const tbl of [`${bot}_positions`, `${bot}_paper_account`, `${bot}_equity_snapshots`, `${bot}_daily_perf`, `${bot}_pdt_log`, `${bot}_signals`]) {
        try {
          await client.query(`UPDATE ${tbl} SET account_type = 'sandbox' WHERE account_type IS NULL`)
        } catch { /* table may not exist yet */ }
      }

      // Silo {bot}_config by account_type so Paper and Live configs don't bleed
      // into each other. Add the column if missing, backfill, swap the unique
      // constraint from (dte_mode) to (dte_mode, account_type), and seed the
      // Live row for the production bot so Live edits have somewhere to land.
      try {
        await client.query(`ALTER TABLE ${bot}_config ADD COLUMN IF NOT EXISTS account_type TEXT DEFAULT 'sandbox'`)
        await client.query(`UPDATE ${bot}_config SET account_type = 'sandbox' WHERE account_type IS NULL`)
        // Drop the legacy single-column unique constraint if present.
        // Name is Postgres's auto-generated default: '{bot}_config_dte_mode_key'.
        await client.query(`ALTER TABLE ${bot}_config DROP CONSTRAINT IF EXISTS ${bot}_config_dte_mode_key`)
        // Idempotent add of the composite unique constraint.
        try {
          await client.query(
            `ALTER TABLE ${bot}_config
             ADD CONSTRAINT ${bot}_config_dte_mode_account_type_key UNIQUE (dte_mode, account_type)`,
          )
        } catch { /* constraint may already exist on re-run */ }
      } catch { /* table may not exist yet */ }
    }

    // SPARK-only: hypothetical "what if we had held to 2:59 PM" P&L tracking.
    // Three columns on spark_positions so historical analysis can compare the
    // bot's actual PT-tier exit vs the late-day-hold counterfactual. NULL is
    // expected for any trade older than Tradier's ~40-day option timesales
    // window. Added to SPARK only because FLAME (2DTE) and INFERNO (0DTE) have
    // different exit models — the comparison is only meaningful for the
    // same-day-exit 1DTE bot.
    for (const col of [
      'hypothetical_eod_pnl NUMERIC(12,2)',
      'hypothetical_eod_spot NUMERIC(10,4)',
      'hypothetical_eod_computed_at TIMESTAMPTZ',
    ]) {
      try {
        await client.query(`ALTER TABLE spark_positions ADD COLUMN IF NOT EXISTS ${col}`)
      } catch { /* column already exists or table doesn't exist yet */ }
    }

    // Add missing columns to ironforge_accounts (needed for production trading)
    // capital_pct controls what % of account equity is used for trading
    // pdt_enabled controls per-account PDT enforcement
    for (const col of ['capital_pct INT DEFAULT 100', 'pdt_enabled BOOLEAN DEFAULT TRUE']) {
      try {
        await client.query(`ALTER TABLE ironforge_accounts ADD COLUMN IF NOT EXISTS ${col}`)
      } catch { /* column already exists */ }
    }

    // Migrate daily_perf UNIQUE constraint from (trade_date) to (trade_date, COALESCE(person, ''))
    // Needed so sandbox and production can both have entries on the same date.
    for (const bot of ['flame', 'spark', 'inferno']) {
      try {
        // Drop old single-column constraint
        await client.query(`ALTER TABLE ${bot}_daily_perf DROP CONSTRAINT IF EXISTS ${bot}_daily_perf_trade_date_key`)
        // Create composite unique index (safe to run repeatedly)
        await client.query(
          `CREATE UNIQUE INDEX IF NOT EXISTS ${bot}_daily_perf_date_person_uniq
           ON ${bot}_daily_perf (trade_date, COALESCE(person, ''))`,
        )
      } catch { /* constraint may already exist or table may not exist */ }
    }

    // Add UNIQUE constraint on ironforge_pdt_config.bot_name (safe to run repeatedly)
    // Prevents duplicate rows from concurrent cold starts. First deduplicate if needed.
    try {
      // Remove duplicate rows keeping only the lowest id per bot_name
      await client.query(`
        DELETE FROM ironforge_pdt_config a
        USING ironforge_pdt_config b
        WHERE a.bot_name = b.bot_name AND a.id > b.id
      `)
      await client.query(`
        CREATE UNIQUE INDEX IF NOT EXISTS ironforge_pdt_config_bot_name_uniq
        ON ironforge_pdt_config (bot_name)
      `)
    } catch { /* constraint may already exist */ }

    // Dedup paper accounts — race condition during concurrent ensureTables() can create duplicates.
    // Keep only the highest-ID active sandbox account per bot/dte; deactivate the rest.
    for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE'], ['inferno', '0DTE']] as const) {
      try {
        await client.query(
          `UPDATE ${bot}_paper_account SET is_active = FALSE
           WHERE is_active = TRUE AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'
             AND id < (SELECT MAX(id) FROM ${bot}_paper_account
                       WHERE is_active = TRUE AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox')`,
          [dte],
        )
      } catch { /* table may not exist yet on first run */ }
    }

    // Seed paper accounts if empty — atomic INSERT ... WHERE NOT EXISTS to prevent race condition duplicates
    for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE'], ['inferno', '0DTE']] as const) {
      await client.query(
        `INSERT INTO ${bot}_paper_account
          (starting_capital, current_balance, cumulative_pnl, buying_power, high_water_mark, dte_mode)
         SELECT 10000, 10000, 0, 10000, 10000, $1
         WHERE NOT EXISTS (
           SELECT 1 FROM ${bot}_paper_account WHERE is_active = TRUE AND dte_mode = $1
         )`,
        [dte],
      )
    }
    // Seed production paper_account for SPARK on each configured production account.
    // SPARK is the sole real-money production bot; we do NOT re-seed a production
    // row for FLAME/INFERNO (they're paper-only now). Any pre-existing
    // flame_paper_account production rows are left in place for historical P&L
    // continuity but will never be written to by the scanner going forward.
    try {
      const prodAccounts = await client.query(
        `SELECT person, capital_pct FROM ironforge_accounts
         WHERE type = 'production' AND is_active = TRUE`,
      )
      for (const row of prodAccounts.rows) {
        const person = row.person
        if (!person) continue
        const pct = parseInt(row.capital_pct) || 15
        const startCap = Math.round(10000 * pct / 100 * 100) / 100
        await client.query(
          `INSERT INTO spark_paper_account
            (starting_capital, current_balance, cumulative_pnl, buying_power, high_water_mark, max_drawdown,
             is_active, dte_mode, account_type, person)
           SELECT $1, $1, 0, $1, $1, 0, TRUE, '1DTE', 'production', $2
           WHERE NOT EXISTS (
             SELECT 1 FROM spark_paper_account
             WHERE account_type = 'production' AND person = $2
           )`,
          [startCap, person],
        )
      }
    } catch (err) {
      console.warn('  SPARK production paper_account seed failed (non-fatal):', err)
    }

    // Normalize ironforge_accounts.bot on production accounts to own SPARK.
    // After the FLAME→SPARK cutover, any leftover FLAME membership must be
    // removed so getAccountsForBotAsync('flame') no longer returns production
    // persons (the tradier.ts safety gate is a second line of defense, not
    // the first). SPARK is added if missing.
    try {
      const prodAccts = await client.query(
        `SELECT id, person, bot FROM ironforge_accounts
         WHERE type = 'production' AND is_active = TRUE`,
      )
      for (const acct of prodAccts.rows) {
        const currentBot = acct.bot || ''
        const parts = currentBot.split(',').map((b: string) => b.trim()).filter(Boolean)
        const dedup = Array.from(new Set(parts))
        const filtered = dedup.filter((b) => b !== 'FLAME')
        if (!filtered.includes('SPARK')) filtered.unshift('SPARK')
        // Canonical order: SPARK first (production owner), then INFERNO if present.
        const ordered = ['SPARK', 'INFERNO'].filter((b) => filtered.includes(b))
        const newBot = ordered.join(',')
        if (newBot && newBot !== currentBot) {
          await client.query(
            `UPDATE ironforge_accounts SET bot = $1, updated_at = NOW() WHERE id = $2`,
            [newBot, acct.id],
          )
          console.log(`  Rewrote production bot for ${acct.person}: '${currentBot}' → '${newBot}'`)
        }
      }
    } catch (err) {
      console.warn('  Production bot column normalization failed (non-fatal):', err)
    }

    // Seed shared ironforge_pdt_config if empty
    for (const [botName, maxDT, maxPerDay] of [
      ['FLAME', 3, 1],
      ['SPARK', 3, 1],
      ['INFERNO', 0, 0],
    ] as const) {
      const sharedPdtRes = await client.query(
        `SELECT id FROM ironforge_pdt_config WHERE bot_name = $1 LIMIT 1`,
        [botName],
      )
      if (sharedPdtRes.rows.length === 0) {
        await client.query(
          `INSERT INTO ironforge_pdt_config (bot_name, pdt_enabled, day_trade_count, max_day_trades, window_days, max_trades_per_day)
           VALUES ($1, $2, 0, $3, 5, $4)`,
          [botName, maxDT > 0, maxDT, maxPerDay],
        )
      }
    }

    // Seed per-bot PDT config if empty
    // INFERNO (0DTE) has PDT disabled (max_day_trades=0) and unlimited trades per day
    for (const [bot, dte, maxDT, maxPerDay] of [
      ['flame', '2DTE', 3, 1],
      ['spark', '1DTE', 3, 1],
      ['inferno', '0DTE', 0, 0],  // 0 = disabled/unlimited
    ] as const) {
      const pdtRes = await client.query(
        `SELECT id FROM ${bot}_pdt_config WHERE bot_name = $1 LIMIT 1`,
        [bot.toUpperCase()],
      )
      if (pdtRes.rows.length === 0) {
        await client.query(
          `INSERT INTO ${bot}_pdt_config (bot_name, pdt_enabled, day_trade_count, max_day_trades, window_days, max_trades_per_day)
           VALUES ($1, $2, 0, $3, 5, $4)`,
          [bot.toUpperCase(), maxDT > 0, maxDT, maxPerDay],
        )
      }
    }

    // Ensure PDT max_day_trades = 3 for FLAME/SPARK (broker-safe limit, under FINRA's 4)
    // INFERNO should have 0 (disabled)
    for (const bot of ['flame', 'spark']) {
      try {
        await client.query(
          `UPDATE ${bot}_pdt_config SET max_day_trades = 3 WHERE max_day_trades NOT IN (0, 3)`,
        )
      } catch { /* ignore if table doesn't exist yet */ }
      try {
        await client.query(
          `UPDATE ${bot}_config SET pdt_max_day_trades = 3 WHERE pdt_max_day_trades NOT IN (0, 3)`,
        )
      } catch { /* ignore if table doesn't exist yet */ }
    }
    // FLAME/SPARK: ensure max_trades_per_day is at least 1 (never 0 = unlimited)
    // Fixes stale DB rows where INSERT IF NOT EXISTS didn't update existing 0 values
    for (const [botName, pdtBot] of [['FLAME', 'flame'], ['SPARK', 'spark']] as const) {
      try {
        await client.query(
          `UPDATE ironforge_pdt_config SET max_trades_per_day = 1
           WHERE bot_name = '${botName}' AND max_trades_per_day = 0`,
        )
      } catch { /* ignore if table doesn't exist yet */ }
      try {
        await client.query(
          `UPDATE ${pdtBot}_pdt_config SET max_trades_per_day = 1
           WHERE max_trades_per_day = 0`,
        )
      } catch { /* ignore if table doesn't exist yet */ }
    }

    // Seed a production row in spark_config so Live config edits have somewhere
    // to land without falling back to the sandbox row. Idempotent: only inserts
    // if no production row exists for 1DTE. Clones structural fields from the
    // sandbox row (strategy params, entry windows) so the schema is consistent,
    // but OVERRIDES the risk knobs for the live-money scope:
    //   buying_power_usage_pct = 0.15   (per operator: 15% of live Tradier OBP)
    //   max_contracts         = 0      (unlimited — bp_pct is the real cap)
    try {
      await client.query(
        `INSERT INTO spark_config (dte_mode, account_type, sd_multiplier, spread_width, min_credit,
                                    profit_target_pct, stop_loss_pct, vix_skip, max_contracts,
                                    max_trades_per_day, buying_power_usage_pct, risk_per_trade_pct,
                                    min_win_probability, entry_start, entry_end, eod_cutoff_et,
                                    pdt_max_day_trades, starting_capital)
         SELECT dte_mode, 'production', sd_multiplier, spread_width, min_credit,
                profit_target_pct, stop_loss_pct, vix_skip, 0 AS max_contracts,
                max_trades_per_day, 0.15 AS buying_power_usage_pct, risk_per_trade_pct,
                min_win_probability, entry_start, entry_end, eod_cutoff_et,
                pdt_max_day_trades, starting_capital
         FROM spark_config
         WHERE dte_mode = '1DTE' AND COALESCE(account_type, 'sandbox') = 'sandbox'
           AND NOT EXISTS (
             SELECT 1 FROM spark_config
             WHERE dte_mode = '1DTE' AND account_type = 'production'
           )`,
      )
    } catch { /* table or constraint may not be ready yet */ }

    // Normalize pre-existing production rows to the live-risk knobs. This is
    // a one-time correction for deploys where the production row was seeded
    // before the Commit-A sizing parity change landed (it would have inherited
    // the sandbox bp_pct=0.85, producing the double-dip bug). Safe to re-run:
    // operator edits via PUT /api/spark/config?account_type=production can
    // re-override afterward. Only touches rows that STILL have the buggy 0.85
    // value, so a legitimate operator setting (e.g. 0.20) is preserved.
    try {
      await client.query(
        `UPDATE spark_config
           SET buying_power_usage_pct = 0.15, updated_at = NOW()
         WHERE account_type = 'production'
           AND dte_mode = '1DTE'
           AND buying_power_usage_pct > 0.25`,
      )
      await client.query(
        `UPDATE spark_config
           SET max_contracts = 0, updated_at = NOW()
         WHERE account_type = 'production'
           AND dte_mode = '1DTE'
           AND max_contracts = 2`,
      )
    } catch { /* table or column may not be ready yet */ }

    // INFERNO: ensure PDT is disabled (0DTE bot, no PDT enforcement)
    try {
      await client.query(
        `UPDATE inferno_pdt_config SET max_day_trades = 0, pdt_enabled = FALSE, max_trades_per_day = 0, day_trade_count = 0
         WHERE bot_name = 'INFERNO'`,
      )
    } catch { /* ignore if table doesn't exist yet */ }
    try {
      await client.query(
        `UPDATE inferno_config SET pdt_max_day_trades = 0 WHERE pdt_max_day_trades > 0`,
      )
    } catch { /* ignore if table doesn't exist yet */ }

    // FLAME/SPARK: fix max_contracts from legacy DB default of 10 → 0 (unlimited, sized by BP)
    // The DB schema previously had DEFAULT 10 which gatekept sizing below 85% BP usage.
    // max_contracts=0 means "no ceiling — size by buying power only" (matches scanner DEFAULT_CONFIG).
    for (const bot of ['flame', 'spark']) {
      try {
        await client.query(
          `UPDATE ${bot}_config SET max_contracts = 0 WHERE max_contracts = 10`,
        )
      } catch { /* ignore if table doesn't exist yet */ }
    }

    // PDT cleanup on startup: clear stale is_day_trade flags outside the rolling
    // 6-day window, and reconcile pdt_config.day_trade_count to match reality.
    // Also clear orphan pdt_log entries that have no matching position.
    for (const [bot, dte] of [['flame', '2DTE'], ['spark', '1DTE']] as const) {
      try {
        // 1. Clear is_day_trade flags for entries outside the 6-day rolling window
        //    These should never count — they're expired from the window.
        await client.query(
          `UPDATE ${bot}_pdt_log
           SET is_day_trade = FALSE
           WHERE is_day_trade = TRUE AND dte_mode = $1
             AND trade_date < ${CT_TODAY} - INTERVAL '6 days'`,
          [dte],
        )

        // 2. Clear is_day_trade flags for orphan pdt_log entries that have no
        //    matching closed position (phantom entries from failed trades)
        await client.query(
          `UPDATE ${bot}_pdt_log pl
           SET is_day_trade = FALSE
           WHERE pl.is_day_trade = TRUE AND pl.dte_mode = $1
             AND NOT EXISTS (
               SELECT 1 FROM ${bot}_positions p
               WHERE p.position_id = pl.position_id
                 AND p.status IN ('closed', 'expired')
                 AND p.dte_mode = $1
             )`,
          [dte],
        )

        // 3. Reconcile pdt_config counter to match actual pdt_log count
        //    Only count sandbox trades — production PDT is tracked separately
        const countRes = await client.query(
          `SELECT COUNT(*) as cnt FROM ${bot}_pdt_log
           WHERE is_day_trade = TRUE AND dte_mode = $1
             AND COALESCE(account_type, 'sandbox') = 'sandbox'
             AND trade_date >= ${CT_TODAY} - INTERVAL '6 days'
             AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`,
          [dte],
        )
        const realCount = parseInt(countRes.rows[0]?.cnt ?? '0', 10)
        await client.query(
          `UPDATE ${bot}_pdt_config
           SET day_trade_count = $1, updated_at = NOW()
           WHERE bot_name = $2`,
          [realCount, bot.toUpperCase()],
        )
        console.log(`  PDT cleanup: ${bot.toUpperCase()} day_trade_count → ${realCount}`)
      } catch (err) {
        console.warn(`  PDT cleanup for ${bot} failed:`, err)
      }
    }

    tablesReady = true

    // Start the scan loop in THIS process (same as API routes).
    // Dynamic import avoids circular dependency (scanner imports db).
    import('./scanner')
      .then(m => m.ensureScannerStarted())
      .catch(err => console.error('Scanner start failed:', err))
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

/** Shared table name — for PostgreSQL, just the table name (no catalog/schema prefix). */
export function sharedTable(name: string): string {
  return name
}

/** Escape single quotes for SQL string literals. */
export function escapeSql(val: string): string {
  return val.replace(/'/g, "''")
}

/** Validate bot name parameter — only flame, spark, or inferno allowed. */
export function validateBot(bot: string): string | null {
  const b = bot.toLowerCase()
  if (b !== 'flame' && b !== 'spark' && b !== 'inferno') return null
  return b
}

// ---- Databricks-compatible aliases ----
// These match the export names from the old databricks-sql.ts client
// so API route files only need an import path change.

/** Alias for query() — matches databricks-sql.ts API surface. */
export const dbQuery = query

/**
 * Execute a SQL statement and return the number of affected rows.
 * Matches databricks-sql.ts dbExecute() API surface.
 */
export async function dbExecute(sql: string, params?: any[]): Promise<number> {
  await ensureTables()
  const client = await getPool().connect()
  try {
    const result = await client.query(sql, params)
    return result.rowCount ?? 0
  } finally {
    client.release()
  }
}
