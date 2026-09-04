import { describe, it, expect } from 'vitest'
import {
  ledgerPageKey,
  getLedgerKey,
  mergeLedgerPages,
  ledgerTotal,
  ledgerTotals,
  hasMoreLedgerPages,
  type LedgerFilters,
  type LedgerPage,
} from '@/ledger/paging'
import type { HistoryTrade } from '@/api/types'

const ALL: LedgerFilters = { agent: 'all', range: '30', query: '' }

function trade(id: string, close_date: string): HistoryTrade {
  return {
    id,
    bot: 'spark',
    strategy: 'Spark',
    paper: false,
    underlying: 'SPY',
    close_date,
    opened_ct: '9:48 AM',
    closed_ct: '1:42 PM',
    contracts: 1,
    credit: 0.5,
    pnl: 12.34,
    pnl_pct: 1.2,
    outcome: 'Profit Target',
    outcome_kind: 'profit',
  }
}

describe('ledgerPageKey', () => {
  it('builds page 1 for the default (all agents, 30 days, no search) filter', () => {
    expect(ledgerPageKey(ALL, null)).toBe('/api/live/trades?limit=30&days=30')
  })

  it('adds bot, days and q only when set', () => {
    const key = ledgerPageKey({ agent: 'spark', range: '90', query: 'profit' }, null)
    expect(key).toContain('bot=spark')
    expect(key).toContain('days=90')
    expect(key).toContain('q=profit')
  })

  it('omits days for "all"', () => {
    expect(ledgerPageKey({ agent: 'all', range: 'all', query: '' }, null)).not.toContain('days=')
  })

  it('trims the search query', () => {
    expect(ledgerPageKey({ agent: 'all', range: '30', query: '  spy  ' }, null)).toContain('q=spy')
  })

  it('appends the cursor on later pages', () => {
    expect(ledgerPageKey(ALL, 'abc123')).toContain('cursor=abc123')
  })
})

describe('getLedgerKey', () => {
  it('page 0 ignores previousPageData and never carries a cursor', () => {
    const getKey = getLedgerKey(ALL)
    expect(getKey(0, null)).toBe('/api/live/trades?limit=30&days=30')
  })

  it('later pages use the previous page\'s next_cursor', () => {
    const getKey = getLedgerKey(ALL)
    const prev: LedgerPage = { trades: [], next_cursor: 'xyz', total: 100 }
    expect(getKey(1, prev)).toContain('cursor=xyz')
  })

  it('stops (returns null) once a page reports next_cursor: null', () => {
    const getKey = getLedgerKey(ALL)
    const prev: LedgerPage = { trades: [], next_cursor: null, total: 5 }
    expect(getKey(1, prev)).toBeNull()
  })

  it('a different filter set produces a different key at page 0 — the basis for a paging reset', () => {
    const a = getLedgerKey({ agent: 'all', range: '30', query: '' })(0, null)
    const b = getLedgerKey({ agent: 'spark', range: '30', query: '' })(0, null)
    const c = getLedgerKey({ agent: 'all', range: '90', query: '' })(0, null)
    const d = getLedgerKey({ agent: 'all', range: '30', query: 'stop' })(0, null)
    expect(new Set([a, b, c, d]).size).toBe(4)
  })
})

