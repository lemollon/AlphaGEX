/**
 * Wire types shared between the webapp (server + web client) and the mobile
 * app (#225). The two apps have no npm workspace — each owns its own tree,
 * installed and built independently — so every response shape used to be
 * hand-kept in sync: see the "hand-written mirror" comments this file
 * replaces in mobile/src/api/types.ts, mobile/src/enroll/types.ts and
 * webapp/src/lib/community/store.ts. A field renamed on one side and missed
 * on the other used to be a silent runtime bug, not a compile error.
 *
 * Pure type-level — every export here is an `interface`/`type`, never a
 * value — so neither bundler ships this file in a real artifact as long as
 * importers use `import type`, which both apps do. The file still needs to
 * be resolvable by each project's TypeScript config (and Metro's bundler,
 * for the rare case a non-type-only import slips in), which is what the
 * `@ironforge/shared/*` path alias in both tsconfigs, webapp's
 * `experimental.externalDir`, and mobile's metro.config.js watchFolders are
 * for — see those files' comments.
 *
 * Field optionality follows mobile's existing convention, not webapp's
 * stricter internal one: an installed app can be older or newer than the
 * API it's talking to, so a field the server may not always send must not
 * fail the type for either caller. Every current caller on both sides
 * already treats these fields defensively (`?? 0`, `if (!x) return null`,
 * truthy checks), so this does not loosen anything either side actually
 * relied on being required.
 */

/**
 * Who authored a Community post (#248). 'member' | 'sparky' | 'flame_ai' are
 * the typed values the server sets at insert time going forward. 'USER' |
 * 'FORGE' | 'SYSTEM' are the legacy values already sitting on rows written
 * before that migration — kept, not backfilled.
 */
export type CommunitySenderType = 'USER' | 'FORGE' | 'SYSTEM' | 'member' | 'sparky' | 'flame_ai'

/** One Forge Community post or reply. */
export interface CommunityMessage {
  id: string
  sender_name: string
  sender_type: CommunitySenderType
  message: string
  created_at: string
  reactions: Array<{ emoji: string; count: number; mine: boolean }>
  /** The channel the post was written in — present once a server supports UX-005's
   *  per-post channel tagging; absent on an older server. */
  channel_slug?: string
  channel_name?: string
  /** The viewer wrote this. Absent is treated as "not mine" by every caller. */
  mine?: boolean
  /** Author is a real member who can be blocked (false for AI/system posts). */
  blockable?: boolean
  /** How many replies this post has. Only meaningful on top-level feed rows. */
  reply_count?: number
  /** The message this is a reply to. Present on rows returned by the replies endpoint. */
  parent_id?: string | null
}

/** GET /api/community/messages?channel=… */
export interface CommunityFeed {
  channels: Array<{ slug: string; name: string }>
  messages: CommunityMessage[]
  online_count: number
  members: Array<{ name: string; you: boolean }>
}

/** GET /api/community/messages/{id}/replies */
export interface ThreadRepliesResponse {
  replies: CommunityMessage[]
  next_cursor: string | null
}

/** GET /api/community/blocks — the viewer's own block list. */
export interface BlockedMember {
  user_id: string
  display_name: string
  created_at: string
}

/** GET /api/public/plans — additive, unauthenticated plan catalogue. Real prices,
 *  never a mock constant, for both the web and mobile /enroll/plan screens. */
export interface PlanCatalog {
  community: { key: string; name: string; price_monthly: number }
  bots: Array<{ slug: 'spark' | 'flame'; name: string; blurb: string; price_monthly: number; accent: string }>
  both: { price_monthly: number }
  trial_days: number
}
