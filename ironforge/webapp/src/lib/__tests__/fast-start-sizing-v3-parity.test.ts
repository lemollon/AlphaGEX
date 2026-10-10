/**
 * PARITY TEST — FLAME fast-start v3 (guarded P&L re-validation): $50/leg
 * margin in the Phase-2 budget checks ONLY, deposit_cap.
 *
 * Fixture: fixtures/fast-start-parity-v3.json, built by merging the v3
 * day-by-day trace from `dev/meltup/fast_start_floor_sim.py` (FROZEN_V3:
 * 2x/X20%/N8/K25/G/margin=$50-per-leg-in-Phase-2-only/deposit_cap=$7,500)
 * with the raw per-day EBB/FLINT candidacy + max-loss columns from
 * `ebb_flint_guarded_pnl.parquet` — the GUARDED (real guard-fire slippage
 * included) P&L file v3 was re-validated against. 3 deposits ($2,000 /
 * $4,242 / $7,500) x 4 paths each (main + 3 random 1-year starts) = 12
 * paths, ~5,190 day-rows.
 *
 * The fixture's own deposit_cap is $7,500 (so its D7500 path exercises the
 * cap directly — every D7500 row is `phase: "BASE"`), but MY implementation
 * uses FAST_START_DEPOSIT_CAP=$5,000 per the explicit 2026-09-29 decision
 * (v3 lost to BASE at $5k/$6k in a later, non-fixtured sweep) — this is a
 * STRICTER cap than the fixture's own $7,500, so it never disagrees with
 * this fixture: every path here is either <$5,000 (fast-start active, same
 * as under a $7,500 cap) or =$7,500 (capped under EITHER threshold). No
 * $5,000-$7,499 path exists in this fixture, so this difference is
 * dedicated-unit-tested separately (fast-start-sizing.test.ts), not provable
 * from this fixture alone.
 *
 * For every day, this feeds decideFastStartSizing() the fixture's own
 * ladder_count/equity/peak_profit and the parquet's candidacy/max-loss, and
 * asserts EXACT ebb_contracts/flint_contracts on every row. `floor` is only
 * asserted on phase-1/2 rows (BASE rows have floor=null in the fixture).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { decideFastStartSizing, seedFastStartState, type FastStartAccountState } from '../fast-start-sizing'

interface FixtureRow {
  date: string
  equity: number
  deposit: number
  peak_profit: number
  phase: number | 'BASE'
  trigger: number | null
  floor: number | null
  ladder_count: number
  ebb_contracts: number
  flint_contracts: number
  combined_maxloss: number
  pnl: number
  ebb_candidate_day: boolean
  flint_candidate_day: boolean
  ebb_maxloss_per_lot: number | null
  flint_maxloss_per_contract: number | null
}

interface Fixture {
  rule: string
  paths: Record<string, Record<string, FixtureRow[]>>
}

const fixture: Fixture = JSON.parse(
  readFileSync(join(__dirname, 'fixtures', 'fast-start-parity-v3.json'), 'utf-8'),
)

const ORIG_ENV = process.env.FLAME_FAST_START

function runPath(rows: FixtureRow[]) {
  let state: FastStartAccountState = seedFastStartState(rows[0].deposit)
  let matched = 0
  const mismatches: string[] = []

  for (const row of rows) {
    const { decision, nextState } = decideFastStartSizing(state, {
      ebbCandidateDay: row.ebb_candidate_day,
      flintCandidateDay: row.flint_candidate_day,
      ebbMaxLossPerLot: row.ebb_maxloss_per_lot,
      flintMaxLossPerContract: row.flint_maxloss_per_contract,
      normalEbbLadder: row.ladder_count,
      equity: row.equity,
      peakProfit: row.peak_profit,
    })

    const isBaseRow = row.phase === 'BASE'
    let ok = decision.ebbContracts === row.ebb_contracts && decision.flintContracts === row.flint_contracts
    if (!isBaseRow) {
      ok = ok && decision.phase === row.phase && decision.floor !== null &&
        Math.abs((decision.floor as number) - (row.floor as number)) <= 0.006
    }

    if (ok) {
      matched += 1
    } else {
      mismatches.push(
        `${row.date}: expected phase=${row.phase} ebb=${row.ebb_contracts} flint=${row.flint_contracts} floor=${row.floor} ` +
          `got phase=${decision.phase} ebb=${decision.ebbContracts} flint=${decision.flintContracts} floor=${decision.floor}`,
      )
    }
    state = nextState
  }
  return { matched, total: rows.length, mismatches }
}

describe('fast-start v3 parity vs the guarded-P&L sim (fast_start_floor_sim.py FROZEN_V3)', () => {
  it('sanity: fixture is the v3 rule (margin in Phase-2 budget only, deposit_cap)', () => {
    expect(fixture.rule).toContain('margin=$50 per leg in Phase-2 budget ONLY')
    expect(fixture.rule).toContain('deposit_cap')
  })

  const allPathNames: string[] = []
  for (const depKey of Object.keys(fixture.paths)) {
    for (const pathName of Object.keys(fixture.paths[depKey])) {
      allPathNames.push(`${depKey}/${pathName}`)
    }
  }

  it('covers all 3 deposits ($2,000 / $4,242 / $7,500), at least 3 paths each', () => {
    expect(Object.keys(fixture.paths).sort()).toEqual(['D2000', 'D4242', 'D7500'])
    for (const depKey of Object.keys(fixture.paths)) {
      expect(Object.keys(fixture.paths[depKey]).length).toBeGreaterThanOrEqual(3)
    }
  })

  for (const depKey of Object.keys(fixture.paths)) {
    for (const pathName of Object.keys(fixture.paths[depKey])) {
      it(`${depKey}/${pathName}: every day matches (ebb_contracts, flint_contracts, phase, floor)`, () => {
        process.env.FLAME_FAST_START = 'on'
        const rows = fixture.paths[depKey][pathName]
        const { matched, total, mismatches } = runPath(rows)
        if (mismatches.length > 0) {
          console.error(
            `${depKey}/${pathName}: ${matched}/${total} matched. First mismatches:\n` +
              mismatches.slice(0, 10).join('\n'),
          )
        }
        expect(matched).toBe(total)
        if (ORIG_ENV === undefined) delete process.env.FLAME_FAST_START
        else process.env.FLAME_FAST_START = ORIG_ENV
      })
    }
  }

  it('TOTAL across all fixture paths: reports days matched / total', () => {
    process.env.FLAME_FAST_START = 'on'
    let totalMatched = 0
    let totalDays = 0
    const allMismatches: string[] = []
    for (const depKey of Object.keys(fixture.paths)) {
      for (const pathName of Object.keys(fixture.paths[depKey])) {
        const { matched, total, mismatches } = runPath(fixture.paths[depKey][pathName])
        totalMatched += matched
        totalDays += total
        allMismatches.push(...mismatches)
      }
    }
    console.log(`V3 PARITY RESULT: ${totalMatched}/${totalDays} days matched across ${allPathNames.length} paths`)
    if (allMismatches.length > 0) {
      console.error(`First mismatches:\n${allMismatches.slice(0, 20).join('\n')}`)
    }
    expect(totalMatched).toBe(totalDays)
    if (ORIG_ENV === undefined) delete process.env.FLAME_FAST_START
    else process.env.FLAME_FAST_START = ORIG_ENV
  })
})
