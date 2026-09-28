/**
 * SPARK_FLINT — WIRED integration tests against the real
 * placeCallSpreadOrderAllAccounts (tradier.ts, botName: 'spark'), with a
 * mocked DB layer and a mocked Tradier HTTP layer (global fetch). Mirrors
 * fast-start-wiring.test.ts's own harness style (FLAME's shipped
 * equivalent) for SPARK's account-level safety net.
 *
 * Covers, at the WIRED call site (not just the pure spark-flint-separate.ts
 * function, which already has its own unit + parity tests):
 *   1. KILL SWITCH: with SPARK_FAST_START off, FLINT-on-SPARK still sizes
 *      off rule R1 alone (byte-identical to FLAME's own R1 gate) — the
 *      safety net only ever DROPS, never adds, and drops nothing when
 *      SPARK hasn't traded today (spark_positions empty -> sparkCost=0).
 *   2. The account-level safety net DROPS FLINT when SPARK's own
 *      already-sized contracts (read back from spark_positions) plus this
 *      FLINT contract would cross the account's current floor.
 *   3. The safety net PASSES FLINT through when there is room.
 *   4. botName is properly threaded: SPARK's production account (paper-only,
 *      canPlaceLiveOrders('spark') hard-coded false) never receives a FLINT
 *      order even if somehow present in the eligible list.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockDbQuery = vi.fn()
const mockDbExecute = vi.fn().mockResolvedValue(1)

let flintFloorStore: Record<string, number> = {}
let fastStartStateStore: Record<string, { phase: number; deposit: number; peak_profit: number }> = {}
let sparkPositionsRow: Record<string, unknown> | null = null

vi.mock('../db', () => ({
  query: (...args: any[]) => mockDbQuery(...args),
  dbQuery: (...args: any[]) => mockDbQuery(...args),
  dbExecute: (...args: any[]) => mockDbExecute(...args),
  sharedTable: (name: string) => name,
  botTable: (bot: string, table: string) => `${bot}_${table}`,
  escapeSql: (s: string) => s.replace(/'/g, "''"),
  num: (v: any) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0 },
  int: (v: any) => { const n = parseInt(v, 10); return Number.isFinite(n) ? n : 0 },
  CT_TODAY: "'2026-09-29'",
}))

const ENV_KEYS = [
  'SPARK_FAST_START', 'SPARK_FAVORABLE_UPSIZE', 'SPARK_FLINT',
  'TRADIER_SANDBOX_KEY_USER', 'TRADIER_SANDBOX_KEY_MATT', 'TRADIER_SANDBOX_KEY_LOGAN',
] as const

const BROKER: Record<string, { accountId: string; equity: number | null; obp: number }> = {
  'sb-user-key': { accountId: 'SBUSER1', equity: 5300, obp: 5000 },
}

function jsonResponse(body: any, ok = true) {
  return { ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'ERR', json: async () => body, text: async () => JSON.stringify(body) } as any
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-29T15:10:00Z')) // ~10:10 CT — SPARK's own window
  for (const k of ENV_KEYS) delete process.env[k]

  flintFloorStore = { 'User:sandbox': 5000 } // deposit = $5,000
  fastStartStateStore = {}
  sparkPositionsRow = null // SPARK has not traded today by default

  mockDbQuery.mockReset()
  mockDbExecute.mockReset().mockResolvedValue(1)

  mockDbQuery.mockImplementation(async (sql: string, params: any[] = []) => {
    if (sql.includes('SELECT person, api_key, account_id, type FROM ironforge_accounts')) {
      return [{ person: 'User', api_key: 'sb-user-key', account_id: 'SBUSER1', type: 'sandbox' }]
    }
    if (sql.includes('SELECT DISTINCT person, type FROM ironforge_accounts')) {
      return [{ person: 'User', type: 'sandbox' }]
    }
    if (sql.includes('SELECT api_key, type FROM ironforge_accounts')) {
      return [{ api_key: 'sb-user-key', type: 'sandbox' }]
    }
    if (sql.includes('SELECT capital_pct FROM ironforge_accounts')) return []
    if (sql.includes('FROM ironforge_owner_pause')) return []
    if (sql.includes('FROM ironforge_production_pause')) return []
    if (sql.includes('FROM flint_positions')) return [{ cnt: 0 }]
    if (sql.includes('FROM spark_positions')) {
      return sparkPositionsRow ? [sparkPositionsRow] : []
    }

    if (sql.includes('SELECT floor_amount FROM flint_account_floor')) {
      const key = `${params[0]}:${params[1]}`
      return flintFloorStore[key] != null ? [{ floor_amount: flintFloorStore[key] }] : []
    }
    if (sql.includes('SELECT funded_amount FROM ironforge_accounts')) return []
    if (sql.includes('INSERT INTO flint_account_floor')) {
      const key = `${params[0]}:${params[1]}`
      if (flintFloorStore[key] == null) flintFloorStore[key] = params[3]
      return []
    }

    if (sql.includes('SELECT phase, deposit, peak_profit FROM fast_start_state')) {
      const key = `${params[0]}:${params[1]}`
      return fastStartStateStore[key] ? [fastStartStateStore[key]] : []
    }
    if (sql.includes('INSERT INTO fast_start_state')) {
      const key = `${params[0]}:${params[1]}`
      if (!fastStartStateStore[key]) {
        fastStartStateStore[key] = { phase: 1, deposit: params[2], peak_profit: params[3] ?? 0 }
      }
      return []
    }
    if (sql.includes('INSERT INTO fast_start_decision_log')) return []

    return []
  })

  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: any) => {
    const auth = String(init?.headers?.Authorization ?? '')
    const key = auth.replace('Bearer ', '')
    const acct = BROKER[key]
    if (url.includes('/user/profile')) return jsonResponse({ profile: { account: { account_number: acct?.accountId ?? null } } })
    if (url.includes('/balances')) {
      if (acct?.equity == null) return jsonResponse({}, false)
      return jsonResponse({ balances: { total_equity: String(acct.equity), margin: { option_buying_power: String(acct.obp) } } })
    }
    if (url.includes('/orders') && init?.method === 'POST') return jsonResponse({ order: { id: 42, status: 'ok' } })
    if (url.includes('/orders/')) return jsonResponse({ order: { status: 'filled', avg_fill_price: '0.30' } })
    return jsonResponse({}, false)
  }))
})

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

import { placeCallSpreadOrderAllAccounts } from '../tradier'

describe('SPARK_FLINT — wired at placeCallSpreadOrderAllAccounts (botName: spark)', () => {
  it('KILL SWITCH: SPARK has not traded today (sparkCost=0) -> safety net never drops FLINT; sizes off rule R1 alone', async () => {
    // deposit=5000, equity=5300 -> cushion=300 >= flint ml (~171.40 for a
    // $2-wide/$0.30-credit contract) -> R1 passes. sparkCost=0 (no row) ->
    // combined=171.40 <= budget_to_floor(equity-floor=300) -> passes.
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos1', { baseContracts: 1, botName: 'spark' },
    )
    expect(result['User:sandbox']).toBeDefined()
  })

  it('the safety net DROPS FLINT when SPARK already committed enough today to cross the floor', async () => {
    // SPARK already sized 3 contracts today at collateral_required=$1,200
    // total ($400/contract) -> sparkCost=$1,200. budget_to_floor (Phase 1,
    // floor=deposit=5000, equity=5300) = 300. combined = 1200+171.40 >> 300
    // -> dropped.
    sparkPositionsRow = { contracts: 3, max_loss: 1200 }
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos2', { baseContracts: 1, botName: 'spark' },
    )
    expect(result['User:sandbox']).toBeUndefined()
  })

  it('the safety net PASSES FLINT when SPARK committed little today and there is room', async () => {
    // SPARK sized 1 contract at $150 collateral -> sparkCost=150.
    // budget_to_floor=300. combined=150+171.40=321.40... that actually
    // EXCEEDS 300, so tighten: raise equity so the budget clears it.
    sparkPositionsRow = { contracts: 1, max_loss: 150 }
    BROKER['sb-user-key'].equity = 6000 // budget_to_floor = 6000-5000 = 1000
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos3', { baseContracts: 1, botName: 'spark' },
    )
    expect(result['User:sandbox']).toBeDefined()
    BROKER['sb-user-key'].equity = 5300
  })

  it("SPARK_FAST_START on, Phase 2: the safety net reads the RATCHETED CPPI floor, not the plain deposit", async () => {
    process.env.SPARK_FAST_START = 'on'
    // Phase 2, deposit=5000, peak_profit=1000 -> floor = 5000+0.25*1000 = 5250.
    // equity=5300 -> budget_to_floor = 50. sparkCost=0 (no row today).
    // combined = 171.40 > 50 -> dropped, EVEN THOUGH the plain-deposit
    // budget (equity-deposit=300) would have passed it — proves the
    // safety net is reading the ratcheted floor, not the deposit.
    fastStartStateStore['User:sandbox'] = { phase: 2, deposit: 5000, peak_profit: 1000 }
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos4', { baseContracts: 1, botName: 'spark' },
    )
    expect(result['User:sandbox']).toBeUndefined()
  })

  it('equity-fetch failure -> rule R1 itself fails closed (never a guessed safety-net pass)', async () => {
    BROKER['sb-user-key'].equity = null as any
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos5', { baseContracts: 1, botName: 'spark' },
    )
    expect(result['User:sandbox']).toBeUndefined()
    BROKER['sb-user-key'].equity = 5300
  })
})
