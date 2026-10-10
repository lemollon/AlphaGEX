/**
 * Google OAuth state + PKCE, carried in a signed, httpOnly, short-lived cookie
 * (not the server-side `oauth_states` table used by the brokerage OAuth flow in
 * lib/enrollment/oauth-state.ts — that table requires an authenticated
 * `user_id`, which does not exist yet at the point a visitor clicks "Continue
 * with Google" on /login or /signup).
 *
 * Signed with HMAC-SHA256 via Web Crypto, same primitives as the onboarding
 * cookie (onboarding.ts) — Edge-safe, though these routes run on the Node
 * runtime anyway (they call fetch() against Google and the customers DB).
 *
 * CSRF: the `state` value here is also placed in the Google authorize URL's
 * `state` param; the callback must find it UNCHANGED inside this signed cookie
 * (verifyGoogleOAuthState) before trusting anything else. PKCE: `verifier` never
 * leaves the server — it rides in this httpOnly cookie, never in a URL.
 */

import { b64urlEncode, b64urlDecode, hmacB64url } from '@/lib/auth/onboarding'
import { safeEqual } from '@/lib/auth/session'

export const GOOGLE_OAUTH_COOKIE = 'ironforge_google_oauth'
export const GOOGLE_OAUTH_TTL_MS = 10 * 60 * 1000 // 10 minutes — matches the brokerage OAuth state TTL

/**
 * The 3 explicit consents, captured on /signup BEFORE the visitor ever leaves for
 * Google — never implied by clicking the button. Absent (undefined) means this
 * round trip started from /login, which asks for none of them; the callback then
 * routes a brand-new account through /signup/google-consent instead of trusting
 * an implied yes. Present means /start received real query-string flags reflecting
 * the checkboxes' state at click time (google/start/route.ts parses them — never
 * defaults a missing or malformed flag to true).
 */
export interface GoogleOAuthConsents {
  ageConfirmed: boolean
  noAdviceAcknowledged: boolean
  electronicCommConsent: boolean
}

export interface GoogleOAuthState {
  /** CSRF value, echoed back in Google's redirect query string. */
  state: string
  /** RFC 7636 PKCE verifier. Never sent to Google directly — only its S256 challenge is. */
  verifier: string
  /** Allowlisted destination after sign-in, e.g. '/enroll'. Resolved server-side at /start. */
  next: string
  consents?: GoogleOAuthConsents
  exp: number
}

/** Same secret cascade as the customer session — this cookie exists only on the customer surface. */
function secret(): string | null {
  return process.env.IRONFORGE_CUSTOMER_SESSION_SECRET || process.env.IRONFORGE_SESSION_SECRET || null
}

export async function signGoogleOAuthState(
  data: Omit<GoogleOAuthState, 'exp'>,
  now: number = Date.now(),
): Promise<string> {
  const s = secret()
  if (!s) throw new Error('google oauth secret is not set')
  const payload = b64urlEncode(JSON.stringify({ ...data, exp: now + GOOGLE_OAUTH_TTL_MS }))
  const sig = await hmacB64url(s, payload)
  return `${payload}.${sig}`
}

export async function verifyGoogleOAuthState(
  token: string | undefined | null,
  now: number = Date.now(),
): Promise<GoogleOAuthState | null> {
  const s = secret()
  if (!s || !token) return null
  const dot = token.indexOf('.')
  if (dot < 1) return null
  const payload = token.slice(0, dot)
  const sig = token.slice(dot + 1)
  const expected = await hmacB64url(s, payload)
  if (!safeEqual(sig, expected)) return null
  try {
    const claims = JSON.parse(b64urlDecode(payload)) as GoogleOAuthState
    if (!claims || typeof claims.state !== 'string' || !claims.state) return null
    if (typeof claims.verifier !== 'string' || !claims.verifier) return null
    if (typeof claims.next !== 'string') return null
    if (claims.consents !== undefined) {
      const c = claims.consents
      if (
        typeof c !== 'object' || c === null ||
        typeof c.ageConfirmed !== 'boolean' ||
        typeof c.noAdviceAcknowledged !== 'boolean' ||
        typeof c.electronicCommConsent !== 'boolean'
      ) {
        return null
      }
    }
    if (typeof claims.exp !== 'number' || now >= claims.exp) return null
    return claims
  } catch {
    return null
  }
}

export function googleOAuthCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    maxAge: Math.floor(GOOGLE_OAUTH_TTL_MS / 1000),
    // Scoped to the OAuth round-trip's own routes — no other route needs to read it.
    path: '/api/auth/google',
  }
}
