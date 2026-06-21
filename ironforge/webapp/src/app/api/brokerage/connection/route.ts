import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { decryptSecret } from '@/lib/crypto/secret-box'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Disconnects a brokerage authorization for the logged-in customer (dashboard action).
 * Removes it at SnapTrade, marks the local rows removed, and clears brokerage_connected when
 * no active connection remains. Customer-session-guarded; path is on the public allowlist.
 */

interface UserRow {
  id: string
  snaptrade_user_id: string | null
  snaptrade_user_secret: string | null
}

export async function DELETE(req: NextRequest) {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })

  if (!isSnapTradeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const authorizationId = String(body.authorizationId ?? '')
  if (!authorizationId) {
    return NextResponse.json({ ok: false, error: 'authorizationId is required.' }, { status: 400 })
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, snaptrade_user_id, snaptrade_user_secret FROM users WHERE id = $1 LIMIT 1`,
      [session.customerId],
    )
    const user = rows[0]
    if (!user?.snaptrade_user_id || !user.snaptrade_user_secret) {
      return NextResponse.json({ ok: false, error: 'No brokerage connection found.' }, { status: 404 })
    }

    const snaptrade = getSnapTrade()
    await snaptrade.connections.removeBrokerageAuthorization({
      authorizationId,
      userId: user.snaptrade_user_id,
      userSecret: decryptSecret(user.snaptrade_user_secret),
    })

    await customerExecute(
      `UPDATE brokerage_connections SET status = 'removed', updated_at = now()
         WHERE user_id = $1 AND authorization_id = $2`,
      [user.id, authorizationId],
    )
    await customerExecute(
      `UPDATE users SET brokerage_connected = FALSE, updated_at = now()
         WHERE id = $1
           AND NOT EXISTS (
             SELECT 1 FROM brokerage_connections bc WHERE bc.user_id = $1 AND bc.status = 'active')`,
      [user.id],
    )
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_DISCONNECTED', $2)`,
      [user.id, JSON.stringify({ authorizationId })],
    ).catch(() => {})

    return NextResponse.json({ ok: true })
  } catch (e) {
    console.error('[brokerage/connection] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong.' }, { status: 500 })
  }
}
