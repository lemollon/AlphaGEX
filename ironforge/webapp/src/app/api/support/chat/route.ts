import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isAnthropicConfigured, streamAnthropic, type ChatMessage } from '@/lib/support/anthropic'
import { buildSparkySystemPrompt } from '@/lib/support/persona'
import { rateLimited } from '@/lib/rate-limit'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Sparky support chat — streams a grounded, guarded reply as SSE.
 *
 * Customer-session guarded (MVP is signed-in only). Returns 503 (not an error) when the
 * Anthropic key isn't provisioned so the UI shows a clean "warming up" fallback. Stateless:
 * the client sends the recent history and receives streamed text; no transcript is persisted
 * in this phase.
 *
 * SSE frames: `data: {"t":"<text delta>"}` … then `data: {"done":true}`, or `data: {"error":"…"}`.
 */

const MAX_TURNS = 16 // cap history sent upstream
const MAX_MSG_LEN = 4000

// Rate limit config — see lib/rate-limit.ts. Support is low-QPS; this just stops abuse.
const WINDOW_MS = 60_000
const MAX_PER_WINDOW = 20

function sanitizeMessages(raw: unknown): ChatMessage[] {
  if (!Array.isArray(raw)) return []
  const out: ChatMessage[] = []
  for (const m of raw) {
    if (!m || typeof m !== 'object') continue
    const role = (m as any).role
    const content = (m as any).content
    if ((role === 'user' || role === 'assistant') && typeof content === 'string' && content.trim()) {
      out.push({ role, content: content.slice(0, MAX_MSG_LEN) })
    }
  }
  // Keep the last MAX_TURNS and ensure it ends on a user turn.
  const trimmed = out.slice(-MAX_TURNS)
  while (trimmed.length && trimmed[trimmed.length - 1].role !== 'user') trimmed.pop()
  return trimmed
}

function sse(obj: unknown): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(obj)}\n\n`)
}

export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer. Shape preserved so the checks below read unchanged.
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
  if (rateLimited(`support:${session.customerId}`, { windowMs: WINDOW_MS, maxPerWindow: MAX_PER_WINDOW })) {
    return NextResponse.json({ error: 'You’re sending messages a bit fast — give it a moment.' }, { status: 429 })
  }

  const body = (await req.json().catch(() => null)) as { messages?: unknown } | null
  const messages = sanitizeMessages(body?.messages)
  if (messages.length === 0) {
    return NextResponse.json({ error: 'Message is empty.' }, { status: 400 })
  }

  const system = buildSparkySystemPrompt({ loggedIn: true })

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for await (const delta of streamAnthropic({ system, messages, maxTokens: 800, signal: req.signal })) {
          controller.enqueue(sse({ t: delta }))
        }
        controller.enqueue(sse({ done: true }))
      } catch (e) {
        // Don't leak internals; log server-side, send a friendly error frame.
        console.error('[support/chat] stream error:', e)
        controller.enqueue(sse({ error: 'Sparky hit a snag. Please try again — or reach a human from the Support page.' }))
      } finally {
        controller.close()
      }
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  })
}
