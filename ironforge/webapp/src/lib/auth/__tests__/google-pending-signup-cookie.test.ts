import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  signGooglePendingSignupState,
  verifyGooglePendingSignupState,
  GOOGLE_PENDING_SIGNUP_TTL_MS,
} from '@/lib/auth/google-pending-signup-cookie'

const SECRET = 'test-secret-value-for-google-pending-signup'

describe('google-pending-signup-cookie (holding pen between Google verification and consent)', () => {
  const saved = { ...process.env }

  beforeEach(() => {
    process.env.IRONFORGE_SESSION_SECRET = SECRET
    delete process.env.IRONFORGE_CUSTOMER_SESSION_SECRET
  })
  afterEach(() => {
    process.env = { ...saved }
  })

  const base = { sub: 'google-sub-1', email: 'dana.reyes@gmail.com', givenName: 'Dana', familyName: 'Reyes', next: '/enroll' }

  it('round-trips the verified Google identity', async () => {
    const now = 1_000_000
    const token = await signGooglePendingSignupState(base, now)
    const claims = await verifyGooglePendingSignupState(token, now + 1000)
    expect(claims).not.toBeNull()
    expect(claims!.sub).toBe('google-sub-1')
    expect(claims!.email).toBe('dana.reyes@gmail.com')
    expect(claims!.givenName).toBe('Dana')
    expect(claims!.familyName).toBe('Reyes')
    expect(claims!.next).toBe('/enroll')
    expect(claims!.exp).toBe(now + GOOGLE_PENDING_SIGNUP_TTL_MS)
  })

  it('round-trips null given/family name', async () => {
    const token = await signGooglePendingSignupState({ ...base, givenName: null, familyName: null })
    const claims = await verifyGooglePendingSignupState(token)
    expect(claims!.givenName).toBeNull()
    expect(claims!.familyName).toBeNull()
  })

  it('rejects a tampered payload (forged email, original signature)', async () => {
    const token = await signGooglePendingSignupState(base)
    const [, sig] = token.split('.')
    const forgedPayload = Buffer.from(
      JSON.stringify({ ...base, email: 'attacker@evil.example', exp: Date.now() + 10_000 }),
    ).toString('base64url')
    expect(await verifyGooglePendingSignupState(`${forgedPayload}.${sig}`)).toBeNull()
  })

  it('rejects an expired cookie', async () => {
    const now = 1_000_000
    const token = await signGooglePendingSignupState(base, now)
    expect(await verifyGooglePendingSignupState(token, now + GOOGLE_PENDING_SIGNUP_TTL_MS + 1)).toBeNull()
  })

  it('returns null for missing/garbage tokens', async () => {
    expect(await verifyGooglePendingSignupState(undefined)).toBeNull()
    expect(await verifyGooglePendingSignupState('')).toBeNull()
    expect(await verifyGooglePendingSignupState('not-a-token')).toBeNull()
  })

  it('fails closed when no secret is configured', async () => {
    const token = await signGooglePendingSignupState(base)
    delete process.env.IRONFORGE_SESSION_SECRET
    expect(await verifyGooglePendingSignupState(token)).toBeNull()
  })

  it('does not verify under a different secret (e.g. a stale cookie after rotation)', async () => {
    const token = await signGooglePendingSignupState(base)
    process.env.IRONFORGE_SESSION_SECRET = 'a-completely-different-secret-value'
    expect(await verifyGooglePendingSignupState(token)).toBeNull()
  })

  it('rejects a payload missing the sub (the stable Google identity cannot be skipped)', async () => {
    const payload = Buffer.from(
      JSON.stringify({ email: base.email, givenName: base.givenName, familyName: base.familyName, next: base.next, exp: Date.now() + 10_000 }),
    ).toString('base64url')
    const { hmacB64url } = await import('@/lib/auth/onboarding')
    const sig = await hmacB64url(SECRET, payload)
    expect(await verifyGooglePendingSignupState(`${payload}.${sig}`)).toBeNull()
  })
})
