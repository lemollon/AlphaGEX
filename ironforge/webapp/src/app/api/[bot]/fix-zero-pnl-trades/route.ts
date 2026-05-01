/**
 * One-shot backfill for ledger rows that the scanner's legacy broker-gone
 * paths wrote with realized_pnl=0. There are TWO such paths:
 *   1. `monitorSinglePosition` → close_reason='deferred_broker_gone'
 *      (fixed at the source in Commit F)
 *   2. `reconcileProductionBrokerPositions` → close_reason='broker_position_gone'
 *      (fixed at the source in Commit H)
 * This backfill matches BOTH so the ledger can be reconciled for any
 * historical rows written before the source fixes landed.
 *
 * Dashboard's Live top card already shows the correct P&L because
 * Commit C mirrors Tradier. This endpoint reconciles the DB ledger to
 * match — so Trade History, Performance, Equity Curve, and any other
 * view that reads from {bot}_positions all agree.
 *
 * GET  /api/{bot}/fix-zero-pnl-trades
 *   Dry run. Lists every candidate row + what it WOULD be corrected to
 *   if you POST. Safe to call anytime.
 *
 * POST /api/{bot}/fix-zero-pnl-trades?confirm=true
 *   Applies the correction. For each candidate:
 *     1. Fetches the close order from Tradier (order_id from the pending
 *        JSON's `{person}:production` or `User:sandbox` entry).
 *     2. If status = filled/partially_filled → uses avg_fill_price.
 *     3. Else falls back to pending JSON's _limit_price (the limit we
 *        placed) — because the broker legs are gone, the limit must
 *        have executed.
 *     4. Recomputes realized_pnl = (entry_credit − close_price) × 100
 *        × contracts, rounds to cents.
 *     5. UPDATEs the row + UPDATEs paper_account.cumulative_pnl and
 *        current_balance to match.
 *     6. Writes a BROKER_GONE_BACKFILL audit log row.
 *   Skips rows where no valid close_price can be recovered — those get
 *   reported in the response with reason='no_recovery_source' so the
 *   operator knows to chase manually.
 *
 * Scope:
 *   - Production close_reason='deferred_broker_gone' + realized_pnl=0
 *     is the primary target.
 *   - Sandbox rows with the same pattern are fixed too (same bug would
 *     have hit them if the Tradier sandbox re-poll ever failed).
 *   - No trading logic. No order placement. Pure DB reconciliation.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import {
  getLoadedSandboxAccountsAsync,
  getAccountIdForKey,
  getTradierOrderDetails,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

interface Candidate {
  position_id: string
  account_type: 'sandbox' | 'production'
  person: string | null
  contracts: number
  entry_credit: number
  collateral: number
  close_time: string | null
  original_close_reason: string
  pending_info: Record<string, unknown>
}

interface RecoveryOutcome {
  position_id: string
  recovered_price: number | null
  recovery_source: 'tradier_fill' | 'pending_limit' | null
  tradier_order_status: string | null
  new_realized_pnl: number | null
  applied: boolean
  reason?: string
}

// Close reasons we will NOT touch — these are intentional zero-PnL closes
// or paths where no real Tradier order was ever placed. Trying to "recover"
// them would either fabricate P&L or overwrite a legitimate reason.
const SKIP_CLOSE_REASONS = new Set([
  'emergency_kill_switch', // operator-initiated panic close
  'stale_holdover',        // prior-day position swept; no close order
  'manual',                // human-driven close
])

async function gatherCandidates(bot: string, dte: string): Promise<Candidate[]> {
  // Broadened from broker-gone-only to *any* close_reason that left the
  // ledger at $0 with a Tradier close order on file. Profit-target and
  // stop-loss rows hit the same fill-recovery problem when Tradier's
  // order status lagged its leg-level fills (e.g. SPARK ids 40/41/43 in
  // April 2026 were profit_target_* with realized_pnl=0 and live order
  // ids in sandbox_close_order_id). Same recovery logic — Tradier order
  // details → pending limit hint — works for them.
  const rows = await dbQuery(
    `SELECT position_id, contracts, total_credit, collateral_required,
            COALESCE(account_type, 'sandbox') AS account_type,
            person, close_time, close_reason, sandbox_close_order_id
     FROM ${botTable(bot, 'positions')}
     WHERE status = 'closed'
       AND realized_pnl = 0
       AND dte_mode = $1
       AND sandbox_close_order_id IS NOT NULL
     ORDER BY close_time DESC`,
    [dte],
  )
  return rows
    .filter((r) => {
      const reason = String(r.close_reason ?? '')
      return !SKIP_CLOSE_REASONS.has(reason)
    })
    .map((r) => {
      let pending: Record<string, unknown> = {}
      try {
        if (r.sandbox_close_order_id) pending = JSON.parse(r.sandbox_close_order_id)
      } catch { /* malformed — leave empty, we'll skip */ }
      return {
        position_id: r.position_id,
        account_type: (r.account_type || 'sandbox') as 'sandbox' | 'production',
        person: r.person || null,
        contracts: int(r.contracts),
        entry_credit: num(r.total_credit),
        collateral: num(r.collateral_required),
        close_time: r.close_time ? new Date(r.close_time).toISOString() : null,
        original_close_reason: String(r.close_reason ?? ''),
        pending_info: pending,
      }
    })
}

