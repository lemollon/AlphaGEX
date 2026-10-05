/**
 * Positions/P&L stream client (dev-handoff `/ws/positions`, served over SSE —
 * see webapp's src/app/api/v1/stream/positions/route.ts for why it's SSE and
 * not a real WebSocket).
 *
 * React Native's built-in `fetch` has no streaming response body; `expo/fetch`
 * does, so this reads raw SSE bytes off it — the exact pattern api/sparky.ts
 * already uses for Ask Sparky, including the same single-retry-on-401. No new
 * native dependency: `expo/fetch` ships inside the `expo` package already in
 * package.json.
 */
import { fetch as streamingFetch } from 'expo/fetch'
import { API_BASE, getAccessToken, refreshAccessToken, AuthExpiredError } from '@/api/client'
import { splitSseFrames, parseSseFrame } from '@/live/sse-parse'
import type { LiveAgent } from '@/api/types'

export interface PositionsPush {
  bot: string
  trade: LiveAgent['trade']
}

export interface PositionsStreamHandlers {
  onPositions: (pushes: PositionsPush[]) => void
  onError?: (err: unknown) => void
}

/**
 * Opens ONE connection and reads it until the server closes it, `signal`
 * aborts, or the body ends. Resolves (does not throw) on a clean end-of-stream
 * so a caller's reconnect loop can tell "the stream ended, try again" apart
 * from "the request itself failed" without wrapping every call in try/catch.
 *
 * Reconnect policy (backoff, foreground-only, pause-in-background) lives in
 * the caller — same separation api/sparky.ts keeps from its screen — so this
 * function's only job is one honest read of one connection.
 */
export async function streamPositions(
  { onPositions, onError }: PositionsStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let token = await getAccessToken()
  let res = await send(token, signal)

  if (res.status === 401) {
    token = await refreshAccessToken()
    if (!token) throw new AuthExpiredError()
    res = await send(token, signal)
  }

  if (!res.ok) throw new Error(`Positions stream unavailable (${res.status}).`)
  if (!res.body) throw new Error('Positions stream returned an empty response.')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })
    const { frames, remainder } = splitSseFrames(buffer)
    buffer = remainder

    for (const raw of frames) {
      const frame = parseSseFrame(raw)
      if (!frame) continue // heartbeat or an incomplete/malformed frame

      if (frame.event === 'error') {
        onError?.(new Error(extractErrorMessage(frame.data)))
        continue // a server-reported error frame is not a reason to drop a working connection
      }
      if (frame.event !== 'positions') continue

      let payload: unknown
      try {
        payload = JSON.parse(frame.data)
      } catch {
        continue // one malformed frame must not kill a good connection
      }
      if (!payload || (payload as { empty?: boolean }).empty) continue

      const agents = (payload as { agents?: PositionsPush[] }).agents
      if (Array.isArray(agents) && agents.length > 0) onPositions(agents)
    }
  }
}

function extractErrorMessage(data: string): string {
  try {
    const parsed = JSON.parse(data) as { error?: string }
    return parsed.error ?? 'Positions stream error.'
  } catch {
    return 'Positions stream error.'
  }
}

function send(token: string | null, signal?: AbortSignal) {
  return streamingFetch(`${API_BASE}/api/v1/stream/positions`, {
    method: 'GET',
    headers: {
      accept: 'text/event-stream',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    signal,
  })
}
