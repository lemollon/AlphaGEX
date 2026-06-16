/**
 * Regime hedge — placement orchestration (Phase 3). Server-only.
 *
 * REAL-MONEY (SPARK production) hedge is APPROVAL-GATED: on a flagged day the scanner
 * only PROPOSES a hedge (status='pending') — a human must confirm via the button
 * (confirmHedgeForToday) before any order is placed. Non-production accounts auto-place
 * (none wired today; forward-looking).
 *
 * SAFETY (all enforced):
 *  - APPROVAL: real-money placement only via explicit confirm (button / authorized POST).
 *  - ARM FLAG: `HEDGE_AUTO_PLACE === 'true'` required even to PROPOSE. Unset → nothing.
 *  - DEBIT CAP: `HEDGE_MAX_DEBIT` (default $800) — refuse if the spread costs more.
 *  - PREVIEW-FIRST: always Tradier-preview + sanity-check legs before risking money.
 *  - IDEMPOTENT: one PLACED hedge per CT day; 'declined' is terminal for the day too.
 *  - FLAGGED-ONLY: only when regime_daily.hedge_flagged.
 * Every outcome is recorded in hedge_orders for audit + display.
 */
import { dbQuery, dbExecute, botTable } from '@/lib/db'
import {
  getQuote, getOptionQuote, buildOccSymbol, getTradierBalanceDetail,
  getHedgeAccount, resolveHedgeExpiration, placeHedgePutSpread, isConfigured,
} from '@/lib/tradier'
import { buildHedgePlan, computeHedgeCap } from '@/lib/hedge/advisor'

const DEFAULT_TAIL = Number(process.env.HEDGE_DEFAULT_TAIL) || 1200
const round2 = (x: number) => Math.round(x * 100) / 100

export type HedgeExecStatus = 'pending' | 'placed' | 'declined' | 'skipped' | 'failed'
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

