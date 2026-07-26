import Link from 'next/link'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { BOT_PLANS } from '@/lib/billing/plans'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Completion screen — now the bridge from the funnel to the sale. The primary
 * action opens an account (Spark or Flame), which starts checkout; "I'll do this
 * later" drops to the dashboard. Previously this dead-ended on "billing coming
 * soon" + a lone dashboard link, so a finished signup had nothing to DO next and
 * had to discover checkout on their own under /live.
 */
export default async function OnboardingCompletePage() {
  // Reachable by a valid onboarding handoff cookie OR a logged-in customer session.
  const claims = await verifyOnboardingToken(cookies().get(ONBOARDING_COOKIE)?.value)
  const session = await getCustomerSession()
  if (!claims && !session.customerId) redirect('/login?next=/onboarding/complete')

  const strategies = [
    { ...BOT_PLANS.spark, tagline: 'Next-day SPY spreads', accent: '#2F80ED' },
    { ...BOT_PLANS.flame, tagline: 'Two-day SPY spreads', accent: '#FD5301' },
  ]

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-lg rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-400">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6"><path d="M20 6 9 17l-5-5" /></svg>
          </div>
          <h1 className="mt-4 text-xl font-bold text-white">You&apos;re set up — one step to go live</h1>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-gray-400">
            Your account and disclosures are on file. Pick a strategy to open its account and start
            your 5-day free trial — no charge today, cancel anytime.
          </p>
        </div>

        <div className="mt-6 grid gap-3">
          {strategies.map((s) => (
            <Link
              key={s.slug}
              href={`/live/${s.slug}/open`}
              className="group flex items-center gap-4 rounded-xl border border-white/10 bg-forge-bg/50 p-4 transition hover:border-white/25"
              style={{ borderLeft: `3px solid ${s.accent}` }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={s.mascot} alt="" className="h-11 w-11 shrink-0 object-contain" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-base font-bold text-white">{s.name}</span>
                  <span className="rounded-full border px-2 py-0.5 text-[11px] font-medium" style={{ borderColor: `${s.accent}66`, color: s.accent }}>${s.priceMonthly}/mo</span>
                </div>
                <div className="text-xs text-gray-400">{s.tagline}</div>
              </div>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 shrink-0 text-gray-500 transition group-hover:translate-x-0.5 group-hover:text-white"><path d="m9 18 6-6-6-6" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </Link>
          ))}
        </div>

        <p className="mt-4 text-center text-xs text-gray-500">
          Running both? Add the second for <span className="text-gray-300">+$25/mo</span> — $75 total.
        </p>

        <div className="mt-6 border-t border-white/10 pt-5 text-center">
          <Link href="/performance" className="text-sm text-gray-400 transition hover:text-white">I&apos;ll do this later — go to my dashboard</Link>
        </div>
      </div>
    </div>
  )
}
