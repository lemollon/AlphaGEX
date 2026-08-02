import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  signAccessToken,
  signStepUpToken,
  verifyAccessToken,
  verifyMobileToken,
  bearerFrom,
  isMobileTokenConfigured,
} from '@/lib/auth/mobile-token'
import { signOnboardingToken, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { MOBILE_SESSION_POLICY } from '@/lib/auth/mobile-policy'

const SECRET = 'test-secret-value-for-mobile-tokens'
const UID = '11111111-2222-3333-4444-555555555555'

describe('mobile-token', () => {
  const saved = { ...process.env }

  beforeEach(() => {
    process.env.IRONFORGE_SESSION_SECRET = SECRET
    delete process.env.IRONFORGE_MOBILE_TOKEN_SECRET
    delete process.env.IRONFORGE_CUSTOMER_SESSION_SECRET
  })
  afterEach(() => {
    process.env = { ...saved }
  })

  it('round-trips a valid access token', async () => {
    const t = await signAccessToken(UID, 0)
    const claims = await verifyAccessToken(t)
    expect(claims).not.toBeNull()
    expect(claims!.sub).toBe(UID)
    expect(claims!.typ).toBe('acc')
    expect(claims!.ep).toBe(0)
  })

  it('carries the token epoch so it can be invalidated server-side', async () => {
    const claims = await verifyAccessToken(await signAccessToken(UID, 7))
    expect(claims!.ep).toBe(7)
  })

  it('rejects a tampered payload', async () => {
    const t = await signAccessToken(UID, 0)
    const [payload, sig] = t.split('.')
    const evil = Buffer.from(JSON.stringify({ sub: 'attacker', typ: 'acc', ep: 0, iat: 1, exp: 9e9 }))
      .toString('base64url')
    expect(await verifyAccessToken(`${evil}.${sig}`)).toBeNull()
    expect(payload).not.toBe(evil)
  })

  it('rejects a token signed with a different secret', async () => {
    const t = await signAccessToken(UID, 0)
    process.env.IRONFORGE_SESSION_SECRET = 'a-completely-different-secret'
    expect(await verifyAccessToken(t)).toBeNull()
  })

  it('rejects an expired token', async () => {
    const now = Date.now()
    const t = await signAccessToken(UID, 0, now)
    const afterExpiry = now + (MOBILE_SESSION_POLICY.accessTtlSec + 1) * 1000
    expect(await verifyAccessToken(t, afterExpiry)).toBeNull()
  })

  it('fails closed when no secret is configured', async () => {
    const t = await signAccessToken(UID, 0)
    delete process.env.IRONFORGE_SESSION_SECRET
    expect(isMobileTokenConfigured()).toBe(false)
    expect(await verifyAccessToken(t)).toBeNull()
  })

  it('refuses a step-up token where an access token is required, and vice versa', async () => {
    const step = await signStepUpToken(UID, 0)
    const acc = await signAccessToken(UID, 0)
    // A step-up token must not authenticate ordinary requests...
    expect(await verifyAccessToken(step)).toBeNull()
    // ...and an ordinary access token must not satisfy a step-up requirement.
    expect(await verifyMobileToken(acc, { type: 'step' })).toBeNull()
    // Each is valid for its own type.
    expect(await verifyMobileToken(step, { type: 'step' })).not.toBeNull()
    expect(await verifyAccessToken(acc)).not.toBeNull()
  })

  it('rejects malformed input without throwing', async () => {
    for (const bad of ['', 'no-dot', '.', 'a.', 'x'.repeat(9000), null, undefined]) {
      expect(await verifyAccessToken(bad as string)).toBeNull()
    }
  })

  // ── Domain separation ──
  //
  // Both token families are HMAC-SHA256 over IRONFORGE_SESSION_SECRET, and
  // verifyOnboardingToken accepts any payload shaped {uid, exp}. Without the
  // "ifm.v1." prefix on the mobile signing input these two would be
  // interchangeable: an onboarding cookie would authenticate the whole customer
  // API, and an access token would grant the onboarding funnel. These two tests
  // are the guard. Do not delete them.

  it('does NOT accept an onboarding token as a mobile access token', async () => {
    const onboarding = await signOnboardingToken(UID)
    expect(await verifyOnboardingToken(onboarding)).not.toBeNull() // still valid for its own purpose
    expect(await verifyAccessToken(onboarding)).toBeNull()
  })

  it('does NOT accept a mobile access token as an onboarding token', async () => {
    const access = await signAccessToken(UID, 0)
    expect(await verifyAccessToken(access)).not.toBeNull()
    expect(await verifyOnboardingToken(access)).toBeNull()
  })
})

describe('bearerFrom', () => {
  it('extracts the token regardless of scheme casing', () => {
    expect(bearerFrom('Bearer abc123')).toBe('abc123')
    expect(bearerFrom('bearer abc123')).toBe('abc123')
    expect(bearerFrom('BEARER  abc123  ')).toBe('abc123')
  })

  it('ignores non-bearer schemes and junk', () => {
    expect(bearerFrom('Basic abc123')).toBeNull()
    expect(bearerFrom('abc123')).toBeNull()
    expect(bearerFrom('Bearer')).toBeNull()
    expect(bearerFrom('Bearer   ')).toBeNull()
    expect(bearerFrom(null)).toBeNull()
    expect(bearerFrom(undefined)).toBeNull()
  })
})
