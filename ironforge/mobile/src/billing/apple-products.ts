/**
 * Apple product catalogue (Apple IAP handoff, "Mobile contract" §1) — a hand-written
 * mirror of `ironforge/webapp/src/lib/billing/apple-products.ts` (server). Same
 * convention as src/enroll/types.ts: there is no shared package between the two apps,
 * so a drift here is a silent bug rather than a compile error — keep both files in
 * sync by hand whenever the product table changes.
 *
 * Product IDs, bots granted, and prices mirror the Stripe lookup keys in
 * webapp/src/lib/billing/plans.ts (spark_monthly/flame_monthly/both_monthly/
 * community_monthly) — same USD prices, same subscription group ("IronForge
 * Membership", bundle trade.ironforge.app). Apple, not this file, is the source of
 * truth for the actual localized price shown to a customer — see loadProducts() in
 * apple-iap.ts, which asks StoreKit for the real price string per product ID.
 *
 * 🚩 FLAG FOR OPERATOR (2026-10-04): all four products share ONE App Store Connect
 * subscription group ("IronForge Membership"). Apple's platform rule is one ACTIVE
 * subscription per group at a time — buying Flame while Spark is active is an
 * upgrade/downgrade/crossgrade WITHIN that group, not a second stacked
 * subscription. Leron's instruction to "allow buying Spark and Flame as two
 * separate subscriptions" cannot be delivered purely in this client code: the app
 * does not block a second purchase (each enrollment/add-agent pass sells exactly
 * one product and nothing here special-cases "already owns the other"), but
 * Apple's own storefront will not let a customer hold both groups-mates active
 * simultaneously unless Spark and Flame are split into their own separate
 * subscription groups in App Store Connect. That ASC change — not a mobile code
 * change — is what's needed to actually allow holding both at once on iOS.
 */

export interface AppleProduct {
  /** App Store Connect product identifier, e.g. "ironforge.spark.monthly". */
  productId: string
  /** The matching Stripe Price lookup key — how the server correlates the two rails. */
  lookupKey: string
  /** Bot(s) this product grants. 'community' is not a trading bot but is tracked the
   *  same way server-side (customer_bot_subscriptions row with bot = 'community'). */
  bots: string[]
  /** True for the two-bot bundle (both spark and flame in one subscription). */
  bundle: boolean
}

/**
 * PRICING CHANGE (Leron, 2026-10-04, binding): no "Both" bundle any more — Spark
 * and Flame each sell as their own separate subscription. Leron later said to SKIP
 * changing the actual price amounts for this task (2026-10-04, follow-up) — the
 * numbers below are UNCHANGED from main: whatever StoreKit returns per product ID
 * (iOS, via loadProducts() in apple-iap.ts) and whatever webapp/src/lib/billing/
 * plans.ts serves (Android/web Stripe) — this file does not hardcode either.
 *
 * `ironforge.both.monthly` is kept below as LEGACY ONLY — not offered for any new
 * purchase (app/enroll/plan.tsx no longer shows a "Both agents" tile; app/enroll/
 * billing.tsx resolves no Apple product for selected_plan === 'both') — so that an
 * existing customer who already bought the bundle still resolves correctly on
 * restore-purchases / server-side verify. Do not remove this entry; removing it
 * would orphan that customer's entitlement lookup.
 *
 * Ember is NOT listed here: it is free (no monthly fee, no Apple product of any
 * kind — see handoff/ironforge-10.4-design-spec.md §3/§5).
 */
export const APPLE_PRODUCTS: AppleProduct[] = [
  { productId: 'ironforge.both.monthly', lookupKey: 'both_monthly', bots: ['spark', 'flame'], bundle: true },
  { productId: 'ironforge.spark.monthly', lookupKey: 'spark_monthly', bots: ['spark'], bundle: false },
  { productId: 'ironforge.flame.monthly', lookupKey: 'flame_monthly', bots: ['flame'], bundle: false },
  { productId: 'ironforge.community.monthly', lookupKey: 'community_monthly', bots: ['community'], bundle: false },
]

/** Apple product ID for a Stripe lookup key, or null if the key is not sold via Apple. */
export function productIdFor(lookupKey: string): string | null {
  return APPLE_PRODUCTS.find((p) => p.lookupKey === lookupKey)?.productId ?? null
}

/** The catalogue row for an Apple product ID, or null if it is not one of ours — the
 *  caller (verify route, purchase UI) must reject unknown product IDs rather than
 *  silently ignore them. */
export function planFor(productId: string): AppleProduct | null {
  return APPLE_PRODUCTS.find((p) => p.productId === productId) ?? null
}
