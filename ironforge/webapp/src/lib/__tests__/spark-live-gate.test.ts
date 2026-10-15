import { describe, it, expect, afterEach } from 'vitest'
import {
  isSparkLiveArmed,
  canPlaceLiveOrders,
  isSparkCustomerEligible,
  getSparkMinEquity,
  SPARK_MIN_EQUITY_DEFAULT,
} from '../tradier'

/**
 * SPARK must not be able to place real-money orders unless deliberately armed.
 *
 * canPlaceLiveOrders('spark') was hard-coded `false` until this PR (2026-08-16
 * operator decision — see tradier.ts's doc comment on canPlaceLiveOrders). These
 * tests pin the fail-closed behavior: if either of the two in-process conditions
 * (env knob, creds) is missing, SPARK still cannot place a real order. The third
 * documented condition — an unpaused ironforge_production_pause row — is enforced
 * downstream by resolveProductionAccounts' generic pause check and is NOT part of
 * isSparkLiveArmed() itself, mirroring isFlameLiveArmed() exactly (see
 * flame-live-gate.test.ts for the equivalent FLAME pins).
 *
 * The gate reads process.env at call time, so setting env per-case is enough —
 * no module reset required.
 */

const ENV_KEYS = ['SPARK_LIVE_ARMED', 'TRADIER_SPARK_API_KEY', 'TRADIER_SPARK_ACCOUNT_ID'] as const
type EnvKey = (typeof ENV_KEYS)[number]

function setEnv(vars: Partial<Record<EnvKey, string>>) {
  for (const k of ENV_KEYS) delete process.env[k]
  Object.assign(process.env, vars)
}

const ARMED = {
  SPARK_LIVE_ARMED: 'true',
  TRADIER_SPARK_API_KEY: 'test-key',
  TRADIER_SPARK_ACCOUNT_ID: 'test-account',
} as const

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  delete process.env.SPARK_MIN_EQUITY
})

describe('SPARK live-arm gate', () => {
  it('is disarmed with no env set at all (the shipped default)', () => {
    setEnv({})
    expect(isSparkLiveArmed()).toBe(false)
    expect(canPlaceLiveOrders('spark')).toBe(false)
  })

  it('stays disarmed when creds exist but the knob is off', () => {
    setEnv({ TRADIER_SPARK_API_KEY: 'k', TRADIER_SPARK_ACCOUNT_ID: 'a' })
    expect(isSparkLiveArmed()).toBe(false)
    expect(canPlaceLiveOrders('spark')).toBe(false)
  })

  it('stays disarmed when the knob is on but creds are missing', () => {
    setEnv({ SPARK_LIVE_ARMED: 'true' })
    expect(isSparkLiveArmed()).toBe(false)
    expect(canPlaceLiveOrders('spark')).toBe(false)
  })

  it('stays disarmed when only one of the two creds is present', () => {
    setEnv({ SPARK_LIVE_ARMED: 'true', TRADIER_SPARK_API_KEY: 'k' })
    expect(isSparkLiveArmed()).toBe(false)

    setEnv({ SPARK_LIVE_ARMED: 'true', TRADIER_SPARK_ACCOUNT_ID: 'a' })
    expect(isSparkLiveArmed()).toBe(false)
  })

  it('rejects truthy-but-not-"true" knob values', () => {
    for (const v of ['1', 'yes', 'TRUE', 'on', '']) {
      setEnv({ ...ARMED, SPARK_LIVE_ARMED: v })
      expect(isSparkLiveArmed(), `knob value ${JSON.stringify(v)} must not arm`).toBe(false)
    }
  })

  it('arms only when the knob is exactly "true" AND both creds are set', () => {
    setEnv(ARMED)
    expect(isSparkLiveArmed()).toBe(true)
    expect(canPlaceLiveOrders('spark')).toBe(true)
  })

  it('never arms FLAME as a side effect of arming SPARK', () => {
    setEnv(ARMED)
    expect(canPlaceLiveOrders('flame')).toBe(false)
  })
})

describe('isSparkCustomerEligible', () => {
  afterEach(() => { delete process.env.SPARK_MIN_EQUITY })

  it('is eligible when subscribed and equity clears the default $5,000 threshold', () => {
    expect(isSparkCustomerEligible(5000, true)).toBe(true)
    expect(isSparkCustomerEligible(10000, true)).toBe(true)
  })

  it('is NOT eligible when subscribed but equity is below the threshold', () => {
    expect(isSparkCustomerEligible(4999.99, true)).toBe(false)
    expect(isSparkCustomerEligible(0, true)).toBe(false)
  })

  it('is NOT eligible when equity clears the threshold but not subscribed', () => {
    expect(isSparkCustomerEligible(50000, false)).toBe(false)
  })

  it('is NOT eligible when neither subscribed nor sufficient equity', () => {
    expect(isSparkCustomerEligible(100, false)).toBe(false)
  })

  it('fails CLOSED when equity is null, even if subscribed', () => {
    expect(isSparkCustomerEligible(null, true)).toBe(false)
  })

  it('fails CLOSED when equity is not a finite number', () => {
    expect(isSparkCustomerEligible(Number.NaN, true)).toBe(false)
    expect(isSparkCustomerEligible(Number.POSITIVE_INFINITY, true)).toBe(false)
  })

  it('respects an explicit minEquity override', () => {
    expect(isSparkCustomerEligible(6000, true, 7500)).toBe(false)
    expect(isSparkCustomerEligible(7500, true, 7500)).toBe(true)
  })

  it('getSparkMinEquity defaults to $5,000 and is env-overridable', () => {
    delete process.env.SPARK_MIN_EQUITY
    expect(getSparkMinEquity()).toBe(SPARK_MIN_EQUITY_DEFAULT)
    expect(getSparkMinEquity()).toBe(5000)

    process.env.SPARK_MIN_EQUITY = '10000'
    expect(getSparkMinEquity()).toBe(10000)
  })

  it('getSparkMinEquity falls back to the default on an unparsable or non-positive override', () => {
    process.env.SPARK_MIN_EQUITY = 'not-a-number'
    expect(getSparkMinEquity()).toBe(SPARK_MIN_EQUITY_DEFAULT)

    process.env.SPARK_MIN_EQUITY = '0'
    expect(getSparkMinEquity()).toBe(SPARK_MIN_EQUITY_DEFAULT)

    process.env.SPARK_MIN_EQUITY = '-100'
    expect(getSparkMinEquity()).toBe(SPARK_MIN_EQUITY_DEFAULT)
  })
})
