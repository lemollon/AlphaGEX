import type { SessionOptions } from 'iron-session'

/**
 * Customer session — DISTINCT from the operator session (src/lib/auth/session.ts).
 * The operator gate reads only `ironforge_session`; the customer gate reads only
 * `ironforge_customer`. They are never cross-honored, so a customer session can
 * never satisfy operator gating. (Sub-project: customer auth, Approach A.)
 *
 * Edge-safe by design: this module is imported by middleware, so it must NOT pull
 * in `next/headers` (server-only). The Node-runtime accessor `getCustomerSession()`
 * lives in `customer-session-server.ts`. Mirrors the operator `session.ts` split.
 */
export interface CustomerSessionData {
  customerId?: string // users.id (uuid) in the ironforge-customers DB
  email?: string
  emailVerified?: boolean
  onboardingStep?: string
}

export const CUSTOMER_SESSION_COOKIE = 'ironforge_customer'

export const customerSessionOptions: SessionOptions = {
  // Distinct secret from the OPERATOR session where one is configured.
  //
  // Both cookies were previously sealed with IRONFORGE_SESSION_SECRET and told
  // apart only by cookie NAME. That is safe today (both are host-only, so they
  // never travel to the same host), but it means an operator-issued sealed blob
  // decrypts cleanly as a customer session. Once the app is split across
  // ops.ironforge.trade and ironforge.trade, anything that later introduces a
  // parent-domain cookie turns that into a live privilege-escalation path.
  //
  // Falls back to the shared secret so nothing breaks before the new var is set.
  // Setting IRONFORGE_CUSTOMER_SESSION_SECRET invalidates existing customer
  // sessions once (customers re-login); operator sessions are unaffected.
  password:
    process.env.IRONFORGE_CUSTOMER_SESSION_SECRET ||
    process.env.IRONFORGE_SESSION_SECRET ||
    '',
  cookieName: CUSTOMER_SESSION_COOKIE,
  cookieOptions: {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: '/',
  },
}
