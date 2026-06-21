import { NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { decryptSecret } from '@/lib/crypto/secret-box'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Lists the logged-in customer's connected brokerage accounts (post-onboarding dashboard view).
 * Customer-session-guarded (the route self-enforces; the path is on the public allowlist so
 * middleware lets the customer session through). Returns a trimmed projection — never secrets.
 */

interface UserRow {
  snaptrade_user_id: string | null
  snaptrade_user_secret: string | null
}

export async function GET() {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })

  if (!isSnapTradeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT snaptrade_user_id, snaptrade_user_secret FROM users WHERE id = $1 LIMIT 1`,
      [session.customerId],
    )
    const user = rows[0]
    if (!user?.snaptrade_user_id || !user.snaptrade_user_secret) {
      return NextResponse.json({ ok: true, connected: false, accounts: [] })
    }

    const snaptrade = getSnapTrade()
    const res = await snaptrade.accountInformation.listUserAccounts({
      userId: user.snaptrade_user_id,
      userSecret: decryptSecret(user.snaptrade_user_secret),
    })
    const accounts = (Array.isArray(res.data) ? res.data : []).map((a) => ({
      id: a.id,
      name: a.name ?? a.institution_name,
      institution: a.institution_name,
      authorizationId: a.brokerage_authorization,
      balance: a.balance?.total ?? null,
    }))

    return NextResponse.json({ ok: true, connected: accounts.length > 0, accounts })
  } catch (e) {
    console.error('[brokerage/accounts] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong.' }, { status: 500 })
  }
}
