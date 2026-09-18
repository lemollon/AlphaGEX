/**
 * Apple In-App Purchase product catalogue — the StoreKit mirror of lib/billing/plans.ts.
 * Same USD prices, same bots granted, ONE subscription group ("IronForge Membership") so
 * a customer can only ever hold one active tier at a time on iOS.
 *
 * This mapping lives ONCE, here. `ironforge/mobile/src/billing/apple-products.ts` is a
 * verbatim copy for the client bundle (mobile can't import server code) — if the two ever
 * drift, the client will offer a product the server rejects at /api/billing/apple/verify.
 *
 * Bundle ID: trade.ironforge.app. App Apple ID: 6804037937.
 */

export interface AppleProduct {
  /** App Store Connect product id, e.g. "ironforge.spark.monthly". */
  productId: string
  /** The matching Stripe Price lookup key — same catalogue row on both rails. */
  lookupKey: string
  /** Bots (or 'community') this product grants. */
  bots: string[]
  /** True for the two-bot bundle product. */
  bundle: boolean
}

export const APPLE_PRODUCTS: AppleProduct[] = [
  { productId: 'ironforge.both.monthly', lookupKey: 'both_monthly', bots: ['spark', 'flame'], bundle: true },
  { productId: 'ironforge.spark.monthly', lookupKey: 'spark_monthly', bots: ['spark'], bundle: false },
  { productId: 'ironforge.flame.monthly', lookupKey: 'flame_monthly', bots: ['flame'], bundle: false },
  { productId: 'ironforge.community.monthly', lookupKey: 'community_monthly', bots: ['community'], bundle: false },
]

/** Stripe lookup key -> Apple product id, for surfaces that only know the Stripe key. */
export function productIdFor(lookupKey: string): string | null {
  return APPLE_PRODUCTS.find((p) => p.lookupKey === lookupKey)?.productId ?? null
}

/** Apple product id -> catalogue row, for decoding a StoreKit transaction's productId. */
export function planFor(productId: string): AppleProduct | null {
  return APPLE_PRODUCTS.find((p) => p.productId === productId) ?? null
}
