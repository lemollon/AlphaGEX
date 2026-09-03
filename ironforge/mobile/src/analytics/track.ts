/**
 * Product analytics (APP-048).
 *
 * Fire-and-forget by contract (SPEC.md cross-package section): any screen in any
 * package can call track() to record a feature event, and it must be safe to call
 * from a render path — it never throws, never awaits the caller, and a dropped batch
 * is acceptable rather than surfaced.
 *
 * Batches locally (up to BATCH_SIZE events or FLUSH_INTERVAL_MS, whichever comes
 * first) rather than firing one HTTP request per event — a session that opens the
 * Forge tab, checks Ledger, and taps into a trade would otherwise be three requests
 * for three screen views alone.
 */
import { Platform } from 'react-native'
import Constants from 'expo-constants'
import { api } from '@/api/client'
import { ApiError } from '@/api/errors'
import { captureApiError } from '@/monitoring/sentry'

export type TrackProps = Record<string, string | number | boolean | null>

export interface TrackedEvent {
  event: string
  props?: TrackProps
  ts: number
  app_version: string
  platform: string
}

/** Never send an account id, a token, a password, or a secret to the analytics pipe. */
const SENSITIVE_KEY_RE = /account|token|password|secret/i

const BATCH_SIZE = 20
const FLUSH_INTERVAL_MS = 10_000

let queue: TrackedEvent[] = []
let timer: ReturnType<typeof setTimeout> | null = null

function redact(props: TrackProps | undefined): TrackProps | undefined {
  if (!props) return undefined
  const out: TrackProps = {}
  for (const [k, v] of Object.entries(props)) {
    if (SENSITIVE_KEY_RE.test(k)) continue
    out[k] = v
  }
  return out
}

function appVersion(): string {
  return Constants.expoConfig?.version ?? 'unknown'
}

function scheduleFlush(): void {
  if (timer) return
  timer = setTimeout(() => {
    void flush()
  }, FLUSH_INTERVAL_MS)
}

async function flush(): Promise<void> {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  if (queue.length === 0) return
  const batch = queue
  queue = []
  try {
    await api('/api/v1/analytics/events', { method: 'POST', body: { events: batch } })
  } catch {
    // Fire-and-forget — a dropped batch never surfaces to the caller. Nothing to
    // retry here: re-queuing risks an unbounded queue if the customer is offline.
  }
}

/**
 * Record a feature event. Every prop key matching /account|token|password|secret/i is
 * dropped before the event ever enters the queue, so a caller that accidentally passes
 * something sensitive cannot leak it even for one batch.
 */
export function track(event: string, props?: TrackProps): void {
  try {
    const safeProps = redact(props)
    queue.push({
      event,
      props: safeProps,
      ts: Date.now(),
      app_version: appVersion(),
      platform: Platform.OS,
    })

    // A 5xx a screen already reported via track('api_error', { status, path }) is also
    // IronForge's fault, not the customer's — send it to Sentry without a second call
    // site every screen would otherwise have to remember.
    if (event === 'api_error' && typeof safeProps?.status === 'number' && safeProps.status >= 500) {
      const path = typeof safeProps.path === 'string' ? ` ${safeProps.path}` : ''
      captureApiError(new ApiError(`API error ${safeProps.status}${path}`, safeProps.status, null))
    }

    if (queue.length >= BATCH_SIZE) void flush()
    else scheduleFlush()
  } catch {
    // Never throw — a broken analytics call must never break the screen that made it.
  }
}
