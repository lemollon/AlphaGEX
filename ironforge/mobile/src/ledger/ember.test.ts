import { describe, it, expect } from 'vitest'
import { emberClosedTradesToHistory } from './ember'
import type { EmberTradeRow } from '@/api/types'

const row = (over: Partial<EmberTradeRow> = {}): EmberTradeRow => ({
  id: 1,
  opened_at: '2026-10-03T14:35:00Z',
  closed_at: '2026-10-03T18:20:00Z',
  symbol: 'SHIB-USD',
  legs: null,
  qty: '140',
  entry_price: '0.0000123',
  exit_price: '0.0000130',
  pnl: '4.52',
  status: 'closed',
  source_ref: 'shib|2026-10-03',
  ...over,
})

describe('emberClosedTradesToHistory', () => {
  it('maps a closed row into HistoryTrade shape, CT-formatted', () => {
    const [t] = emberClosedTradesToHistory([row()])
    expect(t.id).toBe('ember-1')
    expect(t.bot).toBe('ember')
    expect(t.strategy).toBe('Ember')
    expect(t.underlying).toBe('SHIB-USD')
    expect(t.close_date).toBe('2026-10-03')
    expect(t.pnl).toBe(4.52)
    expect(t.contracts).toBe(140)
    expect(t.outcome_kind).toBe('profit')
  })

  it('drops open positions — only closed rows belong in the Ledger', () => {
    const rows = [row({ status: 'open', closed_at: null, pnl: null })]
    expect(emberClosedTradesToHistory(rows)).toEqual([])
  })

  it('negative pnl maps to the stop (loss) outcome kind', () => {
    const [t] = emberClosedTradesToHistory([row({ pnl: '-2.10' })])
    expect(t.outcome_kind).toBe('stop')
    expect(t.pnl).toBe(-2.1)
  })

  it('exactly-zero pnl is neither a win nor a loss', () => {
    const [t] = emberClosedTradesToHistory([row({ pnl: '0' })])
    expect(t.outcome_kind).toBe('other')
  })

  it('a null qty defaults to 1 contract rather than 0', () => {
    const [t] = emberClosedTradesToHistory([row({ qty: null })])
    expect(t.contracts).toBe(1)
  })
})
