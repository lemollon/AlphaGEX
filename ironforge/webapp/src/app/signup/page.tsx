import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { nextRouteForOnboarding } from '@/lib/auth/onboarding-route'
import { isLiveBot } from '@/lib/live/bots'
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
 * Where they land:
 *   - ?bot=spark|flame  → that strategy's Open Account page. The CTA carried an intent
 *     ("I want this bot") and a redirect that drops it would be its own small failure.
 *   - otherwise         → nextRouteForOnboarding(), the SAME resolver login uses, so
 *     there is one rule for "where does a returning customer belong" rather than two
 *     that can drift.
 */
export default async function SignupPage({
  searchParams,
}: {
  searchParams?: { bot?: string }
}) {
  const session = await getCustomerSession()
  if (session.customerId) {
    const bot = searchParams?.bot
    redirect(isLiveBot(bot) ? `/live/${bot}/open` : nextRouteForOnboarding(session.onboardingStep))
  }
  return <SignupClient />
}
