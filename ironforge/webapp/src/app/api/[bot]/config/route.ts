import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/** Default config values (mirrors models.py factory functions). */
const DEFAULTS: Record<string, Record<string, number | string>> = {
  flame: {
    // min_credit mirrors the scanner's DEFAULT_CONFIG floor, not the legacy 0.05.
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.25,
    profit_target_pct: 30.0, stop_loss_pct: 200.0, vix_skip: 32.0,
    max_contracts: 0, max_trades_per_day: 1, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '14:45',
    pdt_max_day_trades: 4, starting_capital: 10000.0,
  },
  spark: {
    // 0.25 = the scanner's code floor (raised from 0.05 on 2026-05-06 to skip
    // un-fillable thin ICs). The DB row still says 0.05 and is clamped up.
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.25,
    profit_target_pct: 30.0, stop_loss_pct: 200.0,
    // 40, not 32 — scanner.ts: `const vixCap = isSparkV2Sizing(bot.name) ? 40 : 32`.
    // Inert fields are now reported from THIS map (the DB value is skipped), so
    // this literal is what the dashboard renders. It must equal the code constant.
    vix_skip: 40.0,
    // SPARK runs the automatic GEX strategy (scanner.ts) and OVERRIDES several of
    // these in code:
    //   · strike width is GEX-adaptive — 1.2 SD positive gamma, 1.5 SD negative
    //   · it SWINGS: no hard stop, so stop_loss_pct is ignored entirely
    //   · sizing is regime-conditional, min(bp_pct, 50% positive / 20% negative
    //     or unknown) — NOT the flat 30% this comment used to claim
    // These values describe the row's shape, never the strategy. /api/{bot}/status
    // carries the authoritative strategy string.
    max_contracts: 0, max_trades_per_day: 1, buying_power_usage_pct: 0.30,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    // 13:00 as of 2026-08-07 — must track DEFAULT_CONFIG.spark.entry_start in
    // scanner.ts, which is the value the bot actually runs. entry_start is an
    // INERT field (the DB row is never read for it), so this literal is the only
    // thing the dashboard renders: leaving it at 08:30 would print a start time
    // the scanner does not use.
    entry_start: '13:00', entry_end: '14:00', eod_cutoff_et: '14:45',
    pdt_max_day_trades: 4, starting_capital: 10000.0,
  },
  // spark2 — SPARK's paper twin. Same strategy code (isSparkV2Sizing +
  // isSparkStrategy both include it), its own ledger and account.
  //
  // Without this entry it fell through to `DEFAULTS.inferno` and the API reported
  // sd 1.0 / stop 1000 / PT 100 / unlimited trades — INFERNO's aggressive 0DTE
  // profile — for a 1DTE bot that actually runs 1.2 SD and one trade a day.
  spark2: {
    sd_multiplier: 1.2, spread_width: 5.0, min_credit: 0.25,
    // 40 — spark2 is on isSparkV2Sizing too, same code constant as SPARK.
    profit_target_pct: 30.0, stop_loss_pct: 200.0, vix_skip: 40.0,
    max_contracts: 0, max_trades_per_day: 1, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '14:45',
    pdt_max_day_trades: 4, starting_capital: 10000.0,
  },
  inferno: {
    sd_multiplier: 1.0, spread_width: 5.0, min_credit: 0.15,
    profit_target_pct: 100.0, stop_loss_pct: 1000.0, vix_skip: 32.0,
    max_contracts: 0, max_trades_per_day: 0, buying_power_usage_pct: 0.85,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:30', eod_cutoff_et: '14:45',
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
 * Columns the SCANNER never reads — writing them changes the row and nothing else.
 *
 * Derived by reading `loadConfigOverrides()` in scanner.ts, which takes exactly two
 * things from the config row: the eight columns in its DB_TO_CFG map, plus `entry_end`
 * and `eod_cutoff_et`, both parsed from "HH:MM" strings. Everything below is absent
 * from all three paths.
 *
 * This route used to accept them silently, so the row could say `vix_skip 35` while the
 * bot skipped at 40 — which is how the config table came to describe a strategy nobody
 * runs. A stored value that governs nothing is worse than no value: it reads as
 * authoritative.
 *
 * If one of these is ever wired up, delete it here in the SAME change.
 */
const INERT_FIELDS: Record<string, string> = {
  vix_skip: 'the VIX ceiling is set in code — 40 for spark/spark2, 32 for the others',
  spread_width: 'wing width is a code constant (wing_width in DEFAULT_CONFIG)',
  risk_per_trade_pct: 'never read; sizing is buying_power_usage_pct against the regime cap',
  min_win_probability: 'never read by the scanner',
  entry_start: 'only entry_end is parsed from the row; the open is a code constant',
  pdt_max_day_trades: 'PDT is enforced from the shared ironforge_pdt_config table',
}

/**
 * Bots that SWING — they hold to expiry and never consult a stop, so `stop_loss_pct`
 * is stored but unused. Mirrors isSparkStrategy() in scanner.ts; these must move
 * together.
 */
const SWING_BOTS = ['spark', 'spark2', 'kindle']

/**
 * `min_credit` FLOORS — scanner.ts loadConfigOverrides, line ~366:
 *
 *     merged.min_credit = Math.max(merged.min_credit, DEFAULT_CONFIG[bot].min_credit)
 *
 * The DB value IS read for this field, then clamped UP. So it is not inert — it
 * simply cannot go below the code floor. SPARK's row says 0.05 while the bot has
 * refused anything under 0.25 since 2026-05-06; reporting the raw row understates
 * the gate by 5x. Values below mirror DEFAULT_CONFIG in scanner.ts and must move
 * with it.
 */
const MIN_CREDIT_FLOOR: Record<string, number> = {
  flame: 0.25, spark: 0.25, spark2: 0.25, inferno: 0.15, kindle: 0.05,
}

/**
 * `profit_target_pct` — what the scanner ACTUALLY exits on, per bot.
 *
 * getSlidingProfitTarget (scanner.ts):
 *   · INFERNO           -> returns 1.0 / HOLD_TO_EOD. The row's PT is never used.
 *   · SPARK-strategy    -> hardcoded 0.40 / 0.35 / 0.30 by CT time-of-day. The
 *     (spark/spark2/     comment there is explicit: "the DB profit_target_pct
 *      kindle)           override does NOT apply to these bots".
 *   · everything else   -> derived FROM the row (basePt, then basePt-0.10, -0.15).
 *
 * So for every bot except FLAME the stored number governs nothing, and a single
 * scalar cannot describe a sliding ladder anyway. `profit_target_effective`
 * carries the real schedule; the scalar stays for back-compat.
 */
function ptEffective(bot: string, basePt: number): { text: string; inert: boolean } {
  if (bot === 'inferno') {
    return { text: 'HOLD_TO_EOD (no intraday PT; EOD cutoff is the exit)', inert: true }
  }
  if (SWING_BOTS.indexOf(bot) >= 0) {
    return { text: '40% before 12:00 CT / 35% until 13:00 / 30% after (code-controlled)', inert: true }
  }
  const p = Math.round(basePt)
  return {
    text: `${p}% before 10:30 CT / ${Math.max(10, p - 10)}% until 13:00 / ${Math.max(10, p - 15)}% after`,
    inert: false,
  }
}

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

    // Fall back to SPARK, not INFERNO. validateBot also admits blaze, flare and
    // kindle, none of which have an entry here — and INFERNO is the most permissive
    // profile in the file (unlimited trades/day, 100% PT, 1000% stop, 1.0 SD). An
    // unlisted bot inheriting THAT is the wrong direction to fail: a reader is told
    // the bot is far more aggressive than it is. SPARK's conservative 1-trade/day
    // profile is the safer thing to show when we do not have a real answer.
    //
    // Display-only either way — the scanner reads DEFAULT_CONFIG in scanner.ts, never
    // this map. The duplication is the root problem; this only stops it lying loudly.
    const defaults = DEFAULTS[bot] ?? DEFAULTS.spark
    if (rows.length === 0) {
      return NextResponse.json({ ...defaults, account_type: accountType, source: 'defaults' })
    }

    const row = rows[0]
    const ptIsInert = ptEffective(bot, 0).inert
    const inertHere = (k: string) =>
      k in INERT_FIELDS
      || (k === 'stop_loss_pct' && SWING_BOTS.indexOf(bot) >= 0)
      || (k === 'profit_target_pct' && ptIsInert)
    const merged: Record<string, number | string> = { ...defaults }
    for (let i = 0; i < ALL_FIELDS.length; i++) {
      const key = ALL_FIELDS[i]
      // AN INERT FIELD MUST NOT TAKE THE DB VALUE (2026-08-07).
      //
      // Naming a field in `inert_fields` was not enough: the row's dead value was
      // still merged over the default and rendered, so the dashboard printed a
      // number the scanner provably ignores. That is how the header came to read
      // "VIX>35 skip" while the code skipped at 40, and how it would have kept
      // printing "entry 08:30" straight after entry_start moved to 13:00 in
      // scanner.ts — the DB row still says 08:30 and always will, because nothing
      // writes it.
      //
      // For these fields the CODE default IS the effective value, so it is the only
      // honest thing to return. The stored value is still available in
      // `stored_inert_values` for anyone reconciling the row itself.
      if (inertHere(key)) continue
      if (row[key] != null) {
        if (INT_FIELDS.indexOf(key) >= 0) merged[key] = int(row[key])
        else if (NUMERIC_FIELDS.indexOf(key) >= 0) merged[key] = num(row[key])
        else merged[key] = row[key]
      }
    }
    // Keep the row's own values visible, clearly separated from what governs.
    const stored: Record<string, number | string> = {}
    for (const key of ALL_FIELDS) {
      if (inertHere(key) && row[key] != null) stored[key] = row[key] as number | string
    }
    if (Object.keys(stored).length > 0) {
      merged.stored_inert_values = JSON.stringify(stored)
    }

    // min_credit: the row IS read, then clamped UP to the code floor. Report the
    // clamped value — it is the gate the bot enforces — and surface the raw row
    // separately when the clamp actually bit.
    const floor = MIN_CREDIT_FLOOR[bot] ?? MIN_CREDIT_FLOOR.spark
    const rawMinCredit = row.min_credit != null ? num(row.min_credit) : Number(merged.min_credit)
    const effMinCredit = Math.max(rawMinCredit, floor)
    merged.min_credit = effMinCredit
    if (effMinCredit !== rawMinCredit) {
      merged.min_credit_stored = rawMinCredit
      merged.min_credit_note =
        `row says $${rawMinCredit.toFixed(2)}; the scanner clamps UP to the $${floor.toFixed(2)} code floor`
    }

    // profit_target_pct: a sliding ladder, and code-controlled on every bot but
    // FLAME. The scalar alone cannot be right, so ship the schedule.
    const pt = ptEffective(bot, Number(merged.profit_target_pct))
    merged.profit_target_effective = pt.text
    merged.account_type = accountType
    // Name the stored values that govern nothing, so a reader does not take the whole
    // row as the strategy. This is the field that would have stopped me reporting
    // SPARK's parameters from this endpoint and getting them wrong.
    merged.inert_fields = Object.keys(INERT_FIELDS)
      .concat(SWING_BOTS.indexOf(bot) >= 0 ? ['stop_loss_pct'] : [])
      .concat(ptIsInert ? ['profit_target_pct'] : [])
      .join(', ')
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

    // REJECT writes the scanner would ignore. Checked BEFORE the upsert, so a request
    // that names even one inert field changes nothing at all — a partial write is how
    // an operator ends up believing the whole edit landed.
    const inert = Object.keys(filtered)
      .filter((k) => k in INERT_FIELDS)
      .map((k) => ({ field: k, reason: INERT_FIELDS[k] }))

    // stop_loss_pct IS read into sl_mult, but swing bots never reach the stop branch,
    // so storing it on those bots is equally misleading.
    if (filtered.stop_loss_pct != null && SWING_BOTS.indexOf(bot) >= 0) {
      inert.push({
        field: 'stop_loss_pct',
        reason: `${bot.toUpperCase()} swings — it holds to expiry and never consults a stop. Size is the risk control.`,
      })
    }

    if (inert.length > 0) {
      return NextResponse.json(
        {
          error: 'These fields do not affect this bot and were not saved.',
          rejected: inert,
          hint: 'Storing a value the scanner ignores makes the config row describe a strategy the bot does not run. Re-send without these fields.',
        },
        { status: 422 },
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
