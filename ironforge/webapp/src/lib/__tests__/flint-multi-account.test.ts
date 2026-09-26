/**
 * FLINT ON EVERY ACCOUNT EBB PLACES ON (Leron, 2026-09-26: "I want it live
 * on customer account too."), plus the 2026-09-26 follow-up: profit
 * protection is enforced PER ACCOUNT ("ironforge will have a lot of
 * accounts"), and the assignment guard's buy-back must route to that same
 * one account, never "every eligible account of this type."
 *
 * placeCallSpreadOrderAllAccounts now loops resolveEligibleAccounts('flame')
 * in full — the sandbox mirrors (User/Matt) EBB's put spread already places
 * on, plus Flame's own production account — not production only. These
 * integration tests exercise the REAL tradier.ts function end-to-end against
 * mocked DB rows and a mocked Tradier HTTP layer (global fetch), pinning:
 *
 *   1. sandbox vs production routing — both fire, correct base URL and
 *      result key (`Name:sandbox` / `Name:production`) for each.
 *   2. one account passes rule R1, another fails, on the SAME call — each
 *      account's cushion decision is fully independent.
 *   3. a paused owner is skipped — production drops, sandbox is unaffected.
 *   4. flint_account_floor is a PER-ACCOUNT floor, independent of equity —
 *      two accounts with the SAME equity but DIFFERENT floors clear R1
 *      differently — and it is seeded exactly once, from equity, never
 *      moved on a later call even as that account's equity changes.
 *   5. opts.close routes the buy-back to EXACTLY opts.targetPerson, never
 *      to any other otherwise-eligible account, and fails closed (zero
 *      accounts) when targetPerson is omitted.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockDbQuery = vi.fn()
vi.mock('../db', () => ({
  query: (...args: any[]) => mockDbQuery(...args),
  dbQuery: (...args: any[]) => mockDbQuery(...args),
  dbExecute: vi.fn().mockResolvedValue(1),
  sharedTable: (name: string) => name,
  botTable: (bot: string, table: string) => `${bot}_${table}`,
  escapeSql: (s: string) => s.replace(/'/g, "''"),
  num: (v: any) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0 },
  int: (v: any) => { const n = parseInt(v, 10); return Number.isFinite(n) ? n : 0 },
  CT_TODAY: "'2026-09-26'",
}))

const ENV_KEYS = [
  'IRONFORGE_FLAME_LIVE', 'TRADIER_FLAME_API_KEY', 'TRADIER_FLAME_ACCOUNT_ID',
  'TRADIER_SANDBOX_KEY_USER', 'TRADIER_SANDBOX_KEY_MATT', 'TRADIER_SANDBOX_KEY_LOGAN',
] as const

const ARMED = {
  IRONFORGE_FLAME_LIVE: 'true',
  TRADIER_FLAME_API_KEY: 'flame-live-key',
  TRADIER_FLAME_ACCOUNT_ID: 'FLAME-ENV-ACCT',
  TRADIER_SANDBOX_KEY_USER: 'sb-user-key',
  TRADIER_SANDBOX_KEY_MATT: 'sb-matt-key',
} as const

// Per-account broker state the fetch mock serves, keyed by API key.
const BROKER: Record<string, { accountId: string; equity: number; obp: number }> = {
  'sb-user-key': { accountId: 'SBUSER1', equity: 2000, obp: 5000 },   // cushion $500 vs $1,500 floor -> clears
  'sb-matt-key': { accountId: 'SBMATT1', equity: 1550, obp: 5000 },   // cushion $50 vs $1,500 floor -> fails R1
  'flame-live-key': { accountId: 'FLAMEPROD1', equity: 2000, obp: 5000 }, // cushion $500 -> clears
}

let ownerPauseRows: Array<{ person: string }> = []
let productionPausedRow: Array<Record<string, unknown>> = []

// flint_account_floor, in-memory — the per-account floor store under test.
// Pre-seeded with the OLD shared-ledger value ($1,500) for both sandbox
// mirrors by default, so every pre-existing test's cushion arithmetic below
// is unchanged; tests that exercise the floor store itself (independence,
// seed-once) override/clear this explicitly.
let floorStore: Record<string, number> = {}

function jsonResponse(body: any, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? 'OK' : 'ERR',
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as any
}

beforeEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  ownerPauseRows = []
  productionPausedRow = []
  floorStore = { 'User:sandbox': 1500, 'Matt:sandbox': 1500 }

  mockDbQuery.mockReset()
  mockDbQuery.mockImplementation(async (sql: string, params: any[] = []) => {
    // ---- account resolution ----
    if (sql.includes('SELECT person, api_key, account_id, type FROM ironforge_accounts')) {
      return [
        { person: 'User', api_key: 'sb-user-key', account_id: 'SBUSER1', type: 'sandbox' },
        { person: 'Matt', api_key: 'sb-matt-key', account_id: 'SBMATT1', type: 'sandbox' },
      ]
    }
    if (sql.includes('SELECT DISTINCT person, type FROM ironforge_accounts')) {
      return [
        { person: 'User', type: 'sandbox' },
        { person: 'Matt', type: 'sandbox' },
      ]
    }
    if (sql.includes('SELECT api_key, type FROM ironforge_accounts')) {
      const m = sql.match(/person = '([^']+)' AND type = '([^']+)'/)
      const person = m?.[1]
      const type = m?.[2]
      if (person === 'User' && type === 'sandbox') return [{ api_key: 'sb-user-key', type: 'sandbox' }]
      if (person === 'Matt' && type === 'sandbox') return [{ api_key: 'sb-matt-key', type: 'sandbox' }]
      return []
    }
    if (sql.includes('SELECT capital_pct FROM ironforge_accounts')) return []

    // ---- pause gates ----
    if (sql.includes('FROM ironforge_owner_pause')) return ownerPauseRows
    if (sql.includes('FROM ironforge_production_pause')) return productionPausedRow

    // ---- FLINT's own dedup / collateral reads ----
    if (sql.includes('FROM flint_positions')) return [{ cnt: 0 }]
    if (sql.includes('FROM flame_positions')) return [{ m: 0 }]

    // ---- floor: production ladder (unchanged, per-person, own table) ----
    if (sql.includes("FROM flame_paper_account") && sql.includes("account_type = 'production'")) {
      return [{ starting_capital: 1500, high_water_balance: 1500 }]
    }

    // ---- floor: flint_account_floor — the per-account store under test ----
    if (sql.includes('SELECT floor_amount FROM flint_account_floor')) {
      const key = `${params[0]}:${params[1]}`
      return floorStore[key] != null ? [{ floor_amount: floorStore[key] }] : []
    }
    if (sql.includes('SELECT funded_amount FROM ironforge_accounts')) {
      return [] // no configured funded amount in this schema — seeding falls through to equity
    }
    if (sql.includes('INSERT INTO flint_account_floor')) {
      const key = `${params[0]}:${params[1]}`
      if (floorStore[key] == null) floorStore[key] = params[3] // ON CONFLICT DO NOTHING semantics
      return []
    }

    return []
  })

  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: any) => {
    const auth = String(init?.headers?.Authorization ?? '')
    const key = auth.replace('Bearer ', '')
    const acct = BROKER[key]
    if (url.includes('/user/profile')) {
      return jsonResponse({ profile: { account: { account_number: acct?.accountId ?? null } } })
    }
    if (url.includes('/balances')) {
      return jsonResponse({
        balances: { total_equity: String(acct?.equity ?? 0), margin: { option_buying_power: String(acct?.obp ?? 0) } },
      })
    }
    if (url.includes('/orders') && init?.method === 'POST') {
      return jsonResponse({ order: { id: Math.floor(Math.random() * 1_000_000) + 1, status: 'ok' } })
    }
    if (url.includes('/orders/')) {
      return jsonResponse({ order: { status: 'filled', avg_fill_price: '0.30' } })
    }
    return jsonResponse({}, false)
  }))
})

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  vi.unstubAllGlobals()
})

import { placeCallSpreadOrderAllAccounts } from '../tradier'

describe('placeCallSpreadOrderAllAccounts — every eligible account, independently gated', () => {
  it('routes sandbox and production correctly: both fire, correct result keys and base URLs', async () => {
    Object.assign(process.env, ARMED)
    const calledUrls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: any) => {
      calledUrls.push(url)
      const auth = String(init?.headers?.Authorization ?? '')
      const key = auth.replace('Bearer ', '')
      const acct = BROKER[key]
      if (url.includes('/user/profile')) return jsonResponse({ profile: { account: { account_number: acct?.accountId ?? null } } })
      if (url.includes('/balances')) {
        return jsonResponse({ balances: { total_equity: String(acct?.equity ?? 0), margin: { option_buying_power: String(acct?.obp ?? 0) } } })
      }
      if (url.includes('/orders') && init?.method === 'POST') return jsonResponse({ order: { id: 42, status: 'ok' } })
      if (url.includes('/orders/')) return jsonResponse({ order: { status: 'filled', avg_fill_price: '0.30' } })
      return jsonResponse({}, false)
    }))

    // Matt's own R1 fails in the default BROKER table, so limit this
    // assertion to the routing question: give Matt a comfortable cushion too.
    BROKER['sb-matt-key'].equity = 2000

    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-TEST-1')
    BROKER['sb-matt-key'].equity = 1550 // restore for other tests

    expect(Object.keys(result).sort()).toEqual(['Flame:production', 'Matt:sandbox', 'User:sandbox'])
    expect(result['Flame:production'].account_type).toBe('production')
    expect(result['User:sandbox'].account_type).toBe('sandbox')
    expect(calledUrls.some((u) => u.includes('api.tradier.com'))).toBe(true)
    expect(calledUrls.some((u) => u.includes('sandbox.tradier.com'))).toBe(true)
  })

  it('one account passes rule R1, another fails, on the SAME call — fully independent', async () => {
    Object.assign(process.env, ARMED)
    // BROKER default: User cushion $500 (clears $171.40 maxloss), Matt cushion $50 (fails).
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-TEST-2')
    expect(Object.keys(result)).toContain('User:sandbox')
    expect(Object.keys(result)).not.toContain('Matt:sandbox')
    // Flame production (cushion $500) still fills — unaffected by Matt's failure.
    expect(Object.keys(result)).toContain('Flame:production')
  })

  it('a paused owner is skipped — production drops, sandbox is unaffected', async () => {
    Object.assign(process.env, ARMED)
    ownerPauseRows = [{ person: 'Flame' }]
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-TEST-3')
    expect(Object.keys(result)).not.toContain('Flame:production')
    expect(Object.keys(result)).toContain('User:sandbox')
  })

  it('production-wide pause drops Flame only; sandbox mirrors still trade', async () => {
    Object.assign(process.env, ARMED)
    productionPausedRow = [{ bot_name: 'FLAME', paused: true, paused_reason: 'test' }]
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-TEST-4')
    expect(Object.keys(result)).not.toContain('Flame:production')
    expect(Object.keys(result)).toContain('User:sandbox')
  })

  it('disarmed FLAME (no live env) drops production but sandbox still trades', async () => {
    // No ARMED env at all — canPlaceLiveOrders('flame') is false.
    process.env.TRADIER_SANDBOX_KEY_USER = 'sb-user-key'
    process.env.TRADIER_SANDBOX_KEY_MATT = 'sb-matt-key'
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-TEST-5')
    expect(Object.keys(result)).not.toContain('Flame:production')
    expect(Object.keys(result)).toContain('User:sandbox')
  })

  it('a favorable-day upsize (desired=2) steps down to 1 for the account whose cushion only covers 1', async () => {
    Object.assign(process.env, ARMED)
    // User: equity 2000, cushion 500 -> clears 2ct maxloss ($342.80) -> stays at 2.
    // Matt: give it a cushion that covers 1ct ($171.40) but not 2ct.
    BROKER['sb-matt-key'].equity = 1500 + 200
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-26', 770, 772, 2, 0.30, 'FLINT-TEST-6', { baseContracts: 1 },
    )
    BROKER['sb-matt-key'].equity = 1550
    expect(result['User:sandbox'].contracts).toBe(2)
    expect(result['Matt:sandbox'].contracts).toBe(1)
  })
})

describe('flint_account_floor — the per-account profit-gate floor', () => {
  it('is independent PER ACCOUNT — same equity, different floors, only the low-floor account clears R1', async () => {
    Object.assign(process.env, ARMED)
    // Same equity for both — isolates the floor as the only variable.
    BROKER['sb-user-key'].equity = 2000
    BROKER['sb-matt-key'].equity = 2000
    floorStore = { 'User:sandbox': 1000, 'Matt:sandbox': 3000 } // User cushion $1,000; Matt cushion -$1,000

    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-FLOOR-1')

    BROKER['sb-matt-key'].equity = 1550 // restore
    expect(Object.keys(result)).toContain('User:sandbox')
    expect(Object.keys(result)).not.toContain('Matt:sandbox')
  })

  it('seeds once, from equity — a fresh account with no configured funded amount floors at its OWN first-read equity', async () => {
    Object.assign(process.env, ARMED)
    floorStore = {} // no pre-existing row for either sandbox account
    BROKER['sb-user-key'].equity = 1000
    BROKER['sb-matt-key'].equity = 1000

    await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-FLOOR-2')

    expect(floorStore['User:sandbox']).toBe(1000)
    expect(floorStore['Matt:sandbox']).toBe(1000)
    BROKER['sb-user-key'].equity = 2000 // restore
    BROKER['sb-matt-key'].equity = 1550
  })

  it('never moves once seeded — a later call with MUCH higher equity does not re-seed the floor', async () => {
    Object.assign(process.env, ARMED)
    floorStore = {} // fresh account, no floor yet
    BROKER['sb-user-key'].equity = 1000 // "day 1" — floor seeds here

    const day1 = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-FLOOR-3A')
    expect(floorStore['User:sandbox']).toBe(1000)
    // Cushion is $0 on day 1 (equity === floor) — R1 fails, no fill.
    expect(Object.keys(day1)).not.toContain('User:sandbox')

    BROKER['sb-user-key'].equity = 5000 // "day 2" — a big profit
    const day2 = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-FLOOR-3B')
    // The floor MUST still be $1,000, not silently re-seeded to $5,000 —
    // that is what makes the $4,000 cushion below real.
    expect(floorStore['User:sandbox']).toBe(1000)
    expect(Object.keys(day2)).toContain('User:sandbox')

    BROKER['sb-user-key'].equity = 2000 // restore
  })

  it('production keeps its existing starting_capital floor — untouched by flint_account_floor', async () => {
    Object.assign(process.env, ARMED)
    floorStore = {} // even with sandbox floors wiped, production is unaffected
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-FLOOR-4')
    expect(Object.keys(result)).toContain('Flame:production') // still reads flame_paper_account, cushion $500
    expect(floorStore).not.toHaveProperty('Flame:production')
  })
})

describe('opts.close (assignment-guard buy-back) routes to targetPerson only', () => {
  it('closes EXACTLY targetPerson — never a different, otherwise-eligible account', async () => {
    Object.assign(process.env, ARMED)
    // User, Matt, and Flame are ALL otherwise fully eligible/resolvable —
    // proving the close call reaches only the one named account, not
    // "every eligible account of this type."
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-CLOSE-1', { close: true, targetPerson: 'User' },
    )
    expect(Object.keys(result)).toEqual(['User:sandbox'])
  })

  it('closes the named PRODUCTION account only, ignoring sandbox mirrors entirely', async () => {
    Object.assign(process.env, ARMED)
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-CLOSE-2', { close: true, targetPerson: 'Flame' },
    )
    expect(Object.keys(result)).toEqual(['Flame:production'])
  })

  it('a close call with no targetPerson fails CLOSED — touches zero accounts', async () => {
    Object.assign(process.env, ARMED)
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-26', 770, 772, 1, 0.30, 'FLINT-CLOSE-3', { close: true },
    )
    expect(Object.keys(result)).toEqual([])
  })
})
