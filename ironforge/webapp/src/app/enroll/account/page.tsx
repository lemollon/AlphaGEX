import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { isLiveBot } from '@/lib/live/bots'
import { ownsStrategy } from '@/lib/live/membership'
import SignedInGate from '@/app/signup/SignedInGate'
import SignupClient from '@/app/signup/SignupClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * /enroll/account — STEP 1 of the enrollment rail (10/5 reorder, "Create account").
 *
 * This is now the canonical account-creation screen; /signup is a thin redirect here
 * (forwarding its query string) so existing links/bookmarks keep working. Logic is
 * identical to the former /signup page — same session guard, same SignedInGate /
 * SignupClient split — just relocated so account creation renders inside the
 * enrollment shell/rail rather than before it. See src/app/signup/page.tsx.
 */
export default async function EnrollAccountPage({
  searchParams,
}: {
  searchParams?: { bot?: string }
}) {
  const session = await getCustomerSession()
  if (session.customerId) {
    const bot = searchParams?.bot
    if (isLiveBot(bot) && (await ownsStrategy(session.customerId))) {
      redirect(`/live/${bot}/open`)
    }
    // UAT-007: never silently swallow "create an account" into the EXISTING session's
    // funnel — surface the explicit choice instead.
    let email: string | null = null
    if (isCustomersDbConfigured()) {
      try {
        const rows = await customerQuery<{ email: string }>(
          `SELECT email FROM users WHERE id = $1 LIMIT 1`,
          [session.customerId],
        )
        email = rows[0]?.email ?? null
      } catch { /* interstitial renders without the email */ }
    }
    return <SignedInGate email={email} />
  }
  return <SignupClient />
}
