'use client'

import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { COMMUNITY_PLAN, BOT_PLANS, BOTH_PLAN } from '@/lib/billing/plans'

/**
 * PLAN-01 — Choose your plan.
 *
 * Four direct tiles: Community, Spark, Flame, Both agents — the same four options
 * mobile's app/enroll/plan.tsx has always shown. Replaces the July 29 two-tile
 * "Forge Automate" design (Leron, 2026-10-04): that design persisted
 * selected_plan='automate' as a family placeholder and deferred the actual
 * bot choice to agent setup, which Apple's In-App Purchase can't do — you pay for
 * a specific product at purchase time, not a deferred-choice family. Web and
 * mobile now pick the real plan up front, same as checkout already bills it.
 *
 * Prices come from lib/billing/plans.ts, never a frontend constant, so a tile
 * can't quote a number Stripe no longer charges.
 */

type PlanSlug = 'community' | 'spark' | 'flame' | 'both'

interface TileSpec {
  slug: PlanSlug
  name: string
  blurb: string
  price: number
  accent: string
}

export default function PlanClient() {
  const { enrollment, busy, setBusy, error, setError, call, router } = useEnrollment('plan')

  async function choose(plan: PlanSlug) {
    if (!enrollment || busy) return
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

  const tiles: TileSpec[] = [
    {
      slug: 'community',
      name: COMMUNITY_PLAN.name,
      blurb: 'Chat, education, and market commentary. No trading bot.',
      price: COMMUNITY_PLAN.priceMonthly,
      accent: '#F59E0B', // amber, matches the prior Community tile
    },
    {
      slug: 'spark',
      name: BOT_PLANS.spark.name,
      blurb: BOT_PLANS.spark.blurb,
      price: BOT_PLANS.spark.priceMonthly,
      accent: BOT_PLANS.spark.accent,
    },
    {
      slug: 'flame',
      name: BOT_PLANS.flame.name,
      blurb: BOT_PLANS.flame.blurb,
      price: BOT_PLANS.flame.priceMonthly,
      accent: BOT_PLANS.flame.accent,
    },
    {
      slug: 'both',
      name: 'Both agents',
      blurb: 'Spark and Flame together, one bundle price.',
      price: BOTH_PLAN.priceMonthly,
      accent: '#F59E0B',
    },
  ]

  return (
    <EnrollShell
      headline="Choose how you enter the Forge."
      subline="Pick the agent (or agents) you want running, or start with Community."
      maxWidthClass="max-w-3xl"
    >
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <h2 className="text-2xl font-bold text-white">Choose your plan</h2>
        <p className="mt-1 text-sm text-gray-400">Select the experience that fits how you want to use IronForge.</p>

        {error ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}

        {!enrollment && !error ? (
          <div className="mt-6 h-72 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        {enrollment ? (
          <div className="mt-6 flex flex-col gap-4">
            {tiles.map((tile) => (
              <button
                key={tile.slug}
                type="button"
                disabled={busy}
                onClick={() => choose(tile.slug)}
                className="flex w-full items-center justify-between gap-4 rounded-xl border bg-black/20 p-6 text-left transition hover:bg-black/30 disabled:cursor-not-allowed disabled:opacity-50"
                style={{ borderColor: `${tile.accent}80` }}
              >
                <div>
                  <h3 className="text-lg font-bold text-white">{tile.name}</h3>
                  <p className="mt-1 text-sm text-gray-400">{tile.blurb}</p>
                </div>
                <div className="shrink-0 text-right">
                  <span className="text-2xl font-bold" style={{ color: tile.accent }}>
                    ${tile.price}
                  </span>
                  <span className="ml-1 text-sm text-gray-500">/mo</span>
                </div>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </EnrollShell>
  )
}
