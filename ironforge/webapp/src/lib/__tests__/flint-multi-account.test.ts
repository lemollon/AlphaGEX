/**
 * FLINT ON EVERY ACCOUNT EBB PLACES ON (Leron, 2026-09-26: "I want it live
 * on customer account too.").
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
// floor (funded seed) for every account in these tests is $1,500 (see the
// flame_paper_account mock below) — cushion = equity - 1500.
const BROKER: Record<string, { accountId: string; equity: number; obp: number }> = {
  'sb-user-key': { accountId: 'SBUSER1', equity: 2000, obp: 5000 },   // cushion $500 -> clears
  'sb-matt-key': { accountId: 'SBMATT1', equity: 1550, obp: 5000 },   // cushion $50 -> fails R1
  'flame-live-key': { accountId: 'FLAMEPROD1', equity: 2000, obp: 5000 }, // cushion $500 -> clears
}

let ownerPauseRows: Array<{ person: string }> = []
let productionPausedRow: Array<Record<string, unknown>> = []

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

    // ---- floors: production ladder + FLAME's shared sandbox paper ledger ----
    if (sql.includes("FROM flame_paper_account") && sql.includes("account_type = 'production'")) {
      return [{ starting_capital: 1500, high_water_balance: 1500 }]
    }
    if (sql.includes('FROM flame_paper_account')) {
      // getFlintPaperLedger (scanner.ts) — FLAME's shared sandbox floor/equity row.
      return [{ starting_capital: 1500, current_balance: 1500 }]
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
