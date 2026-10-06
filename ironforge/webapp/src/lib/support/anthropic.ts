/**
 * Minimal Anthropic Messages client over the REST API (no SDK dependency, matching the
 * dependency-light pattern used for Stripe). If ANTHROPIC_API_KEY is unset,
 * isAnthropicConfigured() is false and the support route returns a clean 503 — Sparky
 * degrades to a friendly "warming up" fallback instead of erroring. The key is never
 * logged or sent to the client.
 */

const API_URL = 'https://api.anthropic.com/v1/messages'
const ANTHROPIC_VERSION = '2023-06-01'

/** Support model — Haiku by default (fast + cheap for FAQ). Overridable via env. */
export const SUPPORT_MODEL = process.env.SUPPORT_MODEL || 'claude-haiku-4-5-20251001'

export function isAnthropicConfigured(): boolean {
  return Boolean(process.env.ANTHROPIC_API_KEY?.trim())
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/**
 * One full (non-streaming) completion — for POST /api/sparky/chat (#264), which
 * answers plain JSON `{reply, conversationId}` rather than SSE deltas. Separate
 * function from streamAnthropic() rather than collecting that generator's
 * output, since a non-streaming caller has no reason to ask Anthropic to
 * stream in the first place.
 */
export async function completeAnthropic(opts: {
  system: string
  messages: ChatMessage[]
  maxTokens?: number
  signal?: AbortSignal
}): Promise<string> {
  const key = process.env.ANTHROPIC_API_KEY?.trim()
  if (!key) throw new Error('ANTHROPIC_API_KEY not configured')

  const res = await fetch(API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': key,
      'anthropic-version': ANTHROPIC_VERSION,
    },
    body: JSON.stringify({
      model: SUPPORT_MODEL,
      max_tokens: opts.maxTokens ?? 800,
      system: opts.system,
      messages: opts.messages,
    }),
    signal: opts.signal,
  })

  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Anthropic ${res.status}: ${detail.slice(0, 300)}`)
  }

  const data = await res.json()
  const blocks = Array.isArray(data?.content) ? data.content : []
  const text = blocks.map((b: any) => b?.text ?? '').join('').trim()
  if (!text) throw new Error('Anthropic returned empty content')
  return text
}

/**
 * Stream a completion from Anthropic, yielding plain text deltas as they arrive.
 * Parses the SSE stream and surfaces only `text_delta` content. Throws on a non-2xx
 * response so the caller can send an error event.
 */
export async function* streamAnthropic(opts: {
  system: string
  messages: ChatMessage[]
  maxTokens?: number
  signal?: AbortSignal
}): AsyncGenerator<string> {
  const key = process.env.ANTHROPIC_API_KEY?.trim()
  if (!key) throw new Error('ANTHROPIC_API_KEY not configured')

  const res = await fetch(API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': key,
      'anthropic-version': ANTHROPIC_VERSION,
    },
    body: JSON.stringify({
      model: SUPPORT_MODEL,
      max_tokens: opts.maxTokens ?? 800,
      system: opts.system,
      messages: opts.messages,
      stream: true,
    }),
    signal: opts.signal,
  })

  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Anthropic ${res.status}: ${detail.slice(0, 300)}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE events are separated by a blank line.
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)

      for (const line of rawEvent.split('\n')) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        const data = trimmed.slice(5).trim()
        if (!data || data === '[DONE]') continue
        try {
          const evt = JSON.parse(data)
          if (evt.type === 'content_block_delta' && evt.delta?.type === 'text_delta') {
            const text = evt.delta.text as string
            if (text) yield text
          }
        } catch {
          /* ignore malformed keep-alive / partial lines */
        }
      }
    }
  }
}
