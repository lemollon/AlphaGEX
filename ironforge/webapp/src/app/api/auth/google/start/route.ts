import { NextRequest, NextResponse } from 'next/server'
import { randomBytes } from 'crypto'
import { publicOrigin } from '@/lib/public-origin'
import { isCustomerPath } from '@/lib/auth/access'
import { isGoogleOAuthConfigured, buildAuthorizeUrl, googleRedirectUri } from '@/lib/auth/google-oauth'
import { generateCodeVerifier, codeChallengeS256 } from '@/lib/enrollment/oauth-state'
import {
  signGoogleOAuthState,
  GOOGLE_OAUTH_COOKIE,
  googleOAuthCookieOptions,
  type GoogleOAuthConsents,
} from '@/lib/auth/google-oauth-cookie'

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
 * The /signup page's "Continue with Google" button is a disabled `<a>` until all 3
 * consent checkboxes are ticked; once enabled, its href carries their state as
 * `consent=1` query flags so the callback can record the SAME truthful affirmation
 * the password form would have recorded — never implied by the click alone. A
 * missing or non-"1" flag reads as false; nothing here ever defaults a flag to
 * true. /login's button sends none of these — consents stay undefined for that
 * round trip, which routes any brand-new account to /signup/google-consent instead.
 */
function consentsFromQuery(params: URLSearchParams): GoogleOAuthConsents | undefined {
  const hasAny = params.has('ageConfirmed') || params.has('noAdvice') || params.has('commConsent')
  if (!hasAny) return undefined
  return {
    ageConfirmed: params.get('ageConfirmed') === '1',
    noAdviceAcknowledged: params.get('noAdvice') === '1',
    electronicCommConsent: params.get('commConsent') === '1',
  }
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
  const consents = consentsFromQuery(req.nextUrl.searchParams)
  const state = randomBytes(32).toString('base64url')
  const verifier = generateCodeVerifier()
  const challenge = codeChallengeS256(verifier)

  const cookieValue = await signGoogleOAuthState({ state, verifier, next, consents })
  const authorizeUrl = buildAuthorizeUrl({
    state,
    codeChallenge: challenge,
    redirectUri: googleRedirectUri(publicOrigin(req)),
  })

  const res = NextResponse.redirect(authorizeUrl)
  res.cookies.set(GOOGLE_OAUTH_COOKIE, cookieValue, googleOAuthCookieOptions())
  return res
}
