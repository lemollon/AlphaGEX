import { describe, it, expect } from 'vitest'
import { topStrikesByGamma, buildReactionFramework, computeDailyExpectedMove } from './derive'

describe('topStrikesByGamma', () => {
  const strikes = [
    { strike: 95, net_gamma: -30 },
    { strike: 97, net_gamma: -10 },
    { strike: 105, net_gamma: 20 },
    { strike: 110, net_gamma: 5 },
  ]
  it('returns top resistance strikes above price by |gamma|', () => {
    const { resistance } = topStrikesByGamma(strikes as any, 100, 2)
    expect(resistance.map((s) => s.strike)).toEqual([105, 110])
  })
  it('returns top support strikes below price by |gamma|', () => {
    const { support } = topStrikesByGamma(strikes as any, 100, 2)
    expect(support.map((s) => s.strike)).toEqual([95, 97])
  })
  it('handles empty input', () => {
    const out = topStrikesByGamma([], 100, 2)
    expect(out.resistance).toEqual([])
    expect(out.support).toEqual([])
  })
  it('bandPct excludes far-OTM noise spikes', () => {
    // A huge far-OTM gamma spike at 130 must NOT win when banded to ±5%.
    const noisy = [
      { strike: 102, net_gamma: 20 },
      { strike: 130, net_gamma: 9999 },
      { strike: 98, net_gamma: -18 },
      { strike: 70, net_gamma: -9999 },
    ]
    const { resistance, support } = topStrikesByGamma(noisy as any, 100, 1, 0.05)
    expect(resistance.map((s) => s.strike)).toEqual([102])
    expect(support.map((s) => s.strike)).toEqual([98])
  })
})

describe('computeDailyExpectedMove', () => {
  it('computes S·σ·sqrt(1/252) and the ±1σ bounds', () => {
    const out = computeDailyExpectedMove(749, 16.8)
    // 749 * 0.168 / sqrt(252) ≈ 7.93
    expect(out.move).toBeCloseTo(7.93, 1)
    expect(out.lower).toBeCloseTo(749 - out.move, 5)
    expect(out.upper).toBeCloseTo(749 + out.move, 5)
  })
  it('returns zero/null on missing or zero vol', () => {
    expect(computeDailyExpectedMove(749, 0)).toEqual({ move: 0, lower: null, upper: null })
    expect(computeDailyExpectedMove(0, 16)).toEqual({ move: 0, lower: null, upper: null })
    expect(computeDailyExpectedMove(749, null)).toEqual({ move: 0, lower: null, upper: null })
  })
})

describe('buildReactionFramework', () => {
  it('positive regime above flip -> chop base case', () => {
    const out = buildReactionFramework({
      gammaForm: 'POSITIVE', price: 750, flip: 743, callWall: 755, putWall: 730,
      balanceLabel: 'Balanced',
    })
    expect(out.baseCase.toLowerCase()).toContain('chop')
    expect(out.invalidatedIf.length).toBeGreaterThan(0)
  })
  it('negative regime -> trend/acceleration base case', () => {
    const out = buildReactionFramework({
      gammaForm: 'NEGATIVE', price: 740, flip: 743, callWall: 755, putWall: 730,
      balanceLabel: 'Balanced',
    })
    expect(out.baseCase.toLowerCase()).toMatch(/trend|acceler/)
  })
})
