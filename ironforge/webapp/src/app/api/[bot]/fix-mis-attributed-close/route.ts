/**
 * One-shot reconciliation for SPARK production rows whose close was written
 * by `reconcileProductionBrokerPositions` via the unsafe `tradier_order_history`
 * recovery tier (or `entry_credit_fallback`) BEFORE the 2026-04-29 safety gate
 * landed.
 *
 * The bug: that recovery summed EVERY close-side option fill on the production
 * Tradier account for the day and attributed the whole net debit to the one
 * SPARK position being reconciled. The Tradier sandbox account is shared
 * across persons/strategies, so cross-account fills got rolled in → fabricated
 * close prices → wildly wrong realized_pnl. 4/28/2026 hit
 * `SPARK-20260428-06B2CE-prod-logan` with a fabricated $0.89 close (= -$224)
 * even though the actual broker-side IC closed for ~ -$20.
 *
 * Fixes already in place that this endpoint does NOT replace:
 *   • `cea9993` — scanner safety gate prevents future bad rows.
 *
 * What this endpoint adds: a SAFE recovery path for the rows that were
 * already corrupted before the gate landed. It is safe because it filters
 * Tradier order fills by THIS position's exact 4 OCC leg symbols — fills
 * for any other strategy / strike / expiration / ticker are excluded by
 * construction, so cross-account contamination cannot happen.
 *
 * GET  /api/spark/fix-mis-attributed-close?position_id=...
 *   Dry-run preview. Returns the row's current state, the recovered close
 *   price + P&L (filtered by leg symbol), and what the delta would be.
 *   Always safe to call.
 *
 * POST /api/spark/fix-mis-attributed-close?position_id=...&confirm=true
 *   Applies the correction:
 *     • UPDATE spark_positions: close_price, realized_pnl,
 *       close_reason='broker_gone_backfill_legmatched', updated_at.
 *     • UPDATE spark_paper_account: current_balance + delta,
 *       cumulative_pnl + delta, buying_power + delta.
 *     • Append a BROKER_RECONCILE_LEGMATCHED audit log row with the full
 *       before/after diff and every matched Tradier order id for traceability.
 *
 * SPARK-only — same constraint as recover-today-trade. We do not have evidence
 * this bug class hit FLAME / INFERNO, and SPARK's 1-trade-per-day rule makes
 * the leg-match unambiguous.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, validateBot } from '@/lib/db'
import {
  getLoadedSandboxAccountsAsync,
  getAccountIdForKey,
  getTradierOrders,
  buildOccSymbol,
  isConfigured,
  type TradierOrder,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const SPARK_ONLY = NextResponse.json(
  { error: 'SPARK-only — leg-matched recovery is only validated against SPARK 1DTE positions today.' },
  { status: 400 },
)

interface PositionRow {
  position_id: string
  status: string
  close_reason: string
  close_price: number
  realized_pnl: number
  contracts: number
  total_credit: number
  collateral: number
  ticker: string
  expiration: string
  put_short_strike: number
  put_long_strike: number
  call_short_strike: number
  call_long_strike: number
  person: string | null
  account_type: string
  dte_mode: string
  open_time_iso: string | null
  close_time_iso: string | null
  open_date_ct: string | null
  close_date_ct: string | null
}

interface LegMatchedRecovery {
  close_price: number
  realized_pnl: number
  debit_total: number
  matched_orders: Array<{
    order_id: number | string
    transaction_date: string | null
    side: string | null
    class: string | null
    legs_matched: Array<{ option_symbol: string; side: string | null; qty: number; price: number; signed_dollars: number }>
  }>
  occ_symbols: { put_short: string; put_long: string; call_short: string; call_long: string }
}

function ctDate(d: Date | null | undefined): string | null {
  if (!d) return null
  return new Date(d.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
    .toISOString()
    .slice(0, 10)
}

async function loadCandidate(positionId: string): Promise<PositionRow | null> {
  const rows = await dbQuery(
    `SELECT position_id, status, close_reason,
            close_price, realized_pnl,
            contracts, total_credit, collateral_required,
            ticker, expiration,
            put_short_strike, put_long_strike,
            call_short_strike, call_long_strike,
            person, account_type, dte_mode,
            open_time, close_time
     FROM spark_positions
     WHERE position_id = $1
     LIMIT 1`,
    [positionId],
  )
  if (rows.length === 0) return null
  const r = rows[0]
  const openTime = r.open_time ? new Date(r.open_time) : null
  const closeTime = r.close_time ? new Date(r.close_time) : null
  return {
    position_id: r.position_id as string,
    status: r.status as string,
    close_reason: (r.close_reason as string) ?? '',
    close_price: num(r.close_price),
    realized_pnl: num(r.realized_pnl),
    contracts: int(r.contracts),
    total_credit: num(r.total_credit),
    collateral: num(r.collateral_required),
    ticker: (r.ticker as string) ?? 'SPY',
    expiration:
      r.expiration instanceof Date
        ? r.expiration.toISOString().slice(0, 10)
        : String(r.expiration).slice(0, 10),
    put_short_strike: num(r.put_short_strike),
    put_long_strike: num(r.put_long_strike),
    call_short_strike: num(r.call_short_strike),
    call_long_strike: num(r.call_long_strike),
    person: (r.person as string) ?? null,
    account_type: (r.account_type as string) ?? 'sandbox',
    dte_mode: (r.dte_mode as string) ?? '1DTE',
    open_time_iso: openTime ? openTime.toISOString() : null,
    close_time_iso: closeTime ? closeTime.toISOString() : null,
    open_date_ct: ctDate(openTime),
    close_date_ct: ctDate(closeTime),
  }
}

function buildLegSet(p: PositionRow) {
  const occPs = buildOccSymbol(p.ticker, p.expiration, p.put_short_strike, 'P')
  const occPl = buildOccSymbol(p.ticker, p.expiration, p.put_long_strike, 'P')
  const occCs = buildOccSymbol(p.ticker, p.expiration, p.call_short_strike, 'C')
  const occCl = buildOccSymbol(p.ticker, p.expiration, p.call_long_strike, 'C')
  return {
    put_short: occPs,
    put_long: occPl,
    call_short: occCs,
    call_long: occCl,
    asSet: new Set([occPs, occPl, occCs, occCl]),
  }
}

/**
 * Sum the close-side fills on Tradier for ONLY this position's 4 leg symbols.
 *
 * Sign convention follows recoverClosePnlFromOrderHistory in scanner.ts:
 *   buy_to_close  → +debit  (we paid to buy back the short)
 *   sell_to_close → −debit  (we received credit selling the long)
 * close_price = max(0, debit_total / contracts / 100)
 * realized_pnl = (entry_credit − close_price) × 100 × contracts
 *
 * Why leg-symbol filtering is the safe fix:
 *   The previous date-only filter in scanner.ts swept up cross-account fills
 *   on the shared Tradier production account. Filtering by THIS position's
 *   exact 4 OCC symbols (ticker + expiration + strike + P/C) makes that
 *   collision impossible: a leg of a different strategy / underlying /
 *   expiration / strike has a different symbol and is excluded.
 */
