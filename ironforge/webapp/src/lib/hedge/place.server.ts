/**
 * Regime hedge — real-money placement orchestration (Phase 3). Server-only.
 *
 * SAFETY (all enforced here):
 *  - ARM FLAG: `HEDGE_AUTO_PLACE === 'true'` required to place a real order. Unset
 *    or anything else → preview-only, NEVER places.
 *  - DEBIT CAP: `HEDGE_MAX_DEBIT` (default $800) — refuse if the spread costs more.
 *  - PREVIEW-FIRST: always Tradier-preview + sanity-check the legs before placing.
 *  - IDEMPOTENT: at most one PLACED hedge per CT day (hedge_orders PK + status guard).
 *  - FLAGGED-ONLY: only on a regime_daily hedge_flagged day.
 *  - DRY-RUN: opts.dryRun (or `HEDGE_DRY_RUN==='true'`) → preview + record, no place.
 *
 * Every outcome is recorded in hedge_orders for audit + display.
 */
import { dbQuery, dbExecute, botTable } from '@/lib/db'
import {
  getQuote, getOptionQuote, buildOccSymbol,
  getHedgeAccount, resolveHedgeExpiration, placeHedgePutSpread, isConfigured,
} from '@/lib/tradier'
import { buildHedgePlan } from '@/lib/hedge/advisor'

const DEFAULT_TAIL = Number(process.env.HEDGE_DEFAULT_TAIL) || 1200
const DEFAULT_CAP = Number(process.env.HEDGE_MAX_DEBIT) || 800
const round2 = (x: number) => Math.round(x * 100) / 100

export type HedgeExecStatus = 'placed' | 'preview' | 'skipped' | 'failed'
export interface HedgeExecResult {
  status: HedgeExecStatus
  reason: string
  detail?: Record<string, unknown>
}

let _hedgeTableEnsured = false
async function ensureHedgeOrdersTable(): Promise<void> {
  if (_hedgeTableEnsured) return
  await dbExecute(`
    CREATE TABLE IF NOT EXISTS hedge_orders (
      ct_date          DATE PRIMARY KEY,
      status           TEXT NOT NULL,
      long_occ         TEXT,
      short_occ        TEXT,
      expiration       DATE,
      contracts        INT,
      limit_debit      REAL,
      est_total_debit  REAL,
      est_max_payoff   REAL,
      preview_cost     REAL,
      tradier_order_id TEXT,
      account_name     TEXT,
      reason           TEXT,
      error            TEXT,
      updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `)
  _hedgeTableEnsured = true
}

/** Upsert today's hedge_orders row — but never downgrade a 'placed' row. */
async function record(status: HedgeExecStatus, fields: Record<string, unknown>): Promise<void> {
  await dbExecute(
    `INSERT INTO hedge_orders
       (ct_date, status, long_occ, short_occ, expiration, contracts,
        limit_debit, est_total_debit, est_max_payoff, preview_cost,
        tradier_order_id, account_name, reason, error, updated_at)
     VALUES ((NOW() AT TIME ZONE 'America/Chicago')::date, $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13, NOW())
     ON CONFLICT (ct_date) DO UPDATE SET
       status=$1, long_occ=$2, short_occ=$3, expiration=$4, contracts=$5,
       limit_debit=$6, est_total_debit=$7, est_max_payoff=$8, preview_cost=$9,
       tradier_order_id=$10, account_name=$11, reason=$12, error=$13, updated_at=NOW()
     WHERE hedge_orders.status <> 'placed'`,
    [
      status,
      fields.long_occ ?? null, fields.short_occ ?? null, fields.expiration ?? null, fields.contracts ?? null,
      fields.limit_debit ?? null, fields.est_total_debit ?? null, fields.est_max_payoff ?? null, fields.preview_cost ?? null,
      fields.tradier_order_id ?? null, fields.account_name ?? null, fields.reason ?? null, fields.error ?? null,
    ],
  )
}