/**
 * Figure out which pending-JSON key holds the close order for this
 * position (production accounts use `${person}:production`; sandbox uses
 * `User:sandbox` or legacy `User`). Returns the order_id + the matching
 * key, or null if no close order is present.
 */
function resolveClosePending(c: Candidate): { key: string; orderId: number; limitPrice: number | null } | null {
  const info = c.pending_info
  const candidates: string[] = []
  if (c.account_type === 'production' && c.person) candidates.push(`${c.person}:production`)
  candidates.push('User:sandbox', 'User')
  for (const key of candidates) {
    const entry = info[key] as { order_id?: number; fill_price?: number | null } | undefined
    if (entry && typeof entry.order_id === 'number' && entry.order_id > 0) {
      const limitPrice = typeof info._limit_price === 'number' ? info._limit_price : null
      return { key, orderId: entry.order_id, limitPrice }
    }
  }
  return null
}

async function recoverOne(
  c: Candidate,
): Promise<RecoveryOutcome> {
  const resolved = resolveClosePending(c)
  if (!resolved) {
    return {
      position_id: c.position_id,
      recovered_price: null,
      recovery_source: null,
      tradier_order_status: null,
      new_realized_pnl: null,
      applied: false,
      reason: 'no_order_id_in_pending_json',
    }
  }

  const accounts = await getLoadedSandboxAccountsAsync()
  const acct = c.account_type === 'production' && c.person
    ? accounts.find((a) => a.name === c.person && a.type === 'production')
    : accounts.find((a) => a.name === 'User' && a.type === 'sandbox') ?? accounts.find((a) => a.name === 'User')
  if (!acct) {
    return {
      position_id: c.position_id,
      recovered_price: null,
      recovery_source: null,
      tradier_order_status: null,
      new_realized_pnl: null,
      applied: false,
      reason: `no_loaded_account_for_${c.account_type}/${c.person ?? 'User'}`,
    }
  }

  let recoveredPrice: number | null = null
  let recoverySource: 'tradier_fill' | 'pending_limit' | null = null
  let tradierStatus: string | null = null
  try {
    const accountId = await getAccountIdForKey(acct.apiKey, acct.baseUrl)
    if (accountId) {
      const details = await getTradierOrderDetails(acct.apiKey, accountId, resolved.orderId, acct.baseUrl)
      if (details) {
        tradierStatus = details.status
        const isFilled = details.status === 'filled' || details.status === 'partially_filled'
        const fillCandidate = details.avg_fill_price ?? details.last_fill_price
        if (isFilled && fillCandidate != null && fillCandidate > 0) {
          recoveredPrice = fillCandidate
          recoverySource = 'tradier_fill'
        }
      }
    }
  } catch { /* continue to fallback */ }

  if (recoveredPrice == null && resolved.limitPrice != null && resolved.limitPrice > 0) {
    recoveredPrice = resolved.limitPrice
    recoverySource = 'pending_limit'
  }

  if (recoveredPrice == null) {
    return {
      position_id: c.position_id,
      recovered_price: null,
      recovery_source: null,
      tradier_order_status: tradierStatus,
      new_realized_pnl: null,
      applied: false,
      reason: 'no_recovery_source',
    }
  }

  const realizedPnl = Math.round((c.entry_credit - recoveredPrice) * 100 * c.contracts * 100) / 100

  return {
    position_id: c.position_id,
    recovered_price: Math.round(recoveredPrice * 10000) / 10000,
    recovery_source: recoverySource,
    tradier_order_status: tradierStatus,
    new_realized_pnl: realizedPnl,
    applied: false,
  }
}

