/**
 * App-store rules that decide what the BILLING surface is allowed to show.
 *
 * Extracted from the Account screen so the rule has exactly one definition and can be
 * tested without a renderer. A `Platform.OS === 'ios'` check buried in JSX is invisible
 * to review and impossible to assert on.
 */

/**
 * Whether the app may surface an in-app route into the Stripe Customer Portal.
 *
 * FALSE on iOS. App Review Guideline 3.1.1 bars "buttons, external links, or other
 * calls to action that direct customers to purchasing mechanisms other than in-app
 * purchase". The portal session the server creates uses Stripe's DEFAULT configuration,
 * which permits *changing plan* — so the button is not merely a link near a purchase
 * surface, it IS one, one tap from the $15 / $50 / $75 tiers.
 *
 * This is not a workaround, it is the shipped product decision: v1 is sign-in only and
 * enrollment stays on the web precisely so the app never becomes a purchase surface.
 * Members keep full billing control at ironforge.trade.
 *
 * 🚨 Do NOT flip this to true on the strength of the 2025 US link-out allowance. That
 * allowance is per-storefront and does not cover a portal that can change plan; the
 * cost of being wrong is a rejection on a first submission, which is the slowest
 * possible way to find out.
 */
export function canManageBillingInApp(platformOS: string): boolean {
  return platformOS !== 'ios'
}

/**
 * Whether the membership PRICE may be rendered.
 *
 * True everywhere, including iOS: showing what an existing subscriber already pays is
 * account information, not a call to action. Kept as a named rule so that if a future
 * screen ever pairs a price with a tap target, both halves are decided in one place.
 */
export function canShowMembershipPrice(_platformOS: string): boolean {
  return true
}
