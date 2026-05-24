import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { safeEqual, hasValidServiceToken, serviceHeaders } from '../session'

describe('safeEqual', () => {
  it('is true for equal strings', () => expect(safeEqual('abc', 'abc')).toBe(true))
  it('is false for different strings', () => expect(safeEqual('abc', 'abd')).toBe(false))
  it('is false for different lengths', () => expect(safeEqual('abc', 'abcd')).toBe(false))
})

describe('hasValidServiceToken', () => {
  const orig = process.env.IRONFORGE_SERVICE_TOKEN
  beforeEach(() => { process.env.IRONFORGE_SERVICE_TOKEN = 'secret-token' })
  afterEach(() => { process.env.IRONFORGE_SERVICE_TOKEN = orig })

  it('is true for a matching header', () => expect(hasValidServiceToken('secret-token')).toBe(true))
  it('is false for a wrong header', () => expect(hasValidServiceToken('nope')).toBe(false))
  it('is false for a null header', () => expect(hasValidServiceToken(null)).toBe(false))
  it('is false when no token is configured', () => {
    delete process.env.IRONFORGE_SERVICE_TOKEN
    expect(hasValidServiceToken('anything')).toBe(false)
  })
})

describe('serviceHeaders', () => {
  it('returns the service header keyed value', () => {
    process.env.IRONFORGE_SERVICE_TOKEN = 'abc'
    expect(serviceHeaders()).toEqual({ 'x-ironforge-service': 'abc' })
  })
})
