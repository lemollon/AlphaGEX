/**
 * ONE_STRATEGY end-to-end, mocked Tradier integration. Exercises the REAL
 * tradier.ts functions (placeIcOrderAllAccounts for EBB, placeCallSpreadOrderAllAccounts
 * for FLINT) against a mocked DB layer and a mocked Tradier HTTP layer (global
 * fetch), the same harness shape as flint-multi-account.test.ts, with
 * process.env.ONE_STRATEGY toggled on.
 *
 * Pins:
 *   1. Kill switch — ONE_STRATEGY unset/off is byte-for-byte the existing
 *      count-ladder behavior (this file's own control case).
 *   2. FLAME's production account ('Flame', standing in for 6YB71371) at a
 *      MOCKED ~$4,242 equity/deposit (no accumulated profit yet) sizes EBB
 *      through the shared module — one_strategy_floor_state gets seeded,
 *      and the resulting contract count differs from the old $1,500-rung
 *      ladder's count on the SAME inputs.
 *   3. An account whose equity has crossed the account's own deposit by
 *      enough to trip the profit-floor trigger still nets EBB + FLINT (the
 *      combined-cushion gap ONE_STRATEGY closes) — FLINT is not starved just
 *      because EBB's own sizing grew.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// tradier.ts caches its market-data quote API key from process.env.TRADIER_API_KEY
// at MODULE LOAD time (see tradier.ts's `_tradierApiKey` module-level `let`). ES
// module imports are evaluated before any ordinary top-level statement in THIS
// file, so a plain `process.env.TRADIER_API_KEY = ...` here would run too late —
// vi.hoisted() is the one thing Vitest guarantees runs before the (also hoisted)
// import of '../tradier' below.
vi.hoisted(() => {
  process.env.TRADIER_API_KEY = 'flame-live-key'
})

const mockDbQuery = vi.fn()
const mockDbExecute = vi.fn().mockResolvedValue(1)

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
  'ONE_STRATEGY', 'IRONFORGE_FLAME_LIVE', 'TRADIER_FLAME_API_KEY', 'TRADIER_FLAME_ACCOUNT_ID',
] as const

const ARMED = {
  IRONFORGE_FLAME_LIVE: 'true',
  TRADIER_FLAME_API_KEY: 'flame-live-key',
  TRADIER_FLAME_ACCOUNT_ID: 'FLAME-ENV-ACCT',
} as const

// Single-account harness: production 'Flame' only (standing in for 6YB71371).
// Both equity and option-buying-power reads resolve off this same figure —
// the mocked ~$4,242 the task asks for.
let flameEquity = 4242
let flameOneStrategyState: { deposit_cents: number; triggered: boolean; peak_equity_cents: number | null } | null = null
let ladderCapital = { starting: 4242, high_water_balance: 4242 }
let prodConfig = { bp_pct: 0.30, max_contracts: 0 }
let flintAlreadyToday = 0

function jsonResponse(body: any, ok = true) {
  return { ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'ERR', json: async () => body, text: async () => JSON.stringify(body) } as any
}

beforeEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  flameEquity = 4242
  flameOneStrategyState = null
  ladderCapital = { starting: 4242, high_water_balance: 4242 }
  prodConfig = { bp_pct: 0.30, max_contracts: 0 }
  flintAlreadyToday = 0

  mockDbQuery.mockReset()
  mockDbExecute.mockReset().mockResolvedValue(1)

  mockDbQuery.mockImplementation(async (sql: string, params: any[] = []) => {
    // ---- account resolution: only the 'Flame' production account exists here ----
    if (sql.includes('SELECT person, api_key, account_id, type FROM ironforge_accounts')) return []
    if (sql.includes('SELECT DISTINCT person, type FROM ironforge_accounts')) return []
    if (sql.includes('SELECT api_key, type FROM ironforge_accounts')) return []
    if (sql.includes('SELECT capital_pct FROM ironforge_accounts')) return []

    // ---- pause gates: nothing paused ----
    if (sql.includes('FROM ironforge_owner_pause')) return []
    if (sql.includes('FROM ironforge_production_pause')) return []

    // ---- production sizing config (loadProductionConfigFor -> {bot}_config) ----
    // An empty-but-present row is enough: loadProductionConfigFor merges onto
    // DEFAULT_CONFIG (flame's own bp_pct=0.20), and max_contracts is inert for
    // ladder bots (ADR 0013) either way.
    if (sql.includes('_config') && sql.includes("account_type = 'production'")) {
      return [{}]
    }

    // ---- FLINT's own dedup / collateral reads ----
    if (sql.includes('FROM flint_positions')) return [{ cnt: flintAlreadyToday }]
    if (sql.includes('FROM flame_positions')) return [{ m: 0 }]

    // ---- getProductionLadderCapital('flame', 'Flame') ----
    if (sql.includes('FROM flame_paper_account') && sql.includes("account_type = 'production'")) {
      return [{ starting_capital: ladderCapital.starting, high_water_balance: ladderCapital.high_water_balance }]
    }

    // ---- one_strategy_floor_state (this PR's new table) ----
    if (sql.includes('SELECT deposit_cents, triggered, peak_equity_cents FROM one_strategy_floor_state')) {
      return flameOneStrategyState ? [flameOneStrategyState] : []
    }

    return []
  })

  mockDbExecute.mockImplementation(async (sql: string, params: any[] = []) => {
    if (sql.includes('CREATE TABLE')) return 0
    if (sql.startsWith('INSERT INTO one_strategy_floor_state')) {
      if (!flameOneStrategyState) {
        flameOneStrategyState = { deposit_cents: Math.round(params[3]), triggered: false, peak_equity_cents: Math.round(params[3]) }
      }
      return 1
    }
    if (sql.startsWith('UPDATE one_strategy_floor_state')) {
      if (flameOneStrategyState) {
        flameOneStrategyState.triggered = flameOneStrategyState.triggered || Boolean(params[3])
        flameOneStrategyState.peak_equity_cents = Math.round(Number(params[4]))
      }
      return 1
    }
    return 1
  })

  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: any) => {
    if (url.includes('/user/profile')) return jsonResponse({ profile: { account: { account_number: 'FLAMEPROD1' } } })
    if (url.includes('/balances')) {
      return jsonResponse({ balances: { total_equity: String(flameEquity), margin: { option_buying_power: String(flameEquity) } } })
    }
    if (url.includes('/markets/quotes')) {
      // Deep book — liquidity never binds in these tests; the sizing math
      // under test is ONE_STRATEGY's, not the liquidity cap.
      return jsonResponse({ quotes: { quote: { bid: '0.50', ask: '0.55', last: '0.52', bidsize: 1000, asksize: 1000 } } })
    }
    if (url.includes('/orders') && init?.method === 'POST') return jsonResponse({ order: { id: 1, status: 'ok' } })
    if (url.includes('/orders/')) return jsonResponse({ order: { status: 'filled', avg_fill_price: '0.30' } })
    return jsonResponse({}, false)
  }))
})

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  vi.unstubAllGlobals()
})

import { placeIcOrderAllAccounts, placeCallSpreadOrderAllAccounts } from '../tradier'

// $5 put-spread width, $0.50 credit -> $450/contract collateral (matches
// FLAME's typical wing/credit shape closely enough for a sizing-mechanics test).
const EBB_ARGS = ['SPY', '2026-09-29', 400, 395, 0, 0, 1, 0.50] as const // put spread (2-leg): callShort/callLong=0

describe('ONE_STRATEGY kill switch — off is byte-for-byte the existing ladder', () => {
  it('off: production sizes via the $1,500-rung count ladder, not the shared module', async () => {
    Object.assign(process.env, ARMED) // ONE_STRATEGY left unset
    const result = await placeIcOrderAllAccounts(...EBB_ARGS, 'flame-ebb-off', 'flame', { productionOnly: true })
    // ladderContracts('flame', 4242) = floor(4242/1500) = 2, but at bp_pct=0.20
    // (flame's DEFAULT_CONFIG value) option BP only margins 1 ($848/$500) — the
    // OLD ladder path's own bp-cap step-down, unrelated to ONE_STRATEGY.
    expect(result['Flame:production']?.contracts).toBe(1)
    expect(flameOneStrategyState).toBeNull() // the new table was never touched
  })
})

describe('ONE_STRATEGY=on — production Flame at a mocked ~$4,242 equity', () => {
  it('EBB sizes through the shared module (20% of equity / collateral), seeding one_strategy_floor_state', async () => {
    Object.assign(process.env, ARMED)
    process.env.ONE_STRATEGY = 'on'
    const result = await placeIcOrderAllAccounts(...EBB_ARGS, 'flame-ebb-on', 'flame', { productionOnly: true })
    // desired = floor(4242*100 * 20/100 / 45000) = floor(84840/45000) = 1.
    expect(result['Flame:production']?.contracts).toBe(1)
    expect(flameOneStrategyState).toBeTruthy()
    expect(flameOneStrategyState?.deposit_cents).toBe(424_200)
    expect(flameOneStrategyState?.triggered).toBe(false) // no profit yet — never triggers at equity===deposit
  })

  it('FLINT nets to 0 at equity===deposit (no profit, profits-only) — never negative equity, never a bare fallback', async () => {
    Object.assign(process.env, ARMED)
    process.env.ONE_STRATEGY = 'on'
    const result = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-29', 405, 407, 1, 0.30, 'flame-flint-on-nogain', { botName: 'flame' },
    )
    expect(result['Flame:production']).toBeUndefined()
  })
})

describe('ONE_STRATEGY=on — combined-cushion gap: an account past the floor trigger still nets EBB + FLINT', () => {
  it('two-call sequence: day 1 seeds the floor at deposit; day 2 at higher equity triggers EBB AND clears FLINT the same day', async () => {
    Object.assign(process.env, ARMED)
    process.env.ONE_STRATEGY = 'on'

    // Day 1 — establishes the persisted floor row at the $4,242 baseline, no trigger.
    const day1 = await placeIcOrderAllAccounts(...EBB_ARGS, 'flame-ebb-day1', 'flame', { productionOnly: true })
    expect(day1['Flame:production']?.contracts).toBe(1)
    expect(flameOneStrategyState?.triggered).toBe(false)

    // Day 2 — equity has grown past $5,592 (3x the $170/contract*... trigger
    // reference at this deposit), clearing the profit-floor trigger.
    flameEquity = 5600

    // FLINT's entry ALWAYS runs before EBB's in the same scan tick (matches
    // production ordering — see tradier.ts's own doc comment on this).
    const flint = await placeCallSpreadOrderAllAccounts(
      'SPY', '2026-09-29', 405, 407, 1, 0.30, 'flame-flint-day2', { botName: 'flame' },
    )
    const ebb = await placeIcOrderAllAccounts(...EBB_ARGS, 'flame-ebb-day2', 'flame', { productionOnly: true })

    expect(ebb['Flame:production']?.contracts).toBeGreaterThan(0)
    expect(flameOneStrategyState?.triggered).toBe(true)
    // The headline assertion: FLINT is NOT starved by EBB's own (larger,
    // triggered) sizing on the SAME account, the same day — the netted
    // cushion check still finds room for both sleeves.
    expect(flint['Flame:production']?.contracts).toBe(1)
  })
})
