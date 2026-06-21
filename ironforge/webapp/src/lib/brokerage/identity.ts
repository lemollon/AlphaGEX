import type { NextRequest } from 'next/server'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerSession } from '@/lib/auth/customer-session-server'

/**
 * Resolve the IronForge `users.id` for a brokerage request from EITHER the signed onboarding
 * handoff cookie (during the onboarding funnel, before a login session exists) OR a logged-in
 * customer session (managing the connection later from the dashboard). Returns null if neither.
 */
export async function resolveCustomerUserId(req: NextRequest): Promise<string | null> {
  const claims = await verifyOnboardingToken(req.cookies.get(ONBOARDING_COOKIE)?.value)
  if (claims?.uid) return claims.uid
  const session = await getCustomerSession()
  return session.customerId ?? null
}
