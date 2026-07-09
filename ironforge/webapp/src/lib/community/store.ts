import { customerQuery, customerExecute } from '@/lib/customers-db'
import {
  generateForgeReply,
  generateScheduledPost,
  isForgeConfigured,
  shouldForgeReply,
  type ForgeSlot,
} from './forge-ai'

/**
 * Forge Community data layer — all tables live in the customers DB
 * (customer identity is there; see customers-db.ts INIT_DDL).
 * Realtime = SWR polling on GET /api/community/messages (no websockets
 * in this single-service stack).
 */

export const FORGE_NAME = 'Forge'
export const DEFAULT_CHANNEL = 'all-chat'

export interface CommunityMessage {
  id: string
  sender_name: string
  sender_type: 'USER' | 'FORGE' | 'SYSTEM'
  message: string
  created_at: string
  reactions: Array<{ emoji: string; count: number; mine: boolean }>
}

export interface CommunityFeed {
  channels: Array<{ slug: string; name: string }>
  messages: CommunityMessage[]
  online_count: number
  members: Array<{ name: string; you: boolean }>
}

export async function getChannelId(slug: string): Promise<string | null> {
  const rows = await customerQuery<{ id: string }>(
    `SELECT id FROM community_channels WHERE slug = $1`, [slug],
  )
  return rows[0]?.id ?? null
}

export async function getFeed(channelSlug: string, viewerUserId: string | null): Promise<CommunityFeed> {
  const channels = await customerQuery<{ slug: string; name: string; id: string }>(
    `SELECT id, slug, name FROM community_channels ORDER BY sort_order ASC`,
  )
  const channel = channels.find((c) => c.slug === channelSlug) ?? channels[0]
  const [messageRows, presenceRows] = await Promise.all([
    channel
      ? customerQuery<any>(
          `SELECT m.id, m.sender_name, m.sender_type, m.message, m.created_at,
                  COALESCE(
                    (SELECT json_agg(json_build_object('emoji', r.emoji, 'count', r.cnt, 'mine', r.mine))
                     FROM (
                       SELECT emoji, COUNT(*)::int AS cnt,
                              BOOL_OR(user_id = $2::uuid) AS mine
                       FROM community_reactions
                       WHERE message_id = m.id
                       GROUP BY emoji
                       ORDER BY cnt DESC
                     ) r),
                    '[]'::json
                  ) AS reactions
           FROM community_messages m
           WHERE m.channel_id = $1
           ORDER BY m.created_at DESC
           LIMIT 100`,
          [channel.id, viewerUserId],
        )
      : Promise.resolve([]),
    customerQuery<{ user_id: string; display_name: string }>(
      `SELECT user_id, display_name FROM community_presence
       WHERE last_seen > now() - interval '5 minutes'
       ORDER BY last_seen DESC LIMIT 50`,
    ),
  ])

  return {
    channels: channels.map((c) => ({ slug: c.slug, name: c.name })),
    messages: messageRows.reverse().map((m) => ({
      id: String(m.id),
      sender_name: String(m.sender_name),
      sender_type: m.sender_type as CommunityMessage['sender_type'],
      message: String(m.message),
      created_at: new Date(m.created_at).toISOString(),
      reactions: Array.isArray(m.reactions) ? m.reactions : [],
    })),
    online_count: presenceRows.length,
    members: presenceRows.map((p) => ({
      name: p.display_name,
      you: viewerUserId != null && p.user_id === viewerUserId,
    })),
  }
}

export async function insertMessage(opts: {
  channelId: string
  userId: string | null
  senderName: string
  senderType: 'USER' | 'FORGE' | 'SYSTEM'
  message: string
}): Promise<string | null> {
  const rows = await customerQuery<{ id: string }>(
    `INSERT INTO community_messages (channel_id, user_id, sender_name, sender_type, message)
     VALUES ($1, $2, $3, $4, $5) RETURNING id`,
    [opts.channelId, opts.userId, opts.senderName, opts.senderType, opts.message],
  )
  return rows[0]?.id ?? null
}

export async function toggleReaction(messageId: string, userId: string, emoji: string): Promise<'added' | 'removed'> {
  const removed = await customerExecute(
    `DELETE FROM community_reactions WHERE message_id = $1 AND user_id = $2 AND emoji = $3`,
    [messageId, userId, emoji],
  )
  if (removed > 0) return 'removed'
  await customerExecute(
    `INSERT INTO community_reactions (message_id, user_id, emoji) VALUES ($1, $2, $3)
     ON CONFLICT (message_id, user_id, emoji) DO NOTHING`,
    [messageId, userId, emoji],
  )
  return 'added'
}

