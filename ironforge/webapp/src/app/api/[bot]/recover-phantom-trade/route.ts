import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import {
  buildOccSymbol,
  getAccountIdForKey,
  getProductionAccountsForBot,
  getTradierOrders,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * Reconciliation companion to /api/{bot}/audit-phantom-closes.
 *
 * For a single phantom-suspect production position, fetches Tradier's
 * filled-order history and recomputes close_price / realized_pnl from
 * actual fills. If no matching close orders exist between open_time and
 * expiration+2 days, marks the row as "expired_worthless" (close_price=0,
 * realized_pnl = total_credit * 100 * contracts).
 *
 * Matching strategy:
 *   - Filter Tradier orders to filled/partially_filled options (or multileg)
 *   - Side must be buy_to_close or sell_to_close
 *   - At least one of the order's legs has option_symbol equal to one of
 *     the position's 4 OCC leg symbols (put_short, put_long, call_short,
 *     call_long), OR the order is a multileg whose legs collectively cover
 *     all 4 strikes.
 *   - transaction_date must be in [open_time, expiration + 2 days CT]
 *
 * GET  preview only (no writes)
 * POST applies the fix when ?confirm=true
 *
 * Usage:
 *   GET  /api/spark/recover-phantom-trade?position_id=SPARK-20260428-06B2CE-prod-logan
 *   POST /api/spark/recover-phantom-trade?position_id=SPARK-20260428-06B2CE-prod-logan&confirm=true
 */

interface MatchedOrder {
  order_id: string | number | null
  transaction_date: string | null
  side: string | null
  class: string | null
  total_quantity: number
  total_fill_dollars: number
  matched_legs: { option_symbol: string; side: string | null; quantity: number | null; fill_price: number | null }[]
}

