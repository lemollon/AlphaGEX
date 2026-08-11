import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/** Default config values (mirrors models.py factory functions). */
const DEFAULTS: Record<string, Record<string, number | string>> = {
  // FLAME v2 (2026-08-10) — 1DTE bull put credit spread. Mirrors
  // DEFAULT_CONFIG.flame in scanner.ts; these must move together.
  // FLAME v3 (2026-08-11) -- three-market 7 DTE put credit spread on SPY/QQQ/IWM.
  // sd_multiplier and spread_width shown are the $5,000 tier; BOTH are derived
  // from live equity by flameParams() in scanner.ts and are reported INERT.
  flame: {
    sd_multiplier: 0.25, spread_width: 2.0, min_credit: 0.05,
    profit_target_pct: 100.0, stop_loss_pct: 1000.0, vix_skip: 32.0,
    // max_contracts is INERT and derived by flameContracts(equity) in scanner.ts:
    //   <$8k -> 1, <$16k -> 2, else 3.
    // It must still MIRROR what that function returns at this bot's starting
    // capital, because an inert field is reported from DEFAULTS -- so a stale
    // mirror makes the API state a number the bot does not use. At $5,000 that
    // is 1. It read 0 (the old "no cap" sentinel) until 2026-08-11.
    max_contracts: 1, max_trades_per_day: 1, buying_power_usage_pct: 0.80,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '14:45',
    pdt_max_day_trades: 4, starting_capital: 5000.0,
  },
  // SPARK v3 (2026-08-10) — the walk-forward 5 DTE condor. Mirrors
  // DEFAULT_CONFIG.spark in scanner.ts; these must move together.
  //
  // SPARK now runs FIXED strike placement (fixed_strike_placement): shorts at
  // exactly 1.25x the expected move, in every gamma regime. The GEX-adaptive widen
  // and the thin-credit SD walk-in are both suppressed for it — they were tuned on
  // the 1DTE structure that measured no edge on real fills.
  //
  // It also STOPS now (1.5x credit) — it is no longer in SWING_BOTS — and holds to
  // expiry with no intraday profit target.
  // SPARK v4 (2026-08-11) -- the SAME strategy as FLAME, at the $10,000+ tier.
  // A single book cannot deploy past ~$5,000 (one trade per market per day), so
  // SPARK is how capital above that gets used: identical rules, 2 contracts.
  // sd_multiplier, spread_width and the contract count are all DERIVED from live
  // equity and reported inert.
  spark: {
    sd_multiplier: 0.25, spread_width: 2.0, min_credit: 0.05,
    profit_target_pct: 100.0, stop_loss_pct: 1000.0, vix_skip: 32.0,
    max_contracts: 2, max_trades_per_day: 1, buying_power_usage_pct: 0.80,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '14:45',
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
  // FORGE (2026-08-10) -- the three-market condor, SPY+QQQ+IWM. Mirrors
  // DEFAULT_CONFIG.forge in scanner.ts; these must move together.
  //
  // Without this entry FORGE falls through to `DEFAULTS.spark` and the config
  // page reports SPARK's 5 DTE single-market settings for a 7 DTE three-market
  // bot -- the same failure that once had spark2 reporting INFERNO's profile.
  //
  // sd_multiplier here is the SPY book's placement; QQQ and IWM run 1.25 and are
  // code-controlled per book (FORGE_BOOKS in scanner.ts), not settable per-bot.
  // buying_power_usage_pct is the TOTAL across all three books; each gets a third.
  forge: {
    // spread_width shown is what forgeWingWidth() DERIVES at the $5,000 seed
    // ($3). It is reported inert -- see DERIVED_WIDTH_BOTS.
    sd_multiplier: 1.75, spread_width: 3.0, min_credit: 0.25,
    profit_target_pct: 100.0, stop_loss_pct: 1000.0, vix_skip: 32.0,
    max_contracts: 1, max_trades_per_day: 1, buying_power_usage_pct: 0.80,
    risk_per_trade_pct: 0.15, min_win_probability: 0.42,
    entry_start: '08:30', entry_end: '14:00', eod_cutoff_et: '14:45',
    pdt_max_day_trades: 4, starting_capital: 5000.0,
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
  risk_per_trade_pct: 'never read; sizing is buying_power_usage_pct against the regime cap',
  min_win_probability: 'never read by the scanner',
  entry_start: 'only entry_end is parsed from the row; the open is a code constant',
  pdt_max_day_trades: 'PDT is enforced from the shared ironforge_pdt_config table',
}

/**
 * Bots that never consult a stop, so `stop_loss_pct` is stored but unused. Mirrors
 * isNoStopBot() in scanner.ts; these must move together.
 *
 * SPARK left this list on 2026-08-10. Its 5 DTE config exits at 1.5x the entry
 * credit, so stop_loss_pct is now genuinely READ for it and must no longer be
 * reported as inert — the whole point of this list is that the API never tells an
 * operator a field is dead when it governs real money.
 */
const SWING_BOTS = ['spark2', 'kindle']

/**
 * Bots whose wing width is DERIVED FROM LIVE EQUITY every scan, so the stored
 * `spread_width` governs nothing and must be reported as inert.
 *
 * FORGE picks $1 / $3 / $10 by account size (forgeWingWidth in scanner.ts),
 * because concurrency is the edge: a $10 condor ties up ~$950 and a $1 condor
 * ~$95, so the same $5,000 account holds 4 positions or 40 depending on width.
 * Letting an operator pin the width would silently break the mechanism the
 * strategy is built on -- and a field that takes your edit and changes nothing
 * is worse than no field, because it reads as authoritative.
 */
const DERIVED_WIDTH_BOTS = ['forge', 'flame', 'spark']

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
  flame: 0.05, spark: 0.05, spark2: 0.25, inferno: 0.15, kindle: 0.05,
  forge: 0.25,
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
  // basePt >= 100 is the engine's OFF switch and it holds ALL DAY — mirrors the
  // `basePt >= 1.0` guard in getSlidingProfitTarget. Reporting the sliding ladder
  // here would claim a 90%/85% midday target that the scanner does not apply.
  if (basePt >= 100) {
    return { text: 'HOLD_TO_EOD (no intraday PT; EOD cutoff / expiry is the exit)', inert: false }
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
      || (k === 'spread_width' && DERIVED_WIDTH_BOTS.indexOf(bot) >= 0)
      || (k === 'sd_multiplier' && (bot === 'flame' || bot === 'spark'))
      || (k === 'max_contracts' && (bot === 'flame' || bot === 'spark'))
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
      .concat(DERIVED_WIDTH_BOTS.indexOf(bot) >= 0 ? ['spread_width'] : [])
      .concat(bot === 'flame' || bot === 'spark' ? ['sd_multiplier', 'max_contracts'] : [])
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
    // profit_target_pct: 0 < pt <= 100.
    //
    // 100 is the documented OFF SWITCH, not an invalid value. scanner.ts stores it
    // as ptFraction = pt/100 = 1.0 and gates the trigger on `ptFraction < 1.0`, so
    // 100 means "never take profit early, hold to expiry". INFERNO's own defaults in
    // this same file already carry profit_target_pct: 100.0.
    //
    // The old bound was `>= 100`, which rejected the one value the scanner treats as
    // the off switch — a config the app could never express even though the engine
    // supports it. FLAME needs it: its 30% target capped wins at 28% of credit while
    // the stop gave back 52%, requiring a 67.5% win rate against an actual 61.9%.
    // Anything ABOVE 100 stays rejected — that would be a target below zero cost.
    const ptPct = filtered.profit_target_pct as number | undefined
    if (ptPct != null && (ptPct <= 0 || ptPct > 100)) {
      return NextResponse.json(
        { error: 'profit_target_pct must be greater than 0 and at most 100 (100 = hold to expiry, no early profit-take)' },
        { status: 422 },
      )
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
