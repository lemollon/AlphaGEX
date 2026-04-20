import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/** Default config values (mirrors models.py factory functions). */
const DEFAULTS: Record<string, Record<string, number | string>> = {
  flame: {
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.05,
    profit_target_pct: 30.0, stop_loss_pct: 200.0, vix_skip: 32.0,
    max_contracts: 0, max_trades_per_day: 1, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '15:45',
    pdt_max_day_trades: 4, starting_capital: 10000.0,
  },
  spark: {
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.05,
    profit_target_pct: 30.0, stop_loss_pct: 200.0, vix_skip: 32.0,
    max_contracts: 0, max_trades_per_day: 1, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '15:45',
    pdt_max_day_trades: 4, starting_capital: 10000.0,
  },
  inferno: {
    sd_multiplier: 1.0, spread_width: 5.0, min_credit: 0.05,
    profit_target_pct: 50.0, stop_loss_pct: 300.0, vix_skip: 32.0,
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
 * Normalize the account_type query param. Paper/sandbox are aliased to
 * 'sandbox' (the legacy/default scope); anything labelled 'live' or
 * 'production' is routed to the 'production' scope. Invalid values fall
 * back to 'sandbox' so a mistyped param never silently rewrites a Live row.
 */
function resolveAccountType(param: string | null): 'sandbox' | 'production' {
  if (!param) return 'sandbox'
  const v = param.toLowerCase()
  if (v === 'production' || v === 'live') return 'production'
  return 'sandbox'
}

/**
 * GET /api/[bot]/config?account_type=sandbox|production
 *
 * Returns merged config: DB overrides on top of factory defaults, scoped to
 * the requested account_type. Paper and Live are siloed — edits to one do
 * not affect the other. Default scope is 'sandbox' (paper).
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot) ?? '0DTE'
  const accountType = resolveAccountType(req.nextUrl.searchParams.get('account_type'))

  try {
    // Prefer an exact (dte, account_type) match; fall back to the legacy
    // unscoped row (where account_type is NULL or 'sandbox') so deployments
    // that haven't migrated yet still return something coherent.
    const rows = await dbQuery(
      `SELECT sd_multiplier, spread_width, min_credit, profit_target_pct,
              stop_loss_pct, vix_skip, max_contracts, max_trades_per_day,
              buying_power_usage_pct, risk_per_trade_pct, min_win_probability,
              entry_start, entry_end, eod_cutoff_et, pdt_max_day_trades,
              starting_capital, COALESCE(account_type, 'sandbox') AS account_type
       FROM ${botTable(bot, 'config')}
       WHERE dte_mode = '${escapeSql(dte)}'
         AND COALESCE(account_type, 'sandbox') IN ('${escapeSql(accountType)}', 'sandbox')
       ORDER BY CASE WHEN COALESCE(account_type, 'sandbox') = '${escapeSql(accountType)}' THEN 0 ELSE 1 END
       LIMIT 1`,
    )

    const defaults = DEFAULTS[bot] ?? DEFAULTS.inferno
    if (rows.length === 0) {
      return NextResponse.json({ ...defaults, account_type: accountType, source: 'defaults' })
    }

    const row = rows[0]
    const merged: Record<string, number | string> = { ...defaults }
    for (let i = 0; i < ALL_FIELDS.length; i++) {
      const key = ALL_FIELDS[i]
      if (row[key] != null) {
        if (INT_FIELDS.indexOf(key) >= 0) merged[key] = int(row[key])
        else if (NUMERIC_FIELDS.indexOf(key) >= 0) merged[key] = num(row[key])
        else merged[key] = row[key]
      }
    }
    merged.account_type = accountType
    // Mark whether the row we matched was an exact (account_type) hit or a
    // fallback from the sandbox row. Operators debugging bleed-over can use
    // this to confirm they're editing the intended scope.
    merged.source = row.account_type === accountType ? 'database' : 'database_fallback_sandbox'
    return NextResponse.json(merged)
  } catch {
    // Config table might not exist yet — return defaults
    return NextResponse.json({ ...DEFAULTS[bot], account_type: accountType, source: 'defaults' })
  }
}

/**
 * PUT /api/[bot]/config?account_type=sandbox|production
 *
 * Save config overrides for the requested account_type scope only. Paper
 * and Live are siloed: a PUT to account_type=production will NEVER modify
 * the sandbox row and vice versa.
 *
 * Body: { "sd_multiplier": 1.5, "profit_target_pct": 40, ... }
 */
export async function PUT(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot) ?? '0DTE'
  const accountType = resolveAccountType(req.nextUrl.searchParams.get('account_type'))

  try {
    const body = await req.json()

    // Filter to only allowed fields
    const filtered: Record<string, number | string> = {}
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
    const ptPct = filtered.profit_target_pct as number | undefined
    if (ptPct != null && (ptPct <= 0 || ptPct >= 100)) {
      return NextResponse.json({ error: 'profit_target_pct must be 0-100' }, { status: 422 })
    }
    const sw = filtered.spread_width as number | undefined
    if (sw != null && sw <= 0) {
      return NextResponse.json({ error: 'spread_width must be positive' }, { status: 422 })
    }
    // Prevent setting max_trades_per_day=0 for FLAME/SPARK (0 means unlimited, only valid for INFERNO)
    const mtpd = filtered.max_trades_per_day as number | undefined
    if (mtpd != null && mtpd === 0 && bot !== 'inferno') {
      return NextResponse.json(
        { error: 'max_trades_per_day cannot be 0 for FLAME/SPARK (use 1+). Only INFERNO allows unlimited (0).' },
        { status: 422 },
      )
    }

    // Build INSERT ... ON CONFLICT upsert scoped to (dte_mode, account_type).
    // This depends on the new composite unique constraint added in db.ts
    // bootstrap — a deploy against a pre-migration DB will fall back to the
    // single-column constraint and raise here, which is caught below.
    const keys = Object.keys(filtered)
    const insertCols = ['dte_mode', 'account_type', ...keys].join(', ')
    const insertVals = [
      `'${escapeSql(dte)}'`,
      `'${escapeSql(accountType)}'`,
      ...keys.map(k =>
        typeof filtered[k] === 'string' ? `'${escapeSql(filtered[k] as string)}'` : String(filtered[k]),
      ),
    ].join(', ')
    const updateSet = keys.map(k =>
      typeof filtered[k] === 'string'
        ? `${k} = '${escapeSql(filtered[k] as string)}'`
        : `${k} = ${filtered[k]}`
    ).concat(['updated_at = NOW()']).join(', ')

    const table = botTable(bot, 'config')
    await dbExecute(
      `INSERT INTO ${table} (${insertCols}) VALUES (${insertVals})
       ON CONFLICT (dte_mode, account_type) DO UPDATE SET ${updateSet}`,
    )

    // Log (scoped so the audit trail records which silo was touched)
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ('CONFIG', 'Config updated [${escapeSql(accountType)}]: ${escapeSql(keys.join(', '))}',
               '${escapeSql(JSON.stringify({ ...filtered, account_type: accountType, source: 'config_api' }))}',
               '${escapeSql(dte)}')`,
    )

    return NextResponse.json({
      success: true,
      account_type: accountType,
      updated_fields: keys,
      values: filtered,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
