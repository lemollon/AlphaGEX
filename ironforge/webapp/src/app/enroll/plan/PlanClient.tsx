'use client'

import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { COMMUNITY_PLAN, BOT_PLANS } from '@/lib/billing/plans'
import { EMBER_AGENT } from '@/lib/agents/ember'

/**
 * PLAN-01 — Choose your plan.
 *
 * Four direct tiles: Community, Spark, Flame, Ember — the real plans this deployment
 * sells. Replaces the July 29 two-tile "Forge Automate" design (Leron, 2026-10-04):
 * that design persisted selected_plan='automate' as a family placeholder and deferred
 * the actual bot choice to agent setup, which Apple's In-App Purchase can't do — you
 * pay for a specific product at purchase time, not a deferred-choice family. Web and
 * mobile now pick the real plan up front, same as checkout already bills it.
 *
 * "Both agents" removed 2026-10-04 (Leron, binding) — no bundle plan for new
 * enrollments. A customer wanting Spark AND Flame runs this flow twice (two separate
 * $50/mo subscriptions); legacy both_monthly subscribers keep their existing bundle
 * (see lib/billing/plans.ts BOTH_PLAN, lib/billing/membership.ts resolvePlan).
 *
 * Prices come from lib/billing/plans.ts, never a frontend constant, so a tile
 * can't quote a number Stripe no longer charges. Ember is free and not Stripe-backed —
 * its price/limits come from lib/agents/ember.ts.
 */

type PlanSlug = 'community' | 'spark' | 'flame' | 'ember'

interface TileSpec {
  slug: PlanSlug
  name: string
  blurb: string
  price: number
  accent: string
  note?: string
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
      slug: 'ember',
      name: EMBER_AGENT.name,
      blurb: EMBER_AGENT.blurb,
      price: EMBER_AGENT.priceMonthly,
      accent: EMBER_AGENT.accent,
      note: '$500–$2,000 accounts · one per person',
    },
  ]

  return (
    <EnrollShell
      headline="Choose how you enter the Forge."
      subline="Pick the agent (or agents) you want running, or start with Community."
      maxWidthClass="max-w-3xl"
      step="plan"
      enrollment={enrollment}
    >
      {error ? <p className="err" style={{ marginBottom: 14 }}>{error}</p> : null}

      {!enrollment && !error ? <div className="card pad" style={{ height: 280 }} /> : null}

      {enrollment ? (
        <div className="agents">
          {tiles.map((tile) => (
            <button
              key={tile.slug}
              type="button"
              disabled={busy}
              onClick={() => choose(tile.slug)}
              className="agent"
              style={{ borderColor: `${tile.accent}80` }}
            >
              <span className="av" aria-hidden="true" />
              <span>
                <h3 style={{ color: tile.accent }}>{tile.name}</h3>
                <span className="sub">{tile.blurb}</span>
                {tile.note ? <span className="tags"><span>{tile.note}</span></span> : null}
              </span>
              <span className={`pr ${tile.price === 0 ? 'free' : ''}`}>
                {tile.price === 0 ? (
                  <b>Free</b>
                ) : (
                  <>
                    <b>${tile.price}</b>
                    <small>/month</small>
                  </>
                )}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </EnrollShell>
  )
}
