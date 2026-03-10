import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot, dteMode } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

/** Escape a string for safe SQL interpolation. */
function esc(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/'/g, "''")
}

/** Default config values (mirrors models.py factory functions). */
const DEFAULTS: Record<string, Record<string, any>> = {
  flame: {
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.05,
    profit_target_pct: 30.0, stop_loss_pct: 100.0, vix_skip: 32.0,
    max_contracts: 10, max_trades_per_day: 1, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '15:45',
    pdt_max_day_trades: 3, starting_capital: 10000.0,
  },
  spark: {
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.05,
    profit_target_pct: 30.0, stop_loss_pct: 100.0, vix_skip: 32.0,
    max_contracts: 10, max_trades_per_day: 1, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '15:45',
    pdt_max_day_trades: 3, starting_capital: 10000.0,
  },
  inferno: {
    sd_multiplier: 1.0, spread_width: 5.0, min_credit: 0.05,
    profit_target_pct: 50.0, stop_loss_pct: 200.0, vix_skip: 32.0,
    max_contracts: 0, max_trades_per_day: 0, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:30', eod_cutoff_et: '15:45',
    pdt_max_day_trades: 0, starting_capital: 10000.0,
  },
}

const NUMERIC_FIELDS = [
  'sd_multiplier', 'spread_width', 'min_credit', 'profit_target_pct',
  'stop_loss_pct', 'vix_skip', 'buying_power_usage_pct', 'risk_per_trade_pct',
  'min_win_probability', 'starting_capital',
]
const INT_FIELDS = ['max_contracts', 'max_trades_per_day', 'pdt_max_day_trades']
const STRING_FIELDS = ['entry_start', 'entry_end', 'eod_cutoff_et']
const ALL_FIELDS = NUMERIC_FIELDS.concat(INT_FIELDS, STRING_FIELDS)

/**
 * GET /api/[bot]/config
 *
 * Returns merged config: DB overrides on top of factory defaults.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)

  try {
    const rows = await query(
      `SELECT sd_multiplier, spread_width, min_credit, profit_target_pct,
              stop_loss_pct, vix_skip, max_contracts, max_trades_per_day,
              buying_power_usage_pct, risk_per_trade_pct, min_win_probability,
              entry_start, entry_end, eod_cutoff_et, pdt_max_day_trades,
              starting_capital
       FROM ${botTable(bot, 'config')}
       WHERE dte_mode = '${dte}' LIMIT 1`,
    )

    const defaults = DEFAULTS[bot]
    if (rows.length === 0) {
      return NextResponse.json({ ...defaults, source: 'defaults' })
    }

    const row = rows[0]
    const merged: Record<string, any> = { ...defaults }
    for (const key of ALL_FIELDS) {
      if (row[key] != null) {
        if (INT_FIELDS.includes(key)) merged[key] = int(row[key])
        else if (NUMERIC_FIELDS.includes(key)) merged[key] = num(row[key])
        else merged[key] = row[key]
      }
    }
    merged.source = 'database'
    return NextResponse.json(merged)
  } catch {
    // Config table might not exist yet — return defaults
    return NextResponse.json({ ...DEFAULTS[bot], source: 'defaults' })
  }
}

/**
 * PUT /api/[bot]/config
 *
 * Save config overrides. Only allowed fields are persisted.
 * Uses MERGE INTO for Databricks upsert.
 *
 * Body: { "sd_multiplier": 1.5, "profit_target_pct": 40, ... }
 */
export async function PUT(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)

  try {
    const body = await req.json()

    // Filter to only allowed fields
    const filtered: Record<string, any> = {}
    for (const [key, val] of Object.entries(body)) {
      if (!ALL_FIELDS.includes(key)) continue
      if (INT_FIELDS.includes(key)) {
        const v = parseInt(String(val), 10)
        if (isNaN(v) || v < 0) continue
        filtered[key] = v
      } else if (NUMERIC_FIELDS.includes(key)) {
        const v = parseFloat(String(val))
        if (isNaN(v) || v < 0) continue
        filtered[key] = v
      } else {
        filtered[key] = String(val)
      }
    }

    if (Object.keys(filtered).length === 0) {
      return NextResponse.json(
        { error: 'No valid config fields provided' },
        { status: 400 },
      )
    }

    // Validate ranges
    if (filtered.profit_target_pct != null && (filtered.profit_target_pct <= 0 || filtered.profit_target_pct >= 100)) {
      return NextResponse.json({ error: 'profit_target_pct must be 0-100' }, { status: 422 })
    }
    if (filtered.spread_width != null && filtered.spread_width <= 0) {
      return NextResponse.json({ error: 'spread_width must be positive' }, { status: 422 })
    }

    // Build MERGE INTO for Databricks upsert
    const allCols = ['dte_mode', ...Object.keys(filtered)]
    const sourceValues = allCols.map(col => {
      if (col === 'dte_mode') return `'${dte}' AS dte_mode`
      const val = filtered[col]
      if (STRING_FIELDS.includes(col)) return `'${esc(String(val))}' AS ${col}`
      return `${val} AS ${col}`
    })

    const updateSet = Object.keys(filtered)
      .map(k => `target.${k} = source.${k}`)
      .concat(['target.updated_at = CURRENT_TIMESTAMP()'])
      .join(', ')

    const insertCols = allCols.concat(['created_at', 'updated_at']).join(', ')
    const insertVals = allCols.map(c => `source.${c}`)
      .concat(['CURRENT_TIMESTAMP()', 'CURRENT_TIMESTAMP()'])
      .join(', ')

    await query(
      `MERGE INTO ${botTable(bot, 'config')} AS target
       USING (SELECT ${sourceValues.join(', ')}) AS source
       ON target.dte_mode = source.dte_mode
       WHEN MATCHED THEN UPDATE SET ${updateSet}
       WHEN NOT MATCHED THEN INSERT (${insertCols}) VALUES (${insertVals})`,
    )

    // Log the config change
    const msg = esc(`Config updated: ${Object.keys(filtered).join(', ')}`)
    const details = esc(JSON.stringify({ ...filtered, source: 'config_api' }))
    await query(
      `INSERT INTO ${botTable(bot, 'logs')} (log_time, level, message, details, dte_mode)
       VALUES (CURRENT_TIMESTAMP(), 'CONFIG', '${msg}', '${details}', '${dte}')`,
    )

    return NextResponse.json({
      success: true,
      updated_fields: Object.keys(filtered),
      values: filtered,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
