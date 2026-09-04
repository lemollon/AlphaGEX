import { describe, it, expect } from 'vitest'
import { computeCardStats, lifetimeReturnPct } from '../card-stats'

/**
 * Forge agent-card stat row (mobile Forge tab, handoff/ledger-kpis.md PART 2):
 * Account Capital / Growth / Last 10 / Best Trade, all LIFETIME. Pure and
 * DB-independent, same reasoning as computeTradesTotals in trades-history.ts —
 * closedTradesDesc is exactly the shape loadBotTrades hands back (newest
 * close_time first).
 */
describe('lifetimeReturnPct', () => {
  it('null with no starting capital — never divide by zero', () => {
    expect(lifetimeReturnPct(500, 0)).toBeNull()
  })

  it('positive growth, 2dp', () => {
    expect(lifetimeReturnPct(340, 5000)).toBe(6.8)
  })

  it('negative growth stays negative, not clamped to 0', () => {
    expect(lifetimeReturnPct(-250, 5000)).toBe(-5)
  })
})

describe('computeCardStats', () => {
  it('zero closed trades: no capital, no growth-denominator issue, "—" for last10/best trade', () => {
    expect(computeCardStats(0, 0, [])).toEqual({
      account_capital_cents: null,
      growth_pct: null,
      last10: { wins: 0, losses: 0 },
      best_trade_cents: null,
    })
  })

  it('starting capital with zero trades still reports account capital and 0% growth', () => {
    const result = computeCardStats(5000, 0, [])
    expect(result.account_capital_cents).toBe(500000)
    expect(result.growth_pct).toBe(0)
    expect(result.last10).toEqual({ wins: 0, losses: 0 })
    expect(result.best_trade_cents).toBeNull()
  })

  it('fewer than 10 closed trades counts what exists, not padded to 10', () => {
    const trades = [{ realized_pnl: '50' }, { realized_pnl: '-20' }, { realized_pnl: '30' }]
    const result = computeCardStats(5000, 60, trades)
    expect(result.last10).toEqual({ wins: 2, losses: 1 })
    expect(result.best_trade_cents).toBe(5000) // $50.00
  })

  it('exactly 10 with a mix — matches the approved mock (8 wins, 2 losses)', () => {
    const trades = [
      ...Array.from({ length: 8 }, () => ({ realized_pnl: '15' })),
      ...Array.from({ length: 2 }, () => ({ realized_pnl: '-10' })),
    ]
    const result = computeCardStats(5000, 100, trades)
    expect(result.last10).toEqual({ wins: 8, losses: 2 })
  })

  it('more than 10 closed trades: Last 10 only looks at the first 10 (newest), not the whole list', () => {
    // 15 trades, newest-first: the 11th-15th (oldest) are all wins that must NOT
    // be counted in Last 10, but DO still count toward the lifetime total passed
    // in separately and toward Best Trade, since those aren't limited to 10.
    const newest10 = Array.from({ length: 10 }, () => ({ realized_pnl: '-5' }))
    const older5 = Array.from({ length: 5 }, () => ({ realized_pnl: '999' }))
    const trades = [...newest10, ...older5]
    const result = computeCardStats(5000, -50 + 999 * 5, trades)
    expect(result.last10).toEqual({ wins: 0, losses: 10 })
    expect(result.best_trade_cents).toBe(99900)
  })

  it('a scratch (pnl exactly 0) counts as a loss in Last 10, and is never Best Trade', () => {
    const trades = [{ realized_pnl: '0' }, { realized_pnl: '10' }]
    const result = computeCardStats(1000, 10, trades)
    expect(result.last10).toEqual({ wins: 1, losses: 1 })
    expect(result.best_trade_cents).toBe(1000)
  })

  it('ties on best trade: the tied value wins once, not doubled or dropped', () => {
    const trades = [{ realized_pnl: '100' }, { realized_pnl: '100' }, { realized_pnl: '50' }]
    const result = computeCardStats(5000, 250, trades)
    expect(result.best_trade_cents).toBe(10000)
  })

  it('all-losing history: Best Trade is "—" (null), not the least-bad loss', () => {
    const trades = [{ realized_pnl: '-10' }, { realized_pnl: '-40' }]
    const result = computeCardStats(5000, -50, trades)
    expect(result.best_trade_cents).toBeNull()
    expect(result.last10).toEqual({ wins: 0, losses: 2 })
    expect(result.growth_pct).toBe(-1)
  })

  it('negative growth passes through unclamped', () => {
    const result = computeCardStats(5000, -340, [{ realized_pnl: '-340' }])
    expect(result.growth_pct).toBe(-6.8)
  })

  it('parses pg NUMERIC strings, not just JS numbers', () => {
    const trades = [{ realized_pnl: '15.50' }, { realized_pnl: '-3.25' }]
    const result = computeCardStats(1000, 12.25, trades)
    expect(result.best_trade_cents).toBe(1550)
    expect(result.last10).toEqual({ wins: 1, losses: 1 })
  })
})
