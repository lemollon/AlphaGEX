/**
 * Minimal Server-Sent Events frame parser, hand-rolled because React Native
 * has no EventSource and the positions stream is read as raw bytes (see
 * api/positionsStream.ts, the same `expo/fetch` streaming pattern
 * api/sparky.ts already uses for Ask Sparky).
 *
 * Pure and side-effect free on purpose — this is the part worth getting
 * right in a test, unlike the fetch/reconnect wiring around it.
 */

export interface SseFrame {
  event: string
  data: string
}

/**
 * Splits a growing text buffer into complete SSE frames (blank-line
 * terminated) plus whatever partial frame is left over. A network chunk can
 * split one frame across two `reader.read()` calls, so the remainder must be
 * fed back into the next chunk rather than dropped.
 */
export function splitSseFrames(buffer: string): { frames: string[]; remainder: string } {
  const frames = buffer.split('\n\n')
  const remainder = frames.pop() ?? ''
  return { frames, remainder }
}

/**
 * Parses one frame's `event:` / `data:` lines.
 *
 * Comment-only frames (every line starts with `:`, used here as heartbeat
 * pings) and frames with no `data:` line at all parse to null — there is
 * nothing for a caller to act on.
 */
export function parseSseFrame(frame: string): SseFrame | null {
  let event = 'message'
  let data: string | null = null
  for (const rawLine of frame.split('\n')) {
    const line = rawLine.trim()
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data = (data ?? '') + line.slice(5).trim()
  }
  return data == null ? null : { event, data }
}
