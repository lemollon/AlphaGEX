'use client'

import { useRef } from 'react'
import useSWR from 'swr'

import { isAbortError } from '@/lib/botLedger/state'

export class LedgerHttpError extends Error {
  readonly status: number
  readonly code: string
  /** Server correlation id, so a reported failure can be found in the logs. */
  readonly requestId: string | null
  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message)
    this.name = 'LedgerHttpError'
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export interface LedgerResource<T> {
  data: T | undefined
  error: Error | undefined
  /** Nothing to show yet — render skeletons. */
  isLoading: boolean
  /** Revalidating with values already on screen — drives aria-busy. */
  isRefreshing: boolean
  retry: () => void
}

/**
 * SWR with a genuinely abortable fetcher.
 *
 * Stock SWR cannot cancel an in-flight request, and a hand-rolled
 * useEffect+AbortController loses keepPreviousData and the cache. This hybrid
 * gets both:
 *   - `keepPreviousData` keeps prior values visible while refetching, so a
 *     period change never blanks the cards.
 *   - SWR commits per key, so a late response for a superseded key can never
 *     land on the current one.
 *   - The AbortController ref is scoped PER HOOK INSTANCE, so the summary and
 *     the trade log cancel independently — changing the period cannot cancel
 *     the log request.
 */
export function useLedgerResource<T>(key: string | null): LedgerResource<T> {
  const abortRef = useRef<AbortController | null>(null)

  const swr = useSWR<T>(
    key,
    async (url: string) => {
      abortRef.current?.abort()
      const ac = new AbortController()
      abortRef.current = ac

      const res = await fetch(url, { signal: ac.signal, headers: { accept: 'application/json' } })
      if (!res.ok) {
        let code = 'LEDGER_UNAVAILABLE'
        let message = `Request failed (${res.status})`
        let requestId = res.headers.get('x-request-id')
        try {
          const body = (await res.json()) as {
            error?: string
            error_code?: string
            request_id?: string
          }
          if (body?.error_code) code = body.error_code
          if (body?.error) message = body.error
          if (body?.request_id) requestId = body.request_id
        } catch {
          // Non-JSON error body; keep the defaults.
        }
        throw new LedgerHttpError(res.status, code, message, requestId)
      }
      return (await res.json()) as T
    },
    {
      keepPreviousData: true,
      revalidateOnFocus: false,
      revalidateIfStale: false,
      dedupingInterval: 30_000,
      errorRetryCount: 1,
      // An aborted request is us superseding ourselves. Retrying it would
      // resurrect a request we deliberately cancelled.
      shouldRetryOnError: (err) => !isAbortError(err),
    },
  )

  // Without this filter every period toggle would flip a healthy card into the
  // error state, because an aborted fetch rejects with an AbortError.
  const error = swr.error && !isAbortError(swr.error) ? (swr.error as Error) : undefined

  return {
    data: swr.data,
    error,
    isLoading: swr.data === undefined && error === undefined,
    isRefreshing: swr.isValidating && swr.data !== undefined,
    retry: () => {
      void swr.mutate()
    },
  }
}
