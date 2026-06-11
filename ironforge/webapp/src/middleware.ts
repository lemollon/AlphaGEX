import { NextRequest, NextResponse } from 'next/server'
import { getIronSession } from 'iron-session'
import { sessionOptions, hasValidServiceToken, type SessionData } from '@/lib/auth/session'
import { decideAccess } from '@/lib/auth/access'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { customerSessionOptions, type CustomerSessionData } from '@/lib/auth/customer-session'

export async function middleware(req: NextRequest) {
  // Placeholder mode: while public access is on, the login wall is dormant and the
  // whole site is open (until invite/signup goes live). Fail-secure — ANY value other
  // than the exact string 'true' leaves the gate enforced, so losing the env var locks
  // down rather than exposes. Flip IRONFORGE_PUBLIC_MODE off (or remove it) to enforce.
  if (process.env.IRONFORGE_PUBLIC_MODE === 'true') {
    return NextResponse.next()
  }

  const { pathname } = req.nextUrl
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
    let hasCustomerSession = false
    try {
      const cs = await getIronSession<CustomerSessionData>(req, res, customerSessionOptions)
      hasCustomerSession = Boolean(cs.customerId)
    } catch {
      hasCustomerSession = false
    }
    if (hasCustomerSession) return res
    if (isApi) return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }

  const decision = decideAccess({ pathname, isApi, hasSession, hasServiceToken })
  if (decision === 'allow') return res
  if (decision === 'unauthorized') {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }
  // Operator wall → operator login (customers use /login).
  const url = req.nextUrl.clone()
  url.pathname = '/ops/login'
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
