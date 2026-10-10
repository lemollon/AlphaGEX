/**
 * Postgres-backed history for FLAME v2 / SPARK v2 signals. Two things live
 * here that MUST be prior-only expanding windows (never a global/backward-
 * looking stat):
 *   1. CALM's 67th-percentile threshold history (one row/session/bot).
 *   2. The D2/D1 band-eligible-day feature+outcome rows the regime brain and
 *      trailing-winner train on.
 *
 * SEEDING: CALM's raw per-day measure (not its percentile threshold, which
 * stays a live-computed expanding window) is pre-computed offline from
 * vix_minute.duckdb (Leron's laptop, not reachable from Render — see
 * ironforge/scripts/seed_flame_v2_signal_history.py) and committed as JSON
 * under ./seed/. `ensureCalmSeedLoaded()` below loads any still-missing
 * seed rows into this table on first use of `priorCalmMeasures`, in every
 * environment, so a fresh deploy never needs ~20 real sessions before CALM
 * can first fire. This module never touches the local DuckDB files itself —
 * only the committed JSON the operator's script already produced.
 *
 * D1/D2's own training rows (ratio, prior_spy_up, r0_pnl..r3_pnl, D2's 7
 * features) are NOT seeded — signal_on_flame_spark.py never persisted a
 * per-day dump of those, so D1/D2 start empty and accumulate purely from
 * live trading days (see the seed script's own header for the full
 * rationale). Both already fail closed to today's existing admission rule
 * until minHist=20 / minSamples=40 real days accumulate.
 *
 * Every function here fails closed: a DB error returns an empty/`null`
 * result (never throws past the caller), because a missing table or an
 * unreachable DB must degrade to "no history yet" -> CALM/LONGG stay
 * unavailable -> shadow logs "insufficient_history" -> live behavior
 * unaffected. Same posture as scanner.ts's own ensureVixHistory/vixDecayCheck.
 */
import { query, dbExecute } from '@/lib/db'
import flameCalmSeedRaw from './seed/flame_calm_seed.json'
import sparkCalmSeedRaw from './seed/spark_calm_seed.json'

export type BotKey = 'flame' | 'spark'

let _tableEnsured = false

export async function ensureSignalHistoryTable(): Promise<void> {
  if (_tableEnsured) return
  try {
    await dbExecute(`
      CREATE TABLE IF NOT EXISTS flame_v2_signal_history (
        bot              TEXT NOT NULL,
        trade_date       DATE NOT NULL,
        calm_measure     DOUBLE PRECISION,
        is_calm          BOOLEAN,
        igex_net         DOUBLE PRECISION,
        is_longg         BOOLEAN,
        band_eligible     BOOLEAN NOT NULL DEFAULT FALSE,
        ratio            DOUBLE PRECISION,
        prior_spy_up     BOOLEAN,
        r0_pnl           DOUBLE PRECISION,
        r1_pnl           DOUBLE PRECISION,
        r2_pnl           DOUBLE PRECISION,
        r3_pnl           DOUBLE PRECISION,
        vix_level        DOUBLE PRECISION,
        vix_1y_pct       DOUBLE PRECISION,
        vix_20d_chg      DOUBLE PRECISION,
        ts_ratio_l       DOUBLE PRECISION,
        ret20            DOUBLE PRECISION,
        ret60            DOUBLE PRECISION,
        above_50dma      DOUBLE PRECISION,
        source           TEXT NOT NULL DEFAULT 'live',
        created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY (bot, trade_date)
      )
    `)
    _tableEnsured = true
  } catch (e) {
    console.error('[flame-v2] ensureSignalHistoryTable failed (fail-closed, no history available):', e)
  }
}

export type DailySignalRow = {
  calmMeasure?: number | null
  isCalm?: boolean | null
  igexNet?: number | null
  isLongg?: boolean | null
  bandEligible?: boolean
  ratio?: number | null
  priorSpyUp?: boolean | null
  r0Pnl?: number | null
  r1Pnl?: number | null
  r2Pnl?: number | null
  r3Pnl?: number | null
  vixLevel?: number | null
  vix1yPct?: number | null
  vix20dChg?: number | null
  tsRatioL?: number | null
  ret20?: number | null
  ret60?: number | null
  above50dma?: number | null
}

/** Upsert — safe to call multiple times for the same (bot, date) as new
 *  fields become known through the trading day (e.g. CALM known at entry,
 *  R1/R0 pnl only known at settlement). */
