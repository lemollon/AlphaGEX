/** Paths reachable without a session. */
const PUBLIC_EXACT = new Set<string>([
  // Public marketing site (homepage + How It Works).
  '/',
  '/how-it-works',
  '/login',
  '/signup',
  '/pricing',
  '/contact',
  '/privacy',
  '/terms',
  '/ops/login',
  '/forgot-password',
  '/reset-password',
  '/api/auth/login',
  '/api/auth/signup',
  '/api/auth/verify',
  '/api/auth/resend-verification',
  '/api/auth/logout',
  '/api/auth/seed',
  '/api/auth/customer-login',
  '/api/auth/customer-logout',
  '/api/auth/customer-me',
  // Magic admin link — self-guarded by IRONFORGE_ADMIN_KEY (constant-time
  // compare in-route); must be reachable without a session by design.
  '/api/ops/admin',
  '/api/auth/forgot-password',
  '/api/auth/reset-password',
  '/api/health',
  // Public proof surface: the paper/live track record shown to prospects. Read-only
  // aggregate of CLOSED trades — no balances, no open positions, no controls.
  '/track-record',
])

/**
 * Paths that require a CUSTOMER session (an operator session also satisfies them).
 *
 * These were previously in PUBLIC_EXACT under an "ungated while dark" comment.
 * They render a person's own money, so they are gated on identity — not on the
 * IRONFORGE_LIVE_OPEN review flag, which only scopes WHICH bots a viewer may see.
 *
 * Unauthenticated page requests go to /login (the CUSTOMER door), never /ops/login.
 */
const CUSTOMER_EXACT = new Set<string>([
  '/home',
  '/live',
  // Per-bot "Open Account" (subscribe) pages — render the customer's own setup + pricing.
  '/live/spark/open',
  '/live/flame/open',
  '/performance',
  '/community',
  '/account/trades',
  // Signed-in password change. Omitting it sent a customer who clicked
  // "Change password" to /ops/login — the OPERATOR door, which they can
  // never satisfy. Same class of bug as /home and /live before #2560.
  '/change-password',
  // The Live page's Pause control. Self-guards ownership in-route; this only
  // establishes that an anonymous caller can never reach it at all.
  '/api/spark/production-pause',
  '/api/spark2/production-pause',
  '/api/flame/production-pause',
])

export function isCustomerPath(pathname: string): boolean {
  // Customer Live/Home/Performance aggregation APIs. resolveLiveViewer() already
  // fails closed, but an anonymous caller should not reach them at all.
  if (pathname.startsWith('/api/live/')) return true
  return CUSTOMER_EXACT.has(pathname)
}

export function isPublicPath(pathname: string): boolean {
  // All /api/brokerage/* routes are middleware-open and self-guarded in-route
  // (webhook → shared secret, customer routes → customer session, internal → service
  // token). The webhook has no session of any kind, so it cannot be customer-gated.
  if (pathname.startsWith('/api/brokerage/')) return true
  // All /api/billing/* routes are middleware-open and self-guarded in-route (checkout → customer
  // session, webhook → Stripe signature). The webhook has no session, so it cannot be gated here.
  if (pathname.startsWith('/api/billing/')) return true
  // Public track-record payload: closed-trade aggregates only, no account state.
  if (pathname.startsWith('/api/public/')) return true
  // Forge Community APIs: GET is public-read (drives the locked preview for
  // anonymous visitors); POSTs self-guard the customer session in-route.
  if (pathname.startsWith('/api/community/')) return true
  return PUBLIC_EXACT.has(pathname)
}

export type AccessDecision =
  | 'allow'
  | 'redirect-login'
  | 'redirect-customer-login'
  | 'unauthorized'

export function decideAccess(opts: {
  pathname: string
  isApi: boolean
  hasSession: boolean
  hasCustomerSession?: boolean
  hasServiceToken: boolean
}): AccessDecision {
  if (opts.hasServiceToken) return 'allow'
  if (isPublicPath(opts.pathname)) return 'allow'
  // Operators may see everything, including the customer surface.
  if (opts.hasSession) return 'allow'
  if (isCustomerPath(opts.pathname)) {
    if (opts.hasCustomerSession) return 'allow'
    // Bounce to the CUSTOMER door. Sending a customer to /ops/login is the
    // failure mode this branch exists to prevent.
    return opts.isApi ? 'unauthorized' : 'redirect-customer-login'
  }
  return opts.isApi ? 'unauthorized' : 'redirect-login'
}
