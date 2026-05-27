import { describe, it, expect } from 'vitest'
import { topStrikesByGamma, buildReactionFramework } from './derive'

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
