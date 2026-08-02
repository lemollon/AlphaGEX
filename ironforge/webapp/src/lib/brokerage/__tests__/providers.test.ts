import { describe, it, expect } from 'vitest'
import {
  isOptionsCapable,
  isAllowedProvider,
  OPTIONS_CAPABLE_SLUGS,
} from '@/lib/brokerage/providers'

describe('options-capable broker allowlist (APP-041)', () => {
  it('accepts the US options brokers we support', () => {
    for (const slug of ['TASTYTRADE', 'SCHWAB', 'FIDELITY', 'ROBINHOOD']) {
      expect(isOptionsCapable(slug)).toBe(true)
    }
  })

  it('is case-insensitive, because the slug arrives from a client', () => {
    expect(isOptionsCapable('tastytrade')).toBe(true)
    expect(isOptionsCapable('TastyTrade')).toBe(true)
  })

  // The point of the list. Connecting one of these SUCCEEDS at SnapTrade and then the
  // bot silently cannot trade options — a failure the customer only discovers later,
  // which is worse than a clean refusal at connect time.
  it('refuses crypto exchanges and international brokers', () => {
    for (const slug of ['COINBASE', 'BINANCE', 'KRAKEN', 'WEALTHSIMPLE', 'QUESTRADE', 'TRADING212']) {
      expect(isOptionsCapable(slug)).toBe(false)
    }
  })

  it('refuses junk and injection-shaped input', () => {
    expect(isOptionsCapable('')).toBe(false)
    expect(isOptionsCapable("'; DROP TABLE users; --")).toBe(false)
    expect(isOptionsCapable('TASTYTRADE; SCHWAB')).toBe(false)
  })

  it('has no empty entries that would let a blank slug through', () => {
    expect(OPTIONS_CAPABLE_SLUGS.has('')).toBe(false)
  })
})

describe('provider allowlist', () => {
  it('accepts only the two providers we implement', () => {
    expect(isAllowedProvider('snaptrade')).toBe(true)
    expect(isAllowedProvider('tradier')).toBe(true)
  })

  it('rejects anything else, including non-strings', () => {
    for (const v of ['SNAPTRADE', 'plaid', '', null, undefined, 42, {}]) {
      expect(isAllowedProvider(v)).toBe(false)
    }
  })
})
