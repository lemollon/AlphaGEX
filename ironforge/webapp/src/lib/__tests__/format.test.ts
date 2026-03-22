/**
 * Tests for format.ts — number/currency formatting utilities.
 *
 * All formatters return "--" for null/undefined/NaN.
 */

import { describe, it, expect } from 'vitest'
import { formatCurrency, formatPct, formatGreek, formatDollarPnl } from '../format'

/* ================================================================== */
/*  formatCurrency                                                     */
/* ================================================================== */

describe('formatCurrency', () => {
  it('null → "--"', () => {
    expect(formatCurrency(null)).toBe('--')
  })

  it('undefined → "--"', () => {
    expect(formatCurrency(undefined)).toBe('--')
  })

  it('NaN → "--"', () => {
    expect(formatCurrency(NaN)).toBe('--')
  })

  it('0 → "$0"', () => {
    expect(formatCurrency(0)).toBe('$0')
  })

  it('1357.4 → "$1,357"', () => {
    expect(formatCurrency(1357.4)).toBe('$1,357')
  })

  it('-769 → "-$769"', () => {
    expect(formatCurrency(-769)).toBe('-$769')
  })

  it('1_000_000 → "$1,000,000"', () => {
    expect(formatCurrency(1_000_000)).toBe('$1,000,000')
  })
})

/* ================================================================== */
/*  formatPct                                                          */
/* ================================================================== */

describe('formatPct', () => {
  it('null → "--"', () => {
    expect(formatPct(null)).toBe('--')
  })

  it('36.0 → "36.0%"', () => {
    expect(formatPct(36.0)).toBe('36.0%')
  })

  it('-5.2 → "-5.2%"', () => {
    expect(formatPct(-5.2)).toBe('-5.2%')
  })

  it('0 → "0.0%"', () => {
    expect(formatPct(0)).toBe('0.0%')
  })

  it('100 → "100.0%"', () => {
    expect(formatPct(100)).toBe('100.0%')
  })
})

/* ================================================================== */
/*  formatGreek                                                        */
/* ================================================================== */

describe('formatGreek', () => {
  it('null → "--"', () => {
    expect(formatGreek(null)).toBe('--')
  })

  it('positive value gets + sign', () => {
    expect(formatGreek(0.1234)).toBe('+0.1234')
  })

  it('negative value keeps - sign', () => {
    expect(formatGreek(-0.5678)).toBe('-0.5678')
  })

  it('zero has no sign', () => {
    expect(formatGreek(0)).toBe('0.0000')
  })

  it('custom decimals: formatGreek(0.1, 2) → "+0.10"', () => {
    expect(formatGreek(0.1, 2)).toBe('+0.10')
  })
})

/* ================================================================== */
/*  formatDollarPnl                                                    */
/* ================================================================== */

describe('formatDollarPnl', () => {
  it('null → "--"', () => {
    expect(formatDollarPnl(null)).toBe('--')
  })

  it('positive P&L gets + sign', () => {
    expect(formatDollarPnl(125.50)).toBe('+$125.50')
  })

  it('negative P&L gets - sign', () => {
    expect(formatDollarPnl(-42.00)).toBe('-$42.00')
  })

  it('zero → "$0.00"', () => {
    expect(formatDollarPnl(0)).toBe('$0.00')
  })

  it('large positive', () => {
    expect(formatDollarPnl(12345.67)).toBe('+$12,345.67')
  })

  it('large negative', () => {
    expect(formatDollarPnl(-9876.54)).toBe('-$9,876.54')
  })
})
