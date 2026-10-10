import { describe, it, expect } from 'vitest'
import { isHardBounce, parseResendEvent, svixSign, verifySvixSignature } from '../resend-webhook'

const SECRET = 'whsec_' + Buffer.from('a-test-signing-key-32-bytes-long!!').toString('base64')
const BODY = JSON.stringify({ type: 'email.bounced', data: { to: ['A@Example.com'], email_id: 'm1', bounce: { type: 'Permanent' } } })
const NOW = new Date('2026-09-08T15:00:00Z')
const TS = String(Math.floor(NOW.getTime() / 1000))

function headers(sig: string, id = 'msg_1', timestamp = TS) {
  return { id, timestamp, signature: sig }
}

describe('verifySvixSignature', () => {
  it('accepts a correctly signed body', () => {
    const sig = `v1,${svixSign(SECRET, 'msg_1', TS, BODY)}`
    expect(verifySvixSignature(headers(sig), BODY, { secret: SECRET, now: NOW })).toEqual({ ok: true })
  })

  it('accepts when the valid signature is one of several space-separated entries', () => {
    const good = svixSign(SECRET, 'msg_1', TS, BODY)
    const sig = `v1,${Buffer.from('nope').toString('base64')} v1,${good}`
    expect(verifySvixSignature(headers(sig), BODY, { secret: SECRET, now: NOW }).ok).toBe(true)
  })

  it('FAILS CLOSED when the secret is unset', () => {
    const sig = `v1,${svixSign(SECRET, 'msg_1', TS, BODY)}`
    expect(verifySvixSignature(headers(sig), BODY, { secret: '', now: NOW })).toEqual({ ok: false, reason: 'secret_unset' })
    expect(verifySvixSignature(headers(sig), BODY, { secret: null, now: NOW })).toEqual({ ok: false, reason: 'secret_unset' })
  })

  it('rejects a tampered body', () => {
    const sig = `v1,${svixSign(SECRET, 'msg_1', TS, BODY)}`
    expect(verifySvixSignature(headers(sig), BODY + ' ', { secret: SECRET, now: NOW })).toEqual({ ok: false, reason: 'bad_signature' })
  })

  it('rejects a signature made with a different secret', () => {
    const other = 'whsec_' + Buffer.from('another-key-entirely-here-32bytes').toString('base64')
    const sig = `v1,${svixSign(other, 'msg_1', TS, BODY)}`
    expect(verifySvixSignature(headers(sig), BODY, { secret: SECRET, now: NOW }).ok).toBe(false)
  })

  it('rejects missing headers', () => {
    expect(verifySvixSignature({ id: null, timestamp: TS, signature: 'v1,x' }, BODY, { secret: SECRET, now: NOW })).toEqual({
      ok: false,
      reason: 'missing_headers',
    })
  })

  it('rejects a stale timestamp (replay guard) and a non-numeric one', () => {
    const oldTs = String(Math.floor(NOW.getTime() / 1000) - 6 * 60)
    const sig = `v1,${svixSign(SECRET, 'msg_1', oldTs, BODY)}`
    expect(verifySvixSignature(headers(sig, 'msg_1', oldTs), BODY, { secret: SECRET, now: NOW })).toEqual({
      ok: false,
      reason: 'stale_timestamp',
    })
    expect(verifySvixSignature(headers('v1,x', 'msg_1', 'soon'), BODY, { secret: SECRET, now: NOW })).toEqual({
      ok: false,
      reason: 'bad_timestamp',
    })
  })

  it('ignores signature entries that are not v1', () => {
    const good = svixSign(SECRET, 'msg_1', TS, BODY)
    expect(verifySvixSignature(headers(`v0,${good}`), BODY, { secret: SECRET, now: NOW }).ok).toBe(false)
  })
})

describe('parseResendEvent', () => {
  it('normalises recipients to lowercase and reads the bounce type', () => {
    const e = parseResendEvent(JSON.parse(BODY))
    expect(e).toEqual({ type: 'email.bounced', emails: ['a@example.com'], messageId: 'm1', bounceType: 'Permanent', createdAt: null })
    expect(isHardBounce(e!)).toBe(true)
  })

  it('a Transient bounce is not a hard bounce', () => {
    const e = parseResendEvent({ type: 'email.bounced', data: { to: 'b@x.com', bounce: { type: 'Transient' } } })
    expect(isHardBounce(e!)).toBe(false)
  })

  it('a complaint has no bounce type', () => {
    const e = parseResendEvent({ type: 'email.complained', data: { to: ['c@x.com'], email_id: 'm2' } })
    expect(e?.bounceType).toBeNull()
    expect(e?.type).toBe('email.complained')
  })

  it('returns null for bodies with no addressable recipient', () => {
    expect(parseResendEvent(null)).toBeNull()
    expect(parseResendEvent({ type: 'email.sent' })).toBeNull()
    expect(parseResendEvent({ type: 'email.sent', data: { to: [] } })).toBeNull()
  })
})
