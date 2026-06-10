import { describe, it, expect } from 'vitest'
import {
  generateToken,
  hashToken,
  isExpired,
  TOKEN_TTL_MS,
} from '@/lib/auth/verification-token'

describe('generateToken', () => {
  it('returns a non-empty raw token whose hash equals hashToken(raw)', () => {
    const { raw, hash } = generateToken()
    expect(raw.length).toBeGreaterThan(20)
    expect(hash).toBe(hashToken(raw))
  })
  it('produces a different raw token each call', () => {
    expect(generateToken().raw).not.toBe(generateToken().raw)
  })
})

describe('hashToken', () => {
  it('is deterministic for the same input', () => {
    expect(hashToken('abc')).toBe(hashToken('abc'))
  })
  it('differs for different input', () => {
    expect(hashToken('abc')).not.toBe(hashToken('abd'))
  })
  it('does not return the raw value', () => {
    expect(hashToken('abc')).not.toBe('abc')
  })
})

describe('isExpired', () => {
  const base = new Date('2026-06-10T12:00:00Z')
  it('is false before the expiry', () => {
    const expires = new Date(base.getTime() + 1000)
    expect(isExpired(expires, base)).toBe(false)
  })
  it('is true after the expiry', () => {
    const expires = new Date(base.getTime() - 1000)
    expect(isExpired(expires, base)).toBe(true)
  })
  it('accepts an ISO string expiry', () => {
    const expires = new Date(base.getTime() - 1000).toISOString()
    expect(isExpired(expires, base)).toBe(true)
  })
})

describe('TOKEN_TTL_MS', () => {
  it('is 24 hours', () => {
    expect(TOKEN_TTL_MS).toBe(24 * 60 * 60 * 1000)
  })
})
