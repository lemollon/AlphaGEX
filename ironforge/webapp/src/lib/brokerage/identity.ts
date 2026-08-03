import type { NextRequest } from 'next/server'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'

/**
 * Resolve the IronForge `users.id` for a brokerage request from any of the three ways a
 * caller can legitimately prove who they are:
 *
 *  1. the signed onboarding handoff cookie — the funnel, before a login session exists;
 *  2. a logged-in customer session cookie — the web dashboard;
 *  3. a mobile bearer token — the app.
 *
 * (3) was missing, and it made the whole mobile brokerage flow unreachable: the callback
 * had been taught to work without a cookie, but CONNECT still 401'd every bearer caller,
 * so the app could never start a connection in the first place. Caught by an end-to-end
 * run against the sandbox with a real token — every unit test passed without it.
 *
 * Onboarding cookie stays FIRST: during the funnel that cookie is the only credential a
 * half-signed-up user has, and it must keep winning.
 */
export async function resolveCustomerUserId(req: NextRequest): Promise<string | null> {
  const claims = await verifyOnboardingToken(req.cookies.get(ONBOARDING_COOKIE)?.value)
  if (claims?.uid) return claims.uid
  const identity = await getCustomerIdentity()
  return identity?.customerId ?? null
}
