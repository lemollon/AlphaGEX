import { describe, it, expect } from 'vitest'
import { classifyTrade, buildStreakSummary } from '../winLossStreak'

describe('classifyTrade', () => {
  it('classifies exactly $0.00 as a loss — a scratch trade is not a win', () => {
    expect(classifyTrade(0)).toBe('loss')
  })

  it('classifies a penny of profit as a win', () => {
    expect(classifyTrade(0.01)).toBe('win')
  })

  it('classifies a penny of loss as a loss', () => {
    expect(classifyTrade(-0.01)).toBe('loss')
  })
})

describe('buildStreakSummary', () => {
  it('reverses newest-first input to oldest-first display order', () => {
    // Newest-first: +100 (most recent), +50, -20, +80 (oldest).
    const summary = buildStreakSummary([100, 50, -20, 80])
    expect(summary.trades).toEqual(['win', 'loss', 'win', 'win'])
  })

  it('computes the current streak off the most recent trades', () => {
    const summary = buildStreakSummary([100, 50, -20, 80])
    expect(summary.currentStreak).toEqual({ count: 2, type: 'win' })
  })

  it('computes a LOSING streak just as correctly as a winning one', () => {
    const summary = buildStreakSummary([-10, -20, -30])
    expect(summary.currentStreak).toEqual({ count: 3, type: 'loss' })
    expect(summary.trades).toEqual(['loss', 'loss', 'loss'])
    expect(summary.winsCount).toBe(0)
    expect(summary.lossesCount).toBe(3)
  })

  it('returns an honest empty state for zero trades', () => {
    const summary = buildStreakSummary([])
    expect(summary).toEqual({
      trades: [],
      winsCount: 0,
      lossesCount: 0,
      currentStreak: null,
    })
  })
})
