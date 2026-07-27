import { permanentRedirect } from 'next/navigation'

/**
 * RETIRED 2026-07-27 — the pricing page is gone.
 *
 * Membership lives on the homepage (`#memberships`), which is the only place
 * the tiers are now defined for visitors. A standalone /pricing page meant two
 * surfaces stating prices, which is how they drift apart.
 *
 * A 308 rather than a delete: /pricing was in the masthead and the footer, so it
 * is linked from outside. The redirect carries that traffic to the membership
 * section instead of 404ing it. The route file stays so surface.ts continues to
 * describe a real route.
 */
export const dynamic = 'force-dynamic'

export default function PricingPage() {
  permanentRedirect('/#memberships')
}