async function buildRecoveryPlan(bot: string, positionId: string) {
  // 1. Fetch position
  const posRows = await dbQuery(
    `SELECT position_id, account_type, person, expiration, open_time, close_time,
            put_short_strike, put_long_strike, call_short_strike, call_long_strike,
            contracts, total_credit, close_price, realized_pnl, close_reason,
            ticker, status, dte_mode
     FROM ${botTable(bot, 'positions')}
     WHERE position_id = $1
     LIMIT 1`,
    [positionId],
  )
  if (!posRows.length) {
    return { error: `position_id ${positionId} not found in ${bot}_positions` as const, status: 404 }
  }
  const pos = posRows[0]
  const accountType = (pos.account_type || 'sandbox') as string
  if (accountType !== 'production') {
    return {
      error: `position ${positionId} has account_type='${accountType}'; recovery is production-only` as const,
      status: 400,
    }
  }
  const person = pos.person as string | null
  if (!person) {
    return { error: `position ${positionId} has no person; cannot fetch broker history` as const, status: 400 }
  }

  const ticker = (pos.ticker as string) || 'SPY'
  const ps = num(pos.put_short_strike)
  const pl = num(pos.put_long_strike)
  const cs = num(pos.call_short_strike)
  const cl = num(pos.call_long_strike)
  const contracts = int(pos.contracts)
  const entryCredit = num(pos.total_credit)
  const expirationStr = pos.expiration?.toISOString?.()?.slice(0, 10)
    ?? (pos.expiration ? String(pos.expiration).slice(0, 10) : null)
  if (!expirationStr) {
    return { error: `position ${positionId} has no expiration; cannot match orders` as const, status: 400 }
  }
  const openTime = pos.open_time ? new Date(pos.open_time) : null
  if (!openTime || isNaN(openTime.getTime())) {
    return { error: `position ${positionId} has no open_time; cannot match orders` as const, status: 400 }
  }
  // Window: from open_time → expiration day + 2 (covers same-day, next-day, and a day of slack)
  const expirationEndUtc = new Date(`${expirationStr}T23:59:59Z`)
  const windowEnd = new Date(expirationEndUtc.getTime() + 2 * 24 * 60 * 60 * 1000)

  // 2. Build expected leg OCC symbols
  const occPs = buildOccSymbol(ticker, expirationStr, ps, 'P')
  const occPl = buildOccSymbol(ticker, expirationStr, pl, 'P')
  const occCs = buildOccSymbol(ticker, expirationStr, cs, 'C')
  const occCl = buildOccSymbol(ticker, expirationStr, cl, 'C')
  const expectedLegSet = new Set([occPs, occPl, occCs, occCl])

  // 3. Find production account for this person
  const prodAccts = await getProductionAccountsForBot(bot)
  const prodAcct = prodAccts.find((a) => a.name === person)
  if (!prodAcct) {
    return {
      error: `no production account loaded for person='${person}' (bot=${bot})` as const,
      status: 400,
    }
  }
  const accountId = prodAcct.accountId ?? (await getAccountIdForKey(prodAcct.apiKey, prodAcct.baseUrl))
  if (!accountId) {
    return {
      error: `failed to resolve Tradier accountId for person='${person}'` as const,
      status: 502,
    }
  }

  // 4. Fetch all filled Tradier orders and match
  const orders = await getTradierOrders(prodAcct.apiKey, accountId, prodAcct.baseUrl, 'filled')
  const matched: MatchedOrder[] = []
  let debitTotal = 0
  for (const o of orders) {
    if (o.class !== 'option' && o.class !== 'multileg') continue
    if (o.status !== 'filled' && o.status !== 'partially_filled') continue
    // Side check on order-level OR leg-level (multileg orders sometimes have null top-level side)
    const orderSide = (o.side ?? '').toLowerCase()
    if (!o.transaction_date) continue
    const txMs = Date.parse(o.transaction_date)
    if (!Number.isFinite(txMs)) continue
    if (txMs < openTime.getTime()) continue
    if (txMs > windowEnd.getTime()) continue

    // Match legs against this position's OCC symbols
    const matchedLegs = o.legs.filter((l) => l.option_symbol && expectedLegSet.has(l.option_symbol))
    if (matchedLegs.length === 0) continue

    let orderDollarValue = 0
    let totalQty = 0
    const legSummary: MatchedOrder['matched_legs'] = []
    for (const leg of matchedLegs) {
      const legSide = (leg.side ?? orderSide ?? '').toLowerCase()
      if (legSide !== 'buy_to_close' && legSide !== 'sell_to_close') continue
      const qty = leg.exec_quantity ?? leg.quantity ?? 0
      const px = leg.last_fill_price ?? 0
      if (!qty || !px) continue
      const dollarValue = px * qty * 100
      orderDollarValue += legSide === 'buy_to_close' ? dollarValue : -dollarValue
      totalQty += qty
      legSummary.push({ option_symbol: leg.option_symbol!, side: leg.side, quantity: qty, fill_price: px })
    }

    // For single-leg option orders, leg.side may be missing — fall back to order-level side
    if (legSummary.length === 0 && o.class === 'option' && (orderSide === 'buy_to_close' || orderSide === 'sell_to_close')) {
      const qty = o.exec_quantity ?? o.quantity ?? 0
      const px = o.avg_fill_price ?? o.last_fill_price ?? 0
      if (qty && px) {
        const dollarValue = px * qty * 100
        orderDollarValue = orderSide === 'buy_to_close' ? dollarValue : -dollarValue
        totalQty = qty
        legSummary.push({
          option_symbol: matchedLegs[0]?.option_symbol ?? null as unknown as string,
          side: orderSide,
          quantity: qty,
          fill_price: px,
        })
      }
    }

    if (legSummary.length === 0) continue
    debitTotal += orderDollarValue
    matched.push({
      order_id: o.id,
      transaction_date: o.transaction_date,
      side: o.side,
      class: o.class,
      total_quantity: totalQty,
      total_fill_dollars: Math.round(orderDollarValue * 100) / 100,
      matched_legs: legSummary,
    })
  }

  // 5. Compute new values
  const maxProfit = Math.round(entryCredit * 100 * contracts * 100) / 100
  let newClosePrice: number
  let newRealizedPnl: number
  let recoveryVerdict: 'tradier_order_history' | 'expired_worthless'
  if (matched.length === 0) {
    // No close fills found → assume expired worthless (max profit kept)
    newClosePrice = 0
    newRealizedPnl = maxProfit
    recoveryVerdict = 'expired_worthless'
  } else {
    const closeBasePrice = debitTotal / (contracts * 100)
    newClosePrice = Math.round(Math.max(0, closeBasePrice) * 10000) / 10000
    newRealizedPnl = Math.round((entryCredit - newClosePrice) * 100 * contracts * 100) / 100
    recoveryVerdict = 'tradier_order_history'
  }

  return {
    plan: {
      position_id: positionId,
      person,
      account_id: accountId,
      ticker,
      expiration: expirationStr,
      strikes: { put_long: pl, put_short: ps, call_short: cs, call_long: cl },
      contracts,
      entry_credit: entryCredit,
      window_utc: { from: openTime.toISOString(), to: windowEnd.toISOString() },
      stored: {
        close_price: num(pos.close_price),
        realized_pnl: num(pos.realized_pnl),
        close_reason: pos.close_reason,
        status: pos.status,
        close_time: pos.close_time?.toISOString?.() ?? pos.close_time,
      },
      matched_orders: matched,
      debit_total_dollars: Math.round(debitTotal * 100) / 100,
      proposed: {
        close_price: newClosePrice,
        realized_pnl: newRealizedPnl,
        close_reason: recoveryVerdict === 'expired_worthless'
          ? 'expired_worthless_recovered'
          : 'broker_position_gone_recovered',
        recovery_source: recoveryVerdict,
      },
      delta: {
        close_price_change: Math.round((newClosePrice - num(pos.close_price)) * 10000) / 10000,
        realized_pnl_change: Math.round((newRealizedPnl - num(pos.realized_pnl)) * 100) / 100,
      },
    },
    pos,
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const positionId = req.nextUrl.searchParams.get('position_id')
  if (!positionId) return NextResponse.json({ error: 'position_id query param is required' }, { status: 400 })

  try {
    const result = await buildRecoveryPlan(bot, positionId)
    if ('error' in result) return NextResponse.json({ error: result.error }, { status: result.status })
    return NextResponse.json({ mode: 'preview', ...result.plan })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const positionId = req.nextUrl.searchParams.get('position_id')
  if (!positionId) return NextResponse.json({ error: 'position_id query param is required' }, { status: 400 })
  const confirm = req.nextUrl.searchParams.get('confirm') === 'true'

  try {
    const result = await buildRecoveryPlan(bot, positionId)
    if ('error' in result) return NextResponse.json({ error: result.error }, { status: result.status })

    if (!confirm) {
      return NextResponse.json({ mode: 'preview_via_post', note: 'pass &confirm=true to apply', ...result.plan })
    }

    // Apply the update
    const dte = dteMode(bot)
    const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
    const rowsAffected = await dbExecute(
      `UPDATE ${botTable(bot, 'positions')}
       SET close_price = $1,
           realized_pnl = $2,
           close_reason = $3,
           updated_at = NOW()
       WHERE position_id = $4 ${dteFilter}`,
      [result.plan.proposed.close_price, result.plan.proposed.realized_pnl, result.plan.proposed.close_reason, positionId],
    )

    return NextResponse.json({
      mode: 'applied',
      rows_affected: rowsAffected,
      ...result.plan,
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
