import { describe, expect, it } from 'vitest'

import { summarize, winStreak } from '../calc'
import type { LedgerTrade, Outcome } from '../types'

/**
 * Build a trade directly, bypassing projection, so these tests assert the KPI
 * algebra and nothing else.
 */
function trade(netCents: number, returnOnBpHpct: number, bpCents = 50_000): LedgerTrade {
  const outcome: Outcome = netCents > 0 ? 'WIN' : netCents < 0 ? 'LOSS' : 'SCRATCH'
  return {
    publicId: `trd_${netCents}_${returnOnBpHpct}`,
    bot: 'spark',
    closedDate: '2026-07-25',
    closedAtMs: 0,
    rowId: 0,
    setup: 'SPY 1DTE Iron Condor',
    legs: 4,
    bpCents,
    netCents,
    returnOnBpHpct,
    outcome,
    tzDivergent: false,
  }
}

describe('the spec KPI test vector (section 9.1)', () => {
  // T1 +$42 / +8.4% WIN, T2 +$39 / +7.8% WIN, T3 -$26 / -5.2% LOSS,
  // T4 +$31 / +6.2% WIN, T5 $0 / 0.0% SCRATCH — all on $500 buying power.
  const trades = [
    trade(4200, 840),
    trade(3900, 780),
    trade(-2600, -520),
    trade(3100, 620),
    trade(0, 0),
  ]

  it('reproduces every expected value exactly', () => {
    const s = summarize(trades)
    expect(s.closed_trades).toBe(5)
    expect(s.wins).toBe(3)
    expect(s.losses).toBe(1)
    expect(s.scratches).toBe(1)
    expect(s.win_rate_pct).toBe('60.00') // 3 / 5 x 100, displayed as 60.0
    expect(s.avg_return_on_bp_pct).toBe('3.44') // (8.4+7.8-5.2+6.2+0)/5
    expect(s.profit_factor).toBe('4.31') // (42+39+31)/26
    expect(s.avg_winner_pct).toBe('7.47') // (8.4+7.8+6.2)/3
    expect(s.avg_loser_pct).toBe('-5.20') // T3 only
  })

  it('keeps counts partitioned', () => {
    const s = summarize(trades)
    expect(s.wins + s.losses + s.scratches).toBe(s.closed_trades)
  })
})

describe('KPI edge cases', () => {
  it('returns null, not zero, when there are no trades at all', () => {
    const s = summarize([])
    expect(s.closed_trades).toBe(0)
    expect(s.win_rate_pct).toBeNull()
    expect(s.avg_return_on_bp_pct).toBeNull()
    expect(s.profit_factor).toBeNull()
    expect(s.avg_winner_pct).toBeNull()
    expect(s.avg_loser_pct).toBeNull()
  })

  it('returns null profit factor with no losses — never Infinity and never "0"', () => {
    const s = summarize([trade(4200, 840), trade(3900, 780)])
    expect(s.profit_factor).toBeNull()
    expect(s.profit_factor).not.toBe('0.00')
    expect(String(s.profit_factor)).not.toContain('Infinity')
    expect(s.win_rate_pct).toBe('100.00')
  })

  it('handles a set with no winners', () => {
    const s = summarize([trade(-2600, -520), trade(-1000, -200)])
    expect(s.avg_winner_pct).toBeNull()
    expect(s.profit_factor).toBe('0.00') // gross profit is genuinely zero
    expect(s.win_rate_pct).toBe('0.00')
  })

  it('treats an all-scratch set as 0% win rate with no profit factor', () => {
    const s = summarize([trade(0, 0), trade(0, 0)])
    expect(s.win_rate_pct).toBe('0.00')
    expect(s.avg_return_on_bp_pct).toBe('0.00')
    expect(s.profit_factor).toBeNull()
    expect(s.scratches).toBe(2)
  })

  it('never emits negative zero', () => {
    const s = summarize([trade(0, 0)])
    expect(s.avg_return_on_bp_pct).toBe('0.00')
    expect(s.avg_return_on_bp_pct).not.toBe('-0.00')
  })
})

describe('winStreak (section 9.2)', () => {
  it('counts consecutive wins from the newest trade backward', () => {
    // Newest-to-oldest: WIN, WIN, WIN, LOSS, WIN -> 3
    const t = [trade(1, 10), trade(1, 10), trade(1, 10), trade(-1, -10), trade(1, 10)]
    expect(winStreak(t)).toBe(3)
  })

  it('is 0 when the newest trade is a loss', () => {
    expect(winStreak([trade(-1, -10), trade(1, 10), trade(1, 10)])).toBe(0)
  })

  it('is 0 when the newest trade is a scratch — a scratch breaks a streak', () => {
    expect(winStreak([trade(0, 0), trade(1, 10), trade(1, 10)])).toBe(0)
  })

  it('is 0 for an empty ledger', () => {
    expect(winStreak([])).toBe(0)
  })
})
