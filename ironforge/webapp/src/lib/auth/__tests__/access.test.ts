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

  // Google Search Console verification file (HTML-file method). Google's cookieless
  // crawler would otherwise 307 to /login, same failure mode as the apple-app-
  // site-association bug above — verification fails silently, with no error and no log.
  it('serves the Google site-verification file unauthenticated', () => {
    expect(isPublicPath('/googleeca775e503b449ab.html')).toBe(true)
    // Convention-matched, not hardcoded to one token — the next re-verification must
    // not require another code change.
    expect(isPublicPath('/google1234567890abcdef.html')).toBe(true)
    expect(
      decideAccess({ ...base, isApi: false, pathname: '/googleeca775e503b449ab.html' }),
    ).toBe('allow')
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

  // Google Play requires account deletion to be requestable from a URL that works
  // WITHOUT signing in — a deletion page behind a login wall does not count, because
  // the people most likely to need it are the ones locked out.
  it('serves /delete-account unauthenticated', () => {
    expect(isPublicPath('/delete-account')).toBe(true)
    expect(decideAccess({ ...base, isApi: false, pathname: '/delete-account' })).toBe('allow')
  })

  // The PAGE is public but the ACTION must not be: anyone who could POST this
  // anonymously could cancel a stranger's subscription and disconnect their broker.
  // It must answer 401 rather than redirect — the client reads res.status === 401 to
  // decide "show the sign-in prompt", and a 307 to an HTML login page would be read
  // as success and then fail on JSON.parse. Same gate-vs-guard trap as /api/v1/ and
  // /api/auth/change-password before it.
  it('requires a session for the deletion-request API, and 401s rather than redirecting', () => {
    expect(isPublicPath('/api/account/deletion-request')).toBe(false)
    expect(isCustomerPath('/api/account/deletion-request')).toBe(true)
    expect(
      decideAccess({ ...base, isApi: true, pathname: '/api/account/deletion-request' }),
    ).toBe('unauthorized')
    // A signed-in customer — by cookie or by mobile bearer — gets through.
    expect(
      decideAccess({
        ...base,
        isApi: true,
        pathname: '/api/account/deletion-request',
        hasCustomerSession: true,
      }),
    ).toBe('allow')
    expect(
      decideAccess({
        ...base,
        isApi: true,
        pathname: '/api/account/deletion-request',
        hasBearerCustomer: true,
      }),
    ).toBe('allow')
  })

  // The purge is the irreversible half. A customer must never reach it: a mobile
  // bearer is deliberately scoped to be exactly as strong as the customer cookie and
  // no stronger, so it must NOT open an operator route. This is the property that
  // keeps the operator surface closed by construction rather than by an allowlist
  // that rots as routes are added — so it gets asserted, not assumed.
  it('keeps the deletion purge on the operator surface, closed to customers', () => {
    const path = '/api/ops/account-deletion/purge'
    expect(isPublicPath(path)).toBe(false)
    expect(isCustomerPath(path)).toBe(false)
    expect(decideAccess({ ...base, isApi: true, pathname: path })).toBe('unauthorized')
    expect(
      decideAccess({ ...base, isApi: true, pathname: path, hasCustomerSession: true }),
    ).toBe('unauthorized')
    expect(
      decideAccess({ ...base, isApi: true, pathname: path, hasBearerCustomer: true }),
    ).toBe('unauthorized')
    // Only an operator session gets through.
    expect(decideAccess({ ...base, isApi: true, pathname: path, hasSession: true })).toBe('allow')
  })
})
