import { NextRequest, NextResponse } from 'next/server'
import { getIronSession } from 'iron-session'
import { sessionOptions, hasValidServiceToken, type SessionData } from '@/lib/auth/session'
import { decideAccess, isCustomerPath, isPublicMode } from '@/lib/auth/access'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { customerSessionOptions, type CustomerSessionData } from '@/lib/auth/customer-session'
import { bearerFrom, verifyAccessToken } from '@/lib/auth/mobile-token'
import { resolveSurface, servesPath, OPERATOR_LANDING } from '@/lib/surface'
import { preflightResponse, resolveAllowedOrigin, corsHeaders } from '@/lib/auth/cors'

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

  // Public mode: the login wall is dormant and this whole deployment is open.
  // The self-guarding routes (ops admin tools, production-pause) read the same
  // isPublicMode() helper, so a service running open is open all the way down
  // instead of serving pages whose APIs still 401. See lib/auth/access.ts.
  if (isPublicMode()) {
    return NextResponse.next()
  }

  const isApi = pathname.startsWith('/api/')
  const hasServiceToken = hasValidServiceToken(req.headers.get('x-ironforge-service'))

  // ── CORS for the mobile app's WEB build ──
  //
  // Placed AFTER the surface split (so it can never resurrect an operator route that
  // 404s here) and after public-mode, but BEFORE the auth gate — because a preflight
  // must be answered without credentials. OPTIONS carries no cookie or token and
  // returns no data; gating it would 401 the preflight and the real request would
  // never leave the browser.
  //
  // Entirely inert unless CORS_ALLOWED_ORIGINS is set, and it never echoes '*' nor
  // allows credentials. See lib/auth/cors.ts.
  const reqOrigin = req.headers.get('origin')
  const preflight = preflightResponse(req.method, reqOrigin, pathname)
  if (preflight) return preflight
  const allowedOrigin = isApi ? resolveAllowedOrigin(reqOrigin) : null

  // Applied to every response this middleware returns. A 401 needs the headers just as
  // much as a 200: without them the browser surfaces an opaque CORS failure and the app
  // can never see that the real problem was an expired token.
  const withCors = <T extends Response>(r: T): T => {
    if (allowedOrigin) {
      for (const [k, v] of Object.entries(corsHeaders(allowedOrigin))) r.headers.set(k, v)
    }
    return r
  }

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

  // Mobile bearer token, same lazy discipline as the customer cookie above: verified at
  // most once per request, and only for paths that could actually accept it. Edge-safe
  // (Web Crypto HMAC, no DB) — see mobile-token.ts.
  let _bearerChecked = false
  let _hasBearerCustomer = false
  const bearerCustomer = async (): Promise<boolean> => {
    if (_bearerChecked) return _hasBearerCustomer
    _bearerChecked = true
    try {
      const token = bearerFrom(req.headers.get('authorization'))
      _hasBearerCustomer = token ? Boolean(await verifyAccessToken(token)) : false
    } catch {
      _hasBearerCustomer = false
    }
    return _hasBearerCustomer
  }

  // Onboarding funnel (sub-project F): reachable by a holder of a valid signed
  // onboarding cookie even though they have no login session yet. Operators (session)
  // and internal callers (service token) pass too. Everyone else is bounced to login.
  const isOnboarding =
    pathname === '/onboarding' ||
    pathname.startsWith('/onboarding/') ||
    pathname.startsWith('/api/onboarding/')
  if (isOnboarding) {
    if (hasSession || hasServiceToken) return withCors(res)
    const claims = await verifyOnboardingToken(req.cookies.get(ONBOARDING_COOKIE)?.value)
    if (claims) return withCors(res)
    // A logged-in customer can resume onboarding via their own session cookie.
    if (await customerSession()) return withCors(res)
    // ...or, from the app, via a bearer token. Without this a mobile user who still
    // has onboarding steps left is locked out of finishing them.
    if (await bearerCustomer()) return withCors(res)
    if (isApi) return withCors(NextResponse.json({ error: 'unauthorized' }, { status: 401 }))
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }

  // Customer-surface paths need the customer cookie; everything else decides on the
  // operator session alone, so we only pay for the extra decrypt where it matters.
  const isCustomerSurface = isCustomerPath(pathname)
  const hasCustomerSession = isCustomerSurface ? await customerSession() : false
  // Only consulted when the cookie did not already answer, and only on the customer
  // surface — an operator path must never be reachable with a customer bearer token.
  const hasBearerCustomer =
    isCustomerSurface && !hasCustomerSession ? await bearerCustomer() : false

  const decision = decideAccess({
    pathname,
    isApi,
    hasSession,
    hasCustomerSession,
    hasBearerCustomer,
    hasServiceToken,
  })
  if (decision === 'allow') return withCors(res)
  if (decision === 'unauthorized') {
    return withCors(NextResponse.json({ error: 'unauthorized' }, { status: 401 }))
  }
  // A caller that presented an Authorization header is an API client, not a browser.
  // Redirecting it to an HTML login page yields a 200 full of markup that the app has
  // to guess is a failure; 401 says exactly what happened (token missing/expired →
  // refresh, then retry).
  if (req.headers.get('authorization')) {
    return withCors(NextResponse.json({ error: 'unauthorized' }, { status: 401 }))
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
