import { describe, it, expect } from 'vitest'
import { encodeTradeCursor, decodeTradeCursor, paginateSorted, classifyLifecycleEvent } from '../trades-history'

describe('trade cursor encode/decode', () => {
  it('round-trips a normal cursor', () => {
    const c = { close_date: '2026-09-01', id: 'SPARK-SPY-20260901-AB12CD' }
    expect(decodeTradeCursor(encodeTradeCursor(c))).toEqual(c)
  })

  it('decodes null/undefined/empty to null', () => {
    expect(decodeTradeCursor(null)).toBeNull()
    expect(decodeTradeCursor(undefined)).toBeNull()
    expect(decodeTradeCursor('')).toBeNull()
  })

  it('decodes garbage input to null rather than throwing', () => {
    expect(decodeTradeCursor('not-a-real-cursor')).toBeNull()
    expect(decodeTradeCursor(Buffer.from('no-separator-here', 'utf8').toString('base64'))).toBeNull()
  })
})

describe('paginateSorted — merge ordering across bots', () => {
  // Simulates exactly what loadMergedRows' SQL (UNION ALL ... ORDER BY
  // ct_date DESC, position_id DESC) hands back: rows from two different
  // bots interleaved by date, ties on the same date broken by id DESC.
  type Row = { bot_key: string; ct_date: string; position_id: string }
  const rows: Row[] = [
    { bot_key: 'spark', ct_date: '2026-09-03', position_id: 'SPARK-Z' },
    { bot_key: 'flame', ct_date: '2026-09-03', position_id: 'FLAME-A' },
    { bot_key: 'spark', ct_date: '2026-09-02', position_id: 'SPARK-B' },
    { bot_key: 'flame', ct_date: '2026-09-01', position_id: 'FLAME-C' },
    { bot_key: 'spark', ct_date: '2026-09-01', position_id: 'FLAME-B' },
  ]
  const sorted = [...rows].sort((a, b) =>
    a.ct_date < b.ct_date ? 1 : a.ct_date > b.ct_date ? -1 : a.position_id < b.position_id ? 1 : -1,
  )

  it('returns a page in the same order as the sorted input', () => {
    const { page } = paginateSorted(sorted, null, 3)
    expect(page).toEqual(sorted.slice(0, 3))
  })

  it('sets next_cursor to null once every row has been served', () => {
    const { next_cursor } = paginateSorted(sorted, null, sorted.length)
    expect(next_cursor).toBeNull()
  })

  it('sets next_cursor to a valid cursor when more rows remain', () => {
    const { next_cursor } = paginateSorted(sorted, null, 2)
    expect(next_cursor).not.toBeNull()
    expect(decodeTradeCursor(next_cursor)).toEqual({ close_date: sorted[1].ct_date, id: sorted[1].position_id })
  })

  it('walking the whole list by cursor covers every row exactly once — no skips, no duplicates', () => {
    const pageSize = 2
    let cursor = decodeTradeCursor(null)
    const seen: string[] = []
    for (let i = 0; i < 10; i++) {
      const { page, next_cursor } = paginateSorted(sorted, cursor, pageSize)
      seen.push(...page.map((r) => r.position_id))
      if (!next_cursor) break
      cursor = decodeTradeCursor(next_cursor)
    }
    expect(seen).toEqual(sorted.map((r) => r.position_id))
    expect(new Set(seen).size).toBe(sorted.length)
  })

  it('a filter change resets paging — cursor=null always restarts from the top', () => {
    const first = paginateSorted(sorted, null, 2)
    const cursor = decodeTradeCursor(first.next_cursor)
    const midway = paginateSorted(sorted, cursor, 2)
    expect(midway.page[0].position_id).not.toBe(first.page[0].position_id)

    const restarted = paginateSorted(sorted, null, 2)
    expect(restarted.page).toEqual(first.page)
  })

  it('an unmatched cursor (row since deleted) lands past the end, not mid-list', () => {
    const { page, next_cursor } = paginateSorted(sorted, { close_date: '2000-01-01', id: 'ZZZ' }, 2)
    expect(page).toEqual([])
    expect(next_cursor).toBeNull()
  })
})

describe('classifyLifecycleEvent — curated labels only, never raw scanner text', () => {
  it('maps known levels to fixed labels', () => {
    expect(classifyLifecycleEvent('TRADE_OPEN', 'AUTO TRADE: SPARK-SPY-20260901-AB12CD ...')).toBe(
      'Position opened',
    )
    expect(classifyLifecycleEvent('TRADE_CLOSE', 'AUTO CLOSE: SPARK-SPY-20260901-AB12CD ...')).toBe(
      'Position closed',
    )
    expect(classifyLifecycleEvent('SWING_HOLD', 'SWING_HOLD_OVERNIGHT pos=SPARK-SPY-20260901-AB12CD ...')).toBe(
      'Held open overnight',
    )
  })

  it('maps CLOSE_TRIGGER reasons by matching the fixed *_FIRED prefix', () => {
    expect(classifyLifecycleEvent('CLOSE_TRIGGER', 'PT_FIRED pos=X tier=1 cost_to_close_last=0.4200')).toBe(
      'Profit target reached',
    )
    expect(classifyLifecycleEvent('CLOSE_TRIGGER', 'STOP_LOSS_FIRED pos=X cost_to_close=1.9000')).toBe(
      'Stop loss triggered',
    )
    expect(classifyLifecycleEvent('CLOSE_TRIGGER', 'EOD_CUTOFF_FIRED pos=X entry_credit=0.5000')).toBe(
      'End-of-day close triggered',
    )
  })

  it('falls back to a generic label for an unrecognized CLOSE_TRIGGER reason, never the raw text', () => {
    const label = classifyLifecycleEvent('CLOSE_TRIGGER', 'SOME_NEW_REASON_FIRED pos=X detail=secret')
    expect(label).toBe('Exit condition detected')
    expect(label).not.toMatch(/SOME_NEW_REASON|secret/)
  })

  it('returns null for internal-only log levels with no customer meaning', () => {
    expect(classifyLifecycleEvent('PT_TIER_ADVANCE', 'anything')).toBeNull()
    expect(classifyLifecycleEvent('CRITICAL', 'anything')).toBeNull()
    expect(classifyLifecycleEvent('PRODUCTION_ORDER', 'anything')).toBeNull()
  })
})
