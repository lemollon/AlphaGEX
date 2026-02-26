import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot } from '@/lib/db'

export const dynamic = 'force-dynamic'

/** Default config values (mirrors models.py factory functions). */
const DEFAULTS: Record<string, Record<string, any>> = {
  flame: {
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.05,
    profit_target_pct: 30.0, stop_loss_pct: 100.0, vix_skip: 32.0,
    max_contracts: 10, max_trades_per_day: 1, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '15:45',
    pdt_max_day_trades: 3, starting_capital: 5000.0,
  },
  spark: {
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.05,
    profit_target_pct: 30.0, stop_loss_pct: 100.0, vix_skip: 32.0,
    max_contracts: 10, max_trades_per_day: 1, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '15:45',
    pdt_max_day_trades: 3, starting_capital: 5000.0,
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

  const dte = bot === 'flame' ? '2DTE' : '1DTE'

  try {
    const rows = await query(
      `SELECT sd_multiplier, spread_width, min_credit, profit_target_pct,
              stop_loss_pct, vix_skip, max_contracts, max_trades_per_day,
              buying_power_usage_pct, risk_per_trade_pct, min_win_probability,
              entry_start, entry_end, eod_cutoff_et, pdt_max_day_trades,
              starting_capital
       FROM ${botTable(bot, 'config')}
       WHERE dte_mode = $1 LIMIT 1`,
      [dte],
    )

    const defaults = DEFAULTS[bot]
    if (rows.length === 0) {
      return NextResponse.json({ ...defaults, source: 'defaults' })
    }

    const row = rows[0]
    const merged: Record<string, any> = { ...defaults }
    for (let i = 0; i < ALL_FIELDS.length; i++) {
      const key = ALL_FIELDS[i]
      if (row[key] != null) {
        if (INT_FIELDS.indexOf(key) >= 0) merged[key] = int(row[key])
        else if (NUMERIC_FIELDS.indexOf(key) >= 0) merged[key] = num(row[key])
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
 *
 * Body: { "sd_multiplier": 1.5, "profit_target_pct": 40, ... }
 */
export async function PUT(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : '1DTE'

  try {
    const body = await req.json()

    // Filter to only allowed fields
    const filtered: Record<string, any> = {}
    for (const [key, val] of Object.entries(body)) {
      if (ALL_FIELDS.indexOf(key) < 0) continue
      if (INT_FIELDS.indexOf(key) >= 0) {
        const v = parseInt(String(val), 10)
        if (isNaN(v) || v < 0) continue
        filtered[key] = v
      } else if (NUMERIC_FIELDS.indexOf(key) >= 0) {
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

    // Build upsert
    const columns = ['dte_mode'].concat(Object.keys(filtered))
    const values = ([dte] as any[]).concat(Object.values(filtered))
    const placeholders = values.map((_: any, i: number) => `$${i + 1}`).join(', ')
    const colNames = columns.join(', ')
    const updateParts = Object.keys(filtered).map(k => `${k} = EXCLUDED.${k}`)
    updateParts.push('updated_at = NOW()')

    await query(
      `INSERT INTO ${botTable(bot, 'config')} (${colNames})
       VALUES (${placeholders})
       ON CONFLICT (dte_mode) DO UPDATE SET ${updateParts.join(', ')}`,
      values,
    )

    // Log
    await query(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'CONFIG',
        `Config updated: ${Object.keys(filtered).join(', ')}`,
        JSON.stringify({ ...filtered, source: 'config_api' }),
        dte,
      ],
    )

    return NextResponse.json({
      success: true,
      updated_fields: Object.keys(filtered),
      values: filtered,
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
