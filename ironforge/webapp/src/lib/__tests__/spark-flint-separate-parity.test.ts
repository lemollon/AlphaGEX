/**
 * PARITY TEST — SPARK_FLINT (separate budget) vs the real sim
 * (spark_flint_separate_sim.py, variant (a) — the shipped variant per
 * RESULT_spark_flint_separate.md: fixed 1 lot, profits-only, floor-safety-
 * drops-FLINT-first, PASSES at all 3 deposits).
 *
 * Fixture: fixtures/spark-flint-separate-parity.json, built by merging the
 * verified day-by-day trace from `dev/meltup/spark_flint_separate_sim.py`
 * with the raw per-day SPARK + FLINT candidacy/max-loss columns
 * (spark_daily_pnl.parquet, ebb_flint_daily_pnl.parquet) and the VIX-ratio
 * favorable-day flag. The sim's own baseline already includes the
 * favorable-upsize below $7,500 (RESULT_spark_addons.md's own settled
 * boundary) — so this test exercises fast-start + upsize + FLINT together,
 * end to end. 3 deposits x 4 real account paths = 12 paths, 5,190 day-rows.
 *
 * For every day: (1) reproduce spark_n_total (fast-start base + upsize when
 * deposit < $7,500) exactly; (2) feed decideSparkFlintContracts SPARK's own
 * floor + today's already-sized SPARK contracts and reproduce flint_n
 * exactly (0 or 1) — including the floor-safety-net drop.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { decideFastStartSizing, seedFastStartState, FAST_START_K, type FastStartAccountState } from '../fast-start-sizing'
import { decideSparkFavorableUpsize, isSparkUpsizeEligibleDeposit } from '../spark-favorable-upsize'
import { decideSparkFlintContracts } from '../spark-flint-separate'

interface FixtureRow {
  date: string
  equity: number
  deposit: number
  phase: number
  floor: number
  ladder_count: number
  spark_n_total: number
  flint_n: number
  pnl: number
  spark_candidate_day: boolean
  spark_maxloss_per_contract: number | null
  flint_candidate_day: boolean
  flint_maxloss_per_contract: number | null
  favorable: boolean
}

interface Fixture {
  rule: string
  paths: Record<string, Record<string, FixtureRow[]>>
}

const fixture: Fixture = JSON.parse(
  readFileSync(join(__dirname, 'fixtures', 'spark-flint-separate-parity.json'), 'utf-8'),
)

const ORIG_FAST_START = process.env.SPARK_FAST_START
const LADDER_CAP = 100

function runPath(rows: FixtureRow[]) {
  let state: FastStartAccountState = seedFastStartState(rows[0].deposit)
  let matched = 0
  const mismatches: string[] = []

  for (const row of rows) {
    const peakProfit = (row.floor - row.deposit) / FAST_START_K
    const { decision, nextState } = decideFastStartSizing(
      state,
      {
        ebbCandidateDay: row.spark_candidate_day,
        flintCandidateDay: false,
        ebbMaxLossPerLot: row.spark_maxloss_per_contract,
        flintMaxLossPerContract: null,
        normalEbbLadder: row.ladder_count,
        equity: row.equity,
        peakProfit,
      },
      { envVar: 'SPARK_FAST_START' },
    )

    let sparkTotal = decision.ebbContracts
    if (isSparkUpsizeEligibleDeposit(row.deposit)) {
      const upsize = decideSparkFavorableUpsize({
        decision,
        deposit: row.deposit,
        sparkCandidateDay: row.spark_candidate_day,
        sparkMaxLossPerContract: row.spark_maxloss_per_contract,
        favorable: row.favorable,
        ladderCap: LADDER_CAP,
      })
      sparkTotal += upsize.upsizeContracts
    }

    const flint = decideSparkFlintContracts({
      equity: row.equity,
      deposit: row.deposit,
      sparkFloor: decision.floor ?? row.deposit,
      flintCandidateDay: row.flint_candidate_day,
      flintMaxLossPerContract: row.flint_maxloss_per_contract,
      sparkContractsToday: sparkTotal,
      sparkMaxLossPerContract: row.spark_maxloss_per_contract,
    })

    const ok =
      decision.phase === row.phase &&
      sparkTotal === row.spark_n_total &&
      flint.flintContracts === row.flint_n

    if (ok) {
      matched += 1
    } else {
      mismatches.push(
        `${row.date}: expected phase=${row.phase} spark=${row.spark_n_total} flint=${row.flint_n} ` +
          `got phase=${decision.phase} spark=${sparkTotal} flint=${flint.flintContracts} (${flint.reason})`,
      )
    }
    state = nextState
  }
  return { matched, total: rows.length, mismatches }
}

describe('SPARK FLINT-separate-budget parity vs the real sim (spark_flint_separate_sim.py, variant a)', () => {
  afterEach(() => {
    if (ORIG_FAST_START === undefined) delete process.env.SPARK_FAST_START
    else process.env.SPARK_FAST_START = ORIG_FAST_START
  })

  it('sanity: fixture is variant (a)', () => {
    expect(fixture.rule).toContain('variant (a)')
    expect(fixture.rule).toContain('floor safety net')
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
      it(`${depKey}/${pathName}: every day matches (spark contracts + flint contracts)`, () => {
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
    console.log(`SPARK FLINT-SEPARATE PARITY: ${totalMatched}/${totalDays} days matched across ${allPathNames.length} paths`)
    if (allMismatches.length > 0) {
      console.error(`First mismatches:\n${allMismatches.slice(0, 20).join('\n')}`)
    }
    expect(totalMatched).toBe(totalDays)
  })
})
