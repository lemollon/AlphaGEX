import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import RiskForm from './RiskForm'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Risk-assessment onboarding step (suitability → recommended bot). Server-guarded by the
 * onboarding handoff cookie — works even while PUBLIC_MODE bypasses middleware. Reached
 * after the legal step; advisory and never blocks.
 */
export default async function RiskPage() {
  const claims = await verifyOnboardingToken(cookies().get(ONBOARDING_COOKIE)?.value)
  if (!claims) redirect('/login?next=/onboarding/risk')
  return <RiskForm />
}
