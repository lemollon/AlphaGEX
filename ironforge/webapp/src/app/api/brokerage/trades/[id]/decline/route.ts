import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/** Customer declines a pending trade approval. Idempotent — only a pending row transitions. */
export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })

  const rows = await customerQuery<{ id: string; user_id: string; status: string }>(
    `SELECT id, user_id, status FROM trade_approvals WHERE id = $1 LIMIT 1`,
    [params.id],
  )
  const appr = rows[0]
  if (!appr || appr.user_id !== session.customerId) {
    return NextResponse.json({ ok: false, error: 'not found' }, { status: 404 })
  }

  await customerExecute(
    `UPDATE trade_approvals SET status = 'declined', decided_at = now() WHERE id = $1 AND status = 'pending'`,
    [appr.id],
  )
  await customerExecute(
    `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'TRADE_DECLINED', $2)`,
    [appr.user_id, JSON.stringify({ approvalId: appr.id })],
  ).catch(() => {})

  return NextResponse.json({ ok: true, status: 'declined' })
}