function leg_matched_recover(
  orders: TradierOrder[],
  p: PositionRow,
): LegMatchedRecovery | null {
  const legs = buildLegSet(p)

  // Time window: from the position's open through now. We accept fills any
  // time after open because the actual broker close can happen later than
  // the (incorrect) close_time the scanner wrote — e.g. an orphan-cleanup
  // probe wrote close_time on 4/28 but the broker legs actually filled
  // afterwards. We don't lower-bound on close_time for that reason.
  const openMs = p.open_time_iso ? new Date(p.open_time_iso).getTime() : null

  const matchedOrders: LegMatchedRecovery['matched_orders'] = []
  let debitTotal = 0

  for (const o of orders) {
    if (o.class !== 'option' && o.class !== 'multileg') continue
    if (o.status !== 'filled' && o.status !== 'partially_filled') continue

    const txMs = o.transaction_date ? new Date(o.transaction_date).getTime() : null
    if (openMs != null && txMs != null && txMs < openMs) continue

    const orderLegs = o.legs && o.legs.length > 0
      ? o.legs
      : [{
          option_symbol: o.symbol,
          side: o.side,
          quantity: o.quantity,
          exec_quantity: o.exec_quantity,
          last_fill_price: o.last_fill_price ?? o.avg_fill_price,
          type: null,
        }]

    const matchedLegs: LegMatchedRecovery['matched_orders'][number]['legs_matched'] = []
    for (const l of orderLegs) {
      if (!l.option_symbol || !legs.asSet.has(l.option_symbol)) continue
      const sideRaw = (l.side ?? '').toLowerCase()
      if (sideRaw !== 'buy_to_close' && sideRaw !== 'sell_to_close') continue
      const qty = l.exec_quantity ?? l.quantity ?? 0
      const px = l.last_fill_price ?? o.avg_fill_price ?? o.last_fill_price ?? 0
      if (!qty || !px) continue
      const signed = (sideRaw === 'buy_to_close' ? 1 : -1) * px * qty * 100
      debitTotal += signed
      matchedLegs.push({
        option_symbol: l.option_symbol,
        side: l.side,
        qty,
        price: px,
        signed_dollars: Math.round(signed * 100) / 100,
      })
    }

    if (matchedLegs.length > 0) {
      matchedOrders.push({
        order_id: o.id,
        transaction_date: o.transaction_date,
        side: o.side,
        class: o.class,
        legs_matched: matchedLegs,
      })
    }
  }

  if (matchedOrders.length === 0) return null

  const closePrice = Math.max(0, debitTotal / (p.contracts * 100))
  const realized = Math.round((p.total_credit - closePrice) * 100 * p.contracts * 100) / 100

  return {
    close_price: Math.round(closePrice * 10000) / 10000,
    realized_pnl: realized,
    debit_total: Math.round(debitTotal * 100) / 100,
    matched_orders: matchedOrders,
    occ_symbols: {
      put_short: legs.put_short,
      put_long: legs.put_long,
      call_short: legs.call_short,
      call_long: legs.call_long,
    },
  }
}

