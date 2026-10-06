/**
 * Mobile client for POST /api/v1/events — the dev-handoff's named product
 * events (tab_view, agent_sheet_open, community_post, …), posted to the SAME
 * first-party endpoint the web track() helper in ironforge/webapp uses.
 *
 * Deliberately separate from src/analytics/track.ts (APP-048's existing
 * screen_view/app_opened/api_error pipe into /api/v1/analytics/events and
 * `mobile_analytics_events`) — that pipe already ships, is already tested,
 * and nothing here touches it. This module exists only for the dev-handoff's
 * own named events, which that pipe never carried.
 *
 * No new native dependency: identity rides the existing bearer session via
 * `api()` (expo-secure-store is already in the shipped fingerprint); the
 * anon_id fallback for a pre-login event (e.g. `app_open` before sign-in) is
 * a Math.random()-based id, not a crypto UUID, persisted with the same
 * setItem/getItem used for tokens — adding expo-crypto or
 * react-native-get-random-values just for this id is not worth a new native
 * module.
 *
 * Batches the same way track.ts does (up to BATCH_SIZE events or
 * FLUSH_INTERVAL_MS) and, unlike track.ts, retries a failed flush exactly
 * once by re-queuing at the FRONT of the next batch — bounded so a customer
 * who is offline for a while cannot grow the queue without limit.
 */
import { Platform } from 'react-native'
import { api } from '@/api/client'
import { getItem, setItem } from '@/api/storage'
import { isAllowedMobileEvent, type MobileAnalyticsEventName } from './events'

type Surface = 'ios' | 'android' | 'web'

interface QueuedEvent {
  event: MobileAnalyticsEventName
  props?: Record<string, string | number | boolean | null>
  surface: Surface
  /** Set once this item has already failed one flush — a second failure drops it. */
  retried?: boolean
}

const ANON_ID_KEY = 'ironforge.analyticsAnonId'
const BATCH_SIZE = 20
const FLUSH_INTERVAL_MS = 10_000

let queue: QueuedEvent[] = []
let timer: ReturnType<typeof setTimeout> | null = null
let anonIdCache: string | null = null

function surface(): Surface {
  return Platform.OS === 'ios' || Platform.OS === 'android' ? Platform.OS : 'web'
}

/**
 * Populates anonIdCache in the background. Deliberately fire-and-forget and
 * read synchronously by flush() (see below) rather than awaited inline there
 * — awaiting a storage round-trip would push the actual api() call to a
 * later microtask every single flush, when all but the very first flush of
 * a cold app already has the id cached.
 */
function primeAnonId(): void {
  if (anonIdCache) return
  void (async () => {
    try {
      const existing = await getItem(ANON_ID_KEY)
      if (existing) {
        anonIdCache = existing
        return
      }
      const next = `anon_${Date.now()}_${Math.random().toString(36).slice(2)}`
      await setItem(ANON_ID_KEY, next)
      anonIdCache = next
    } catch {
      // Best-effort — a storage failure just means this batch ships without anon_id.
    }
  })()
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
    await api('/api/v1/events', {
      method: 'POST',
      body: {
        events: batch.map(({ event, props, surface: s }) => ({ event, props, surface: s })),
        surface: surface(),
        ...(anonIdCache ? { anon_id: anonIdCache } : {}),
      },
    })
  } catch {
    // Retry exactly once per event, by re-queuing only the items that haven't
    // already failed a flush — a customer who is offline for a while still
    // cannot grow the queue without bound.
    const retryable = batch.filter((e) => !e.retried).map((e) => ({ ...e, retried: true }))
    queue = [...retryable, ...queue]
    if (queue.length > 0) scheduleFlush()
  }
}

/**
 * Record a dev-handoff mobile product event. Safe to call from any render
 * path — never throws, never awaits the caller. An event name not on the
 * allowlist is dropped silently rather than sent, matching the server's own
 * allowlist rejection.
 */
export function trackEvent(event: string, props?: Record<string, string | number | boolean | null>): void {
  try {
    if (!isAllowedMobileEvent(event)) return
    primeAnonId()
    queue.push({ event, props, surface: surface() })
    if (queue.length >= BATCH_SIZE) void flush()
    else scheduleFlush()
  } catch {
    // Never throw — a broken analytics call must never break the screen that made it.
  }
}

/** Test-only. */
export function __resetTrackEvent(): void {
  queue = []
  if (timer) clearTimeout(timer)
  timer = null
  anonIdCache = null
}
