import { describe, it, expect, afterEach } from 'vitest'
import { isPublicPath, isCustomerPath, decideAccess, isPublicMode } from '../access'

describe('isPublicPath', () => {
  it('treats login, auth endpoints, and health as public', () => {
    expect(isPublicPath('/login')).toBe(true)
    // Operator password login was retired 2026-07-27; the route no longer exists.
    expect(isPublicPath('/api/auth/login')).toBe(false)
    expect(isPublicPath('/api/auth/logout')).toBe(true)
    expect(isPublicPath('/api/auth/seed')).toBe(false)
    expect(isPublicPath('/api/health')).toBe(true)
  })
  it('treats the signup page and signup endpoint as public', () => {
    expect(isPublicPath('/signup')).toBe(true)
    expect(isPublicPath('/api/auth/signup')).toBe(true)
  })
  it('treats the pricing page as public', () => {
    expect(isPublicPath('/pricing')).toBe(true)
  })
  it('treats the email-verify callback as public', () => {
    expect(isPublicPath('/api/auth/verify')).toBe(true)
  })
  it('treats the resend-verification endpoint as public', () => {
    expect(isPublicPath('/api/auth/resend-verification')).toBe(true)
  })
  it('treats operator pages and bot routes as non-public', () => {
    // NB: '/' IS public — it is the marketing homepage. This assertion used to
    // claim otherwise and had been failing since the homepage shipped.
    expect(isPublicPath('/')).toBe(true)
    expect(isPublicPath('/spark')).toBe(false)
    expect(isPublicPath('/api/spark/status')).toBe(false)
    expect(isPublicPath('/api/auth/me')).toBe(false)
  })
  it('exposes the public track record but not the customer surface', () => {
    expect(isPublicPath('/track-record')).toBe(true)
    expect(isPublicPath('/api/public/track-record')).toBe(true)
    expect(isPublicPath('/bot-ledger')).toBe(true)
    // These pass via the /api/public/ prefix branch; asserted explicitly so a
    // future narrowing of that branch is caught here rather than in production.
    expect(isPublicPath('/api/public/bot-ledger/summary')).toBe(true)
    expect(isPublicPath('/api/public/bot-ledger/trades')).toBe(true)
    for (const p of ['/home', '/live', '/performance', '/community', '/account/trades']) {
      expect(isPublicPath(p)).toBe(false)
    }
    expect(isPublicPath('/api/live/summary')).toBe(false)
  })
})

describe('isCustomerPath', () => {
  it('claims the customer surface and its aggregation APIs', () => {
    for (const p of ['/home', '/live', '/performance', '/community', '/account/trades']) {
      expect(isCustomerPath(p)).toBe(true)
    }
    expect(isCustomerPath('/api/live/summary')).toBe(true)
    expect(isCustomerPath('/api/spark/production-pause')).toBe(true)
  })
  it('does not claim public or operator paths', () => {
    for (const p of ['/', '/pricing', '/track-record', '/spark', '/api/spark/status']) {
      expect(isCustomerPath(p)).toBe(false)
    }
  })
})

describe('decideAccess', () => {
  const base = { pathname: '/spark', isApi: false, hasSession: false, hasServiceToken: false }
  it('allows when a valid service token is present', () => {
    expect(decideAccess({ ...base, isApi: true, pathname: '/api/spark/status', hasServiceToken: true })).toBe('allow')
  })
  it('allows public paths without a session', () => {
    expect(decideAccess({ ...base, pathname: '/login' })).toBe('allow')
  })
  it('allows any path with a session', () => {
    expect(decideAccess({ ...base, hasSession: true })).toBe('allow')
  })
  it('returns unauthorized for gated API without session', () => {
    expect(decideAccess({ ...base, isApi: true, pathname: '/api/spark/status' })).toBe('unauthorized')
  })
  it('returns redirect-login for gated page without session', () => {
    expect(decideAccess({ ...base })).toBe('redirect-login')
  })
})

describe('decideAccess — customer surface', () => {
  const base = { isApi: false, hasSession: false, hasServiceToken: false }
  it('sends an anonymous visitor to the CUSTOMER door, not the operator door', () => {
    expect(decideAccess({ ...base, pathname: '/live' })).toBe('redirect-customer-login')
    expect(decideAccess({ ...base, pathname: '/home' })).toBe('redirect-customer-login')
  })
  it('still sends anonymous operator-surface requests to the operator door', () => {
    expect(decideAccess({ ...base, pathname: '/spark' })).toBe('redirect-login')
  })
  it('admits a customer session to the customer surface', () => {
    expect(decideAccess({ ...base, pathname: '/live', hasCustomerSession: true })).toBe('allow')
  })
  it('does NOT admit a customer session to the operator surface', () => {
    expect(decideAccess({ ...base, pathname: '/spark', hasCustomerSession: true })).toBe('redirect-login')
  })
  it('admits an operator to the customer surface', () => {
    expect(decideAccess({ ...base, pathname: '/live', hasSession: true })).toBe('allow')
  })
  it('401s an unauthenticated customer API call instead of redirecting', () => {
    expect(decideAccess({ ...base, pathname: '/api/live/summary', isApi: true })).toBe('unauthorized')
  })
  it('leaves the public track record open', () => {
    expect(decideAccess({ ...base, pathname: '/track-record' })).toBe('allow')
    expect(decideAccess({ ...base, pathname: '/api/public/track-record', isApi: true })).toBe('allow')
  })
})

