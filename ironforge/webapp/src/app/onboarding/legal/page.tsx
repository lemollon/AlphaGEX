import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import LegalForm from './LegalForm'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Legal & Disclosures onboarding step (sub-project F). Server-guarded: only a holder
 * of a valid signed onboarding cookie may view it — works even while PUBLIC_MODE is on
 * (when middleware is bypassed). The blocking rule: no progress past account creation
 * until email is verified (which is exactly what minted the cookie).
 */
export default async function LegalPage() {
  const token = cookies().get(ONBOARDING_COOKIE)?.value
  const claims = await verifyOnboardingToken(token)
  if (!claims) redirect('/login?next=/onboarding/legal')
  return <LegalForm />
}
