/**
 * Mobile ACCESS token — stateless, HMAC-SHA256, verified at the Edge.
 *
 * Why stateless rather than an opaque DB-backed token: src/middleware.ts runs on the
 * Edge runtime, where `pg` cannot run. A DB-backed access token would force a database
 * round trip that the middleware physically cannot make. So the access token must carry
 * its own proof. The REFRESH token is the opaque, revocable half — see mobile-session.ts.
 *
 * Signed with Web Crypto only (no node:crypto, no next/headers, no pg) so this module is
 * importable from the Edge middleware, Node route handlers, and tests alike — the same
 * discipline customer-session.ts follows.
 *
 * ── The domain-separation prefix is load-bearing, not cosmetic ──
 *
 * verifyOnboardingToken() (onboarding.ts) accepts ANY payload that parses to
 * `{uid: string, exp: number}` and is signed with IRONFORGE_SESSION_SECRET. Our secret
 * cascade (below) falls through to that same value when the mobile/customer secrets are
 * unset. Without a prefix, a mobile access token would therefore verify as a valid
 * onboarding cookie — and an onboarding cookie would verify as a valid access token,
 * handing a half-signed-up user the whole customer API.
 *
 * Prefixing the SIGNED INPUT (not the payload) makes both directions fail while leaving
 * the existing onboarding token byte-for-byte unchanged — no migration, no invalidation.
 * mobile-token.test.ts asserts both directions reject; do not remove those tests.
 *
 * REVOCATION LIMIT: a stateless token cannot be withdrawn before it expires. The window
 * is accessTtlSec (15 min). Routes that do anything sensitive must call
 * getCustomerIdentity({ verifyEpoch: true }), which compares the token's `ep` claim
 * against users.token_epoch and costs one indexed row read.
 */

import { safeEqual } from '@/lib/auth/session'
import { b64urlEncode, b64urlDecode, hmacB64url } from '@/lib/auth/onboarding'
import { MOBILE_SESSION_POLICY } from '@/lib/auth/mobile-policy'

/** Domain separator mixed into the HMAC input. Bump the version on any claim-shape change. */
const DOMAIN = 'ifm.v1.'

/** Defensive cap — an Authorization header is attacker-controlled and we parse it before auth. */
const MAX_TOKEN_LEN = 4096

export type MobileTokenType = 'acc' | 'step'

export interface MobileClaims {
  /** users.id (uuid) in the customers DB. */
  sub: string
  typ: MobileTokenType
  /** users.token_epoch at mint time — the stateless-revocation kill switch. */
  ep: number
  iat: number
  exp: number
}

/**
 * Same cascade as customer-session.ts, plus a mobile-specific override so the mobile
 * surface can be re-keyed (invalidating every app session) without logging out the web.
 * Unset = fail closed, matching verifyOnboardingToken.
 */
function secret(): string | null {
  return (
    process.env.IRONFORGE_MOBILE_TOKEN_SECRET ||
    process.env.IRONFORGE_CUSTOMER_SESSION_SECRET ||
    process.env.IRONFORGE_SESSION_SECRET ||
    null
  )
}

export function isMobileTokenConfigured(): boolean {
  return secret() !== null
}

async function sign(claims: MobileClaims): Promise<string> {
  const s = secret()
  if (!s) throw new Error('mobile token secret is not set')
  const payload = b64urlEncode(JSON.stringify(claims))
  const sig = await hmacB64url(s, DOMAIN + payload)
  return `${payload}.${sig}`
}

export async function signAccessToken(
  sub: string,
  epoch: number,
  now: number = Date.now(),
): Promise<string> {
  return sign({
    sub,
    typ: 'acc',
    ep: epoch,
    iat: Math.floor(now / 1000),
    exp: Math.floor(now / 1000) + MOBILE_SESSION_POLICY.accessTtlSec,
  })
}

/** Short-lived proof of a fresh password check, for MOBILE_SESSION_POLICY.stepUpActions. */
export async function signStepUpToken(
  sub: string,
  epoch: number,
  now: number = Date.now(),
): Promise<string> {
  return sign({
    sub,
    typ: 'step',
    ep: epoch,
    iat: Math.floor(now / 1000),
    exp: Math.floor(now / 1000) + MOBILE_SESSION_POLICY.stepUpTtlSec,
  })
}

/**
 * Verify and decode. Returns null — never throws — on every failure mode so callers
 * cannot accidentally treat a malformed token as an error worth surfacing:
 * missing secret, malformed shape, bad signature, expired, or wrong type.
 */
export async function verifyMobileToken(
  token: string | undefined | null,
  opts: { type?: MobileTokenType; now?: number } = {},
): Promise<MobileClaims | null> {
  const s = secret()
  if (!s || !token) return null
  if (token.length > MAX_TOKEN_LEN) return null

  const dot = token.indexOf('.')
  if (dot < 1 || dot === token.length - 1) return null
  const payload = token.slice(0, dot)
  const sig = token.slice(dot + 1)

  const expected = await hmacB64url(s, DOMAIN + payload)
  if (!safeEqual(sig, expected)) return null

  try {
    const claims = JSON.parse(b64urlDecode(payload)) as MobileClaims
    if (!claims || typeof claims.sub !== 'string' || !claims.sub) return null
    if (claims.typ !== 'acc' && claims.typ !== 'step') return null
    if (typeof claims.ep !== 'number') return null
    if (typeof claims.exp !== 'number') return null
    const nowSec = Math.floor((opts.now ?? Date.now()) / 1000)
    if (nowSec >= claims.exp) return null
    // Default to 'acc': a step-up token must never be accepted where a plain access
    // token is expected, and vice versa.
    if ((opts.type ?? 'acc') !== claims.typ) return null
    return claims
  } catch {
    return null
  }
}

/** Convenience wrapper — the overwhelmingly common case. */
export async function verifyAccessToken(
  token: string | undefined | null,
  now?: number,
): Promise<MobileClaims | null> {
  return verifyMobileToken(token, { type: 'acc', now })
}

/**
 * Pull the bearer token out of an Authorization header.
 * Case-insensitive scheme per RFC 7235; returns null for any other scheme.
 */
export function bearerFrom(header: string | undefined | null): string | null {
  if (!header) return null
  const trimmed = header.trim()
  if (trimmed.length > MAX_TOKEN_LEN + 16) return null
  const space = trimmed.indexOf(' ')
  if (space < 0) return null
  if (trimmed.slice(0, space).toLowerCase() !== 'bearer') return null
  const token = trimmed.slice(space + 1).trim()
  return token.length > 0 ? token : null
}
