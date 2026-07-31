'use client'

import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { MARKETING_TIERS, TRIAL_DAYS } from '@/lib/billing/plans'

/**
 * PLAN-01 — Choose membership (July 29 handoff).
 *
 * Two tiles: Forge Community vs Forge Automate. "Forge Automate $50" is
 * PRESENTATION of the automate FAMILY — billing stays per-bot (spark/flame are both
 * $50/mo); the AGENT-01 choice decides which Stripe price is actually subscribed at
 * activation. The enrollment persists selected_plan='automate' here and the agent is
 * never a second plan write.
 *
 * Prices and names come from lib/billing/plans.ts, never frontend constants, so this
 * tile can't quote a number Stripe no longer charges.
 */

const COMMUNITY_FEATURES = [
  'AI market briefings',
  'Daily market commentary',
  'Member discussions',
  'Educational content',
  'Trade reviews',
  'Community access',
]

const AUTOMATE_FEATURES = [
  'Automated execution',
  'Risk-managed strategy',
  'Connected brokerage',
  'Real-time monitoring',
  'Trade history',
  'Performance dashboard',
]

function FeatureList({ items, checkClass }: { items: string[]; checkClass: string }) {
  return (
    <ul className="mt-4 grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
      {items.map((f) => (
        <li key={f} className="flex items-start gap-2 text-sm text-gray-300">
          <span aria-hidden className={`mt-0.5 font-bold ${checkClass}`}>✓</span>
          {f}
        </li>
      ))}
    </ul>
  )
}

export default function PlanClient() {
  const { enrollment, busy, setBusy, error, setError, call, router } = useEnrollment('plan')

  async function choose(plan: 'community' | 'automate') {
    if (!enrollment) return
    setBusy(true)
    setError(null)
    try {
      await call(`/api/v1/enrollments/${enrollment.id}/plan`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ plan }),
      })
      // Community has no standalone legal screen — its clickwrap lives at billing.
      router.push(plan === 'community' ? '/enroll/billing' : '/enroll/legal')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your selection.')
      setBusy(false)
    }
  }

  return (
    <EnrollShell
      headline="Choose how you enter the Forge."
      subline="Start with Community or unlock automated execution."
      maxWidthClass="max-w-3xl"
    >
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <h2 className="text-2xl font-bold text-white">Choose your membership</h2>
        <p className="mt-1 text-sm text-gray-400">Select the experience that fits how you want to use IronForge.</p>

        {error ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}

        {!enrollment && !error ? (
          <div className="mt-6 h-72 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        {enrollment ? (
          <div className="mt-6 grid gap-5 md:grid-cols-2">
            {/* Forge Community — orange outline + accents per the approved reference (UAT-009) */}
            <div className="flex flex-col rounded-xl border border-amber-500/50 bg-black/20 p-6">
              <h3 className="text-xl font-bold">
                <span className="text-white">Forge </span>
                <span className="text-amber-500">Community</span>
              </h3>
              <p className="mt-1 text-sm text-gray-400">The foundation.</p>
              <FeatureList items={COMMUNITY_FEATURES} checkClass="text-amber-500" />
              <div className="mt-auto pt-6">
                <div className="border-t border-forge-border pt-5">
                  <span className="text-3xl font-bold text-white">${MARKETING_TIERS.community.priceMonthly}</span>
                  <span className="ml-1 text-sm text-gray-500">/month</span>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => choose('community')}
                  className="mt-4 w-full rounded-lg bg-amber-500 px-5 py-3 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Join Community
                </button>
              </div>
            </div>

            {/* Forge Automate */}
            <div className="relative flex flex-col rounded-xl border border-emerald-500/50 bg-black/20 p-6">
              <span className="absolute -top-3 right-5 rounded-full border border-emerald-500/50 bg-emerald-950 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                {TRIAL_DAYS} trading day free trial
              </span>
              {/* Fully green per the approved reference (UAT-009) — heading + checks
                  included, not just outline/badge/CTA. */}
              <h3 className="text-xl font-bold">
                <span className="text-white">Forge </span>
                <span className="text-emerald-400">Automate</span>
              </h3>
              <p className="mt-1 text-sm text-gray-400">Everything in Forge Community, plus:</p>
              <FeatureList items={AUTOMATE_FEATURES} checkClass="text-emerald-400" />
              <div className="mt-auto pt-6">
                <div className="border-t border-forge-border pt-5">
                  <span className="text-3xl font-bold text-white">${MARKETING_TIERS.starter.priceMonthly}</span>
                  <span className="ml-1 text-sm text-gray-500">/month</span>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => choose('automate')}
                  className="mt-4 w-full rounded-lg bg-emerald-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Start {TRIAL_DAYS}-Day Free Trial
                </button>
                <p className="mt-2 text-center text-xs text-gray-500">No long-term commitment. Cancel anytime.</p>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </EnrollShell>
  )
}
