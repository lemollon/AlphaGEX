/**
 * 2026-10-02 FLAME-SPY-20261002-Y7RZKZ: the broker closed the 768/766 put spread
 * (multileg sell-to-close REJECTED, then BTC 768 @0.38 and STC 766 @0.08 filled
 * as single legs) but the app kept firing an unfillable close every minute and
 * showed the trade open. findTodaySpreadCloseFill must recover the real $0.30
 * net debit from the broker's own order history.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

vi.mock('../db', () => ({
  query: vi.fn().mockResolvedValue([]),
  dbExecute: vi.fn().mockResolvedValue(1),
  botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
  num: (v: any) => (v == null || v === '' ? 0 : parseFloat(v)),
  int: (v: any) => (v == null || v === '' ? 0 : parseInt(v, 10)),
  CT_TODAY: "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date",
}))

import { findTodaySpreadCloseFill } from '../tradier'

const SHORT = 'SPY261002P00768000'
const LONG = 'SPY261002P00766000'
const nowIso = new Date().toISOString()
const PROD = 'https://api.tradier.com/v1'

function respond(body: unknown) {
  mockFetch.mockResolvedValue({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })
}

describe('findTodaySpreadCloseFill', () => {
  beforeEach(() => mockFetch.mockReset())

  it('books the broker net debit from single-leg fills after a rejected multileg', async () => {
    respond({ orders: { order: [
      { id: 100, class: 'multileg', status: 'filled', create_date: nowIso, leg: [
        { option_symbol: SHORT, side: 'sell_to_open', exec_quantity: '4', avg_fill_price: '0.30', status: 'filled' },
        { option_symbol: LONG, side: 'buy_to_open', exec_quantity: '4', avg_fill_price: '0.08', status: 'filled' },
      ] },
      { id: 101, class: 'option', status: 'rejected', create_date: nowIso, option_symbol: LONG, side: 'sell_to_close', quantity: '4', exec_quantity: '0' },
      { id: 102, class: 'option', status: 'filled', create_date: nowIso, option_symbol: SHORT, side: 'buy_to_close', quantity: '4', exec_quantity: '4', avg_fill_price: '0.38' },
      { id: 103, class: 'option', status: 'filled', create_date: nowIso, option_symbol: LONG, side: 'sell_to_close', quantity: '4', exec_quantity: '4', avg_fill_price: '0.08' },
    ] } })
    const fill = await findTodaySpreadCloseFill('k', 'ACCT', PROD, SHORT, LONG)
    expect(fill).not.toBeNull()
    expect(fill!.net).toBeCloseTo(0.30, 6)
    expect(fill!.orderId).toBe(103)
  })

  it('returns null when no closing fill exists — never invents a price', async () => {
    respond({ orders: { order: [
      { id: 100, class: 'multileg', status: 'filled', create_date: nowIso, leg: [
        { option_symbol: SHORT, side: 'sell_to_open', exec_quantity: '4', avg_fill_price: '0.30', status: 'filled' },
      ] },
    ] } })
    expect(await findTodaySpreadCloseFill('k', 'ACCT', PROD, SHORT, LONG)).toBeNull()
  })

  it('ignores closes from a previous day', async () => {
    respond({ orders: { order: [
      { id: 90, class: 'option', status: 'filled', create_date: '2020-01-02T15:00:00.000Z', option_symbol: SHORT, side: 'buy_to_close', exec_quantity: '4', avg_fill_price: '0.50' },
    ] } })
    expect(await findTodaySpreadCloseFill('k', 'ACCT', PROD, SHORT, LONG)).toBeNull()
  })
})
