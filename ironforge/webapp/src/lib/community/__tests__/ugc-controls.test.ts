import { describe, it, expect, beforeEach, vi } from 'vitest'

/**
 * UGC safety controls — Google Play's User Generated Content policy requires an
 * in-app way to REPORT content and to BLOCK a member. Server-side moderation
 * already runs before persistence, but it is an automated pre-filter and does not
 * satisfy either obligation.
 *
 * The block itself is enforced in SQL, so these tests pin two things a unit test
 * can actually hold: that the feed query still carries the block guard and still
 * binds the viewer to it, and that the store helpers behave at their edges
 * (double-report, self-block, a blocked member whose posts have all gone).
 */

const db = vi.hoisted(() => ({
  queries: [] as Array<{ sql: string; params: unknown[] }>,
  messageRows: [] as any[],
  insertReportReturns: [] as any[],
  blockedRows: [] as any[],
}))

vi.mock('@/lib/customers-db', () => ({
  CustomersDbNotConfiguredError: class extends Error {},
  customerQuery: vi.fn(async (sql: string, params: unknown[] = []) => {
    db.queries.push({ sql, params })
    if (sql.includes('FROM community_channels')) {
      return [{ id: 'chan-1', slug: 'all-chat', name: 'All Chat' }]
    }
    // These two queries now MENTION EACH OTHER'S TABLES: the feed carries a
    // `community_blocks` NOT EXISTS, and listBlocked carries a `community_messages`
    // subquery to resolve a display name. Routing on table names matches both in
    // either order, so route on each one's unique select list instead.
    if (sql.includes('SELECT b.blocked_id')) return db.blockedRows
    if (sql.includes('FROM community_messages m')) return db.messageRows
    if (sql.includes('FROM community_presence')) return []
    if (sql.includes('INSERT INTO community_message_reports')) return db.insertReportReturns
    if (sql.includes('FROM community_messages WHERE id')) {
      return [{ id: 'm1', user_id: 'author-1', sender_name: 'Dana', message: 'hello there' }]
    }
    return []
  }),
  customerExecute: vi.fn(async (sql: string, params: unknown[] = []) => {
    db.queries.push({ sql, params })
    return undefined
  }),
}))

vi.mock('../forge-ai', () => ({
  generateForgeReply: vi.fn(),
  generateScheduledPost: vi.fn(),
  isForgeConfigured: () => false,
  shouldForgeReply: () => false,
}))

import {
  blockUser,
  getFeed,
  getMessageAuthor,
  listBlocked,
  reportMessage,
  unblockUser,
  REPORT_REASONS,
} from '../store'

function feedQuery() {
  return db.queries.find((q) => q.sql.includes('FROM community_messages m'))!
}

beforeEach(() => {
  db.queries = []
  db.messageRows = []
  db.insertReportReturns = []
  db.blockedRows = []
})

describe('feed block guard', () => {
  it('excludes blocked authors and binds the viewer to the guard', async () => {
    await getFeed('all-chat', 'viewer-1')
    const q = feedQuery()
    // The guard itself. If this disappears, blocking silently stops working while
    // every button still reports success.
    expect(q.sql).toContain('community_blocks')
    expect(q.sql).toContain('b.blocker_id = $2::uuid')
    expect(q.sql).toContain('b.blocked_id = m.user_id')
    expect(q.params[1]).toBe('viewer-1')
  })

  it('shows everything to a logged-out viewer instead of nothing', async () => {
    // NULL blocker_id makes the NOT EXISTS vacuously true. Written as NOT EXISTS
    // rather than a join precisely so the anonymous preview is not blanked out.
    db.messageRows = [
      { id: 'm1', user_id: 'author-1', sender_name: 'Dana', sender_type: 'USER', message: 'hi', created_at: new Date().toISOString(), reactions: [] },
    ]
    const feed = await getFeed('all-chat', null)
    expect(feed.messages).toHaveLength(1)
    expect(feedQuery().params[1]).toBeNull()
  })

  it('marks the viewer’s own posts as unblockable', async () => {
    const now = new Date().toISOString()
    db.messageRows = [
      { id: 'm1', user_id: 'viewer-1', sender_name: 'You', sender_type: 'USER', message: 'mine', created_at: now, reactions: [] },
      { id: 'm2', user_id: 'author-2', sender_name: 'Dana', sender_type: 'USER', message: 'theirs', created_at: now, reactions: [] },
      { id: 'm3', user_id: null, sender_name: 'Forge', sender_type: 'FORGE', message: 'bot', created_at: now, reactions: [] },
    ]
    const feed = await getFeed('all-chat', 'viewer-1')
    const byId = Object.fromEntries(feed.messages.map((m) => [m.id, m]))
    expect(byId.m1.mine).toBe(true)
    expect(byId.m1.blockable).toBe(false)
    expect(byId.m2.mine).toBe(false)
    expect(byId.m2.blockable).toBe(true)
    // Forge has no user row to block.
    expect(byId.m3.blockable).toBe(false)
  })
})

describe('reporting', () => {
  it('freezes an excerpt so a deleted post can still be reviewed', async () => {
    db.insertReportReturns = [{ id: 'rep-1' }]
    const author = await getMessageAuthor('m1')
    const result = await reportMessage({
      messageId: 'm1',
      reporterId: 'viewer-1',
      reason: 'SPAM',
      author: author!,
    })
    expect(result).toBe('filed')
    const insert = db.queries.find((q) => q.sql.includes('INSERT INTO community_message_reports'))!
    expect(insert.params).toContain('hello there')
    expect(insert.params).toContain('author-1')
  })

  it('treats a second report from the same person as already filed', async () => {
    // ON CONFLICT DO NOTHING returns no row. A double-tap must not read as a failure
    // to the reporter, nor inflate the moderation queue.
    db.insertReportReturns = []
    const author = await getMessageAuthor('m1')
    await expect(
      reportMessage({ messageId: 'm1', reporterId: 'viewer-1', reason: 'OTHER', author: author! }),
    ).resolves.toBe('already_reported')
  })

  it('keeps the reason allowlist in one place', () => {
    expect([...REPORT_REASONS]).toEqual(['SPAM', 'HARASSMENT', 'HATE', 'ADVICE', 'OTHER'])
  })
})

describe('blocking', () => {
  it('is idempotent', async () => {
    await blockUser('viewer-1', 'author-1')
    const q = db.queries.find((x) => x.sql.includes('INSERT INTO community_blocks'))!
    expect(q.sql).toContain('ON CONFLICT DO NOTHING')
    expect(q.params).toEqual(['viewer-1', 'author-1'])
  })

  it('unblocks only the viewer’s own row', async () => {
    await unblockUser('viewer-1', 'author-1')
    const q = db.queries.find((x) => x.sql.includes('DELETE FROM community_blocks'))!
    expect(q.sql).toContain('blocker_id = $1::uuid')
    expect(q.sql).toContain('blocked_id = $2::uuid')
  })

  it('still names a blocked member whose posts have all gone', async () => {
    // Otherwise the row renders blank and there is nothing to press Unblock next to.
    db.blockedRows = [{ blocked_id: 'author-1', display_name: null, created_at: new Date().toISOString() }]
    const [row] = await listBlocked('viewer-1')
    expect(row.display_name).toBe('Blocked member')
    expect(row.user_id).toBe('author-1')
  })
})
