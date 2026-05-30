import { describe, it, expect } from 'vitest'
import {
  stanceLabel,
  regimeLabel,
  fmtPct,
  windowText,
  dteText,
  type AdvisorTiming,
} from './volatility'

describe('stanceLabel', () => {
  it('maps known stances', () => {
    expect(stanceLabel('buy_the_bounce')).toBe('Buy the bounce')
    expect(stanceLabel('lean_calls')).toBe('Lean calls')
    expect(stanceLabel('lean_puts')).toBe('Lean puts')
    expect(stanceLabel('neutral')).toBe('Neutral')
  })

  it('falls back to em-dash on unknown/missing', () => {
    expect(stanceLabel(undefined)).toBe('—')
    expect(stanceLabel(null)).toBe('—')
    expect(stanceLabel('something_else')).toBe('—')
    expect(stanceLabel('')).toBe('—')
  })
})

describe('regimeLabel', () => {
  it('maps known regime keys', () => {
    expect(regimeLabel('backwardation_stressed')).toBe('Backwardation (stressed)')
    expect(regimeLabel('exhaustion')).toBe('Exhaustion')
    expect(regimeLabel('floor_complacent')).toBe('Floor (complacent)')
    expect(regimeLabel('contango_flattening')).toBe('Contango (flattening)')
    expect(regimeLabel('contango_calm')).toBe('Contango (calm)')
  })

  it('falls back to Unknown on unknown/missing', () => {
    expect(regimeLabel('unknown')).toBe('Unknown')
    expect(regimeLabel(undefined)).toBe('Unknown')
    expect(regimeLabel(null)).toBe('Unknown')
    expect(regimeLabel('not_a_regime')).toBe('Unknown')
  })
})

describe('fmtPct', () => {
  it('formats positive with a leading +', () => {
    expect(fmtPct(0.9)).toBe('+0.9%')
    expect(fmtPct(12.34)).toBe('+12.3%')
  })

  it('formats negative with a leading -', () => {
    expect(fmtPct(-1.2)).toBe('-1.2%')
  })

  it('formats zero without a sign', () => {
    expect(fmtPct(0)).toBe('0.0%')
  })

  it('falls back to em-dash on null/undefined/NaN', () => {
    expect(fmtPct(null)).toBe('—')
    expect(fmtPct(undefined)).toBe('—')
    expect(fmtPct(NaN)).toBe('—')
  })
})

describe('windowText', () => {
  it('combines range and median', () => {
    const t: AdvisorTiming = { p25_days: 3, p75_days: 8, median_days: 5 }
    expect(windowText(t)).toBe('3–8 trading days (median 5)')
  })

  it('renders range only when median missing', () => {
    expect(windowText({ p25_days: 3, p75_days: 8 })).toBe('3–8 trading days')
  })

  it('renders median only when range missing', () => {
    expect(windowText({ median_days: 5 })).toBe('median 5 trading days')
  })

  it('returns empty string when nothing available', () => {
    expect(windowText({})).toBe('')
    expect(windowText(undefined)).toBe('')
    expect(windowText(null)).toBe('')
  })
})

describe('dteText', () => {
  it('formats suggested DTE', () => {
    expect(dteText({ suggested_dte: 13 })).toBe('~13 DTE')
    expect(dteText({ suggested_dte: 0 })).toBe('~0 DTE')
  })

  it('returns empty string when missing', () => {
    expect(dteText({})).toBe('')
    expect(dteText(undefined)).toBe('')
    expect(dteText(null)).toBe('')
    expect(dteText({ suggested_dte: NaN })).toBe('')
  })
})
