import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerQuery, customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Mark notification history rows read (10.4 gap audit).
 *
 * Body `{ id: string }` marks one row read; `{ all: true }` (or no body at all — the
 * mobile "Mark all read" action) marks every unread row for the caller read. Always
 * scoped to `user_id = $1` from the authenticated identity, never a client-supplied
 * owner — same rule as the device/preferences routes.
 */
export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const id = typeof body.id === 'string' ? body.id : null

  if (id) {
    await customerExecute(
      `UPDATE customer_notifications
          SET read_at = now()
        WHERE id = $1 AND user_id = $2 AND read_at IS NULL`,
      [id, identity.customerId],
    )
  } else {
    await customerExecute(
      `UPDATE customer_notifications
          SET read_at = now()
        WHERE user_id = $1 AND read_at IS NULL`,
      [identity.customerId],
    )
  }

  const [{ count }] = await customerQuery<{ count: string }>(
    `SELECT count(*)::text AS count FROM customer_notifications WHERE user_id = $1 AND read_at IS NULL`,
    [identity.customerId],
  )

  return NextResponse.json({ ok: true, unread_count: Number(count ?? 0) })
}
