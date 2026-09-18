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
