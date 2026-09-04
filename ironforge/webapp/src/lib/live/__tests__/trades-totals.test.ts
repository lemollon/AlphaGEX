import { describe, it, expect } from 'vitest'
import { computeTradesTotals } from '../trades-history'
import { winRatePct } from '../performance'

/**
 * The Ledger KPI strip (mobile, handoff/ledger-kpis.md): completed_trades /
 * win_rate over the SAME rows getCustomerTradesPage hands to pagination —
 * pure and DB-independent, same reasoning as paginateSorted in
 * trades-cursor.test.ts.
 */
describe('computeTradesTotals', () => {
  it('is null win_rate with 0 completed trades — never divide by zero', () => {
    expect(computeTradesTotals([])).toEqual({ completed_trades: 0, win_rate: null })
  })

  it('7 wins of 8 rounds to 87.5, not 87 or 88', () => {
    const rows = [
      ...Array.from({ length: 7 }, () => ({ realized_pnl: '12.34' })),
      { realized_pnl: '-5.00' },
    ]
    expect(computeTradesTotals(rows)).toEqual({ completed_trades: 8, win_rate: 87.5 })
  })

  it('a whole-number win rate comes back as a whole number (e.g. 100, not 100.0)', () => {
    const rows = Array.from({ length: 4 }, () => ({ realized_pnl: '1' }))
    expect(computeTradesTotals(rows)).toEqual({ completed_trades: 4, win_rate: 100 })
  })

  it('win = pnl > 0 — a scratch (pnl exactly 0) counts as a loss, not a win', () => {
    const rows = [{ realized_pnl: '0' }, { realized_pnl: '10' }]
    expect(computeTradesTotals(rows)).toEqual({ completed_trades: 2, win_rate: 50 })
  })

  it('parses pg NUMERIC strings, not just JS numbers', () => {
    const rows = [{ realized_pnl: '10.50' }, { realized_pnl: '-3.25' }]
    expect(computeTradesTotals(rows)).toEqual({ completed_trades: 2, win_rate: 50 })
  })

  it('only counts the rows it is given — the caller (loadMergedRows) owns the bot/days/q filter', () => {
    const flameOnly = [{ realized_pnl: '5' }, { realized_pnl: '-1' }]
    const sparkOnly = [{ realized_pnl: '5' }, { realized_pnl: '5' }, { realized_pnl: '-1' }]
    expect(computeTradesTotals(flameOnly)).toEqual({ completed_trades: 2, win_rate: 50 })
    expect(computeTradesTotals(sparkOnly)).toEqual({ completed_trades: 3, win_rate: 66.7 })
    // Filtering to one bot changes both numbers — confirms totals track whatever
    // population is passed in rather than some fixed/global count.
    expect(computeTradesTotals([...flameOnly, ...sparkOnly])).toEqual({ completed_trades: 5, win_rate: 60 })
  })
})

describe('winRatePct — shared by performance.ts and the trades totals above', () => {
  it('null with 0 trades', () => {
    expect(winRatePct(0, 0)).toBeNull()
  })

  it('one decimal place, standard rounding', () => {
    expect(winRatePct(1, 3)).toBe(33.3)
    expect(winRatePct(2, 3)).toBe(66.7)
  })
})
