/** Paths reachable without a session. */
const PUBLIC_EXACT = new Set<string>([
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
  '/api/auth/forgot-password',
  '/api/auth/reset-password',
  '/api/health',
  // Customer trade-approval UI: page shell loads for anyone; the data API self-guards
  // the customer session, so the page shows a sign-in prompt when unauthenticated.
  '/account/trades',
  // Customer Live page (site not launched; ungated while dark).
  '/live',
  // Middleware-open so the Live page can reach it; POST self-guards in-route
  // (operator session OR IRONFORGE_PAUSE_PASSWORD). GET is read-only state.
  '/api/spark/production-pause',
])

export function isPublicPath(pathname: string): boolean {
  // All /api/brokerage/* routes are middleware-open and self-guarded in-route
  // (webhook → shared secret, customer routes → customer session, internal → service
  // token). Middleware only recognizes the OPERATOR session, so customer-facing
  // brokerage APIs must bypass it here and enforce their own auth.
  if (pathname.startsWith('/api/brokerage/')) return true
  // Customer-shaped Live page aggregation APIs; read-only, no operator internals.
  if (pathname.startsWith('/api/live/')) return true
  return PUBLIC_EXACT.has(pathname)
}

export type AccessDecision = 'allow' | 'redirect-login' | 'unauthorized'

export function decideAccess(opts: {
  pathname: string
  isApi: boolean
  hasSession: boolean
  hasServiceToken: boolean
}): AccessDecision {
  if (opts.hasServiceToken) return 'allow'
  if (isPublicPath(opts.pathname)) return 'allow'
  if (opts.hasSession) return 'allow'
  return opts.isApi ? 'unauthorized' : 'redirect-login'
}
