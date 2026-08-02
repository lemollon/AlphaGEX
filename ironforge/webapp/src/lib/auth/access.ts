/**
 * True when this deployment runs with the login wall lifted entirely.
 *
 * One flag, one meaning, read in one place. Middleware skips the whole access
 * decision, and the few routes that guard themselves *after* middleware (the
 * operator admin tools and the production-pause control) consult this same
 * helper — so "open" means the same thing everywhere on that service. Without
 * it, IRONFORGE_PUBLIC_MODE opened every page while those routes kept
 * answering 401/403, which reads as broken rather than open.
 *
 * Fail-secure: ANY value other than the exact string 'true' leaves the gate
 * enforced, so losing the variable locks the site down rather than exposing it.
 * Read at call time (never captured at module load) so middleware and a route
 * handler can never disagree about the current value.
 *
 * Scope is per-deployment — it is a Render env var, set on the operator console
 * (ironforge-legacy) and NOT on the customer site.
 */
export function isPublicMode(): boolean {
  return process.env.IRONFORGE_PUBLIC_MODE === 'true'
}

/** Paths reachable without a session. */
const PUBLIC_EXACT = new Set<string>([
  // Public marketing site (homepage + How It Works + Waitlist).
  '/',
  '/how-it-works',
  '/waitlist',
  '/login',
  '/signup',
  '/pricing',
  '/contact',
  '/privacy',
  '/terms',
  // Operator sign-in page. Password login was retired 2026-07-27 (see the page);
  // it stays public because middleware redirects every gated operator route here,
  // and a gated redirect must not land on a login wall it cannot pass.
  '/ops/login',
  '/forgot-password',
  '/reset-password',
  '/api/auth/signup',
  '/api/auth/verify',
  '/api/auth/resend-verification',
  '/api/auth/logout',
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
  // Public proof surface: paper-trade KPI cards and the closed-trade log for
  // Spark and Flame. Same read-only aggregate basis as /track-record.
  '/bot-ledger',
])

/**
 * Paths that require a CUSTOMER session (an operator session also satisfies them).
 *
 * These were previously in PUBLIC_EXACT under an "ungated while dark" comment.
 * They render a person's own money, so they are gated on identity — not on the
 * per-viewer bot scoping in lib/live/viewer.ts, which only decides WHICH bots a
 * signed-in viewer may see.
 *
 * Unauthenticated page requests go to /login (the CUSTOMER door), never /ops/login.
 */
