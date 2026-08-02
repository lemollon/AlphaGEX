import { NextRequest, NextResponse } from 'next/server'
import { revokeRefreshToken, revokeAllForUser } from '@/lib/auth/mobile-session'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Sign out. `{ scope: 'all' }` signs out every device and invalidates outstanding
 * access tokens (needs a valid bearer to prove who is asking); the default signs out
 * only the device whose refresh token is presented.
 *
 * Always returns 200. Logout is not an oracle: telling a caller that their token was
 * already invalid reveals token state to whoever holds a stolen value, and there is
 * nothing the client would do differently either way.
 */
export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>

  if (body.scope === 'all') {
    const identity = await getCustomerIdentity({ verifyEpoch: true })
    if (!identity) {
      return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
    }
    await revokeAllForUser(identity.customerId, 'logout_all')
    return NextResponse.json({ ok: true, scope: 'all' })
  }

  const refreshToken = String(body.refreshToken ?? '')
  if (refreshToken) await revokeRefreshToken(refreshToken, 'logout')
  return NextResponse.json({ ok: true, scope: 'device' })
}
