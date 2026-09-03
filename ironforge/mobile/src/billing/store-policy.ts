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