const CUSTOMER_EXACT = new Set<string>([
  '/home',
  '/live',
  // Per-bot "Open Account" (subscribe) pages — render the customer's own setup + pricing.
  '/live/spark/open',
  '/live/flame/open',
  // Agent workspaces (UAT-008) — /live now only redirects into these.
  '/agents/spark',
  '/agents/flame',
  '/performance',
  '/community',
  '/support',
  '/account/trades',
  '/account/billing',
  // Which brokerage accounts a person has linked, with masks and buying power — their
  // own money, so gated on identity like the rest of /account.
  '/account/brokerage',
  // Enrollment funnel — creates a server-owned enrollment for THIS customer, so it
  // requires identity before it can do anything.
  '/enroll',
  // Signed-in password change. Omitting it sent a customer who clicked
  // "Change password" to /ops/login — the OPERATOR door, which they can
  // never satisfy. Same class of bug as /home and /live before #2560.
  '/change-password',
  // Settings hub (UAT-013) — the single rail entry over billing/brokerage/security.
  '/settings',
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
  // The route-per-screen enrollment funnel (/enroll/plan, /enroll/legal, ...) — every
  // screen operates on the caller's own server-owned enrollment, so identity first.
  if (pathname.startsWith('/enroll/')) return true
  // The enrollment v1 API contract. Without this clause the middleware never even
  // READS the customer cookie for /api/v1/* (decideAccess got hasCustomerSession =
  // false) and 401'd every call — the whole enrollment API was unreachable by real
  // customers while every unit test passed. Found by the first live E2E walk.
  // The routes still self-guard with getCustomerSession; this only lets the
  // middleware consider the customer cookie at all.
  if (pathname.startsWith('/api/v1/')) return true
  // Account-settings APIs (TradingView perk, ...). Same middleware lesson as /api/v1/.
  if (pathname.startsWith('/api/account/')) return true
  // Sparky support chat — customer-session guarded (also self-guards in-route).
  if (pathname.startsWith('/api/support/')) return true
  // Push device registration + notification preferences. /api/notifications/dispatch is
  // the scanner's seam and passes on the service token via decideAccess's first branch;
  // it ALSO self-guards in-route, because IRONFORGE_PUBLIC_MODE bypasses this gate and a
  // route that can push to arbitrary customers must not inherit that.
  if (pathname.startsWith('/api/notifications/')) return true
  // Password change is a customer-session route. It was classified NOWHERE, so the
  // middleware never read the customer cookie and 401'd a signed-in customer's own
  // password change — the exact /api/v1/ trap documented above, found during UAT-013.
  if (pathname === '/api/auth/change-password') return true
  return CUSTOMER_EXACT.has(pathname)
}

export function isPublicPath(pathname: string): boolean {
  // Apple/Google app-association files for Universal Links + App Links. Their fetchers
  // arrive with no cookies, and apple-app-site-association has NO FILE EXTENSION, so the
  // middleware page matcher (extension-anchored) matches it and would 307 it to /login —
  // after which Universal Links silently never verify, with no error and no log. This
  // branch is the fix; access.test.ts pins it.
  if (pathname.startsWith('/.well-known/')) return true
  // Mobile auth endpoints are middleware-open and self-guarded in-route: login checks the
  // password, refresh/logout check the presented refresh token, me checks the bearer, and
  // policy returns constants only. Same shape as /api/auth/customer-me.
  if (pathname.startsWith('/api/auth/mobile/')) return true
  // Versioned legal document pages (/legal/risk, /legal/refund-policy, ...). Public for
  // the same reason /terms and /privacy are: partners and prospects must be able to read
  // them before signing in, and the enrollment "Review" actions open them directly.
  if (pathname.startsWith('/legal/')) return true
  // All /api/brokerage/* routes are middleware-open and self-guarded in-route
  // (webhook → shared secret, customer routes → customer session, internal → service
  // token). The webhook has no session of any kind, so it cannot be customer-gated.
  if (pathname.startsWith('/api/brokerage/')) return true
  // All /api/billing/* routes are middleware-open and self-guarded in-route (checkout → customer
  // session, webhook → Stripe signature). The webhook has no session, so it cannot be gated here.
  if (pathname.startsWith('/api/billing/')) return true
  // Public track-record payload: closed-trade aggregates only, no account state.
  if (pathname.startsWith('/api/public/')) return true
  // Public waitlist submission — no auth by design; self-guards with validation,
  // rate limits, and a honeypot in-route.
  if (pathname === '/api/waitlist') return true
  // CRM agent façade — middleware-open, self-guarded in-route by CRM_AGENT_TOKEN. The agent
  // carries its own credential rather than the service token precisely so it CANNOT reach the
  // other /api/ops/* tooling; that separation is the point, so it cannot be gated here.
  // CRM_AGENT_TOKEN unset = every request 401s, matching the repo's fail-safe env convention.
  if (pathname.startsWith('/api/crm/')) return true
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
  /**
   * A verified mobile access token (Authorization: Bearer). Consumed at EXACTLY ONE
   * place — the isCustomerPath branch below — and deliberately not beside
   * hasServiceToken or hasSession. That placement is what makes a bearer token exactly
   * as powerful as the customer cookie and no more: the operator surface stays closed
   * by construction rather than by an allowlist that can rot as routes are added.
   */
  hasBearerCustomer?: boolean
  hasServiceToken: boolean
}): AccessDecision {
  if (opts.hasServiceToken) return 'allow'
  if (isPublicPath(opts.pathname)) return 'allow'
  // Operators may see everything, including the customer surface.
  if (opts.hasSession) return 'allow'
  if (isCustomerPath(opts.pathname)) {
    if (opts.hasCustomerSession || opts.hasBearerCustomer) return 'allow'
    // Bounce to the CUSTOMER door. Sending a customer to /ops/login is the
    // failure mode this branch exists to prevent.
    return opts.isApi ? 'unauthorized' : 'redirect-customer-login'
  }
  return opts.isApi ? 'unauthorized' : 'redirect-login'
}
