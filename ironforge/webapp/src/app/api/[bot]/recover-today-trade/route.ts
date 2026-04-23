/**
 * R2 — One-shot backfill for a specific closed SPARK production position whose
 * DB ledger recorded realized_pnl=$0 via `entry_credit_fallback` even though
 * Tradier actually executed the close at a real price. Reconstructs the real
 * P&L from Tradier's same-day order history and UPDATEs the DB row.
 *
 * Primary target: today's 8:56 AM SPARK trade
 * (SPARK-20260423-BEB86D-prod-logan) which has realized_pnl=0 in the DB
 * but Tradier day_pnl=+$7 — caused by the premature close's trigger path
 * not writing a sandbox_close_order_id before the cascade fired, so
 * reconcileProductionBrokerPositions had nothing to look up and fell
 * through to entry_credit_fallback.
 *
 * This endpoint replicates the same logic as the scanner's R2 tier-4
 * recovery (recoverClosePnlFromOrderHistory) but applies it on demand to
 * an already-closed row. Idempotent: skips rows whose realized_pnl is
 * already non-zero OR whose close_reason is not in the broker-gone set.
 *
 * SPARK-only (we don't have evidence this bug exists on FLAME/INFERNO —
 * and the SPARK-specific "1 trade per day" rule is what keeps the
 * order-history summing correct).
 *
 *   GET  /api/spark/recover-today-trade?position_id=...
 *     Dry-run. Returns the row's current state, the recovered P&L, and
 *     what the delta would be. Safe to call anytime.
 *
 *   POST /api/spark/recover-today-trade?position_id=...&confirm=true
 *     Applies the update:
 *       spark_positions.close_price, realized_pnl, close_reason, updated_at
 *       spark_paper_account.current_balance += realized_pnl_delta
 *       spark_paper_account.cumulative_pnl  += realized_pnl_delta
 *     Writes audit log BROKER_RECOVERY_FROM_ORDERS with details JSON.
 *     Returns the before/after snapshot.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot } from '@/lib/db'
import {
  getLoadedSandboxAccountsAsync,
  getAccountIdForKey,
  getTradierOrders,
  isConfigured,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const SPARK_ONLY = NextResponse.json(
  { error: 'SPARK-only — recovery depends on the 1-trade-per-day rule to sum close fills correctly.' },
  { status: 400 },
)

/**
 * Mirror of scanner.ts `recoverClosePnlFromOrderHistory` for the endpoint.
 * (Not imported because scanner.ts doesn't export it — keeping scanner's
 * internals encapsulated.)
 *
 * Filters Tradier's filled orders to today's close-side option fills and
 * sums them as a net debit → per-contract close_price → realized_pnl.
 */
async function recoverFromOrderHistory(args: {
  apiKey: string
  baseUrl: string
  entryCredit: number
  contracts: number
  referenceDateCt: string // 'YYYY-MM-DD' — usually the close_time's CT date
}): Promise<{ close_price: number; realized_pnl: number; debit_total: number; matched_orders: number } | null> {
  const { apiKey, baseUrl, entryCredit, contracts, referenceDateCt } = args
  const accountId = await getAccountIdForKey(apiKey, baseUrl)
  if (!accountId) return null
  const orders = await getTradierOrders(apiKey, accountId, baseUrl, 'filled')
  if (!orders || orders.length === 0) return null

  const closeFills = orders.filter((o) => {
    if (o.class !== 'option' && o.class !== 'multileg') return false
    if (o.status !== 'filled' && o.status !== 'partially_filled') return false
    const side = (o.side ?? '').toLowerCase()
    if (side !== 'buy_to_close' && side !== 'sell_to_close') return false
    if (!o.transaction_date) return false
    const txCt = new Date(new Date(o.transaction_date).toLocaleString('en-US', { timeZone: 'America/Chicago' }))
      .toISOString().slice(0, 10)
    return txCt === referenceDateCt
  })
  if (closeFills.length === 0) return null

  let debitTotal = 0
  for (const o of closeFills) {
    const qty = o.exec_quantity ?? o.quantity ?? 0
    const px = o.avg_fill_price ?? o.last_fill_price ?? 0
    if (!qty || !px) continue
    const dollarValue = px * qty * 100
    debitTotal += (o.side === 'buy_to_close') ? dollarValue : -dollarValue
  }
  const closePrice = Math.max(0, debitTotal / (contracts * 100))
  const realized = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100

  return {
    close_price: Math.round(closePrice * 10000) / 10000,
    realized_pnl: realized,
    debit_total: Math.round(debitTotal * 100) / 100,
    matched_orders: closeFills.length,
  }
}

