import { describe, it, expect } from 'vitest'
import { readdirSync, statSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import {
  resolveSurface,
  servesPath,
  CUSTOMER_PAGES,
  OPERATOR_PAGES,
  CUSTOMER_API_EXCEPTIONS,
  OPERATOR_LANDING,
} from '../surface'

/**
 * The customer/operator surface split. These tests exist because the route lists
 * are the kind of thing that silently rots: someone adds a page, forgets to
 * classify it, and it quietly appears on the public site.
 */

describe('resolveSurface', () => {
  it('defaults to "both" so a deploy that forgot the var serves everything', () => {
    expect(resolveSurface(undefined)).toBe('both')
    expect(resolveSurface(null)).toBe('both')
    expect(resolveSurface('')).toBe('both')
    expect(resolveSurface('nonsense')).toBe('both')
    expect(resolveSurface('CUSTOMER')).toBe('both') // case-sensitive by design
  })

  it('recognises the two real surfaces', () => {
    expect(resolveSurface('customer')).toBe('customer')
    expect(resolveSurface('operator')).toBe('operator')
  })
})

describe('surface "both" is a no-op', () => {
  it('serves every classified path', () => {
    for (const p of [...CUSTOMER_PAGES, ...OPERATOR_PAGES, '/api/spark/force-trade', '/whatever']) {
      expect(servesPath('both', p)).toBe(true)
    }
  })
})

describe('customer surface', () => {
  it('serves the customer pages', () => {
    for (const p of CUSTOMER_PAGES) {
      expect(servesPath('customer', p), `customer should serve ${p}`).toBe(true)
    }
  })

  it('serves the onboarding funnel', () => {
    for (const p of ['/onboarding', '/onboarding/legal', '/onboarding/risk', '/onboarding/brokerage']) {
      expect(servesPath('customer', p), `customer should serve ${p}`).toBe(true)
    }
  })

  it('does NOT serve operator pages', () => {
    for (const p of OPERATOR_PAGES) {
      expect(servesPath('customer', p), `customer must NOT serve ${p}`).toBe(false)
    }
  })

  it('does NOT serve the dangerous bot-console writes', () => {
    // The whole point of the split: these place and close real trades.
    for (const p of [
      '/api/spark/force-trade',
      '/api/spark/force-close',
      '/api/spark/eod-close',
      '/api/spark/toggle',
      '/api/spark/config',
      '/api/spark2/force-trade',
      '/api/flame/force-close',
    ]) {
      expect(servesPath('customer', p), `customer must NOT serve ${p}`).toBe(false)
    }
  })

  it('does NOT serve broker credential APIs', () => {
    for (const p of ['/api/accounts/manage', '/api/accounts/production', '/api/accounts/test-all']) {
      expect(servesPath('customer', p), `customer must NOT serve ${p}`).toBe(false)
    }
  })

  it('DOES serve the pause endpoints the Live page needs', () => {
    for (const p of CUSTOMER_API_EXCEPTIONS) {
      expect(servesPath('customer', p), `customer must serve ${p}`).toBe(true)
    }
  })

  it('serves customer API namespaces', () => {
    for (const p of [
      '/api/live/summary',
      '/api/live/trade',
      '/api/community/messages',
      '/api/brokerage/trades',
      '/api/auth/customer-login',
      '/api/health',
    ]) {
      expect(servesPath('customer', p), `customer should serve ${p}`).toBe(true)
    }
  })
})

describe('operator surface', () => {
  it('serves operator pages and bot APIs', () => {
    for (const p of [...OPERATOR_PAGES, '/api/spark/force-trade', '/api/accounts/manage', '/briefings/archive']) {
      expect(servesPath('operator', p), `operator should serve ${p}`).toBe(true)
    }
  })

  it('does NOT serve the customer product pages', () => {
    for (const p of ['/live', '/home', '/community', '/pricing', '/how-it-works']) {
      expect(servesPath('operator', p), `operator must NOT serve ${p}`).toBe(false)
    }
  })

  it('still serves shared auth + health', () => {
    for (const p of ['/api/auth/login', '/api/health']) {
      expect(servesPath('operator', p)).toBe(true)
    }
  })
})

describe('the two surfaces partition the app', () => {
  it('no classified page is served by both restricted surfaces', () => {
    for (const p of [...CUSTOMER_PAGES, ...OPERATOR_PAGES]) {
      const c = servesPath('customer', p)
      const o = servesPath('operator', p)
      expect(c && o, `${p} must not be served by both`).toBe(false)
      expect(c || o, `${p} must be served by at least one`).toBe(true)
    }
  })
})

/**
 * Drift guard: every real page in the app router must be classified. Without
 * this, a new page silently defaults to "served by both" — which on the customer
 * site means an unreviewed page going public.
 */
describe('route classification is complete', () => {
  const appDir = join(__dirname, '..', '..', 'app')

  function collectRoutes(dir: string, prefix = ''): string[] {
    if (!existsSync(dir)) return []
    const out: string[] = []
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry)
      if (!statSync(full).isDirectory()) {
        if (entry === 'page.tsx') out.push(prefix === '' ? '/' : prefix)
        continue
      }
      // Skip route groups (parenthesised) and dynamic segments — dynamic pages
      // are covered by their parent prefix.
      if (entry.startsWith('(') || entry.startsWith('[') || entry === 'api') continue
      out.push(...collectRoutes(full, `${prefix}/${entry}`))
    }
    return out
  }

  it('every page route is claimed by exactly one surface', () => {
    const routes = collectRoutes(appDir)
    expect(routes.length, 'expected to discover app router pages').toBeGreaterThan(10)

    const unclassified = routes
      .filter((r) => servesPath('customer', r) && servesPath('operator', r))
      // /ops/* is deliberately shared: the operator sign-in must exist on both
      // deployments (see SHARED_PAGE_PREFIXES). Every OTHER page must still be
      // claimed by exactly one surface, which is what this guard protects.
      .filter((r) => !r.startsWith('/ops'))
    expect(
      unclassified,
      `these pages are not classified in surface.ts and would be served by BOTH sites: ${unclassified.join(', ')}`,
    ).toEqual([])
  })
})

