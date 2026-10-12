import { NextRequest, NextResponse } from 'next/server'
import { requireIdentityWithStepUp } from '@/lib/auth/mobile-step-up'
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
 *
 * Mobile callers must present a step-up token (MOBILE_SESSION_POLICY.stepUpActions includes
 * 'trade_approve') — same gate as brokerage connect/disconnect and account deletion. See
 * @/lib/auth/mobile-step-up. Cookie (web dashboard) sessions are unaffected.
 *
 * Immediately before the real broker call, claimApproval() atomically flips the row
 * pending -> approved (`UPDATE ... WHERE status='pending' ... `, checked by rowcount). Only the
 * caller that wins that race may place the order — a concurrent duplicate (double-tap, a client
 * retry after a timeout) gets a clean 409 instead of a second real order.
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

/**
 * Atomically flip a still-pending, unexpired approval to 'approved'. Returns false if a
 * concurrent request already claimed (or the window lapsed on) it — the caller must not
 * place an order in that case.
 */
async function claimApproval(id: string): Promise<boolean> {
  const count = await customerExecute(
    `UPDATE trade_approvals SET status = 'approved', decided_at = now()
       WHERE id = $1 AND status = 'pending' AND expires_at > now()`,
    [id],
  )
  return count > 0
}

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const { identity, error } = await requireIdentityWithStepUp()
  if (error === 'step_up_required') {
    return NextResponse.json({ ok: false, error: 'step_up_required' }, { status: 401 })
  }
  const session = { customerId: identity?.customerId ?? null }
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

    // No column captures a limit/stop price, so a Limit order would be sent priceless and a
    // Stop/StopLimit would silently become a market order — the customer approves one order
    // and a different one executes. Fail closed rather than guess, same philosophy as the
    // unsupported-provider branch below.
    if ((appr.order_type || '').toLowerCase() !== 'market') {
      return NextResponse.json(
        {
          ok: false,
          error: `${appr.order_type} orders aren't supported yet — only market orders can be approved.`,
        },
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
        if (!(await claimApproval(appr.id))) {
          return NextResponse.json({ ok: false, error: 'This trade can no longer be approved.' }, { status: 409 })
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
        if (!(await claimApproval(appr.id))) {
          return NextResponse.json({ ok: false, error: 'This trade can no longer be approved.' }, { status: 409 })
        }
        const res = await tradierPlaceOrder(decryptSecret(enc), appr.account_id, {
          symbol: appr.symbol,
          side: appr.action.toLowerCase() === 'sell' ? 'sell' : 'buy',
          quantity: Number(appr.units ?? 0),
          type: 'market',
          duration: 'day',
        })
        orderId = res.orderId
      } else {
        // unsupported / unknown provider — never guess which broker to send a real order to.
        return NextResponse.json({ ok: false, error: 'This trade cannot be placed.' }, { status: 409 })
      }

      try {
        await customerExecute(
          `UPDATE trade_approvals SET status = 'placed', placed_order_id = $2, decided_at = now()
             WHERE id = $1 AND status = 'approved'`,
          [appr.id, orderId],
        )
      } catch (writeErr) {
        // The broker call above already succeeded — this order is real and live. Failing to
        // record that must never be reported as "the broker rejected the order" (false, and
        // could prompt a dangerous manual retry) or leave the row looking re-approvable.
        console.error('[trades/approve] order placed but status write failed — needs manual reconciliation:', {
          approvalId: appr.id,
          orderId,
          writeErr,
        })
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'TRADE_PLACED_STATUS_WRITE_FAILED', $2)`,
          [appr.user_id, JSON.stringify({ approvalId: appr.id, provider: appr.provider, orderId })],
        ).catch(() => {})
        return NextResponse.json({
          ok: true,
          status: 'placed',
          orderId,
          warning: 'Order placed, but confirming its status is taking longer than usual.',
        })
      }

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
        `UPDATE trade_approvals SET status = 'failed', error = $2, decided_at = now()
           WHERE id = $1 AND status = 'approved'`,
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
