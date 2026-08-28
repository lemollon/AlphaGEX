import { describe, it, expect, afterEach } from 'vitest'
import { isFlameLiveArmed, isProductionBot, getProductionAccountsForBot, describeLiveGate, canPlaceLiveOrders } from '../tradier'

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

  // Being armed is necessary but NO LONGER SUFFICIENT. Since per-owner pause
  // (ironforge_owner_pause) the gate also has to know who has paused their own
  // account, and that read fails CLOSED — so with no database reachable, as in
  // this suite, an armed FLAME still resolves to zero accounts. That is the
  // safe direction and is asserted deliberately here rather than mocked away.
  // The armed-and-readable path is covered in owner-pause.test.ts.
  it('is still blocked when armed but the owner-pause table is unreadable', async () => {
    setEnv(ARMED)
    await expect(getProductionAccountsForBot('flame')).resolves.toEqual([])
  })
})

/**
 * WHY it is disarmed has to be sayable out loud.
 *
 * 2026-08-19: FLAME's arm env was set on the operator console, which never runs
 * the scanner, while the scanning service had no FLAME creds. The scan log wrote
 * `traded@0.24` — byte-identical to a day that also filled live — because the
 * disarmed branch appended nothing. A whole trading day was lost to a blank
 * string. These pin the reason string that replaced it.
 */
describe('describeLiveGate — a disarmed bot must say which condition is unmet', () => {
  it('names every missing FLAME condition when nothing is set', () => {
    setEnv({})
    const why = describeLiveGate('flame')
    expect(why).toContain('IRONFORGE_FLAME_LIVE')
    expect(why).toContain('TRADIER_FLAME_API_KEY')
    expect(why).toContain('TRADIER_FLAME_ACCOUNT_ID')
  })

  it('names only the knob when the creds are present — the 8/19 failure exactly', () => {
    setEnv({ TRADIER_FLAME_API_KEY: 'k', TRADIER_FLAME_ACCOUNT_ID: 'a' })
    expect(describeLiveGate('flame')).toBe('missing:IRONFORGE_FLAME_LIVE')
  })

  it('names only the creds when the knob is on but the service lacks them', () => {
    setEnv({ IRONFORGE_FLAME_LIVE: 'true' })
    expect(describeLiveGate('flame')).toBe(
      'missing:TRADIER_FLAME_API_KEY,TRADIER_FLAME_ACCOUNT_ID',
    )
  })

  it('reports armed once all three are set', () => {
    setEnv(ARMED)
    expect(describeLiveGate('flame')).toBe('armed')
    expect(canPlaceLiveOrders('flame')).toBe(true)
  })

  it('never leaks a credential value', () => {
    setEnv({ TRADIER_FLAME_API_KEY: 'super-secret-key', TRADIER_FLAME_ACCOUNT_ID: 'acct-123' })
    const why = describeLiveGate('flame')
    expect(why).not.toContain('super-secret-key')
    expect(why).not.toContain('acct-123')
  })

  it('explains SPARK as a policy decision, not a missing variable', () => {
    setEnv(ARMED)
    expect(canPlaceLiveOrders('spark')).toBe(false)
    expect(describeLiveGate('spark')).toBe('spark_is_paper_only')
  })
})
