import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { hasValidServiceToken } from '@/lib/auth/session'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { loadSnapTradeCreds } from '@/lib/brokerage/snaptrade-user'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const APPROVAL_TTL_MS = 5 * 60 * 1000 // a fresh approval must be acted on within 5 minutes

/**
 * GET  — the logged-in customer's recent trade approvals (dashboard).
 * POST — INTERNAL (service-token): create a pending approval from a bot signal. Resolves the
 *        ticker → universal symbol, runs getOrderImpact for the preview + tradeId, stores a
 *        pending row, and (TODO) notifies the customer. This is the seam the scanner / AlphaGEX
 *        calls. It NEVER places an order — placement happens only on explicit customer approval.
 */

interface ApprovalListRow {
  id: string
  bot: string | null
  symbol: string
  action: string
  units: string | null
  order_type: string
  status: string
  preview: unknown
  expires_at: string
  created_at: string
}

export async function GET() {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })

  const rows = await customerQuery<ApprovalListRow>(
    `SELECT id, bot, symbol, action, units, order_type, status, preview, expires_at, created_at
       FROM trade_approvals WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50`,
    [session.customerId],
  )
  return NextResponse.json({ ok: true, approvals: rows })
}

export async function POST(req: NextRequest) {
  if (!hasValidServiceToken(req.headers.get('x-ironforge-service'))) {
    return NextResponse.json({ ok: false, error: 'forbidden' }, { status: 403 })
  }
  if (!isSnapTradeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const userId = String(body.userId ?? '')
  const accountId = String(body.accountId ?? '')
  const symbol = String(body.symbol ?? '').toUpperCase()
  const action = String(body.action ?? '').toUpperCase()
  const units = Number(body.units ?? 0)
  const orderType = (String(body.orderType ?? 'Market') || 'Market') as 'Market' | 'Limit' | 'Stop' | 'StopLimit'
  const timeInForce = (String(body.timeInForce ?? 'Day') || 'Day') as 'Day' | 'FOK' | 'GTC' | 'IOC'
  const bot = body.bot ? String(body.bot) : null

  if (!userId || !accountId || !symbol || (action !== 'BUY' && action !== 'SELL') || !(units > 0)) {
    return NextResponse.json({ ok: false, error: 'userId, accountId, symbol, action(BUY|SELL), units>0 required' }, { status: 400 })
  }

  try {
    const creds = await loadSnapTradeCreds(userId)
    if (!creds) return NextResponse.json({ ok: false, error: 'Customer has no connected brokerage.' }, { status: 409 })

    const snaptrade = getSnapTrade()

    // Resolve ticker → universal symbol for this account.
    const search = await snaptrade.referenceData.symbolSearchUserAccount({
      userId: creds.snaptradeUserId,
      userSecret: creds.userSecret,
      accountId,
      substring: symbol,
    })
    const matches = Array.isArray(search.data) ? search.data : []
    const sym = matches.find((s) => s.symbol === symbol || s.raw_symbol === symbol) ?? matches[0]
    if (!sym) return NextResponse.json({ ok: false, error: `Symbol ${symbol} not tradable on this account.` }, { status: 422 })

    // Preview (fees/impact) + a validated tradeId we can later place.
    const impact = await snaptrade.trading.getOrderImpact({
      userId: creds.snaptradeUserId,
      userSecret: creds.userSecret,
      account_id: accountId,
      action,
      universal_symbol_id: sym.id,
      order_type: orderType,
      time_in_force: timeInForce,
      units,
    })
    const tradeId = impact.data.trade?.id
    if (!tradeId) return NextResponse.json({ ok: false, error: 'Could not price this order.' }, { status: 502 })

    const expiresAt = new Date(Date.now() + APPROVAL_TTL_MS).toISOString()
    const inserted = await customerQuery<{ id: string }>(
      `INSERT INTO trade_approvals
         (user_id, account_id, bot, symbol, action, units, order_type, preview, snaptrade_trade_id, status, expires_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'pending',$10)
       RETURNING id`,
      [
        userId, accountId, bot, symbol, action, units, orderType,
        JSON.stringify({
          impacts: impact.data.trade_impacts ?? null,
          remainingBalance: impact.data.combined_remaining_balance ?? null,
        }),
        tradeId, expiresAt,
      ],
    )

    // TODO(notify): email/push the customer that a trade is awaiting approval (fast-follow).
    await customerQuery(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'TRADE_APPROVAL_CREATED', $2)`,
      [userId, JSON.stringify({ approvalId: inserted[0].id, symbol, action, units, bot })],
    ).catch(() => {})

    return NextResponse.json({ ok: true, approvalId: inserted[0].id, expiresAt })
  } catch (e) {
    console.error('[trades:create] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong creating the approval.' }, { status: 500 })
  }
}
