/**
 * The analytics event allowlist — every event name POST /api/v1/events will
 * accept, taken verbatim from the dev handoff's three "Analytics events"
 * tables (public site ps-events, enrollment en-events, mobile mb-events).
 *
 * This is the enforcement mechanism, not documentation: the route rejects any
 * event name not in this set with 400, so a typo or an attacker-supplied name
 * can never create a new, unreviewed series in `analytics_events`. Adding a
 * real new event means editing this file, which a reviewer will see.
 *
 * Property NAMES are also allowlisted per event (loosely — this is telemetry,
 * not a schema migration) so a caller cannot smuggle an arbitrary key through
 * `props`. Unlisted keys are dropped, not rejected, the same way the PII scrub
 * drops rather than 400s — a bad prop should never block the import of the
 * part of the event that IS valid.
 */

export const ANALYTICS_EVENTS = {
  // --- Public site (ps-events) ---
  cta_click: ['cta', 'placement'],
  agent_filter: ['filter'],
  hero_chart_tab: ['agent'],
  waitlist_open: ['placement', 'capitalRange'],
  waitlist_submit: ['placement', 'capitalRange'],
  waitlist_error: ['placement', 'field'],
  section_view: ['section'],

  // --- Enrollment (en-events) ---
  enroll_step_view: ['step'],
  enroll_step_complete: ['step', 'ms_on_step'],
  enroll_sso: ['provider'],
  legal_accept_all: [],
  agent_selected: ['agent'],
  broker_connect_start: ['provider'],
  broker_connect_success: ['provider'],
  broker_connect_cancel: ['provider'],
  broker_connect_error: ['provider'],
  ember_balance_block: [],
  billing_trial_started: ['agent'],
  enroll_complete: ['agent'],

  // --- Mobile app (mb-events) ---
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

export type AnalyticsEventName = keyof typeof ANALYTICS_EVENTS

export function isAllowedEvent(name: unknown): name is AnalyticsEventName {
  return typeof name === 'string' && Object.prototype.hasOwnProperty.call(ANALYTICS_EVENTS, name)
}

/** Drop any prop key not declared for this event. */
export function allowedPropsFor(name: AnalyticsEventName, props: Record<string, unknown> | null | undefined) {
  if (!props) return null
  const allowed = new Set<string>(ANALYTICS_EVENTS[name] as readonly string[])
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(props)) {
    if (allowed.has(k)) out[k] = v
  }
  return Object.keys(out).length > 0 ? out : null
}

export const ANALYTICS_SURFACES = ['web', 'ios', 'android'] as const
export type AnalyticsSurface = (typeof ANALYTICS_SURFACES)[number]

export function isAllowedSurface(s: unknown): s is AnalyticsSurface {
  return typeof s === 'string' && (ANALYTICS_SURFACES as readonly string[]).includes(s)
}

/** Enrollment steps the funnel in /api/ops/analytics/summary reports on, in rail order. */
export const ENROLL_FUNNEL_STEPS = ['account', 'legal', 'plan', 'broker', 'billing', 'review', 'done'] as const
