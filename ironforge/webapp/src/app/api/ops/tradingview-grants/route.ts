import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { isUuid } from '@/lib/enrollment/ids'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Operator view of the TradingView indicator grant queue (7/30 perk).
 *
 * GET  → pending + recently granted usernames (the durable record behind the ntfy ping)
 * POST → { user_id } marks the grant done after the operator adds the username to the
 *        invite-only script's access list in the TradingView UI.
 *
 * Same auth pattern as ops/billing-readiness: public-mode deployments (ironforge-legacy)
 * have no login wall so no session can exist there; everywhere else an operator session
 * is required. Emails are operator-facing contact data, not customer-visible output.
 */
async function authorized(): Promise<boolean> {
  if (isPublicMode()) return true
  const ops = await getSession()
  return Boolean(ops.userId)
}

export async function GET() {
  if (!(await authorized())) {
    return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: true, pending: [], granted: [] })

  const rows = await customerQuery<{
    id: string
    email: string | null
    tradingview_username: string
    tradingview_granted_at: string | null
  }>(
    `SELECT id, email, tradingview_username, tradingview_granted_at
       FROM users
      WHERE tradingview_username IS NOT NULL
      ORDER BY tradingview_granted_at NULLS FIRST, updated_at DESC
      LIMIT 200`,
    [],
  )
  return NextResponse.json({
    ok: true,
    pending: rows.filter((r) => !r.tradingview_granted_at).map((r) => ({
      user_id: r.id,
      email: r.email,
      username: r.tradingview_username,
    })),
    granted: rows.filter((r) => r.tradingview_granted_at).map((r) => ({
      user_id: r.id,
      username: r.tradingview_username,
      granted_at: r.tradingview_granted_at,
    })),
  })
}

export async function POST(req: NextRequest) {
  if (!(await authorized())) {
    return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as { user_id?: unknown }
  const userId = typeof body.user_id === 'string' ? body.user_id : ''
  // Non-UUID would RAISE on the cast, not match zero rows.
  if (!isUuid(userId)) return NextResponse.json({ ok: false, error: 'bad user_id' }, { status: 422 })

  const n = await customerExecute(
    `UPDATE users SET tradingview_granted_at = now(), updated_at = now()
      WHERE id = $1 AND tradingview_username IS NOT NULL AND tradingview_granted_at IS NULL`,
    [userId],
  )
  await customerExecute(
    `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'TRADINGVIEW_ACCESS_GRANTED', '{}')`,
    [userId],
  ).catch(() => {})
  return NextResponse.json({ ok: true, updated: n })
}
