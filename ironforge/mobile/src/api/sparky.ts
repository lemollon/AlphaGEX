/**
 * Ask Sparky streaming client (APP-032).
 *
 * `/api/support/chat` answers Server-Sent Events, not JSON, so it cannot go through
 * api() — that helper parses a whole body. React Native's built-in fetch has no
 * streaming body either, so this uses `expo/fetch`, which does.
 *
 * Frames are `data: {"t":"<delta>"}` then `data: {"done":true}`, or `data: {"error":"…"}`.
 * The endpoint is deliberately stateless: it takes recent history and persists nothing,
 * so the transcript lives only in screen state and dies with the screen.
 */
import { fetch as streamingFetch } from 'expo/fetch'
import { API_BASE, getAccessToken, refreshAccessToken, AuthExpiredError } from '@/api/client'

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

/**
 * Streams one reply, invoking `onDelta` for each text chunk.
 *
 * Retries exactly once on 401 with a refreshed token — the same contract api() honours,
 * hand-rolled here because the response is a stream.
 */
export async function streamSparky(
  messages: SparkyTurn[],
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  let token = await getAccessToken()
  let res = await send(token, messages, signal)

  if (res.status === 401) {
    token = await refreshAccessToken()
    if (!token) throw new AuthExpiredError()
    res = await send(token, messages, signal)
  }

  // 503 is "not provisioned", not a failure — the route says so explicitly, and the UI
  // shows a calm fallback rather than an error state.
  if (res.status === 503) throw new SparkyUnavailableError()
  if (!res.ok) throw new Error(`Sparky is unavailable (${res.status}).`)
  if (!res.body) throw new Error('Sparky returned an empty response.')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  // SSE frames are newline-delimited but a chunk can split one in half, so hold the
  // remainder rather than dropping it.
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      const line = frame.trim()
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (!payload) continue
      let obj: { t?: string; done?: boolean; error?: string }
      try {
        obj = JSON.parse(payload)
      } catch {
        continue // a malformed frame is not a reason to kill a good answer
      }
      if (obj.error) throw new Error(obj.error)
      if (obj.done) return
      if (typeof obj.t === 'string') onDelta(obj.t)
    }
  }
}

function send(token: string | null, messages: SparkyTurn[], signal?: AbortSignal) {
  return streamingFetch(`${API_BASE}/api/support/chat`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'text/event-stream',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ messages }),
    signal,
  })
}
