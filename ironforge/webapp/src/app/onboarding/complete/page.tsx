import Link from 'next/link'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { BOT_PLANS } from '@/lib/billing/plans'
import { BOT_RATIONALE, type RecommendedBot } from '@/lib/onboarding/risk-scoring'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Final onboarding step — the bridge from the funnel to the sale. It carries the
 * risk quiz's recommended strategy through (highlighted + ordered first) so the
 * quiz actually pays off, and the primary action opens that account (checkout).
 * "I'll do this later" drops to the dashboard. Previously this dead-ended on
 * "billing coming soon" and the quiz's recommendation was dropped on the floor.
 */
export default async function OnboardingCompletePage() {
  const claims = await verifyOnboardingToken(cookies().get(ONBOARDING_COOKIE)?.value)
  const session = await getCustomerSession()
  if (!claims && !session.customerId) redirect('/login?next=/onboarding/complete')

  // Recommended strategy from the risk step (users.recommended_bot). INFERNO isn't
  // a customer product, so only SPARK/FLAME map to a highlighted purchasable plan.
  const uid = claims?.uid ?? session.customerId ?? null
  let recommended: RecommendedBot | null = null
  if (uid && isCustomersDbConfigured()) {
    try {
      const rows = await customerQuery<{ recommended_bot: string | null }>(
        `SELECT recommended_bot FROM users WHERE id = $1 LIMIT 1`,
        [uid],
      )
      const raw = (rows[0]?.recommended_bot ?? '').toString().toUpperCase()
      if (raw === 'SPARK' || raw === 'FLAME' || raw === 'INFERNO') recommended = raw as RecommendedBot
    } catch { /* recommendation is a nicety, never block the page */ }
  }
  const recSlug = recommended === 'FLAME' ? 'flame' : recommended === 'SPARK' ? 'spark' : null

  const base = [
    { ...BOT_PLANS.spark, tagline: 'Next-day SPY spreads', accent: '#2F80ED' },
    { ...BOT_PLANS.flame, tagline: 'Two-day SPY spreads', accent: '#FD5301' },
  ]
  // Order the recommended strategy first.
  const strategies = recSlug ? [...base].sort((a, b) => (a.slug === recSlug ? -1 : b.slug === recSlug ? 1 : 0)) : base

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-lg rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
        <div className="text-center">
          <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-amber-500">Final step · open your account</div>
          <div className="mx-auto mt-3 flex h-11 w-11 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-400">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6"><path d="M20 6 9 17l-5-5" /></svg>
          </div>
          <h1 className="mt-4 text-xl font-bold text-white">You&apos;re set up — one step to go live</h1>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-gray-400">
            {recSlug
              ? 'Based on your answers, we’ve matched you to a strategy. Open its account to start your 5-day free trial — no charge today, cancel anytime.'
              : 'Pick a strategy to open its account and start your 5-day free trial — no charge today, cancel anytime.'}
          </p>
        </div>

        <div className="mt-6 grid gap-3">
          {strategies.map((s) => {
            const isRec = s.slug === recSlug
            return (
              <Link
                key={s.slug}
                href={`/live/${s.slug}/open`}
                className={`group flex items-center gap-4 rounded-xl border bg-forge-bg/50 p-4 transition ${isRec ? 'border-white/25 ring-1 ring-inset' : 'border-white/10 hover:border-white/25'}`}
                style={{ borderLeft: `3px solid ${s.accent}`, ...(isRec ? { boxShadow: `inset 0 0 0 1px ${s.accent}55` } : {}) }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={s.mascot} alt="" className="h-11 w-11 shrink-0 object-contain" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-base font-bold text-white">{s.name}</span>
                    {isRec && <span className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider" style={{ background: `${s.accent}22`, color: s.accent }}>Recommended for you</span>}
                    <span className="rounded-full border px-2 py-0.5 text-[11px] font-medium" style={{ borderColor: `${s.accent}66`, color: s.accent }}>${s.priceMonthly}/mo</span>
                  </div>
                  <div className="text-xs text-gray-400">{isRec && recommended ? BOT_RATIONALE[recommended] : s.tagline}</div>
                </div>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 shrink-0 text-gray-500 transition group-hover:translate-x-0.5 group-hover:text-white"><path d="m9 18 6-6-6-6" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </Link>
            )
          })}
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
