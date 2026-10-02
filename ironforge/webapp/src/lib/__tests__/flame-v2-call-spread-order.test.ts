/**
 * placeFlameV2CallSpreadOrder (tradier.ts) — the FLAME v2 SPY 0DTE CALL
 * credit spread order path, exercised end-to-end against mocked db.ts rows
 * and a mocked Tradier HTTP layer (global fetch), the same style
 * flint-multi-account.test.ts already uses for the analogous FLINT function.
 *
 * Pins:
 *   1. open: correct multileg legs (sell_to_open short call, buy_to_open
 *      long call), type=limit at the given credit, for every eligible
 *      account (sandbox mirrors + FLAME's own production account once
 *      armed).
 *   2. production is dropped when FLAME is not armed, or is paused — sandbox
 *      is unaffected either way.
 *   3. an account whose option buying power cannot margin the trade is
 *      skipped, independently of every other account.
 *   4. opts.close flips legs to buy_to_close/sell_to_close, type=market, and
 *      touches EXACTLY opts.targetPerson — never any other eligible account
 *      — and fails closed (zero orders) when targetPerson is omitted.
 *   5. a non-positive contracts count or callLong<=callShort refuses to
 *      place anything, with zero DB/fetch calls.
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
  CT_TODAY: "'2026-10-02'",
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
} as const

const BROKER: Record<string, { accountId: string; equity: number; obp: number }> = {
  'sb-user-key': { accountId: 'SBUSER1', equity: 5000, obp: 5000 },
  'flame-live-key': { accountId: 'FLAMEPROD1', equity: 5000, obp: 5000 },
}

let ownerPauseRows: Array<{ person: string }> = []
let productionPausedRow: Array<Record<string, unknown>> = []
const orderCalls: Array<{ url: string; body: Record<string, string> }> = []

function jsonResponse(body: any, ok = true) {
  return {
    ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'ERR',
    json: async () => body, text: async () => JSON.stringify(body),
  } as any
}

function parseBody(init?: any): Record<string, string> {
  const raw = String(init?.body ?? '')
  const out: Record<string, string> = {}
  for (const pair of raw.split('&')) {
    if (!pair) continue
    const [k, v] = pair.split('=')
    out[decodeURIComponent(k)] = decodeURIComponent(v ?? '')
  }
  return out
}

beforeEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  ownerPauseRows = []
  productionPausedRow = []
  orderCalls.length = 0

  mockDbQuery.mockReset()
  mockDbQuery.mockImplementation(async (sql: string) => {
    if (sql.includes('SELECT person, api_key, account_id, type FROM ironforge_accounts')) {
      return [{ person: 'User', api_key: 'sb-user-key', account_id: 'SBUSER1', type: 'sandbox' }]
    }
    if (sql.includes('SELECT DISTINCT person, type FROM ironforge_accounts')) {
      return [{ person: 'User', type: 'sandbox' }]
    }
    if (sql.includes('FROM ironforge_owner_pause')) return ownerPauseRows
    if (sql.includes('FROM ironforge_production_pause')) return productionPausedRow
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
      orderCalls.push({ url, body: parseBody(init) })
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

import { placeFlameV2CallSpreadOrder } from '../tradier'

describe('open — correct legs/price, every eligible account', () => {
  it('sandbox only (not armed): sell_to_open/buy_to_open, type=limit at entryCredit', async () => {
    process.env.TRADIER_SANDBOX_KEY_USER = ARMED.TRADIER_SANDBOX_KEY_USER
    const result = await placeFlameV2CallSpreadOrder('SPY', '2026-10-02', 650, 652, 2, 0.35, 'FLAMEV2C-TEST-1')
    expect(result['User:sandbox']).toBeTruthy()
    expect(result['Flame:production']).toBeUndefined()
    expect(orderCalls.length).toBe(1)
    const body = orderCalls[0].body
    expect(body.class).toBe('multileg')
    expect(body.type).toBe('limit')
    expect(body.price).toBe('0.35')
    expect(body['side[0]']).toBe('sell_to_open')
    expect(body['side[1]']).toBe('buy_to_open')
    expect(body['quantity[0]']).toBe('2')
    expect(body['option_symbol[0]']).toContain('650')
    expect(body['option_symbol[1]']).toContain('652')
  })

  it('armed + unpaused: production account also fires', async () => {
    Object.assign(process.env, ARMED)
    const result = await placeFlameV2CallSpreadOrder('SPY', '2026-10-02', 650, 652, 1, 0.30, 'FLAMEV2C-TEST-2')
    expect(result['User:sandbox']).toBeTruthy()
    expect(result['Flame:production']).toBeTruthy()
    expect(orderCalls.length).toBe(2)
  })

  it('not armed (IRONFORGE_FLAME_LIVE unset): production dropped, sandbox unaffected', async () => {
    Object.assign(process.env, ARMED)
    delete process.env.IRONFORGE_FLAME_LIVE
    const result = await placeFlameV2CallSpreadOrder('SPY', '2026-10-02', 650, 652, 1, 0.30, 'FLAMEV2C-TEST-3')
    expect(result['User:sandbox']).toBeTruthy()
    expect(result['Flame:production']).toBeUndefined()
  })

  it('production trading paused: production dropped, sandbox unaffected', async () => {
    Object.assign(process.env, ARMED)
    productionPausedRow = [{ paused: true, paused_reason: 'test' }]
    const result = await placeFlameV2CallSpreadOrder('SPY', '2026-10-02', 650, 652, 1, 0.30, 'FLAMEV2C-TEST-4')
    expect(result['User:sandbox']).toBeTruthy()
    expect(result['Flame:production']).toBeUndefined()
  })

  it('owner paused: production dropped, sandbox unaffected', async () => {
    Object.assign(process.env, ARMED)
    ownerPauseRows = [{ person: 'Flame' }]
    const result = await placeFlameV2CallSpreadOrder('SPY', '2026-10-02', 650, 652, 1, 0.30, 'FLAMEV2C-TEST-5')
    expect(result['User:sandbox']).toBeTruthy()
    expect(result['Flame:production']).toBeUndefined()
  })

  it('insufficient option buying power: that account skipped, no order placed', async () => {
    process.env.TRADIER_SANDBOX_KEY_USER = ARMED.TRADIER_SANDBOX_KEY_USER
    BROKER['sb-user-key'].obp = 50 // $2 wide x 100 x 2 contracts = $400 needed
    const result = await placeFlameV2CallSpreadOrder('SPY', '2026-10-02', 650, 652, 2, 0.30, 'FLAMEV2C-TEST-6')
    expect(result['User:sandbox']).toBeUndefined()
    expect(orderCalls.length).toBe(0)
    BROKER['sb-user-key'].obp = 5000 // restore for later tests
  })
})

describe('close (assignment-guard buy-back) routes to targetPerson only', () => {
  it('flips to buy_to_close/sell_to_close, market order, exactly one account', async () => {
    process.env.TRADIER_SANDBOX_KEY_USER = ARMED.TRADIER_SANDBOX_KEY_USER
    const result = await placeFlameV2CallSpreadOrder(
      'SPY', '2026-10-02', 650, 652, 2, 0, 'FLAMEV2C-TEST-CLOSE-1',
      { close: true, targetPerson: 'User', targetAccountType: 'sandbox' },
    )
    expect(result['User:sandbox']).toBeTruthy()
    expect(orderCalls.length).toBe(1)
    const body = orderCalls[0].body
    expect(body.type).toBe('market')
    expect(body['side[0]']).toBe('buy_to_close')
    expect(body['side[1]']).toBe('sell_to_close')
  })

  it('omitting targetPerson fails closed: zero accounts touched', async () => {
    process.env.TRADIER_SANDBOX_KEY_USER = ARMED.TRADIER_SANDBOX_KEY_USER
    const result = await placeFlameV2CallSpreadOrder(
      'SPY', '2026-10-02', 650, 652, 2, 0, 'FLAMEV2C-TEST-CLOSE-2', { close: true },
    )
    expect(Object.keys(result)).toEqual([])
    expect(orderCalls.length).toBe(0)
  })

  it('a different eligible account is never touched by someone elses close', async () => {
    Object.assign(process.env, ARMED)
    const result = await placeFlameV2CallSpreadOrder(
      'SPY', '2026-10-02', 650, 652, 1, 0, 'FLAMEV2C-TEST-CLOSE-3',
      { close: true, targetPerson: 'User', targetAccountType: 'sandbox' },
    )
    expect(result['User:sandbox']).toBeTruthy()
    expect(result['Flame:production']).toBeUndefined()
    expect(orderCalls.length).toBe(1)
  })
})

describe('invalid inputs refuse to place anything', () => {
  it('contracts <= 0: zero DB/fetch calls', async () => {
    process.env.TRADIER_SANDBOX_KEY_USER = ARMED.TRADIER_SANDBOX_KEY_USER
    const result = await placeFlameV2CallSpreadOrder('SPY', '2026-10-02', 650, 652, 0, 0.30, 'FLAMEV2C-TEST-7')
    expect(result).toEqual({})
    expect(orderCalls.length).toBe(0)
    expect(mockDbQuery).not.toHaveBeenCalled()
  })
  it('callLong <= callShort: refuses', async () => {
    process.env.TRADIER_SANDBOX_KEY_USER = ARMED.TRADIER_SANDBOX_KEY_USER
    const result = await placeFlameV2CallSpreadOrder('SPY', '2026-10-02', 652, 650, 1, 0.30, 'FLAMEV2C-TEST-8')
    expect(result).toEqual({})
    expect(orderCalls.length).toBe(0)
  })
})
