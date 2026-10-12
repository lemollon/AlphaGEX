import { describe, it, expect } from 'vitest'
import crypto from 'crypto'
import { verifyStripeSignature, STRIPE_SIGNATURE_TOLERANCE_SECONDS } from '../stripe'

/**
 * Bug fix (brokerage/billing webhook audit): verifyStripeSignature must (a) reject a replayed
 * signed payload once its `t` timestamp is outside Stripe's documented ~5 minute tolerance, and
 * (b) accept ANY `v1=` signature present in the header — not just the last one — since Stripe
 * sends both the old and new secret's signatures during a signing-secret rotation.
 */

const SECRET = 'whsec_test_secret'

function sign(secret: string, t: number, rawBody: string): string {
  return crypto.createHmac('sha256', secret).update(`${t}.${rawBody}`, 'utf8').digest('hex')
}

describe('verifyStripeSignature', () => {
  it('accepts a freshly-signed payload', () => {
    const now = new Date('2026-10-12T12:00:00Z')
    const t = Math.floor(now.getTime() / 1000)
    const body = '{"id":"evt_1"}'
    const header = `t=${t},v1=${sign(SECRET, t, body)}`
    expect(verifyStripeSignature(body, header, SECRET, { now })).toBe(true)
  })

  it('rejects a replayed payload once the timestamp is past the tolerance window', () => {
    const now = new Date('2026-10-12T12:00:00Z')
    const staleT = Math.floor(now.getTime() / 1000) - (STRIPE_SIGNATURE_TOLERANCE_SECONDS + 1)
    const body = '{"id":"evt_1"}'
    const header = `t=${staleT},v1=${sign(SECRET, staleT, body)}`
    expect(verifyStripeSignature(body, header, SECRET, { now })).toBe(false)
  })

  it('accepts a payload right at the edge of the tolerance window', () => {
    const now = new Date('2026-10-12T12:00:00Z')
    const edgeT = Math.floor(now.getTime() / 1000) - STRIPE_SIGNATURE_TOLERANCE_SECONDS
    const body = '{"id":"evt_1"}'
    const header = `t=${edgeT},v1=${sign(SECRET, edgeT, body)}`
    expect(verifyStripeSignature(body, header, SECRET, { now })).toBe(true)
  })

  it('accepts the NEW secret signature when the header carries both during a key rotation, old first', () => {
    const now = new Date('2026-10-12T12:00:00Z')
    const t = Math.floor(now.getTime() / 1000)
    const body = '{"id":"evt_1"}'
    const oldSig = sign('whsec_old_secret', t, body)
    const newSig = sign(SECRET, t, body)
    // Stripe's real rotation header lists the old signature first, new second.
    const header = `t=${t},v1=${oldSig},v1=${newSig}`
    expect(verifyStripeSignature(body, header, SECRET, { now })).toBe(true)
  })

  it('accepts the matching signature even when it is NOT the last v1= entry', () => {
    const now = new Date('2026-10-12T12:00:00Z')
    const t = Math.floor(now.getTime() / 1000)
    const body = '{"id":"evt_1"}'
    const matchingSig = sign(SECRET, t, body)
    const otherSig = sign('whsec_unrelated', t, body)
    // The matching ('our') signature is first, an unrelated one is last — Object.fromEntries
    // collapse would have kept only the last and rejected this as invalid.
    const header = `t=${t},v1=${matchingSig},v1=${otherSig}`
    expect(verifyStripeSignature(body, header, SECRET, { now })).toBe(true)
  })

  it('rejects when no v1 signature matches', () => {
    const now = new Date('2026-10-12T12:00:00Z')
    const t = Math.floor(now.getTime() / 1000)
    const body = '{"id":"evt_1"}'
    const header = `t=${t},v1=${sign('whsec_wrong', t, body)}`
    expect(verifyStripeSignature(body, header, SECRET, { now })).toBe(false)
  })

  it('rejects a missing signature header or secret', () => {
    expect(verifyStripeSignature('{}', null, SECRET)).toBe(false)
    expect(verifyStripeSignature('{}', 't=1,v1=abc', '')).toBe(false)
  })
})
