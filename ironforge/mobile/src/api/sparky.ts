/**
 * Ask Sparky chat client (#264).
 *
 * POST /api/sparky/chat {message, conversationId} -> {reply, conversationId}.
 * Plain JSON through the normal api() client, not SSE — unlike the old
 * /api/support/chat this replaces in the app, the server now keeps the
 * conversation's history itself (sparky_conversations/sparky_messages), so
 * the client only ever sends the ONE new message plus the conversationId it
 * got back last time. `conversationId` is omitted on the first message of a
 * fresh conversation; the server starts one and returns its id.
 */
import { api, ApiError } from '@/api/client'

export interface SparkyTurn {
  role: 'user' | 'assistant'
  content: string
}

export class SparkyUnavailableError extends Error {
  constructor() {
    super("Sparky is warming up and can't answer right now. Please try again shortly.")
    this.name = 'SparkyUnavailableError'
  }
}

interface SparkyChatResponse {
  reply: string
  conversationId: string
}

/** Sends one message and returns the reply plus the conversationId to send on the next turn. */
export async function sendSparkyMessage(
  message: string,
  conversationId: string | null,
): Promise<SparkyChatResponse> {
  try {
    return await api<SparkyChatResponse>('/api/sparky/chat', {
      method: 'POST',
      body: conversationId ? { message, conversationId } : { message },
    })
  } catch (e) {
    // 503 is "not provisioned", not a failure — the route says so explicitly, and
    // the UI shows a calm fallback rather than an error state.
    if (e instanceof ApiError && e.status === 503) throw new SparkyUnavailableError()
    throw e
  }
}
