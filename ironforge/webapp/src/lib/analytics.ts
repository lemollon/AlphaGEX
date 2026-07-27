/**
 * Minimal, provider-agnostic analytics emitter.
 *
 * No network, no vendor SDK, no cookies. Events queue until a sink is
 * installed; installing one flushes the queue. Dropping in a real provider
 * later is a one-file change with no edits to any component.
 *
 * Event names and property names below mirror the Bot Ledger requirements
 * section 19.1 exactly, so the analytics schema handoff needs no translation
 * layer.
 *
 * PRIVACY INVARIANT — read this before editing AnalyticsEvent:
 * Never add a monetary amount, P&L, win rate, return, trade identifier,
 * account identifier, email, or any other financial or personally-identifying
 * field to these props (requirements section 19.2). The closed union below IS
 * the enforcement mechanism — there is no Record<string, unknown> escape
 * hatch, so a violation cannot be added without editing this file, which a
 * reviewer will see.
 */

export type Period = '7d' | '30d'
export type BotFilter = 'all' | 'spark' | 'flame'
/** Coarse buckets only — never a raw pixel width, which is a fingerprinting vector. */
export type ViewportClass = 'mobile' | 'tablet' | 'desktop'
/** Coarse buckets only — never the raw referrer URL. */
export type ReferrerClass = 'direct' | 'internal' | 'external' | 'search' | 'social'

export type AnalyticsEvent =
  | {
      name: 'bot_ledger_view'
      props: {
        period: Period
        viewport_class: ViewportClass
        referrer_class: ReferrerClass
        auth_state: 'anonymous' | 'authenticated'
      }
    }
  | { name: 'period_change'; props: { from_period: Period; to_period: Period } }
  | { name: 'bot_filter_change'; props: { from_bot: BotFilter; to_bot: BotFilter } }
  | {
      name: 'cta_click'
      props: {
        cta_name: 'create_account' | 'start_trial'
        placement: 'hero'
        target_route: string
        plan: 'automate' | 'none'
      }
    }
  | {
      name: 'trade_log_page'
      props: { direction: 'next' | 'prev'; page_size: number; bot_filter: BotFilter }
    }
  | {
      name: 'ledger_error'
      props: { component: 'summary' | 'trade_log'; error_code: string; request_id: string | null }
    }

type Sink = (event: AnalyticsEvent) => void

let sink: Sink | null = null
const queue: AnalyticsEvent[] = []
const MAX_QUEUE = 50

export function track(event: AnalyticsEvent): void {
  // Never emit during SSR — an event is a user action, not a render.
  if (typeof window === 'undefined') return

  if (sink) {
    try {
      sink(event)
    } catch {
      // Analytics must never break the page.
    }
    return
  }
  // Bounded, so a page with no provider installed cannot grow without limit.
  if (queue.length < MAX_QUEUE) queue.push(event)
}

export function setAnalyticsSink(next: Sink): void {
  sink = next
  const pending = queue.splice(0, queue.length)
  for (const event of pending) {
    try {
      sink(event)
    } catch {
      // ignore
    }
  }
}

/** Coarse viewport bucket, matching the responsive breakpoints. */
export function viewportClass(width: number): ViewportClass {
  if (width < 768) return 'mobile'
  if (width < 1024) return 'tablet'
  return 'desktop'
}

/**
 * Bucket the referrer without ever recording the URL itself. Search and social
 * are separated because they are the two buckets marketing actually acts on.
 */
export function referrerClass(referrer: string, host: string): ReferrerClass {
  if (!referrer) return 'direct'
  let h: string
  try {
    h = new URL(referrer).hostname.toLowerCase()
  } catch {
    return 'direct'
  }
  if (h === host.toLowerCase()) return 'internal'
  if (/(^|\.)(google|bing|duckduckgo|yahoo|ecosia|brave)\./.test(h)) return 'search'
  if (/(^|\.)(x|twitter|t|facebook|instagram|linkedin|reddit|youtube|discord)\./.test(h)) {
    return 'social'
  }
  return 'external'
}

/** Test-only. */
export function __resetAnalytics(): void {
  sink = null
  queue.length = 0
}

/** Test-only. */
export function __queuedEvents(): readonly AnalyticsEvent[] {
  return queue
}
