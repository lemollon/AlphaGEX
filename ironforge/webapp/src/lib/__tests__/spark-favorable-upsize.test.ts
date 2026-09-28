import { describe, it, expect } from 'vitest'
import {
  decideSparkFavorableUpsize,
  isSparkFavorableUpsizeMode,
  isSparkUpsizeEligibleDeposit,
  SPARK_UPSIZE_DEPOSIT_CEILING,
} from '../spark-favorable-upsize'
import type { FastStartDecision } from '../fast-start-sizing'

function phase1Decision(overrides: Partial<FastStartDecision> = {}): FastStartDecision {
  return {
    phase: 1,
    ebbContracts: 2,
    flintContracts: 0,
    floor: 5000,
    budget: null,
    phase1CapBudget: 1000, // 20% of $5,000
    cushion: 500,
    triggerLevel: 4000,
    triggeredToday: false,
    reason: 'test',
    ...overrides,
  }
}

function phase2Decision(overrides: Partial<FastStartDecision> = {}): FastStartDecision {
  return {
    phase: 2,
    ebbContracts: 3,
    flintContracts: 0,
    floor: 5200,
    budget: 800,
    phase1CapBudget: null,
    cushion: 1000,
    triggerLevel: null,
    triggeredToday: false,
    reason: 'test',
    ...overrides,
  }
}

describe('isSparkFavorableUpsizeMode', () => {
  it('off by default / unset', () => {
    delete process.env.SPARK_FAVORABLE_UPSIZE
    expect(isSparkFavorableUpsizeMode()).toBe(false)
  })
  it('on only for exactly "on" (case-insensitive)', () => {
    process.env.SPARK_FAVORABLE_UPSIZE = 'ON'
    expect(isSparkFavorableUpsizeMode()).toBe(true)
    process.env.SPARK_FAVORABLE_UPSIZE = 'true'
    expect(isSparkFavorableUpsizeMode()).toBe(false)
    delete process.env.SPARK_FAVORABLE_UPSIZE
  })
})

describe('isSparkUpsizeEligibleDeposit', () => {
  it('strictly below $7,500', () => {
    expect(isSparkUpsizeEligibleDeposit(5000)).toBe(true)
    expect(isSparkUpsizeEligibleDeposit(7499.99)).toBe(true)
    expect(isSparkUpsizeEligibleDeposit(7500)).toBe(false)
    expect(isSparkUpsizeEligibleDeposit(10000)).toBe(false)
  })
  it('constant matches the settled boundary', () => {
    expect(SPARK_UPSIZE_DEPOSIT_CEILING).toBe(7500)
  })
})

describe('decideSparkFavorableUpsize', () => {
  const base = {
    decision: phase1Decision(),
    deposit: 5000,
    sparkCandidateDay: true,
    sparkMaxLossPerContract: 200,
    favorable: true,
    ladderCap: 100,
  }

  it('not a candidate day -> 0', () => {
    const r = decideSparkFavorableUpsize({ ...base, sparkCandidateDay: false })
    expect(r.upsizeContracts).toBe(0)
    expect(r.reason).toContain('not_a_candidate_day')
  })

  it('deposit at or above the $7,500 ceiling -> 0', () => {
    expect(decideSparkFavorableUpsize({ ...base, deposit: 7500 }).upsizeContracts).toBe(0)
    expect(decideSparkFavorableUpsize({ ...base, deposit: 10000 }).upsizeContracts).toBe(0)
  })

  it('not a favorable day -> 0', () => {
    const r = decideSparkFavorableUpsize({ ...base, favorable: false })
    expect(r.upsizeContracts).toBe(0)
    expect(r.reason).toContain('not_a_favorable_day')
  })

  it('max loss null/unreadable -> 0', () => {
    expect(decideSparkFavorableUpsize({ ...base, sparkMaxLossPerContract: null }).upsizeContracts).toBe(0)
    expect(decideSparkFavorableUpsize({ ...base, sparkMaxLossPerContract: 0 }).upsizeContracts).toBe(0)
    expect(decideSparkFavorableUpsize({ ...base, sparkMaxLossPerContract: -5 }).upsizeContracts).toBe(0)
  })

  it('ladder cap already reached -> 0', () => {
    const r = decideSparkFavorableUpsize({ ...base, decision: phase1Decision({ ebbContracts: 100 }), ladderCap: 100 })
    expect(r.upsizeContracts).toBe(0)
    expect(r.reason).toContain('ladder_cap')
  })

  describe('phase 1', () => {
    it('cushion insufficient -> 0', () => {
      const d = phase1Decision({ cushion: 100, phase1CapBudget: 1000, ebbContracts: 0 })
      const r = decideSparkFavorableUpsize({ ...base, decision: d, sparkMaxLossPerContract: 200 })
      expect(r.upsizeContracts).toBe(0)
    })

    it('cap budget exhausted by own contracts -> 0', () => {
      // 2 contracts * $200 = $400 spent; only $1000 cap budget, but cushion is huge so cushion check passes;
      // remaining = 1000 - 400 = 600 >= 200 -> should actually pass. Use a tighter cap to force a fail.
      const d = phase1Decision({ cushion: 5000, phase1CapBudget: 450, ebbContracts: 2 })
      const r = decideSparkFavorableUpsize({ ...base, decision: d, sparkMaxLossPerContract: 200 })
      // remaining cap = 450 - 400 = 50 < 200 -> fail
      expect(r.upsizeContracts).toBe(0)
      expect(r.reason).toContain('phase1')
    })

    it('both cushion and cap budget clear -> 1', () => {
      const d = phase1Decision({ cushion: 5000, phase1CapBudget: 1000, ebbContracts: 2 })
      const r = decideSparkFavorableUpsize({ ...base, decision: d, sparkMaxLossPerContract: 200 })
      expect(r.upsizeContracts).toBe(1)
      expect(r.reason).toContain('phase1')
    })

    it('phase1CapBudget missing (defensive) -> 0', () => {
      const d = phase1Decision({ phase1CapBudget: null })
      const r = decideSparkFavorableUpsize({ ...base, decision: d })
      expect(r.upsizeContracts).toBe(0)
      expect(r.reason).toContain('phase1_cap_budget_unavailable')
    })
  })

  describe('phase 2', () => {
    it('remaining cushion insufficient -> 0', () => {
      const d = phase2Decision({ cushion: 300, ebbContracts: 1 })
      const r = decideSparkFavorableUpsize({ ...base, decision: d, sparkMaxLossPerContract: 200 })
      // remaining = 300 - 1*200 = 100 < 200 -> fail
      expect(r.upsizeContracts).toBe(0)
      expect(r.reason).toContain('phase2')
    })

    it('remaining cushion sufficient -> 1', () => {
      const d = phase2Decision({ cushion: 1000, ebbContracts: 1 })
      const r = decideSparkFavorableUpsize({ ...base, decision: d, sparkMaxLossPerContract: 200 })
      // remaining = 1000 - 200 = 800 >= 200 -> pass
      expect(r.upsizeContracts).toBe(1)
      expect(r.reason).toContain('phase2')
    })
  })
})
