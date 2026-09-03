/**
 * Turns a NotificationEvent into a wire-ready push message.
 *
 * PURE — no DB, no network, no clock. That is deliberate: APP-035's rule that account
 * values must not appear on a lock screen by default becomes a property that can be
 * asserted for every category x preference combination, rather than a convention
 * someone has to remember while writing copy.
 */
import { appSchemeUrl, safeAppRoute } from '@/lib/mobile/deep-link'
import type { NotificationEvent, PushMessage, NotificationCategory } from '@/lib/push/types'

export interface RenderPrefs {
  showAmountsOnLockscreen: boolean
}

/** Android notification channels. Separate channels let a customer mute one class in OS settings. */
const CHANNEL: Record<NotificationCategory, string> = {
  trade_opened: 'trades',
  trade_closed: 'trades',
  trade_approval: 'approvals',
  brokerage_health: 'account',
  billing: 'account',
  community: 'community',
}

/** Approvals expire in 5 minutes; a push that outlives the decision is noise. */
const TTL_SEC: Record<NotificationCategory, number> = {
  trade_opened: 900,
  trade_closed: 900,
  trade_approval: 300,
  brokerage_health: 1800,
  billing: 86400,
  community: 3600,
}

export function formatAmount(n: number): string {
  const sign = n >= 0 ? '+' : '-'
  return `${sign}$${Math.abs(n).toFixed(2)}`
}

/**
 * Anything that looks like money. Used both to APPEND an amount when permitted and as
 * the assertion target in tests — matching on a regex rather than a snapshot means a
 * reworded string cannot quietly start leaking a balance.
 */
export const CURRENCY_RE = /[$€£]|\d[\d,]*\.\d{2}/

const AGENT_BOTS = new Set(['spark', 'flame'])

/**
 * The mobile app's notification tap handler (src/notifications/route-for.ts) routes
 * on three flat `data` keys — `trade_id`, `agent`, `kind` — rather than parsing
 * `route`/`params`, because `routeParams` is producer-defined free text (an approval
 * uses `approvalId`, a brokerage alert uses `connectionId`, a trade event uses
 * whatever key the scanner happened to name it). Deriving these here, once,
 * server-side, means every producer's naming choice still lands on a deep link the
 * app actually knows how to open, instead of every future producer having to
 * remember the exact key the client expects.
 */
function deriveNavKeys(event: NotificationEvent): { trade_id?: string; agent?: string; kind?: string } {
  const params = event.routeParams ?? {}
  const tradeId = params.tradeId ?? params.trade_id ?? params.positionId ?? params.position_id
  const agent = params.agent ?? params.bot ?? params.account
  const nav: { trade_id?: string; agent?: string; kind?: string } = {}
  if (typeof tradeId === 'string' && tradeId) nav.trade_id = tradeId
  if (typeof agent === 'string' && AGENT_BOTS.has(agent)) nav.agent = agent
  if (event.category === 'brokerage_health') nav.kind = 'brokerage'
  else if (event.category === 'billing') nav.kind = 'billing'
  return nav
}

export function renderNotification(
  event: NotificationEvent,
  prefs: RenderPrefs,
): PushMessage & { data: { v: number } } {
  const route = safeAppRoute(event.route)
  const params = event.routeParams ?? {}

  // The money rule. Default is OFF, so a customer who has never opened notification
  // settings does not get their P&L displayed on a locked phone in public.
  const mayShowAmount = prefs.showAmountsOnLockscreen && typeof event.amount === 'number'
  const body = mayShowAmount
    ? `${event.body} ${formatAmount(event.amount as number)}`
    : event.body

  return {
    to: '', // filled per-device by dispatch
    title: event.title,
    body,
    sound: 'default',
    priority: event.category === 'trade_approval' ? 'high' : 'default',
    channelId: CHANNEL[event.category],
    ttl: TTL_SEC[event.category],
    data: {
      v: 1,
      type: event.category,
      route,
      params,
      // Derived server-side from the allowlisted route — never accepted from the
      // event producer, so a compromised producer cannot aim a tap at an arbitrary URL.
      url: appSchemeUrl(route, params),
      eventKey: event.eventKey,
      occurredAt: event.occurredAt,
      // The amount ALWAYS travels here regardless of the lock-screen preference: the
      // app is behind biometrics, so showing it after unlock is fine. Only the visible
      // title/body are redacted.
      ...(typeof event.amount === 'number' ? { amount: event.amount } : {}),
      ...deriveNavKeys(event),
    },
  }
}