export async function recordDailySignal(bot: BotKey, tradeDate: string, row: DailySignalRow): Promise<void> {
  await ensureSignalHistoryTable()
  try {
    await dbExecute(
      `INSERT INTO flame_v2_signal_history (
         bot, trade_date, calm_measure, is_calm, igex_net, is_longg, band_eligible,
         ratio, prior_spy_up, r0_pnl, r1_pnl, r2_pnl, r3_pnl,
         vix_level, vix_1y_pct, vix_20d_chg, ts_ratio_l, ret20, ret60, above_50dma
       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
       ON CONFLICT (bot, trade_date) DO UPDATE SET
         calm_measure = COALESCE(EXCLUDED.calm_measure, flame_v2_signal_history.calm_measure),
         is_calm      = COALESCE(EXCLUDED.is_calm, flame_v2_signal_history.is_calm),
         igex_net     = COALESCE(EXCLUDED.igex_net, flame_v2_signal_history.igex_net),
         is_longg     = COALESCE(EXCLUDED.is_longg, flame_v2_signal_history.is_longg),
         band_eligible = EXCLUDED.band_eligible OR flame_v2_signal_history.band_eligible,
         ratio        = COALESCE(EXCLUDED.ratio, flame_v2_signal_history.ratio),
         prior_spy_up = COALESCE(EXCLUDED.prior_spy_up, flame_v2_signal_history.prior_spy_up),
         r0_pnl = COALESCE(EXCLUDED.r0_pnl, flame_v2_signal_history.r0_pnl),
         r1_pnl = COALESCE(EXCLUDED.r1_pnl, flame_v2_signal_history.r1_pnl),
         r2_pnl = COALESCE(EXCLUDED.r2_pnl, flame_v2_signal_history.r2_pnl),
         r3_pnl = COALESCE(EXCLUDED.r3_pnl, flame_v2_signal_history.r3_pnl),
         vix_level = COALESCE(EXCLUDED.vix_level, flame_v2_signal_history.vix_level),
         vix_1y_pct = COALESCE(EXCLUDED.vix_1y_pct, flame_v2_signal_history.vix_1y_pct),
         vix_20d_chg = COALESCE(EXCLUDED.vix_20d_chg, flame_v2_signal_history.vix_20d_chg),
         ts_ratio_l = COALESCE(EXCLUDED.ts_ratio_l, flame_v2_signal_history.ts_ratio_l),
         ret20 = COALESCE(EXCLUDED.ret20, flame_v2_signal_history.ret20),
         ret60 = COALESCE(EXCLUDED.ret60, flame_v2_signal_history.ret60),
         above_50dma = COALESCE(EXCLUDED.above_50dma, flame_v2_signal_history.above_50dma)
      `,
      [
        bot, tradeDate, row.calmMeasure ?? null, row.isCalm ?? null, row.igexNet ?? null, row.isLongg ?? null,
        row.bandEligible ?? false, row.ratio ?? null, row.priorSpyUp ?? null,
        row.r0Pnl ?? null, row.r1Pnl ?? null, row.r2Pnl ?? null, row.r3Pnl ?? null,
        row.vixLevel ?? null, row.vix1yPct ?? null, row.vix20dChg ?? null, row.tsRatioL ?? null,
        row.ret20 ?? null, row.ret60 ?? null, row.above50dma ?? null,
      ],
    )
  } catch (e) {
    console.error(`[flame-v2] recordDailySignal(${bot}, ${tradeDate}) failed (non-fatal):`, e)
  }
}

/**
 * One-time (per process) load of the committed CALM-measure seed
 * (ironforge/scripts/seed_flame_v2_signal_history.py's output,
 * seed/{bot}_calm_seed.json) into flame_v2_signal_history, so a fresh
 * deploy does not need ~20 real trading sessions before CALM can first
 * fire for either bot — see this file's header comment.
 *
 * Idempotent: `ON CONFLICT (bot, trade_date) DO NOTHING` means re-running
 * this (a new deploy, a restarted process, or a re-generated/extended seed
 * file that gets recommitted) only ever inserts rows that are still
 * missing — it never overwrites a real trading day's already-recorded
 * CALM measure or any other column `recordDailySignal` has since written
 * for that date. Source is tagged 'seed' (vs. 'live') so the two are
 * distinguishable in the table. Fails closed: a DB error here never
 * blocks the caller — CALM simply accumulates live instead, same posture
 * as every other function in this file.
 */
type CalmSeedRow = { trade_date: string; calm_measure: number }
const CALM_SEED_BY_BOT: Record<BotKey, CalmSeedRow[]> = {
  flame: flameCalmSeedRaw as CalmSeedRow[],
  spark: sparkCalmSeedRaw as CalmSeedRow[],
}
const _seedLoaded: Partial<Record<BotKey, boolean>> = {}
// 2026-10-02 audit: a failure used to set _seedLoaded=true forever, so one
// transient cold-start DB error disabled CALM for the life of the process
// (~20 trading days of no call spreads, silently). Now: retry at most every
// SEED_RETRY_MS, and mark loaded only after the inserts succeed.
const _seedLastAttemptMs: Partial<Record<BotKey, number>> = {}
const SEED_RETRY_MS = 10 * 60 * 1000

