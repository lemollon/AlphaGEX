import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { COMMUNITY_KEY } from '@/lib/billing/plans'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Read-only report: who is STILL being charged for Community (Leron, 2026-10-05,
 * binding — Community is now free for every NEW signup; checkout no longer offers
 * community_monthly). Existing paying subscribers are deliberately left alone —
 * "DO NOT cancel or refund anything automatically" — so this endpoint exists purely
 * to give Leron the list he needs to decide what (if anything) happens to them.
 *
 * A row counts here only if `stripe_subscription_id IS NOT NULL` — the free grant
 * written by checkout/webhook for a new Community member leaves that column NULL,
 * so this report can never mistake a free member for a paying one.
 *
 * GET /api/ops/community-paid-subscribers (operator session required; same
 * public-mode bypass every other read-only ops report uses).
 */

interface PaidCommunityRow {
  user_id: string
  email: string | null
  first_name: string | null
  last_name: string | null
  status: string
  stripe_subscription_id: string
  price_lookup_key: string | null
  current_period_end: string | null
  created_at: string
}

export async function GET() {
  if (!isPublicMode()) {
    const ops = await getSession()
    if (!ops.userId) {
      return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
    }
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Customers DB not configured.' }, { status: 503 })
  }

  const rows = await customerQuery<PaidCommunityRow>(
    `SELECT s.user_id, u.email, u.first_name, u.last_name, s.status,
            s.stripe_subscription_id, s.price_lookup_key,
            to_char(s.current_period_end, 'YYYY-MM-DD') AS current_period_end,
            to_char(s.created_at, 'YYYY-MM-DD') AS created_at
       FROM customer_bot_subscriptions s
       JOIN users u ON u.id = s.user_id
      WHERE s.bot = $1
        AND s.stripe_subscription_id IS NOT NULL
        AND s.status IN ('trialing', 'active', 'past_due')
      ORDER BY s.created_at ASC`,
    [COMMUNITY_KEY],
  )

  return NextResponse.json({
    ok: true,
    count: rows.length,
    subscribers: rows.map((r) => ({
      userId: r.user_id,
      email: r.email,
      name: `${r.first_name ?? ''} ${r.last_name ?? ''}`.trim(),
      status: r.status,
      stripeSubscriptionId: r.stripe_subscription_id,
      priceLookupKey: r.price_lookup_key,
      currentPeriodEnd: r.current_period_end,
      memberSince: r.created_at,
    })),
  })
}
