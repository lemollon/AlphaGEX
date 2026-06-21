import { describe, it, expect } from 'vitest'
import { buildHedgePlan, hedgePlanText, computeHedgeCap } from '@/lib/hedge/advisor'

describe('computeHedgeCap (relative cap)', () => {
  it('soft cap = min(50% of tail, 12% of account); hard ceiling = the tail', () => {
    const c = computeHedgeCap({ tail: 1200, accountEquity: 5145 })
    // 50% of 1200 = 600; 12% of 5145 = 617 → soft = 600; hard = 1200
    expect(c.softCap).toBe(600)
    expect(c.hardCeiling).toBe(1200)
  })

  it('a small account tightens the soft cap via the %-of-account ceiling', () => {
    const c = computeHedgeCap({ tail: 1200, accountEquity: 3000 }) // 12% = 360 < 600
    expect(c.softCap).toBe(360)
  })

  it('an absolute $ override only lowers the soft cap', () => {
    expect(computeHedgeCap({ tail: 1200, accountEquity: 5145, absoluteSoftCap: 500 }).softCap).toBe(500)
    expect(computeHedgeCap({ tail: 1200, accountEquity: 5145, absoluteSoftCap: 5000 }).softCap).toBe(600)
  })

  it('hard ceiling is the tail regardless of percentages (never pay > what you protect)', () => {
    expect(computeHedgeCap({ tail: 1200 }).hardCeiling).toBe(1200)
  })
})

describe('buildHedgePlan', () => {
  it('returns no-hedge on a calm (unflagged) day', () => {
    const p = buildHedgePlan({ flagged: false, reasons: [], tail: 1200, spy: 742 })
    expect(p.hedge).toBe(false)
    expect(p.contracts).toBe(0)
    expect(hedgePlanText(p)).toMatch(/no hedge/i)
  })

  it('sizes a 1-contract put spread to ~100% of a $1,200 tail at SPY 742', () => {
    const p = buildHedgePlan({ flagged: true, reasons: ['ts_flattening'], tail: 1200, spy: 742 })
    expect(p.hedge).toBe(true)
    expect(p.contracts).toBe(1)
    expect(p.width).toBe(12) // 1200 / 100
    expect(p.long_strike).toBe(731) // round(742 * 0.985)
    expect(p.short_strike).toBe(719) // 731 - 12
    expect(p.est_max_payoff).toBe(1200)
    expect(p.coverage_pct).toBeCloseTo(1.0, 2)
    // debit cheaper than payoff (the whole point of a debit spread)
    expect(p.est_debit).toBeLessThan(p.est_max_payoff)
    expect(p.est_cost_pct).toBeCloseTo(0.33, 2)
  })

  it('honors a 50% coverage ratio (cheaper)', () => {
    const full = buildHedgePlan({ flagged: true, reasons: ['x'], tail: 1200, spy: 742 })
    const half = buildHedgePlan({ flagged: true, reasons: ['x'], tail: 1200, spy: 742, coverage: 0.5 })
    expect(half.est_max_payoff).toBeLessThan(full.est_max_payoff)
    expect(half.coverage_pct).toBeCloseTo(0.5, 1)
  })

  it('adds contracts (not absurd width) for a large aggregate tail', () => {
    const p = buildHedgePlan({ flagged: true, reasons: ['x'], tail: 9000, spy: 742 })
    expect(p.contracts).toBeGreaterThan(1)
    expect(p.width).toBeLessThanOrEqual(30) // capped; scale via contracts
  })

  it('degrades to no-hedge on bad inputs even when flagged', () => {
    expect(buildHedgePlan({ flagged: true, reasons: ['x'], tail: 0, spy: 742 }).hedge).toBe(false)
    expect(buildHedgePlan({ flagged: true, reasons: ['x'], tail: 1200, spy: 0 }).hedge).toBe(false)
  })

  it('renders a concrete order line', () => {
    const p = buildHedgePlan({ flagged: true, reasons: ['ts_flattening'], tail: 1200, spy: 742 })
    expect(hedgePlanText(p)).toMatch(/BUY 1× SPY 35D 731\/719 put spread/)
  })
})