const ELIGIBLE_REASONS = new Set([
  // Pre-safety-gate Path B writes (the actual root cause for 4/28).
  'broker_position_gone',
  'deferred_broker_gone',
  // Pre-Commit-H Path B writes that have already been backfilled once.
  'broker_gone_backfill_tradier_fill',
  'broker_gone_backfill_pending_limit',
  'broker_gone_backfill_tradier_order_history',
  'broker_gone_backfill_entry_credit_fallback',
])

function eligibilityReason(p: PositionRow): string | null {
  if (p.status !== 'closed') return `status=${p.status} (need 'closed')`
  if (!ELIGIBLE_REASONS.has(p.close_reason)) {
    return `close_reason=${p.close_reason} (not a broker-gone variant)`
  }
  return null
}

async function fetchOrdersForPosition(p: PositionRow): Promise<TradierOrder[] | { error: string }> {
  const accounts = await getLoadedSandboxAccountsAsync()
  const acct = accounts.find((a) => a.name === p.person && a.type === p.account_type)
  if (!acct) {
    return { error: `no loaded account for ${p.person}:${p.account_type}` }
  }
  const accountId = await getAccountIdForKey(acct.apiKey, acct.baseUrl)
  if (!accountId) {
    return { error: 'getAccountIdForKey returned null — Tradier unreachable or key invalid' }
  }
  const orders = await getTradierOrders(acct.apiKey, accountId, acct.baseUrl, 'filled')
  return orders ?? []
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

    const ineligible = eligibilityReason(cand)
    if (ineligible) {
      return NextResponse.json({
        bot: 'spark',
        position_id: positionId,
        dry_run: true,
        eligible: false,
        reason: ineligible,
        current: cand,
      })
    }

    const ordersOrErr = await fetchOrdersForPosition(cand)
    if (!Array.isArray(ordersOrErr)) {
      return NextResponse.json({
        bot: 'spark',
        position_id: positionId,
        dry_run: true,
        eligible: true,
        can_recover: false,
        reason: ordersOrErr.error,
        current: cand,
      })
    }

    const recovery = leg_matched_recover(ordersOrErr, cand)

    return NextResponse.json({
      bot: 'spark',
      position_id: positionId,
      dry_run: true,
      eligible: true,
      can_recover: recovery != null,
      current: cand,
      recovery,
      would_update: recovery
        ? {
            close_price_before: cand.close_price,
            close_price_after: recovery.close_price,
            realized_pnl_before: cand.realized_pnl,
            realized_pnl_after: recovery.realized_pnl,
            realized_pnl_delta: Math.round((recovery.realized_pnl - cand.realized_pnl) * 100) / 100,
            close_reason_after: 'broker_gone_backfill_legmatched',
          }
        : null,
      instructions: recovery
        ? `POST /api/spark/fix-mis-attributed-close?position_id=${positionId}&confirm=true to apply.`
        : 'No leg-matched close fills found on the owning Tradier account. The order history may be outside the broker retention window.',
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

    const ineligible = eligibilityReason(cand)
    if (ineligible) {
      return NextResponse.json({ applied: false, reason: ineligible, current: cand })
    }

    const ordersOrErr = await fetchOrdersForPosition(cand)
    if (!Array.isArray(ordersOrErr)) {
      return NextResponse.json({ applied: false, reason: ordersOrErr.error, current: cand })
    }

    const recovery = leg_matched_recover(ordersOrErr, cand)
    if (!recovery) {
      return NextResponse.json({
        applied: false,
        reason: 'no leg-matched close fills found — broker retention window likely exceeded',
        current: cand,
      })
    }

    const delta = Math.round((recovery.realized_pnl - cand.realized_pnl) * 100) / 100

    // Idempotency: only update if the state we observed is still the state in
    // the DB. If a concurrent writer already corrected the row, we bail.
    const rowsAffected = await dbExecute(
      `UPDATE spark_positions
       SET close_price = $1,
           realized_pnl = $2,
           close_reason = 'broker_gone_backfill_legmatched',
           updated_at = NOW()
       WHERE position_id = $3
         AND status = 'closed'
         AND realized_pnl = $4
         AND close_reason = $5`,
      [recovery.close_price, recovery.realized_pnl, positionId, cand.realized_pnl, cand.close_reason],
    )
    if (rowsAffected === 0) {
      return NextResponse.json({
        applied: false,
        reason: 'UPDATE matched 0 rows — state changed between load and apply',
        current: cand,
      })
    }

    if (delta !== 0) {
      if (cand.account_type === 'production') {
        await dbExecute(
          `UPDATE spark_paper_account
           SET current_balance = current_balance + $1,
               cumulative_pnl  = cumulative_pnl + $1,
               buying_power    = buying_power + $1,
               updated_at = NOW()
           WHERE account_type = 'production' AND person = $2 AND is_active = TRUE AND dte_mode = $3`,
          [delta, cand.person ?? 'User', cand.dte_mode],
        )
      } else {
        await dbExecute(
          `UPDATE spark_paper_account
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
          'BROKER_RECONCILE_LEGMATCHED',
          `LEG-MATCHED RECOVERY: ${positionId} realized_pnl $${cand.realized_pnl.toFixed(2)} → $${recovery.realized_pnl.toFixed(2)} ` +
            `(close_price $${cand.close_price.toFixed(4)} → $${recovery.close_price.toFixed(4)}, delta $${delta.toFixed(2)}, ` +
            `${recovery.matched_orders.length} matched orders)`,
          JSON.stringify({
            event: 'broker_reconcile_legmatched',
            position_id: positionId,
            account_type: cand.account_type,
            person: cand.person,
            entry_credit: cand.total_credit,
            contracts: cand.contracts,
            close_price_before: cand.close_price,
            close_price_after: recovery.close_price,
            realized_pnl_before: cand.realized_pnl,
            realized_pnl_after: recovery.realized_pnl,
            realized_pnl_delta: delta,
            previous_close_reason: cand.close_reason,
            debit_total: recovery.debit_total,
            occ_symbols: recovery.occ_symbols,
            matched_orders: recovery.matched_orders,
          }),
          cand.dte_mode,
          cand.person,
        ],
      )
    } catch { /* audit log best-effort */ }

    const after = await loadCandidate(positionId)
    return NextResponse.json({
      applied: true,
      bot: 'spark',
      position_id: positionId,
      before: cand,
      after,
      recovery,
      delta,
      note: 'Refresh /spark Trade History + Equity Curve to see the corrected P&L.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
