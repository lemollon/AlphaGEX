/**
 * Which half of IronForge a given deployment serves.
 *
 * The app is deployed twice from one image:
 *
 *   PRODUCT (ironforge.trade)
 *     The real business. SPARK, SPARK2 and FLAME; the live broker accounts; and
 *     everything a paying customer sees (marketing, signup, Live, Home,
 *     Community). Holds the broker credentials. Runs the trading engine.
 *
 *   LAB (ironforge-899p.onrender.com)
 *     Private research. INFERNO, BLAZE, FLARE, KINDLE; backtests (EMBER); the
 *     GEX/volatility/briefing tools. NO live money and NO account credentials.
 *     Displays results the product engine wrote; it does not drive trading.
 *
 * Selected by IRONFORGE_MODE. Imported by middleware (Edge), server components
 * AND client components, so it must stay free of `next/server`, the DB client,
 * auth, and import-time side effects.
 *
 * DEFAULT IS 'both'. An unset IRONFORGE_MODE serves everything — today's
 * behaviour. Deliberate: a deploy that forgot the variable must not silently
 * 404 half the app. Each service opts IN to being restricted.
 *
 * This is a routing boundary, NOT the security boundary. Auth still gates
 * operator pages independently, and the real protection is that the lab does not
 * hold the account credentials — so it cannot place a live order even if a
 * routing bug let a page render.
 */

export type Surface = 'product' | 'lab' | 'both'

export function resolveSurface(raw?: string | null): Surface {
  return raw === 'product' ? 'product' : raw === 'lab' ? 'lab' : 'both'
}

/** Live-money bots. Their consoles and APIs belong to the product only. */
export const PRODUCT_BOTS = ['spark', 'spark2', 'flame'] as const

/** Paper/research bots. Lab only — none of these ever touches real money. */
export const LAB_BOTS = ['inferno', 'blaze', 'flare', 'kindle'] as const

/** Customer-facing and marketing pages — product only. */
export const PRODUCT_PAGES: readonly string[] = [
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
  // Bot consoles for the live-money bots, plus the broker account manager.
  '/spark',
  '/spark2',
  '/flame',
  '/accounts',
]

export const PRODUCT_PAGE_PREFIXES: readonly string[] = ['/onboarding']

/** Research consoles and analysis tooling — lab only. */
export const LAB_PAGES: readonly string[] = [
  '/inferno',
  '/blaze',
  '/flare',
  '/kindle',
  '/ember',
  '/gex',
  '/volatility',
  '/calendar',
  '/compare',
]

export const LAB_PAGE_PREFIXES: readonly string[] = ['/briefings', '/calendar/']

/** Broker credential management. Product only — this is the live-account page. */
export const PRODUCT_API_PREFIXES: readonly string[] = [
  '/api/accounts/',
  '/api/live/',
  '/api/community/',
  '/api/brokerage/',
  '/api/onboarding/',
]

export const LAB_API_PREFIXES: readonly string[] = [
  '/api/ember/',
  '/api/briefings/',
  '/api/calendar/',
]

/** Operator login + admin link: both services need their own way in. */
export const SHARED_PAGES: readonly string[] = ['/ops/login']
export const SHARED_PAGE_PREFIXES: readonly string[] = ['/ops']
export const SHARED_API_PREFIXES: readonly string[] = ['/api/auth/', '/api/ops/']
export const SHARED_API_EXACT: readonly string[] = ['/api/health']

function matches(pathname: string, exact: readonly string[], prefixes: readonly string[]): boolean {
  if (exact.includes(pathname)) return true
  return prefixes.some((p) => pathname === p || pathname.startsWith(p.endsWith('/') ? p : `${p}/`))
}

/** `/api/{bot}/...` → the bot slug, or null when not a bot-console route. */
function botApiSlug(pathname: string): string | null {
  if (!pathname.startsWith('/api/')) return null
  const seg = pathname.split('/')[2] ?? ''
  const all: readonly string[] = [...PRODUCT_BOTS, ...LAB_BOTS]
  return all.includes(seg) ? seg : null
}

/**
 * Should this deployment serve this path?
 *
 * Anything claimed by neither side (a new, unclassified route) is served by
 * both — same fail-open reasoning as the default surface. The accompanying test
 * walks the app router and fails if any real page is unclassified, so this
 * cannot rot silently.
 */
export function servesPath(surface: Surface, pathname: string): boolean {
  if (surface === 'both') return true

  if (
    matches(pathname, SHARED_API_EXACT, SHARED_API_PREFIXES) ||
    matches(pathname, SHARED_PAGES, SHARED_PAGE_PREFIXES)
  ) {
    return true
  }

  const slug = botApiSlug(pathname)
  if (slug) {
    return surface === 'product'
      ? (PRODUCT_BOTS as readonly string[]).includes(slug)
      : (LAB_BOTS as readonly string[]).includes(slug)
  }

  const isProduct =
    matches(pathname, PRODUCT_PAGES, PRODUCT_PAGE_PREFIXES) ||
    matches(pathname, [], PRODUCT_API_PREFIXES)

  const isLab = matches(pathname, LAB_PAGES, LAB_PAGE_PREFIXES) || matches(pathname, [], LAB_API_PREFIXES)

  return surface === 'product' ? isProduct || !isLab : isLab || !isProduct
}

/**
 * Surface as seen by CLIENT components.
 *
 * IRONFORGE_MODE is server-only, so nav reads the NEXT_PUBLIC_ mirror, which
 * Next inlines at build time. Each service builds its own image, so it is
 * accurate per deployment.
 *
 * Degrades safely: unset → 'both' → nav renders as today. A stale nav link
 * would be a dead link (middleware still 404s it), never a data leak.
 */
export function clientSurface(): Surface {
  return resolveSurface(process.env.NEXT_PUBLIC_IRONFORGE_MODE)
}

/**
 * Filter a nav list to what this deployment serves.
 *
 * Reusing servesPath means a nav item can never point at a route this
 * deployment 404s — they read the same lists, so they cannot drift.
 */
export function filterNavBySurface<T extends { href: string | null }>(
  items: readonly T[],
  surface: Surface = clientSurface(),
): T[] {
  return items.filter((item) => item.href == null || servesPath(surface, item.href))
}
