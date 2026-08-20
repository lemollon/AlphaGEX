import type { CommunityFeed } from '@/api/types'

/**
 * The flame reaction (APP-055).
 *
 * 🔥 and not the mockup's ❤️ on purpose: the requirement says "one flame reaction per
 * post", and the server's ALLOWED_EMOJI is 👍🔥💯😂🎯🙌 — there is no heart to send, so a
 * heart would be rejected on arrival.
 */
export const FLAME = '🔥'

/**
 * Optimistic local toggle, mirroring what the server's toggleReaction() does.
 *
 * Extracted so it can be tested: the count is the visible consequence of a tap, and the
 * two ways to get it wrong — going negative, or leaving a stale zero-count entry that
 * renders as a reacted state — both look like the feature is broken.
 */
export function applyFlame(
  cur: CommunityFeed | undefined,
  id: string,
): CommunityFeed | undefined {
  if (!cur) return cur
  return {
    ...cur,
    messages: cur.messages.map((m) => {
      if (m.id !== id) return m
      const rest = (m.reactions ?? []).filter((r) => r.emoji !== FLAME)
      const flame = (m.reactions ?? []).find((r) => r.emoji === FLAME)
      const mine = !(flame?.mine ?? false)
      // Never below zero. A server that reports a count of 0 with mine=true (or any
      // other drift) must not be able to push this negative on a tap.
      const count = Math.max(0, (flame?.count ?? 0) + (mine ? 1 : -1))
      return {
        ...m,
        // Drop the entry entirely once nobody is reacting, rather than leaving a
        // zero-count record that the row would still render.
        reactions: count > 0 || mine ? [...rest, { emoji: FLAME, count, mine }] : rest,
      }
    }),
  }
}
