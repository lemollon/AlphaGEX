import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  decideXspSwap,
  applyXspFillFallback,
  isXspSwapMode,
  isXspTicker,
  isXspOccSymbol,
  xspSettlementValueFromSpxClose,
  xspSpreadSettlementValue,
  xspSettlementPnl,
  XSP_SWAP_MAX_CONTRACTS,
  XSP_SWAP_MIN_CREDIT_EDGE,
  XSP_TICKER,
} from '../xsp-swap'

describe('isXspSwapMode — kill switch', () => {
  const ORIGINAL = process.env.XSP_SWAP
  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.XSP_SWAP
    else process.env.XSP_SWAP = ORIGINAL
  })

  it('unset reads as off', () => {
    delete process.env.XSP_SWAP
    expect(isXspSwapMode()).toBe(false)
  })
  it("'off' reads as off", () => {
    process.env.XSP_SWAP = 'off'
    expect(isXspSwapMode()).toBe(false)
  })
  it('any garbage value reads as off (fails closed)', () => {
    process.env.XSP_SWAP = 'true'
    expect(isXspSwapMode()).toBe(false)
    process.env.XSP_SWAP = '1'
    expect(isXspSwapMode()).toBe(false)
  })
  it("exactly 'on' (case-insensitive) reads as on", () => {
    process.env.XSP_SWAP = 'on'
    expect(isXspSwapMode()).toBe(true)
    process.env.XSP_SWAP = 'ON'
    expect(isXspSwapMode()).toBe(true)
    process.env.XSP_SWAP = ' on '
    expect(isXspSwapMode()).toBe(true)
  })
})

describe('decideXspSwap — price gate boundary', () => {
  it('applies exactly at the $0.05/share boundary (xsp credit == spy credit - 0.05)', () => {
    const d = decideXspSwap({ nHost: 3, spyCreditPerContract: 0.50, xspCreditPerContract: 0.45, xspShortBidSize: 10 })
    expect(d.usedXsp).toBe(true)
    expect(d.reason).toBe('xsp_swap_applied')
  })
  it('fails one cent past the boundary (xsp credit == spy credit - 0.06)', () => {
    const d = decideXspSwap({ nHost: 3, spyCreditPerContract: 0.50, xspCreditPerContract: 0.44, xspShortBidSize: 10 })
    expect(d.usedXsp).toBe(false)
    expect(d.reason).toBe('xsp_credit_below_gate')
    expect(d.nSpy).toBe(3)
    expect(d.nXsp).toBe(0)
  })
  it('applies when XSP credit is BETTER than SPY (no upper bound on the edge)', () => {
    const d = decideXspSwap({ nHost: 2, spyCreditPerContract: 0.50, xspCreditPerContract: 5.00, xspShortBidSize: 10 })
    expect(d.usedXsp).toBe(true)
  })
})

describe('decideXspSwap — touch-size (depth) gate', () => {
  it('applies when the touch depth exactly covers the candidate size', () => {
    const d = decideXspSwap({ nHost: 2, spyCreditPerContract: 0.50, xspCreditPerContract: 0.50, xspShortBidSize: 2 })
    expect(d.usedXsp).toBe(true)
    expect(d.nXsp).toBe(2)
  })
  it('fails when the touch depth is one short of the candidate size', () => {
    const d = decideXspSwap({ nHost: 2, spyCreditPerContract: 0.50, xspCreditPerContract: 0.50, xspShortBidSize: 1 })
    expect(d.usedXsp).toBe(false)
    expect(d.reason).toBe('xsp_touch_too_thin')
  })
  it('an UNKNOWN touch size (null) is treated as not covering — conservative, not "ladder some"', () => {
    const d = decideXspSwap({ nHost: 1, spyCreditPerContract: 0.50, xspCreditPerContract: 0.50, xspShortBidSize: null })
    expect(d.usedXsp).toBe(false)
    expect(d.reason).toBe('xsp_touch_too_thin')
  })
})

describe('decideXspSwap — quote availability and host size', () => {
  it('nHost <= 0 short-circuits with no_host_contracts', () => {
    const d = decideXspSwap({ nHost: 0, spyCreditPerContract: 0.50, xspCreditPerContract: 0.60, xspShortBidSize: 10 })
    expect(d.reason).toBe('no_host_contracts')
    expect(d.nXsp).toBe(0)
    expect(d.nSpy).toBe(0)
  })
  it('a null XSP quote routes 100% to SPY (never invents a price)', () => {
    const d = decideXspSwap({ nHost: 4, spyCreditPerContract: 0.50, xspCreditPerContract: null, xspShortBidSize: 10 })
    expect(d.reason).toBe('xsp_quote_unavailable')
    expect(d.nSpy).toBe(4)
  })
  it('opts.swapEnabled === false forces all-SPY regardless of a favorable quote', () => {
    const d = decideXspSwap(
      { nHost: 3, spyCreditPerContract: 0.50, xspCreditPerContract: 5.0, xspShortBidSize: 10 },
      { swapEnabled: false },
    )
    expect(d.usedXsp).toBe(false)
    expect(d.reason).toBe('xsp_swap_disabled')
  })
})

