import { describe, it, expect } from 'vitest'
import { formatMoney } from './money-format'

describe('formatMoney', () => {
  it('formats an ordinary positive value', () => {
    expect(formatMoney(36)).toEqual({ text: '+$36.00', tone: 'pos' })
  })

  it('formats an ordinary negative value', () => {
    expect(formatMoney(-12.5)).toEqual({ text: '-$12.50', tone: 'neg' })
  })

  it('formats exactly zero as a plain two-decimal amount', () => {
    expect(formatMoney(0)).toEqual({ text: '+$0.00', tone: 'pos' })
  })

  it('returns null (caller renders a dash) for null/undefined', () => {
    expect(formatMoney(null)).toBeNull()
    expect(formatMoney(undefined)).toBeNull()
  })

  it('returns null instead of propagating NaN into the text', () => {
    expect(formatMoney(NaN)).toBeNull()
    expect(formatMoney(0 / 0)).toBeNull()
  })

  it('returns null for Infinity', () => {
    expect(formatMoney(Infinity)).toBeNull()
    expect(formatMoney(-Infinity)).toBeNull()
  })

  it('gives a tiny negative value that rounds to zero at 2dp extra precision instead of disguising it as "-$0.00"', () => {
    expect(formatMoney(-0.004)).toEqual({ text: '-$0.0040', tone: 'neg' })
  })

  it('gives a tiny positive value the same extra-precision treatment', () => {
    expect(formatMoney(0.004)).toEqual({ text: '+$0.0040', tone: 'pos' })
  })

  it('does not add extra precision once the magnitude is large enough to round away from zero', () => {
    expect(formatMoney(-0.006)).toEqual({ text: '-$0.01', tone: 'neg' })
    expect(formatMoney(-0.5)).toEqual({ text: '-$0.50', tone: 'neg' })
  })
})