describe('mergeLedgerPages', () => {
  it('flattens pages in order', () => {
    const pages: LedgerPage[] = [
      { trades: [trade('1', '2026-09-03'), trade('2', '2026-09-02')], next_cursor: 'c1', total: 4 },
      { trades: [trade('3', '2026-09-01'), trade('4', '2026-08-30')], next_cursor: null, total: 4 },
    ]
    expect(mergeLedgerPages(pages).map((t) => t.id)).toEqual(['1', '2', '3', '4'])
  })

  it('de-duplicates a row that appears in more than one loaded page, keeping the first', () => {
    const pages: LedgerPage[] = [
      { trades: [trade('1', '2026-09-03')], next_cursor: 'c1', total: 2 },
      { trades: [trade('1', '2026-09-03'), trade('2', '2026-09-02')], next_cursor: null, total: 2 },
    ]
    expect(mergeLedgerPages(pages).map((t) => t.id)).toEqual(['1', '2'])
  })

  it('returns empty for undefined/empty input', () => {
    expect(mergeLedgerPages(undefined)).toEqual([])
    expect(mergeLedgerPages([])).toEqual([])
  })

  it('skips a not-yet-loaded (undefined) page without breaking order', () => {
    const pages: Array<LedgerPage | undefined> = [
      { trades: [trade('1', '2026-09-03')], next_cursor: 'c1', total: 3 },
      undefined,
      { trades: [trade('2', '2026-09-01')], next_cursor: null, total: 3 },
    ]
    expect(mergeLedgerPages(pages).map((t) => t.id)).toEqual(['1', '2'])
  })
})

describe('ledgerTotal', () => {
  it('reads total off the last loaded page', () => {
    const pages: LedgerPage[] = [
      { trades: [], next_cursor: 'c1', total: 57 },
      { trades: [], next_cursor: null, total: 57 },
    ]
    expect(ledgerTotal(pages)).toBe(57)
  })

  it('is 0 with no pages', () => {
    expect(ledgerTotal(undefined)).toBe(0)
    expect(ledgerTotal([])).toBe(0)
  })
})

describe('ledgerTotals', () => {
  it('reads totals off the last loaded page', () => {
    const pages: LedgerPage[] = [
      { trades: [], next_cursor: 'c1', total: 8, totals: { completed_trades: 8, win_rate: 87.5 } },
      { trades: [], next_cursor: null, total: 8, totals: { completed_trades: 8, win_rate: 87.5 } },
    ]
    expect(ledgerTotals(pages)).toEqual({ completed_trades: 8, win_rate: 87.5 })
  })

  it('null win_rate with 0 completed trades — never "0%"', () => {
    const pages: LedgerPage[] = [
      { trades: [], next_cursor: null, total: 0, totals: { completed_trades: 0, win_rate: null } },
    ]
    expect(ledgerTotals(pages)).toEqual({ completed_trades: 0, win_rate: null })
  })

  it('is undefined with no pages, so the caller shows a skeleton rather than "0"', () => {
    expect(ledgerTotals(undefined)).toBeUndefined()
    expect(ledgerTotals([])).toBeUndefined()
  })

  it('is undefined against an older server response with no totals field yet', () => {
    expect(ledgerTotals([{ trades: [], next_cursor: null, total: 5 }])).toBeUndefined()
  })

  it('a filter change (fewer completed trades in the new population) is reflected once the new page loads', () => {
    const allAgents: LedgerPage = {
      trades: [],
      next_cursor: null,
      total: 20,
      totals: { completed_trades: 20, win_rate: 55 },
    }
    const sparkOnly: LedgerPage = {
      trades: [],
      next_cursor: null,
      total: 8,
      totals: { completed_trades: 8, win_rate: 87.5 },
    }
    expect(ledgerTotals([allAgents])).toEqual({ completed_trades: 20, win_rate: 55 })
    expect(ledgerTotals([sparkOnly])).toEqual({ completed_trades: 8, win_rate: 87.5 })
  })
})

describe('hasMoreLedgerPages', () => {
  it('true before anything has loaded (so the first fetch is armed)', () => {
    expect(hasMoreLedgerPages(undefined)).toBe(true)
  })

  it('true while the last loaded page still has a cursor', () => {
    expect(hasMoreLedgerPages([{ trades: [], next_cursor: 'c1', total: 10 }])).toBe(true)
  })

  it('false once the last loaded page has none', () => {
    expect(hasMoreLedgerPages([{ trades: [], next_cursor: 'c1', total: 10 }, { trades: [], next_cursor: null, total: 10 }])).toBe(
      false,
    )
  })
})
