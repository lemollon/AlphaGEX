import { describe, it, expect } from 'vitest'
import { resolvePlacement } from '@/lib/brokerage/placement'

describe('resolvePlacement', () => {
  it('routes snaptrade and tradier to their own placers', () => {
    expect(resolvePlacement('snaptrade')).toBe('snaptrade')
    expect(resolvePlacement('tradier')).toBe('tradier')
  })
  it('refuses unknown/null providers rather than guessing a broker', () => {
    expect(resolvePlacement(null)).toBe('unsupported')
    expect(resolvePlacement(undefined)).toBe('unsupported')
    expect(resolvePlacement('robinhood')).toBe('unsupported')
  })
})
