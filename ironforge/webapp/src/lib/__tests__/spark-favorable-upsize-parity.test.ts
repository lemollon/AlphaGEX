/**
 * PARITY TEST — SPARK_FAVORABLE_UPSIZE vs the real sim (spark_addons_sim.py,
 * the ONE passing arm from RESULT_spark_addons.md: favorable-day (VIX
 * ratio<=0.70) +1 upsize at the $5,000 deposit).
 *
 * Fixture: fixtures/spark-favorable-upsize-parity.json, built by merging the
 * verified day-by-day trace from `dev/meltup/spark_addons_sim.py` with the
 * raw per-day SPARK candidacy + max-loss columns (spark_daily_pnl.parquet)
 * and the VIX-ratio favorable-day flag (recomputed identically to
 * `spark_addons_sim.load_favorable`). 1 deposit ($5,000 — the only deposit
 * that passed) x 4 real account paths (main + 3 random 1-year starts) =
 * 4 paths, 1,730 day-rows total.
 *
 * For every day: (1) SPARK's own fast-start decision must reproduce
 * `spark_n_total - (upsize?1:0)` exactly (re-verifies fast-start-sizing.ts
 * on this SAME fixture, independent of spark-fast-start-parity.test.ts's
 * own fixture); (2) decideSparkFavorableUpsize, fed that SAME decision plus
 * this day's favorable flag, must reproduce the fixture's `upsize` boolean
 * exactly.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { decideFastStartSizing, seedFastStartState, FAST_START_K, type FastStartAccountState } from '../fast-start-sizing'
import { decideSparkFavorableUpsize } from '../spark-favorable-upsize'

interface FixtureRow {
  date: string
  equity: number
  deposit: number
  phase: number
  floor: number
  ladder_count: number
  spark_n_total: number
  upsize: boolean
  pnl: number
  spark_candidate_day: boolean
  spark_maxloss_per_contract: number | null
  favorable: boolean
}

interface Fixture {
  rule: string
  deposit: number
  paths: Record<string, FixtureRow[]>
}

const fixture: Fixture = JSON.parse(
  readFileSync(join(__dirname, 'fixtures', 'spark-favorable-upsize-parity.json'), 'utf-8'),
)

const ORIG_FAST_START = process.env.SPARK_FAST_START
const LADDER_CAP = 100 // EBB_LADDER_CAP (ebb-sizing.ts) — pinned here to avoid a cross-module import in a pure-math test

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

    const expectedBase = row.spark_n_total - (row.upsize ? 1 : 0)
    const baseOk = decision.ebbContracts === expectedBase && decision.phase === row.phase

    const upsize = decideSparkFavorableUpsize({
      decision,
      deposit: row.deposit,
      sparkCandidateDay: row.spark_candidate_day,
      sparkMaxLossPerContract: row.spark_maxloss_per_contract,
      favorable: row.favorable,
      ladderCap: LADDER_CAP,
    })
    const upsizeOk = (upsize.upsizeContracts === 1) === row.upsize

    if (baseOk && upsizeOk) {
      matched += 1
    } else {
      mismatches.push(
        `${row.date}: expected base=${expectedBase} upsize=${row.upsize} phase=${row.phase} ` +
          `got base=${decision.ebbContracts} phase=${decision.phase} upsize=${upsize.upsizeContracts === 1} (${upsize.reason})`,
      )
    }
    state = nextState
  }
  return { matched, total: rows.length, mismatches }
}

describe('SPARK favorable-upsize parity vs the real sim (spark_addons_sim.py, $5,000 passing arm)', () => {
  afterEach(() => {
    if (ORIG_FAST_START === undefined) delete process.env.SPARK_FAST_START
    else process.env.SPARK_FAST_START = ORIG_FAST_START
  })

  it('sanity: fixture is the passing arm (deposit $5,000)', () => {
    expect(fixture.deposit).toBe(5000)
    expect(fixture.rule).toContain('upsize')
  })

  it('covers 4 real account paths', () => {
    expect(Object.keys(fixture.paths).length).toBe(4)
  })

  for (const pathName of Object.keys(fixture.paths)) {
    it(`${pathName}: every day matches (base contracts + upsize flag)`, () => {
      process.env.SPARK_FAST_START = 'on'
      const { matched, total, mismatches } = runPath(fixture.paths[pathName])
      if (mismatches.length > 0) {
        console.error(`${pathName}: ${matched}/${total} matched. First mismatches:\n${mismatches.slice(0, 10).join('\n')}`)
      }
      expect(matched).toBe(total)
    })
  }

  it('TOTAL across all fixture paths: reports days matched / total', () => {
    process.env.SPARK_FAST_START = 'on'
    let totalMatched = 0
    let totalDays = 0
    const allMismatches: string[] = []
    for (const pathName of Object.keys(fixture.paths)) {
      const { matched, total, mismatches } = runPath(fixture.paths[pathName])
      totalMatched += matched
      totalDays += total
      allMismatches.push(...mismatches)
    }
    console.log(`SPARK UPSIZE PARITY: ${totalMatched}/${totalDays} days matched across ${Object.keys(fixture.paths).length} paths`)
    if (allMismatches.length > 0) {
      console.error(`First mismatches:\n${allMismatches.slice(0, 20).join('\n')}`)
    }
    expect(totalMatched).toBe(totalDays)
  })
})
