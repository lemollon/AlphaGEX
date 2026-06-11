import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  signOnboardingToken,
  verifyOnboardingToken,
  ONBOARDING_TTL_MS,
} from '@/lib/auth/onboarding'

const OLD = { ...process.env }

beforeEach(() => {
  process.env.IRONFORGE_SESSION_SECRET = 'a-test-secret-at-least-32-chars-long!!'
})
afterEach(() => {
  process.env = { ...OLD }
})

describe('onboarding token', () => {
  it('round-trips a signed token back to its claims', async () => {
    const now = 1_000_000
    const token = await signOnboardingToken('user-123', now)
    const claims = await verifyOnboardingToken(token, now + 1000)
    expect(claims).not.toBeNull()
    expect(claims!.uid).toBe('user-123')
    expect(claims!.exp).toBe(now + ONBOARDING_TTL_MS)
  })

  it('rejects a tampered payload', async () => {
    const token = await signOnboardingToken('user-123', 1000)
    const [, sig] = token.split('.')
    // forge a different uid but keep the original signature
    const forgedPayload = Buffer.from(JSON.stringify({ uid: 'attacker', exp: Date.now() + 10000 }))
      .toString('base64url')
    const forged = `${forgedPayload}.${sig}`
    expect(await verifyOnboardingToken(forged)).toBeNull()
  })

  it('rejects an expired token', async () => {
    const now = 1_000_000
    const token = await signOnboardingToken('user-123', now)
    const afterExpiry = now + ONBOARDING_TTL_MS + 1
    expect(await verifyOnboardingToken(token, afterExpiry)).toBeNull()
  })

  it('returns null for missing/garbage tokens', async () => {
    expect(await verifyOnboardingToken(undefined)).toBeNull()
    expect(await verifyOnboardingToken('')).toBeNull()
    expect(await verifyOnboardingToken('not-a-token')).toBeNull()
  })

  it('fails closed when the secret is unset', async () => {
    const token = await signOnboardingToken('user-123', 1000)
    delete process.env.IRONFORGE_SESSION_SECRET
    expect(await verifyOnboardingToken(token)).toBeNull()
  })

  it('does not verify under a different secret', async () => {
    const token = await signOnboardingToken('user-123', 1000)
    process.env.IRONFORGE_SESSION_SECRET = 'a-completely-different-secret-value!!'
    expect(await verifyOnboardingToken(token, 2000)).toBeNull()
  })
})