describe('operator landing page', () => {
  // '/' belongs to the customer surface, so the operator console redirects it.
  // If OPERATOR_LANDING ever pointed at a route the operator surface does NOT
  // serve, the console's root URL would redirect straight into a 404.
  it('is a route the operator surface actually serves', () => {
    expect(servesPath('operator', OPERATOR_LANDING)).toBe(true)
  })

  it('is not a customer route', () => {
    expect(servesPath('customer', OPERATOR_LANDING)).toBe(false)
  })

  it("confirms '/' is why the redirect is needed", () => {
    expect(servesPath('operator', '/')).toBe(false)
    expect(servesPath('customer', '/')).toBe(true)
  })
})

describe('operator sign-in is reachable on BOTH deployments', () => {
  // Regression: classifying /ops/* as operator-only 404'd the operator login
  // and the admin magic link on the customer site, leaving no way to get an
  // operator session there at all.
  it('serves /ops/login on both surfaces', () => {
    expect(servesPath('customer', '/ops/login')).toBe(true)
    expect(servesPath('operator', '/ops/login')).toBe(true)
  })

  it('serves the admin magic link on both surfaces', () => {
    expect(servesPath('customer', '/api/ops/admin')).toBe(true)
    expect(servesPath('operator', '/api/ops/admin')).toBe(true)
  })

  it('still hides the dangerous operator surfaces from customers', () => {
    for (const p of ['/accounts', '/api/accounts/manage', '/api/spark/force-trade', '/spark']) {
      expect(servesPath('customer', p), `${p} must stay hidden`).toBe(false)
    }
  })
})
