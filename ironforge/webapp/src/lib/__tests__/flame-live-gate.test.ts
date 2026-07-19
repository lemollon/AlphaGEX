import { describe, it, expect, afterEach } from 'vitest'
import { isFlameLiveArmed, isProductionBot, getProductionAccountsForBot } from '../tradier'

/**
 * FLAME must not be able to place real-money orders unless deliberately armed.
 *
 * FLAME backtested negative-EV at executable fills, so the live path exists but
 * ships disarmed. These tests pin the fail-closed behavior: if any one of the
 * three conditions (env knob, API key, account id) is missing, FLAME is not a
 * production bot and has zero production accounts.
 *
 * The gate reads process.env at call time, so setting env per-case is enough —
 * no module reset required.
 */

const ENV_KEYS = ['IRONFORGE_FLAME_LIVE', 'TRADIER_FLAME_API_KEY', 'TRADIER_FLAME_ACCOUNT_ID'] as const
type EnvKey = (typeof ENV_KEYS)[number]

function setEnv(vars: Partial<Record<EnvKey, string>>) {
  for (const k of ENV_KEYS) delete process.env[k]
  Object.assign(process.env, vars)
}

const ARMED = {
  IRONFORGE_FLAME_LIVE: 'true',
  TRADIER_FLAME_API_KEY: 'test-key',
  TRADIER_FLAME_ACCOUNT_ID: 'test-account',
} as const

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

describe('FLAME live-arm gate', () => {
  it('is disarmed with no env set at all (the shipped default)', () => {
    setEnv({})
    expect(isFlameLiveArmed()).toBe(false)
    expect(isProductionBot('flame')).toBe(false)
  })

  it('stays disarmed when creds exist but the knob is off', () => {
    setEnv({ TRADIER_FLAME_API_KEY: 'k', TRADIER_FLAME_ACCOUNT_ID: 'a' })
    expect(isFlameLiveArmed()).toBe(false)
    expect(isProductionBot('flame')).toBe(false)
  })

  it('stays disarmed when the knob is on but creds are missing', () => {
    setEnv({ IRONFORGE_FLAME_LIVE: 'true' })
    expect(isFlameLiveArmed()).toBe(false)
    expect(isProductionBot('flame')).toBe(false)
  })

  it('stays disarmed when only one of the two creds is present', () => {
    setEnv({ IRONFORGE_FLAME_LIVE: 'true', TRADIER_FLAME_API_KEY: 'k' })
    expect(isFlameLiveArmed()).toBe(false)

    setEnv({ IRONFORGE_FLAME_LIVE: 'true', TRADIER_FLAME_ACCOUNT_ID: 'a' })
    expect(isFlameLiveArmed()).toBe(false)
  })

  it('rejects truthy-but-not-"true" knob values', () => {
    for (const v of ['1', 'yes', 'TRUE', 'on', '']) {
      setEnv({ ...ARMED, IRONFORGE_FLAME_LIVE: v })
      expect(isFlameLiveArmed(), `knob value ${JSON.stringify(v)} must not arm`).toBe(false)
    }
  })

  it('arms only when the knob is exactly "true" AND both creds are set', () => {
    setEnv(ARMED)
    expect(isFlameLiveArmed()).toBe(true)
    expect(isProductionBot('flame')).toBe(true)
  })

  it('never changes the other bots, armed or not', () => {
    setEnv({})
    expect(isProductionBot('spark')).toBe(true)
    expect(isProductionBot('spark2')).toBe(true)
    expect(isProductionBot('inferno')).toBe(false)
    expect(isProductionBot('blaze')).toBe(false)

    setEnv(ARMED)
    expect(isProductionBot('spark')).toBe(true)
    expect(isProductionBot('inferno')).toBe(false)
    expect(isProductionBot('blaze')).toBe(false)
  })
})

describe('FLAME production accounts', () => {
  it('returns zero accounts while disarmed — no order can be routed', async () => {
    setEnv({})
    await expect(getProductionAccountsForBot('flame')).resolves.toEqual([])
  })

  it('returns zero accounts when the knob is on but creds are absent', async () => {
    setEnv({ IRONFORGE_FLAME_LIVE: 'true' })
    await expect(getProductionAccountsForBot('flame')).resolves.toEqual([])
  })

  it('returns the FLAME account only when fully armed', async () => {
    setEnv(ARMED)
    const accounts = await getProductionAccountsForBot('flame')
    expect(accounts).toHaveLength(1)
    expect(accounts[0]).toMatchObject({ name: 'Flame', accountId: 'test-account' })
  })
})
