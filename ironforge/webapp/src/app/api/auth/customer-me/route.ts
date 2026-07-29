import { NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { ownsStrategy, hasActiveMembership } from '@/lib/live/membership'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Who is signed in, and what do they actually own?
 *
 * `ok` means SIGNED IN and nothing more. It has always meant only that, and the existing
 * callers depend on it, so its meaning is unchanged.
 *
 * `ownsStrategy` is ADDED because callers were using `ok` to answer "is this a customer",
 * which it cannot. The marketing nav showed Live to anyone with a free account, because a
 * session was being read as an entitlement. Anything gating on "may they see the product"
 * needs this field, never `ok`.
 */
export async function GET() {
  const session = await getCustomerSession()
  if (!session.customerId) {
    return NextResponse.json({ ok: false }, { status: 401 })
  }
  return NextResponse.json({
    ok: true,
    // Fails closed inside the helper — an entitlement we cannot verify is never advertised.
    ownsStrategy: await ownsStrategy(session.customerId),
    // ANY live subscription — a strategy OR Community. Gates the Community link, which
    // is a $10 product: showing it to someone who has bought nothing advertises a door
    // they cannot walk through. Discovery survives via the homepage membership section,
    // which is where Community is actually sold.
    hasMembership: await hasActiveMembership(session.customerId),
    customer: {
      id: session.customerId,
      email: session.email,
      emailVerified: session.emailVerified,
      onboardingStep: session.onboardingStep,
    },
  })
}
