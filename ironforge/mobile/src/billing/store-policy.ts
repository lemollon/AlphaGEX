/**
 * Whether the Manage Membership and Billing control may open the billing portal
 * from inside the app, per platform (APP-039).
 *
 * This used to be a client-side gate that hid the button entirely on iOS, because
 * Stripe's default portal configuration allows changing plan — a purchasing
 * mechanism under App Review Guideline 3.1.1 if reachable from inside an iOS app.
 * That gate never actually shipped as code (account.tsx only ever had a comment
 * describing it), and it is the wrong layer for the guarantee anyway: a client flag
 * is trivially bypassed and proves nothing to a reviewer.
 *
 * The guarantee now lives on the server. POST /api/billing/portal serves a mobile
 * bearer client a Stripe portal session with subscription/plan changes disabled,
 * and fails CLOSED — 503 `portal_unconfigured` — rather than falling back to
 * Stripe's default (plan-changeable) portal if that restricted configuration is
 * missing. So this returns true for every platform: 3.1.1 is enforced by what the
 * server is willing to hand back, not by whether the client shows a button.
 */
export function canManageBillingInApp(_platform: 'ios' | 'android' | 'web'): boolean {
  return true
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
