/**
 * Notification history cursor pagination (10.4 gap audit) — the pure paging/merge
 * rules for useSWRInfinite('/api/v1/notifications', ...), kept out of the screen so
 * they are unit-testable without a React Native renderer. Mirrors src/ledger/paging.ts,
 * the established pattern for this app's one other cursor-paginated feed.
 *
 * The server (GET /api/v1/notifications) does the ordering and unread count in SQL
 * and hands back { notifications, next_cursor, unread_count } pages, newest first.
 * This module only has to: (1) build each page's key, (2) tell useSWRInfinite when to
 * stop, and (3) flatten + de-duplicate the pages SWR has accumulated.
 */
import type { NotificationItem } from '@/api/types'

export const NOTIFICATIONS_PAGE_SIZE = 20

export interface NotificationsPage {
  notifications: NotificationItem[]
  next_cursor: string | null
  unread_count: number
}

/** Query string for ONE page — page 1 when `cursor` is null. */
export function notificationsPageKey(cursor: string | null): string {
  const params = new URLSearchParams()
  params.set('limit', String(NOTIFICATIONS_PAGE_SIZE))
  if (cursor) params.set('cursor', cursor)
  return `/api/v1/notifications?${params.toString()}`
}

/** useSWRInfinite's `getKey`. Returning null tells SWR there is nothing more to fetch. */
export function getNotificationsKey() {
  return (pageIndex: number, previousPageData: NotificationsPage | null): string | null => {
    if (previousPageData && !previousPageData.next_cursor) return null
    const cursor = pageIndex === 0 ? null : (previousPageData?.next_cursor ?? null)
    return notificationsPageKey(cursor)
  }
}

/**
 * Flatten the pages SWR has accumulated into one ordered list, de-duplicated by id —
 * same reasoning as mergeLedgerPages: a pull-to-refresh can revalidate an earlier page
 * while later pages are still cached, and a duplicate id would render the row twice.
 */
export function mergeNotificationPages(
  pages: Array<NotificationsPage | undefined> | undefined,
): NotificationItem[] {
  if (!pages || pages.length === 0) return []
  const seen = new Set<string>()
  const out: NotificationItem[] = []
  for (const page of pages) {
    if (!page?.notifications) continue
    for (const n of page.notifications) {
      if (seen.has(n.id)) continue
      seen.add(n.id)
      out.push(n)
    }
  }
  return out
}

/** Whether a "Load more" / onEndReached should be armed. */
export function hasMoreNotificationPages(pages: Array<NotificationsPage | undefined> | undefined): boolean {
  if (!pages || pages.length === 0) return true
  const last = pages[pages.length - 1]
  return !!last?.next_cursor
}

/** The server's unread count, from the most recently loaded page (every page in a
 *  run carries the current total, same convention as ledgerTotal) — this is what the
 *  header bell's dot and the "Mark all read" button both read. */
export function latestUnreadCount(pages: Array<NotificationsPage | undefined> | undefined): number {
  if (!pages || pages.length === 0) return 0
  for (let i = pages.length - 1; i >= 0; i--) {
    const p = pages[i]
    if (p && typeof p.unread_count === 'number') return p.unread_count
  }
  return 0
}
