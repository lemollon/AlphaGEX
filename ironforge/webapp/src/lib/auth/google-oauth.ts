/**
 * Google OAuth 2.0 (authorization-code + PKCE) — "Continue with Google" for the
 * customer web app (web only; the mobile app deliberately does NOT get this —
 * see the callback route's header).
 *
 * No SDK: the authorize/token endpoints are plain fetches, and the ID token is a
 * standard RS256 JWT verified against Google's published JWKS with node:crypto.
 * `jose` is not already a dependency of this app, so it is not added for this.
 */

import { createPublicKey, verify as cryptoVerify } from 'crypto'

export const GOOGLE_AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
export const GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
export const GOOGLE_JWKS_URL = 'https://www.googleapis.com/oauth2/v3/certs'

/** Google's documented issuer values — both appear in the wild across token versions. */
const GOOGLE_ISSUERS = new Set(['https://accounts.google.com', 'accounts.google.com'])

const JWKS_TTL_MS = 60 * 60 * 1000

export function isGoogleOAuthConfigured(): boolean {
  return !!process.env.GOOGLE_CLIENT_ID && !!process.env.GOOGLE_CLIENT_SECRET
}

/** The EXACT registered redirect URI — https://ironforge.trade/api/auth/google/callback in prod. */
export function googleRedirectUri(origin: string): string {
  return `${origin.replace(/\/$/, '')}/api/auth/google/callback`
}

export function buildAuthorizeUrl(opts: { state: string; codeChallenge: string; redirectUri: string }): string {
  const url = new URL(GOOGLE_AUTHORIZE_URL)
  url.searchParams.set('client_id', process.env.GOOGLE_CLIENT_ID || '')
  url.searchParams.set('redirect_uri', opts.redirectUri)
  url.searchParams.set('response_type', 'code')
  url.searchParams.set('scope', 'openid email profile')
  url.searchParams.set('state', opts.state)
  url.searchParams.set('code_challenge', opts.codeChallenge)
  url.searchParams.set('code_challenge_method', 'S256')
  url.searchParams.set('access_type', 'online')
  // Always show the account chooser — a customer on a shared/kiosk browser must not
  // silently get logged into whichever Google account last authenticated there.
  url.searchParams.set('prompt', 'select_account')
  return url.toString()
}

export interface GoogleTokenResponse {
  idToken: string
  accessToken: string | null
}

export async function exchangeCodeForToken(
  code: string,
  codeVerifier: string,
  redirectUri: string,
): Promise<GoogleTokenResponse> {
  const body = new URLSearchParams({
    code,
    client_id: process.env.GOOGLE_CLIENT_ID || '',
    client_secret: process.env.GOOGLE_CLIENT_SECRET || '',
    redirect_uri: redirectUri,
    grant_type: 'authorization_code',
    code_verifier: codeVerifier,
  })
  const res = await fetch(GOOGLE_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    // Never log the code/verifier/secret — only the provider's own error detail.
    throw new Error(`Google token exchange failed (${res.status}): ${detail.slice(0, 300)}`)
  }
  const json = (await res.json()) as { id_token?: string; access_token?: string }
  if (!json.id_token) throw new Error('Google token response had no id_token')
  return { idToken: json.id_token, accessToken: json.access_token ?? null }
}

interface GoogleJwk {
  kid: string
  kty: string
  n: string
  e: string
  alg?: string
  use?: string
}

let jwksCache: { keys: GoogleJwk[]; fetchedAt: number } | null = null

async function getGoogleJwks(): Promise<GoogleJwk[]> {
  if (jwksCache && Date.now() - jwksCache.fetchedAt < JWKS_TTL_MS) return jwksCache.keys
  const res = await fetch(GOOGLE_JWKS_URL)
  if (!res.ok) throw new Error(`Failed to fetch Google JWKS (${res.status})`)
  const json = (await res.json()) as { keys: GoogleJwk[] }
  jwksCache = { keys: json.keys || [], fetchedAt: Date.now() }
  return jwksCache.keys
}

export interface GoogleIdClaims {
  sub: string
  email: string
  emailVerified: boolean
  givenName: string | null
  familyName: string | null
  picture: string | null
}

/**
 * Verify an ID token's RS256 signature against Google's published JWKS and check
 * the standard claims (iss, aud, exp, email_verified). Returns null for ANY
 * failure — callers must treat "could not verify" and "verified but invalid" the
 * same way (reject), never distinguish by exception message, so nothing a caller
 * does accidentally trusts a token that failed one check but not another.
 */
export async function verifyGoogleIdToken(idToken: string): Promise<GoogleIdClaims | null> {
  try {
    const parts = idToken.split('.')
    if (parts.length !== 3) return null
    const [headerB64, payloadB64, sigB64] = parts

    const header = JSON.parse(Buffer.from(headerB64, 'base64url').toString('utf8')) as {
      kid?: string
      alg?: string
    }
    if (header.alg !== 'RS256' || !header.kid) return null

    const keys = await getGoogleJwks()
    const jwk = keys.find((k) => k.kid === header.kid && k.kty === 'RSA')
    if (!jwk) return null

    const publicKey = createPublicKey({ key: { kty: jwk.kty, n: jwk.n, e: jwk.e }, format: 'jwk' })
    const signingInput = Buffer.from(`${headerB64}.${payloadB64}`)
    const signature = Buffer.from(sigB64, 'base64url')
    if (!cryptoVerify('RSA-SHA256', signingInput, publicKey, signature)) return null

    const payload = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8')) as Record<string, unknown>

    const iss = String(payload.iss ?? '')
    if (!GOOGLE_ISSUERS.has(iss)) return null
    if (!process.env.GOOGLE_CLIENT_ID || payload.aud !== process.env.GOOGLE_CLIENT_ID) return null

    const exp = Number(payload.exp)
    if (!Number.isFinite(exp) || Date.now() >= exp * 1000) return null

    const sub = String(payload.sub ?? '')
    const email = String(payload.email ?? '')
    if (!sub || !email) return null

    return {
      sub,
      email,
      emailVerified: payload.email_verified === true || payload.email_verified === 'true',
      givenName: typeof payload.given_name === 'string' ? payload.given_name : null,
      familyName: typeof payload.family_name === 'string' ? payload.family_name : null,
      picture: typeof payload.picture === 'string' ? payload.picture : null,
    }
  } catch {
    return null
  }
}

/**
 * A username CANDIDATE derived from the Google profile — sanitized to the app's
 * username charset, but never checked for validity or uniqueness on its own; the
 * caller (google/callback route) owns the DB uniqueness loop.
 */
export function deriveUsernameBase(claims: GoogleIdClaims): string {
  const fromName = (claims.givenName || '').toLowerCase().replace(/[^a-z0-9_]/g, '')
  const fromEmail = claims.email.split('@')[0].toLowerCase().replace(/[^a-z0-9_]/g, '')
  let base = fromName || fromEmail || 'member'
  if (!/^[a-z]/.test(base)) base = `m${base}`
  base = base.slice(0, 16)
  if (base.length < 3) base = `${base}member`.slice(0, 16)
  return base
}

/** Test-only escape hatch so JWKS fetch mocks aren't poisoned across test cases. */
export function resetGoogleJwksCacheForTests(): void {
  jwksCache = null
}
