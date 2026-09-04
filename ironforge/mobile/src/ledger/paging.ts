/**
 * Ledger cursor pagination (APP-020) — the pure paging/merge rules for
 * useSWRInfinite('/api/live/trades', ...), kept out of the screen so they are
 * unit-testable without a React Native renderer.
 *
 * The server (GET /api/live/trades) does the actual cross-bot merge in SQL and
 * hands back { trades, next_cursor, total } pages in stable newest-first order.
 * This module only has to: (1) build the query-string key for each page given the
 * active filters, (2) tell useSWRInfinite when to stop, and (3) flatten the pages
 * SWR has accumulated into one ordered, de-duplicated list.
 */
import type { HistoryTrade, TradesTotals } from '@/api/types'

export const LEDGER_PAGE_SIZE = 30

export interface LedgerFilters {
  /** 'all' | 'spark' | 'flame' — mirrors the AGENTS control in ledger.tsx. */
  agent: string
  /** '30' | '90' | 'all' — mirrors the RANGES control in ledger.tsx. */
  range: string
  /** Free-text search, already trimmed or not — trimmed here. */
  query: string
}

export interface LedgerPage {
  trades: HistoryTrade[]
  next_cursor: string | null
  total: number
  totals?: TradesTotals
  empty?: boolean
}

/** Query string for ONE page — page 1 when `cursor` is null. */
export function ledgerPageKey(filters: LedgerFilters, cursor: string | null): string {
  const params = new URLSearchParams()
  params.set('limit', String(LEDGER_PAGE_SIZE))
  if (filters.agent !== 'all') params.set('bot', filters.agent)
  if (filters.range === '30' || filters.range === '90') params.set('days', filters.range)
  const q = filters.query.trim()
  if (q) params.set('q', q)
  if (cursor) params.set('cursor', cursor)
  return `/api/live/trades?${params.toString()}`
}

/**
 * useSWRInfinite's `getKey`. A fresh function per filter set — the caller must
 * build a new one (and reset SWR's page count to 1) whenever a filter changes;
 * see the "filter change resets" contract in ledger.tsx. Returning null tells
 * SWR there is nothing more to fetch.
 */
export function getLedgerKey(filters: LedgerFilters) {
  return (pageIndex: number, previousPageData: LedgerPage | null): string | null => {
    // A falsy cursor (null, or absent entirely on the { empty: true } no-account
    // response) means "no more pages" — never just `=== null`, since the
    // no-account shape omits the field rather than setting it to null.
    if (previousPageData && !previousPageData.next_cursor) return null
    const cursor = pageIndex === 0 ? null : (previousPageData?.next_cursor ?? null)
    return ledgerPageKey(filters, cursor)
  }
}

/**
 * Flatten the pages SWR has accumulated into one ordered list, de-duplicated by
 * id. The server's cursor already guarantees no page skips or repeats a row, but
 * SWR can revalidate an earlier page (e.g. a pull-to-refresh) while later pages
 * are still cached, and a duplicate id would otherwise render the same card
 * twice. First occurrence wins, so order always matches the server's.
 */
export function mergeLedgerPages(pages: Array<LedgerPage | undefined> | undefined): HistoryTrade[] {
  if (!pages || pages.length === 0) return []
  const seen = new Set<string>()
  const out: HistoryTrade[] = []
  for (const page of pages) {
    if (!page?.trades) continue
    for (const trade of page.trades) {
      if (seen.has(trade.id)) continue
      seen.add(trade.id)
      out.push(trade)
    }
  }
  return out
}

/** The server's count of every row matching the current filters, from the most
 *  recently loaded page (every page in a run carries the same `total`). */
export function ledgerTotal(pages: Array<LedgerPage | undefined> | undefined): number {
  if (!pages || pages.length === 0) return 0
  for (let i = pages.length - 1; i >= 0; i--) {
    const p = pages[i]
    // The empty-account response ({ empty: true, viewer }) has no `total` at
    // all — treat it the same as "0 matching trades" rather than showing
    // "of undefined".
    if (p && typeof p.total === 'number') return p.total
  }
  return 0
}

/** The KPI strip's numbers, from the most recently loaded page (every page in a
 *  run carries the same `totals`, computed over the whole filtered population —
 *  same convention as `ledgerTotal`). Undefined while nothing has loaded yet, or
 *  if an older server build hasn't started sending `totals`. */
export function ledgerTotals(pages: Array<LedgerPage | undefined> | undefined): TradesTotals | undefined {
  if (!pages || pages.length === 0) return undefined
  for (let i = pages.length - 1; i >= 0; i--) {
    const t = pages[i]?.totals
    if (t) return t
  }
  return undefined
}

/** Whether a "Load more" control / onEndReached should be armed. */
export function hasMoreLedgerPages(pages: Array<LedgerPage | undefined> | undefined): boolean {
  if (!pages || pages.length === 0) return true
  const last = pages[pages.length - 1]
  return !!last?.next_cursor
}
