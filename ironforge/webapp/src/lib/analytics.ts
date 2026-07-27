/**
 * Minimal, provider-agnostic analytics emitter.
 *
 * No network, no vendor SDK, no cookies. Events queue until a sink is
 * installed; installing one flushes the queue. Dropping in a real provider
 * later is a one-file change with no edits to any component.
 *
 * PRIVACY INVARIANT — read this before editing AnalyticsEvent:
 * Never add a monetary amount, P&L, win rate, return, trade identifier,
 * account identifier, email, or any other financial or personally-identifying
 * field to these props. The closed union below IS the enforcement mechanism —
 * there is no Record<string, unknown> escape hatch, so a violation cannot be
 * added without editing this file, which a reviewer will see.
 */

export type AnalyticsEvent =
  | { name: 'bot_ledger_view'; props: { period: '7d' | '30d'; bot: 'all' | 'spark' | 'flame' } }
  | { name: 'bot_ledger_period_change'; props: { from: '7d' | '30d'; to: '7d' | '30d' } }
  | {
      name: 'bot_ledger_bot_filter_change'
      props: { from: 'all' | 'spark' | 'flame'; to: 'all' | 'spark' | 'flame' }
    }
  | {
      name: 'bot_ledger_cta_click'
      props: { cta: 'create_account' | 'start_trial'; placement: 'hero' }
    }
  | { name: 'bot_ledger_trade_log_page'; props: { direction: 'next' | 'prev'; page_size: number } }
  | {
      name: 'bot_ledger_error'
      props: { component: 'summary' | 'trade_log'; error_code: string }
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

/** Test-only. */
export function __resetAnalytics(): void {
  sink = null
  queue.length = 0
}

/** Test-only. */
export function __queuedEvents(): readonly AnalyticsEvent[] {
  return queue
}