/** Run the hedge flow for today. Idempotent, capped, preview-first, arm-gated. */
export async function placeHedgeForToday(opts: { dryRun?: boolean } = {}): Promise<HedgeExecResult> {
  if (!isConfigured()) return { status: 'skipped', reason: 'Tradier not configured' }
  await ensureHedgeOrdersTable()

  // Idempotency — already placed today?
  const placedRows = await dbQuery(
    `SELECT 1 FROM hedge_orders WHERE ct_date=(NOW() AT TIME ZONE 'America/Chicago')::date AND status='placed' LIMIT 1`,
  )
  if (placedRows.length > 0) return { status: 'skipped', reason: 'already hedged today' }

  // Flagged today?
  const reg = await dbQuery<{ hedge_flagged: boolean; hedge_reasons: string[] | null }>(
    `SELECT hedge_flagged, hedge_reasons FROM regime_daily
      WHERE ct_date=(NOW() AT TIME ZONE 'America/Chicago')::date LIMIT 1`,
  )
  if (!reg[0]?.hedge_flagged) {
    await record('skipped', { reason: 'regime not flagged' })
    return { status: 'skipped', reason: 'regime not flagged' }
  }
  const reasons = reg[0].hedge_reasons ?? []

  // Tail (SPARK live IC max-loss, else default) + SPY + plan.
  const tailRows = await dbQuery<{ tail: number }>(
    `SELECT COALESCE(SUM(GREATEST(spread_width - total_credit, 0) * contracts * 100), 0) AS tail
       FROM ${botTable('spark', 'positions')}
      WHERE status='open' AND dte_mode='1' AND COALESCE(account_type,'sandbox')='production'`,
  )
  const openTail = Number(tailRows[0]?.tail ?? 0)
  const tail = openTail > 0 ? Math.round(openTail) : DEFAULT_TAIL

  const spyQ = await getQuote('SPY')
  if (!spyQ?.last) return { status: 'skipped', reason: 'no SPY quote' }
  const plan = buildHedgePlan({ flagged: true, reasons, tail, spy: spyQ.last })
  if (!plan.hedge) { await record('skipped', { reason: plan.reason }); return { status: 'skipped', reason: plan.reason } }

  // Resolve real expiration + quote the two put legs.
  const expiration = await resolveHedgeExpiration(plan.dte)
  if (!expiration) return { status: 'failed', reason: 'no SPY expiration near target DTE' }
  const occLong = buildOccSymbol('SPY', expiration, plan.long_strike, 'P')
  const occShort = buildOccSymbol('SPY', expiration, plan.short_strike, 'P')
  const [lq, sq] = await Promise.all([getOptionQuote(occLong), getOptionQuote(occShort)])
  if (!lq || !sq) {
    await record('failed', { expiration, long_occ: occLong, short_occ: occShort, error: 'legs not quotable (strike unavailable)' })
    return { status: 'failed', reason: 'hedge strikes not quotable on chain' }
  }

  // Net debit per spread; sanity-check the structure before risking money.
  const midDebit = round2(lq.mid - sq.mid)
  const totalDebit = round2(midDebit * 100 * plan.contracts)
  const cap = DEFAULT_CAP
  if (!(plan.long_strike > plan.short_strike) || midDebit <= 0) {
    await record('failed', { expiration, long_occ: occLong, short_occ: occShort, error: `invalid legs (mid debit ${midDebit})` })
    return { status: 'failed', reason: 'invalid hedge legs' }
  }
  if (totalDebit > cap) {
    await record('skipped', { expiration, long_occ: occLong, short_occ: occShort, contracts: plan.contracts, est_total_debit: totalDebit,
      reason: `debit $${totalDebit} exceeds cap $${cap}` })
    return { status: 'skipped', reason: `debit $${totalDebit} > cap $${cap}` }
  }

  const acct = await getHedgeAccount()
  if (!acct) return { status: 'failed', reason: 'no production account resolved' }

  const limitDebit = round2(midDebit + 0.05) // small fill buffer; still cap-bounded
  const legs = { occLong, occShort, contracts: plan.contracts, limitDebit }
  const base = {
    long_occ: occLong, short_occ: occShort, expiration, contracts: plan.contracts,
    limit_debit: limitDebit, est_total_debit: totalDebit, est_max_payoff: plan.est_max_payoff,
    account_name: acct.name, reason: reasons.join('; '),
  }

  // PREVIEW always (catches leg/structure errors before real money).
  const preview = await placeHedgePutSpread(acct, legs, { preview: true })
  if (!preview.ok) {
    await record('failed', { ...base, preview_cost: preview.cost, error: preview.error })
    return { status: 'failed', reason: `preview rejected: ${preview.error}` }
  }

  const armed = process.env.HEDGE_AUTO_PLACE === 'true'
  const dryRun = opts.dryRun === true || process.env.HEDGE_DRY_RUN === 'true'
  if (dryRun || !armed) {
    const reason = !armed ? 'HEDGE_AUTO_PLACE not enabled — preview only' : 'dry-run — preview only'
    await record('preview', { ...base, preview_cost: preview.cost, reason })
    return { status: 'preview', reason, detail: { ...base, preview_cost: preview.cost } }
  }

  // ARMED + not dry-run → place the real order.
  const placed = await placeHedgePutSpread(acct, legs, { preview: false })
  if (!placed.ok) {
    await record('failed', { ...base, preview_cost: preview.cost, error: placed.error })
    return { status: 'failed', reason: `place rejected: ${placed.error}` }
  }
  await record('placed', { ...base, preview_cost: preview.cost, tradier_order_id: placed.orderId })
  return { status: 'placed', reason: 'hedge placed', detail: { ...base, order_id: placed.orderId } }
}
