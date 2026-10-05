import { describe, it, expect } from 'vitest'
import {
  notificationsPageKey,
  getNotificationsKey,
  mergeNotificationPages,
  hasMoreNotificationPages,
  latestUnreadCount,
  type NotificationsPage,
} from '@/notifications/history'
import type { NotificationItem } from '@/api/types'

function note(id: string, read: boolean): NotificationItem {
  return {
    id,
    kind: 'trade_closed',
    title: 'Trade Closed',
    body: 'Position exited successfully and added to your Ledger.',
    data: { trade_id: id },
    created_at: '2026-09-03T18:00:00.000Z',
    read_at: read ? '2026-09-03T18:05:00.000Z' : null,
  }
}

describe('notificationsPageKey', () => {
  it('builds page 1 with the default limit and no cursor', () => {
    expect(notificationsPageKey(null)).toBe('/api/v1/notifications?limit=20')
  })

  it('appends the cursor on later pages', () => {
    expect(notificationsPageKey('abc123')).toContain('cursor=abc123')
  })
})

describe('getNotificationsKey', () => {
  it('page 0 ignores previousPageData and never carries a cursor', () => {
    const getKey = getNotificationsKey()
    expect(getKey(0, null)).toBe('/api/v1/notifications?limit=20')
  })

  it("later pages use the previous page's next_cursor", () => {
    const getKey = getNotificationsKey()
    const prev: NotificationsPage = { notifications: [], next_cursor: 'xyz', unread_count: 3 }
    expect(getKey(1, prev)).toContain('cursor=xyz')
  })

  it('stops (returns null) once a page reports next_cursor: null', () => {
    const getKey = getNotificationsKey()
    const prev: NotificationsPage = { notifications: [], next_cursor: null, unread_count: 0 }
    expect(getKey(1, prev)).toBeNull()
  })
})

describe('mergeNotificationPages', () => {
  it('flattens pages in order', () => {
    const pages: NotificationsPage[] = [
      { notifications: [note('1', false), note('2', false)], next_cursor: 'c1', unread_count: 4 },
      { notifications: [note('3', true), note('4', true)], next_cursor: null, unread_count: 4 },
    ]
    expect(mergeNotificationPages(pages).map((n) => n.id)).toEqual(['1', '2', '3', '4'])
  })

  it('de-duplicates a row that appears in more than one loaded page, keeping the first', () => {
    const pages: NotificationsPage[] = [
      { notifications: [note('1', false)], next_cursor: 'c1', unread_count: 2 },
      { notifications: [note('1', false), note('2', false)], next_cursor: null, unread_count: 2 },
    ]
    expect(mergeNotificationPages(pages).map((n) => n.id)).toEqual(['1', '2'])
  })

  it('returns empty for undefined/empty input', () => {
    expect(mergeNotificationPages(undefined)).toEqual([])
    expect(mergeNotificationPages([])).toEqual([])
  })
})

describe('hasMoreNotificationPages', () => {
  it('true before anything has loaded', () => {
    expect(hasMoreNotificationPages(undefined)).toBe(true)
  })

  it('true while the last loaded page still has a cursor', () => {
    expect(hasMoreNotificationPages([{ notifications: [], next_cursor: 'c1', unread_count: 0 }])).toBe(true)
  })

  it('false once the last loaded page has none', () => {
    expect(
      hasMoreNotificationPages([
        { notifications: [], next_cursor: 'c1', unread_count: 0 },
        { notifications: [], next_cursor: null, unread_count: 0 },
      ]),
    ).toBe(false)
  })
})

describe('latestUnreadCount', () => {
  it('reads unread_count off the last loaded page', () => {
    const pages: NotificationsPage[] = [
      { notifications: [], next_cursor: 'c1', unread_count: 7 },
      { notifications: [], next_cursor: null, unread_count: 7 },
    ]
    expect(latestUnreadCount(pages)).toBe(7)
  })

  it('is 0 with no pages', () => {
    expect(latestUnreadCount(undefined)).toBe(0)
    expect(latestUnreadCount([])).toBe(0)
  })
})
