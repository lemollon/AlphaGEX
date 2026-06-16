import { describe, it, expect } from 'vitest'
import {
  hedgeFlagged,
  stepStreaks,
  debouncedTransitions,
  VVIX_STRESS,
  ALERTING_SIGNAL_KEYS,
} from './volAlerts'

describe('hedgeFlagged (daily hedge trigger)', () => {
  it('does NOT flag a calm contango day (VIX < VIX3M, benign VVIX)', () => {
    const d = hedgeFlagged({ regimeLabel: 'contango_calm', activeSignals: [], vix: 16.2, vix3m: 18.0, vvix: 88 })
    expect(d.flagged).toBe(false)
    expect(d.reasons).toHaveLength(0)
  })

  it('flags ts_flattening (the Jun 05 / Jun 09 condition)', () => {
    const d = hedgeFlagged({ regimeLabel: 'contango_flattening', activeSignals: ['ts_flattening'], vix: 20, vix3m: 21 })
    expect(d.flagged).toBe(true)
    expect(d.reasons).toContain('ts_flattening')
  })

  it('flags backwardation via term structure (VIX > VIX3M)', () => {
    const d = hedgeFlagged({ regimeLabel: 'contango_calm', activeSignals: [], vix: 24, vix3m: 22 })
    expect(d.flagged).toBe(true)
    expect(d.reasons.some((r) => r.includes('VIX 24.0 > VIX3M 22.0'))).toBe(true)
  })

  it('flags a VVIX (vol-of-vol) spike at/above threshold', () => {
    const at = hedgeFlagged({ activeSignals: [], vix: 18, vix3m: 19, vvix: VVIX_STRESS })
    expect(at.flagged).toBe(true)
    const below = hedgeFlagged({ activeSignals: [], vix: 18, vix3m: 19, vvix: VVIX_STRESS - 1 })
    expect(below.flagged).toBe(false)
  })

  it('flags the stressed-backwardation regime on its own', () => {
    expect(hedgeFlagged({ regimeLabel: 'backwardation_stressed', activeSignals: [] }).flagged).toBe(true)
  })
})

describe('debounce (stepStreaks + debouncedTransitions)', () => {
  const keys = ALERTING_SIGNAL_KEYS

  it('does not OPEN on a single active read (1 < openAfter=2)', () => {
    const s1 = stepStreaks({}, ['ts_flattening'], keys)
    expect(debouncedTransitions(s1, []).toOpen).toEqual([])
  })

  it('OPENS after the active streak reaches the threshold', () => {
    let s = stepStreaks({}, ['ts_flattening'], keys)
    s = stepStreaks(s, ['ts_flattening'], keys) // 2 consecutive
    expect(debouncedTransitions(s, []).toOpen).toContain('ts_flattening')
  })

  it('does NOT resolve on a single inactive read (the flap fix)', () => {
    // open, then one inactive read
    let s = stepStreaks({}, ['ts_flattening'], keys)
    s = stepStreaks(s, ['ts_flattening'], keys)
    s = stepStreaks(s, [], keys) // inactive 1
    expect(debouncedTransitions(s, ['ts_flattening']).toResolve).toEqual([])
  })

  it('RESOLVES only after sustained inactivity (≥ resolveAfter=3)', () => {
    let s: Record<string, { active: number; inactive: number }> = {}
    for (let i = 0; i < 3; i++) s = stepStreaks(s, [], keys) // 3 inactive
    expect(debouncedTransitions(s, ['ts_flattening']).toResolve).toContain('ts_flattening')
  })
})
