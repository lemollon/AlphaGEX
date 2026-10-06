/**
 * Web client for POST /api/v1/events — the dev-handoff's named product
 * events (cta_click, waitlist_*, enroll_*, …), separate from the unused
 * sink-based `lib/analytics.ts` (a different, never-wired emitter for a
 * different events table) and from `/api/track` (anonymous page-view beacon
 * only, no event name or props).
 *
 * Fire-and-forget: track() never throws and never returns a promise the
 * caller has to handle — a dropped event must never break the click it was
 * attached to. A signed-in customer rides their session cookie; everyone
 * else gets a client-generated anon_id, persisted in localStorage so repeat
 * visits (and an enrollment funnel that starts anonymous and ends signed in)
 * share one identity until the cookie takes over server-side.
 */
import { ANALYTICS_EVENTS, type AnalyticsEventName } from './events'

const ANON_ID_KEY = 'if_anon_id'

function anonId(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const existing = window.localStorage.getItem(ANON_ID_KEY)
    if (existing) return existing
    const next =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `anon_${Date.now()}_${Math.random().toString(36).slice(2)}`
    window.localStorage.setItem(ANON_ID_KEY, next)
    return next
  } catch {
    // Storage disabled/unavailable (private mode, quota) — the event still
    // sends; the server just won't have a stable anon_id to join on.
    return null
  }
}

type PropsFor<E extends AnalyticsEventName> = Partial<Record<(typeof ANALYTICS_EVENTS)[E][number], string | number | boolean | null>>

/**
 * Record a web product event. Safe to call from any render path or handler —
 * never throws, never awaits the caller, and silently no-ops during SSR.
 */
export function track<E extends AnalyticsEventName>(event: E, props?: PropsFor<E>): void {
  if (typeof window === 'undefined') return
  try {
    const id = anonId()
    const payload: Record<string, unknown> = { event, props, surface: 'web' }
    if (id) payload.anon_id = id

    const body = JSON.stringify(payload)
    // navigator.sendBeacon survives a page unload (e.g. a CTA that navigates
    // away immediately); fall back to fetch keepalive where it's unavailable.
    if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
      const blob = new Blob([body], { type: 'application/json' })
      navigator.sendBeacon('/api/v1/events', blob)
      return
    }
    void fetch('/api/v1/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      keepalive: true,
      body,
    }).catch(() => {
      // Fire-and-forget — a dropped event never surfaces to the caller.
    })
  } catch {
    // Analytics must never break the page.
  }
}
