/**
 * PARITY TEST — the key test (per task spec: "do not skip it").
 *
 * Fixture: fixtures/fast-start-parity.json, built by merging the verified
 * day-by-day trace from `dev/meltup/fast_start_floor_sim.py` (the exact
 * simulation engine behind RESULT_profit_floor_cppi.md's round 4/5 numbers,
 * confirmed to reproduce that published held-out table) with the raw
 * per-day EBB/FLINT candidacy + max-loss columns from
 * `ebb_flint_daily_pnl.parquet` (the sim's own input data). 4 real account
 * paths (main + 3 random 1-year starts) at EACH of $2,000 and $4,242 —
 * 8 paths, 3,358 day-rows total.
 *
 * For every day, this feeds decideFastStartSizing() the SAME inputs the
 * Python sim used (ladder count, candidacy, max-loss, equity, peak_profit)
 * and asserts the TypeScript port reproduces, EXACTLY:
 *   - phase (1 or 2, sticky)
 *   - ebb_contracts
 *   - flint_contracts
 *   - floor
 * Phase is threaded day-to-day exactly like a real caller would persist it
 * (yesterday's returned nextState.phase feeds today's call).
 */
import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { decideFastStartSizing, seedFastStartState, type FastStartAccountState } from '../fast-start-sizing'

interface FixtureRow {
  date: string
  equity: number
  deposit: number
  peak_profit: number
  phase: number
  trigger: number
  floor: number
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
  readFileSync(join(__dirname, 'fixtures', 'fast-start-parity.json'), 'utf-8'),
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

    const ok =
      decision.phase === row.phase &&
      decision.ebbContracts === row.ebb_contracts &&
      decision.flintContracts === row.flint_contracts &&
      decision.floor !== null &&
      // fixture rounds floor to 2dp (Python round()) when it dumps the JSON
      // trace; ours keeps full precision. Compare within half a cent plus a
      // hair of float-representation slack (0.006, not 0.005) so a value
      // that lands exactly on a .xx5 boundary can't flip either side's
      // rounding direction and register as a false mismatch.
      Math.abs((decision.floor as number) - row.floor) <= 0.006

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

describe('fast-start parity vs the real sim (fast_start_floor_sim.py)', () => {
  afterEach(() => {
    if (ORIG_ENV === undefined) delete process.env.FLAME_FAST_START
    else process.env.FLAME_FAST_START = ORIG_ENV
  })

  it('sanity: fixture is the frozen rule (2x/X20/N8/K25/G)', () => {
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

  it('covers at least 3 real account paths', () => {
    expect(allPathNames.length).toBeGreaterThanOrEqual(3)
  })

  for (const depKey of Object.keys(fixture.paths)) {
    for (const pathName of Object.keys(fixture.paths[depKey])) {
      it(`${depKey}/${pathName}: every day matches (phase, ebb_contracts, flint_contracts, floor)`, () => {
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
    console.log(`PARITY RESULT: ${totalMatched}/${totalDays} days matched across ${allPathNames.length} paths`)
    if (allMismatches.length > 0) {
      console.error(`First mismatches:\n${allMismatches.slice(0, 20).join('\n')}`)
    }
    expect(totalMatched).toBe(totalDays)
  })
})
