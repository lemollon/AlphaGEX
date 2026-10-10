/**
 * PARITY TEST — SPARK_FAST_START vs the real sim (spark_fast_start_floor_sim.py).
 *
 * Fixture: fixtures/spark-fast-start-parity.json, built by merging the
 * verified day-by-day trace from `dev/meltup/spark_fast_start_floor_sim.py`
 * (the FROZEN 2x/X=20%/N=8/K=0.25/G engine behind RESULT_spark_fast_start.md)
 * with the raw per-day SPARK candidacy + max-loss columns from
 * `spark_daily_pnl.parquet` (the sim's own input data) — same construction
 * as FLAME's fast-start-parity.json, generalized to SPARK's single-leg
 * structure (no FLINT term; flintCandidateDay is always false here — SPARK's
 * FLINT is a SEPARATE, independent budget, see spark-flint-separate.test.ts).
 * 3 deposits ($5,000/$7,500/$10,000) x 4 real account paths each (main + 3
 * random 1-year starts) = 12 paths, 5,190 day-rows total.
 *
 * For every day, this feeds decideFastStartSizing() the SAME inputs the
 * Python sim used (ladder count, candidacy, max-loss, equity) with
 * `{envVar: 'SPARK_FAST_START'}` and asserts the TypeScript port
 * reproduces, EXACTLY: phase (1 or 2, sticky), ebb_contracts, floor. Phase
 * is threaded day-to-day exactly like a real caller would persist it.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  decideFastStartSizing,
  seedFastStartState,
  FAST_START_K,
  type FastStartAccountState,
} from '../fast-start-sizing'

interface FixtureRow {
  date: string
  equity: number
  deposit: number
  phase: number
  floor: number
  ladder_count: number
  ebb_contracts: number
  pnl: number
  ebb_candidate_day: boolean
  ebb_maxloss_per_lot: number | null
}

interface Fixture {
  rule: string
  paths: Record<string, Record<string, FixtureRow[]>>
}

const fixture: Fixture = JSON.parse(
  readFileSync(join(__dirname, 'fixtures', 'spark-fast-start-parity.json'), 'utf-8'),
)

const ORIG_ENV = process.env.SPARK_FAST_START

function runPath(rows: FixtureRow[]) {
  let state: FastStartAccountState = seedFastStartState(rows[0].deposit)
  let matched = 0
  const mismatches: string[] = []

  for (const row of rows) {
    // (floor - deposit) / K reproduces peak_profit exactly: floor stays ==
    // deposit throughout Phase 1 (peak_profit unused there), and floor ==
    // deposit + K*peak_profit throughout Phase 2 by construction.
    const peakProfit = (row.floor - row.deposit) / FAST_START_K

    const { decision, nextState } = decideFastStartSizing(
      state,
      {
        ebbCandidateDay: row.ebb_candidate_day,
        flintCandidateDay: false,
        ebbMaxLossPerLot: row.ebb_maxloss_per_lot,
        flintMaxLossPerContract: null,
        normalEbbLadder: row.ladder_count,
        equity: row.equity,
        peakProfit,
      },
      { envVar: 'SPARK_FAST_START' },
    )

    const ok =
      decision.phase === row.phase &&
      decision.ebbContracts === row.ebb_contracts &&
      decision.floor !== null &&
      Math.abs((decision.floor as number) - row.floor) <= 0.006

    if (ok) {
      matched += 1
    } else {
      mismatches.push(
        `${row.date}: expected phase=${row.phase} ebb=${row.ebb_contracts} floor=${row.floor} ` +
          `got phase=${decision.phase} ebb=${decision.ebbContracts} floor=${decision.floor}`,
      )
    }
    state = nextState
  }
  return { matched, total: rows.length, mismatches }
}

describe('SPARK fast-start parity vs the real sim (spark_fast_start_floor_sim.py)', () => {
  afterEach(() => {
    if (ORIG_ENV === undefined) delete process.env.SPARK_FAST_START
    else process.env.SPARK_FAST_START = ORIG_ENV
  })

  it('sanity: fixture is the frozen rule (2x/X=20/N=8/K=0.25/G)', () => {
    expect(fixture.rule).toContain('X=20%')
    expect(fixture.rule).toContain('N=8')
    expect(fixture.rule).toContain('K=0.25')
  })

  const allPathNames: string[] = []
  for (const depKey of Object.keys(fixture.paths)) {
    for (const pathName of Object.keys(fixture.paths[depKey])) {
      allPathNames.push(`${depKey}/${pathName}`)
    }
  }

  it('covers all 3 deposits x 4 real account paths', () => {
    expect(allPathNames.length).toBe(12)
  })

  for (const depKey of Object.keys(fixture.paths)) {
    for (const pathName of Object.keys(fixture.paths[depKey])) {
      it(`${depKey}/${pathName}: every day matches (phase, ebb_contracts, floor)`, () => {
        process.env.SPARK_FAST_START = 'on'
        const rows = fixture.paths[depKey][pathName]
        const { matched, total, mismatches } = runPath(rows)
        if (mismatches.length > 0) {
          console.error(
            `${depKey}/${pathName}: ${matched}/${total} matched. First mismatches:\n` +
              mismatches.slice(0, 10).join('\n'),
          )
        }
        expect(matched).toBe(total)
      })
    }
  }

  it('TOTAL across all fixture paths: reports days matched / total', () => {
    process.env.SPARK_FAST_START = 'on'
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
    console.log(`SPARK FAST-START PARITY: ${totalMatched}/${totalDays} days matched across ${allPathNames.length} paths`)
    if (allMismatches.length > 0) {
      console.error(`First mismatches:\n${allMismatches.slice(0, 20).join('\n')}`)
    }
    expect(totalMatched).toBe(totalDays)
  })
})
