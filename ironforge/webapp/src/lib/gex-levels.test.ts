import { describe, it, expect } from 'vitest'
import { computeGexLevels, regimeFromNetGex } from './gex-levels'
import type { GexChainOption } from './tradier'

describe('computeGexLevels', () => {
  const spot = 100

  it('picks the strike with the largest call $gamma as call_wall, put as put_wall', () => {
    const chain: GexChainOption[] = [
      { strike: 105, type: 'call', gamma: 0.01, oi: 1000 }, // biggest call
      { strike: 110, type: 'call', gamma: 0.005, oi: 500 },
      { strike: 95, type: 'put', gamma: 0.02, oi: 2000 }, // biggest put
      { strike: 90, type: 'put', gamma: 0.01, oi: 800 },
    ]
    const out = computeGexLevels(chain, spot)
    expect(out.call_wall).toBe(105)
    expect(out.put_wall).toBe(95)
    expect(out.spot).toBe(100)
    expect(out.call_gex).not.toBeNull()
    expect(out.put_gex).not.toBeNull()
    expect(out.net_gex).toBeCloseTo((out.call_gex ?? 0) - (out.put_gex ?? 0), 6)
  })

  it('accumulates multiple rows at the same strike before picking the max', () => {
    const chain: GexChainOption[] = [
      { strike: 105, type: 'call', gamma: 0.002, oi: 1000 },
      { strike: 105, type: 'call', gamma: 0.002, oi: 1000 }, // same strike, two expirations
      { strike: 110, type: 'call', gamma: 0.003, oi: 1000 }, // bigger alone, but 105's sum wins
      { strike: 100, type: 'put', gamma: 0.001, oi: 500 },
    ]
    const out = computeGexLevels(chain, spot)
    // 105: 2 * (0.002*1000*100*100^2*0.01) = 2 * 200000 = 400000
    // 110: 1 * (0.003*1000*100*100^2*0.01) = 300000
    expect(out.call_wall).toBe(105)
  })

  it('ignores non-positive or non-finite gamma/OI rows', () => {
    const chain: GexChainOption[] = [
      { strike: 105, type: 'call', gamma: 0, oi: 1000 },
      { strike: 110, type: 'call', gamma: NaN, oi: 1000 },
      { strike: 95, type: 'put', gamma: 0.01, oi: 0 },
    ]
    const out = computeGexLevels(chain, spot)
    expect(out.call_wall).toBeNull()
    expect(out.put_wall).toBeNull()
    expect(out.net_gex).toBeNull()
    expect(out.call_gex).toBeNull()
    expect(out.put_gex).toBeNull()
  })

  it('returns all-null levels on an empty chain', () => {
    const out = computeGexLevels([], spot)
    expect(out).toEqual({ spot, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null })
  })

  it('returns all-null levels when spot is missing or non-positive', () => {
    const chain: GexChainOption[] = [{ strike: 105, type: 'call', gamma: 0.01, oi: 1000 }]
    expect(computeGexLevels(chain, null)).toEqual({
      spot: null, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null,
    })
    expect(computeGexLevels(chain, 0)).toEqual({
      spot: 0, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null,
    })
  })

  it('handles a call-only or put-only chain without throwing', () => {
    const callOnly: GexChainOption[] = [{ strike: 105, type: 'call', gamma: 0.01, oi: 1000 }]
    const outCallOnly = computeGexLevels(callOnly, spot)
    expect(outCallOnly.call_wall).toBe(105)
    expect(outCallOnly.put_wall).toBeNull()
    expect(outCallOnly.put_gex).toBeNull()
    expect(outCallOnly.net_gex).not.toBeNull()

    const putOnly: GexChainOption[] = [{ strike: 95, type: 'put', gamma: 0.01, oi: 1000 }]
    const outPutOnly = computeGexLevels(putOnly, spot)
    expect(outPutOnly.put_wall).toBe(95)
    expect(outPutOnly.call_wall).toBeNull()
    expect(outPutOnly.call_gex).toBeNull()
  })
})

describe('regimeFromNetGex', () => {
  it('buckets net GEX into the expected labels', () => {
    expect(regimeFromNetGex(-4e9)).toBe('EXTREME_NEGATIVE')
    expect(regimeFromNetGex(-2.5e9)).toBe('HIGH_NEGATIVE')
    expect(regimeFromNetGex(-1.5e9)).toBe('MODERATE_NEGATIVE')
    expect(regimeFromNetGex(0)).toBe('NEUTRAL')
    expect(regimeFromNetGex(1.5e9)).toBe('MODERATE_POSITIVE')
    expect(regimeFromNetGex(2.5e9)).toBe('HIGH_POSITIVE')
    expect(regimeFromNetGex(4e9)).toBe('EXTREME_POSITIVE')
  })
})
