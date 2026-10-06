import type { CommunityFeed } from '@/api/types'

/**
 * The post reaction (APP-055 / 10.4 fidelity audit "Reaction").
 *
 * HEART (❤️) is now the primary, tappable reaction — the server's ALLOWED_EMOJI
 * gained ❤️ specifically for the 10.4 redesign (every design screenshot shows a
 * heart, never a flame), so the client no longer has to substitute one emoji the
 * server accepts for the one the design actually shows.
 *
 * FLAME (🔥) is kept as a LEGACY, read-only value: posts reacted to before this
 * change still carry real 🔥 rows from the server and must keep rendering them —
 * community.tsx shows any existing flame count as a small secondary badge next to
 * the heart button, but no UI here ever sends a NEW 🔥 reaction anymore.
 */
export const HEART = '❤️'
export const FLAME = '🔥'

/**
 * Optimistic local toggle for one reaction emoji on one message, mirroring what the
 * server's toggleReaction() does.
 *
 * Extracted so it can be tested: the count is the visible consequence of a tap, and the
 * two ways to get it wrong — going negative, or leaving a stale zero-count entry that
 * renders as a reacted state — both look like the feature is broken.
 */
export function applyReaction(
  cur: CommunityFeed | undefined,
  id: string,
  emoji: string,
): CommunityFeed | undefined {
  if (!cur) return cur
  return {
    ...cur,
    messages: cur.messages.map((m) => {
      if (m.id !== id) return m
      const rest = (m.reactions ?? []).filter((r) => r.emoji !== emoji)
      const current = (m.reactions ?? []).find((r) => r.emoji === emoji)
      const mine = !(current?.mine ?? false)
      // Never below zero. A server that reports a count of 0 with mine=true (or any
      // other drift) must not be able to push this negative on a tap.
      const count = Math.max(0, (current?.count ?? 0) + (mine ? 1 : -1))
      return {
        ...m,
        // Drop the entry entirely once nobody is reacting, rather than leaving a
        // zero-count record that the row would still render.
        reactions: count > 0 || mine ? [...rest, { emoji, count, mine }] : rest,
      }
    }),
  }
}

/** Toggle the heart — the only reaction any UI in this app sends going forward. */
export function applyHeart(cur: CommunityFeed | undefined, id: string): CommunityFeed | undefined {
  return applyReaction(cur, id, HEART)
}

/**
 * Toggle the flame — kept for the pre-10.4 call sites/tests. No screen in the app
 * calls this for a NEW reaction anymore (see applyHeart above); it survives only so
 * legacy behaviour stays provably unchanged.
 */
export function applyFlame(cur: CommunityFeed | undefined, id: string): CommunityFeed | undefined {
  return applyReaction(cur, id, FLAME)
}
