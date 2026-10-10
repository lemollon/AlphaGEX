import { redirect } from 'next/navigation'
import { cookies } from 'next/headers'
import {
  verifyGooglePendingSignupState,
  GOOGLE_PENDING_SIGNUP_COOKIE,
} from '@/lib/auth/google-pending-signup-cookie'
import EnrollShell from '@/app/enroll/EnrollShell'
import GoogleConsentClient from './GoogleConsentClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * One-time consent screen for a Google sign-in that the callback determined
 * would CREATE a new account with no consents captured (i.e. it started from
 * /login, not /signup — see google/callback/route.ts). Server-verifies the
 * signed, httpOnly google-pending-signup cookie before rendering anything: a
 * missing, tampered, or expired cookie never reaches the consent form — it
 * bounces back to /signup with an error the page's own ContinueWithGoogle
 * already knows how to show.
 */
export default async function GoogleConsentPage() {
  const token = cookies().get(GOOGLE_PENDING_SIGNUP_COOKIE)?.value
  const pending = await verifyGooglePendingSignupState(token)
  if (!pending) {
    redirect('/signup?googleError=consent_expired')
  }

  return (
    <EnrollShell
      headline="Built for disciplined execution."
      subline="Confirm a few things to finish setting up your account."
      topRight="login"
      maxWidthClass="max-w-2xl"
    >
      <GoogleConsentClient email={pending.email} />
    </EnrollShell>
  )
}
