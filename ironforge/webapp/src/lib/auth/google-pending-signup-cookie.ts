/**
 * Google pending-signup cookie — the holding pen between "Google verified this
 * identity" and "a human ticked the 3 required consent boxes."
 *
 * Login's "Continue with Google" never collects consent (there is nothing to
 * collect — it's a sign-IN surface). When that round trip's callback would have
 * to CREATE a new account (no auth_user_id match, no verified-email match), the
 * callback must not do so on an implied yes. Instead it seals the verified Google
 * claims it already checked (signature, issuer, audience, email_verified) into
 * THIS short-lived signed cookie and sends the browser to
 * /signup/google-consent. Only a POST to /api/auth/google/complete-signup that
 * carries this cookie AND 3 explicit `true` values creates the account.
 *
 * Same primitives as google-oauth-cookie.ts (HMAC-SHA256 via Web Crypto, shared
 * with the onboarding cookie) and the same secret cascade — this is still a
 * customer-surface-only cookie.
 */

import { b64urlEncode, b64urlDecode, hmacB64url } from '@/lib/auth/onboarding'
import { safeEqual } from '@/lib/auth/session'

export const GOOGLE_PENDING_SIGNUP_COOKIE = 'ironforge_google_pending_signup'
// Matches the Google OAuth round-trip's own TTL — this is a continuation of that
// same round trip, not a new grant.
export const GOOGLE_PENDING_SIGNUP_TTL_MS = 10 * 60 * 1000

export interface GooglePendingSignupState {
  /** Google's `sub` — the stable account id, never the mutable email alone. */
  sub: string
  email: string
  givenName: string | null
  familyName: string | null
  /** Allowlisted destination after the account is finally created. */
  next: string
  exp: number
}

function secret(): string | null {
  return process.env.IRONFORGE_CUSTOMER_SESSION_SECRET || process.env.IRONFORGE_SESSION_SECRET || null
}

export async function signGooglePendingSignupState(
  data: Omit<GooglePendingSignupState, 'exp'>,
  now: number = Date.now(),
): Promise<string> {
  const s = secret()
  if (!s) throw new Error('google pending signup secret is not set')
  const payload = b64urlEncode(JSON.stringify({ ...data, exp: now + GOOGLE_PENDING_SIGNUP_TTL_MS }))
  const sig = await hmacB64url(s, payload)
  return `${payload}.${sig}`
}

export async function verifyGooglePendingSignupState(
  token: string | undefined | null,
  now: number = Date.now(),
): Promise<GooglePendingSignupState | null> {
  const s = secret()
  if (!s || !token) return null
  const dot = token.indexOf('.')
  if (dot < 1) return null
  const payload = token.slice(0, dot)
  const sig = token.slice(dot + 1)
  const expected = await hmacB64url(s, payload)
  if (!safeEqual(sig, expected)) return null
  try {
    const claims = JSON.parse(b64urlDecode(payload)) as GooglePendingSignupState
    if (!claims || typeof claims.sub !== 'string' || !claims.sub) return null
    if (typeof claims.email !== 'string' || !claims.email) return null
    if (typeof claims.givenName !== 'string' && claims.givenName !== null) return null
    if (typeof claims.familyName !== 'string' && claims.familyName !== null) return null
    if (typeof claims.next !== 'string') return null
    if (typeof claims.exp !== 'number' || now >= claims.exp) return null
    return claims
  } catch {
    return null
  }
}

export function googlePendingSignupCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    maxAge: Math.floor(GOOGLE_PENDING_SIGNUP_TTL_MS / 1000),
    // Needs to be readable by both /signup/google-consent (GET) and
    // /api/auth/google/complete-signup (POST) — two different paths, so this
    // cookie (unlike the OAuth round-trip cookie) is not scoped to /api/auth/google.
    path: '/',
  }
}
