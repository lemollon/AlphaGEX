import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { decodeCursor, encodeCursor, filterKey, type CursorPayload } from '../cursor'

const ORIGINAL = process.env.IRONFORGE_SESSION_SECRET

beforeEach(() => {
  process.env.IRONFORGE_SESSION_SECRET = 'test-secret-for-bot-ledger-cursors'
})

afterEach(() => {
  if (ORIGINAL === undefined) delete process.env.IRONFORGE_SESSION_SECRET
  else process.env.IRONFORGE_SESSION_SECRET = ORIGINAL
})

const payload: CursorPayload = { v: 1, s: 'bl1_1784067600_a8f3c1d2', f: 'all:20', o: 20 }

describe('cursor signing', () => {
  it('round-trips a payload', () => {
    expect(decodeCursor(encodeCursor(payload))).toEqual(payload)
  })

  it('rejects a tampered payload', () => {
    const token = encodeCursor(payload)
    const [body, mac] = token.split('.')
    const flipped = `${body.slice(0, -1)}${body.slice(-1) === 'A' ? 'B' : 'A'}.${mac}`
    expect(decodeCursor(flipped)).toBeNull()
  })

  it('rejects a cursor signed with a different key', () => {
    const token = encodeCursor(payload)
    process.env.IRONFORGE_SESSION_SECRET = 'a-completely-different-secret'
    expect(decodeCursor(token)).toBeNull()
  })

  it('rejects structurally broken tokens', () => {
    for (const bad of ['', 'no-dot', '.', 'abc.', '.abc', null, 42, 'x'.repeat(600)]) {
      expect(decodeCursor(bad)).toBeNull()
    }
  })

  it('rejects a payload with a negative or non-integer offset', () => {
    expect(decodeCursor(encodeCursor({ ...payload, o: -1 }))).toBeNull()
    expect(decodeCursor(encodeCursor({ ...payload, o: 1.5 }))).toBeNull()
  })

  it('carries a filter key so a spark cursor cannot be replayed against all bots', () => {
    const decoded = decodeCursor(encodeCursor({ ...payload, f: filterKey('spark', 20) }))
    expect(decoded?.f).toBe('spark:20')
    expect(decoded?.f).not.toBe(filterKey('all', 20))
  })

  it('produces an opaque token that does not reveal the offset in plain text', () => {
    expect(encodeCursor(payload)).not.toContain('20')
  })
})
