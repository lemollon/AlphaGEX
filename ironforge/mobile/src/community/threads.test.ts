import { describe, it, expect } from 'vitest'
import {
  appendOptimisticReply,
  applyFlameToReply,
  bumpReplyCount,
  reconcileReply,
  removeReply,
} from '@/community/threads'
import { FLAME } from '@/community/reactions'
import type { CommunityFeedV2, CommunityMessageV2, ThreadReplies } from '@/api/types'

function reply(over: Partial<CommunityMessageV2> = {}): CommunityMessageV2 {
  return {
    id: 'r1',
    sender_name: 'Jordan M.',
    sender_type: 'USER',
    message: 'good point',
    created_at: '2026-09-03T14:00:00Z',
    reactions: [],
    parent_id: 'm1',
    ...over,
  }
}

function thread(...replies: CommunityMessageV2[]): ThreadReplies {
  return { replies, next_cursor: null }
}

function feed(...messages: CommunityMessageV2[]): CommunityFeedV2 {
  return { channels: [], messages, online_count: 0, members: [] }
}

describe('appendOptimisticReply', () => {
  it('appends the reply', () => {
    const out = appendOptimisticReply(thread(), reply())
    expect(out.replies).toHaveLength(1)
    expect(out.replies[0].id).toBe('r1')
  })

  it('appends onto existing replies without disturbing them', () => {
    const out = appendOptimisticReply(thread(reply({ id: 'r0' })), reply({ id: 'r1' }))
    expect(out.replies.map((r) => r.id)).toEqual(['r0', 'r1'])
  })

  it('does not duplicate the same optimistic row twice', () => {
    const out = appendOptimisticReply(thread(reply({ id: 'temp-1' })), reply({ id: 'temp-1' }))
    expect(out.replies).toHaveLength(1)
  })

  it('starts a thread from nothing', () => {
    const out = appendOptimisticReply(undefined, reply())
    expect(out.replies).toHaveLength(1)
    expect(out.next_cursor).toBeNull()
  })
})

describe('reconcileReply', () => {
  it('replaces the optimistic row with the server copy', () => {
    const optimistic = reply({ id: 'temp-1', message: 'good point' })
    const server = reply({ id: 'real-99', message: 'good point' })
    const out = reconcileReply(thread(optimistic), 'temp-1', server)
    expect(out.replies).toHaveLength(1)
    expect(out.replies[0].id).toBe('real-99')
  })

  it('does not leave the temp row alongside the real one', () => {
    const out = reconcileReply(thread(reply({ id: 'temp-1' })), 'temp-1', reply({ id: 'real-99' }))
    expect(out.replies.map((r) => r.id)).not.toContain('temp-1')
  })

  it('is a no-op duplicate-wise if the server row already arrived via poll', () => {
    const out = reconcileReply(
      thread(reply({ id: 'temp-1' }), reply({ id: 'real-99' })),
      'temp-1',
      reply({ id: 'real-99' }),
    )
    expect(out.replies.filter((r) => r.id === 'real-99')).toHaveLength(1)
  })

  it('reconciles onto an undefined thread', () => {
    const out = reconcileReply(undefined, 'temp-1', reply({ id: 'real-99' }))
    expect(out.replies.map((r) => r.id)).toEqual(['real-99'])
  })
})

describe('removeReply', () => {
  it('drops a failed optimistic reply', () => {
    const out = removeReply(thread(reply({ id: 'temp-1' }), reply({ id: 'r0' })), 'temp-1')
    expect(out.replies.map((r) => r.id)).toEqual(['r0'])
  })
})

describe('bumpReplyCount', () => {
  it('increments the parent post reply_count', () => {
    const out = bumpReplyCount(feed({ ...reply({ id: 'm1', parent_id: null, reply_count: 2 }) }), 'm1', 1)
    expect(out!.messages[0].reply_count).toBe(3)
  })

  it('treats a missing reply_count as zero', () => {
    const out = bumpReplyCount(feed({ ...reply({ id: 'm1', parent_id: null }) }), 'm1', 1)
    expect(out!.messages[0].reply_count).toBe(1)
  })

  it('rolls back on failure without going below zero', () => {
    const withOne = bumpReplyCount(feed({ ...reply({ id: 'm1', parent_id: null, reply_count: 0 }) }), 'm1', 1)
    const rolledBack = bumpReplyCount(withOne, 'm1', -1)
    const rolledBackAgain = bumpReplyCount(rolledBack, 'm1', -1)
    expect(rolledBack!.messages[0].reply_count).toBe(0)
    expect(rolledBackAgain!.messages[0].reply_count).toBe(0)
  })

  it('touches only the targeted message', () => {
    const out = bumpReplyCount(
      feed({ ...reply({ id: 'm1', parent_id: null, reply_count: 0 }) }, { ...reply({ id: 'm2', parent_id: null, reply_count: 5 }) }),
      'm1',
      1,
    )
    expect(out!.messages.find((m) => m.id === 'm2')!.reply_count).toBe(5)
  })

  it('is a no-op on an undefined feed', () => {
    expect(bumpReplyCount(undefined, 'm1', 1)).toBeUndefined()
  })
})

describe('applyFlameToReply — duplicate flame prevented', () => {
  it('adds my flame from nothing', () => {
    const out = applyFlameToReply(thread(reply({ id: 'r1' })), 'r1')
    const r = out!.replies[0].reactions!.find((x) => x.emoji === FLAME)
    expect(r).toEqual({ emoji: FLAME, count: 1, mine: true })
  })

  it('a second tap removes it rather than stacking a second flame', () => {
    const once = applyFlameToReply(thread(reply({ id: 'r1' })), 'r1')
    const twice = applyFlameToReply(once, 'r1')
    const r = twice!.replies[0].reactions!.find((x) => x.emoji === FLAME)
    expect(r).toBeUndefined()
  })

  it('never produces a negative or double count from inconsistent server state', () => {
    const out = applyFlameToReply(
      thread(reply({ id: 'r1', reactions: [{ emoji: FLAME, count: 0, mine: true }] })),
      'r1',
    )
    const r = out!.replies[0].reactions!.find((x) => x.emoji === FLAME)
    expect(r).toBeUndefined()
  })

  it('touches only the targeted reply', () => {
    const out = applyFlameToReply(thread(reply({ id: 'r1' }), reply({ id: 'r2' })), 'r2')
    expect(out!.replies.find((r) => r.id === 'r1')!.reactions).toEqual([])
    expect(out!.replies.find((r) => r.id === 'r2')!.reactions!.find((x) => x.emoji === FLAME)?.mine).toBe(true)
  })

  it('is a no-op on an undefined thread', () => {
    expect(applyFlameToReply(undefined, 'r1')).toBeUndefined()
  })
})
