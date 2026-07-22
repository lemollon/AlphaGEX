import { NextRequest, NextResponse } from 'next/server'
import { getIronSession } from 'iron-session'
import { sessionOptions, hasValidServiceToken, type SessionData } from '@/lib/auth/session'
import { decideAccess, isCustomerPath } from '@/lib/auth/access'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { customerSessionOptions, type CustomerSessionData } from '@/lib/auth/customer-session'
import { resolveSurface, servesPath, OPERATOR_LANDING } from '@/lib/surface'

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl

  // Surface split — deliberately BEFORE the public-mode bypass below.
  //
  // This app is deployed twice from one image (customer site / operator console).
  // A route belonging to the other half is 404, not 401: the public service should
  // not even admit that /accounts exists. Placing this first means IRONFORGE_PUBLIC_MODE
  // can never re-expose operator routes on the customer domain — the two flags
  // compose safely instead of one overriding the other.
  //
  // Unset IRONFORGE_MODE → 'both' → this is a no-op (today's behaviour).
  const surface = resolveSurface(process.env.IRONFORGE_MODE)

  // Landing page for the operator console. '/' is the customer marketing page,
  // so on the operator surface it would 404 — meaning the console's own root URL
  // greets you with "page can't be found". Send it to the first bot dashboard
  // instead. Only '/' is redirected; every other customer route still 404s, which
  // is the point of the split.
  if (surface === 'operator' && pathname === '/') {
    const url = req.nextUrl.clone()
    url.pathname = OPERATOR_LANDING
    return NextResponse.redirect(url)
  }

  if (!servesPath(surface, pathname)) {
    return new NextResponse(null, { status: 404 })
  }

  // Placeholder mode: while public access is on, the login wall is dormant and the
  // whole site is open (until invite/signup goes live). Fail-secure — ANY value other
  // than the exact string 'true' leaves the gate enforced, so losing the env var locks
  // down rather than exposes. Flip IRONFORGE_PUBLIC_MODE off (or remove it) to enforce.
  if (process.env.IRONFORGE_PUBLIC_MODE === 'true') {
    return NextResponse.next()
  }

  const isApi = pathname.startsWith('/api/')
  const hasServiceToken = hasValidServiceToken(req.headers.get('x-ironforge-service'))

  // Read (not write) the session cookie. Edge-safe: iron-session uses Web Crypto.
  const res = NextResponse.next()
  let hasSession = false
  try {
    const session = await getIronSession<SessionData>(req, res, sessionOptions)
    hasSession = Boolean(session.userId)
  } catch {
    hasSession = false
  }

  // Customer session, read once and reused by both the onboarding branch and the
  // main access decision. Edge-safe (iron-session uses Web Crypto). Read lazily so
  // an operator/public request never pays for a second cookie decrypt.
  let _customerChecked = false
  let _hasCustomerSession = false
  const customerSession = async (): Promise<boolean> => {
    if (_customerChecked) return _hasCustomerSession
    _customerChecked = true
    try {
      const cs = await getIronSession<CustomerSessionData>(req, res, customerSessionOptions)
      _hasCustomerSession = Boolean(cs.customerId)
    } catch {
      _hasCustomerSession = false
    }
    return _hasCustomerSession
  }

  // Onboarding funnel (sub-project F): reachable by a holder of a valid signed
  // onboarding cookie even though they have no login session yet. Operators (session)
  // and internal callers (service token) pass too. Everyone else is bounced to login.
  const isOnboarding =
    pathname === '/onboarding' ||
    pathname.startsWith('/onboarding/') ||
    pathname.startsWith('/api/onboarding/')
  if (isOnboarding) {
    if (hasSession || hasServiceToken) return res
    const claims = await verifyOnboardingToken(req.cookies.get(ONBOARDING_COOKIE)?.value)
    if (claims) return res
    // A logged-in customer can resume onboarding via their own session cookie.
    if (await customerSession()) return res
    if (isApi) return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }

  // Customer-surface paths need the customer cookie; everything else decides on the
  // operator session alone, so we only pay for the extra decrypt where it matters.
  const hasCustomerSession = isCustomerPath(pathname) ? await customerSession() : false

  const decision = decideAccess({
    pathname,
    isApi,
    hasSession,
    hasCustomerSession,
    hasServiceToken,
  })
  if (decision === 'allow') return res
  if (decision === 'unauthorized') {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }
  const url = req.nextUrl.clone()
  // Customer surface → customer door; operator surface → operator door. Sending a
  // customer to /ops/login is a dead end: they have no operator credentials.
  url.pathname = decision === 'redirect-customer-login' ? '/login' : '/ops/login'
  url.searchParams.set('next', pathname)
  return NextResponse.redirect(url)
}

// API routes are ALWAYS gated — no static-extension escape hatch (a path like
// /api/ember/build.js must not bypass the gate into the catch-all proxy).
// Pages run on everything except framework statics and files whose path ENDS in a
// static-asset extension (so public images/styles load on the /login page). The `$`
// end-anchor is essential: without it, any path *containing* ".js" etc. is skipped.
export const config = {
  matcher: [
    '/api/:path*',
    '/((?!_next/static|_next/image|.*\\.(?:svg|png|jpg|jpeg|gif|ico|webp|css|js|map|woff2?)$).*)',
  ],
}