export async function touchPresence(userId: string, displayName: string): Promise<void> {
  await customerExecute(
    `INSERT INTO community_presence (user_id, display_name, last_seen)
     VALUES ($1, $2, now())
     ON CONFLICT (user_id) DO UPDATE SET display_name = EXCLUDED.display_name, last_seen = now()`,
    [userId, displayName],
  )
}

export async function getDisplayName(userId: string): Promise<string> {
  const rows = await customerQuery<{ first_name: string; last_name: string; email: string }>(
    `SELECT first_name, last_name, email FROM users WHERE id = $1`, [userId],
  )
  const u = rows[0]
  if (!u) return 'Member'
  const name = `${u.first_name ?? ''} ${u.last_name ?? ''}`.trim()
  return name || u.email.split('@')[0]
}

/** Seed Forge's standing welcome so the room is never empty. Idempotent. */
export async function seedWelcomeMessage(): Promise<void> {
  const channelId = await getChannelId(DEFAULT_CHANNEL)
  if (!channelId) return
  const existing = await customerQuery<{ cnt: string }>(
    `SELECT COUNT(*)::int AS cnt FROM community_messages WHERE channel_id = $1`, [channelId],
  )
  if (Number(existing[0]?.cnt ?? 0) > 0) return
  await insertMessage({
    channelId,
    userId: null,
    senderName: FORGE_NAME,
    senderType: 'FORGE',
    message:
      "Welcome to the Forge Community! 🔥 I'm Forge — your AI guide here. I share market observations, answer questions, and keep the conversation disciplined. Say hi, introduce yourself, and let's have a great trading day. Protect the forge.",
  })
}

// ── Forge scheduled posts (08:00 / 12:00 / 15:00 / 17:00 ET, doc §10) ───
// Generated lazily when the feed is read: no scanner changes, no cron.
// A slot only fires within 90 minutes of its scheduled time and exactly
// once (community_forge_posts dedupe row is claimed atomically).

const SLOTS: Array<{ slot: ForgeSlot; hourET: number }> = [
  { slot: 'premarket', hourET: 8 },
  { slot: 'midday', hourET: 12 },
  { slot: 'powerhour', hourET: 15 },
  { slot: 'recap', hourET: 17 },
]

export async function maybePostScheduledUpdate(): Promise<void> {
  if (!isForgeConfigured()) return
  const nowET = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const day = nowET.getDay()
  if (day === 0 || day === 6) return // weekends: no scheduled posts
  const minutes = nowET.getHours() * 60 + nowET.getMinutes()
  const due = SLOTS.filter((s) => {
    const slotMin = s.hourET * 60
    return minutes >= slotMin && minutes < slotMin + 90
  }).pop()
  if (!due) return
  const dateET = nowET.toLocaleDateString('en-CA')
  const slotKey = `${dateET}-${due.slot}`
  // Atomic claim — only one request generates the post.
  const claimed = await customerExecute(
    `INSERT INTO community_forge_posts (slot_key) VALUES ($1) ON CONFLICT (slot_key) DO NOTHING`,
    [slotKey],
  )
  if (claimed === 0) return
  try {
    const channelId = await getChannelId(DEFAULT_CHANNEL)
    if (!channelId) return
    const text = await generateScheduledPost(due.slot)
    const messageId = await insertMessage({
      channelId, userId: null, senderName: FORGE_NAME, senderType: 'FORGE', message: text,
    })
    await customerExecute(
      `UPDATE community_forge_posts SET message_id = $2 WHERE slot_key = $1`,
      [slotKey, messageId],
    )
  } catch (e) {
    // Release the claim so a later poll can retry this slot.
    await customerExecute(
      `DELETE FROM community_forge_posts WHERE slot_key = $1 AND message_id IS NULL`,
      [slotKey],
    ).catch(() => undefined)
    console.error('[community] scheduled post failed:', e)
  }
}

/** Fire Forge's reply to a member message (call fire-and-forget after persist). */
export async function maybeForgeReply(opts: {
  channelId: string
  senderName: string
  message: string
}): Promise<void> {
  if (!isForgeConfigured() || !shouldForgeReply(opts.message)) return
  try {
    const recent = await customerQuery<any>(
      `SELECT sender_name, sender_type, message FROM community_messages
       WHERE channel_id = $1 ORDER BY created_at DESC LIMIT 10`,
      [opts.channelId],
    )
    const reply = await generateForgeReply({
      senderName: opts.senderName,
      message: opts.message,
      recentMessages: recent.reverse(),
    })
    await insertMessage({
      channelId: opts.channelId,
      userId: null,
      senderName: FORGE_NAME,
      senderType: 'FORGE',
      message: reply,
    })
  } catch (e) {
    console.error('[community] forge reply failed:', e)
  }
}
