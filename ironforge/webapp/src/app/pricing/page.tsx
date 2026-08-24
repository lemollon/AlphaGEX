import type { Metadata } from 'next'
import HomeNav from '../_home/HomeNav'
import { isPublicMode } from '@/lib/auth/access'
import { MembershipSection } from '../_home/sections'
import { LegalFooter, MARKETING_BG } from '../_home/marketing'

/**
 * Membership tiers.
 *
 * HISTORY, so this does not get retired a second time. /pricing was deleted on
 * 2026-07-27 and 308'd to `/#memberships`, on the reasoning that two surfaces
 * stating a price is how they drift apart. That reasoning was sound but the fix
 * was aimed at the wrong thing: the drift came from prices being TYPED in two
 * files, and both cards have read `MARKETING_TIERS` from lib/billing/plans.ts
 * ever since. There is still exactly one source for a price.
 *
 * The page is back because the homepage now renders the approved marketing
 * design, which has no membership section and therefore no `#memberships`
 * anchor. Three live paths need somewhere to send a signed-in customer to see
 * plans — the billing screen's "See plans", the checkout 409 (already
 * subscribed) redirect, and the support knowledge base — and all three would
 * otherwise land on a marketing page with no tiers on it and no anchor to
 * scroll to. A dead scroll target fails silently, which is the worst way for an
 * upgrade path to break.
 *
 * The tier cards themselves are still defined once, in `_home/sections.tsx`,
 * and rendered only here.
 */

export const metadata: Metadata = {
  title: 'Membership — IronForge',
  description:
    'Forge Community and Forge Automate. Daily market intelligence, community access, and automated execution with risk management built in.',
}

export default function PricingPage() {
  return (
    <div className={`min-h-screen ${MARKETING_BG}`}>
      <HomeNav showAll={isPublicMode()} />
      <main className="pt-10">
        <MembershipSection />
      </main>
      <LegalFooter />
    </div>
  )
}
