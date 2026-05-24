import { describe, it, expect } from 'vitest'
import { isPublicPath, decideAccess } from '../access'

describe('isPublicPath', () => {
  it('treats login, auth endpoints, and health as public', () => {
    expect(isPublicPath('/login')).toBe(true)
    expect(isPublicPath('/api/auth/login')).toBe(true)
    expect(isPublicPath('/api/auth/logout')).toBe(true)
    expect(isPublicPath('/api/auth/seed')).toBe(true)
    expect(isPublicPath('/api/health')).toBe(true)
  })
  it('treats app pages and bot routes as non-public', () => {
    expect(isPublicPath('/')).toBe(false)
    expect(isPublicPath('/spark')).toBe(false)
    expect(isPublicPath('/api/spark/status')).toBe(false)
    expect(isPublicPath('/api/auth/me')).toBe(false)
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