async function applyOne(bot: string, dte: string, c: Candidate, o: RecoveryOutcome): Promise<void> {
  if (o.recovered_price == null || o.new_realized_pnl == null) return

  // UPDATE the closed position row with the recovered close price + P&L.
  // Guard on realized_pnl=0 so we never double-apply on a re-run.
  // Preserve the original close_reason and append a `_backfill_<source>`
  // suffix so trade-history queries still see the underlying tier
  // (profit_target_MIDDAY_backfill_tradier_fill, stop_loss_backfill_pending_limit, …).
  const newCloseReason = c.original_close_reason
    ? `${c.original_close_reason}_backfill_${o.recovery_source}`
    : `broker_gone_backfill_${o.recovery_source}`
  const rowsAffected = await dbExecute(
    `UPDATE ${botTable(bot, 'positions')}
     SET close_price = $1,
         realized_pnl = $2,
         close_reason = $3,
         updated_at = NOW()
     WHERE position_id = $4
       AND status = 'closed'
       AND realized_pnl = 0`,
    [o.recovered_price, o.new_realized_pnl, newCloseReason, c.position_id],
  )
  if (rowsAffected === 0) return

  // Reconcile the paper_account row: add the recovered P&L into
  // cumulative_pnl + current_balance. The original row's close path
  // added 0 P&L, so the delta is simply the new realized_pnl.
  if (c.account_type === 'production') {
    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET current_balance = current_balance + $1,
           cumulative_pnl = cumulative_pnl + $1,
           buying_power = buying_power + $1,
           updated_at = NOW()
       WHERE account_type = 'production' AND person = $2 AND is_active = TRUE AND dte_mode = $3`,
      [o.new_realized_pnl, c.person ?? 'User', dte],
    )
  } else {
    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET current_balance = current_balance + $1,
           cumulative_pnl = cumulative_pnl + $1,
           buying_power = buying_power + $1,
           updated_at = NOW()
       WHERE COALESCE(account_type, 'sandbox') = 'sandbox' AND dte_mode = $2`,
      [o.new_realized_pnl, dte],
    )
  }

  try {
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'BROKER_GONE_BACKFILL',
        `${c.position_id}: corrected realized_pnl 0 → $${o.new_realized_pnl.toFixed(2)} (close_price $${o.recovered_price.toFixed(4)}, via ${o.recovery_source})`,
        JSON.stringify({
          event: 'broker_gone_backfill',
          position_id: c.position_id,
          account_type: c.account_type,
          person: c.person,
          contracts: c.contracts,
          entry_credit: c.entry_credit,
          recovered_close_price: o.recovered_price,
          recovery_source: o.recovery_source,
          tradier_order_status: o.tradier_order_status,
          realized_pnl_delta: o.new_realized_pnl,
        }),
        dte,
      ],
    )
  } catch { /* audit log is best-effort */ }

  o.applied = true
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  try {
    const candidates = await gatherCandidates(bot, dte)
    if (candidates.length === 0) {
      return NextResponse.json({
        bot,
        candidates: 0,
        dry_run: true,
        note: 'No realized_pnl=0 broker-gone rows to fix.',
      })
    }

    const outcomes: RecoveryOutcome[] = []
    for (const c of candidates) {
      outcomes.push(await recoverOne(c))
    }

    const totalDelta = outcomes
      .map((o) => o.new_realized_pnl ?? 0)
      .reduce((a, b) => a + b, 0)

    return NextResponse.json({
      bot,
      dry_run: true,
      candidates: candidates.length,
      recoverable: outcomes.filter((o) => o.recovered_price != null).length,
      unrecoverable: outcomes.filter((o) => o.recovered_price == null).length,
      projected_pnl_delta: Math.round(totalDelta * 100) / 100,
      instructions: `POST /api/${bot}/fix-zero-pnl-trades?confirm=true to apply.`,
      outcomes,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  const confirm = req.nextUrl.searchParams.get('confirm') === 'true'
  if (!confirm) {
    return NextResponse.json(
      {
        error: 'Refusing to modify ledger without ?confirm=true — call GET first to preview.',
      },
      { status: 400 },
    )
  }

  try {
    const candidates = await gatherCandidates(bot, dte)
    const outcomes: RecoveryOutcome[] = []
    for (const c of candidates) {
      const outcome = await recoverOne(c)
      await applyOne(bot, dte, c, outcome)
      outcomes.push(outcome)
    }

    const appliedCount = outcomes.filter((o) => o.applied).length
    const totalDelta = outcomes
      .filter((o) => o.applied)
      .map((o) => o.new_realized_pnl ?? 0)
      .reduce((a, b) => a + b, 0)

    return NextResponse.json({
      bot,
      candidates: candidates.length,
      applied: appliedCount,
      skipped: candidates.length - appliedCount,
      total_pnl_delta: Math.round(totalDelta * 100) / 100,
      outcomes,
      note: `Ledger reconciled. Refresh /${bot} to see updated Trade History / Equity Curve.`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
