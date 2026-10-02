import { describe, it, expect } from 'vitest'
import { decideSparkFlintContracts, isSparkFlintMode, SPARK_FLINT_MAX_CONTRACTS } from '../spark-flint-separate'

describe('isSparkFlintMode', () => {
  it('off by default / unset', () => {
    delete process.env.SPARK_FLINT
    expect(isSparkFlintMode()).toBe(false)
  })
  it('on only for exactly "on" (case-insensitive)', () => {
    process.env.SPARK_FLINT = 'On'
    expect(isSparkFlintMode()).toBe(true)
    process.env.SPARK_FLINT = '1'
    expect(isSparkFlintMode()).toBe(false)
    delete process.env.SPARK_FLINT
  })
})

describe('decideSparkFlintContracts', () => {
  const base = {
    equity: 5300,
    deposit: 5000,
    sparkFloor: 5000,
    flintCandidateDay: true,
    flintMaxLossPerContract: 180,
    sparkContractsToday: 2,
    sparkMaxLossPerContract: 200,
  }

  it('not a candidate day -> 0, not dropped for safety', () => {
    const r = decideSparkFlintContracts({ ...base, flintCandidateDay: false })
    expect(r.flintContracts).toBe(0)
    expect(r.droppedForSafety).toBe(false)
    expect(r.reason).toContain('not_a_candidate_day')
  })

  it('max loss null/unreadable -> 0', () => {
    expect(decideSparkFlintContracts({ ...base, flintMaxLossPerContract: null }).flintContracts).toBe(0)
    expect(decideSparkFlintContracts({ ...base, flintMaxLossPerContract: 0 }).flintContracts).toBe(0)
    expect(decideSparkFlintContracts({ ...base, flintMaxLossPerContract: -10 }).flintContracts).toBe(0)
  })

  it('R1 profit gate fails (cushion < flint max loss) -> 0, not a safety drop', () => {
    // cushion = equity - deposit = 5300-5000 = 300 < flint ml 180? no, 300>=180 passes.
    // Force a fail: equity below deposit + ml.
    const r = decideSparkFlintContracts({ ...base, equity: 5100 }) // cushion=100 < 180
    expect(r.flintContracts).toBe(0)
    expect(r.droppedForSafety).toBe(false)
    expect(r.reason).toContain('flint_profit_cushion')
  })

  it('R1 passes but the account-level safety net drops FLINT (combined cost crosses the floor)', () => {
    // equity=5300, sparkFloor=5000 -> budget_to_floor = 300.
    // sparkCost = 2 * 200 = 400 (already exceeds 300 on its own) -> combined > budget -> drop.
    const r = decideSparkFlintContracts({ ...base, equity: 5300, sparkFloor: 5000, sparkContractsToday: 2, sparkMaxLossPerContract: 200 })
    expect(r.flintContracts).toBe(0)
    expect(r.droppedForSafety).toBe(true)
    expect(r.reason).toContain('spark_flint_floor_safety')
  })

  it('R1 passes and the safety net has room -> 1 contract', () => {
    // equity=6000, sparkFloor=5000 -> budget_to_floor=1000. sparkCost=2*200=400. flint ml=180.
    // combined=580 <= 1000 -> passes.
    const r = decideSparkFlintContracts({ ...base, equity: 6000, sparkFloor: 5000 })
    expect(r.flintContracts).toBe(SPARK_FLINT_MAX_CONTRACTS)
    expect(r.droppedForSafety).toBe(false)
    expect(r.reason).toContain('flint:1')
  })

  it('SPARK max loss null is treated as zero cost (never blocks FLINT on an unreadable SPARK number)', () => {
    const r = decideSparkFlintContracts({ ...base, equity: 5300, sparkFloor: 5000, sparkMaxLossPerContract: null, sparkContractsToday: 2 })
    // sparkCost treated as 0, combined = 0 + 180 = 180 <= budget_to_floor(300) -> passes
    expect(r.flintContracts).toBe(1)
    expect(r.droppedForSafety).toBe(false)
  })

  it('negative sparkContractsToday is floored to zero cost, never a negative budget credit', () => {
    const r = decideSparkFlintContracts({ ...base, equity: 5300, sparkFloor: 5000, sparkContractsToday: -5, sparkMaxLossPerContract: 200 })
    // sparkCost floored to 0 (max(0,-5)*200=0), combined=180 <= 300 -> passes
    expect(r.flintContracts).toBe(1)
  })

  it('exactly at the boundary (combined === budget) passes — >, not >=, drops it', () => {
    // budget_to_floor = equity-floor. Set combined exactly equal.
    // flint ml=180, sparkCost=0 (sparkMaxLossPerContract null) -> combined=180.
    // equity - floor = 180 exactly.
    const r = decideSparkFlintContracts({
      ...base, equity: 5180, sparkFloor: 5000, sparkMaxLossPerContract: null, sparkContractsToday: 0,
    })
    expect(r.flintContracts).toBe(1)
  })
})
