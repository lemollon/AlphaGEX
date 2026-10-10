/**
 * FLAME'S LIVE ORDER HAD NOWHERE TO GO (2026-08-20).
 *
 * FLAME was armed on the scanning service, reached the live branch, called
 * placeIcOrderAllAccounts — and filled nothing, every day since 2026-04-17. The
 * scan log said `live:no_fill`, which reads like a broker rejection. It wasn't:
 *
 *   [tradier] placeIcOrderAllAccounts: bot=flame,
 *             eligible=[User:sandbox, Matt:sandbox, Logan:sandbox]
 *
 * Zero production accounts. The eligible list is composed from the
 * ironforge_accounts table, whose single production row is Logan's, carrying
 * bot="SPARK,INFERNO". FLAME's live account is credentialed by TRADIER_FLAME_*
 * ENV, so it could never appear there. KINDLE had already hit this exact bug on
 * 2026-06-24 and got an injection block; FLAME never got the equivalent.
 *
 * These tests pin the routing in BOTH directions: armed FLAME reaches its
 * account, disarmed FLAME still cannot, and the exit is never narrower than the
 * entry.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.hoisted(() => {
  process.env.TRADIER_API_KEY = 'test-production-key'
})

const mockDbQuery = vi.fn()
vi.mock('../db', () => ({
  query: (...args: any[]) => mockDbQuery(...args),
  dbQuery: (...args: any[]) => mockDbQuery(...args),
  dbExecute: vi.fn(),
  sharedTable: (name: string) => name,
  botTable: (bot: string, table: string) => `${bot}_${table}`,
  escapeSql: (s: string) => s.replace(/'/g, "''"),
  num: (v: any) => parseFloat(v) || 0,
  int: (v: any) => parseInt(v) || 0,
  CT_TODAY: "'2026-08-20'",
}))

import { resolveEligibleAccounts, flameProductionAccount } from '../tradier'

const ENV_KEYS = ['IRONFORGE_FLAME_LIVE', 'TRADIER_FLAME_API_KEY', 'TRADIER_FLAME_ACCOUNT_ID'] as const
type EnvKey = (typeof ENV_KEYS)[number]

const ARMED = {
  IRONFORGE_FLAME_LIVE: 'true',
  TRADIER_FLAME_API_KEY: 'flame-live-key',
  TRADIER_FLAME_ACCOUNT_ID: '6YB71371',
} as const

function setEnv(vars: Partial<Record<EnvKey, string>>) {
  for (const k of ENV_KEYS) delete process.env[k]
  Object.assign(process.env, vars)
}

/**
 * PRODUCTION AS IT ACTUALLY WAS on 2026-08-20: three sandbox rows carrying
 * FLAME, one production row (Logan) that does NOT. Reproducing the real table is
 * the point — a mock that hands FLAME a production row would test nothing.
 */
const REAL_WORLD_ROWS = [
  { person: 'User', type: 'sandbox', api_key: 'sb-user', account_id: 'SB1', is_active: true },
  { person: 'Matt', type: 'sandbox', api_key: 'sb-matt', account_id: 'SB2', is_active: true },
  { person: 'Logan', type: 'sandbox', api_key: 'sb-logan', account_id: 'SB3', is_active: true },
]

beforeEach(() => {
  mockDbQuery.mockReset()
  mockDbQuery.mockResolvedValue(REAL_WORLD_ROWS)
})

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

function productionNames(accts: Array<{ name: string; type: string }>) {
  return accts.filter((a) => a.type === 'production').map((a) => a.name)
}

describe('resolveEligibleAccounts — FLAME reaches its env-credentialed live account', () => {
  it('THE BUG: armed FLAME had zero production accounts and so could never fill', async () => {
    setEnv(ARMED)
    const accts = await resolveEligibleAccounts('flame')
    // Before the fix this was [] — the whole defect, in one assertion.
    expect(productionNames(accts)).toEqual(['Flame'])
  })

  it('routes to the account id from env, not one discovered from /user/profile', async () => {
    setEnv(ARMED)
    const flame = (await resolveEligibleAccounts('flame')).find((a) => a.type === 'production')
    expect(flame?.cachedAccountId).toBe('6YB71371')
  })

  it('composes ZERO production accounts while disarmed — unchanged fail-closed default', async () => {
    setEnv({})
    expect(productionNames(await resolveEligibleAccounts('flame'))).toEqual([])
  })

  it('composes ZERO production accounts when the knob is on but creds are absent', async () => {
    setEnv({ IRONFORGE_FLAME_LIVE: 'true' })
    expect(productionNames(await resolveEligibleAccounts('flame'))).toEqual([])
  })

  it('composes ZERO production accounts when creds exist but the knob is off', async () => {
    setEnv({ TRADIER_FLAME_API_KEY: 'k', TRADIER_FLAME_ACCOUNT_ID: 'a' })
    expect(productionNames(await resolveEligibleAccounts('flame'))).toEqual([])
  })

  it('never injects on a sandboxOnly call, even fully armed', async () => {
    setEnv(ARMED)
    expect(productionNames(await resolveEligibleAccounts('flame', { sandboxOnly: true }))).toEqual([])
  })

  it('does not leak FLAME\'s account into another bot — INFERNO stays paper', async () => {
    setEnv(ARMED)
    expect(productionNames(await resolveEligibleAccounts('inferno'))).toEqual([])
    expect(productionNames(await resolveEligibleAccounts('spark'))).toEqual([])
  })

  it('still returns the sandbox accounts alongside — paper never regressed', async () => {
    setEnv(ARMED)
    const accts = await resolveEligibleAccounts('flame')
    expect(accts.filter((a) => a.type !== 'production').length).toBeGreaterThan(0)
  })
})

/**
 * AN EXIT MUST NEVER BE NARROWER THAN ITS ENTRY.
 *
 * Fixing only the open path would let FLAME acquire a real position it has no
 * route to close — the orphan-left-to-expire → assignment case. So the close
 * path uses the same account, and deliberately does NOT require the arm knob.
 */
describe('flameProductionAccount — entry requires arming, exit does not', () => {
  it('ENTRY: null while disarmed', () => {
    setEnv({ TRADIER_FLAME_API_KEY: 'k', TRADIER_FLAME_ACCOUNT_ID: 'a' })
    expect(flameProductionAccount({ requireArmed: true })).toBeNull()
  })

  it('EXIT: resolves while disarmed, so an open position can always be closed', () => {
    setEnv({ TRADIER_FLAME_API_KEY: 'k', TRADIER_FLAME_ACCOUNT_ID: 'a' })
    expect(flameProductionAccount({ requireArmed: false })?.name).toBe('Flame')
  })

  it('EXIT: still null with no credentials at all — nothing to fabricate', () => {
    setEnv({})
    expect(flameProductionAccount({ requireArmed: false })).toBeNull()
  })

  it('EXIT: null when only one of the two creds is present', () => {
    setEnv({ TRADIER_FLAME_API_KEY: 'k' })
    expect(flameProductionAccount({ requireArmed: false })).toBeNull()
    setEnv({ TRADIER_FLAME_ACCOUNT_ID: 'a' })
    expect(flameProductionAccount({ requireArmed: false })).toBeNull()
  })

  it('always resolves to the live broker, never the sandbox host', () => {
    setEnv(ARMED)
    expect(flameProductionAccount({ requireArmed: true })?.baseUrl).toContain('api.tradier.com')
  })
})
