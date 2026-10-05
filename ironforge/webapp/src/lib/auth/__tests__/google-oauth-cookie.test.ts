import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  signGoogleOAuthState,
  verifyGoogleOAuthState,
  GOOGLE_OAUTH_TTL_MS,
} from '@/lib/auth/google-oauth-cookie'

const SECRET = 'test-secret-value-for-google-oauth-state'

describe('google-oauth-cookie (state + PKCE verifier cookie)', () => {
  const saved = { ...process.env }

  beforeEach(() => {
    process.env.IRONFORGE_SESSION_SECRET = SECRET
    delete process.env.IRONFORGE_CUSTOMER_SESSION_SECRET
  })
  afterEach(() => {
    process.env = { ...saved }
  })

  it('round-trips state, verifier and next', async () => {
    const now = 1_000_000
    const token = await signGoogleOAuthState({ state: 'abc', verifier: 'v-123', next: '/enroll' }, now)
    const claims = await verifyGoogleOAuthState(token, now + 1000)
    expect(claims).not.toBeNull()
    expect(claims!.state).toBe('abc')
    expect(claims!.verifier).toBe('v-123')
    expect(claims!.next).toBe('/enroll')
    expect(claims!.exp).toBe(now + GOOGLE_OAUTH_TTL_MS)
  })

  it('rejects a tampered payload (forged verifier, original signature)', async () => {
    const token = await signGoogleOAuthState({ state: 'abc', verifier: 'v-123', next: '/enroll' })
    const [, sig] = token.split('.')
    const forgedPayload = Buffer.from(
      JSON.stringify({ state: 'abc', verifier: 'attacker-verifier', next: '/enroll', exp: Date.now() + 10_000 }),
    ).toString('base64url')
    expect(await verifyGoogleOAuthState(`${forgedPayload}.${sig}`)).toBeNull()
  })

  it('rejects an expired cookie', async () => {
    const now = 1_000_000
    const token = await signGoogleOAuthState({ state: 'abc', verifier: 'v-123', next: '/enroll' }, now)
    expect(await verifyGoogleOAuthState(token, now + GOOGLE_OAUTH_TTL_MS + 1)).toBeNull()
  })

  it('returns null for missing/garbage tokens', async () => {
    expect(await verifyGoogleOAuthState(undefined)).toBeNull()
    expect(await verifyGoogleOAuthState('')).toBeNull()
    expect(await verifyGoogleOAuthState('not-a-token')).toBeNull()
  })

  it('fails closed when no secret is configured', async () => {
    const token = await signGoogleOAuthState({ state: 'abc', verifier: 'v-123', next: '/enroll' })
    delete process.env.IRONFORGE_SESSION_SECRET
    expect(await verifyGoogleOAuthState(token)).toBeNull()
  })

  it('does not verify under a different secret (e.g. a stale cookie after rotation)', async () => {
    const token = await signGoogleOAuthState({ state: 'abc', verifier: 'v-123', next: '/enroll' })
    process.env.IRONFORGE_SESSION_SECRET = 'a-completely-different-secret-value'
    expect(await verifyGoogleOAuthState(token)).toBeNull()
  })

  it('rejects a payload missing the verifier (PKCE cannot be skipped)', async () => {
    const payload = Buffer.from(JSON.stringify({ state: 'abc', next: '/enroll', exp: Date.now() + 10_000 })).toString(
      'base64url',
    )
    // Sign it properly so only the SHAPE is being tested, not the signature.
    const { hmacB64url } = await import('@/lib/auth/onboarding')
    const sig = await hmacB64url(SECRET, payload)
    expect(await verifyGoogleOAuthState(`${payload}.${sig}`)).toBeNull()
  })

  it('carries the 3 consents through the cookie (the /signup round trip)', async () => {
    const consents = { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: true }
    const token = await signGoogleOAuthState({ state: 'abc', verifier: 'v-123', next: '/enroll', consents })
    const claims = await verifyGoogleOAuthState(token)
    expect(claims!.consents).toEqual(consents)
  })

  it('leaves consents undefined for the /login round trip (nothing to carry)', async () => {
    const token = await signGoogleOAuthState({ state: 'abc', verifier: 'v-123', next: '/enroll' })
    const claims = await verifyGoogleOAuthState(token)
    expect(claims!.consents).toBeUndefined()
  })

  it('rejects a tampered consents block (one flag flipped, original signature)', async () => {
    const consents = { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: true }
    const token = await signGoogleOAuthState({ state: 'abc', verifier: 'v-123', next: '/enroll', consents })
    const [, sig] = token.split('.')
    const forgedPayload = Buffer.from(
      JSON.stringify({
        state: 'abc',
        verifier: 'v-123',
        next: '/enroll',
        consents: { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: false },
        exp: Date.now() + 10_000,
      }),
    ).toString('base64url')
    expect(await verifyGoogleOAuthState(`${forgedPayload}.${sig}`)).toBeNull()
  })

  it('rejects a malformed consents shape (not all 3 booleans present)', async () => {
    const payload = Buffer.from(
      JSON.stringify({
        state: 'abc',
        verifier: 'v-123',
        next: '/enroll',
        consents: { ageConfirmed: true, noAdviceAcknowledged: true },
        exp: Date.now() + 10_000,
      }),
    ).toString('base64url')
    const { hmacB64url } = await import('@/lib/auth/onboarding')
    const sig = await hmacB64url(SECRET, payload)
    expect(await verifyGoogleOAuthState(`${payload}.${sig}`)).toBeNull()
  })
})
