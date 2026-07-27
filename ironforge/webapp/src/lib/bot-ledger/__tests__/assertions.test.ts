import { describe, expect, it } from 'vitest'

import {
  assertDedupeCount,
  assertPeriodStats,
  assertPersistedTotal,
  assertPublicTradeShape,
  LedgerInvariantError,
} from '../assertions'
import type { LedgerTrade, PeriodStats, PublicLedgerTrade } from '../types'

function trade(netCents: number): LedgerTrade {
  return {
    publicId: 'trd_abc123abc123',
    bot: 'spark',
    closedDate: '2026-07-25',
    closedAtMs: 0,
    rowId: 1,
    setup: 'SPY 1DTE Iron Condor',
    legs: 4,
    bpCents: 50_000,
    netCents,
    returnOnBpHpct: 100,
    outcome: netCents > 0 ? 'WIN' : netCents < 0 ? 'LOSS' : 'SCRATCH',
    tzDivergent: false,
  }
}

function stats(over: Partial<PeriodStats> = {}): PeriodStats {
  return {
    closed_trades: 2,
    wins: 1,
    losses: 1,
    scratches: 0,
    win_rate_pct: '50.00',
    avg_return_on_bp_pct: '1.00',
    profit_factor: '1.00',
    avg_winner_pct: '1.00',
    avg_loser_pct: '-1.00',
    ...over,
  }
}

const trades = [trade(100), trade(-100)]

describe('assertPeriodStats', () => {
  it('accepts a consistent block', () => {
    expect(() => assertPeriodStats('t', stats(), trades)).not.toThrow()
  })

  it('rejects counts that do not partition', () => {
    expect(() => assertPeriodStats('t', stats({ wins: 2 }), trades)).toThrow(LedgerInvariantError)
  })

  it('rejects closed_trades disagreeing with the trade set', () => {
    expect(() => assertPeriodStats('t', stats(), [trade(100)])).toThrow(LedgerInvariantError)
  })

  it('rejects a profit factor present with zero losses', () => {
    const bad = stats({ closed_trades: 1, wins: 1, losses: 0, avg_loser_pct: null })
    expect(() => assertPeriodStats('t', bad, [trade(100)])).toThrow(/profit_factor nullability/)
  })

  it('rejects a null win rate when trades exist', () => {
    expect(() => assertPeriodStats('t', stats({ win_rate_pct: null }), trades)).toThrow(
      /win_rate_pct nullability/,
    )
  })

  it('rejects a number where a decimal string is required', () => {
    // @ts-expect-error deliberately wrong type
    expect(() => assertPeriodStats('t', stats({ win_rate_pct: 50 }), trades)).toThrow(
      LedgerInvariantError,
    )
  })

  it('rejects negative zero and non-finite values', () => {
    expect(() => assertPeriodStats('t', stats({ avg_loser_pct: '-0.00' }), trades)).toThrow(
      /negative zero/,
    )
    expect(() => assertPeriodStats('t', stats({ profit_factor: 'Infinity' }), trades)).toThrow(
      LedgerInvariantError,
    )
  })
})

describe('assertPersistedTotal', () => {
  it('accepts an exact match', () => {
    expect(() => assertPersistedTotal('spark', 300, [100, 200])).not.toThrow()
  })

  it('rejects a one-cent disagreement — the tolerance is zero', () => {
    expect(() => assertPersistedTotal('spark', 301, [100, 200])).toThrow(LedgerInvariantError)
  })
})

describe('assertDedupeCount', () => {
  it('rejects Postgres and JavaScript disagreeing on row count', () => {
    expect(() => assertDedupeCount('spark', 10, 10)).not.toThrow()
    expect(() => assertDedupeCount('spark', 10, 9)).toThrow(LedgerInvariantError)
  })
})

describe('assertPublicTradeShape', () => {
  const good: PublicLedgerTrade = {
    public_id: 'trd_abc123abc123',
    closed_date: '2026-07-25',
    bot: 'spark',
    setup: 'SPY 1DTE Iron Condor',
    buying_power_used: '500.00',
    net_result: '42.00',
    return_on_bp_pct: '8.40',
    outcome: 'win',
  }

  it('accepts the allowlisted shape', () => {
    expect(() => assertPublicTradeShape([good])).not.toThrow()
  })

  it('rejects any extra field, however it got there', () => {
    const leaky = { ...good, close_reason: 'profit_target' } as PublicLedgerTrade
    expect(() => assertPublicTradeShape([leaky])).toThrow(/disallowed field: close_reason/)
  })

  it('rejects a close date that is not a plain date', () => {
    const bad = { ...good, closed_date: '2026-07-25T19:50:00Z' }
    expect(() => assertPublicTradeShape([bad])).toThrow(/not a plain date/)
  })
})
