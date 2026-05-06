'use client'

import { useCallback, useEffect, useMemo } from 'react'
import useSWRInfinite from 'swr/infinite'

const API = process.env.NEXT_PUBLIC_API_URL || ''

export type Trade = {
  bot_id: string
  bot_label: string
  position_id: string
  side: 'long' | 'short'
  quantity: number
  entry_price: number
  close_price: number | null
  realized_pnl: number
  realized_pnl_pct: number | null
  close_reason: string | null
  open_time: string | null
  close_time: string | null
  max_risk_usd: number | null
}

export type TradesPage = {
  trades: Trade[]
  has_more: boolean
  next_cursor: string | null
  window: { since: string | null; until: string | null }
}

export type RangePreset = '7d' | '30d' | '90d' | 'all'
export type Range = RangePreset | { since: Date; until: Date }

export type UseAgapePerpTradesOpts = {
  bots: string[]
  range: Range
  pageSize?: number
}

function rangeToParams(range: Range): { since?: string; until?: string } {
  if (typeof range === 'string') {
    if (range === 'all') return {}
    const days = range === '7d' ? 7 : range === '30d' ? 30 : 90
    const since = new Date(Date.now() - days * 86_400_000).toISOString()
    return { since }
  }
  return { since: range.since.toISOString(), until: range.until.toISOString() }
}

function buildUrl(bots: string[], range: Range, limit: number, before: string | null): string {
  const { since, until } = rangeToParams(range)
  const qs = new URLSearchParams()
  qs.set('bots', bots.join(','))
  qs.set('limit', String(limit))
  if (since) qs.set('since', since)
  if (until) qs.set('until', until)
  if (before) qs.set('before', before)
  return `${API}/api/agape-perpetuals/trades?${qs.toString()}`
}

const fetcher = (url: string) =>
  fetch(url).then(r => {
    if (!r.ok) throw new Error(`API error ${r.status}`)
    return r.json() as Promise<TradesPage>
  })

export function useAgapePerpTrades({ bots, range, pageSize = 100 }: UseAgapePerpTradesOpts) {
  const botsKey = useMemo(() => [...bots].sort().join(','), [bots])
  const rangeKey = useMemo(
    () =>
      typeof range === 'string'
        ? range
        : `${range.since.toISOString()}_${range.until.toISOString()}`,
    [range],
  )

  const getKey = useCallback(
    (pageIndex: number, prevPageData: TradesPage | null) => {
      if (prevPageData && !prevPageData.has_more) return null
      const before = pageIndex === 0 ? null : prevPageData?.next_cursor ?? null
      return ['agape-perp-trades', botsKey, rangeKey, pageIndex, before, pageSize] as const
    },
    [botsKey, rangeKey, pageSize],
  )

  const { data, size, setSize, isLoading, isValidating, error, mutate } = useSWRInfinite<TradesPage>(
    getKey as any,
    async (key: any) => {
      const before = key[4] as string | null
      return fetcher(buildUrl(bots, range, pageSize, before))
    },
    {
      // Don't refetch page 1 every time we load a new page — that would burn
      // a network call on every Load more. The 60s mutate below handles page
      // 1 freshness independently.
      revalidateFirstPage: false,
      refreshInterval: 0,
      dedupingInterval: 30_000,
    },
  )

  // Refresh page 1 every 60s without re-pulling subsequent pages.
  useEffect(() => {
    const id = setInterval(() => mutate(), 60_000)
    return () => clearInterval(id)
  }, [mutate])

  const pages: TradesPage[] = data || []
  const trades = useMemo(() => pages.flatMap(p => p.trades), [pages])
  const lastPage = pages[pages.length - 1]
  const hasMore = !!lastPage?.has_more

  const loadMore = useCallback(() => {
    setSize(s => s + 1)
  }, [setSize])

  const reset = useCallback(() => {
    setSize(1)
    mutate()
  }, [setSize, mutate])

  return {
    trades,
    hasMore,
    loadMore,
    reset,
    isLoading: isLoading && pages.length === 0,
    isLoadingMore: isValidating && pages.length > 0 && size > pages.length - 1,
    error: error as Error | undefined,
  }
}
