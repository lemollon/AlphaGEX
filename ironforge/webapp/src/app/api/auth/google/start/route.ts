import { NextRequest, NextResponse } from 'next/server'
import { randomBytes } from 'crypto'
import { publicOrigin } from '@/lib/public-origin'
import { isCustomerPath } from '@/lib/auth/access'
import { isGoogleOAuthConfigured, buildAuthorizeUrl, googleRedirectUri } from '@/lib/auth/google-oauth'
import { generateCodeVerifier, codeChallengeS256 } from '@/lib/enrollment/oauth-state'
import { signGoogleOAuthState, GOOGLE_OAUTH_COOKIE, googleOAuthCookieOptions } from '@/lib/auth/google-oauth-cookie'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * `next` is a caller-supplied query param, so it is allowlisted against the same
 * customer-surface path set middleware itself trusts — never a raw passthrough.
 * An unrecognized or absolute/protocol-relative value falls back to /enroll.
 */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/enroll'
  const path = raw.split('?')[0].split('#')[0]
  return path === '/enroll' || isCustomerPath(path) ? path : '/enroll'
}

/**
 * Starts the Google sign-in/sign-up round trip for the customer web app.
 *
 * GET, not POST: the button is a plain navigation (an <a href>), so there is no
 * fetch, no CORS, and nothing a browser extension or ad blocker can treat as an
 * XHR to block. State and PKCE are resolved server-side and handed back to the
 * browser only as an opaque, signed, httpOnly cookie (google-oauth-cookie.ts) —
 * the verifier never appears in a URL or in client-readable storage.
 */
export async function GET(req: NextRequest) {
  if (!isGoogleOAuthConfigured()) {
    return NextResponse.json({ ok: false, error: 'Google sign-in is not configured.' }, { status: 404 })
  }

  const next = safeNext(req.nextUrl.searchParams.get('next'))
  const state = randomBytes(32).toString('base64url')
  const verifier = generateCodeVerifier()
  const challenge = codeChallengeS256(verifier)

  const cookieValue = await signGoogleOAuthState({ state, verifier, next })
  const authorizeUrl = buildAuthorizeUrl({
    state,
    codeChallenge: challenge,
    redirectUri: googleRedirectUri(publicOrigin(req)),
  })

  const res = NextResponse.redirect(authorizeUrl)
  res.cookies.set(GOOGLE_OAUTH_COOKIE, cookieValue, googleOAuthCookieOptions())
  return res
}
