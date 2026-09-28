/**
 * one-strategy.ts — the shared sizing/decision module ONE_STRATEGY hands to
 * production and sandbox accounts.
 *
 *  1. Kill switch: isOneStrategyMode() defaults OFF.
 *  2. 100% day-row parity against `customer_protection_finalK.py`'s own fixture
 *     (the SAME fixture final-package-parity.test.ts already proves the
 *     app-customer path against, K=0.1/variant G/N=3) — evaluateOneStrategyHostSizing
 *     + evaluateOneStrategyFlint must reproduce n_host, n_flint, floor,
 *     triggered, and calm_applied on every day, all 4 cells (FLAME $2,000/
 *     $4,242 "production-like", SPARK $5,000/$7,500 "sandbox-like").
 *  3. Persistence (applyOneStrategyHostFloor / planOneStrategyHostContracts /
 *     decideOneStrategyFlintContracts) against a mocked ../db, proving the
 *     read-or-seed + ratchet-and-persist sequence for an INTERNAL account.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const mockDbQuery = vi.fn()
const mockDbExecute = vi.fn().mockResolvedValue(1)

interface StoredRow { deposit_cents: number; triggered: boolean; peak_equity_cents: number | null }
let store: Record<string, StoredRow> = {}

function key(person: string, accountType: string, botName: string): string {
  return `${person}:${accountType}:${botName}`
}

vi.mock('../db', () => ({
  query: (...args: any[]) => mockDbQuery(...args),
  dbExecute: (...args: any[]) => mockDbExecute(...args),
}))

beforeEach(() => {
  store = {}
  mockDbQuery.mockReset()
  mockDbExecute.mockReset().mockResolvedValue(1)

  mockDbQuery.mockImplementation(async (sql: string, params: any[] = []) => {
    if (sql.includes('CREATE TABLE')) return []
    if (sql.includes('SELECT deposit_cents, triggered, peak_equity_cents FROM one_strategy_floor_state')) {
      const k = key(params[0], params[1], params[2])
      return store[k] ? [store[k]] : []
    }
    return []
  })

  mockDbExecute.mockImplementation(async (sql: string, params: any[] = []) => {
    if (sql.includes('CREATE TABLE')) return 0
    if (sql.startsWith('INSERT INTO one_strategy_floor_state')) {
      const k = key(params[0], params[1], params[2])
      if (!store[k]) {
        store[k] = { deposit_cents: Math.round(params[3]), triggered: false, peak_equity_cents: Math.round(params[3]) }
      }
      return 1
    }
    if (sql.startsWith('UPDATE one_strategy_floor_state')) {
      const k = key(params[0], params[1], params[2])
      const row = store[k]
      if (row) {
        row.triggered = row.triggered || Boolean(params[3])
        row.peak_equity_cents = Math.round(Number(params[4]))
      }
      return 1
    }
    return 0
  })
})

import {
  isOneStrategyMode,
  evaluateOneStrategyHostSizing,
  evaluateOneStrategyFlint,
  decideOneStrategyFlintContracts,
  applyOneStrategyHostFloor,
  planOneStrategyHostContracts,
  currentFloorLevelCents,
  ONE_STRATEGY_MARGIN_CENTS,
  ONE_STRATEGY_FLOOR_K,
} from '../one-strategy'

describe('isOneStrategyMode — kill switch', () => {
  const cases: { v: string | undefined; expected: boolean }[] = [
    { v: undefined, expected: false },
    { v: '', expected: false },
    { v: 'off', expected: false },
    { v: 'true', expected: false },
    { v: '1', expected: false },
    { v: 'ON', expected: true }, // case-insensitive
    { v: 'On ', expected: true }, // trims whitespace
    { v: 'on', expected: true },
  ]
  for (const { v, expected } of cases) {
    it(`process.env.ONE_STRATEGY=${JSON.stringify(v)} -> ${expected}`, () => {
      const prev = process.env.ONE_STRATEGY
      if (v === undefined) delete process.env.ONE_STRATEGY
      else process.env.ONE_STRATEGY = v
      expect(isOneStrategyMode()).toBe(expected)
      if (prev === undefined) delete process.env.ONE_STRATEGY
      else process.env.ONE_STRATEGY = prev
    })
  }
})

// ---------------------------------------------------------------------------
// 100% day-row parity vs customer_protection_finalK.py's own fixture.
// ---------------------------------------------------------------------------
const VIX_CEILING = 0.70
const MIN_DEPOSIT_FOR_CALM_POST = 400_000

interface FixtureDay {
  day_index: number
  equity_cents: number
  deposit_cents: number
  ml_cents: number
  cand: boolean
  calm: boolean
  flint_cand: boolean
  flint_ml_cents: number
  n_host: number
  n_flint: number
  floor_cents: number
  triggered_after: boolean
  calm_applied: boolean
}

interface FixtureCell {
  deposit: number
  use_b1_pre: boolean
  use_calm_post: boolean
  days: FixtureDay[]
}

const fixturePath = join(__dirname, '..', 'customer-executor', '__tests__', 'fixtures', 'final-package-parity.json')
const fixture = JSON.parse(readFileSync(fixturePath, 'utf8')) as Record<string, FixtureCell>

describe('evaluateOneStrategyHostSizing + evaluateOneStrategyFlint — 100% day-row parity (ROUND 8, K=0.1/G)', () => {
  it('the fixture covers both bots at a production-like and a sandbox-like deposit', () => {
    expect(Object.keys(fixture)).toEqual(['FLAME_D2000', 'FLAME_D4242', 'SPARK_D5000', 'SPARK_D7500'])
  })

  for (const [label, cell] of Object.entries(fixture)) {
    // use_b1_pre is true on every cell in this fixture (B1 ships on all deposits/both
    // bots — contracts.ts's own doc comment). ONE_STRATEGY always evaluates B1
    // pre-trigger and calm-upsize post-trigger; a cell with use_calm_post=false
    // (FLAME $2,000) never reaches the post-trigger branch with deposit>=$4,000, so
    // evaluateCalmUpsize's own deposit gate makes it a no-op there — no special-casing
    // needed in the test.
    it(`${label}: n_host, n_flint, floor, and triggered match on every day`, () => {
      let triggered = false
      let peakEquityCents = cell.deposit * 100

      for (const day of cell.days) {
        // The caller's own peak-equity tracking (an EOD hook, or — for app
        // customers — the trade-time ratchet) runs every day, cand or not; see
        // applyOneStrategyHostFloor's own doc comment for why production/sandbox's
        // ACTUAL wiring only ratchets on host-candidate days (a documented,
        // conservative simplification) — this test proves the PURE decision
        // functions, not that wiring cadence.
        peakEquityCents = Math.max(peakEquityCents, day.equity_cents)

        let nHost = 0
        let calmApplied = false
        // Non-candidate-day default: the floor level is a pure function of
        // persisted (deposit, peak, triggered) state even when no sizing call
        // happens this day — matches final-package-parity.test.ts's own
        // top-of-loop default.
        let floorLevelCents = triggered ? currentFloorLevelCents(day.deposit_cents, peakEquityCents, true, ONE_STRATEGY_FLOOR_K) : day.deposit_cents

        if (day.cand) {
          const result = evaluateOneStrategyHostSizing({
            equityCents: day.equity_cents, depositCents: day.deposit_cents,
            maxLossCentsPerContract: day.ml_cents, vixRatio: day.calm ? 0.5 : 0.9,
            triggered, peakEquityCents,
          })
          nHost = result.contracts
          floorLevelCents = result.floorLevelCents
          calmApplied = result.fastStartApplied || result.calmUpsizeApplied
          triggered = triggered || result.triggeredNow
          peakEquityCents = result.nextPeakEquityCents
        }

        let nFlint = 0
        if (day.flint_cand && day.flint_ml_cents > 0) {
          const gate = evaluateOneStrategyFlint({
            equityCents: day.equity_cents, protectLevelCents: floorLevelCents,
            hostContracts: nHost, hostMaxLossCentsPerContract: day.ml_cents,
            flintMaxLossCents: day.flint_ml_cents,
          })
          nFlint = gate.eligible ? 1 : 0
        }

        const ctx = `${label} day_index=${day.day_index} cand=${day.cand} triggered=${triggered}`
        expect(nHost, `n_host mismatch: ${ctx}`).toBe(day.n_host)
        expect(nFlint, `n_flint mismatch: ${ctx}`).toBe(day.n_flint)
        expect(floorLevelCents, `floor mismatch: ${ctx}`).toBe(day.floor_cents)
        expect(calmApplied, `calm_applied mismatch: ${ctx}`).toBe(day.calm_applied)
        expect(triggered, `triggered mismatch: ${ctx}`).toBe(day.triggered_after)
      }
    })
  }
})

// ---------------------------------------------------------------------------
// decideOneStrategyFlintContracts — the two-candidate step-down.
// ---------------------------------------------------------------------------
describe('decideOneStrategyFlintContracts', () => {
  const flintMaxLossFn = (s: number, l: number, c: number, n: number) => (l - s - c) * 100 * n

  it('desired (2) covers the netted cushion -> trades 2', () => {
    const r = decideOneStrategyFlintContracts({
      desired: 2, base: 1, equityCents: 1_000_000, protectLevelCents: 400_000,
      hostContracts: 1, hostMaxLossCentsPerContract: 40_000,
      shortStrike: 400, longStrike: 402, credit: 0.5,
      flintMaxLossFn,
    })
    expect(r.contracts).toBe(2)
    expect(r.eligible).toBe(true)
  })

  it('desired (2) breaks cushion but base (1) clears it -> steps down to 1', () => {
    const r = decideOneStrategyFlintContracts({
      desired: 2, base: 1, equityCents: 460_000, protectLevelCents: 400_000,
      hostContracts: 1, hostMaxLossCentsPerContract: 40_000,
      shortStrike: 400, longStrike: 402, credit: 0.5,
      flintMaxLossFn,
    })
    // cushion after netting host: 460_000-400_000-40_000=20_000. FLINT@1=15_000+5_000margin=20_000 -> eligible.
    // FLINT@2=30_000+5_000=35_000 > 20_000 -> not eligible at 2.
    expect(r.contracts).toBe(1)
    expect(r.eligible).toBe(true)
  })

  it('neither candidate clears the cushion -> 0', () => {
    const r = decideOneStrategyFlintContracts({
      desired: 2, base: 1, equityCents: 400_000, protectLevelCents: 400_000,
      hostContracts: 1, hostMaxLossCentsPerContract: 40_000,
      shortStrike: 400, longStrike: 402, credit: 0.5,
      flintMaxLossFn,
    })
    expect(r.contracts).toBe(0)
    expect(r.eligible).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Persistence: applyOneStrategyHostFloor / planOneStrategyHostContracts
// against a mocked ../db, for an internal account.
// ---------------------------------------------------------------------------
describe('applyOneStrategyHostFloor — internal-account persistence', () => {
  it('first sight seeds the row at the given deposit and sizes plain BASE (no floor triggered)', async () => {
    const r = await applyOneStrategyHostFloor({
      person: 'Flame', accountType: 'production', botName: 'flame',
      depositCents: 424_200, equityCents: 424_200, maxLossCentsPerContract: 40_000, vixRatio: 0.9,
    })
    expect(r.dataOk).toBe(true)
    expect(r.triggeredForSizing).toBe(false)
    // desired = floor(424200*20/100/40000) = floor(2.121) = 2
    expect(r.contracts).toBe(2)
    expect(store['Flame:production:flame']).toBeTruthy()
  })

  it('ratchets peak-equity across two sequential calls and persists the trigger once it fires', async () => {
    const person = 'User'
    // Day 1: modest equity, not yet triggered.
    const r1 = await applyOneStrategyHostFloor({
      person, accountType: 'sandbox', botName: 'flame',
      depositCents: 200_000, equityCents: 210_000, maxLossCentsPerContract: 17_000, vixRatio: 0.9,
    })
    expect(r1.triggeredNow).toBe(false)

    // Day 2: equity clears 3x the trigger reference (dcountRef=2 @ $170/contract,
    // combined_ml=$340, N=3 -> needs cushion >= $1,020; $320,000-$200,000=$1,200 clears it).
    const r2 = await applyOneStrategyHostFloor({
      person, accountType: 'sandbox', botName: 'flame',
      depositCents: 200_000, equityCents: 320_000, maxLossCentsPerContract: 17_000, vixRatio: 0.9,
    })
    expect(r2.triggeredNow).toBe(true)
    expect(store['User:sandbox:flame'].triggered).toBe(true)
    expect(store['User:sandbox:flame'].peak_equity_cents).toBe(320_000)
  })

  it('unreadable equity fails closed: dataOk=false, contracts=0, no crash', async () => {
    const r = await applyOneStrategyHostFloor({
      person: 'Matt', accountType: 'sandbox', botName: 'spark',
      depositCents: 500_000, equityCents: null, maxLossCentsPerContract: 40_000, vixRatio: null,
    })
    expect(r.dataOk).toBe(false)
    expect(r.contracts).toBe(0)
  })
})

describe('planOneStrategyHostContracts — FLINT\'s read-only planning read', () => {
  it('never mutates persisted state (a second real call still sees the ORIGINAL seed, not the plan\'s equity)', async () => {
    const person = 'Logan'
    const planned = await planOneStrategyHostContracts({
      person, accountType: 'sandbox', botName: 'flame',
      depositCents: 200_000, equityCents: 900_000, maxLossCentsPerContract: 19_000, vixRatio: null,
    })
    expect(planned).not.toBeNull()
    // The plan read seeded the row (first sight) but must NOT have written
    // peak_equity_cents=900_000 — only applyOneStrategyHostFloor may ratchet.
    expect(store['Logan:sandbox:flame'].peak_equity_cents).toBe(200_000)

    const real = await applyOneStrategyHostFloor({
      person, accountType: 'sandbox', botName: 'flame',
      depositCents: 200_000, equityCents: 205_000, maxLossCentsPerContract: 19_000, vixRatio: null,
    })
    expect(real.dataOk).toBe(true)
    // The real call ratchets from the ORIGINAL 200_000 seed, not the plan's 900_000.
    expect(real.nextPeakEquityCents).toBe(205_000)
  })

  it('returns null (never fabricates a plan) on a DB read failure', async () => {
    mockDbQuery.mockRejectedValueOnce(new Error('connection reset'))
    const planned = await planOneStrategyHostContracts({
      person: 'Broken', accountType: 'production', botName: 'flame',
      depositCents: 400_000, equityCents: 400_000, maxLossCentsPerContract: 40_000, vixRatio: null,
    })
    expect(planned).toBeNull()
  })
})

describe('ONE_STRATEGY_MARGIN_CENTS', () => {
  it('is $50, matching the sim\'s MARGIN constant', () => {
    expect(ONE_STRATEGY_MARGIN_CENTS).toBe(5_000)
  })
})
