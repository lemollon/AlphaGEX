import { describe, it, expect } from 'vitest'
import { isPublicPath, isCustomerPath, decideAccess } from '../access'

describe('isPublicPath', () => {
  it('treats login, auth endpoints, and health as public', () => {
    expect(isPublicPath('/login')).toBe(true)
    expect(isPublicPath('/api/auth/login')).toBe(true)
    expect(isPublicPath('/api/auth/logout')).toBe(true)
    expect(isPublicPath('/api/auth/seed')).toBe(true)
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
