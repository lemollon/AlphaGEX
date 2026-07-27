import { describe, expect, it } from 'vitest'

import {
  centsFromNumericString,
  divRoundHalfAway,
  formatScaled,
  LedgerMathError,
  meanExact,
  sumExact,
} from '../money'

describe('centsFromNumericString', () => {
  it('parses the shapes pg actually returns for NUMERIC', () => {
    expect(centsFromNumericString('42.37')).toBe(4237)
    expect(centsFromNumericString('-26')).toBe(-2600)
    expect(centsFromNumericString('0.00')).toBe(0)
    expect(centsFromNumericString('0')).toBe(0)
    expect(centsFromNumericString('1234567.89')).toBe(123456789)
    expect(centsFromNumericString('42.3')).toBe(4230)
    expect(centsFromNumericString('+7.50')).toBe(750)
  })

  it('accepts integers, which pg returns for INT columns', () => {
    expect(centsFromNumericString(5)).toBe(500)
    expect(centsFromNumericString(-3)).toBe(-300)
  })

  it('rounds a third decimal half away from zero', () => {
    expect(centsFromNumericString('1.005')).toBe(101)
    expect(centsFromNumericString('1.004')).toBe(100)
    expect(centsFromNumericString('-1.005')).toBe(-101)
  })

  it('refuses anything that is not a plain decimal', () => {
    for (const bad of ['abc', '', '1e5', '1,000', null, undefined, {}, NaN, Infinity]) {
      expect(() => centsFromNumericString(bad)).toThrow(LedgerMathError)
    }
  })
})

describe('divRoundHalfAway', () => {
  it('rounds .5 away from zero in both directions', () => {
    expect(divRoundHalfAway(5, 2)).toBe(3)
    expect(divRoundHalfAway(-5, 2)).toBe(-3)
    expect(divRoundHalfAway(5, -2)).toBe(-3)
    expect(divRoundHalfAway(-5, -2)).toBe(3)
  })

  it('rounds normally below and above the midpoint', () => {
    expect(divRoundHalfAway(1, 3)).toBe(0)
    expect(divRoundHalfAway(2, 3)).toBe(1)
    expect(divRoundHalfAway(-2, 3)).toBe(-1)
    expect(divRoundHalfAway(100, 10)).toBe(10)
  })

  it('rejects zero divisors and non-integers', () => {
    expect(() => divRoundHalfAway(1, 0)).toThrow(LedgerMathError)
    expect(() => divRoundHalfAway(1.5, 2)).toThrow(LedgerMathError)
  })
})

describe('formatScaled', () => {
  it('renders fixed-point without producing negative zero', () => {
    expect(formatScaled(4237, 2)).toBe('42.37')
    expect(formatScaled(-520, 2)).toBe('-5.20')
    expect(formatScaled(0, 2)).toBe('0.00')
    expect(formatScaled(-0, 2)).toBe('0.00')
    expect(formatScaled(5, 2)).toBe('0.05')
    expect(formatScaled(6000, 2)).toBe('60.00')
  })
})

describe('exact accumulation', () => {
  it('does not drift over many additions, unlike float cents', () => {
    const tenCents = Array.from({ length: 300 }, () => 10)
    expect(sumExact(tenCents)).toBe(3000)
    expect(meanExact(tenCents)).toBe(10)
  })

  it('returns null for the mean of an empty set rather than NaN', () => {
    expect(meanExact([])).toBeNull()
  })
})
