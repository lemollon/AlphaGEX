import { describe, expect, it } from 'vitest'

import {
  EM_DASH,
  integer,
  longDate,
  marketDate,
  profitFactor,
  relativeTime,
  sampleLine,
  sampleLineAccessible,
  signedDollars,
  signedPct,
  wholeDollars,
  winRate,
} from '../format'

const MINUS = '−' // U+2212

describe('winRate', () => {
  it('renders one decimal and never a plus sign', () => {
    expect(winRate('73.68')).toBe('73.7%')
    expect(winRate('60.00')).toBe('60.0%')
    expect(winRate('100.00')).toBe('100.0%')
    expect(winRate('0.00')).toBe('0.0%')
  })

  it('renders an em dash when the value is unavailable', () => {
    expect(winRate(null)).toBe(EM_DASH)
    expect(winRate(undefined)).toBe(EM_DASH)
    expect(winRate('')).toBe(EM_DASH)
    expect(winRate('abc')).toBe(EM_DASH)
  })
})

describe('signedPct', () => {
  it('applies an explicit sign to gains and losses', () => {
    expect(signedPct('4.80')).toBe('+4.8%')
    expect(signedPct('-5.10')).toBe(`${MINUS}5.1%`)
  })

  it('uses the typographic minus, not an ASCII hyphen', () => {
    expect(signedPct('-5.10')).toContain(MINUS)
    expect(signedPct('-5.10')).not.toContain('-')
  })

  it('renders values that round to zero without a sign', () => {
    expect(signedPct('0.00')).toBe('0.0%')
    expect(signedPct('-0.04')).toBe('0.0%')
    expect(signedPct('0.04')).toBe('0.0%')
    // The failure this guards against is a visible signed zero.
    expect(signedPct('-0.04')).not.toContain(MINUS)
    expect(signedPct('-0.04')).not.toBe('-0.0%')
  })

  it('renders an em dash when unavailable', () => {
    expect(signedPct(null)).toBe(EM_DASH)
  })
})

describe('profitFactor', () => {
  it('renders two decimals', () => {
    expect(profitFactor('1.46')).toBe('1.46')
    expect(profitFactor('1.8712')).toBe('1.87')
    expect(profitFactor('0.00')).toBe('0.00')
  })

  it('renders an em dash for null — never Infinity', () => {
    expect(profitFactor(null)).toBe(EM_DASH)
    expect(profitFactor('Infinity')).toBe(EM_DASH)
  })
})

describe('currency', () => {
  it('renders whole dollars', () => {
    expect(wholeDollars('500.00')).toBe('$500')
    expect(wholeDollars('1240.55')).toBe('$1,241')
  })

  it('signs the net result and uses the typographic minus', () => {
    expect(signedDollars('42.00')).toBe('+$42')
    expect(signedDollars('-26.00')).toBe(`${MINUS}$26`)
    expect(signedDollars('0.00')).toBe('$0')
  })
})

describe('dates', () => {
  it('renders the market date without a year in the current year', () => {
    expect(marketDate('2026-07-25', 2026)).toBe('JUL 25')
  })

  it('includes the year when it is not the current year', () => {
    expect(marketDate('2025-12-31', 2026)).toBe('DEC 31 2025')
  })

  it('does not shift the day through the local timezone', () => {
    // Parsed by hand, so a browser in UTC-8 still shows the server's date.
    expect(marketDate('2026-01-01', 2026)).toBe('JAN 1')
  })

  it('renders the inception disclosure in long form', () => {
    expect(longDate('2026-04-23')).toBe('23 Apr 2026')
  })
})

describe('relativeTime', () => {
  const base = Date.parse('2026-07-26T12:00:00Z')

  it('is coarse, matching the 5-minute snapshot cadence', () => {
    expect(relativeTime('2026-07-26T12:00:00Z', base)).toBe('just now')
    expect(relativeTime('2026-07-26T11:48:00Z', base)).toBe('12 minutes ago')
    expect(relativeTime('2026-07-26T11:59:00Z', base)).toBe('1 minute ago')
    expect(relativeTime('2026-07-26T09:00:00Z', base)).toBe('3 hours ago')
    expect(relativeTime('2026-07-24T12:00:00Z', base)).toBe('2 days ago')
  })

  it('takes now as a parameter so it is deterministic and SSR-safe', () => {
    expect(relativeTime('2026-07-26T11:48:00Z', base)).toBe(
      relativeTime('2026-07-26T11:48:00Z', base),
    )
  })
})

describe('sample line', () => {
  it('omits the scratch term when there are none', () => {
    expect(sampleLine(14, 5, 0, 19)).toBe('14 wins · 5 losses · 19 closed trades')
  })

  it('includes the scratch term when there are some', () => {
    expect(sampleLine(14, 4, 1, 19)).toContain('1 scratch')
  })

  it('has a spoken form without shorthand punctuation', () => {
    expect(sampleLineAccessible(14, 5, 0, 19)).toBe('14 wins, 5 losses, 19 closed paper trades')
  })
})

describe('integer', () => {
  it('groups thousands and dashes on null', () => {
    expect(integer(1234)).toBe('1,234')
    expect(integer(null)).toBe(EM_DASH)
  })
})
