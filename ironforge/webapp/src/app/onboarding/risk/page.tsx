import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import RiskForm from './RiskForm'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Risk-assessment onboarding step (suitability → recommended bot). Server-guarded by the
 * onboarding handoff cookie OR a signed-in customer session — works even while
 * PUBLIC_MODE bypasses middleware. Reached after the legal step; advisory and never blocks.
 *
 * Session fallback for the same reason as /onboarding/legal: the onboarding cookie is
 * device-local and 7-day-lived, so a customer at onboarding_step 'legal_accepted' who
 * logs in from another device would be redirected here, bounced back to /login, and see
 * "nothing happens" forever. See that page for the full write-up.
 */
export default async function RiskPage() {
  const claims = await verifyOnboardingToken(cookies().get(ONBOARDING_COOKIE)?.value)
  const session = await getCustomerSession()
  if (!claims && !session.customerId) redirect('/login?next=/onboarding/risk')
  return <RiskForm />
}
