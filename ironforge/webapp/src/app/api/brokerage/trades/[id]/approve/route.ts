import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { decideApproval, type ApprovalStatus } from '@/lib/brokerage/approval'
import { resolvePlacement } from '@/lib/brokerage/placement'
import { loadSnapTradeCreds } from '@/lib/brokerage/snaptrade-user'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { decryptSecret } from '@/lib/crypto/secret-box'
import { isTradierOAuthConfigured, placeOrder as tradierPlaceOrder } from '@/lib/tradier-oauth'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * COMPLIANCE-CRITICAL: the ONLY place IronForge places a real broker order, and only after the
 * account owner explicitly approves while the approval is still pending + unexpired
 * (decideApproval gate). Placement dispatches on the stored provider (SnapTrade vs Tradier);
 * the gate, ownership check, and "no place without approval" invariant are provider-agnostic.
 */
interface ApprovalRow {
  id: string
  user_id: string
  status: ApprovalStatus
  expires_at: string
  provider: string
  snaptrade_trade_id: string | null
  account_id: string
  symbol: string
  action: string
  units: string | null
  order_type: string
}

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })

  try {
    const rows = await customerQuery<ApprovalRow>(
      `SELECT id, user_id, status, expires_at, provider, snaptrade_trade_id,
              account_id, symbol, action, units, order_type
         FROM trade_approvals WHERE id = $1 LIMIT 1`,
      [params.id],
    )
    const appr = rows[0]
    if (!appr || appr.user_id !== session.customerId) {
      return NextResponse.json({ ok: false, error: 'not found' }, { status: 404 })
    }

    const gate = decideApproval({ status: appr.status, now: new Date(), expiresAt: new Date(appr.expires_at) })
    if (gate === 'invalid') {
      return NextResponse.json({ ok: false, error: 'This trade can no longer be approved.' }, { status: 409 })
    }
    if (gate === 'expired') {
      await customerExecute(
        `UPDATE trade_approvals SET status = 'expired', decided_at = now() WHERE id = $1 AND status = 'pending'`,
        [appr.id],
      )
      return NextResponse.json(
        { ok: false, code: 'expired', error: 'This trade request expired. A new one is needed.' },
        { status: 409 },
      )
    }

    const target = resolvePlacement(appr.provider)

    try {
      let orderId: string | null = null

      if (target === 'snaptrade') {
        if (!isSnapTradeConfigured()) return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
        const creds = await loadSnapTradeCreds(appr.user_id)
        if (!creds || !appr.snaptrade_trade_id) {
          return NextResponse.json({ ok: false, error: 'This trade can no longer be placed.' }, { status: 409 })
        }
        const placed = await getSnapTrade().trading.placeOrder({
          tradeId: appr.snaptrade_trade_id,
          userId: creds.snaptradeUserId,
          userSecret: creds.userSecret,
        })
        const data = placed.data as { brokerage_order_id?: string; id?: string }
        orderId = data.brokerage_order_id ?? data.id ?? null
      } else if (target === 'tradier') {
        if (!isTradierOAuthConfigured()) return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
        const trows = await customerQuery<{ tradier_access_token: string | null }>(
          `SELECT tradier_access_token FROM users WHERE id = $1 LIMIT 1`,
          [appr.user_id],
        )
        const enc = trows[0]?.tradier_access_token
        if (!enc) return NextResponse.json({ ok: false, error: 'This trade can no longer be placed.' }, { status: 409 })
        const res = await tradierPlaceOrder(decryptSecret(enc), appr.account_id, {
          symbol: appr.symbol,
          side: appr.action.toLowerCase() === 'sell' ? 'sell' : 'buy',
          quantity: Number(appr.units ?? 0),
          type: appr.order_type?.toLowerCase() === 'limit' ? 'limit' : 'market',
          duration: 'day',
        })
        orderId = res.orderId
      } else {
        // unsupported / unknown provider — never guess which broker to send a real order to.
        return NextResponse.json({ ok: false, error: 'This trade cannot be placed.' }, { status: 409 })
      }

      await customerExecute(
        `UPDATE trade_approvals SET status = 'placed', placed_order_id = $2, decided_at = now() WHERE id = $1`,
        [appr.id, orderId],
      )
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'TRADE_PLACED', $2)`,
        [appr.user_id, JSON.stringify({ approvalId: appr.id, provider: appr.provider, orderId })],
      ).catch(() => {})

      return NextResponse.json({ ok: true, status: 'placed', orderId })
    } catch (e) {
      const detail =
        (e as { response?: { data?: unknown } })?.response?.data
          ? JSON.stringify((e as { response: { data: unknown } }).response.data).slice(0, 300)
          : e instanceof Error ? e.message : 'place failed'
      await customerExecute(
        `UPDATE trade_approvals SET status = 'failed', error = $2, decided_at = now() WHERE id = $1`,
        [appr.id, detail],
      )
      console.error('[trades/approve] placeOrder failed:', detail)
      return NextResponse.json({ ok: false, status: 'failed', error: 'The broker rejected the order.' }, { status: 502 })
    }
  } catch (e) {
    console.error('[trades/approve] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong.' }, { status: 500 })
  }
}
