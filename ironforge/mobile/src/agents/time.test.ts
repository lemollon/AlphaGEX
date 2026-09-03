import { describe, it, expect } from 'vitest'
import { formatPausedAt } from '@/agents/time'

describe('formatPausedAt', () => {
  it('converts UTC to Central time and labels it CT (CDT, summer)', () => {
    expect(formatPausedAt('2026-09-03T20:30:00Z')).toBe('Sep 3, 3:30 PM CT')
  })

  it('converts UTC to Central time and labels it CT (CST, winter)', () => {
    expect(formatPausedAt('2026-01-15T14:05:00Z')).toBe('Jan 15, 8:05 AM CT')
  })

  it('returns null for null input', () => {
    expect(formatPausedAt(null)).toBeNull()
  })

  it('returns null for an unparseable string', () => {
    expect(formatPausedAt('not-a-date')).toBeNull()
  })
})
