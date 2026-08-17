import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  canPlaceLiveOrders,
  canReadProductionBalance,
  isFlameLiveArmed,
  isTwoLegSpread,
  buildLegs,
} from '@/lib/tradier'

/**
 * PROOF for the FLAME live order path (PR #2824).
 *
 * Three claims are load-bearing and each is asserted here rather than argued:
 *   1. FLAME cannot place a live order unless ALL arm conditions hold.
 *   2. SPARK can NEVER place a live order, whatever the env says.
 *   3. A put spread emits exactly two legs, a condor four, indices contiguous.
 */

const ENV = { ...process.env }
beforeEach(() => {
  delete process.env.IRONFORGE_FLAME_LIVE
  delete process.env.TRADIER_FLAME_API_KEY
  delete process.env.TRADIER_FLAME_ACCOUNT_ID
})
afterEach(() => { process.env = { ...ENV } })

const arm = () => {
  process.env.IRONFORGE_FLAME_LIVE = 'true'
  process.env.TRADIER_FLAME_API_KEY = 'k'
  process.env.TRADIER_FLAME_ACCOUNT_ID = '6YB71371'
}

describe('1 · FLAME arm gate — every condition is necessary', () => {
  it('disarmed by default', () => {
    expect(isFlameLiveArmed()).toBe(false)
    expect(canPlaceLiveOrders('flame')).toBe(false)
  })

  it('armed only when the switch AND both creds are present', () => {
    arm()
    expect(canPlaceLiveOrders('flame')).toBe(true)
  })

  it.each([
    ['IRONFORGE_FLAME_LIVE', 'IRONFORGE_FLAME_LIVE'],
    ['the API key', 'TRADIER_FLAME_API_KEY'],
    ['the account id', 'TRADIER_FLAME_ACCOUNT_ID'],
  ])('removing %s disarms it', (_label, key) => {
    arm()
    delete process.env[key]
    expect(canPlaceLiveOrders('flame')).toBe(false)
  })

  it("is not fooled by a non-'true' switch value", () => {
    arm()
    for (const v of ['TRUE', '1', 'yes', 'True', '']) {
      process.env.IRONFORGE_FLAME_LIVE = v
      expect(canPlaceLiveOrders('flame')).toBe(false)
    }
  })
})

describe('2 · SPARK can never place a live order', () => {
  it('is false with nothing set', () => {
    expect(canPlaceLiveOrders('spark')).toBe(false)
  })

  it('stays false even with FLAME fully armed', () => {
    arm()
    expect(canPlaceLiveOrders('flame')).toBe(true)
    expect(canPlaceLiveOrders('spark')).toBe(false)
  })

  it('can still READ its live account — the block is placement only', () => {
    expect(canReadProductionBalance('spark')).toBe(true)
  })
})

describe('3 · order legs match the structure', () => {
  const sides = { shortSide: 'sell_to_open', longSide: 'buy_to_open' }

  it('a put spread (no call strikes) is two legs', () => {
    expect(isTwoLegSpread(0, 0)).toBe(true)
    const legs = buildLegs('PS', 'PL', '', '', 1, sides, true)
    expect(Object.keys(legs).filter(k => k.startsWith('option_symbol'))).toHaveLength(2)
    expect(legs['option_symbol[0]']).toBe('PS')
    expect(legs['side[0]']).toBe('sell_to_open')
    expect(legs['option_symbol[1]']).toBe('PL')
    expect(legs['side[1]']).toBe('buy_to_open')
    expect(legs['option_symbol[2]']).toBeUndefined()
  })

  it('a condor (call strikes present) is four legs', () => {
    expect(isTwoLegSpread(798, 808)).toBe(false)
    const legs = buildLegs('PS', 'PL', 'CS', 'CL', 2, sides, false)
    expect(Object.keys(legs).filter(k => k.startsWith('option_symbol'))).toHaveLength(4)
    expect(legs['option_symbol[2]']).toBe('CS')
    expect(legs['option_symbol[3]']).toBe('CL')
  })

  it('leg indices are contiguous from 0 — Tradier drops the tail otherwise', () => {
    for (const [twoLeg, n] of [[true, 2], [false, 4]] as const) {
      const legs = buildLegs('PS', 'PL', 'CS', 'CL', 1, sides, twoLeg)
      for (let i = 0; i < n; i++) {
        expect(legs[`option_symbol[${i}]`]).toBeDefined()
        expect(legs[`side[${i}]`]).toBeDefined()
        expect(legs[`quantity[${i}]`]).toBeDefined()
      }
    }
  })

  it('quantity is applied to every leg', () => {
    const legs = buildLegs('PS', 'PL', 'CS', 'CL', 7, sides, false)
    expect(Object.entries(legs).filter(([k]) => k.startsWith('quantity'))
      .every(([, v]) => v === '7')).toBe(true)
  })

  it('a half-specified call side is treated as two legs, not a broken four', () => {
    expect(isTwoLegSpread(798, 0)).toBe(true)
    expect(isTwoLegSpread(0, 808)).toBe(true)
  })
})
