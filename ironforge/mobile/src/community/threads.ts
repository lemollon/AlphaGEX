import type { CommunityFeedV2, CommunityMessageV2, ThreadReplies } from '@/api/types'
import { FLAME } from './reactions'

/**
 * Thread state helpers (APP-055 / APP-031 reply part).
 *
 * Pure, mirroring reactions.ts: the thread sheet does two optimistic things when a
 * member posts a reply — append the reply to the open thread, and bump the parent's
 * visible reply_count in the main feed — then reconciles both against the server once
 * the POST resolves (or rolls them back if it fails). Extracted here rather than
 * inlined in the screen so each step can be tested against the two ways a naive
 * version gets this wrong: a duplicate row once the real one arrives, and a count
 * that never comes back down after a failed send.
 */

/**
 * Append a freshly-sent reply to a thread's list.
 *
 * Guards against appending the same optimistic row twice — a fast double-tap on
 * Send, or a retried mutate() call — by id.
 */
export function appendOptimisticReply(
  cur: ThreadReplies | undefined,
  reply: CommunityMessageV2,
): ThreadReplies {
  const existing = cur?.replies ?? []
  if (existing.some((r) => r.id === reply.id)) {
    return { replies: existing, next_cursor: cur?.next_cursor ?? null }
  }
  return { replies: [...existing, reply], next_cursor: cur?.next_cursor ?? null }
}

/**
 * Swap an optimistic reply for the server's copy once the POST resolves.
 *
 * Matches by the temp id and replaces it with the real row — never appends
 * alongside it — so the thread shows one reply, not two, and a later poll that
 * returns the same server id is a no-op rather than a third copy.
 */
export function reconcileReply(
  cur: ThreadReplies | undefined,
  tempId: string,
  serverReply: CommunityMessageV2,
): ThreadReplies {
  const withoutTemp = (cur?.replies ?? []).filter((r) => r.id !== tempId && r.id !== serverReply.id)
  return { replies: [...withoutTemp, serverReply], next_cursor: cur?.next_cursor ?? null }
}

/** Drop a reply whose POST failed — the send failed, so the optimistic row must go. */
export function removeReply(cur: ThreadReplies | undefined, id: string): ThreadReplies {
  return { replies: (cur?.replies ?? []).filter((r) => r.id !== id), next_cursor: cur?.next_cursor ?? null }
}

/**
 * Bump one message's reply_count by one — the feed-side half of an optimistic
 * reply post. `delta` is 1 when a reply is sent and -1 to roll it back on failure;
 * never lets the count go below zero regardless of how it drifted.
 */
export function bumpReplyCount(
  cur: CommunityFeedV2 | undefined,
  parentId: string,
  delta: 1 | -1,
): CommunityFeedV2 | undefined {
  if (!cur) return cur
  return {
    ...cur,
    messages: cur.messages.map((m) =>
      m.id === parentId ? { ...m, reply_count: Math.max(0, (m.reply_count ?? 0) + delta) } : m,
    ),
  }
}

/**
 * Toggle the flame on one reply inside an open thread.
 *
 * Same rules as applyFlame() in reactions.ts (never negative, drop a zero-count
 * entry rather than leaving a stale one), scoped to a thread's replies array
 * instead of a feed's messages — the two lists never share a cache key, so the
 * feed's flame toggle can't reach a reply and this can't reach the feed. Prevents
 * a duplicate flame the same way applyFlame does: toggling is idempotent per tap,
 * so two rapid taps on an already-mine flame both apply the SAME removal, they
 * don't stack a second entry.
 */
export function applyFlameToReply(
  cur: ThreadReplies | undefined,
  id: string,
): ThreadReplies | undefined {
  if (!cur) return cur
  return {
    ...cur,
    replies: cur.replies.map((r) => {
      if (r.id !== id) return r
      const rest = (r.reactions ?? []).filter((x) => x.emoji !== FLAME)
      const flame = (r.reactions ?? []).find((x) => x.emoji === FLAME)
      const mine = !(flame?.mine ?? false)
      const count = Math.max(0, (flame?.count ?? 0) + (mine ? 1 : -1))
      return {
        ...r,
        reactions: count > 0 || mine ? [...rest, { emoji: FLAME, count, mine }] : rest,
      }
    }),
  }
}