export async function ensureCalmSeedLoaded(bot: BotKey): Promise<void> {
  if (_seedLoaded[bot]) return
  const now = Date.now()
  if (now - (_seedLastAttemptMs[bot] ?? 0) < SEED_RETRY_MS) return
  _seedLastAttemptMs[bot] = now
  await ensureSignalHistoryTable()
  const rows = CALM_SEED_BY_BOT[bot]
  if (!rows || rows.length === 0) { _seedLoaded[bot] = true; return }
  try {
    const CHUNK = 200
    let inserted = 0
    for (let i = 0; i < rows.length; i += CHUNK) {
      const chunk = rows.slice(i, i + CHUNK)
      const params: unknown[] = []
      const tuples = chunk.map((r, j) => {
        params.push(bot, r.trade_date, r.calm_measure)
        return `($${j * 3 + 1}, $${j * 3 + 2}, $${j * 3 + 3}, FALSE, 'seed')`
      })
      const n = await dbExecute(
        `INSERT INTO flame_v2_signal_history (bot, trade_date, calm_measure, band_eligible, source)
         VALUES ${tuples.join(', ')}
         ON CONFLICT (bot, trade_date) DO NOTHING`,
        params as any[],
      )
      inserted += Number(n) || 0
    }
    console.log(`[flame-v2] CALM seed check for ${bot}: ${inserted}/${rows.length} new row(s) inserted (rest already present)`)
    _seedLoaded[bot] = true
  } catch (e) {
    console.error(`[flame-v2] ensureCalmSeedLoaded(${bot}) failed (non-fatal, CALM accumulates from live days only):`, e)
  }
}

/** CALM measure on every session strictly before `beforeDate`, most recent
 *  first, capped at `limit` — matches calm_flag's "all PRIOR days" (an
 *  expanding window; the cap is just a sane upper bound, not a sliding
 *  window — 2000 sessions is ~8 years, far more than `minHist=20` needs). */
export async function priorCalmMeasures(bot: BotKey, beforeDate: string, limit = 2000): Promise<number[]> {
  await ensureSignalHistoryTable()
  await ensureCalmSeedLoaded(bot)
  try {
    const rows = await query<{ calm_measure: number }>(
      `SELECT calm_measure FROM flame_v2_signal_history
        WHERE bot = $1 AND trade_date < $2 AND calm_measure IS NOT NULL
        ORDER BY trade_date DESC LIMIT $3`,
      [bot, beforeDate, limit],
    )
    return rows.map((r) => Number(r.calm_measure)).filter((v) => Number.isFinite(v))
  } catch (e) {
    console.error(`[flame-v2] priorCalmMeasures(${bot}) failed (fail-closed, empty history):`, e)
    return []
  }
}

export type BandDayRow = {
  tradeDate: string
  ratio: number | null
  priorSpyUp: boolean | null
  r0Pnl: number; r1Pnl: number; r2Pnl: number; r3Pnl: number
  vixLevel: number | null; vix1yPct: number | null; vix20dChg: number | null
  tsRatioL: number | null; ret20: number | null; ret60: number | null; above50dma: number | null
}

/** All band-eligible rows strictly before `beforeDate` (for D1's trailing-60
 *  window and D2's monthly refit training set). */
export async function priorBandEligibleRows(bot: BotKey, beforeDate: string, limit = 2000): Promise<BandDayRow[]> {
  await ensureSignalHistoryTable()
  try {
    const rows = await query<Record<string, unknown>>(
      `SELECT trade_date, ratio, prior_spy_up, r0_pnl, r1_pnl, r2_pnl, r3_pnl,
              vix_level, vix_1y_pct, vix_20d_chg, ts_ratio_l, ret20, ret60, above_50dma
         FROM flame_v2_signal_history
        WHERE bot = $1 AND trade_date < $2 AND band_eligible = TRUE
        ORDER BY trade_date ASC LIMIT $3`,
      [bot, beforeDate, limit],
    )
    return rows.map((r) => ({
      tradeDate: String(r.trade_date),
      ratio: r.ratio === null ? null : Number(r.ratio),
      priorSpyUp: r.prior_spy_up === null ? null : Boolean(r.prior_spy_up),
      r0Pnl: Number(r.r0_pnl ?? 0), r1Pnl: Number(r.r1_pnl ?? 0), r2Pnl: Number(r.r2_pnl ?? 0), r3Pnl: Number(r.r3_pnl ?? 0),
      vixLevel: r.vix_level === null ? null : Number(r.vix_level),
      vix1yPct: r.vix_1y_pct === null ? null : Number(r.vix_1y_pct),
      vix20dChg: r.vix_20d_chg === null ? null : Number(r.vix_20d_chg),
      tsRatioL: r.ts_ratio_l === null ? null : Number(r.ts_ratio_l),
      ret20: r.ret20 === null ? null : Number(r.ret20),
      ret60: r.ret60 === null ? null : Number(r.ret60),
      above50dma: r.above_50dma === null ? null : Number(r.above_50dma),
    }))
  } catch (e) {
    console.error(`[flame-v2] priorBandEligibleRows(${bot}) failed (fail-closed, empty history):`, e)
    return []
  }
}
