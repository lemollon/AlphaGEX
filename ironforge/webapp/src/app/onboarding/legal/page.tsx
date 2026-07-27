import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import LegalForm from './LegalForm'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Legal & Disclosures onboarding step (sub-project F). Server-guarded: viewable by a
 * holder of a valid signed onboarding cookie, OR by a signed-in customer resuming
 * onboarding. Works even while PUBLIC_MODE is on (when middleware is bypassed). The
 * blocking rule: no progress past account creation until email is verified (which is
 * exactly what minted the cookie).
 *
 * The SESSION fallback is not optional. The onboarding cookie is minted at signup, is
 * DEVICE-LOCAL and expires in 7 days, so a customer who signs up on a laptop and later
 * logs in on their phone arrives here with no token at all. Requiring the token alone
 * made login look broken: sign-in SUCCEEDED, redirected here (onboarding_step
 * 'email_verified' resolves to /onboarding/legal), this guard bounced straight back to
 * /login, and the user saw "nothing happens" — an unbreakable loop locking them out of
 * their own account with no error message anywhere.
 *
 * /onboarding/brokerage and /onboarding/complete already accepted a session; legal and
 * risk did not. Middleware also lets a logged-in customer through ("A logged-in customer
 * can resume onboarding via their own session cookie") — this makes the page agree with
 * the middleware instead of silently overriding it.
 */
export default async function LegalPage() {
  const claims = await verifyOnboardingToken(cookies().get(ONBOARDING_COOKIE)?.value)
  const session = await getCustomerSession()
  if (!claims && !session.customerId) redirect('/login?next=/onboarding/legal')
  return <LegalForm />
}
