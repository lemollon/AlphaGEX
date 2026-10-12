import { describe, it, expect } from 'vitest'
import { totalCapital } from '@/live/capital'
import type { LiveAgent, LiveSummary } from '@/api/types'

/**
 * The rule under test: never present a total that mixes pretend money with real money,
 * and never present a partial sum as if it were the whole balance.
 */
function agent(bot: string, value: number | null, mode: 'paper' | 'production'): LiveAgent {
  return {
    bot,
    label: bot,
    paper: mode === 'paper',
    state: null,
    account: {
      value,
      today_pnl: null,
      today_pnl_pct: null,
      source: 'tradier',
      mode,
      disclosure: null,
    },
    trade: null,
    error: null,
  }
}

const summary = { account: { value: 1000 } } as unknown as LiveSummary

describe('totalCapital', () => {
  it('sums when every agent reported and all are production', () => {
    const r = totalCapital([agent('spark', 6000, 'production'), agent('flame', 4000, 'production')], summary)
    expect(r.value).toBe(10000)
    expect(r.note).toBe('Across 2 accounts')
  })

  it('sums when every agent reported and all are paper', () => {
    const r = totalCapital([agent('spark', 25, 'paper'), agent('flame', 75, 'paper')], summary)
    expect(r.value).toBe(100)
  })

  it('REFUSES to add paper money to production money', () => {
    const r = totalCapital([agent('spark', 6000, 'production'), agent('flame', 4000, 'paper')], summary)
    // Falls back to the single real account rather than inventing a $10,000 total that is
    // 40% imaginary.
    expect(r.value).toBe(1000)
    expect(r.note).toMatch(/different account types/)
  })

  it('does not present a partial sum as a total when an agent failed to report', () => {
    const broken: LiveAgent = { ...agent('flame', null, 'production'), account: null, error: 'state' }
    const r = totalCapital([agent('spark', 6000, 'production'), broken], summary)
    expect(r.value).toBe(1000)
    expect(r.note).toMatch(/could not read every agent/)
  })

  it('does not sum when an agent reported an account with a null balance', () => {
    const r = totalCapital(
      [agent('spark', 6000, 'production'), agent('flame', null, 'production')],
      summary,
    )
    expect(r.value).toBe(1000)
  })

  it('uses the single account view for one agent, with no note', () => {
    const r = totalCapital([agent('spark', 6000, 'production')], summary)
    expect(r.value).toBe(1000)
    expect(r.note).toBeNull()
  })

  it('handles an empty agent list', () => {
    expect(totalCapital([], summary).value).toBe(1000)
  })
})
