/**
 * Unread notification count for the header bell's dot (10.4 gap audit).
 *
 * `limit=1` — the bell only needs the count, not a page of rows, and `unread_count`
 * is computed server-side over the whole table regardless of the page size requested
 * (see GET /api/v1/notifications). Polling matches the other 60s background polls on
 * the Forge tab (summary/home/agents) — frequent enough that a push-driven event
 * (trade closed, approval needed) shows up on the bell within a minute of the push
 * itself, without adding a second streaming connection just for a dot.
 */
import useSWR from 'swr'
import { api } from '@/api/client'
import type { NotificationsPageResponse } from '@/api/types'

export function useUnreadNotificationsCount(): number {
  const { data } = useSWR<NotificationsPageResponse>(
    '/api/v1/notifications?limit=1',
    (p: string) => api<NotificationsPageResponse>(p),
    { refreshInterval: 60_000 },
  )
  return data?.unread_count ?? 0
}
