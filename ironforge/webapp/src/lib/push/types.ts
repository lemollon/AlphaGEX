/**
 * Push notification contracts (APP-033 … APP-036).
 *
 * Kept separate from the transport so the event vocabulary is readable in one place,
 * and so rendering/eligibility can be pure functions over it (which is what makes the
 * lock-screen redaction rule testable rather than conventional).
 */
import type { AppRoute } from '@/lib/mobile/deep-link'

export type NotificationCategory =
  | 'trade_opened'
  | 'trade_closed'
  | 'trade_approval'
  | 'brokerage_health'
  | 'billing'
  | 'community'

/** Maps a category to the boolean column in notification_prefs that gates it. */
export const CATEGORY_PREF_COLUMN: Record<NotificationCategory, string> = {
  trade_opened: 'trade_opened',
  trade_closed: 'trade_closed',
  trade_approval: 'trade_approval',
  brokerage_health: 'brokerage_health',
  billing: 'billing',
  community: 'community',
}

/**
 * How old an event may be before we refuse to deliver it.
 *
 * This is the "no stale alerts" half of APP-034/035 that a transition check alone
 * cannot provide: if the scanner's dispatch call failed and retried twenty minutes
 * later, the transition is still technically valid but the notification is a lie.
 *
 * trade_approval matches APP-041's 5-minute approval TTL exactly — there is no point
 * waking someone for a decision that has already expired.
 */
export const STALE_AFTER_SEC: Record<NotificationCategory, number> = {
  trade_opened: 900,
  trade_closed: 900,
  trade_approval: 300,
  brokerage_health: 1800,
  billing: 86400,
  community: 3600,
}

export interface NotificationEvent {
  category: NotificationCategory
  /**
   * Dedupe key. MUST be derived from immutable facts (ids), never timestamps —
   * a timestamped key makes every retry a new "unique" event and defeats the point.
   */
  eventKey: string
  /** ISO timestamp of when the underlying thing happened, for the staleness check. */
  occurredAt: string
  /** Where tapping the notification should land. Validated against the allowlist. */
  route: AppRoute
  routeParams?: Record<string, string>
  /** Human-facing copy fragments. Amounts travel separately — see `amount`. */
  title: string
  /** Second line on platforms that render one (iOS notification subtitle). Optional —
   * most categories never set it; render.ts only forwards it when present. */
  subtitle?: string
  body: string
  /**
   * Money. NEVER interpolated into title/body by the caller; render.ts decides whether
   * it may appear on a lock screen based on the customer's preference (APP-035).
   */
  amount?: number | null
  /**
   * For state-carrying categories (brokerage_health). Only an actual transition
   * notifies; re-reporting the same state does not.
   */
  state?: string | null
}

export interface PushMessage {
  to: string
  title: string
  subtitle?: string
  body: string
  sound: 'default' | null
  priority: 'default' | 'high'
  channelId: string
  ttl: number
  data: Record<string, unknown>
}
