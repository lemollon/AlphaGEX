import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isAnthropicConfigured, completeAnthropic } from '@/lib/support/anthropic'
import { buildSparkySystemPrompt } from '@/lib/support/persona'
import { resolveConversation, getConversationHistory, appendTurn } from '@/lib/support/conversations'
import { rateLimited } from '@/lib/rate-limit'
import { CustomersDbNotConfiguredError } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Sparky chat (#264) — `POST /api/sparky/chat {message, conversationId}` →
 * `{reply, conversationId}`. Stateful: unlike /api/support/chat (kept working
 * unchanged for app builds that still call it), the client does not resend the
 * transcript — history is kept server-side in sparky_conversations/
 * sparky_messages (lib/support/conversations.ts) and looked up by
 * `conversationId`. A missing/omitted conversationId starts a new conversation;
 * the response always carries the id to continue it.
 *
 * Plain JSON, not SSE — the mobile UI shows a typing indicator while it waits
 * for the one complete reply, not token-by-token deltas.
 */

const MAX_MSG_LEN = 4000
const WINDOW_MS = 60_000
const MAX_PER_WINDOW = 20

function dbUnavailable() {
  return NextResponse.json({ error: 'Sparky is not available yet.' }, { status: 503 })
}

export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer — same session shape every other customer route uses.
  const session = { customerId: identity?.customerId ?? null }
  if (!session.customerId) {
    return NextResponse.json({ error: 'Please sign in to chat with Sparky.' }, { status: 401 })
  }
  if (!isAnthropicConfigured()) {
    return NextResponse.json(
      { error: 'Sparky is warming up and isn’t available just yet. Please try again shortly.' },
      { status: 503 },
    )
  }
  if (rateLimited(`sparky:${session.customerId}`, { windowMs: WINDOW_MS, maxPerWindow: MAX_PER_WINDOW })) {
    return NextResponse.json({ error: 'You’re sending messages a bit fast — give it a moment.' }, { status: 429 })
  }

  const body = (await req.json().catch(() => null)) as { message?: unknown; conversationId?: unknown } | null
  const message = typeof body?.message === 'string' ? body.message.trim() : ''
  if (!message) return NextResponse.json({ error: 'Message is empty.' }, { status: 400 })
  if (message.length > MAX_MSG_LEN) {
    return NextResponse.json({ error: 'Message is too long.' }, { status: 400 })
  }
  const requestedConversationId =
    typeof body?.conversationId === 'string' && body.conversationId.trim() ? body.conversationId.trim() : null

  try {
    const conversationId = await resolveConversation(session.customerId, requestedConversationId)
    const history = await getConversationHistory(conversationId)

    const system = buildSparkySystemPrompt({ loggedIn: true })
    const reply = await completeAnthropic({
      system,
      messages: [...history, { role: 'user', content: message }],
      maxTokens: 800,
      signal: req.signal,
    })

    // Persist both turns together — a reply that fails to save would otherwise
    // silently drop out of this conversation's memory on the next turn.
    await appendTurn(conversationId, 'user', message)
    await appendTurn(conversationId, 'assistant', reply)

    return NextResponse.json({ reply, conversationId })
  } catch (e) {
    if (e instanceof CustomersDbNotConfiguredError) return dbUnavailable()
    console.error('[sparky/chat] failed:', e)
    return NextResponse.json(
      { error: 'Sparky hit a snag. Please try again — or reach a human from the Support page.' },
      { status: 500 },
    )
  }
}
