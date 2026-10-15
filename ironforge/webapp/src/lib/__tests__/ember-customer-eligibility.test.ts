import { describe, it, expect, afterEach } from 'vitest'
import { isEmberCustomerEligible, getEmberMinEquity, EMBER_MIN_EQUITY_DEFAULT } from '../agents/ember'

/**
 * EMBER's per-customer-account auto-eligibility function (subscribed + equity
 * >= EMBER_MIN_EQUITY, default $500) — mirrors isSparkCustomerEligible's /
 * isFlameCustomerEligible's test shape exactly. STANDALONE: EMBER has no
 * customer-executor mirror path in this repo (CUSTOMER_AGENTS in executor.ts
 * is spark/flame only) and is currently paused by operator decision, so this
 * function is not wired into any live path — these tests only pin the pure
 * eligibility math, not any arm/pause switch.
 */

describe('isEmberCustomerEligible', () => {
  afterEach(() => { delete process.env.EMBER_MIN_EQUITY })

  it('is eligible when subscribed and equity clears the default $500 threshold', () => {
    expect(isEmberCustomerEligible(500, true)).toBe(true)
    expect(isEmberCustomerEligible(2000, true)).toBe(true)
  })

  it('is NOT eligible when subscribed but equity is below the threshold', () => {
    expect(isEmberCustomerEligible(499.99, true)).toBe(false)
    expect(isEmberCustomerEligible(0, true)).toBe(false)
  })

  it('is NOT eligible when equity clears the threshold but not subscribed', () => {
    expect(isEmberCustomerEligible(50000, false)).toBe(false)
  })

  it('is NOT eligible when neither subscribed nor sufficient equity', () => {
    expect(isEmberCustomerEligible(100, false)).toBe(false)
  })

  it('fails CLOSED when equity is null, even if subscribed', () => {
    expect(isEmberCustomerEligible(null, true)).toBe(false)
  })

  it('fails CLOSED when equity is not a finite number', () => {
    expect(isEmberCustomerEligible(Number.NaN, true)).toBe(false)
    expect(isEmberCustomerEligible(Number.POSITIVE_INFINITY, true)).toBe(false)
  })

  it('respects an explicit minEquity override', () => {
    expect(isEmberCustomerEligible(600, true, 750)).toBe(false)
    expect(isEmberCustomerEligible(750, true, 750)).toBe(true)
  })

  it('getEmberMinEquity defaults to $500 and is env-overridable', () => {
    delete process.env.EMBER_MIN_EQUITY
    expect(getEmberMinEquity()).toBe(EMBER_MIN_EQUITY_DEFAULT)
    expect(getEmberMinEquity()).toBe(500)

    process.env.EMBER_MIN_EQUITY = '1000'
    expect(getEmberMinEquity()).toBe(1000)
  })

  it('getEmberMinEquity falls back to the default on an unparsable or non-positive override', () => {
    process.env.EMBER_MIN_EQUITY = 'not-a-number'
    expect(getEmberMinEquity()).toBe(EMBER_MIN_EQUITY_DEFAULT)

    process.env.EMBER_MIN_EQUITY = '0'
    expect(getEmberMinEquity()).toBe(EMBER_MIN_EQUITY_DEFAULT)

    process.env.EMBER_MIN_EQUITY = '-100'
    expect(getEmberMinEquity()).toBe(EMBER_MIN_EQUITY_DEFAULT)
  })
})
