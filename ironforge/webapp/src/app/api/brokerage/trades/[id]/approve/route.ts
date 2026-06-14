import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { decideApproval, type ApprovalStatus } from '@/lib/brokerage/approval'
import { loadSnapTradeCreds } from '@/lib/brokerage/snaptrade-user'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * COMPLIANCE-CRITICAL: this is the ONLY place IronForge places a real broker order, and it does
 * so only after the account owner explicitly approves, and only while the approval is still
 * pending + unexpired (decideApproval gate). No discretionary / blanket placement exists.
 */

interface ApprovalRow {
  id: string
  user_id: string
  status: ApprovalStatus
  expires_at: string
  snaptrade_trade_id: string | null
}

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })
  if (!isSnapTradeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  try {
    const rows = await customerQuery<ApprovalRow>(
      `SELECT id, user_id, status, expires_at, snaptrade_trade_id FROM trade_approvals WHERE id = $1 LIMIT 1`,
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

    const creds = await loadSnapTradeCreds(appr.user_id)
    if (!creds || !appr.snaptrade_trade_id) {
      return NextResponse.json({ ok: false, error: 'This trade can no longer be placed.' }, { status: 409 })
    }

    try {
      const snaptrade = getSnapTrade()
      const placed = await snaptrade.trading.placeOrder({
        tradeId: appr.snaptrade_trade_id,
        userId: creds.snaptradeUserId,
        userSecret: creds.userSecret,
      })
      const data = placed.data as { brokerage_order_id?: string; id?: string }
      const orderId = data.brokerage_order_id ?? data.id ?? null

      await customerExecute(
        `UPDATE trade_approvals SET status = 'placed', placed_order_id = $2, decided_at = now() WHERE id = $1`,
        [appr.id, orderId],
      )
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'TRADE_PLACED', $2)`,
        [appr.user_id, JSON.stringify({ approvalId: appr.id, orderId })],
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
      return NextResponse.json(
        { ok: false, status: 'failed', error: 'The broker rejected the order.' },
        { status: 502 },
      )
    }
  } catch (e) {
    console.error('[trades/approve] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong.' }, { status: 500 })
  }
}
