import { NextResponse } from 'next/server'
import { COMMUNITY_PLAN, BOT_PLANS, BOTH_PLAN, TRIAL_DAYS } from '@/lib/billing/plans'

export const dynamic = 'force-dynamic'

/**
 * Public plan catalogue. GET /api/public/plans
 *
 * Read-only, no session, no DB — the mobile app's /enroll/plan screen has no way to
 * import webapp/src/lib/billing/plans.ts directly (separate app, separate bundle), and
 * the enrollment spec is explicit that "every price/doc/plan comes from the API, never
 * a mock constant". Before this route existed there was no way to satisfy that for a
 * mobile client; the web /enroll/plan screen gets away with importing the module
 * because Next.js bundles it straight into the client component.
 *
 * Mirrors lib/billing/plans.ts exactly — this route computes nothing, it only serves
 * what that file already exports, so a price can never drift between the two callers.
 */
export async function GET() {
  return NextResponse.json(
    {
      community: { key: COMMUNITY_PLAN.key, name: COMMUNITY_PLAN.name, price_monthly: COMMUNITY_PLAN.priceMonthly },
      bots: Object.values(BOT_PLANS).map((p) => ({
        slug: p.slug,
        name: p.name,
        blurb: p.blurb,
        price_monthly: p.priceMonthly,
        accent: p.accent,
      })),
      both: { price_monthly: BOTH_PLAN.priceMonthly },
      trial_days: TRIAL_DAYS,
    },
    { headers: { 'Cache-Control': 'public, max-age=300' } },
  )
}
