/**
 * Deep links back into the mobile app (APP-034, APP-041).
 *
 * Two link types, and the distinction matters:
 *
 *   - **Universal Link / App Link** (`https://ironforge.trade/app/...`) — cryptographically
 *     bound to the domain via /.well-known. This is the canonical form.
 *   - **Custom scheme** (`ironforge://...`) — a fallback. ANY installed app can register
 *     a custom scheme, so it is not an identity claim; never make it the only path for
 *     anything carrying a token or a state parameter.
 *
 * Third parties (Stripe, brokerage OAuth) will not redirect to a custom scheme at all:
 * Stripe rejects non-https return URLs at session-creation time. So the mobile flow is
 * always `provider → https bridge page → app`, never `provider → ironforge://`.
 */

export const APP_SCHEME = 'ironforge'

/**
 * In-app destinations a bridge or push payload may target.
 *
 * An allowlist rather than validation-by-shape: `route` reaches this from a Stripe
 * redirect or a push payload, and "starts with /" is not enough — `/ops/impersonate`
 * starts with a slash too. Enumerating the customer surface means a new operator route
 * can never become reachable by forgetting to exclude it.
 */
export const ALLOWED_APP_ROUTES = [
  '/live',
  '/home',
  '/performance',
  '/community',
  '/account',
  '/account/billing',
  '/account/trades',
  '/account/brokerage',
  '/settings',
  '/onboarding/brokerage',
  '/enroll/broker',
] as const

export type AppRoute = (typeof ALLOWED_APP_ROUTES)[number]

export function isAllowedAppRoute(route: string): route is AppRoute {
  return (ALLOWED_APP_ROUTES as readonly string[]).includes(route)
}

/**
 * Normalize an untrusted route to a safe one.
 * Protocol-relative (`//evil.com`) and absolute URLs are rejected outright — they are
 * the open-redirect shape, and neither is ever a legitimate in-app route.
 */
export function safeAppRoute(route: string | null | undefined, fallback: AppRoute = '/live'): AppRoute {
  if (!route || typeof route !== 'string') return fallback
  if (!route.startsWith('/') || route.startsWith('//')) return fallback
  const path = route.split('?')[0].split('#')[0]
  return isAllowedAppRoute(path) ? (path as AppRoute) : fallback
}

/** The custom-scheme form, for the bridge page's final hop. */
export function appSchemeUrl(route: AppRoute, params: Record<string, string> = {}): string {
  const qs = new URLSearchParams(params).toString()
  return `${APP_SCHEME}://${route.replace(/^\//, '')}${qs ? `?${qs}` : ''}`
}

export type BillingClient = 'web' | 'mobile'

/**
 * Where a third party should send the customer back to.
 *
 * Web gets the page directly. Mobile gets the https bridge at /app/return, which then
 * hands off to the app — because Stripe and the brokerage portals will only accept an
 * https URL, and because an https Universal Link is the form that is actually verified.
 */
export function billingReturn(
  origin: string,
  client: BillingClient,
  dest: string,
  extra: Record<string, string> = {},
): string {
  if (client === 'web') {
    const qs = new URLSearchParams(extra).toString()
    return `${origin}${dest}${qs ? (dest.includes('?') ? '&' : '?') + qs : ''}`
  }
  const params = new URLSearchParams({ to: safeAppRoute(dest), ...extra })
  return `${origin}/app/return?${params.toString()}`
}
