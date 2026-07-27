/**
 * Server-side mirror of the analytics event allowlist.
 *
 * This is NOT a formality. The client union in `@/lib/analytics` stops a
 * developer from *authoring* a bad event; this stops anyone from *posting*
 * one. The endpoint is public, so without a strict allowlist here it would be
 * an open write channel into our logs — which is exactly how a log store ends
 * up holding data section 19.2 forbids.
 *
 * Everything is an enum or a bounded primitive. There is no free-form string
 * field except `target_route` (path only) and `error_code` (screaming snake),
 * both of which are pattern-checked.
 */

const PERIODS = new Set(['7d', '30d'])
const BOTS = new Set(['all', 'spark', 'flame'])
const VIEWPORTS = new Set(['mobile', 'tablet', 'desktop'])
const REFERRERS = new Set(['direct', 'internal', 'external', 'search', 'social'])
const AUTH = new Set(['anonymous', 'authenticated'])
const CTAS = new Set(['create_account', 'start_trial'])
const PLANS = new Set(['automate', 'none'])
const DIRECTIONS = new Set(['next', 'prev'])
const COMPONENTS = new Set(['summary', 'trade_log'])

const ERROR_CODE_RE = /^[A-Z_]{3,40}$|^network$/
const ROUTE_RE = /^\/[A-Za-z0-9/_-]{0,63}$/
const REQUEST_ID_RE = /^[\w.:-]{1,128}$/

type Props = Record<string, unknown>

/** Every allowed event, with an exact key set and a validator per key. */
const SCHEMA: Record<string, { keys: string[]; check: (p: Props) => boolean }> = {
  bot_ledger_view: {
    keys: ['period', 'viewport_class', 'referrer_class', 'auth_state'],
    check: (p) =>
      PERIODS.has(p.period as string) &&
      VIEWPORTS.has(p.viewport_class as string) &&
      REFERRERS.has(p.referrer_class as string) &&
      AUTH.has(p.auth_state as string),
  },
  period_change: {
    keys: ['from_period', 'to_period'],
    check: (p) => PERIODS.has(p.from_period as string) && PERIODS.has(p.to_period as string),
  },
  bot_filter_change: {
    keys: ['from_bot', 'to_bot'],
    check: (p) => BOTS.has(p.from_bot as string) && BOTS.has(p.to_bot as string),
  },
  cta_click: {
    keys: ['cta_name', 'placement', 'target_route', 'plan'],
    check: (p) =>
      CTAS.has(p.cta_name as string) &&
      p.placement === 'hero' &&
      typeof p.target_route === 'string' &&
      ROUTE_RE.test(p.target_route) &&
      PLANS.has(p.plan as string),
  },
  trade_log_page: {
    keys: ['direction', 'page_size', 'bot_filter'],
    check: (p) =>
      DIRECTIONS.has(p.direction as string) &&
      Number.isInteger(p.page_size) &&
      (p.page_size as number) >= 1 &&
      (p.page_size as number) <= 100 &&
      BOTS.has(p.bot_filter as string),
  },
  ledger_error: {
    keys: ['component', 'error_code', 'request_id'],
    check: (p) =>
      COMPONENTS.has(p.component as string) &&
      typeof p.error_code === 'string' &&
      ERROR_CODE_RE.test(p.error_code) &&
      (p.request_id === null ||
        (typeof p.request_id === 'string' && REQUEST_ID_RE.test(p.request_id))),
  },
}

export interface ValidEvent {
  name: string
  props: Props
}

/**
 * Returns the event if it matches the allowlist exactly, else null.
 *
 * Rejects unknown names, missing keys, and — critically — any EXTRA key, so a
 * caller cannot smuggle a field through by appending it to a valid event.
 */
export function validateEvent(raw: unknown): ValidEvent | null {
  if (!raw || typeof raw !== 'object') return null
  const { name, props } = raw as { name?: unknown; props?: unknown }
  if (typeof name !== 'string') return null

  const spec = SCHEMA[name]
  if (!spec) return null
  if (!props || typeof props !== 'object' || Array.isArray(props)) return null

  const p = props as Props
  const keys = Object.keys(p)
  if (keys.length !== spec.keys.length) return null
  for (const k of spec.keys) if (!keys.includes(k)) return null
  if (!spec.check(p)) return null

  // Rebuild from the schema rather than passing the caller's object through,
  // so nothing non-enumerable or prototype-borne survives.
  const clean: Props = {}
  for (const k of spec.keys) clean[k] = p[k]
  return { name, props: clean }
}

export const MAX_EVENTS_PER_REQUEST = 20
export const ALLOWED_EVENT_NAMES = Object.keys(SCHEMA)
