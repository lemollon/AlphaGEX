import { describe, it, expect, beforeEach, vi } from 'vitest'

/**
 * #218's retry half — a held post (community_pending_messages, written when the
 * scorer itself errors) must not be stuck forever. retryPendingModeration()
 * re-scores every held row; publishPendingMessage()/rejectPendingMessage() are
 * the two resolutions it (and the operator ops/community-pending-posts route)
 * can reach.
 *
 * Same vi.mock pattern as ugc-controls.test.ts: route on each query's unique
 * SQL fragment rather than table name, since more than one query here touches
 * community_pending_messages / community_messages / community_moderation_events.
 */

const db = vi.hoisted(() => ({
  queries: [] as Array<{ sql: string; params: unknown[] }>,
  pendingRows: [] as any[],
  insertMessageReturns: [] as any[],
}))

vi.mock('@/lib/customers-db', () => ({
  CustomersDbNotConfiguredError: class extends Error {},
  isCustomersDbConfigured: () => true,
  customerQuery: vi.fn(async (sql: string, params: unknown[] = []) => {
    db.queries.push({ sql, params })
    if (sql.includes('FROM community_pending_messages p')) return db.pendingRows
    if (sql.includes('INSERT INTO community_messages')) return db.insertMessageReturns
    return []
  }),
  customerExecute: vi.fn(async (sql: string, params: unknown[] = []) => {
    db.queries.push({ sql, params })
    return undefined
  }),
}))

const { moderateMessage } = vi.hoisted(() => ({ moderateMessage: vi.fn() }))

vi.mock('../forge-ai', () => ({
  generateForgeReply: vi.fn(),
  generateScheduledPost: vi.fn(),
  isForgeConfigured: () => false,
  shouldForgeReply: () => false,
  moderateMessage,
}))

import {
  retryPendingModeration,
  publishPendingMessage,
  rejectPendingMessage,
  listPendingMessages,
  type PendingMessage,
} from '../store'

/** A raw DB row (what customerQuery resolves with — joined channel columns). */
function row(over: Partial<any> = {}) {
  return pending(over)
}

function pending(over: Partial<PendingMessage> = {}): PendingMessage {
  return {
    id: 'pend-1',
    channel_id: 'chan-1',
    channel_slug: 'market-talk',
    channel_name: 'Market Talk',
    user_id: 'viewer-1',
    sender_name: 'Dana',
    message: 'A perfectly normal message about the range today.',
    parent_id: null,
    reason: 'MODERATION_UNAVAILABLE',
    created_at: new Date().toISOString(),
    ...over,
  }
}

beforeEach(() => {
  db.queries = []
  db.pendingRows = []
  db.insertMessageReturns = []
  moderateMessage.mockReset()
})

describe('listPendingMessages', () => {
  it('maps the joined channel columns and orders oldest first in SQL', async () => {
    db.pendingRows = [row()]
    const rows = await listPendingMessages(50)
    expect(rows).toHaveLength(1)
    expect(rows[0].channel_slug).toBe('market-talk')
    const q = db.queries.find((x) => x.sql.includes('FROM community_pending_messages p'))!
    expect(q.sql).toContain('ORDER BY p.created_at ASC')
    expect(q.params).toEqual([50])
  })
})

describe('publishPendingMessage', () => {
  it('writes into community_messages as a typed member post and clears the pending row', async () => {
    db.insertMessageReturns = [{ id: 'msg-1' }]
    const messageId = await publishPendingMessage(pending())
    expect(messageId).toBe('msg-1')

    const insert = db.queries.find((x) => x.sql.includes('INSERT INTO community_messages'))!
    expect(insert.params).toContain('member')
    expect(insert.params).toContain('A perfectly normal message about the range today.')

    const del = db.queries.find((x) => x.sql.includes('DELETE FROM community_pending_messages'))!
    expect(del.params).toEqual(['pend-1'])
  })
})

