import { describe, it, expect, afterEach } from 'vitest'
import { isFlameCustomerEligible, getFlameMinEquity, FLAME_MIN_EQUITY_DEFAULT } from '../tradier'

/**
 * FLAME's per-customer-account auto-eligibility (subscribed + equity >=
 * FLAME_MIN_EQUITY, default $2,000) — mirrors isSparkCustomerEligible's test
 * shape exactly (see spark-live-gate.test.ts). This file does NOT re-test
 * FLAME's global live-arm switch — isFlameLiveArmed()/canPlaceLiveOrders('flame')
 * are pre-existing and unchanged; see flame-live-gate.test.ts for those pins.
 */

describe('isFlameCustomerEligible', () => {
  afterEach(() => { delete process.env.FLAME_MIN_EQUITY })

  it('is eligible when subscribed and equity clears the default $2,000 threshold', () => {
    expect(isFlameCustomerEligible(2000, true)).toBe(true)
    expect(isFlameCustomerEligible(10000, true)).toBe(true)
  })

  it('is NOT eligible when subscribed but equity is below the threshold', () => {
    expect(isFlameCustomerEligible(1999.99, true)).toBe(false)
    expect(isFlameCustomerEligible(0, true)).toBe(false)
  })

  it('is NOT eligible when equity clears the threshold but not subscribed', () => {
    expect(isFlameCustomerEligible(50000, false)).toBe(false)
  })

  it('is NOT eligible when neither subscribed nor sufficient equity', () => {
    expect(isFlameCustomerEligible(100, false)).toBe(false)
  })

  it('fails CLOSED when equity is null, even if subscribed', () => {
    expect(isFlameCustomerEligible(null, true)).toBe(false)
  })

  it('fails CLOSED when equity is not a finite number', () => {
    expect(isFlameCustomerEligible(Number.NaN, true)).toBe(false)
    expect(isFlameCustomerEligible(Number.POSITIVE_INFINITY, true)).toBe(false)
  })

  it('respects an explicit minEquity override', () => {
    expect(isFlameCustomerEligible(3000, true, 3500)).toBe(false)
    expect(isFlameCustomerEligible(3500, true, 3500)).toBe(true)
  })

  it('getFlameMinEquity defaults to $2,000 and is env-overridable', () => {
    delete process.env.FLAME_MIN_EQUITY
    expect(getFlameMinEquity()).toBe(FLAME_MIN_EQUITY_DEFAULT)
    expect(getFlameMinEquity()).toBe(2000)

    process.env.FLAME_MIN_EQUITY = '4000'
    expect(getFlameMinEquity()).toBe(4000)
  })

  it('getFlameMinEquity falls back to the default on an unparsable or non-positive override', () => {
    process.env.FLAME_MIN_EQUITY = 'not-a-number'
    expect(getFlameMinEquity()).toBe(FLAME_MIN_EQUITY_DEFAULT)

    process.env.FLAME_MIN_EQUITY = '0'
    expect(getFlameMinEquity()).toBe(FLAME_MIN_EQUITY_DEFAULT)

    process.env.FLAME_MIN_EQUITY = '-100'
    expect(getFlameMinEquity()).toBe(FLAME_MIN_EQUITY_DEFAULT)
  })
})
