/**
 * Whether the Manage Membership and Billing control may open the billing portal
 * from inside the app, per platform (APP-039).
 *
 * REJECTED 2026-09-14 (submission b937edf7, build 1.0/17), Guideline 3.1.1: "The app
 * accesses digital content purchased outside the app, such as membership, but that
 * content isn't available to purchase using In-App Purchase." The prior fix (restrict
 * the Stripe portal to a no-plan-change configuration server-side) was the wrong
 * target — Apple's objection was never limited to plan CHANGES. Any in-app control
 * that opens a Stripe-hosted payment-management surface, even a restricted one, is
 * itself the "access without IAP" Apple is describing. There is no server-side
 * restriction that satisfies this; the control has to not exist on iOS.
 *
 * iOS therefore gets a hard client-side false. This is the whole guarantee for iOS —
 * not a UX nicety layered on top of a server check. Android and web are unaffected;
 * the server-side portal restriction (api/billing/portal/route.ts) still applies
 * there as defense in depth, it just isn't what makes iOS compliant anymore.
 *
 * STILL false on iOS after the 2026-09-18 Apple IAP PR — that PR made the missing
 * half of Apple's sentence true (content is now "available to purchase using In-App
 * Purchase", see canPurchaseInApp below), it did not reopen a path to the Stripe
 * portal. An Apple-provisioned membership is managed via Apple's OWN subscription
 * settings (manageSubscriptionUrl below), never Stripe's.
 */
export function canManageBillingInApp(platform: 'ios' | 'android' | 'web'): boolean {
  return platform !== 'ios'
}

/**
 * May the /enroll/billing step (or the Account screen) open a purchase surface on
 * this platform — Stripe Checkout, a hosted card form, or a native store purchase
 * sheet; anything that collects a NEW payment method or creates a NEW subscription?
 *
 * REJECTED 2026-09-05, Guideline 3.1.1, while the iOS build was IN REVIEW: an in-app
 * link to Stripe Checkout is an external purchase mechanism for digital content —
 * unlike the billing PORTAL above (managing a subscription that already exists),
 * starting a NEW one is squarely a purchase, and Stripe Checkout is not Apple's
 * in-app purchase API. That PR (build brief) killed the control on EVERY platform,
 * not just iOS, because the native purchase path did not exist yet anywhere: until a
 * real StoreKit/Play Billing surface shipped, "Coming soon" was the only honest
 * state, on iOS or off it.
 *
 * 2026-09-18 (Apple IAP PR): iOS now has that surface — StoreKit 2 via expo-iap
 * (src/billing/apple-iap.ts), wired into /enroll/billing's iOS branch. iOS flips to
 * `true`. Android and web are UNCHANGED — Play Billing is explicitly out of scope
 * for this PR (see the spec's "Out of scope" section) and web's own Stripe Checkout
 * is a developer-preview target that has never shipped (see api/client.ts), so both
 * stay `false` here; those platforms are not under Apple review and this function
 * only exists to satisfy Apple's guideline, not to gate every purchase surface that
 * will ever exist.
 */
export function canPurchaseInApp(platform: 'ios' | 'android' | 'web'): boolean {
  return platform === 'ios'
}

/**
 * Where "Manage subscription" should deep-link for a given billing provider and
 * platform, or null when there is no in-app management link for that combination.
 *
 * This is NOT the Stripe portal `canManageBillingInApp` guards above — it points at
 * Apple's OWN App Store subscription settings, which is exactly the surface Apple
 * expects an iOS app to hand a customer to for a StoreKit-billed subscription. That
 * is why it is safe to offer on iOS when canManageBillingInApp('ios') is false: it
 * is not "access to a purchase made outside IAP", it is Apple's IAP management UI.
 *
 * Returns null for every other combination (Android/web, or an iOS customer whose
 * membership is still on Stripe) — those cases render their own copy/link instead,
 * see app/(tabs)/account.tsx.
 */
export function manageSubscriptionUrl(
  provider: 'stripe' | 'apple' | null | undefined,
  platform: 'ios' | 'android' | 'web',
): string | null {
  if (platform === 'ios' && provider === 'apple') {
    return 'https://apps.apple.com/account/subscriptions'
  }
  return null
}
