/**
 * The dev-handoff's named mobile analytics events (mb-events), mirrored from
 * the webapp's `src/lib/analytics/events.ts` allowlist. Kept as a separate,
 * small copy rather than a shared package (mobile already keeps its own API
 * types for the same reason — src/api/types.ts) so this file has no build
 * dependency on the webapp at all.
 *
 * This is the enforcement mechanism for trackEvent(): a name not in this map
 * is dropped client-side before it ever reaches the network, the same way
 * the server allowlist drops it a second time if a client falls out of date.
 */
export const MOBILE_ANALYTICS_EVENTS = {
  app_open: [],
  tab_view: ['tab'],
  period_select: ['period'],
  chart_scrub: [],
  agent_sheet_open: ['agent'],
  trade_sheet_open: [],
  add_agent_start: ['agent'],
  add_agent_complete: ['agent'],
  agent_pause: ['agent'],
  agent_resume: ['agent'],
  pause_all: [],
  community_post: [],
  community_like: [],
  community_reply: [],
  sparky_question: ['mode'],
  push_open: ['type'],
  theme_toggle: ['theme'],
} as const

export type MobileAnalyticsEventName = keyof typeof MOBILE_ANALYTICS_EVENTS

export function isAllowedMobileEvent(name: string): name is MobileAnalyticsEventName {
  return Object.prototype.hasOwnProperty.call(MOBILE_ANALYTICS_EVENTS, name)
}
