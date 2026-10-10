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

// #246: 50, matching the server's own default (GET /api/live/trades: "limit
// (default 50, max 200)") — was 30, an app-side number smaller than what the
// server already hands back by default.
export const LEDGER_PAGE_SIZE = 50

export interface LedgerFilters {
  /** 'all' | 'spark' | 'flame' — mirrors the AGENTS control in ledger.tsx.
   *  ('ember' is filtered client-side from a separate endpoint, never sent
   *  here — see ledger.tsx's useEmberLedger.) */
  agent: string
  /** A day-count string ('5' Week / '21' Month / '63' 3 months, per the 10.4
   *  redesign's RANGES in ledger.tsx) or 'all' for all time. Any positive
   *  integer string is accepted — the server (GET /api/live/trades) no
   *  longer restricts this to 30/90. */
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
  const days = Number(filters.range)
  if (filters.range !== 'all' && Number.isFinite(days) && days > 0) params.set('days', String(days))
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

// ---- 10.4 redesign additions: day-grouping, local totals, range chips ----

/**
 * The Ledger redesign's range chips (10.4 app.html `.chips[aria-label=Range]`:
 * Week/Month/3 months/All time) — Week=5 and Month=21 are TRADING-day counts
 * per the mobile addendum, sent straight through as a `days=N` server filter
 * the same way the original 30/90-day chips already did.
 */
export const LEDGER_RANGES = [
  { key: '5', label: 'Week' },
  { key: '21', label: 'Month' },
  { key: '63', label: '3 months' },
  { key: 'all', label: 'All time' },
] as const

/** One day's trades, grouped for the Ledger's day-header rows — newest day
 *  first, trades within a day in whatever order they arrived (the server and
 *  the Ember adapter both already hand back newest-trade-first). */
export interface LedgerDayGroup {
  /** YYYY-MM-DD, the group key. */
  date: string
  /** Sum of pnl across every trade in the group — shown beside the day header. */
  net: number
  trades: HistoryTrade[]
}

/** Groups an already-sorted (newest close_date first) trade list into
 *  per-day buckets without re-sorting — a stable grouping, not a re-ranking,
 *  so ties the server already broke (same-day trades) keep their order. */
export function groupTradesByDay(trades: HistoryTrade[]): LedgerDayGroup[] {
  const groups: LedgerDayGroup[] = []
  const byDate = new Map<string, LedgerDayGroup>()
  for (const t of trades) {
    let g = byDate.get(t.close_date)
    if (!g) {
      g = { date: t.close_date, net: 0, trades: [] }
      byDate.set(t.close_date, g)
      groups.push(g)
    }
    g.trades.push(t)
    g.net = Math.round((g.net + t.pnl) * 100) / 100
  }
  return groups
}

/**
 * The Ledger summary card's totals computed CLIENT-side from a trade list
 * already in hand — used for the Ember path (a separate, un-paginated
 * endpoint with no server-computed `totals`) with the exact same formula
 * the server's computeTradesTotals (trades-history.ts) uses for Spark/Flame,
 * so the two paths never disagree about what "Up %" means.
 */
export function totalsFromTrades(trades: HistoryTrade[]): Required<TradesTotals> {
  const completed_trades = trades.length
  const wins = trades.reduce((a, t) => (t.pnl > 0 ? a + 1 : a), 0)
  const net_pnl = Math.round(trades.reduce((a, t) => a + t.pnl, 0) * 100) / 100
  const win_rate =
    completed_trades === 0 ? null : Math.round((wins / completed_trades) * 1000) / 10
  return { completed_trades, win_rate, net_pnl }
}

/** The CT calendar-date cutoff for a LEDGER_RANGES key N days back from `now`
 *  (inclusive of today), or null for 'all' — used to filter the Ember trade
 *  list client-side the same way `days=N` filters the server-side list. */
export function rangeCutoffDate(rangeKey: string, now: Date = new Date()): string | null {
  if (rangeKey === 'all') return null
  const days = Number(rangeKey)
  if (!Number.isFinite(days) || days <= 0) return null
  const cutoff = new Date(now.getTime() - (days - 1) * 86_400_000)
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(cutoff)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '00'
  return `${get('year')}-${get('month')}-${get('day')}`
}
