'use client'

import { useEffect, useRef } from 'react'
import { mutate } from 'swr'
import type { LiveTrade } from '@/lib/live/types'

/**
 * Subscribes to the sub-5-second positions/P&L stream
 * (GET /api/v1/stream/positions) and feeds each push straight into the
 * existing SWR cache for `tradeKey` — the same key the page's 30s
 * `useSWR<LiveTrade>(tradeKey, ...)` poll already owns.
 *
 * This is additive, not a replacement: the 30s poll keeps running underneath
 * it as the fallback. If this browser doesn't support EventSource, if the
 * stream never connects, or if it keeps failing, nothing here throws or
 * blocks rendering — the page just keeps showing whatever the poll last
 * fetched, same as before this hook existed.
 *
 * `enabled` must be false while the viewer's own account state hasn't loaded
 * yet (or is the anonymous/empty conversion state) — a stream has nothing
 * useful to push there, and reopening it in a loop against the server for a
 * page that was never going to show a position is wasted server load.
 */
export function useLivePositionsStream(streamUrl: string, tradeKey: string, enabled: boolean): void {
  const retryCountRef = useRef(0)

  useEffect(() => {
    if (!enabled) return
    if (typeof window === 'undefined' || typeof window.EventSource === 'undefined') return

    let es: EventSource | null = null
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let stopped = false

    const connect = () => {
      if (stopped) return
      es = new EventSource(streamUrl, { withCredentials: true })

      es.addEventListener('positions', (ev: MessageEvent) => {
        retryCountRef.current = 0
        try {
          const data = JSON.parse(ev.data)
          // {empty:true} means this viewer has no account to stream — the 30s
          // poll's own empty-state handling already covers this; don't overwrite
          // a loaded trade with it.
          if (!data || data.empty) return
          // The single-bot payload (this page always passes ?account=<bot>) is
          // byte-for-byte the LiveTrade shape /api/live/trade returns, so it can
          // be written straight into that key's cache with no revalidate.
          void mutate(tradeKey, data as LiveTrade, { revalidate: false })
        } catch {
          // A malformed frame is not a reason to drop a connection that is
          // otherwise working.
        }
      })

      es.addEventListener('error', () => {
        // The browser's own EventSource retries automatically, but a repeated
        // failure (server 429 from the per-viewer stream cap, a proxy that
        // kills long-lived connections, etc.) should back off instead of
        // hammering — the 30s SWR poll on tradeKey is the fallback either way.
        es?.close()
        if (stopped) return
        const delay = Math.min(30_000, 1_000 * 2 ** retryCountRef.current)
        retryCountRef.current += 1
        retryTimer = setTimeout(connect, delay)
      })
    }

    connect()

    return () => {
      stopped = true
      es?.close()
      if (retryTimer) clearTimeout(retryTimer)
    }
  }, [streamUrl, tradeKey, enabled])
}
