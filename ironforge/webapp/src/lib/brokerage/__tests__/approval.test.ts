import { describe, it, expect } from 'vitest'
import { decideApproval, isPlaceable } from '@/lib/brokerage/approval'

const now = new Date('2026-06-14T18:00:00Z')
const future = new Date('2026-06-14T18:05:00Z')
const past = new Date('2026-06-14T17:55:00Z')

describe('decideApproval', () => {
  it('places a pending approval that is still within its window', () => {
    expect(decideApproval({ status: 'pending', now, expiresAt: future })).toBe('place')
  })
  it('expires a pending approval whose window has lapsed', () => {
    expect(decideApproval({ status: 'pending', now, expiresAt: past })).toBe('expired')
  })
  it('treats the exact expiry instant as expired (not placeable)', () => {
    expect(decideApproval({ status: 'pending', now, expiresAt: now })).toBe('expired')
  })
  it('is invalid for any already-decided state (idempotent guard)', () => {
    for (const status of ['approved', 'placed', 'failed', 'expired', 'declined'] as const) {
      expect(decideApproval({ status, now, expiresAt: future })).toBe('invalid')
    }
  })
})

describe('isPlaceable', () => {
  it('is true only for a pending, unexpired approval', () => {
    expect(isPlaceable('pending', now, future)).toBe(true)
    expect(isPlaceable('pending', now, past)).toBe(false)
    expect(isPlaceable('approved', now, future)).toBe(false)
  })
})