describe('isPublicMode', () => {
  const prev = process.env.IRONFORGE_PUBLIC_MODE
  afterEach(() => {
    if (prev === undefined) delete process.env.IRONFORGE_PUBLIC_MODE
    else process.env.IRONFORGE_PUBLIC_MODE = prev
  })

  it('is true only for the exact string "true"', () => {
    process.env.IRONFORGE_PUBLIC_MODE = 'true'
    expect(isPublicMode()).toBe(true)
  })
  // Fail-secure: every other value, including a lost variable, keeps the gate on.
  it('is false when unset', () => {
    delete process.env.IRONFORGE_PUBLIC_MODE
    expect(isPublicMode()).toBe(false)
  })
  it.each(['false', 'TRUE', '1', 'yes', ''])('is false for %o', (v) => {
    process.env.IRONFORGE_PUBLIC_MODE = v
    expect(isPublicMode()).toBe(false)
  })
  it('reads the variable at call time, not at import time', () => {
    delete process.env.IRONFORGE_PUBLIC_MODE
    expect(isPublicMode()).toBe(false)
    process.env.IRONFORGE_PUBLIC_MODE = 'true'
    expect(isPublicMode()).toBe(true)
  })
})

// ── Mobile bearer surface ──
//
// A bearer token must be EXACTLY as powerful as the customer cookie and no more.
// The whole reason hasBearerCustomer is consumed inside the isCustomerPath branch
// (and nowhere else) is so the operator surface stays closed by construction rather
// than by an allowlist someone has to remember to update.

describe('mobile bearer access', () => {
  const base = { isApi: true, hasSession: false, hasServiceToken: false }

  it('opens the customer API surface', () => {
    for (const p of ['/api/live/summary', '/api/live/trades', '/api/support/chat', '/api/v1/enrollment']) {
      expect(decideAccess({ ...base, pathname: p, hasBearerCustomer: true })).toBe('allow')
    }
  })

  it('opens customer PAGES too, so deep links resolve', () => {
    expect(decideAccess({ ...base, isApi: false, pathname: '/live', hasBearerCustomer: true })).toBe('allow')
  })

  it('does NOT open the operator surface', () => {
    // The failure mode this pins: a customer token reaching bot control or account CRUD.
    for (const p of ['/api/spark/status', '/api/accounts/manage', '/api/scanner/status']) {
      expect(decideAccess({ ...base, pathname: p, hasBearerCustomer: true })).toBe('unauthorized')
    }
    expect(decideAccess({ ...base, isApi: false, pathname: '/spark', hasBearerCustomer: true }))
      .toBe('redirect-login')
  })

  it('still 401s a customer API path with no credential of any kind', () => {
    expect(decideAccess({ ...base, pathname: '/api/live/summary' })).toBe('unauthorized')
  })

  it('treats the mobile auth endpoints as public (they self-guard in-route)', () => {
    expect(isPublicPath('/api/auth/mobile/login')).toBe(true)
    expect(isPublicPath('/api/auth/mobile/refresh')).toBe(true)
    expect(isPublicPath('/api/auth/mobile/policy')).toBe(true)
  })

  // Universal Links / App Links verification files. apple-app-site-association has NO
  // file extension, so the middleware page matcher (extension-anchored) matches it; without
  // this branch Apple's cookieless fetcher gets a 307 to /login and Universal Links
  // silently never verify — no error, no log, just links that always open Safari.
  it('serves the .well-known association files unauthenticated', () => {
    expect(isPublicPath('/.well-known/apple-app-site-association')).toBe(true)
    expect(isPublicPath('/.well-known/assetlinks.json')).toBe(true)
  })

  // Regression: /app/* was classified in surface.ts (which SERVICE serves it) but not in
  // access.ts (whether it needs a session), so the bridge 307'd to /ops/login — the
  // OPERATOR door — at the end of every mobile checkout and brokerage connect. The
  // browser arriving here is a fresh ASWebAuthenticationSession with no cookie, so it
  // could never satisfy that. Caught by a live smoke test; pinned here.
  it('serves the mobile hand-off bridge unauthenticated', () => {
    expect(isPublicPath('/app/return')).toBe(true)
    expect(isPublicPath('/app/brokerage/return')).toBe(true)
    expect(
      decideAccess({ ...base, isApi: false, pathname: '/app/return', hasBearerCustomer: false }),
    ).toBe('allow')
  })
})
