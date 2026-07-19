import { describe, it, expect } from 'vitest'
import { readdirSync, statSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import {
  resolveSurface,
  servesPath,
  PRODUCT_PAGES,
  LAB_PAGES,
  PRODUCT_BOTS,
  LAB_BOTS,
} from '../surface'

/**
 * The product/lab split.
 *
 * PRODUCT = the real business (SPARK, SPARK2, FLAME, live accounts, customer
 * pages). LAB = private research (INFERNO, BLAZE, FLARE, KINDLE, backtests),
 * no live money. These tests exist because the route lists are exactly the kind
 * of thing that rots silently — someone adds a page, forgets to classify it, and
 * it appears on the wrong site.
 */

describe('resolveSurface', () => {
  it('defaults to "both" so a deploy that forgot the var serves everything', () => {
    for (const v of [undefined, null, '', 'nonsense', 'PRODUCT', 'customer', 'operator']) {
      expect(resolveSurface(v as string | null | undefined)).toBe('both')
    }
  })

  it('recognises the two real surfaces', () => {
    expect(resolveSurface('product')).toBe('product')
    expect(resolveSurface('lab')).toBe('lab')
  })
})

describe('"both" is a no-op', () => {
  it('serves everything', () => {
    for (const p of [...PRODUCT_PAGES, ...LAB_PAGES, '/api/spark/force-trade', '/anything']) {
      expect(servesPath('both', p)).toBe(true)
    }
  })
})

describe('product site', () => {
  it('serves the customer product and marketing', () => {
    for (const p of ['/', '/pricing', '/how-it-works', '/live', '/home', '/community', '/account/trades']) {
      expect(servesPath('product', p), `product should serve ${p}`).toBe(true)
    }
  })

  it('serves the live-money bot consoles and the accounts page', () => {
    for (const p of ['/spark', '/spark2', '/flame', '/accounts']) {
      expect(servesPath('product', p), `product should serve ${p}`).toBe(true)
    }
  })

  it('serves the live-money bot APIs', () => {
    for (const b of PRODUCT_BOTS) {
      expect(servesPath('product', `/api/${b}/status`), `product should serve /api/${b}`).toBe(true)
    }
  })

  it('does NOT serve the lab bots or their APIs', () => {
    for (const b of LAB_BOTS) {
      expect(servesPath('product', `/${b}`), `product must NOT serve /${b}`).toBe(false)
      expect(servesPath('product', `/api/${b}/status`), `product must NOT serve /api/${b}`).toBe(false)
    }
  })

  it('does NOT serve the research tooling', () => {
    for (const p of ['/ember', '/gex', '/volatility', '/compare', '/briefings', '/briefings/archive']) {
      expect(servesPath('product', p), `product must NOT serve ${p}`).toBe(false)
    }
  })
})

describe('lab site', () => {
  it('serves the paper bots and research tooling', () => {
    for (const p of ['/inferno', '/blaze', '/flare', '/kindle', '/ember', '/gex', '/volatility', '/compare']) {
      expect(servesPath('lab', p), `lab should serve ${p}`).toBe(true)
    }
  })

  it('serves the paper bot APIs', () => {
    for (const b of LAB_BOTS) {
      expect(servesPath('lab', `/api/${b}/status`), `lab should serve /api/${b}`).toBe(true)
    }
  })

  it('does NOT serve the live-money bots — the core separation', () => {
    for (const b of PRODUCT_BOTS) {
      expect(servesPath('lab', `/${b}`), `lab must NOT serve /${b}`).toBe(false)
      expect(servesPath('lab', `/api/${b}/status`), `lab must NOT serve /api/${b}`).toBe(false)
    }
  })

  it('does NOT serve the live broker accounts page or its API', () => {
    expect(servesPath('lab', '/accounts')).toBe(false)
    expect(servesPath('lab', '/api/accounts/manage')).toBe(false)
    expect(servesPath('lab', '/api/accounts/production')).toBe(false)
  })

  it('does NOT serve the customer product', () => {
    for (const p of ['/live', '/home', '/community', '/pricing', '/signup', '/account/trades']) {
      expect(servesPath('lab', p), `lab must NOT serve ${p}`).toBe(false)
    }
  })

  it('cannot reach the dangerous live-bot writes', () => {
    for (const p of [
      '/api/spark/force-trade',
      '/api/spark/force-close',
      '/api/spark/eod-close',
      '/api/spark/config',
      '/api/spark2/force-trade',
      '/api/flame/force-close',
    ]) {
      expect(servesPath('lab', p), `lab must NOT serve ${p}`).toBe(false)
    }
  })
})

describe('both services keep their own way in', () => {
  it('serves operator login, admin link and health on each', () => {
    for (const s of ['product', 'lab'] as const) {
      expect(servesPath(s, '/ops/login')).toBe(true)
      expect(servesPath(s, '/api/ops/admin')).toBe(true)
      expect(servesPath(s, '/api/auth/login')).toBe(true)
      expect(servesPath(s, '/api/health')).toBe(true)
    }
  })
})

describe('the two surfaces partition the app', () => {
  it('no classified page is served by both', () => {
    for (const p of [...PRODUCT_PAGES, ...LAB_PAGES]) {
      const inProduct = servesPath('product', p)
      const inLab = servesPath('lab', p)
      expect(inProduct && inLab, `${p} must not be on both sites`).toBe(false)
      expect(inProduct || inLab, `${p} must be on at least one site`).toBe(true)
    }
  })

  it('every bot belongs to exactly one side', () => {
    const overlap = (PRODUCT_BOTS as readonly string[]).filter((b) =>
      (LAB_BOTS as readonly string[]).includes(b),
    )
    expect(overlap, 'a bot must never be on both sites').toEqual([])
  })
})

/**
 * Drift guard: every real page must be classified. Without this a new page
 * silently defaults to "served by both" — on the product site that means an
 * unreviewed page going public.
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
      if (entry.startsWith('(') || entry.startsWith('[') || entry === 'api') continue
      out.push(...collectRoutes(full, `${prefix}/${entry}`))
    }
    return out
  }

  it('every page route is claimed by exactly one side', () => {
    const routes = collectRoutes(appDir)
    expect(routes.length, 'expected to discover app router pages').toBeGreaterThan(10)

    const unclassified = routes.filter((r) => servesPath('product', r) && servesPath('lab', r))
    // /ops/* is intentionally shared — both services need an operator login.
    const unexpected = unclassified.filter((r) => !r.startsWith('/ops'))
    expect(
      unexpected,
      `unclassified pages would be served by BOTH sites: ${unexpected.join(', ')}`,
    ).toEqual([])
  })
})
