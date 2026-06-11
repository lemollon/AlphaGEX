import { describe, it, expect } from 'vitest'
import {
  scoreToProfile,
  validateRiskAnswers,
  RISK_QUESTIONS,
  type RiskAnswers,
} from '@/lib/onboarding/risk-scoring'

// Helper: build an answers object from explicit option ids (in question order).
function answers(ids: string[]): RiskAnswers {
  const a: RiskAnswers = {}
  RISK_QUESTIONS.forEach((q, i) => (a[q.key] = ids[i]))
  return a
}

describe('scoreToProfile', () => {
  it('scores all-lowest as 0 → Conservative/FLAME with caution', () => {
    const p = scoreToProfile(answers(['none', 'preserve', 'avoid', 'sell', 'critical', 'longterm']))
    expect(p.score).toBe(0)
    expect(p.tier).toBe('Conservative')
    expect(p.recommendedBot).toBe('FLAME')
    expect(p.caution).toBe(true)
  })

  it('treats 8 as the top of Conservative', () => {
    // experienced(4)+steady(2)+avoid(0)+sell(0)+moderate(2)+longterm(0) = 8
    const p = scoreToProfile(answers(['experienced', 'steady', 'avoid', 'sell', 'moderate', 'longterm']))
    expect(p.score).toBe(8)
    expect(p.tier).toBe('Conservative')
    expect(p.recommendedBot).toBe('FLAME')
    expect(p.caution).toBe(true) // tier-driven
  })

  it('treats 10 as Moderate/SPARK with no caution', () => {
    // experienced(4)+aggressive(4)+avoid(0)+sell(0)+moderate(2)+longterm(0) = 10
    const p = scoreToProfile(answers(['experienced', 'aggressive', 'avoid', 'sell', 'moderate', 'longterm']))
    expect(p.score).toBe(10)
    expect(p.tier).toBe('Moderate')
    expect(p.recommendedBot).toBe('SPARK')
    expect(p.caution).toBe(false)
  })

  it('treats 16 as the top of Moderate', () => {
    // experienced(4)+aggressive(4)+large(4)+sell(0)+small(4)+longterm(0) = 16
    const p = scoreToProfile(answers(['experienced', 'aggressive', 'large', 'sell', 'small', 'longterm']))
    expect(p.score).toBe(16)
    expect(p.tier).toBe('Moderate')
    expect(p.recommendedBot).toBe('SPARK')
  })

  it('treats 18 as Aggressive/INFERNO', () => {
    // experienced(4)+aggressive(4)+large(4)+add(4)+moderate(2)+longterm(0) = 18
    const p = scoreToProfile(answers(['experienced', 'aggressive', 'large', 'add', 'moderate', 'longterm']))
    expect(p.score).toBe(18)
    expect(p.tier).toBe('Aggressive')
    expect(p.recommendedBot).toBe('INFERNO')
    expect(p.caution).toBe(false)
  })

  it('scores all-highest as 24 → Aggressive/INFERNO, no caution', () => {
    const p = scoreToProfile(answers(['experienced', 'aggressive', 'large', 'add', 'small', 'daily']))
    expect(p.score).toBe(24)
    expect(p.tier).toBe('Aggressive')
    expect(p.recommendedBot).toBe('INFERNO')
    expect(p.caution).toBe(false)
  })

  it('forces caution when capacity is critical even at a high score', () => {
    // experienced(4)+aggressive(4)+large(4)+add(4)+critical(0)+daily(4) = 20
    const p = scoreToProfile(answers(['experienced', 'aggressive', 'large', 'add', 'critical', 'daily']))
    expect(p.score).toBe(20)
    expect(p.tier).toBe('Aggressive')
    expect(p.caution).toBe(true) // capacity override
  })
})

describe('validateRiskAnswers', () => {
  it('accepts a complete, valid answer set', () => {
    expect(validateRiskAnswers(answers(['none', 'preserve', 'avoid', 'sell', 'critical', 'longterm']))).toBe(true)
  })
  it('rejects a missing question', () => {
    const a = answers(['none', 'preserve', 'avoid', 'sell', 'critical', 'longterm'])
    delete a.horizon
    expect(validateRiskAnswers(a)).toBe(false)
  })
  it('rejects an unknown option id', () => {
    const a = answers(['none', 'preserve', 'avoid', 'sell', 'critical', 'longterm'])
    a.goal = 'not-an-option'
    expect(validateRiskAnswers(a)).toBe(false)
  })
  it('rejects non-objects', () => {
    expect(validateRiskAnswers(null)).toBe(false)
    expect(validateRiskAnswers('x')).toBe(false)
  })
})
