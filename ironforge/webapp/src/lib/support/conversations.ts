/**
 * Sparky conversation memory (#264) — the DB layer behind POST /api/sparky/chat.
 * The client sends only {message, conversationId}; the history this builds the
 * prompt from lives here, in sparky_conversations/sparky_messages (customers-db.ts).
 */
import { customerQuery, customerExecute } from '@/lib/customers-db'
import type { ChatMessage } from './anthropic'

/** Same cap /api/support/chat applies to the client-resent history it gets. */
const MAX_HISTORY_TURNS = 16

/**
 * Resolves the conversation a new message belongs to. A `conversationId` that is
 * missing, unknown, or owned by someone else silently starts a fresh conversation
 * rather than erroring — the one thing this must never do is attach a reply to
 * another customer's thread.
 */
export async function resolveConversation(userId: string, conversationId: string | null): Promise<string> {
  if (conversationId) {
    const rows = await customerQuery<{ id: string }>(
      `SELECT id FROM sparky_conversations WHERE id = $1::uuid AND user_id = $2`,
      [conversationId, userId],
    ).catch(() => [] as Array<{ id: string }>)
    if (rows[0]) return rows[0].id
  }
  const created = await customerQuery<{ id: string }>(
    `INSERT INTO sparky_conversations (user_id) VALUES ($1) RETURNING id`,
    [userId],
  )
  return created[0].id
}

/** The most recent turns, oldest first — the shape completeAnthropic()'s `messages` wants. */
export async function getConversationHistory(conversationId: string): Promise<ChatMessage[]> {
  const rows = await customerQuery<{ role: string; content: string }>(
    `SELECT role, content FROM (
       SELECT role, content, created_at FROM sparky_messages
        WHERE conversation_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
     ) recent
     ORDER BY created_at ASC`,
    [conversationId, MAX_HISTORY_TURNS],
  )
  return rows.map((r) => ({ role: r.role as ChatMessage['role'], content: r.content }))
}

export async function appendTurn(conversationId: string, role: ChatMessage['role'], content: string): Promise<void> {
  await customerExecute(
    `INSERT INTO sparky_messages (conversation_id, role, content) VALUES ($1, $2, $3)`,
    [conversationId, role, content],
  )
  await customerExecute(`UPDATE sparky_conversations SET updated_at = now() WHERE id = $1`, [conversationId])
}
