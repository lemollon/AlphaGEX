import { describe, it, expect } from 'vitest'
import { isStale, staleLabel, STALE_THRESHOLD_MS } from '@/live/staleness'

describe('isStale', () => {
  it('is never stale with no timestamp yet (still loading)', () => {
    expect(isStale(null, 1_000_000)).toBe(false)
  })

  it('is not stale right at the threshold', () => {
    expect(isStale(0, STALE_THRESHOLD_MS)).toBe(false)
  })

  it('is stale one millisecond past the threshold', () => {
    expect(isStale(0, STALE_THRESHOLD_MS + 1)).toBe(true)
  })

  it('is not stale for a fresh update', () => {
    expect(isStale(1_000_000, 1_000_500)).toBe(false)
  })
})

describe('staleLabel', () => {
  it('singular second', () => {
    expect(staleLabel(0, 1_000)).toBe('Updated 1 second ago')
  })

  it('plural seconds', () => {
    expect(staleLabel(0, 42_000)).toBe('Updated 42 seconds ago')
  })

  it('switches to minutes at 60 seconds', () => {
    expect(staleLabel(0, 60_000)).toBe('Updated 1 minute ago')
  })

  it('plural minutes', () => {
    expect(staleLabel(0, 5 * 60_000)).toBe('Updated 5 minutes ago')
  })

  it('never goes negative for a clock that moved backward', () => {
    expect(staleLabel(10_000, 0)).toBe('Updated 0 seconds ago')
  })
})
