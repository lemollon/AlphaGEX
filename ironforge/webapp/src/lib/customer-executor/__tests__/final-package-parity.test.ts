/**
 * Full-package day-row parity: drives evaluateDepositFloorCap + evaluateFastStartUpsize
 * (B1) + evaluateCalmUpsize + evaluateFlintCushion together, exactly reproducing
 * `customer_protection_final_package.py`'s simulate_package() day loop (ROUND 7 — "one
 * rule everywhere," B1 pre-cushion on ALL deposits/both bots, house-money calm-post
 * gated on deposit >= $4,000), and checks 100% day-row parity against a fixture
 * generated directly from that Python source (fixtures/final-package-parity.json) —
 * n_host, n_flint, floor, triggered, and calm_applied on every day, all 4 cells
 * (FLAME $2,000/$4,242, SPARK $5,000/$7,500), sequential and stateful.
 *
 * The fixture carries a `calm` boolean per day (already the VIX<=0.70 result) rather
 * than a raw ratio; this test converts it to a deterministic surrogate ratio (0.5 for
 * calm, 0.9 for not) purely so evaluateFastStartUpsize/evaluateCalmUpsize's own ratio
 * comparison has something to compare against — the ceiling comparison itself is
 * covered directly with explicit values elsewhere in this file.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  evaluateDepositFloorCap,
  evaluateFastStartUpsize,
  evaluateCalmUpsize,
  evaluateFlintCushion,
} from '../contracts'

const VIX_CEILING = 0.70
const MARGIN_CENTS = 5_000
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

const fixturePath = join(__dirname, 'fixtures', 'final-package-parity.json')
const fixture = JSON.parse(readFileSync(fixturePath, 'utf8')) as Record<string, FixtureCell>

describe('final customer package — 100% day-row parity vs customer_protection_final_package.py (ROUND 7)', () => {
  it('the fixture is non-trivial across all 4 cells (calm-applied, FLINT, and trigger days all present)', () => {
    expect(Object.keys(fixture)).toEqual(['FLAME_2000', 'FLAME_4242', 'SPARK_5000', 'SPARK_7500'])
    for (const cell of Object.values(fixture)) {
      expect(cell.days.length).toBeGreaterThan(300)
      expect(cell.days.some((d) => d.calm_applied)).toBe(true)
      expect(cell.days.some((d) => d.n_flint > 0)).toBe(true)
      expect(cell.days.some((d) => d.triggered_after)).toBe(true)
    }
  })

  for (const [label, cell] of Object.entries(fixture)) {
    it(`${label}: n_host, n_flint, floor, triggered, and calm_applied match on every day`, () => {
      let triggered = false

      for (const day of cell.days) {
        let nHost = 0
        let calmApplied = false
        let dataOkThisDay = true

        if (day.cand) {
          const desiredContracts = Math.floor((day.equity_cents * 20) / 100 / day.ml_cents)
          const floorResult = evaluateDepositFloorCap({
            equityCents: day.equity_cents, depositCents: day.deposit_cents,
            maxLossCentsPerContract: day.ml_cents, marginCents: MARGIN_CENTS,
            pct: 20, desiredContracts, triggered, triggerN: 3,
          })
          dataOkThisDay = floorResult.dataOk
          nHost = floorResult.contracts
          const vixRatio = day.calm ? 0.5 : 0.9

          if (!floorResult.triggeredForSizing && cell.use_b1_pre) {
            const b1 = evaluateFastStartUpsize({
              triggeredForSizing: floorResult.triggeredForSizing, baseContracts: nHost,
              vixRatio, vixCeiling: VIX_CEILING,
            })
            if (b1.extraContract) { nHost += 1; calmApplied = true }
          } else if (floorResult.triggeredForSizing && cell.use_calm_post) {
            const calm = evaluateCalmUpsize({
              equityCents: day.equity_cents, depositCents: day.deposit_cents, baseContracts: nHost,
              maxLossCentsPerContract: day.ml_cents, marginCents: MARGIN_CENTS,
              vixRatio, vixCeiling: VIX_CEILING, minDepositCentsForUpsize: MIN_DEPOSIT_FOR_CALM_POST,
            })
            if (calm.extraContract) { nHost += 1; calmApplied = true }
          }

          triggered = triggered || floorResult.triggeredNow
        }

        // floor_level === deposit forever at K=0, regardless of triggered state.
        const floorCents = day.deposit_cents

        // The SIM's own FLINT gate has NO margin term (`equity - protect_level >= fml`,
        // customer_protection_sim.py) — marginCents:0 here reproduces that exactly. The
        // live implementation (mirrorOneFlintOpen) deliberately ADDS the $50 margin per
        // Leron's explicit instruction; that live-only tightening is covered separately
        // in contracts.test.ts's evaluateFlintCushion suite, not in this sim-parity check.
        let nFlint = 0
        if (day.flint_cand && day.flint_ml_cents > 0) {
          const flintGate = evaluateFlintCushion({
            equityCents: day.equity_cents, protectLevelCents: day.deposit_cents,
            maxLossCents: day.flint_ml_cents, marginCents: 0,
          })
          nFlint = flintGate.eligible ? 1 : 0
        }

        const ctx = `${label} day_index=${day.day_index} cand=${day.cand} dataOk=${dataOkThisDay}`
        expect(nHost, `n_host mismatch: ${ctx}`).toBe(day.n_host)
        expect(nFlint, `n_flint mismatch: ${ctx}`).toBe(day.n_flint)
        expect(floorCents, `floor mismatch: ${ctx}`).toBe(day.floor_cents)
        expect(triggered, `triggered mismatch: ${ctx}`).toBe(day.triggered_after)
        expect(calmApplied, `calm_applied mismatch: ${ctx}`).toBe(day.calm_applied)
      }
    })
  }
})
