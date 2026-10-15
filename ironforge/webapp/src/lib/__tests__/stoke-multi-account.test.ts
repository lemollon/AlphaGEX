/**
 * STOKE ON EVERY ACCOUNT FLAME'S OWN PUT SPREAD PLACES ON — mirrors FLINT's
 * own multi-account integration test shape (flint-multi-account.test.ts),
 * but for placeStokeOrderAllAccounts: own table (flame_stoke_positions),
 * own floor table (stoke_account_floor), own two entry gates (EBB-skip VIX
 * ratio + prior-day-SPY-down), evaluated against the REAL tradier.ts
 * function end-to-end against mocked DB rows, a mocked scanner.ts (gate
 * inputs), and a mocked Tradier HTTP layer (global fetch).
 *
 * Pins:
 *   1. BOTH entry gates are enforced, independently, before any account is
 *      even considered — gate 1 alone failing, or gate 2 alone failing,
 *      both zero out every account; both passing lets routing proceed.
 *   2. sandbox vs production routing — both fire, correct base URL and
 *      result key for each.
 *   3. one account passes the profit gate, another fails, on the SAME call.
 *   4. a paused owner / production-wide pause / disarmed FLAME all behave
 *      exactly like FLINT's own equivalents.
 *   5. stoke_account_floor is a PER-ACCOUNT floor, seeded once from equity,
 *      never moved — completely independent of flint_account_floor (never
 *      queried at all).
 *   6. opts.close routes the buy-back to EXACTLY opts.targetPerson, fails
 *      closed when omitted, and is NEVER blocked by gate 1/gate 2 (a
 *      buy-back must proceed even on a gate-failing day).
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
  CT_TODAY: "'2026-10-15'",
}))

// Gate 1 (EBB-skip VIX ratio > 0.80) + Gate 2 (prior-day-SPY-down) inputs —
// mutable per test so each scenario can flip them independently. Default
// here is BOTH gates passing (a real STOKE trading day).
let vixRatio: number | null = 0.85
let priorSpyUp: boolean | null = false // false = "closed DOWN" = gate 2 passes
let stokePnlByAccount: Record<string, number> = {}

vi.mock('../scanner', () => ({
  vixDecayCheck: vi.fn(async () => ({ reason: vixRatio != null && vixRatio > 0.80 ? null : 'vix_elevated', ratio: vixRatio, prior: 12, windowMax: 14 })),
  VIX_DECAY_CEILING: { spark: 0.90, flame: 0.80 },
  priorSpySessionWasUp: vi.fn(async () => priorSpyUp),
  getStokeCumulativeRealizedPnl: vi.fn(async (person: string, accountType: string) => stokePnlByAccount[`${person}:${accountType}`] ?? 0),
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

const BROKER: Record<string, { accountId: string; equity: number; obp: number }> = {
  'sb-user-key': { accountId: 'SBUSER1', equity: 2000, obp: 5000 },
  'sb-matt-key': { accountId: 'SBMATT1', equity: 1550, obp: 5000 },
  'flame-live-key': { accountId: 'FLAMEPROD1', equity: 2000, obp: 5000 },
}

let ownerPauseRows: Array<{ person: string }> = []
let productionPausedRow: Array<Record<string, unknown>> = []

// stoke_account_floor, in-memory — the per-account floor store under test.
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
  vixRatio = 0.85
  priorSpyUp = false
  stokePnlByAccount = {}

  mockDbQuery.mockReset()
  mockDbQuery.mockImplementation(async (sql: string, params: any[] = []) => {
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

    if (sql.includes('FROM ironforge_owner_pause')) return ownerPauseRows
    if (sql.includes('FROM ironforge_production_pause')) return productionPausedRow

    // ---- STOKE's own dedup ----
    if (sql.includes('FROM flame_stoke_positions')) return [{ cnt: 0 }]

    // ---- STOKE's own floor table ----
    if (sql.includes('SELECT floor_amount FROM stoke_account_floor')) {
      const key = `${params[0]}:${params[1]}`
      return floorStore[key] != null ? [{ floor_amount: floorStore[key] }] : []
    }
    if (sql.includes('SELECT funded_amount FROM ironforge_accounts')) {
      return []
    }
    if (sql.includes('INSERT INTO stoke_account_floor')) {
      const key = `${params[0]}:${params[1]}`
      if (floorStore[key] == null) floorStore[key] = params[3]
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

import { placeStokeOrderAllAccounts } from '../tradier'

describe('placeStokeOrderAllAccounts — both entry gates evaluated ONCE, market-wide, before any account', () => {
  it('gate 1 failing (ratio <= 0.80, EBB itself would trade) zeroes out every account, even otherwise-eligible ones', async () => {
    Object.assign(process.env, ARMED)
    vixRatio = 0.70 // EBB is trading today — STOKE must not fire
    priorSpyUp = false
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-GATE1')
    expect(Object.keys(result)).toEqual([])
  })

  it('a null/unreadable gate-1 ratio fails CLOSED, zero accounts', async () => {
    Object.assign(process.env, ARMED)
    vixRatio = null
    priorSpyUp = false
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-GATE1B')
    expect(Object.keys(result)).toEqual([])
  })

  it('gate 2 failing (prior SPY session closed UP, not down) zeroes out every account', async () => {
    Object.assign(process.env, ARMED)
    vixRatio = 0.85
    priorSpyUp = true // closed UP — STOKE requires DOWN
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-GATE2')
    expect(Object.keys(result)).toEqual([])
  })

  it('a null/unreadable gate-2 prior-day read fails CLOSED, zero accounts', async () => {
    Object.assign(process.env, ARMED)
    vixRatio = 0.85
    priorSpyUp = null
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-GATE2B')
    expect(Object.keys(result)).toEqual([])
  })

  it('both gates passing routes sandbox and production correctly', async () => {
    Object.assign(process.env, ARMED)
    vixRatio = 0.85
    priorSpyUp = false
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-BOTH-OK')
    expect(Object.keys(result).sort()).toEqual(['Flame:production', 'Matt:sandbox', 'User:sandbox'])
    expect(result['Flame:production'].account_type).toBe('production')
    expect(result['User:sandbox'].account_type).toBe('sandbox')
  })
})

describe('placeStokeOrderAllAccounts — per-account profit gate + routing (gates passing)', () => {
  it('one account passes the profit gate, another fails, on the SAME call — fully independent', async () => {
    Object.assign(process.env, ARMED)
    floorStore = { 'User:sandbox': 1500, 'Matt:sandbox': 100 }
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-TEST-2')
    expect(Object.keys(result)).toContain('User:sandbox')
    expect(Object.keys(result)).not.toContain('Matt:sandbox')
    expect(Object.keys(result)).toContain('Flame:production')
  })

  it('a paused owner is skipped — production drops, sandbox is unaffected', async () => {
    Object.assign(process.env, ARMED)
    ownerPauseRows = [{ person: 'Flame' }]
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-TEST-3')
    expect(Object.keys(result)).not.toContain('Flame:production')
    expect(Object.keys(result)).toContain('User:sandbox')
  })

  it('production-wide pause drops Flame only; sandbox mirrors still trade', async () => {
    Object.assign(process.env, ARMED)
    productionPausedRow = [{ bot_name: 'FLAME', paused: true, paused_reason: 'test' }]
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-TEST-4')
    expect(Object.keys(result)).not.toContain('Flame:production')
    expect(Object.keys(result)).toContain('User:sandbox')
  })

  it('disarmed FLAME (no live env) drops production but sandbox still trades', async () => {
    process.env.TRADIER_SANDBOX_KEY_USER = 'sb-user-key'
    process.env.TRADIER_SANDBOX_KEY_MATT = 'sb-matt-key'
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-TEST-5')
    expect(Object.keys(result)).not.toContain('Flame:production')
    expect(Object.keys(result)).toContain('User:sandbox')
  })

  it('a same-day STOKE loss on one account never affects another account\'s cushion', async () => {
    Object.assign(process.env, ARMED)
    floorStore = { 'User:sandbox': 500, 'Matt:sandbox': 500 }
    stokePnlByAccount = { 'User:sandbox': -400, 'Matt:sandbox': 0 } // User cushion=100<171.40 fails; Matt cushion=500 clears
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-TEST-6')
    expect(Object.keys(result)).not.toContain('User:sandbox')
    expect(Object.keys(result)).toContain('Matt:sandbox')
  })
})

describe('stoke_account_floor — STOKE\'s OWN per-account floor, never shared with FLINT', () => {
  it('seeds once, from equity — a fresh account with no configured funded amount floors at its OWN first-read equity', async () => {
    Object.assign(process.env, ARMED)
    floorStore = {}
    BROKER['sb-user-key'].equity = 1000
    BROKER['sb-matt-key'].equity = 1000

    await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-FLOOR-2')

    expect(floorStore['User:sandbox']).toBe(1000)
    expect(floorStore['Matt:sandbox']).toBe(1000)
    BROKER['sb-user-key'].equity = 2000
    BROKER['sb-matt-key'].equity = 1550
  })

  it('never moves once seeded — a later call with much higher equity does not re-seed the floor', async () => {
    Object.assign(process.env, ARMED)
    floorStore = {}
    BROKER['sb-user-key'].equity = 100 // seeds here, under the $500 cap

    const day1 = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-FLOOR-3A')
    expect(floorStore['User:sandbox']).toBe(100)
    expect(Object.keys(day1)).not.toContain('User:sandbox') // cushion $100 < $171.40 maxloss

    BROKER['sb-user-key'].equity = 5000
    const day2 = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-FLOOR-3B')
    expect(floorStore['User:sandbox']).toBe(100)
    expect(Object.keys(day2)).not.toContain('User:sandbox')

    BROKER['sb-user-key'].equity = 2000
  })

  it('production gets its own stoke_account_floor row, never flint_account_floor', async () => {
    Object.assign(process.env, ARMED)
    floorStore = {}
    const result = await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-FLOOR-4')
    expect(Object.keys(result)).toContain('Flame:production')
    expect(floorStore['Flame:production']).toBe(2000)
  })

  it('never reads flint_account_floor at all — proof STOKE and FLINT keep fully separate floors', async () => {
    Object.assign(process.env, ARMED)
    await placeStokeOrderAllAccounts('SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-FLOOR-5')
    const sqlCalls = mockDbQuery.mock.calls.map((c) => String(c[0]))
    expect(sqlCalls.some((s) => s.includes('flint_account_floor'))).toBe(false)
    expect(sqlCalls.some((s) => s.includes('flint_positions'))).toBe(false)
  })
})

describe('opts.close (assignment-guard buy-back) routes to targetPerson only, and is NEVER blocked by gate 1/gate 2', () => {
  it('closes EXACTLY targetPerson even on a day BOTH entry gates would fail', async () => {
    Object.assign(process.env, ARMED)
    vixRatio = 0.10 // gate 1 would fail
    priorSpyUp = true // gate 2 would fail
    const result = await placeStokeOrderAllAccounts(
      'SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-CLOSE-1', { close: true, targetPerson: 'User' },
    )
    expect(Object.keys(result)).toEqual(['User:sandbox'])
  })

  it('closes the named PRODUCTION account only, ignoring sandbox mirrors entirely', async () => {
    Object.assign(process.env, ARMED)
    const result = await placeStokeOrderAllAccounts(
      'SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-CLOSE-2', { close: true, targetPerson: 'Flame' },
    )
    expect(Object.keys(result)).toEqual(['Flame:production'])
  })

  it('a close call with no targetPerson fails CLOSED — touches zero accounts', async () => {
    Object.assign(process.env, ARMED)
    const result = await placeStokeOrderAllAccounts(
      'SPY', '2026-10-15', 770, 772, 1, 0.30, 'STOKE-CLOSE-3', { close: true },
    )
    expect(Object.keys(result)).toEqual([])
  })
})
