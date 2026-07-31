import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { hasActiveMembership } from '@/lib/live/membership'
import EnrollShell from '../EnrollShell'
import TradingViewPerkCard from '@/components/customer/TradingViewPerkCard'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Welcome to the Forge — IronForge',
  description: 'Your membership is active.',
}

/**
 * Enrollment completion landing — the Community checkout success return
 * (Automate never lands here: activation routes straight to /live per DASH-FIRST-01).
 *
 * NOT static: this page ASSERTS "Membership active", so it must verify it (UAT-007 —
 * the static version told every session holder they were in, including brand-new
 * accounts that had bought nothing). hasActiveMembership fails closed, and anyone
 * without a live subscription is bounced to /enroll, which resumes their real state.
 * Webhook lag is covered: the checkout return path runs resume-time reconciliation
 * before landing here, so a just-paid member has their subscription row already.
 */
export default async function EnrollDonePage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  if (!(await hasActiveMembership(session.customerId))) redirect('/enroll')
  return (
    <EnrollShell headline="Welcome to the Forge." subline="Your membership is active." topRight="none">
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-400">
          Membership active
        </span>
        <h2 className="mt-4 text-2xl font-bold text-white">You’re in.</h2>
        <p className="mt-2 text-sm leading-relaxed text-gray-400">
          Your Forge Community membership is live — briefings, market commentary, and member
          discussions are open to you now.
        </p>
        <Link
          href="/community"
          className="mt-6 inline-flex rounded-lg bg-amber-500 px-5 py-3 text-sm font-semibold text-black transition hover:bg-amber-400"
        >
          Enter the Community
        </Link>
      </div>

      {/* First perk, offered right where membership begins. Optional — skipping it
          here loses nothing; the same card lives at /account/tradingview. */}
      <div className="mt-4">
        <TradingViewPerkCard />
      </div>
    </EnrollShell>
  )
}
