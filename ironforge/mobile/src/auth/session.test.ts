import { describe, it, expect, vi } from 'vitest'

/**
 * session.ts reaches expo-local-authentication and, through api/client, expo-constants
 * and react-native (via api/storage). None of that exists in the node test environment
 * and none of it is the subject here — see the identical note in api/client.test.ts.
 * Mock the edges, keep session.ts real.
 */
vi.mock('expo-local-authentication', () => ({
  hasHardwareAsync: async () => false,
  isEnrolledAsync: async () => false,
  authenticateAsync: async () => ({ success: false }),
}))

vi.mock('expo-constants', () => ({
  default: { expoConfig: { extra: { apiBase: 'https://example.test' } } },
}))

vi.mock('@/api/storage', () => ({
  setItem: async () => {},
  getItem: async () => null,
  deleteItem: async () => {},
  AFTER_FIRST_UNLOCK: 'AFTER_FIRST_UNLOCK',
}))

const { shouldLock } = await import('./session')

/**
 * shouldLock had no tests before this file. It is the single piece of math the
 * foreground lock (APP-010) hinges on, so a regression here would silently widen or
 * shrink the lock window without anyone noticing.
 */
describe('shouldLock', () => {
  const policy = { foregroundLockSec: 300 }

  it('never locks if the app was never backgrounded', () => {
    expect(shouldLock(null, policy, Date.now())).toBe(false)
  })

  it('does not lock when under the threshold', () => {
    const now = 1_000_000_000
    expect(shouldLock(now - 299_000, policy, now)).toBe(false)
  })

  it('locks once strictly over the threshold', () => {
    const now = 1_000_000_000
    expect(shouldLock(now - 301_000, policy, now)).toBe(true)
  })

  it('does not lock exactly at the threshold', () => {
    const now = 1_000_000_000
    expect(shouldLock(now - 300_000, policy, now)).toBe(false)
  })

  it('respects a tighter server-driven policy', () => {
    const now = 1_000_000_000
    const tight = { foregroundLockSec: 30 }
    expect(shouldLock(now - 31_000, tight, now)).toBe(true)
    expect(shouldLock(now - 29_000, tight, now)).toBe(false)
  })
})