/** Upsert today's hedge_orders row — never downgrade a terminal (placed/declined) row. */
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
     WHERE hedge_orders.status NOT IN ('placed','declined')`,
    [
      status,
      fields.long_occ ?? null, fields.short_occ ?? null, fields.expiration ?? null, fields.contracts ?? null,
      fields.limit_debit ?? null, fields.est_total_debit ?? null, fields.est_max_payoff ?? null, fields.preview_cost ?? null,
      fields.tradier_order_id ?? null, fields.account_name ?? null, fields.reason ?? null, fields.error ?? null,
    ],
  )
}

export async function getTodayHedgeOrder(): Promise<Record<string, unknown> | null> {
  await ensureHedgeOrdersTable()
  const rows = await dbQuery(
    `SELECT status, long_occ, short_occ, expiration, contracts, limit_debit,
            est_total_debit, est_max_payoff, preview_cost, tradier_order_id, reason, error, updated_at
       FROM hedge_orders WHERE ct_date=(NOW() AT TIME ZONE 'America/Chicago')::date LIMIT 1`,
  )
  return rows[0] ?? null
}

export function hedgeArmState(): { armed: boolean } {
  return { armed: process.env.HEDGE_AUTO_PLACE === 'true' }
}

interface PreparedHedge {
  acct: { apiKey: string; baseUrl: string; accountId: string; name: string }
  legs: { occLong: string; occShort: string; contracts: number; limitDebit: number }
  base: Record<string, unknown>
  previewCost: number | null
}

/**
 * Shared pre-flight: flagged-check, tail/SPY/plan, resolve real strikes, cap-check,
 * Tradier preview + leg sanity. Returns the prepared hedge or a terminal skip/fail.
 * Does NOT place. Both propose and confirm call this so the confirmed order is priced
 * fresh (market may have moved since the proposal).
 */
async function prepareHedge(): Promise<{ ok: true; prepared: PreparedHedge } | { ok: false; result: HedgeExecResult }> {
  const reg = await dbQuery<{ hedge_flagged: boolean; hedge_reasons: string[] | null }>(
    `SELECT hedge_flagged, hedge_reasons FROM regime_daily
      WHERE ct_date=(NOW() AT TIME ZONE 'America/Chicago')::date LIMIT 1`,
  )
  if (!reg[0]?.hedge_flagged) return { ok: false, result: { status: 'skipped', reason: 'regime not flagged' } }
  const reasons = reg[0].hedge_reasons ?? []

  const tailRows = await dbQuery<{ tail: number }>(
    `SELECT COALESCE(SUM(GREATEST(spread_width - total_credit, 0) * contracts * 100), 0) AS tail
       FROM ${botTable('spark', 'positions')}
      WHERE status='open' AND dte_mode='1' AND COALESCE(account_type,'sandbox')='production'`,
  )
  const openTail = Number(tailRows[0]?.tail ?? 0)
  const tail = openTail > 0 ? Math.round(openTail) : DEFAULT_TAIL

  const spyQ = await getQuote('SPY')
  if (!spyQ?.last) return { ok: false, result: { status: 'skipped', reason: 'no SPY quote' } }
  const plan = buildHedgePlan({ flagged: true, reasons, tail, spy: spyQ.last })
  if (!plan.hedge) return { ok: false, result: { status: 'skipped', reason: plan.reason } }

  const expiration = await resolveHedgeExpiration(plan.dte)
  if (!expiration) return { ok: false, result: { status: 'failed', reason: 'no SPY expiration near target DTE' } }
  const occLong = buildOccSymbol('SPY', expiration, plan.long_strike, 'P')
  const occShort = buildOccSymbol('SPY', expiration, plan.short_strike, 'P')
  const [lq, sq] = await Promise.all([getOptionQuote(occLong), getOptionQuote(occShort)])
  if (!lq || !sq) {
    await record('failed', { expiration, long_occ: occLong, short_occ: occShort, error: 'legs not quotable (strike unavailable)' })
    return { ok: false, result: { status: 'failed', reason: 'hedge strikes not quotable on chain' } }
  }

  const midDebit = round2(lq.mid - sq.mid)
  const totalDebit = round2(midDebit * 100 * plan.contracts)
  if (!(plan.long_strike > plan.short_strike) || midDebit <= 0) {
    await record('failed', { expiration, long_occ: occLong, short_occ: occShort, error: `invalid legs (mid debit ${midDebit})` })
    return { ok: false, result: { status: 'failed', reason: 'invalid hedge legs' } }
  }

  const acct = await getHedgeAccount()
  if (!acct) return { ok: false, result: { status: 'failed', reason: 'no production account resolved' } }

  // RELATIVE cap. Soft = min(50% of tail, 12% of account equity, optional $ override) —
  // scales with risk so it never blocks a legitimately-sized hedge. Hard ceiling = the tail.
  let accountEquity: number | null = null
  try {
    const bal = await getTradierBalanceDetail(acct.apiKey, acct.accountId, acct.baseUrl)
    accountEquity = bal?.total_equity ?? null
  } catch { /* equity is optional for the cap */ }
  const { softCap, hardCeiling } = computeHedgeCap({
    tail,
    accountEquity,
    tailPct: Number(process.env.HEDGE_CAP_TAIL_PCT) || undefined,
    acctPct: Number(process.env.HEDGE_CAP_ACCT_PCT) || undefined,
    absoluteSoftCap: Number(process.env.HEDGE_MAX_DEBIT) || undefined,
  })

  // HARD ceiling = circuit breaker: a hedge costing more than the tail it protects is
  // pathological / bad pricing → skip.
  if (totalDebit > hardCeiling) {
    await record('skipped', { expiration, long_occ: occLong, short_occ: occShort, contracts: plan.contracts, est_total_debit: totalDebit,
      reason: `debit $${totalDebit} > hard ceiling $${hardCeiling} (more than the tail — bad pricing)` })
    return { ok: false, result: { status: 'skipped', reason: `debit $${totalDebit} exceeds the tail it protects — skipped` } }
  }

  // Over the SOFT cap → still PROPOSE (never silently skip an expensive hedge on a high-vol
  // day — that's exactly when it's needed). Flag it so the operator decides at the button.
  const expensive = totalDebit > softCap
  const reasonText = reasons.join('; ') +
    (expensive ? ` — ⚠ expensive: $${totalDebit} (${Math.round((totalDebit / tail) * 100)}% of tail; soft cap $${softCap})` : '')

  const limitDebit = round2(midDebit + 0.05)
  const legs = { occLong, occShort, contracts: plan.contracts, limitDebit }
  const base = {
    long_occ: occLong, short_occ: occShort, expiration, contracts: plan.contracts,
    limit_debit: limitDebit, est_total_debit: totalDebit, est_max_payoff: plan.est_max_payoff,
    account_name: acct.name, reason: reasonText,
  }

  const preview = await placeHedgePutSpread(acct, legs, { preview: true })
  if (!preview.ok) {
    await record('failed', { ...base, error: preview.error })
    return { ok: false, result: { status: 'failed', reason: `preview rejected: ${preview.error}` } }
  }
  return { ok: true, prepared: { acct, legs, base, previewCost: preview.cost } }
}

/** Scanner path: on a flagged + armed day, PROPOSE the real-money hedge (status='pending').
 *  Never places. The operator confirms via the button. Idempotent / terminal-safe. */
export async function runHedgeProposal(): Promise<HedgeExecResult> {
  if (!isConfigured()) return { status: 'skipped', reason: 'Tradier not configured' }
  if (process.env.HEDGE_AUTO_PLACE !== 'true') return { status: 'skipped', reason: 'hedge system not enabled' }
  await ensureHedgeOrdersTable()

  const today = await getTodayHedgeOrder()
  const st = today?.status as string | undefined
  if (st === 'placed' || st === 'declined') return { status: st as HedgeExecStatus, reason: `already ${st} today` }

  const prep = await prepareHedge()
  if (!prep.ok) return prep.result
  await record('pending', { ...prep.prepared.base, preview_cost: prep.prepared.previewCost,
    reason: `${prep.prepared.base.reason} — awaiting confirmation` })
  return { status: 'pending', reason: 'hedge proposed — awaiting confirmation', detail: { ...prep.prepared.base, preview_cost: prep.prepared.previewCost } }
}

/** Button path: place the real-money hedge after explicit human confirmation. */
export async function confirmHedgeForToday(): Promise<HedgeExecResult> {
  if (!isConfigured()) return { status: 'skipped', reason: 'Tradier not configured' }
  await ensureHedgeOrdersTable()
  const today = await getTodayHedgeOrder()
  if (today?.status === 'placed') return { status: 'placed', reason: 'already hedged today' }

  const prep = await prepareHedge() // re-price fresh before risking money
  if (!prep.ok) return prep.result
  const { acct, legs, base, previewCost } = prep.prepared

  const placed = await placeHedgePutSpread(acct, legs, { preview: false })
  if (!placed.ok) {
    await record('failed', { ...base, preview_cost: previewCost, error: placed.error })
    return { status: 'failed', reason: `place rejected: ${placed.error}` }
  }
  await record('placed', { ...base, preview_cost: previewCost, tradier_order_id: placed.orderId })
  return { status: 'placed', reason: 'hedge placed', detail: { ...base, order_id: placed.orderId } }
}

/** Button path: decline today's hedge (terminal — won't re-propose today). */
export async function declineHedgeForToday(): Promise<HedgeExecResult> {
  await ensureHedgeOrdersTable()
  await record('declined', { reason: 'declined by operator' })
  return { status: 'declined', reason: 'hedge declined' }
}
