import { NextRequest, NextResponse } from 'next/server'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * SnapTrade webhook listener (no session — verified by shared secret in the body). Keeps
 * brokerage_connections.status in sync as connections are added/broken/removed and touches
 * last_synced_at on holdings updates. Always 200s after a valid secret so SnapTrade does not
 * retry-storm; 401 only on a bad/missing secret. Public path (self-guarded by the secret).
 */
export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>

  const expected = process.env.SNAPTRADE_WEBHOOK_SECRET
  if (!expected || body.webhookSecret !== expected) {
    return NextResponse.json({ ok: false }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: true })

  const eventType = String(body.eventType ?? body.type ?? '')
  const snaptradeUserId = body.userId ? String(body.userId) : null
  const authorizationId = body.brokerageAuthorizationId ? String(body.brokerageAuthorizationId) : null

  // Map SnapTrade events → our connection status.
  const statusByEvent: Record<string, string> = {
    CONNECTION_ADDED: 'active',
    CONNECTION_UPDATED: 'active',
    CONNECTION_FIXED: 'active',
    CONNECTION_BROKEN: 'disabled',
    CONNECTION_DELETED: 'removed',
    CONNECTION_REMOVED: 'removed',
  }

  try {
    if (eventType === 'ACCOUNT_HOLDINGS_UPDATED' && snaptradeUserId) {
      await customerExecute(
        `UPDATE brokerage_connections SET last_synced_at = now(), updated_at = now()
           WHERE user_id = (SELECT id FROM users WHERE snaptrade_user_id = $1)`,
        [snaptradeUserId],
      )
    } else if (statusByEvent[eventType] && snaptradeUserId) {
      const newStatus = statusByEvent[eventType]
      await customerExecute(
        `UPDATE brokerage_connections SET status = $3, updated_at = now()
           WHERE user_id = (SELECT id FROM users WHERE snaptrade_user_id = $1)
             AND ($2::text IS NULL OR authorization_id = $2)`,
        [snaptradeUserId, authorizationId, newStatus],
      )
      // If a connection broke/was removed and none remain active, clear the user flag.
      await customerExecute(
        `UPDATE users SET brokerage_connected = FALSE, updated_at = now()
           WHERE snaptrade_user_id = $1
             AND NOT EXISTS (
               SELECT 1 FROM brokerage_connections bc
                WHERE bc.user_id = users.id AND bc.status = 'active')`,
        [snaptradeUserId],
      )
    }
  } catch (e) {
    console.error('[brokerage/webhook] update failed:', eventType, e)
    // Still 200 — SnapTrade retries are not helpful for our internal write failures.
  }

  return NextResponse.json({ ok: true })
}
