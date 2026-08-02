/**
 * Mobile session policy — the SINGLE source of truth for how long a mobile session
 * lives, returned verbatim by login, refresh, and GET /api/auth/mobile/policy so the
 * app never hardcodes its own numbers (APP-010).
 *
 * Deliberately NOT derived from the iron-session cookie. That cookie has a hard 30-day
 * life written only at login (customer-session.ts maxAge, customer-login/route.ts
 * session.save()) with no sliding renewal — conflating the two would hand the app a
 * policy it cannot honour. A mobile client needs a short access token it can refresh
 * silently and a refresh token that expires on INACTIVITY, which the cookie has no
 * concept of.
 *
 * Pure constants, no imports: this module is read from the Edge middleware, Node route
 * handlers, and tests alike.
 */

export const MOBILE_SESSION_POLICY = {
  /** Bumped whenever a field below changes meaning, so the app can react to a server change. */
  version: 1,

  /** Access token lifetime. Short because a stateless token cannot be revoked mid-flight
   *  (see mobile-token.ts) — this is the blast radius of a leaked access token. */
  accessTtlSec: 900, // 15 min

  /** Absolute refresh lifetime. Even a continuously-active device must re-authenticate
   *  with a password after this. */
  refreshTtlSec: 60 * 60 * 24 * 60, // 60 days

  /** APP-010 inactivity timeout: a refresh token unused for this long is dead even if
   *  it has not hit refreshTtlSec. */
  refreshIdleTtlSec: 60 * 60 * 24 * 14, // 14 days

  /** APP-008: how long the app may stay backgrounded before it must re-prompt biometrics. */
  foregroundLockSec: 300, // 5 min

  /** Step-up token lifetime, minted by /api/auth/mobile/reauth. */
  stepUpTtlSec: 300, // 5 min

  /** Actions that require a fresh step-up token, not just a valid access token.
   *  Anything that moves money, changes who can trade, or changes credentials. */
  stepUpActions: [
    'trade_approve',
    'brokerage_connect',
    'brokerage_disconnect',
    'password_change',
    'billing_cancel',
  ],

  /** Whether the app may unlock a stored refresh token with biometrics (APP-008). */
  biometricUnlockAllowed: true,

  /** Refresh tokens are single-use; presenting a rotated one is treated as theft. */
  rotateRefreshOnUse: true,
} as const

export type MobileSessionPolicy = typeof MOBILE_SESSION_POLICY
