import { NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { CustomersDbNotConfiguredError } from '@/lib/customers-db'
import { getUnreadCount, markRead } from '@/lib/community/store'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function dbUnavailable() {
  return NextResponse.json({ error: 'Community is not available yet.' }, { status: 503 })
}

/**
 * Community unread count (mobile fidelity #229 — `tabBarBadge` had nothing real to
 * read from). Cookie OR mobile bearer, same as every other /api/community/* route.
 * Logged-out viewers get 0 rather than a 401 — there is nothing to mark unread for
 * someone who has never read anything, and a badge that errors for a signed-out
 * visitor is worse than one that is just quietly zero.
 */
export async function GET() {
  try {
    const identity = await getCustomerIdentity()
    if (!identity?.customerId) return NextResponse.json({ unread_count: 0 })
    const unread_count = await getUnreadCount(identity.customerId)
    return NextResponse.json({ unread_count })
  } catch (e) {
    if (e instanceof CustomersDbNotConfiguredError) return dbUnavailable()
    console.error('[community/unread] GET failed:', e)
    return NextResponse.json({ error: 'Failed to load unread count.' }, { status: 500 })
  }
}

/** Marks the feed read as of now — called when the Community tab opens/focuses. */
export async function POST() {
  try {
    const identity = await getCustomerIdentity()
    if (!identity?.customerId) {
      return NextResponse.json({ error: 'Log in to continue.' }, { status: 401 })
    }
    await markRead(identity.customerId)
    return NextResponse.json({ ok: true })
  } catch (e) {
    if (e instanceof CustomersDbNotConfiguredError) return dbUnavailable()
    console.error('[community/unread] POST failed:', e)
    return NextResponse.json({ error: 'Failed to mark read.' }, { status: 500 })
  }
}