async function loadCandidate(positionId: string) {
  const rows = await dbQuery(
    `SELECT position_id, status, close_reason,
            close_price, realized_pnl,
            contracts, total_credit, collateral_required,
            person, account_type, dte_mode,
            open_time, close_time
     FROM spark_positions
     WHERE position_id = $1
     LIMIT 1`,
    [positionId],
  )
  if (rows.length === 0) return null
  const r = rows[0]
  const closeTime = r.close_time ? new Date(r.close_time) : null
  const closeDateCt = closeTime
    ? new Date(closeTime.toLocaleString('en-US', { timeZone: 'America/Chicago' })).toISOString().slice(0, 10)
    : null
  return {
    position_id: r.position_id as string,
    status: r.status as string,
    close_reason: (r.close_reason as string) ?? '',
    close_price: num(r.close_price),
    realized_pnl: num(r.realized_pnl),
    contracts: int(r.contracts),
    total_credit: num(r.total_credit),
    collateral: num(r.collateral_required),
    person: (r.person as string) ?? null,
    account_type: (r.account_type as string) ?? 'sandbox',
    dte_mode: (r.dte_mode as string) ?? '1DTE',
    close_date_ct: closeDateCt,
    close_time_iso: closeTime ? closeTime.toISOString() : null,
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'spark') return SPARK_ONLY

  const positionId = req.nextUrl.searchParams.get('position_id')
  if (!positionId) {
    return NextResponse.json({ error: 'position_id query param required' }, { status: 400 })
  }
  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured' }, { status: 500 })
  }

  try {
    const cand = await loadCandidate(positionId)
    if (!cand) return NextResponse.json({ error: 'position_id not found' }, { status: 404 })

    const eligible = cand.status === 'closed'
      && cand.realized_pnl === 0
      && (
        cand.close_reason === 'broker_position_gone'
        || cand.close_reason === 'deferred_broker_gone'
        || cand.close_reason.startsWith('broker_gone_backfill_')
      )

    if (!eligible) {
      return NextResponse.json({
        bot: 'spark',
        position_id: positionId,
        dry_run: true,
        eligible: false,
        reason: cand.realized_pnl !== 0
          ? 'already has non-zero realized_pnl'
          : cand.status !== 'closed'
            ? `status=${cand.status} (need 'closed')`
            : `close_reason=${cand.close_reason} (need broker-gone variant)`,
        current: cand,
      })
    }

    const accounts = await getLoadedSandboxAccountsAsync()
    const acct = accounts.find((a) => a.name === cand.person && a.type === cand.account_type)
    if (!acct) {
      return NextResponse.json({
        bot: 'spark',
        position_id: positionId,
        dry_run: true,
        eligible: true,
        can_recover: false,
        reason: `no loaded account for ${cand.person}:${cand.account_type}`,
        current: cand,
      })
    }

    const referenceDateCt = cand.close_date_ct
      ?? new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
        .toISOString().slice(0, 10)
    const recovery = await recoverFromOrderHistory({
      apiKey: acct.apiKey,
      baseUrl: acct.baseUrl,
      entryCredit: cand.total_credit,
      contracts: cand.contracts,
      referenceDateCt,
    })

    return NextResponse.json({
      bot: 'spark',
      position_id: positionId,
      dry_run: true,
      eligible: true,
      can_recover: recovery != null,
      current: cand,
      recovery,
      would_update: recovery ? {
        close_price_before: cand.close_price,
        close_price_after: recovery.close_price,
        realized_pnl_before: cand.realized_pnl,
        realized_pnl_after: recovery.realized_pnl,
        realized_pnl_delta: recovery.realized_pnl - cand.realized_pnl,
        close_reason_after: 'broker_gone_backfill_tradier_order_history',
      } : null,
      instructions: recovery
        ? `POST /api/spark/recover-today-trade?position_id=${positionId}&confirm=true to apply.`
        : `No recoverable close fills found for ${referenceDateCt}. Close orders may be outside Tradier's retention window.`,
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
  if (bot !== 'spark') return SPARK_ONLY

  const positionId = req.nextUrl.searchParams.get('position_id')
  if (!positionId) return NextResponse.json({ error: 'position_id required' }, { status: 400 })
  if (req.nextUrl.searchParams.get('confirm') !== 'true') {
    return NextResponse.json(
      { error: 'Refusing to mutate without ?confirm=true — call GET first to preview.' },
      { status: 400 },
    )
  }
  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured' }, { status: 500 })
  }

  try {
    const cand = await loadCandidate(positionId)
    if (!cand) return NextResponse.json({ error: 'position_id not found' }, { status: 404 })

    if (cand.realized_pnl !== 0 || cand.status !== 'closed') {
      return NextResponse.json({
        applied: false,
        reason: 'row already has non-zero realized_pnl or is not closed',
        current: cand,
      })
    }

    const accounts = await getLoadedSandboxAccountsAsync()
    const acct = accounts.find((a) => a.name === cand.person && a.type === cand.account_type)
    if (!acct) {
      return NextResponse.json({
        applied: false,
        reason: `no loaded account for ${cand.person}:${cand.account_type}`,
      })
    }

    const referenceDateCt = cand.close_date_ct
      ?? new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
        .toISOString().slice(0, 10)
    const recovery = await recoverFromOrderHistory({
      apiKey: acct.apiKey,
      baseUrl: acct.baseUrl,
      entryCredit: cand.total_credit,
      contracts: cand.contracts,
      referenceDateCt,
    })
    if (!recovery) {
      return NextResponse.json({
        applied: false,
        reason: 'no recoverable close fills found — may be outside Tradier retention window',
      })
    }

    // UPDATE the position row.
    const rowsAffected = await dbExecute(
      `UPDATE spark_positions
       SET close_price = $1,
           realized_pnl = $2,
           close_reason = 'broker_gone_backfill_tradier_order_history',
           updated_at = NOW()
       WHERE position_id = $3
         AND status = 'closed'
         AND realized_pnl = 0`,
      [recovery.close_price, recovery.realized_pnl, positionId],
    )

    if (rowsAffected === 0) {
      return NextResponse.json({
        applied: false,
        reason: 'UPDATE matched 0 rows — state changed between load and apply',
      })
    }

    // Reconcile the per-account paper_account row with the recovered P&L delta.
    // Delta = recovered realized - 0 (was hard-zero) = recovery.realized_pnl.
    const delta = recovery.realized_pnl
    if (delta !== 0) {
      if (cand.account_type === 'production') {
        await dbExecute(
          `UPDATE ${escapeSql('spark')}_paper_account
           SET current_balance = current_balance + $1,
               cumulative_pnl  = cumulative_pnl + $1,
               buying_power    = buying_power + $1,
               updated_at = NOW()
           WHERE account_type = 'production' AND person = $2 AND is_active = TRUE AND dte_mode = $3`,
          [delta, cand.person ?? 'User', cand.dte_mode],
        )
      } else {
        await dbExecute(
          `UPDATE ${escapeSql('spark')}_paper_account
           SET current_balance = current_balance + $1,
               cumulative_pnl  = cumulative_pnl + $1,
               buying_power    = buying_power + $1,
               updated_at = NOW()
           WHERE COALESCE(account_type, 'sandbox') = 'sandbox' AND dte_mode = $2`,
          [delta, cand.dte_mode],
        )
      }
    }

    try {
      await dbExecute(
        `INSERT INTO ${botTable('spark', 'logs')} (level, message, details, dte_mode, person)
         VALUES ($1, $2, $3, $4, $5)`,
        [
          'BROKER_RECOVERY_FROM_ORDERS',
          `R2 recovery: ${positionId} realized_pnl 0 → $${recovery.realized_pnl.toFixed(2)} ` +
          `(close_price $${recovery.close_price.toFixed(4)} from ${recovery.matched_orders} close fills on ${referenceDateCt})`,
          JSON.stringify({
            event: 'broker_gone_recovery_from_order_history',
            position_id: positionId,
            account_type: cand.account_type,
            person: cand.person,
            reference_date_ct: referenceDateCt,
            entry_credit: cand.total_credit,
            contracts: cand.contracts,
            close_price_before: cand.close_price,
            close_price_after: recovery.close_price,
            realized_pnl_before: 0,
            realized_pnl_after: recovery.realized_pnl,
            realized_pnl_delta: delta,
            debit_total: recovery.debit_total,
            matched_orders: recovery.matched_orders,
          }),
          cand.dte_mode,
          cand.person,
        ],
      )
    } catch { /* audit log is best-effort */ }

    const after = await loadCandidate(positionId)
    return NextResponse.json({
      applied: true,
      bot: 'spark',
      position_id: positionId,
      before: cand,
      after,
      recovery,
      delta,
      note: 'Refresh /spark Trade History + Performance to see the corrected P&L.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
