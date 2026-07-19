/**
 * Which half of IronForge a given deployment serves.
 *
 * The app is deployed twice from one image:
 *   - customer  → ironforge.trade        (marketing, Live, Home, Community)
 *   - operator  → ops.ironforge.trade    (bot consoles, accounts, backtests)
 *
 * Selected by IRONFORGE_MODE. This module is imported by middleware (Edge),
 * server components AND client components, so it must stay free of `next/server`,
 * the DB client, auth, and `process`-dependent side effects at import time.
 *
 * DEFAULT IS 'both'. An unset IRONFORGE_MODE serves everything — exactly today's
 * behaviour. That is deliberate: making the default restrictive would mean a
 * deploy that forgot the variable silently 404s half the site. The customer
 * service opts IN to being restricted; nothing breaks by omission.
 *
 * NOTE: this is a routing/organisation boundary, NOT the security boundary.
 * Authentication still gates operator routes independently (see access.ts).
 * Never rely on surface filtering alone to protect operator data — the real
 * protection is that the customer service does not hold the Tradier credentials.
 */

export type Surface = 'customer' | 'operator' | 'both'

export function resolveSurface(raw?: string | null): Surface {
  return raw === 'customer' ? 'customer' : raw === 'operator' ? 'operator' : 'both'
}

/** Pages served by the customer site. */
export const CUSTOMER_PAGES: readonly string[] = [
  '/',
  '/how-it-works',
  '/pricing',
  '/live',
  '/home',
  '/community',
  '/account/trades',
  '/login',
  '/signup',
  '/forgot-password',
  '/reset-password',
  '/change-password',
  '/contact',
  '/privacy',
  '/terms',
]

/** Page prefixes served by the customer site (onboarding funnel). */
export const CUSTOMER_PAGE_PREFIXES: readonly string[] = ['/onboarding']

/** Pages served by the operator console. */
export const OPERATOR_PAGES: readonly string[] = [
  '/spark',
  '/spark2',
  '/flame',
  '/inferno',
  '/blaze',
  '/flare',
  '/kindle',
  '/ember',
  '/compare',
  '/accounts',
  '/gex',
  '/volatility',
  '/calendar',
  '/ops/login',
]

/** Page prefixes served by the operator console. */
export const OPERATOR_PAGE_PREFIXES: readonly string[] = ['/briefings', '/calendar/', '/ops/']

/**
 * Operator API namespaces. `/api/[bot]/*` is the bot console API and
 * `/api/accounts/*` exposes broker credentials — neither belongs on the public
 * service, with the narrow exception below.
 */
export const OPERATOR_API_PREFIXES: readonly string[] = [
  '/api/accounts/',
  '/api/ops/',
  '/api/ember/',
  '/api/briefings/',
  '/api/calendar/',
]

/**
 * Operator-namespace endpoints the CUSTOMER site genuinely needs.
 *
 * The Live page's Pause control posts here. These live under `/api/[bot]/` but
 * are customer-facing, so the customer service must keep serving them. Explicit
 * list, never a wildcard — `/api/[bot]/` also contains force-trade, force-close,
 * eod-close and config, which must never be reachable from the public site.
 */
export const CUSTOMER_API_EXCEPTIONS: readonly string[] = [
  '/api/spark/production-pause',
  '/api/spark2/production-pause',
  '/api/flame/production-pause',
]

/**
 * Customer API namespaces. Read-only aggregation and customer-session-guarded
 * writes; no operator internals.
 */
export const CUSTOMER_API_PREFIXES: readonly string[] = [
  '/api/live/',
  '/api/community/',
  '/api/brokerage/',
  '/api/onboarding/',
]

/** Shared infrastructure endpoints both services need. */
export const SHARED_API_PREFIXES: readonly string[] = ['/api/auth/']
export const SHARED_API_EXACT: readonly string[] = ['/api/health']

function matches(pathname: string, exact: readonly string[], prefixes: readonly string[]): boolean {
  if (exact.includes(pathname)) return true
  return prefixes.some((p) => pathname === p || pathname.startsWith(p.endsWith('/') ? p : `${p}/`))
}

/**
 * Should this deployment serve this path at all?
 *
 * Anything not claimed by either side (a new route nobody classified) is served
 * by both — same fail-open reasoning as the default surface. A route that should
 * be restricted must be added to a list explicitly, and the accompanying tests
 * assert that every real route is classified so this cannot rot silently.
 */
export function servesPath(surface: Surface, pathname: string): boolean {
  if (surface === 'both') return true

  if (matches(pathname, SHARED_API_EXACT, SHARED_API_PREFIXES)) return true

  const isCustomer =
    matches(pathname, CUSTOMER_PAGES, CUSTOMER_PAGE_PREFIXES) ||
    matches(pathname, CUSTOMER_API_EXCEPTIONS, CUSTOMER_API_PREFIXES)

  const isOperator =
    matches(pathname, OPERATOR_PAGES, OPERATOR_PAGE_PREFIXES) ||
    // Bot console API: everything under /api/{bot}/ except the pause exceptions
    // already matched above.
    (pathname.startsWith('/api/') && isBotConsoleApi(pathname)) ||
    matches(pathname, [], OPERATOR_API_PREFIXES)

  if (surface === 'customer') {
    // Claimed by the customer side, or claimed by neither (unclassified → serve).
    return isCustomer || !isOperator
  }
  // operator
  return isOperator || !isCustomer
}

/**
 * Surface as seen by CLIENT components.
 *
 * `IRONFORGE_MODE` is server-only, so nav components read the NEXT_PUBLIC_ mirror,
 * which Next inlines at build time. Each service builds its own image with its own
 * env, so this is accurate per deployment.
 *
 * Degrades safely: if the mirror is not set, this returns 'both' and nav renders
 * exactly as it does today. A nav link to the other half would then be a dead
 * link, because middleware still 404s it — cosmetic, never a data leak. The
 * security boundary is middleware plus the credential split, never this.
 */
export function clientSurface(): Surface {
  return resolveSurface(process.env.NEXT_PUBLIC_IRONFORGE_MODE)
}

/**
 * Filter a nav list down to what this deployment actually serves.
 *
 * Reusing servesPath means a nav item can never point at a route the deployment
 * 404s — the two cannot drift, because they read the same lists. This is how the
 * "Performance → /spark" operator link disappears from the customer site.
 */
export function filterNavBySurface<T extends { href: string | null }>(
  items: readonly T[],
  surface: Surface = clientSurface(),
): T[] {
  return items.filter((item) => item.href == null || servesPath(surface, item.href))
}

const BOT_SLUGS = ['spark', 'spark2', 'flame', 'inferno', 'blaze', 'flare', 'kindle']

/** True for `/api/{bot}/...` where {bot} is a known bot console slug. */
function isBotConsoleApi(pathname: string): boolean {
  const seg = pathname.split('/')[2]
  return seg != null && BOT_SLUGS.includes(seg)
}
