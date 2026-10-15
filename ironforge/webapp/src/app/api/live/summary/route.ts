import { NextRequest, NextResponse } from 'next/server'
import { getLiveSummary } from '@/lib/live/summary'
import { resolveLiveViewer } from '@/lib/live/viewer'
import { getMembership } from '@/lib/live/membership'
import { getActivationConfirmation } from '@/lib/live/activation-confirmation'
import { getMilestones } from '@/lib/live/milestones'

export const dynamic = 'force-dynamic'

/**
 * Customer Live page — full-page payload (hero state, account, market
 * conditions, intraday equity). Polled at ~60s by the client.
 * Account-aware: ?account=spark|flame, authorized server-side per viewer
 * (operators see all; customers only their mapped bots; anonymous = spark).
 */
export async function GET(req: NextRequest) {
  try {
    const raw = req.nextUrl.searchParams.get('mode')
    const modeParam = raw === 'paper' ? 'paper' as const
      : (raw === 'live' || raw === 'production') ? 'production' as const
      : undefined
    const viewer = await resolveLiveViewer(req)
    // DASH-FIRST-01: attached BEFORE the empty-return on purpose — a just-activated
    // customer typically has no ironforge_customer_bots mapping yet, so their first
    // entry lands on the empty branch, and that is exactly the moment the activation
    // confirmation must render.
    //
    // membership is fetched here too, same reasoning: a Community-only member (no
    // Spark/Flame bot) always lands on the empty branch below, and used to get no
    // `membership` key at all — every page that reads CustomerShell's plan card off
    // this response (dashboard, brokerage, settings, community) showed "No
    // membership" for a real, active (free) Community member, contradicting the
    // Billing page's own separate /api/billing/entitlements-based fetch, which
    // correctly showed "Active". getMembership() already reads the billing DB, not
    // the trading one getLiveSummary below depends on, so it needs no bot to resolve.
    const [activationConfirmation, membership] = await Promise.all([
      getActivationConfirmation(viewer.customerId),
      getMembership(viewer.customerId),
    ])
    if (!viewer.bot) {
      // Viewer has no live account (fresh signup / anonymous): empty state,
      // never another account's data.
      return NextResponse.json({ empty: true, viewer, activation_confirmation: activationConfirmation, membership })
    }
    const [summary, milestones] = await Promise.all([
      getLiveSummary(viewer.bot, {
        allowAggregate: viewer.isOperator,
        person: viewer.person,
        // ?mode=paper|live — FLAME has both a $2,000 paper ledger and a live
        // account, and the page lets the viewer switch. Anything else is ignored
        // and the bot's default mode applies.
        mode: modeParam,
      }),
      // Same pattern as membership above: getLiveSummary has no customerId, so
      // it returns milestones: null; this resolves the real tenure/scan-count
      // badges and the spread below replaces the placeholder.
      getMilestones(viewer.customerId, viewer.bot),
    ])
    return NextResponse.json({ ...summary, membership, viewer, activation_confirmation: activationConfirmation, milestones })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
