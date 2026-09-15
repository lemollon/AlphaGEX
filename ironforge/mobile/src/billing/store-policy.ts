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
 */
export function canManageBillingInApp(platform: 'ios' | 'android' | 'web'): boolean {
  return platform !== 'ios'
}

/**
 * May the /enroll/billing step open an in-app purchase surface (Stripe Checkout,
 * a hosted card form, anything that collects a NEW payment method or creates a NEW
 * subscription) on this platform? APP STORE REVIEW, 2026-09-05: the iOS build is IN
 * REVIEW right now and Guideline 3.1.1 treats any in-app link to a web checkout as an
 * external purchase mechanism for digital content — unlike the billing PORTAL above
 * (managing a subscription that already exists), starting a NEW one is squarely a
 * purchase, and Stripe Checkout is not Apple's in-app purchase API.
 *
 * Always false today, on every platform — not iOS-only. The in-app purchase path
 * (react-native-iap, Apple/Google native billing) does not exist yet; it ships in PR B.
 * Until then /enroll/billing shows that option disabled ("Coming soon") and offers only
 * "I already subscribed on the web" (GET /api/billing/membership), which reads existing
 * entitlement state rather than starting a purchase.
 *
 * TODO(PR B): flip this to platform-aware once react-native-iap lands — true when a
 * native store purchase sheet is available, still false wherever it is not (e.g. web).
 */
export function canPurchaseInApp(_platform: 'ios' | 'android' | 'web'): boolean {
  return false
}
