import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { isLiveBot } from '@/lib/live/bots'
import { ownsStrategy } from '@/lib/live/membership'
import SignedInGate from './SignedInGate'
import SignupClient from './SignupClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Signup, guarded against people who already have an account.
 *
 * Nothing here checked for a session, so a SIGNED-IN customer who clicked any
 * "Get started" CTA was handed the create-an-account form and asked for their name,
 * email, phone, state and a password — for the account they were already logged into.
 * The same defect was fixed on the /live empty state (#2633), but that was one of nine
 * doors: the homepage has three of these CTAs, /how-it-works three, /bot-ledger two,
 * plus bookmarks and external links that no per-CTA branch could ever cover.
 *
 * So the guard lives HERE, at the destination, where every entry passes through — and
 * server-side, so a signed-in visitor never sees a flash of the form before bouncing.
 *
 * Where they land (cutover 7/30, revised for UAT-007):
 *   - EXISTING strategy owner with ?bot= intent → that bot's Open Account page, which
 *     still owns the second-bot bundle upgrade ($75 total, not a second $50 sub).
 *   - everyone else signed-in → SignedInGate: an explicit "continue as {email} / sign
 *     out & create a new account" choice. The old silent redirect to /enroll swallowed
 *     a genuine create-account intent into the previous user's session — a new tester
 *     "inherited" another account's membership (UAT-007).
 */
export default async function SignupPage({
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
    // funnel — that read as inheriting another user's membership. Surface the choice.
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