describe('rejectPendingMessage', () => {
  it('logs a REJECTED moderation event and clears the pending row', async () => {
    await rejectPendingMessage(pending(), { category: 'SPAM_DETECTED', score: 0.9 })

    const insert = db.queries.find((x) => x.sql.includes('INSERT INTO community_moderation_events'))!
    expect(insert.params).toEqual(['viewer-1', 'A perfectly normal message about the range today.', 'SPAM_DETECTED', 0.9])
    expect(insert.sql).toContain("'REJECTED'")

    const del = db.queries.find((x) => x.sql.includes('DELETE FROM community_pending_messages'))!
    expect(del.params).toEqual(['pend-1'])
  })

  it('defaults the category to OPERATOR_REJECTED when none is given (the ops route path)', async () => {
    await rejectPendingMessage(pending())
    const insert = db.queries.find((x) => x.sql.includes('INSERT INTO community_moderation_events'))!
    expect(insert.params[2]).toBe('OPERATOR_REJECTED')
  })
})

describe('retryPendingModeration', () => {
  it('publishes a held post once the scorer finally clears it', async () => {
    db.pendingRows = [row()]
    db.insertMessageReturns = [{ id: 'msg-1' }]
    moderateMessage.mockResolvedValue({ ok: true })

    const r = await retryPendingModeration()
    expect(r).toEqual({ checked: 1, published: 1, rejected: 0, stillPending: 0 })
    expect(db.queries.some((q) => q.sql.includes('INSERT INTO community_messages'))).toBe(true)
  })

  it('rejects a held post once the scorer gives a real REJECTED verdict', async () => {
    db.pendingRows = [row()]
    moderateMessage.mockResolvedValue({ ok: false, category: 'PROFANITY_DETECTED', score: 1 })

    const r = await retryPendingModeration()
    expect(r).toEqual({ checked: 1, published: 0, rejected: 1, stillPending: 0 })
    const insert = db.queries.find((q) => q.sql.includes('INSERT INTO community_moderation_events'))!
    expect(insert.params[2]).toBe('PROFANITY_DETECTED')
  })

  it('leaves a post pending — never auto-published, never auto-rejected — while the scorer keeps erroring', async () => {
    db.pendingRows = [row()]
    moderateMessage.mockResolvedValue({ ok: false, pending: true, category: 'MODERATION_UNAVAILABLE' })

    const r = await retryPendingModeration()
    expect(r).toEqual({ checked: 1, published: 0, rejected: 0, stillPending: 1 })
    expect(db.queries.some((q) => q.sql.includes('INSERT INTO community_messages'))).toBe(false)
    expect(db.queries.some((q) => q.sql.includes('DELETE FROM community_pending_messages'))).toBe(false)
  })

  it('processes a mixed batch independently — one bad apple does not block the rest', async () => {
    db.pendingRows = [row({ id: 'pend-1' }), row({ id: 'pend-2' }), row({ id: 'pend-3' })]
    db.insertMessageReturns = [{ id: 'msg-1' }]
    moderateMessage
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({ ok: false, pending: true })
      .mockResolvedValueOnce({ ok: false, category: 'SPAM_DETECTED' })

    const r = await retryPendingModeration()
    expect(r).toEqual({ checked: 3, published: 1, rejected: 1, stillPending: 1 })
  })

  it('passes the batch limit straight through to the query', async () => {
    db.pendingRows = []
    await retryPendingModeration(5)
    const q = db.queries.find((x) => x.sql.includes('FROM community_pending_messages p'))!
    expect(q.params).toEqual([5])
  })

  it('is a no-op on an empty queue', async () => {
    db.pendingRows = []
    const r = await retryPendingModeration()
    expect(r).toEqual({ checked: 0, published: 0, rejected: 0, stillPending: 0 })
    expect(moderateMessage).not.toHaveBeenCalled()
  })
})