describe('decideXspSwap — the R4 cap (min(n,2))', () => {
  it('caps at 2 even when the host has 5 contracts', () => {
    const d = decideXspSwap({ nHost: 5, spyCreditPerContract: 0.50, xspCreditPerContract: 0.60, xspShortBidSize: 10 })
    expect(d.nXsp).toBe(2)
    expect(d.nSpy).toBe(3)
  })
  it('takes exactly 1 when the host only has 1', () => {
    const d = decideXspSwap({ nHost: 1, spyCreditPerContract: 0.50, xspCreditPerContract: 0.60, xspShortBidSize: 10 })
    expect(d.nXsp).toBe(1)
    expect(d.nSpy).toBe(0)
  })
  it('every decision satisfies nXsp + nSpy === nHost', () => {
    for (const nHost of [0, 1, 2, 3, 4, 10]) {
      for (const xspCredit of [null, 0.10, 0.50, 0.60, 5.0]) {
        for (const size of [null, 0, 1, 2, 10]) {
          const d = decideXspSwap({ nHost, spyCreditPerContract: 0.50, xspCreditPerContract: xspCredit, xspShortBidSize: size })
          expect(d.nXsp + d.nSpy).toBe(Math.max(0, nHost))
          expect(d.nXsp === 0 || d.nXsp === Math.min(nHost, XSP_SWAP_MAX_CONTRACTS)).toBe(true)
        }
      }
    }
  })
})

describe('applyXspFillFallback — "never skip the trade because XSP failed"', () => {
  it('routes the full original nHost to SPY when the XSP order does not fill', () => {
    const d = decideXspSwap({ nHost: 5, spyCreditPerContract: 0.50, xspCreditPerContract: 0.60, xspShortBidSize: 10 })
    expect(d.usedXsp).toBe(true)
    const fb = applyXspFillFallback(d, false)
    expect(fb.usedXsp).toBe(false)
    expect(fb.nXsp).toBe(0)
    expect(fb.nSpy).toBe(5)
  })
  it('is a no-op when the XSP order DID fill', () => {
    const d = decideXspSwap({ nHost: 5, spyCreditPerContract: 0.50, xspCreditPerContract: 0.60, xspShortBidSize: 10 })
    const fb = applyXspFillFallback(d, true)
    expect(fb).toEqual(d)
  })
  it('is a no-op when the decision never used XSP in the first place', () => {
    const d = decideXspSwap({ nHost: 5, spyCreditPerContract: 0.50, xspCreditPerContract: null, xspShortBidSize: 10 })
    const fb = applyXspFillFallback(d, false)
    expect(fb).toEqual(d)
  })
})

describe('isXspTicker / isXspOccSymbol', () => {
  it('matches XSP case-insensitively, rejects everything else', () => {
    expect(isXspTicker('XSP')).toBe(true)
    expect(isXspTicker('xsp')).toBe(true)
    expect(isXspTicker(' XSP ')).toBe(true)
    expect(isXspTicker('SPY')).toBe(false)
    expect(isXspTicker(null)).toBe(false)
    expect(isXspTicker(undefined)).toBe(false)
  })
  it('recognizes both OCC symbol conventions used in this codebase', () => {
    expect(isXspOccSymbol('XSP260929P00773000')).toBe(true) // tradier.ts (unpadded root)
    expect(isXspOccSymbol('XSP   260929P00773000')).toBe(true) // contracts.ts (padded to 6)
    expect(isXspOccSymbol('SPY260929P00773000')).toBe(false)
  })
})

describe('XSP settlement math', () => {
  it('settles from the official SPX close ÷ 10, never SPY\'s own close', () => {
    expect(xspSettlementValueFromSpxClose(7730)).toBeCloseTo(773, 4)
    expect(xspSettlementValueFromSpxClose(0)).toBeNull()
    expect(xspSettlementValueFromSpxClose(-5)).toBeNull()
    expect(xspSettlementValueFromSpxClose(NaN)).toBeNull()
  })
  it('spread settlement value is clamped to the wing width, never guesses on a bad row', () => {
    // Short 773 / long 771 (width $2). Settle at 770 -> full width ($2) intrinsic.
    expect(xspSpreadSettlementValue(773, 771, 770)).toBeCloseTo(2, 4)
    // Settle at 780 (above short) -> worthless, $0.
    expect(xspSpreadSettlementValue(773, 771, 780)).toBeCloseTo(0, 4)
    // Settle at 772 (between strikes) -> intrinsic $1.
    expect(xspSpreadSettlementValue(773, 771, 772)).toBeCloseTo(1, 4)
    // Malformed width (short <= long) -> refuse, never guess.
    expect(xspSpreadSettlementValue(771, 773, 770)).toBeNull()
    expect(xspSpreadSettlementValue(773, 771, 0)).toBeNull()
  })
  it('settlement PnL is credit minus value, per contract, in dollars', () => {
    // credit $0.50, settled worthless ($0 value), 2 contracts -> full credit kept = $100
    expect(xspSettlementPnl(0.50, 0, 2)).toBeCloseTo(100, 2)
    // credit $0.50, settled at full width ($2 value), 1 contract -> -$150 loss
    expect(xspSettlementPnl(0.50, 2, 1)).toBeCloseTo(-150, 2)
  })
})

describe('constants match the frozen R4 spec', () => {
  it('caps at 2 contracts and gates at $0.05/share', () => {
    expect(XSP_SWAP_MAX_CONTRACTS).toBe(2)
    expect(XSP_SWAP_MIN_CREDIT_EDGE).toBe(0.05)
    expect(XSP_TICKER).toBe('XSP')
  })
})
