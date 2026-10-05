/**
 * The "Due after setup" headline on the billing screen must never quote a
 * different number than the Subscribe button directly below it — two prices on
 * one screen is an App Review risk (Guideline 3.1.1/3.1.2: the price presented
 * must match what StoreKit will actually charge).
 *
 * On iOS, once the real StoreKit product has loaded, the headline uses its
 * `displayPrice` — the same value the Subscribe button already renders — never
 * the Stripe number. Android/web have no StoreKit product, so they keep the
 * Stripe `price_monthly` from the plan catalogue. While the StoreKit product is
 * still loading on iOS, falling back to the Stripe price is safe: the Subscribe
 * button itself is replaced by a "Loading subscription options…" state at that
 * point (see billing.tsx), so there is no second price on screen to disagree with.
 */
export function headlinePriceLabel(opts: {
  iapEnabled: boolean
  iapProduct: { displayPrice: string } | null | undefined
  stripePrice: number | null | undefined
}): string | null {
  if (opts.iapEnabled && opts.iapProduct) return `${opts.iapProduct.displayPrice}/month`
  if (opts.stripePrice != null) return `$${opts.stripePrice}/month`
  return null
}
