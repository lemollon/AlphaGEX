import { describe, it, expect } from 'vitest'
import { computeTradesTotals, computeAgentPeriodKpis, last20DailyBars } from '../trades-history'
import { winRatePct } from '../performance'

/**
 * The Ledger KPI strip (mobile, handoff/ledger-kpis.md): completed_trades /
 * win_rate over the SAME rows getCustomerTradesPage hands to pagination —
 * pure and DB-independent, same reasoning as paginateSorted in
 * trades-cursor.test.ts.
 */
describe('computeTradesTotals', () => {
  it('is null win_rate with 0 completed trades — never divide by zero', () => {
    expect(computeTradesTotals([])).toEqual({ completed_trades: 0, win_rate: null, net_pnl: 0 })
  })

  it('7 wins of 8 rounds to 87.5, not 87 or 88', () => {
    const rows = [
      ...Array.from({ length: 7 }, () => ({ realized_pnl: '12.34' })),
      { realized_pnl: '-5.00' },
    ]
    expect(computeTradesTotals(rows)).toEqual({ completed_trades: 8, win_rate: 87.5, net_pnl: 81.38 })
  })

  it('a whole-number win rate comes back as a whole number (e.g. 100, not 100.0)', () => {
    const rows = Array.from({ length: 4 }, () => ({ realized_pnl: '1' }))
    expect(computeTradesTotals(rows)).toEqual({ completed_trades: 4, win_rate: 100, net_pnl: 4 })
  })

  it('win = pnl > 0 — a scratch (pnl exactly 0) counts as a loss, not a win', () => {
    const rows = [{ realized_pnl: '0' }, { realized_pnl: '10' }]
    expect(computeTradesTotals(rows)).toEqual({ completed_trades: 2, win_rate: 50, net_pnl: 10 })
  })

  it('parses pg NUMERIC strings, not just JS numbers', () => {
    const rows = [{ realized_pnl: '10.50' }, { realized_pnl: '-3.25' }]
    expect(computeTradesTotals(rows)).toEqual({ completed_trades: 2, win_rate: 50, net_pnl: 7.25 })
  })

  it('only counts the rows it is given — the caller (loadMergedRows) owns the bot/days/q filter', () => {
    const flameOnly = [{ realized_pnl: '5' }, { realized_pnl: '-1' }]
    const sparkOnly = [{ realized_pnl: '5' }, { realized_pnl: '5' }, { realized_pnl: '-1' }]
    expect(computeTradesTotals(flameOnly)).toEqual({ completed_trades: 2, win_rate: 50, net_pnl: 4 })
    expect(computeTradesTotals(sparkOnly)).toEqual({ completed_trades: 3, win_rate: 66.7, net_pnl: 9 })
    // Filtering to one bot changes both numbers — confirms totals track whatever
    // population is passed in rather than some fixed/global count.
    expect(computeTradesTotals([...flameOnly, ...sparkOnly])).toEqual({
      completed_trades: 5,
      win_rate: 60,
      net_pnl: 13,
    })
  })

  it('net_pnl can be negative — a losing filter set is not floored at 0', () => {
    const rows = [{ realized_pnl: '-10' }, { realized_pnl: '3' }]
    expect(computeTradesTotals(rows).net_pnl).toBe(-7)
  })
})

describe('computeAgentPeriodKpis', () => {
  // 2026-10-05 is a Monday CT — the start of its own week — and the start of
  // October, so this data set exercises the week/month boundary distinctly:
  // 10/2 is inside October (month) but before Monday 10/5 (week).
  const trades = [
    { close_date: '2026-10-05', pnl: 40 }, // today — in week AND month
    { close_date: '2026-10-02', pnl: 10 }, // in month, NOT in week
    { close_date: '2026-09-15', pnl: 25 }, // in neither — prior month
    { close_date: '2026-08-01', pnl: -100 }, // in neither — only in lifetime
  ]
  const now = new Date('2026-10-05T18:00:00Z')

  it('buckets week/month from close_date, life from the caller-supplied unbounded total', () => {
    const k = computeAgentPeriodKpis(trades, 999, null, now)
    expect(k.today).toBeNull()
    expect(k.week).toBe(40)
    expect(k.month).toBe(50)
    expect(k.life).toBe(999)
  })

  it('today_pnl (open-position-inclusive) is added into week and month, not just echoed as today', () => {
    const k = computeAgentPeriodKpis(trades, 999, 7, now)
    expect(k.today).toBe(7)
    expect(k.week).toBe(47)
    expect(k.month).toBe(57)
  })

  it('an agent with no closed trades yet still returns 0s, not nulls, for week/month/life', () => {
    const k = computeAgentPeriodKpis([], 0, null, now)
    expect(k).toEqual({ today: null, week: 0, month: 0, life: 0 })
  })
})

describe('last20DailyBars', () => {
  it('groups by close_date, sums same-day trades, oldest to newest, capped at 20 days', () => {
    const trades = [
      { close_date: '2026-10-03', pnl: 5 },
      { close_date: '2026-10-03', pnl: -2 },
      { close_date: '2026-10-02', pnl: 10 },
      { close_date: '2026-10-01', pnl: -3 },
    ]
    expect(last20DailyBars(trades)).toEqual([
      { date: '2026-10-01', pnl: -3 },
      { date: '2026-10-02', pnl: 10 },
      { date: '2026-10-03', pnl: 3 },
    ])
  })

  it('caps at the most recent 20 distinct trading days', () => {
    const trades = Array.from({ length: 25 }, (_, i) => ({
      close_date: `2026-09-${String(i + 1).padStart(2, '0')}`,
      pnl: 1,
    }))
    const bars = last20DailyBars(trades)
    expect(bars).toHaveLength(20)
    expect(bars[0].date).toBe('2026-09-06') // oldest of the most-recent 20
    expect(bars[19].date).toBe('2026-09-25') // newest
  })

  it('empty trade list returns an empty array, not an error', () => {
    expect(last20DailyBars([])).toEqual([])
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
